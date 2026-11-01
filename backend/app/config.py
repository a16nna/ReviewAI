"""Tiny .env loader (no extra dependency). Real environment variables always win."""
import os
from pathlib import Path


def load_dotenv(path: Path | None = None) -> list[str]:
    if os.environ.get("REVIEWAI_SKIP_DOTENV") == "1":
        return []
    candidates = [path] if path else [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    loaded: list[str] = []
    for f in candidates:
        if not f or not f.is_file():
            continue
        for raw in f.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key and key not in os.environ and val != "":
                os.environ[key] = val
                loaded.append(key)
        break  # first .env found wins
    return loaded
