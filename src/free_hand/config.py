import json
from pathlib import Path

DEFAULT_CONFIG = {"history_file": ".free-hand/history.jsonl", "max_input_bytes": 1_000_000, "max_output_chars": 20_000, "command_timeout_seconds": 30}

def load_config(root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    path = root / ".free-hand.json"
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read config {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("Config must be a JSON object.")
        config.update(loaded)
    return config
