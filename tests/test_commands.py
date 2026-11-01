import subprocess
from pathlib import Path

import pytest

from free_hand.tools.commands import run_command


def test_rejects_empty_argv(tmp_path: Path):
    with pytest.raises(ValueError):
        run_command(tmp_path, [])


def test_rejects_non_string_argv(tmp_path: Path):
    with pytest.raises(ValueError):
        run_command(tmp_path, ["echo", 1])  # type: ignore[list-item]


def test_rejects_nul_byte(tmp_path: Path):
    with pytest.raises(ValueError):
        run_command(tmp_path, ["echo", "a\x00b"])


def test_reports_non_zero_exit(tmp_path: Path):
    output = run_command(tmp_path, ["python", "-c", "import sys; sys.exit(3)"])
    assert "exit_code=3" in output
    assert "--- stdout ---" in output
    assert "--- stderr ---" in output


def test_captures_stdout(tmp_path: Path):
    output = run_command(tmp_path, ["python", "-c", "print('hello')"])
    assert "exit_code=0" in output
    assert "hello" in output


def test_timeout_raises(tmp_path: Path):
    with pytest.raises(subprocess.TimeoutExpired):
        run_command(
            tmp_path,
            ["python", "-c", "import time; time.sleep(5)"],
            timeout=0.1,
        )
