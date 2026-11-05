"""Append-only JSONL run log for pipeline executions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scanner.paths import RUN_LOG
from scanner.storage import append_text


def append_run_log(entry: dict[str, Any], path: Path = RUN_LOG) -> Path:
    payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    return append_text(path, json.dumps(payload, ensure_ascii=False) + "\n")
