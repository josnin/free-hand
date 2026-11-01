from __future__ import annotations

import subprocess
from pathlib import Path

from .filesystem import safe_path


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, shell=False, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f"git exited {result.returncode}").strip())
    return result.stdout.strip() or "(no output)"


def git_status(root: Path) -> str:
    return _git(root, "status", "--short", "--branch")


def git_diff(root: Path, staged: bool = False, paths: list[str] | None = None) -> str:
    args = ["diff", "--no-ext-diff", "--"] if not staged else ["diff", "--cached", "--no-ext-diff", "--"]
    for item in paths or []:
        safe_path(root, item)
        args.append(item)
    return _git(root, *args)


def git_stage(root: Path, paths: list[str]) -> str:
    if not paths:
        raise ValueError("paths must contain at least one explicitly selected file")
    checked = []
    for item in paths:
        safe_path(root, item)
        checked.append(item)
    return _git(root, "add", "--", *checked)


def git_commit(root: Path, message: str | None = None) -> str:
    staged = _git(root, "diff", "--cached", "--name-only")
    if staged == "(no output)":
        raise ValueError("No staged changes to commit")
    msg = message.strip() if isinstance(message, str) and message.strip() else "Update project files"
    return _git(root, "commit", "-m", msg)
