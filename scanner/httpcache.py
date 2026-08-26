"""Disk-cached, polite HTTP fetching. Re-runs never refetch."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "pages"
USER_AGENT = (
    "new-biz-finder/0.1 (seed-round agency-opportunity research; polite crawler)"
)

_last_request_ts = 0.0


@dataclass
class Response:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: str
    from_cache: bool

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _paths(url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]
    base = CACHE_DIR / key
    return base.with_suffix(".meta.json"), base.with_suffix(".body")


def load_cached(url: str) -> Response | None:
    meta_path, body_path = _paths(url)
    if not (meta_path.exists() and body_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return Response(
            url=meta["url"],
            final_url=meta.get("final_url", meta["url"]),
            status=meta["status"],
            content_type=meta.get("content_type", ""),
            body=body_path.read_bytes(),
            fetched_at=meta["fetched_at"],
            from_cache=True,
        )
    except Exception:
        return None


def _throttle(min_interval: float) -> None:
    global _last_request_ts
    wait = min_interval - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def fetch(
    url: str,
    *,
    timeout: float = 15.0,
    retries: int = 2,
    min_interval: float = 1.0,
    follow_redirects: bool = True,
) -> Response:
    """Fetch url with disk cache. Cache hits are instant; misses are throttled."""
    cached = load_cached(url)
    if cached is not None:
        return cached

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(2.0 * attempt)
        _throttle(min_interval)
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=follow_redirects,
                headers=headers,
            ) as client:
                resp = client.get(url)
        except httpx.HTTPError as exc:
            last_error = exc
            continue
        meta_path, body_path = _paths(url)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "url": url,
            "final_url": str(resp.url),
            "status": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        tmp_meta = meta_path.with_suffix(".tmp")
        tmp_body = body_path.with_suffix(".tmpbody")
        tmp_meta.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        tmp_body.write_bytes(resp.content)
        tmp_meta.replace(meta_path)
        tmp_body.replace(body_path)
        return Response(
            url=url,
            final_url=meta["final_url"],
            status=resp.status_code,
            content_type=meta["content_type"],
            body=resp.content,
            fetched_at=meta["fetched_at"],
            from_cache=False,
        )
    raise ConnectionError(f"failed after {retries + 1} attempts: {url}: {last_error}")


def get_text(url: str, **kwargs) -> str | None:
    """Fetch and return text for 2xx responses, else None."""
    try:
        resp = fetch(url, **kwargs)
    except ConnectionError:
        return None
    if resp.ok:
        return resp.text
    return None
