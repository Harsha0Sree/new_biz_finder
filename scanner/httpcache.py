"""Disk-cached, polite HTTP fetching. Re-runs never refetch cached successes.

Transient failures (429/5xx) are retried and are not cached, so a later run can
recover. Per-host throttling lets independent hosts fetch concurrently.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from scanner.paths import PAGES
from scanner.storage import write_bytes, write_json

CACHE_DIR = PAGES
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
# Permanent and not-yet-settled responses are never cached so growth is visible.
NO_CACHE_STATUSES = frozenset({403, 404, 408, 410, 425, 429})

_client_lock = threading.Lock()
_shared_client: httpx.Client | None = None

_throttle_lock = threading.Lock()
_last_request_by_host: dict[str, float] = {}


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


def _paths(url: str) -> tuple:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]
    base = CACHE_DIR / key
    return base.with_suffix(".meta.json"), base.with_suffix(".body")


def load_cached(url: str) -> Response | None:
    meta_path, body_path = _paths(url)
    if not (meta_path.exists() and body_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("url") != url:
            return None
        # Entries cached before negative results were excluded must not serve.
        if meta.get("status") in NO_CACHE_STATUSES:
            return None
        return Response(
            url=meta["url"],
            final_url=meta.get("final_url", meta["url"]),
            status=meta["status"],
            content_type=meta.get("content_type", ""),
            body=body_path.read_bytes(),
            fetched_at=meta["fetched_at"],
            from_cache=True,
        )
    except (OSError, ValueError, KeyError):
        return None


def _get_client() -> httpx.Client:
    global _shared_client
    with _client_lock:
        if _shared_client is None or _shared_client.is_closed:
            _shared_client = httpx.Client(
                follow_redirects=True,
                headers=DEFAULT_HEADERS,
            )
        return _shared_client


def close_client() -> None:
    """Close the process-wide client. Tests and short-lived CLIs call this."""
    global _shared_client
    with _client_lock:
        if _shared_client is not None and not _shared_client.is_closed:
            _shared_client.close()
        _shared_client = None


def _throttle(url: str, min_interval: float) -> None:
    """Reserve the next request slot for this host, then sleep until it arrives."""
    host = (urlsplit(url).hostname or "").lower()
    with _throttle_lock:
        now = time.monotonic()
        next_at = max(now, _last_request_by_host.get(host, 0.0) + min_interval)
        _last_request_by_host[host] = next_at
    wait = next_at - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
    return min(30.0, 2.0 * attempt)


def fetch(
    url: str,
    *,
    timeout: float = 15.0,
    retries: int = 2,
    min_interval: float = 0.5,
    follow_redirects: bool = True,
    headers: dict[str, str] | None = None,
    force_refetch: bool = False,
) -> Response:
    """Fetch url with a disk cache. Only cacheable statuses are persisted.

    2xx, 3xx, and 4xx responses other than 403/404/408/410/425/429 are
    cached. Everything else is re-requested: network failures, 5xx, and
    the excluded negative/transient statuses.
    """
    if not force_refetch:
        cached = load_cached(url)
        if cached is not None:
            return cached

    req_headers = dict(headers or {})
    last_error: Exception | None = None
    response: httpx.Response | None = None

    for attempt in range(retries + 1):
        if attempt:
            time.sleep(_retry_delay(attempt, response))
        response = None
        _throttle(url, min_interval)
        try:
            response = _get_client().get(
                url,
                timeout=timeout,
                headers=req_headers,
                follow_redirects=follow_redirects,
            )
        except httpx.HTTPError as exc:
            last_error = exc
            continue

        if response.status_code in RETRY_STATUSES and attempt < retries:
            continue
        break

    if response is None:
        raise ConnectionError(f"failed after {retries + 1} attempts: {url}: {last_error}")

    if response.status_code in (403, 404, 410):
        # The origin is authoritative here: drop any stale cache pair so a
        # later probe does not resurrect content the server retracted.
        stale_meta, stale_body = _paths(url)
        for stale in (stale_meta, stale_body):
            with suppress(OSError):
                stale.unlink()

    meta = {
        "url": url,
        "final_url": str(response.url),
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if response.status_code < 500 and response.status_code not in NO_CACHE_STATUSES:
        meta_path, body_path = _paths(url)
        # Body first, then the meta that points at it. A reader either sees a
        # matching fresh pair or no meta at all; it never sees meta for a
        # body that has not landed yet.
        write_bytes(body_path, response.content)
        write_json(meta_path, meta)

    return Response(
        url=url,
        final_url=meta["final_url"],
        status=response.status_code,
        content_type=meta["content_type"],
        body=response.content,
        fetched_at=meta["fetched_at"],
        from_cache=False,
    )


def get_text(url: str, **kwargs) -> str | None:
    """Fetch and return text for 2xx responses, else None."""
    try:
        resp = fetch(url, **kwargs)
    except ConnectionError:
        return None
    if resp.ok:
        return resp.text
    return None
