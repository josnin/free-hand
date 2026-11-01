import io

from free_hand import cli
from free_hand.color import CYAN


class _TTY(io.StringIO):
    def isatty(self):
        return True


def test_fh_prompt_cyan_on_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    captured = io.StringIO()

    class _TTYIn(io.StringIO):
        def isatty(self):
            return True

    class _TTYOut(io.StringIO):
        def isatty(self):
            return True

    fake_out = _TTYOut()
    monkeypatch.setattr(cli.sys, "stdout", fake_out)
    monkeypatch.setattr(cli.sys, "stdin", _TTYIn("exit\n"))
    monkeypatch.chdir(__import__("pathlib").Path.cwd())

    assert cli.interactive_session() == 0
    out = fake_out.getvalue()
    assert CYAN in out


def test_fh_prompt_plain_on_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)

    class _TTYIn(io.StringIO):
        def isatty(self):
            return True

    class _NoTTYOut(io.StringIO):
        def isatty(self):
            return False

    fake_out = _NoTTYOut()
    monkeypatch.setattr(cli.sys, "stdout", fake_out)
    monkeypatch.setattr(cli.sys, "stdin", _TTYIn("exit\n"))

    assert cli.interactive_session() == 0
    out = fake_out.getvalue()
    assert CYAN not in out
    assert "fh> " in out
