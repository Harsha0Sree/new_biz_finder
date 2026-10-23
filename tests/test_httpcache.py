import json

import pytest

from scanner import httpcache


class FakeResponse:
    def __init__(self, url: str, status: int = 200, body: bytes = b"ok"):
        self.url = url
        self.status_code = status
        self.content = body
        self.headers = {"content-type": "text/html"}


class FakeClient:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        response.url = url
        return response


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(httpcache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(httpcache.time, "sleep", lambda _seconds: None)
    httpcache._last_request_by_host.clear()
    yield
    httpcache.close_client()
    httpcache._last_request_by_host.clear()


def test_success_is_cached_and_reused(monkeypatch):
    client = FakeClient([FakeResponse("https://example.com/a", body=b"<html>hi</html>")])
    monkeypatch.setattr(httpcache, "_get_client", lambda: client)

    first = httpcache.fetch("https://example.com/a", min_interval=0)
    second = httpcache.fetch("https://example.com/a", min_interval=0)

    assert first.ok and first.from_cache is False
    assert second.ok and second.from_cache is True
    assert second.text == "<html>hi</html>"
    assert client.calls == 1


def test_429_exhaustion_returns_error_response_not_success(monkeypatch):
    client = FakeClient([FakeResponse("https://example.com/a", status=429)] * 2)
    monkeypatch.setattr(httpcache, "_get_client", lambda: client)

    response = httpcache.fetch("https://example.com/a", retries=1, min_interval=0)

    assert response.status == 429
    assert response.ok is False
    assert response.from_cache is False
    assert client.calls == 2
    # Transient failures must not be cached: a later run has to retry.
    meta_path, body_path = httpcache._paths("https://example.com/a")
    assert not meta_path.exists()
    assert not body_path.exists()


def test_permanent_404_is_cached(monkeypatch):
    client = FakeClient([FakeResponse("https://example.com/missing", status=404)])
    monkeypatch.setattr(httpcache, "_get_client", lambda: client)

    first = httpcache.fetch("https://example.com/missing", min_interval=0)
    second = httpcache.fetch("https://example.com/missing", min_interval=0)

    assert first.status == 404 and first.from_cache is False
    assert second.status == 404 and second.from_cache is True
    assert client.calls == 1


def test_force_refetch_bypasses_cache(monkeypatch):
    client = FakeClient(
        [
            FakeResponse("https://example.com/a", body=b"old"),
            FakeResponse("https://example.com/a", body=b"new"),
        ]
    )
    monkeypatch.setattr(httpcache, "_get_client", lambda: client)

    httpcache.fetch("https://example.com/a", min_interval=0)
    refreshed = httpcache.fetch(
        "https://example.com/a", min_interval=0, force_refetch=True
    )

    assert refreshed.text == "new"
    assert refreshed.from_cache is False
    assert client.calls == 2


def test_corrupt_cache_metadata_is_ignored(monkeypatch):
    url = "https://example.com/a"
    meta_path, body_path = httpcache._paths(url)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("{not json", encoding="utf-8")
    body_path.write_bytes(b"body")

    assert httpcache.load_cached(url) is None


def test_cache_metadata_round_trip(monkeypatch):
    url = "https://example.com/a"
    client = FakeClient([FakeResponse(url, body=b"payload")])
    monkeypatch.setattr(httpcache, "_get_client", lambda: client)

    httpcache.fetch(url, min_interval=0)
    meta_path, _ = httpcache._paths(url)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["url"] == url
    assert meta["status"] == 200
    assert meta["fetched_at"]
