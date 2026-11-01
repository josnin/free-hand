"""Command-line interface for Free-hand."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .clipboard import ClipboardError, write_clipboard
from .color import (
    BOLD,
    CYAN,
    YELLOW,
    paint,
    render_results,
    supports_color,
)
from .config import load_config
from .executor import build_registry, execute_response, validate_arguments
from .history import append_history, read_history
from .prompt import make_system_prompt
from .protocol import ProtocolError, clean_response, parse_response
from .render import preview_call, render_activity


def approval(tool, args) -> bool:
    color = supports_color(sys.stdout)
    if color:
        header = (
            f"\n{paint('Approval required', YELLOW)} for "
            f"{paint(tool.name, BOLD)}"
        )
        prompt = paint("Approve this operation?", YELLOW) + " [y/N] "
    else:
        header = f"\nApproval required for {tool.name} [{tool.risk}]"
        prompt = "Approve this operation? [y/N] "
    print(f"{header}\n{preview_call(Path.cwd().resolve(), tool.name, args, color)}")
    return input(prompt).strip().lower() in {"y", "yes"}


def read_response(path: str | None, max_bytes: int) -> str:
    if path:
        raw = Path(path).read_text(encoding="utf-8")
    else:
        print("Paste the complete JSON response, then press Ctrl-D (macOS/Linux):", file=sys.stderr)
        raw = sys.stdin.read()
    if len(raw.encode("utf-8")) > max_bytes:
        raise ValueError(f"Input exceeds configured limit ({max_bytes} bytes)")
    if not raw.strip():
        raise ValueError("No input received. Paste an AI assistant response.")
    return raw


def run(raw: str, source: str, copy_results: bool = False) -> int:
    root = Path.cwd().resolve()
    config = load_config(root)
    if len(raw.encode("utf-8")) > int(config["max_input_bytes"]):
        raise ValueError(f"Input exceeds configured limit ({config['max_input_bytes']} bytes)")
    response = parse_response(clean_response(raw))
    result = execute_response(
        response,
        build_registry(root, config),
        approval,
        int(config.get("max_output_chars", 20_000)),
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(render_activity(response, result, supports_color(sys.stdout)))

    # Keep the latest result in a predictable file for easy manual copy/paste.
    # The .free-hand directory is ignored by Git by default.
    result_file = root / ".free-hand" / "last-results.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(rendered + "\n", encoding="utf-8")

    print(f"\nFull results saved to {result_file.relative_to(root)}; run `fh results` to print them as JSON.")

    history = root / str(config.get("history_file", ".free-hand/history.jsonl"))
    append_history(history, {"source": source, "result": result})
    if copy_results:
        try:
            write_clipboard(rendered)
            print("\nResults copied to clipboard. Paste them back into your AI chat assistant.", file=sys.stderr)
        except ClipboardError as exc:
            print(f"\nClipboard warning: {exc}", file=sys.stderr)
    return 0 if all(item["status"] in {"success", "skipped"} for item in result["results"]) else 1


def interactive_session() -> int:
    """Accept repeated pasted AI responses until the user exits."""
    print("Free-hand interactive session")
    print("Paste one complete JSON response, then enter END on its own line.")
    print("Results are saved and copied when clipboard support is available.")
    print("Enter exit on an empty prompt, or press Ctrl-C to quit.\n")

    while True:
        prompt_prefix = paint("fh>", CYAN) + " " if supports_color(sys.stdout) else "fh> "
        print(prompt_prefix, end="", flush=True)
        lines: list[str] = []
        total_bytes = 0
        too_large = False
        try:
            while True:
                line = sys.stdin.readline()
                if line == "":
                    if lines:
                        raw = "".join(lines)
                        try:
                            run(raw, "interactive", copy_results=True)
                        except (ValueError, OSError, ProtocolError, ClipboardError, TimeoutError) as exc:
                            print(f"Error: {exc}", file=sys.stderr)
                    print("\nLeaving Free-hand session.", file=sys.stderr)
                    return 0
                marker = line.rstrip("\r\n")
                if not lines and marker.strip().lower() in {"exit", "quit"}:
                    print("Leaving Free-hand session.")
                    return 0
                if marker == "END":
                    break
                lines.append(line)
                total_bytes += len(line.encode("utf-8"))
                if not too_large:
                    config = load_config(Path.cwd().resolve())
                    too_large = total_bytes > int(config["max_input_bytes"])
            if too_large:
                print("Input exceeds configured limit; this response was discarded.", file=sys.stderr)
                continue
            raw = "".join(lines)
            if not raw.strip():
                print("No response received. Paste JSON and finish with END.", file=sys.stderr)
                continue
            try:
                run(raw, "interactive", copy_results=True)
            except (ValueError, OSError, ProtocolError, ClipboardError, TimeoutError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                print("You can paste another response; the session is still active.\n", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nLeaving Free-hand session.")
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fh", description="Human-in-the-loop AI tool-call CLI; no AI API required")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init", help="Create local config")
    prompt_parser = sub.add_parser("prompt", help="Print generated system prompt")
    prompt_parser.add_argument("--copy", action="store_true", help="Copy the generated prompt to the clipboard")
    sub.add_parser("tools", help="List registered tools and schemas")
    run_parser = sub.add_parser("run", help="Start an interactive paste/execute session, or execute a JSON file")
    run_parser.add_argument("--input", help="Read and execute one JSON response from a file")
    v = sub.add_parser("validate", help="Validate JSON without execution")
    v.add_argument("response_json", help="JSON text, or path to a file containing JSON")
    e = sub.add_parser("execute", help="Execute JSON file; risky operations require approval")
    e.add_argument("--input", required=True)
    results_parser = sub.add_parser("results", help="Show the latest execution results as clean JSON")
    results_parser.add_argument("--file", action="store_true", help="Print the path to the saved results file")
    results_parser.add_argument("--copy", action="store_true", help="Copy saved results to the clipboard and also print them")
    h = sub.add_parser("history", help="Show recent history")
    h.add_argument("--limit", type=int, default=20)
    sub.add_parser("config", help="Show effective configuration")
    args = parser.parse_args(argv)

    try:
        root = Path.cwd().resolve()
        config = load_config(root)
        registry = build_registry(root, config)
        if args.command == "init":
            path = root / ".free-hand.json"
            if path.exists():
                print(f"Config already exists: {path}")
            else:
                path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                print(f"Created {path}")
        elif args.command == "prompt":
            prompt = make_system_prompt(registry)
            if args.copy:
                write_clipboard(prompt)
                print("System prompt copied to clipboard.", file=sys.stderr)
            else:
                print(prompt)
        elif args.command == "tools":
            print(json.dumps([{"name": t.name, "description": t.description, "risk": t.risk, "schema": t.schema()} for t in registry.all()], indent=2))
        elif args.command == "validate":
            candidate = Path(args.response_json)
            if not args.response_json.lstrip().startswith(("{", "[")) and candidate.is_file():
                raw = read_response(str(candidate), int(config["max_input_bytes"]))
            else:
                raw = args.response_json
                if len(raw.encode("utf-8")) > int(config["max_input_bytes"]):
                    raise ValueError(f"Input exceeds configured limit ({config['max_input_bytes']} bytes)")
            response = parse_response(raw)
            for call in response["tool_calls"]:
                tool = registry.get(call["function"]["name"])
                if tool is None:
                    raise ValueError(f"Unknown tool: {call['function']['name']}")
                validate_arguments(tool, call["function"]["arguments"])
            print("Valid response.")
        elif args.command == "run":
            if args.input:
                return run(read_response(args.input, int(config["max_input_bytes"])), args.input, copy_results=True)
            if sys.stdin.isatty():
                return interactive_session()
            return run(read_response(None, int(config["max_input_bytes"])), "stdin", copy_results=True)
        elif args.command == "execute":
            return run(read_response(args.input, int(config["max_input_bytes"])), args.input)
        elif args.command == "results":
            result_file = root / ".free-hand" / "last-results.json"
            if not result_file.is_file():
                raise ValueError("No saved results yet. Run `fh run` first.")
            if args.file:
                print(result_file)
            else:
                # Re-parse before printing so this command never emits malformed JSON.
                saved = json.loads(result_file.read_text(encoding="utf-8"))
                rendered = json.dumps(saved, indent=2, ensure_ascii=False)
                if args.copy:
                    try:
                        write_clipboard(rendered)
                        print("Saved results copied to clipboard.", file=sys.stderr)
                    except ClipboardError as exc:
                        print(f"Warning: {exc}", file=sys.stderr)
                print(render_results(saved, color=supports_color(sys.stdout)))
        elif args.command == "history":
            print(json.dumps(read_history(root / str(config["history_file"]), max(1, args.limit)), indent=2, ensure_ascii=False))
        elif args.command == "config":
            print(json.dumps(config, indent=2))
        else:
            parser.print_help()
        return 0
    except (ValueError, OSError, ProtocolError, ClipboardError, TimeoutError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
