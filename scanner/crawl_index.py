"""Step 1: crawl /tag/seed-round/ index pages -> data/articles_index.json.

Finds the highest valid page number by doubling + binary search, then crawls
pages in DESCENDING order (reduces drift from newly published posts).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from scanner.httpcache import fetch

BASE = "https://www.thesaasnews.com/tag/seed-round/"
OUT = Path("data/articles_index.json")
CARD_SEL = "div.gh-archive-page-post"
TITLE_LINK_RE = re.compile(r"^/news/([^/]+)/$")


def page_url(n: int) -> str:
    return BASE if n == 1 else f"{BASE}page/{n}/"


def parse_page(html: str, page_no: int) -> list[dict]:
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
                "tag_page": page_no,
            }
        )
    return out


def page_ok(n: int) -> bool:
    try:
        resp = fetch(page_url(n))
    except ConnectionError:
        return False
    return resp.ok


def find_max_page() -> int:
    lo = 1
    hi = 2
    while page_ok(hi):
        lo = hi
        hi *= 2
        print(f"  probe: page {hi} boundary search, ok up to {lo}", flush=True)
    # invariant: lo ok, hi not ok -> binary search largest ok in [lo+1, hi-1]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if page_ok(mid):
            lo = mid
        else:
            hi = mid
        print(f"  probe: window [{lo}, {hi}]", flush=True)
    return lo


def main() -> None:
    force_redo_index = "--refetch" in sys.argv
    if OUT.exists() and not force_redo_index:
        existing = json.loads(OUT.read_text())
        print(f"{OUT} already exists: {existing['count']} articles, max_page={existing['max_page']}")
        return

    print("finding last page...", flush=True)
    max_page = find_max_page()
    print(f"last tag page: {max_page}", flush=True)

    articles: dict[str, dict] = {}
    errors: list[str] = []
    for n in range(max_page, 0, -1):
        url = page_url(n)
        try:
            resp = fetch(url)
        except ConnectionError as exc:
            errors.append(f"page {n}: {exc}")
            continue
        if not resp.ok:
            errors.append(f"page {n}: HTTP {resp.status}")
            continue
        cards = parse_page(resp.text, n)
        for entry in cards:
            articles.setdefault(entry["slug"], entry)
        if n % 10 == 0 or n == 1:
            print(f"  page {n}/{max_page}: +{len(cards)} (total unique {len(articles)})", flush=True)

    payload = {
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "max_page": max_page,
        "count": len(articles),
        "errors": errors,
        "articles": sorted(
            articles.values(),
            key=lambda a: (a["date"] or "", a["tag_page"], a["slug"]),
            reverse=True,
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(articles)} articles from {max_page} pages; {len(errors)} errors")


if __name__ == "__main__":
    main()
