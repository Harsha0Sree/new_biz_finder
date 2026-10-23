"""Small storage helpers for crash-safe JSON and text artifacts.

Long pipeline runs rewrite the same JSON files after every item. A process
kill during a plain `write_text` leaves a truncated file, which then breaks
resume. Every writer in the pipeline goes through these helpers instead.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any


def _atomic_write(path: str | Path, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = f".tmp.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}"
    tmp = target.with_name(target.name + suffix)
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        with suppress(OSError):
            tmp.unlink()
    return target


def write_text(path: str | Path, text: str) -> Path:
    return _atomic_write(path, text)


def write_bytes(path: str | Path, payload: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = f".tmp.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}"
    tmp = target.with_name(target.name + suffix)
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    finally:
        with suppress(OSError):
            tmp.unlink()
    return target


def write_json(path: str | Path, payload: Any, *, indent: int | None = 1) -> Path:
    text = json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"
    return _atomic_write(path, text)


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def append_text(path: str | Path, line: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return target
