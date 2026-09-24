"""Environment variable loader for .env configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> None:
    """Load key-value pairs from a .env file into os.environ if not already set."""
    if path is None:
        path = Path.cwd() / ".env"
    p = Path(path)
    if not p.is_file():
        # Check parent directory or root
        candidate = Path(__file__).resolve().parent.parent / ".env"
        if candidate.is_file():
            p = candidate

    if not p.is_file():
        return

    try:
        content = p.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                # Only populate if key is non-empty and not already present
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


# Automatically load on import
load_dotenv()
