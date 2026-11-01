"""Human-friendly previews and activity summaries for tool calls.

Nothing here feeds the JSON protocol: saved and clipboard results stay JSON.
"""
from __future__ import annotations

import difflib
import json
import re
import shlex
from pathlib import Path
from typing import Any

from .color import BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint
from .tools.filesystem import safe_path

CONTEXT_LINES = 3
MAX_PREVIEW_LINES = 60
MAX_DETAIL_CHARS = 200
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _style(text: str, code: str, color: bool) -> str:
    return paint(text, code) if color else text


def _count_lines(text: str) -> int:
    return len(text.splitlines())


def format_diff(old: str, new: str, color: bool) -> tuple[list[str], int, int]:
    """Return rendered diff lines plus added and removed line counts."""
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", n=CONTEXT_LINES
    )
    out: list[str] = []
    added = removed = 0
    old_no = new_no = 0
    for line in diff:
        if line.startswith(("---", "+++")):
            continue
        hunk = _HUNK.match(line)
        if hunk:
            old_no, new_no = int(hunk.group(1)), int(hunk.group(2))
            if out:
                out.append(_style("      ⋮", DIM, color))
            continue
        marker, text = line[0], line[1:]
        if marker == "+":
            added += 1
            out.append(_style(f"{new_no:>5} + {text}", GREEN, color))
            new_no += 1
        elif marker == "-":
            removed += 1
            out.append(_style(f"{old_no:>5} - {text}", RED, color))
            old_no += 1
        else:
            out.append(_style(f"{new_no:>5}   {text}", DIM, color))
            old_no += 1
            new_no += 1
    return out, added, removed


def _cap(lines: list[str], color: bool) -> list[str]:
    if len(lines) <= MAX_PREVIEW_LINES:
        return lines
    hidden = len(lines) - MAX_PREVIEW_LINES
    return lines[:MAX_PREVIEW_LINES] + [_style(f"      … {hidden} more lines", DIM, color)]


def _header(verb: str, target: str, color: bool, stats: str = "") -> str:
    head = f"{_style('●', CYAN, color)} {_style(verb, BOLD, color)} {target}"
    return f"{head} {_style(stats, DIM, color)}".rstrip()


def _stats(added: int, removed: int, color: bool) -> str:
    return f"({_style(f'+{added}', GREEN, color)} {_style(f'-{removed}', RED, color)})" if color else f"(+{added} -{removed})"


def _preview_edit(root: Path, args: dict[str, Any], color: bool) -> str:
    path, old_text, new_text = args["path"], args["old_text"], args["new_text"]
    notes: list[str] = []
    try:
        content = safe_path(root, path).read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeError) as exc:
        content = None
        notes.append(f"Cannot read current file: {exc}")
    if content is not None and content.count(old_text) == 1:
        before, after = content, content.replace(old_text, new_text, 1)
    else:
        if content is not None:
            notes.append(f"old_text matches {content.count(old_text)} times; this edit will fail.")
        before, after = old_text, new_text
    lines, added, removed = format_diff(before, after, color)
    out = [_header("Edit", path, color, _stats(added, removed, color))]
    out += [_style(f"  {note}", YELLOW, color) for note in notes]
    out += _cap(lines, color)
    return "\n".join(out)


def _preview_write(args: dict[str, Any], color: bool) -> str:
    content = args["content"]
    lines = [_style(f"{number:>5} + {text}", GREEN, color) for number, text in enumerate(content.splitlines(), 1)]
    count = _count_lines(content)
    return "\n".join(
        [_header("Create", args["path"], color, _stats(count, 0, color))] + _cap(lines, color)
    )


def preview_call(root: Path, name: str, args: dict[str, Any], color: bool) -> str:
    """Describe a pending tool call the way a code editor would show it."""
    try:
        return _preview_known(root, name, args, color)
    except (KeyError, TypeError):
        return f"Arguments:\n{json.dumps(args, indent=2, ensure_ascii=False)}"


def _preview_known(root: Path, name: str, args: dict[str, Any], color: bool) -> str:
    if name == "edit_file":
        return _preview_edit(root, args, color)
    if name == "write_file":
        return _preview_write(args, color)
    if name == "run_command":
        return f"{_header('Run', '', color)}\n  {_style('$', DIM, color)} {shlex.join(args['argv'])}"
    if name == "git_stage":
        return "\n".join([_header("Stage", "", color)] + [f"  {path}" for path in args["paths"]])
    if name == "git_commit":
        message = args.get("message") or "(default message)"
        return f"{_header('Commit', '', color)}\n  {message}"
    return f"Arguments:\n{json.dumps(args, indent=2, ensure_ascii=False)}"


def _target(name: str, args: dict[str, Any]) -> str:
    if "path" in args:
        return args["path"]
    if name == "run_command":
        return shlex.join(args.get("argv", []))
    if name == "list_files":
        return args.get("pattern", "**/*")
    if name == "search_files":
        return repr(args.get("query", ""))
    if name == "git_stage":
        return ", ".join(args.get("paths", []))
    if name == "git_diff":
        return ("staged " if args.get("staged") else "") + ", ".join(args.get("paths", []))
    if name == "git_commit":
        return args.get("message", "")
    return ""


def _detail(name: str, item: dict[str, Any]) -> str:
    if item["status"] == "failure":
        return item.get("error", "")
    output = item.get("output", "")
    if item["status"] != "success":
        return output
    if name == "read_file":
        return f"{_count_lines(output)} lines"
    if name in {"list_files", "search_files"}:
        return f"{_count_lines(output)} matches"
    if name == "run_command":
        return output.split("\n", 1)[0].replace("exit_code=", "exit code ")
    if name in {"git_status", "git_diff"}:
        return f"{_count_lines(output)} lines"
    return output.strip().splitlines()[0] if output.strip() else ""


def render_activity(response: dict[str, Any], result: dict[str, Any], color: bool) -> str:
    """Summarize one executed batch: one line per call, no JSON payloads."""
    calls = {call["id"]: call["function"]["arguments"] for call in response["tool_calls"]}
    icons = {"success": ("✓", GREEN), "failure": ("✗", RED), "rejected": ("✗", RED), "skipped": ("–", YELLOW)}
    out: list[str] = []
    for item in result["results"]:
        icon, code = icons.get(item["status"], ("•", DIM))
        args = calls.get(item["id"], {})
        line = f"{_style(icon, code, color)} {_style(item['name'], BOLD, color)} {_target(item['name'], args)}".rstrip()
        detail = _detail(item["name"], item).strip()
        if detail:
            if len(detail) > MAX_DETAIL_CHARS:
                detail = detail[:MAX_DETAIL_CHARS] + "…"
            line += f"\n    {_style(detail, DIM if item['status'] == 'success' else code, color)}"
        out.append(line)
    if result.get("final_message"):
        out.append(f"\n{result['final_message']}")
    return "\n".join(out)
