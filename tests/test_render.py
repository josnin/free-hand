import re

from free_hand.render import preview_call, render_activity

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_edit_preview_shows_diff_with_line_numbers(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    args = {"path": "a.py", "old_text": "two", "new_text": "TWO"}
    text = preview_call(tmp_path, "edit_file", args, color=False)
    assert "Edit a.py (+1 -1)" in text
    assert "    2 - two" in text
    assert "    2 + TWO" in text
    assert "    1   one" in text


def test_edit_preview_warns_when_old_text_is_ambiguous(tmp_path):
    (tmp_path / "a.py").write_text("x\nx\n", encoding="utf-8")
    text = preview_call(tmp_path, "edit_file", {"path": "a.py", "old_text": "x", "new_text": "y"}, color=False)
    assert "matches 2 times" in text


def test_write_preview_lists_added_lines_and_colors_them(tmp_path):
    args = {"path": "n.txt", "content": "a\nb\n"}
    assert "Create n.txt (+2 -0)" in preview_call(tmp_path, "write_file", args, color=False)
    colored = preview_call(tmp_path, "write_file", args, color=True)
    assert "\x1b[32m" in colored
    assert "    1 + a" in ANSI_RE.sub("", colored)


def test_activity_summarizes_without_json_payloads():
    response = {"tool_calls": [
        {"id": "1", "type": "function", "function": {"name": "read_file", "arguments": {"path": "a.py"}}},
        {"id": "2", "type": "function", "function": {"name": "run_command", "arguments": {"argv": ["pytest", "-q"]}}},
    ]}
    result = {"results": [
        {"id": "1", "name": "read_file", "status": "success", "output": "a\nb\n"},
        {"id": "2", "name": "run_command", "status": "failure", "error": "TimeoutExpired: slow"},
    ], "final_message": "Done"}
    text = render_activity(response, result, color=False)
    assert "✓ read_file a.py" in text
    assert "2 lines" in text
    assert "✗ run_command pytest -q" in text
    assert "TimeoutExpired: slow" in text
    assert '"status"' not in text
