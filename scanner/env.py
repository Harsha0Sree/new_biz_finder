"""Minimal .env loader used by the CLI and the LLM clients."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load `KEY=value` pairs from a .env file into os.environ.

    Existing environment variables win unless `override=True`. Values may be
    single- or double-quoted. The parser is deliberately small; it is not a
    shell and does not expand variables.
    """
    if path is None:
        path = Path.cwd() / ".env"
    candidate = Path(path)
    if not candidate.is_file():
        fallback = Path(__file__).resolve().parent.parent / ".env"
        if fallback.is_file():
            candidate = fallback

    if not candidate.is_file():
        return {}

    loaded: dict[str, str] = {}
    content = candidate.read_text(encoding="utf-8")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            continue
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


# Importing the package loads the default .env, matching the previous behavior.
load_dotenv()
