from pathlib import Path
import re

BLOCKED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials", "secrets.json"}

def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip(): raise ValueError("path must be a non-empty string")
    root = root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try: candidate.relative_to(root)
    except ValueError as exc: raise ValueError("Path escapes the project root") from exc
    parts = candidate.relative_to(root).parts
    if any(p.lower() in BLOCKED_NAMES or p.lower().startswith(".env.") for p in parts):
        raise ValueError("Access to secret-like paths is blocked")
    return candidate

def read_file(root: Path, relative: str, max_bytes: int = 200_000) -> str:
    path = safe_path(root, relative)
    if not path.is_file(): raise FileNotFoundError(relative)
    if path.stat().st_size > max_bytes: raise ValueError(f"File exceeds {max_bytes} byte limit")
    return path.read_text(encoding="utf-8")

def list_files(root: Path, pattern: str = "**/*", limit: int = 500) -> list[str]:
    root = root.resolve(); found = []
    for path in root.glob(pattern):
        try:
            resolved = path.resolve(); resolved.relative_to(root)
            rel = resolved.relative_to(root).as_posix()
            if path.is_file() and not any(p.lower() in BLOCKED_NAMES or p.lower().startswith(".env.") for p in Path(rel).parts): found.append(rel)
        except (OSError, ValueError): continue
        if len(found) >= limit: break
    return sorted(set(found))

def search_files(root: Path, query: str, literal: bool = True, limit: int = 200) -> list[str]:
    if not query: raise ValueError("query must not be empty")
    matches = []
    if literal:
        matcher = lambda content: query in content
    else:
        # Smart case: uppercase in the query means case-sensitive regex; otherwise ignore case.
        flags = 0 if any(char.isupper() for char in query) else re.IGNORECASE
        try:
            expression = re.compile(query, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        matcher = lambda content: expression.search(content) is not None
    for relative in list_files(root):
        path = safe_path(root, relative)
        try:
            if path.stat().st_size > 200_000: continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError): continue
        if matcher(content):
            matches.append(relative)
            if len(matches) >= limit: break
    return matches

def write_file(root: Path, relative: str, content: str) -> str:
    path = safe_path(root, relative)
    if not isinstance(content, str): raise ValueError("content must be a string")
    if path.exists(): raise FileExistsError(f"Refusing to overwrite existing file: {relative}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Recheck after creating parents to avoid following an unexpected path outside root.
    path = safe_path(root, relative)
    if path.exists(): raise FileExistsError(f"Refusing to overwrite existing file: {relative}")
    path.write_text(content, encoding="utf-8")
    return f"Created {relative} ({len(content)} characters)"


def edit_file(root: Path, relative: str, old_text: str, new_text: str) -> str:
    if not isinstance(old_text, str) or not old_text:
        raise ValueError("old_text must be a non-empty string")
    if not isinstance(new_text, str):
        raise ValueError("new_text must be a string")
    path = safe_path(root, relative)
    if not path.is_file():
        raise FileNotFoundError(relative)
    if path.stat().st_size > 200_000:
        raise ValueError("File exceeds 200000 byte limit")
    content = path.read_text(encoding="utf-8")
    occurrences = content.count(old_text)
    if occurrences != 1:
        raise ValueError(f"Expected old_text to occur exactly once; found {occurrences}")
    updated = content.replace(old_text, new_text, 1)
    path.write_text(updated, encoding="utf-8")
    return f"Updated {relative} (replaced one exact occurrence)"
