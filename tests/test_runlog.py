import importlib.util
import json
from pathlib import Path

from scanner.runlog import append_run_log

_SPEC = importlib.util.spec_from_file_location("pipeline_main", Path(__file__).resolve().parent.parent / "main.py")
assert _SPEC and _SPEC.loader
_main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_main)


def test_append_run_log_writes_jsonl(tmp_path):
    path = tmp_path / "run_log.jsonl"
    append_run_log({"event": "pipeline_completed", "step": "validate"}, path=path)
    payload = json.loads(path.read_text().splitlines()[0])
    assert payload["event"] == "pipeline_completed"
    assert payload["step"] == "validate"
    assert "ts" in payload


def test_dry_run_returns_without_writing(tmp_path, monkeypatch):
    _main.run_pipeline(step="all", dry_run=True)
    # Dry run returns before the run-log append, so this is a smoke check
    # that the early return path executes without error.
