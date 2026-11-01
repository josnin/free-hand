import subprocess
from pathlib import Path

def run_command(root: Path, argv: list[str], timeout: int = 30) -> str:
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a non-empty array of strings")
    if any("\x00" in arg for arg in argv): raise ValueError("argv contains a NUL byte")
    completed = subprocess.run(argv, cwd=root, shell=False, capture_output=True, text=True, timeout=timeout, check=False)
    return f"exit_code={completed.returncode}\n--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
