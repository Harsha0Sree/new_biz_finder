"""Step 1: crawl /tag/seed-round/ and /tag/pre-seed/ index pages.

Writes `data/articles_index.json`. Existing indexes are updated incrementally
(newest pages until two consecutive pages add nothing); `--refetch` rebuilds
from scratch.
"""

from __future__ import annotations

import re
import sys
import time

from bs4 import BeautifulSoup

from scanner.httpcache import fetch
from scanner.paths import ARTICLES_INDEX
from scanner.storage import read_json, write_json

TAG_CONFIGS = [
    {"name": "seed-round", "base": "https://www.thesaasnews.com/tag/seed-round/"},
    {"name": "pre-seed", "base": "https://www.thesaasnews.com/tag/pre-seed/"},
]
OUT = ARTICLES_INDEX
CARD_SEL = "div.gh-archive-page-post"
TITLE_LINK_RE = re.compile(r"^/news/([^/]+)/$")
MAX_PAGES = 1000


def page_url(base: str, n: int) -> str:
    clean_base = base.rstrip("/") + "/"
    return clean_base if n == 1 else f"{clean_base}page/{n}/"


def parse_page(html: str, page_no: int, tag_name: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select(CARD_SEL):
        link = None
        for a in card.find_all("a", href=True):
            m = TITLE_LINK_RE.match(a["href"])
            if not m:
                continue
            title = a.get_text(" ", strip=True)
            # image-wrapper links have empty text; prefer a titled anchor
            if title:
                link = (m.group(1), title)
                break
            if link is None:
                link = (m.group(1), "")
        if link is None:
            continue
        slug, title = link
        t = card.find("time")
        date = t.get("datetime") if t and t.has_attr("datetime") else None
        out.append(
            {
                "slug": slug,
                "url": f"https://www.thesaasnews.com/news/{slug}/",
                "title": title,
                "date": date,
                "tag": tag_name,
                "tag_page": page_no,
            }
        )
    return out


def page_ok(base: str, n: int) -> bool:
    """Return whether a tag page exists. Transport failures are not a 404."""
    resp = fetch(page_url(base, n))
    return resp.ok


def find_max_page(base: str) -> int:
    """Find the last existing tag page with a doubling probe, then binary search."""
    if not page_ok(base, 1):
        return 0
    lo = 1
    hi = 2
    while hi <= MAX_PAGES and page_ok(base, hi):
        lo = hi
        hi *= 2
        print(f"  probe [{base}]: page {hi} boundary search, ok up to {lo}", flush=True)
    if lo >= MAX_PAGES:
        return lo
    # invariant: lo ok, hi not ok -> binary search largest ok in [lo+1, hi-1]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if page_ok(base, mid):
            lo = mid
        else:
            hi = mid
        print(f"  probe [{base}]: window [{lo}, {hi}]", flush=True)
    return lo


def _sorted_articles(articles: dict[str, dict]) -> list[dict]:
    return sorted(
        articles.values(),
        key=lambda a: (a.get("date") or "", a.get("tag_page", 9999), a.get("slug", "")),
        reverse=True,
    )


def crawl_incremental(existing_payload: dict) -> dict:
    existing_articles = {a["slug"]: a for a in existing_payload.get("articles", [])}
    print(f"Checking for new articles (currently indexed: {len(existing_articles)})...", flush=True)

    errors: list[str] = list(existing_payload.get("errors", []))
    total_new = 0
    tag_max_pages: dict[str, int] = {}

    for cfg in TAG_CONFIGS:
        tag_name = cfg["name"]
        base = cfg["base"]
        print(f"\n--- Checking tag: {tag_name} ({base}) ---", flush=True)
        page = 1
        consecutive_empty = 0
        tag_new = 0
        tag_max_pages[tag_name] = 0

        while page <= MAX_PAGES:
            url = page_url(base, page)
            try:
                resp = fetch(url, force_refetch=True)
            except ConnectionError as exc:
                errors.append(f"incremental {tag_name} page {page}: {exc}")
                break
            if not resp.ok:
                if resp.status != 404:
                    errors.append(f"incremental {tag_name} page {page}: HTTP {resp.status}")
                break
            tag_max_pages[tag_name] = page

            cards = parse_page(resp.text, page, tag_name=tag_name)
            if not cards:
                break

            page_new = 0
            for entry in cards:
                slug = entry["slug"]
                if slug not in existing_articles:
                    existing_articles[slug] = entry
                    tag_new += 1
                    page_new += 1

            print(f"  [{tag_name}] page {page}: found {len(cards)} articles ({page_new} new)", flush=True)

            if page_new == 0:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    print(
                        f"  [{tag_name}] Reached {consecutive_empty} consecutive pages with no new articles.",
                        flush=True,
                    )
                    break
            else:
                consecutive_empty = 0

            page += 1

        total_new += tag_new
        print(f"  [{tag_name}] Added {tag_new} new articles.")

    updated_articles = _sorted_articles(existing_articles)
    payload = {
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "max_page": max(
            [existing_payload.get("max_page", 1), *tag_max_pages.values()],
            default=1,
        ),
        "tag_max_pages": tag_max_pages,
        "count": len(updated_articles),
        "errors": errors,
        "articles": updated_articles,
    }
    write_json(OUT, payload)
    print(
        f"\nIndex updated: added {total_new} new articles "
        f"(total {len(updated_articles)} articles).",
        flush=True,
    )
    return payload


def crawl_full() -> dict:
    articles: dict[str, dict] = {}
    errors: list[str] = []
    tag_max_pages: dict[str, int] = {}

    for cfg in TAG_CONFIGS:
        tag_name = cfg["name"]
        base = cfg["base"]
        print(f"\nFinding max page for {tag_name} ({base})...", flush=True)
        max_page = find_max_page(base)
        tag_max_pages[tag_name] = max_page
        print(f"Last tag page for {tag_name}: {max_page}", flush=True)

        for n in range(max_page, 0, -1):
            url = page_url(base, n)
            try:
                resp = fetch(url)
            except ConnectionError as exc:
                errors.append(f"{tag_name} page {n}: {exc}")
                continue
            if not resp.ok:
                errors.append(f"{tag_name} page {n}: HTTP {resp.status}")
                continue
            cards = parse_page(resp.text, n, tag_name=tag_name)
            for entry in cards:
                articles.setdefault(entry["slug"], entry)
            if n % 10 == 0 or n == 1:
                print(
                    f"  [{tag_name}] page {n}/{max_page}: +{len(cards)} "
                    f"(total unique {len(articles)})",
                    flush=True,
                )

    payload = {
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "max_page": max(tag_max_pages.values(), default=0),
        "tag_max_pages": tag_max_pages,
        "count": len(articles),
        "errors": errors,
        "articles": _sorted_articles(articles),
    }
    write_json(OUT, payload)
    print(f"Wrote {OUT}: {len(articles)} articles; {len(errors)} errors")
    return payload


def main(refetch: bool | None = None) -> None:
    if refetch is None:
        refetch = "--refetch" in sys.argv or "--full" in sys.argv
    if OUT.exists() and not refetch:
        crawl_incremental(read_json(OUT))
        return
    crawl_full()


if __name__ == "__main__":
    main()
