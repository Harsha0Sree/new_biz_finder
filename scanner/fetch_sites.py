"""Step 4: fetch company websites (homepage + linked subpages) with caching.

- homepage + same-domain /pricing /product /about /customers /blog pages when
  linked from the homepage (max ~6 pages/company, 15s timeout)
- strips HTML -> clean text stored in data/cache/text/site__<domain>__*.txt
- records per-site status: ok / js_only / dead_parked / dead
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from scanner.httpcache import fetch, get_text

SITES_OUT = Path("data/sites.json")
TEXT_DIR = Path("data/cache/text")
COMPANIES = Path("data/companies.json")

ALLOWED_PATH_RE = re.compile(r"^/(pricing|product|products|about|customers|blog|case-stud\w*|about-us|company)(/|$)")
MAX_SUBPAGES = 5
MIN_TEXT_LEN_JS_ONLY = 250

PARKED_MARKERS = [
    "this domain is for sale",
    "buy this domain",
    "domain parking",
    "sedoparking",
    "afternic",
    "hugedomains",
    "dan.com",
    "parkingcrew",
    "bodis.com",
    "domain may be for sale",
]


def registered_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def strip_html(html: str) -> tuple[str, str]:
    """Return (clean_text, title)."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, title


def classify(status_code: int, text: str) -> str:
    low = text[:4000].lower()
    if any(m in low for m in PARKED_MARKERS):
        return "dead_parked"
    if status_code >= 400:
        return "dead"
    if len(text.strip()) < MIN_TEXT_LEN_JS_ONLY:
        return "js_only"
    return "ok"


def load_sites() -> dict:
    if SITES_OUT.exists():
        return json.loads(SITES_OUT.read_text())
    return {"sites": {}}


def save_sites(data: dict) -> None:
    SITES_OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")


def fetch_site(domain: str, base_url: str) -> dict:
    entry: dict = {"domain": domain, "base_url": base_url, "pages": {}, "fetched_at": None}
    try:
        resp = fetch(base_url, timeout=15.0)
    except ConnectionError as exc:
        entry["status"] = "dead"
        entry["error"] = str(exc)[:200]
        return entry
    if not resp.ok:
        entry["status"] = classify(resp.status, "")
        entry["http_status"] = resp.status
        return entry
    text, title = strip_html(resp.text)
    status = classify(resp.status, text)
    entry["status"] = status
    entry["title"] = title[:200]
    entry["final_url"] = resp.final_url
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    (TEXT_DIR / f"site__{domain}__home.txt").write_text(text)
    entry["pages"]["/"] = {"status": status, "chars": len(text)}

    if status in ("ok", "js_only"):
        # discover same-domain nav links on homepage
        soup = BeautifulSoup(resp.body.decode("utf-8", errors="replace"), "lxml")
        found: list[str] = []
        for a in soup.find_all("a", href=True):
            absolute = urljoin(resp.final_url, a["href"])
            parts = urlsplit(absolute)
            if registered_domain(absolute) != domain:
                continue
            path = parts.path or "/"
            if not ALLOWED_PATH_RE.match(path):
                continue
            norm = path.rstrip("/") or "/"
            if norm != "/" and norm not in found and len(found) < MAX_SUBPAGES:
                found.append(norm)
        for n, path in enumerate(found):
            sub_url = urljoin(resp.final_url, path + "/")
            try:
                sub_resp = fetch(sub_url, timeout=15.0)
            except ConnectionError:
                entry["pages"][path] = {"status": "error"}
                continue
            if not sub_resp.ok:
                entry["pages"][path] = {"status": f"http_{sub_resp.status}"}
                continue
            sub_text, _t = strip_html(sub_resp.text)
            sub_status = classify(sub_resp.status, sub_text)
            fname = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")[:40]
            (TEXT_DIR / f"site__{domain}__{fname}.txt").write_text(sub_text)
            entry["pages"][path] = {"status": sub_status, "chars": len(sub_text)}
    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return entry


def main() -> None:
    companies = json.loads(COMPANIES.read_text())
    unique = [c for c in companies if not c.get("duplicate_of_previous")]
    sites = load_sites()
    todo = []
    for c in unique:
        dom = c.get("domain")
        if not dom:
            continue
        if dom in sites["sites"]:
            continue
        todo.append(c)
    print(f"{len(unique)} unique companies, {len(todo)} sites to fetch", flush=True)
    if "--limit" in sys.argv:
        n = int(sys.argv[sys.argv.index("--limit") + 1])
        todo = todo[:n]
        print(f"limiting to {n}", flush=True)

    for n, c in enumerate(todo, 1):
        entry = fetch_site(c["domain"], c["website"])
        sites["sites"][c["domain"]] = entry
        save_sites(sites)
        if n % 25 == 0:
            statuses = {}
            for e in sites["sites"].values():
                statuses[e.get("status", "?")] = statuses.get(e.get("status", "?"), 0) + 1
            print(f"  {n}/{len(todo)} {statuses}", flush=True)

    statuses = {}
    for e in sites["sites"].values():
        statuses[e.get("status", "?")] = statuses.get(e.get("status", "?"), 0) + 1
    print("done:", statuses)


if __name__ == "__main__":
    main()
