from free_hand.clipboard import ClipboardError, _run


def test_run_passes_text_as_stdin_without_shell(monkeypatch):
    import subprocess

    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _run(["clipboard-tool", "--option"], text="hello") == ""
    assert observed["command"] == ["clipboard-tool", "--option"]
    assert observed["kwargs"]["input"] == "hello"
    assert observed["kwargs"]["shell"] is False


def test_run_reports_nonzero_clipboard_command(monkeypatch):
    import subprocess
    import pytest

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr="no clipboard"),
    )
    with pytest.raises(ClipboardError, match="could not access the clipboard"):
        _run(["clipboard-tool"])


def test_osc52_writes_to_interactive_terminal(monkeypatch):
    import io
    import base64
    from free_hand import clipboard

    class TTY(io.StringIO):
        def isatty(self):
            return True

    stream = TTY()
    monkeypatch.setattr(clipboard.sys, "stdout", stream)
    assert clipboard._write_osc52("hello clipboard") is True
    output = stream.getvalue()
    assert output.startswith("\x1b]52;c;")
    encoded = output[len("\x1b]52;c;"):-1]
    assert base64.b64decode(encoded).decode() == "hello clipboard"


def test_osc52_skips_non_tty(monkeypatch):
    import io
    from free_hand import clipboard

    stream = io.StringIO()
    monkeypatch.setattr(clipboard.sys, "stdout", stream)
    assert clipboard._write_osc52("hello") is False
    assert stream.getvalue() == ""


def test_wayland_socket_must_exist(monkeypatch, tmp_path):
    from free_hand import clipboard

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert clipboard._wayland_socket_available() is False


def test_decode_osc52_clipboard_reply_bel_and_st():
    import base64
    from free_hand.clipboard import _decode_osc52_response

    encoded = base64.b64encode("hello from terminal".encode())
    assert _decode_osc52_response(b"\x1b]52;c;" + encoded + b"\x07") == "hello from terminal"
    assert _decode_osc52_response(b"\x1b]52;c;" + encoded + b"\x1b\\") == "hello from terminal"


def test_decode_osc52_denied_or_invalid_reply():
    from free_hand.clipboard import _decode_osc52_response

    assert _decode_osc52_response(b"\x1b]52;c;?\x07") is None
    assert _decode_osc52_response(b"\x1b]52;c;not-base64!\x07") is None
    assert _decode_osc52_response(b"unrelated terminal output") is None


def test_linux_read_clipboard_uses_osc52_when_no_native_backend(monkeypatch):
    from free_hand import clipboard

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(clipboard, "_wayland_socket_available", lambda: False)
    monkeypatch.setattr(clipboard, "_read_osc52", lambda: "clipboard from terminal")
    assert clipboard.read_clipboard() == "clipboard from terminal"


def test_linux_read_clipboard_tries_osc52_after_native_backend_fails(monkeypatch):
    from free_hand import clipboard

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(clipboard, "_wayland_socket_available", lambda: False)
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: "/usr/bin/xclip" if name == "xclip" else None)
    monkeypatch.setattr(
        clipboard,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(clipboard.ClipboardError("native clipboard unavailable")),
    )
    monkeypatch.setattr(clipboard, "_read_osc52", lambda: "terminal clipboard")
    assert clipboard.read_clipboard() == "terminal clipboard"



def test_wayland_uses_default_socket_when_display_is_unset(monkeypatch, tmp_path):
    from free_hand import clipboard
    import socket

    runtime = tmp_path
    sock_path = runtime / "wayland-0"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    try:
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
        assert clipboard._wayland_socket_available() is True
    finally:
        server.close()


def test_read_osc52_sends_query_and_restores_terminal(monkeypatch):
    import base64
    from free_hand import clipboard
    import termios
    import tty

    fd = 77
    response = b"\x1b]52;c;" + base64.b64encode(b"from desktop clipboard") + b"\x07"
    calls = {"written": b"", "restored": False, "closed": False}
    monkeypatch.setattr(clipboard.os, "open", lambda *args: fd)
    monkeypatch.setattr(clipboard.os, "isatty", lambda value: value == fd)
    monkeypatch.setattr(clipboard.os, "write", lambda value, data: calls.__setitem__("written", data) or len(data))
    monkeypatch.setattr(clipboard.os, "read", lambda value, size: response)
    monkeypatch.setattr(clipboard.os, "close", lambda value: calls.__setitem__("closed", True))
    monkeypatch.setattr(clipboard.select, "select", lambda *args: ([fd], [], []))
    monkeypatch.setattr(termios, "tcgetattr", lambda value: ["saved-terminal-mode"])
    monkeypatch.setattr(termios, "tcsetattr", lambda *args: calls.__setitem__("restored", True))
    monkeypatch.setattr(tty, "setraw", lambda *args: None)

    assert clipboard._read_osc52() == "from desktop clipboard"
    assert calls["written"] == b"\x1b]52;c;?\x07"
    assert calls["restored"] is True
    assert calls["closed"] is True


def test_wsl_clipboard_backend_uses_powershell(monkeypatch):
    from free_hand import clipboard

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe" if name == "powershell.exe" else None)
    monkeypatch.setattr(clipboard, "_run", lambda command, **kwargs: "windows clipboard")
    assert clipboard.read_clipboard() == "windows clipboard"
