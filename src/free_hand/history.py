import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def append_history(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    item = dict(entry); item["timestamp"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as f: f.write(json.dumps(item, ensure_ascii=False) + "\n")

def read_history(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists(): return []
    output = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict): output.append(item)
        except json.JSONDecodeError: continue
    return output
