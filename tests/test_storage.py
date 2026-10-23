import json

from scanner.storage import append_text, read_json, write_bytes, write_json, write_text


def test_write_and_read_json_round_trip(tmp_path):
    target = tmp_path / "nested" / "data.json"
    payload = {"name": "Café", "values": [1, 2, 3]}

    write_json(target, payload)

    assert read_json(target) == payload
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_write_text_and_bytes_create_parents(tmp_path):
    text_target = tmp_path / "a" / "b" / "note.txt"
    bin_target = tmp_path / "a" / "b" / "blob.bin"

    write_text(text_target, "hello")
    write_bytes(bin_target, b"\x00\x01")

    assert text_target.read_text(encoding="utf-8") == "hello"
    assert bin_target.read_bytes() == b"\x00\x01"


def test_writes_leave_no_temp_files(tmp_path):
    target = tmp_path / "data.json"

    write_json(target, {"ok": True})
    write_text(target, "plain")
    write_bytes(target, b"bytes")

    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]


def test_read_json_missing_returns_default(tmp_path):
    assert read_json(tmp_path / "absent.json") is None
    assert read_json(tmp_path / "absent.json", {"fallback": True}) == {"fallback": True}


def test_append_text(tmp_path):
    target = tmp_path / "errors.log"

    append_text(target, "first\n")
    append_text(target, "second\n")

    assert target.read_text(encoding="utf-8") == "first\nsecond\n"
