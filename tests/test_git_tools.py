import subprocess
from pathlib import Path

import pytest

from free_hand.tools.git_tools import git_commit, git_diff, git_stage, git_status


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def test_status_empty_repo(tmp_path: Path):
    _init_repo(tmp_path)
    assert "## " in git_status(tmp_path)


def test_stage_requires_paths(tmp_path: Path):
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        git_stage(tmp_path, [])


def test_stage_rejects_escaping_path(tmp_path: Path):
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        git_stage(tmp_path, ["../outside"])


def test_diff_rejects_escaping_path(tmp_path: Path):
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        git_diff(tmp_path, paths=["../outside"])


def test_commit_with_nothing_staged_raises(tmp_path: Path):
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        git_commit(tmp_path, "noop")


def test_stage_and_commit_roundtrip(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello\n")
    git_stage(tmp_path, ["a.txt"])
    diff = git_diff(tmp_path, staged=True)
    assert "a.txt" in diff
    git_commit(tmp_path, "add a.txt")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "add a.txt" in log
