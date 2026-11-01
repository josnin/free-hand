import io
import json
from pathlib import Path

from free_hand.color import (
    RESET,
    colorize_json,
    paint,
    render_results,
    supports_color,
)


class _TTY(io.StringIO):
    def isatty(self):
        return True


class _NoTTY(io.StringIO):
    def isatty(self):
        return False


def test_supports_color_true_for_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert supports_color(_TTY()) is True


def test_supports_color_false_for_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert supports_color(_NoTTY()) is False


def test_supports_color_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("TERM", raising=False)
    assert supports_color(_TTY()) is False


def test_supports_color_respects_dumb_term(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert supports_color(_TTY()) is False


def test_paint_wraps_and_resets():
    assert paint("hi", "\x1b[32m") == "\x1b[32mhi" + RESET


def test_render_results_plain_is_valid_json_identity():
    result = {
        "version": 1,
        "results": [
            {"id": "1", "name": "read_file", "status": "success", "output": "ok"},
            {"id": "2", "name": "run_command", "status": "failure", "error": "boom"},
        ],
        "final_message": "done",
    }
    text = render_results(result, color=False)
    assert text == json.dumps(result, indent=2, ensure_ascii=False)
    assert "\x1b[" not in text


def test_render_results_color_adds_ansi_and_keeps_structure():
    result = {
        "version": 1,
        "results": [{"id": "1", "name": "x", "status": "success"}],
        "final_message": "done",
    }
    text = render_results(result, color=True)
    assert "\x1b[" in text
    assert "success" in text
    # Stripping ANSI must recover valid JSON (module docstring promises value fidelity).
    import re

    stripped = re.sub(r"\x1b\[[0-9;]*m", "", text)
    assert json.loads(stripped) == result


def test_colorize_json_colors_status_values():
    text = json.dumps({"results": [{"status": "failure"}]})
    colored = colorize_json(text)
    assert "\x1b[31m" in colored  # red
    import re

    stripped = re.sub(r"\x1b\[[0-9;]*m", "", colored)
    assert json.loads(stripped) == {"results": [{"status": "failure"}]}
