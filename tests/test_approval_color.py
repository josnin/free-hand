import io
import json
import re
from pathlib import Path

import pytest

from free_hand import cli
from free_hand.color import RESET, RISK_COLORS
from free_hand.registry import Tool

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _TTY(io.StringIO):
    def isatty(self):
        return True


class _NoTTY(io.StringIO):
    def isatty(self):
        return False


def _tool(risk: str) -> Tool:
    return Tool(
        name="run_command",
        description="x",
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        handler=lambda a: "ok",
        risk=risk,
    )


def test_approval_color_on_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    tty = _TTY("y\n")
    monkeypatch.setattr(cli.sys, "stdout", tty)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    tool = _tool("command")
    assert cli.approval(tool, {"argv": ["echo", "hi"]}) is True

    out = tty.getvalue()
    assert "\x1b[" in out
    assert "Approval required" in out
    assert "run_command" in out
    # Plain-text (ANSI stripped) still readable
    stripped = ANSI_RE.sub("", out)
    assert "Approval required for run_command [command]" in stripped
    assert json.loads(stripped.split("Arguments:\n", 1)[1]) == {"argv": ["echo", "hi"]}


def test_approval_plain_on_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    stream = _NoTTY()
    monkeypatch.setattr(cli.sys, "stdout", stream)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    assert cli.approval(_tool("write"), {"path": "a"}) is False
    out = stream.getvalue()
    assert "\x1b[" not in out
    assert "Approval required for run_command [write]" in out


def test_approval_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("TERM", raising=False)
    tty = _TTY()
    monkeypatch.setattr(cli.sys, "stdout", tty)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    cli.approval(_tool("git"), {"paths": ["a"]})
    assert "\x1b[" not in tty.getvalue()


def test_risk_colors_cover_all_risks():
    for risk in ("read", "write", "git", "command"):
        assert risk in RISK_COLORS
        assert RISK_COLORS[risk].endswith("m")
        assert RISK_COLORS[risk] != RESET
