import json

import pytest

from free_hand import cli


def test_run_saves_latest_results_and_results_command_prints_clean_json(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    response = '{"version":1,"tool_calls":[],"final_message":"No tools needed."}'

    copied = {}
    monkeypatch.setattr(cli, "write_clipboard", lambda value: copied.setdefault("value", value))
    assert cli.main(["run", "--input", _write_response(tmp_path, response)]) == 0
    assert json.loads(copied["value"])["results"] == []
    capsys.readouterr()

    saved_path = tmp_path / ".free-hand" / "last-results.json"
    assert saved_path.is_file()
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["results"] == []

    assert cli.main(["results"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output) == saved


def test_results_command_reports_missing_results(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["results"]) == 2
    assert "No saved results yet" in capsys.readouterr().err


def test_results_file_option_prints_path(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / ".free-hand" / "last-results.json"
    saved.parent.mkdir()
    saved.write_text('{"results": []}\n', encoding="utf-8")

    assert cli.main(["results", "--file"]) == 0
    assert capsys.readouterr().out.strip() == str(saved)


def _write_response(root, content):
    path = root / "response.json"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_results_copy_option_copies_saved_results_and_prints_json(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / ".free-hand" / "last-results.json"
    saved.parent.mkdir()
    payload = {"results": [], "final_message": "Ready"}
    saved.write_text(json.dumps(payload), encoding="utf-8")
    copied = {}
    monkeypatch.setattr(cli, "write_clipboard", lambda value: copied.setdefault("value", value))

    assert cli.main(["results", "--copy"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload
    assert json.loads(copied["value"]) == payload
    assert "copied to clipboard" in captured.err


def test_results_copy_option_falls_back_to_printed_json_when_clipboard_unavailable(monkeypatch, tmp_path, capsys):
    from free_hand.clipboard import ClipboardError

    monkeypatch.chdir(tmp_path)
    saved = tmp_path / ".free-hand" / "last-results.json"
    saved.parent.mkdir()
    payload = {"results": []}
    saved.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cli, "write_clipboard", lambda value: (_ for _ in ()).throw(ClipboardError("no clipboard")))

    assert cli.main(["results", "--copy"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload
    assert "Warning: no clipboard" in captured.err


def test_run_input_automatically_copies_results(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    response = '{"version":1,"tool_calls":[],"final_message":"Manual input."}'
    response_file = tmp_path / "response.json"
    response_file.write_text(response, encoding="utf-8")
    copied = {}
    monkeypatch.setattr(cli, "write_clipboard", lambda value: copied.setdefault("value", value))

    assert cli.main(["run", "--input", str(response_file)]) == 0
    captured = capsys.readouterr()
    assert json.loads(copied["value"])["results"] == []
    assert "copied to clipboard" in captured.err
    assert "Manual input." in captured.out
    assert '"results"' not in captured.out


def test_interactive_session_processes_multiple_responses_until_exit(monkeypatch, tmp_path, capsys):
    import io

    monkeypatch.chdir(tmp_path)
    response = '{"version":1,"tool_calls":[],"final_message":"Turn"}'
    pasted = response + "\nEND\n" + response + "\nEND\nexit\n"

    class TTYInput(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(cli.sys, "stdin", TTYInput(pasted))
    copied = []
    monkeypatch.setattr(cli, "write_clipboard", lambda value: copied.append(json.loads(value)))

    assert cli.main(["run"]) == 0
    assert len(copied) == 2
    assert (tmp_path / ".free-hand" / "last-results.json").is_file()
    assert "Leaving Free-hand session" in capsys.readouterr().out


def test_interactive_session_survives_invalid_json_and_accepts_next_turn(monkeypatch, tmp_path, capsys):
    import io

    monkeypatch.chdir(tmp_path)
    good = '{"version":1,"tool_calls":[],"final_message":"Good"}'
    pasted = "{not json}\nEND\n" + good + "\nEND\nexit\n"

    class TTYInput(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(cli.sys, "stdin", TTYInput(pasted))
    copied = []
    monkeypatch.setattr(cli, "write_clipboard", lambda value: copied.append(value))

    assert cli.main(["run"]) == 0
    assert len(copied) == 1
    assert "still active" in capsys.readouterr().err


def test_run_rejects_legacy_clipboard_flags(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--clipboard"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--copy"])
    assert exc.value.code == 2
