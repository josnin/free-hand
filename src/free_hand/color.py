"""Dependency-free ANSI color helpers for human-friendly terminal output."""
from __future__ import annotations

import os
import sys
from typing import IO, Any

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
CYAN = "\x1b[36m"

STATUS_COLORS = {
    "success": GREEN,
    "failure": RED,
    "rejected": RED,
    "skipped": YELLOW,
}


def supports_color(stream: IO[str] | None = None) -> bool:
    """Return True only when it is safe and appropriate to emit ANSI color."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    target = stream if stream is not None else sys.stdout
    try:
        return bool(target.isatty())
    except (AttributeError, OSError):
        return False


def paint(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def colorize_json(text: str) -> str:
    """Colorize keys, string values, and status values in already-valid JSON.

    This works on the serialized envelope produced by json.dumps; it is not a
    general JSON highlighter and never feeds its output back into a parser.
    """
    import re

    key_pattern = re.compile(r'^(\s*)("(?:[^"\\]|\\.)*")(\s*:)(.*)$')
    value_pattern = re.compile(r'("status"\s*:\s*)"([a-z]+)"')

    lines = text.split("\n")
    out = []
    for line in lines:
        match = key_pattern.match(line)
        if match:
            indent, key, colon, rest = match.groups()
            line = f"{indent}{paint(key, CYAN)}{colon}{rest}"
        out.append(line)
    joined = "\n".join(out)

    def status_repl(match: re.Match[str]) -> str:
        prefix, value = match.group(1), match.group(2)
        code = STATUS_COLORS.get(value)
        if code is None:
            return match.group(0)
        return f'{prefix}{paint(chr(34) + value + chr(34), code)}'

    return value_pattern.sub(status_repl, joined)


def render_results(result: dict[str, Any], color: bool) -> str:
    """Render a results envelope; identical to json.dumps when color is False."""
    import json

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if not color:
        return text
    return colorize_json(text)
