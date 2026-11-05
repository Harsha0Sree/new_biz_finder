"""Incremental crawl behavior with a mocked network."""

from __future__ import annotations

import json

from scanner import crawl_index
from scanner.httpcache import Response
from scanner.storage import write_json

SEED_URL = "https://www.thesaasnews.com/tag/seed-round/"
PRESEED_URL = "https://www.thesaasnews.com/tag/pre-seed/"


def _card(slug: str, title: str, dt: str) -> str:
    return (
        '<div class="gh-archive-page-post">'
        f'<a href="/news/{slug}/"><span>{title}</span></a>'
        f'<time datetime="{dt}">Date</time>'
        "</div>"
    )


def _page(cards: list[str]) -> str:
    return f"<html><body><main>{''.join(cards)}</main></body></html>"


def _existing() -> dict:
    return {
        "crawled_at": "2026-09-13T00:00:00Z",
        "count": 1,
        "articles": [
            {
                "slug": "old-raise-1",
                "url": SEED_URL + "news/old-raise-1/",
                "title": "Old Raise Announces $12M Seed",
                "date": "2026-09-01T00:00:00Z",
                "tag": "seed-round",
                "tag_page": 1,
            }
        ],
    }


def test_incremental_crawl_refreshes_head_pages_and_adds_new_articles(tmp_path, monkeypatch):
    new_card = _card("brand-new-raise", "Brand New Raises $30M Seed", "2026-11-01T00:00:00Z")
    old_card = _card("old-raise-1", "Old Raise Announces $12M Seed", "2026-09-01T00:00:00Z")
    pages = {
        SEED_URL: _page([new_card, old_card]),
        SEED_URL + "page/2/": _page([old_card]),
        SEED_URL + "page/3/": _page([old_card]),
        PRESEED_URL: _page([old_card]),
        PRESEED_URL + "page/2/": _page([old_card]),
    }
    calls: list[tuple[str, bool]] = []

    def fake_fetch(url, *, force_refetch=False, **kwargs):
        calls.append((url, force_refetch))
        assert url in pages, f"unexpected fetch of {url}"
        return Response(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            body=pages[url].encode("utf-8"),
            fetched_at="2026-11-04T00:00:00Z",
            from_cache=False,
        )

    monkeypatch.setattr(crawl_index, "fetch", fake_fetch)
    monkeypatch.setattr(crawl_index, "OUT", tmp_path / "articles_index.json")
    write_json(tmp_path / "articles_index.json", _existing())
    monkeypatch.setattr(
        crawl_index,
        "TAG_CONFIGS",
        [
            {"name": "seed-round", "base": SEED_URL},
            {"name": "pre-seed", "base": PRESEED_URL},
        ],
    )

    payload = crawl_index.crawl_incremental(_existing())

    slugs = [a["slug"] for a in payload["articles"]]
    assert "brand-new-raise" in slugs
    assert "old-raise-1" in slugs
    assert calls
    assert all(force for _, force in calls)


def test_incremental_crawl_stops_after_two_empty_pages(tmp_path, monkeypatch):
    old_card = _card("old-raise-1", "Old Raise Announces $12M Seed", "2026-09-01T00:00:00Z")
    pages = {
        SEED_URL: _page([old_card]),
        SEED_URL + "page/2/": _page([old_card]),
        SEED_URL + "page/3/": _page([old_card]),
    }
    calls: list[str] = []

    def fake_fetch(url, *, force_refetch=False, **kwargs):
        calls.append(url)
        return Response(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            body=pages[url].encode("utf-8"),
            fetched_at="2026-11-04T00:00:00Z",
            from_cache=False,
        )

    monkeypatch.setattr(crawl_index, "fetch", fake_fetch)
    monkeypatch.setattr(crawl_index, "OUT", tmp_path / "articles_index.json")
    monkeypatch.setattr(
        crawl_index,
        "TAG_CONFIGS",
        [{"name": "seed-round", "base": SEED_URL}],
    )

    crawl_index.crawl_incremental(_existing())

    assert calls == [SEED_URL, SEED_URL + "page/2/"]


def test_incremental_crawl_records_http_errors_without_crashing(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_fetch(url, *, force_refetch=False, **kwargs):
        calls.append(url)
        return Response(
            url=url,
            final_url=url,
            status=500,
            content_type="text/html",
            body=b"error",
            fetched_at="2026-11-04T00:00:00Z",
            from_cache=False,
        )

    monkeypatch.setattr(crawl_index, "fetch", fake_fetch)
    monkeypatch.setattr(crawl_index, "OUT", tmp_path / "articles_index.json")
    monkeypatch.setattr(
        crawl_index,
        "TAG_CONFIGS",
        [{"name": "seed-round", "base": SEED_URL}],
    )

    payload = crawl_index.crawl_incremental(_existing())

    assert payload["errors"]
    assert payload["count"] == 1
    saved = json.loads((tmp_path / "articles_index.json").read_text())
    assert saved["errors"] == payload["errors"]
