"""Step 4: fetch company websites (homepage + linked subpages) with caching.

Records per-site status in `data/sites.json` and clean text in
`data/cache/text/site__<domain>__*.txt`. Bounded concurrency is safe because
the HTTP cache throttles per host and writes atomically.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from scanner.httpcache import fetch
from scanner.paths import COMPANIES, SITES, TEXT
from scanner.storage import read_json, write_json, write_text

SITES_OUT = SITES
TEXT_DIR = TEXT
COMPANIES_PATH = COMPANIES

ALLOWED_PATH_RE = re.compile(
    r"^/(pricing|product|products|solutions|features|platform|technology|tech|"
    r"how-it-works|use-cases|about|about-us|company|customers|case-stud\w*|"
    r"faq|docs|documentation|integrations|security|overview|services|developers|blog)(/|$)",
    re.IGNORECASE,
)
MAX_SUBPAGES = 12
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

_PRICE_RE = re.compile(
    r"[$€£]\s*\d[\d,]*(?:\.\d{1,2})?\s*"
    r"(?:/\s*(?:mo(?:nth)?|yr|year|user|seat|agent|dev|member))?",
    re.IGNORECASE,
)
_PLAN_RE = re.compile(
    r"\b(Free(?:\s+Tier)?|Starter|Pro|Professional|Growth|Business|Team|Enterprise|Custom|Usage-based)\b",
    re.IGNORECASE,
)
_SALES_LED_RE = re.compile(
    r"\b(book\s+a\s+demo|request\s+(?:a\s+)?demo|contact\s+sales|"
    r"talk\s+to\s+(?:sales|expert)|schedule\s+(?:a\s+)?demo|custom\s+pricing|"
    r"get\s+a\s+quote)\b",
    re.IGNORECASE,
)


def registered_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.") or None


def _clean_price(raw: str) -> str | None:
    cleaned = re.sub(r"\s+", "", raw)
    match = re.search(r"([\d,]+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    if amount <= 0 or amount > 100_000:
        return None
    # A bare "$2026" on a page is usually a copyright year, not a plan price.
    if "/" not in cleaned and amount.is_integer() and 2015 <= amount <= 2030:
        return None
    return cleaned


def extract_pricing(soup: BeautifulSoup, text: str) -> dict:
    """Extract public price points, plan names, and sales-led CTAs."""
    valid_prices: list[str] = []
    for match in _PRICE_RE.finditer(text):
        trailing = text[match.end() : match.end() + 12]
        if re.match(r"\s*(?:million|billion|thousand|m|b|k|t)\b", trailing, re.IGNORECASE):
            continue
        price = _clean_price(match.group(0))
        if price and price not in valid_prices:
            valid_prices.append(price)

    plans: list[str] = []
    for match in _PLAN_RE.finditer(text):
        plan = match.group(1).title()
        if plan not in plans:
            plans.append(plan)

    has_sales_led = bool(_SALES_LED_RE.search(text))
    has_public_pricing = bool(valid_prices) and any(
        "/" in price or float(re.search(r"[\d,]+(?:\.\d+)?", price).group(0).replace(",", "")) < 5000
        for price in valid_prices
    )

    summary_parts = []
    if has_public_pricing:
        summary_parts.append(f"Public Pricing: {', '.join(valid_prices[:5])}")
        if plans:
            summary_parts.append(f"Tiers: {', '.join(plans[:5])}")
    elif has_sales_led:
        summary_parts.append(
            "Sales-Led / Enterprise: No public self-serve pricing "
            "(CTAs: 'Book a Demo' / 'Contact Sales')"
        )
    else:
        summary_parts.append("No public pricing published on website.")

    return {
        "has_public_pricing": has_public_pricing,
        "price_points": valid_prices[:10],
        "plans": plans[:8],
        "is_sales_led": has_sales_led,
        "summary": " | ".join(summary_parts),
    }


def _next_data_strings(props: dict, depth: int = 3) -> list[str]:
    if depth <= 0:
        return []
    result: list[str] = []
    if isinstance(props, str):
        text = props.strip()
        if len(text) > 20 and not text.startswith(("http", "data:", "{", "[")):
            result.append(text)
    elif isinstance(props, dict):
        for key, value in props.items():
            if key not in ("_id", "id", "slug", "image", "icon", "url", "href"):
                result.extend(_next_data_strings(value, depth - 1))
    elif isinstance(props, list):
        for item in props[:15]:
            result.extend(_next_data_strings(item, depth - 1))
    return result


def strip_html(html: str) -> tuple[str, str, dict]:
    """Return (clean_text, title, pricing). Recovers SPA state and JSON-LD."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_desc = ""
    desc_tag = (
        soup.find("meta", attrs={"name": re.compile(r"description", re.IGNORECASE)})
        or soup.find("meta", attrs={"property": re.compile(r"og:description", re.IGNORECASE)})
        or soup.find("meta", attrs={"name": re.compile(r"twitter:description", re.IGNORECASE)})
    )
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()

    next_data_text = ""
    next_tag = soup.find("script", id="__NEXT_DATA__")
    if next_tag and next_tag.string:
        try:
            next_data = json.loads(next_tag.string)
            props = next_data.get("props", {}).get("pageProps", {})
            strings = _next_data_strings(props)
            if strings:
                next_data_text = "\n".join(dict.fromkeys(strings))[:4000]
        except (ValueError, AttributeError):
            pass

    json_ld_text = ""
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except ValueError:
            continue
        entries = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            entries = data["@graph"]
        for item in entries:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("headline")
                if desc:
                    json_ld_text += f"\nStructured Info: {desc}"

    headings: list[str] = []
    for heading in soup.find_all(["h1", "h2", "h3"])[:12]:
        text = heading.get_text(" ", strip=True)
        if text and len(text) < 120 and text not in headings:
            headings.append(text)

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if next_data_text and len(text) < 400:
        text = text + "\n\n" + next_data_text
    if json_ld_text and len(text) < 400:
        text = text + "\n\n" + json_ld_text

    header_parts = []
    if title:
        header_parts.append(f"Page Title: {title}")
    if meta_desc:
        header_parts.append(f"Meta Description: {meta_desc}")
    if headings:
        header_parts.append("Key Sections: " + " | ".join(headings))
    if header_parts:
        text = "\n".join(header_parts) + "\n\n" + text

    return text, title, extract_pricing(soup, text)


def classify(status_code: int, text: str) -> str:
    low = text[:4000].lower()
    if any(marker in low for marker in PARKED_MARKERS):
        return "dead_parked"
    if status_code >= 400:
        return "dead"
    if len(text.strip()) < MIN_TEXT_LEN_JS_ONLY:
        return "js_only"
    return "ok"


def load_sites() -> dict:
    payload = read_json(SITES_OUT, {"sites": {}})
    if not isinstance(payload, dict) or not isinstance(payload.get("sites"), dict):
        return {"sites": {}}
    return payload


def save_sites(data: dict) -> None:
    write_json(SITES_OUT, data)


def fetch_site(
    domain: str,
    base_url: str,
    max_subpages: int = MAX_SUBPAGES,
    force_refetch: bool = False,
) -> dict:
    entry: dict = {
        "domain": domain,
        "base_url": base_url,
        "pages": {},
        "pricing": {},
        "fetched_at": None,
    }
    try:
        resp = fetch(base_url, timeout=15.0, force_refetch=force_refetch)
    except ConnectionError as exc:
        entry["status"] = "dead"
        entry["error"] = str(exc)[:200]
        return entry
    if not resp.ok:
        entry["status"] = classify(resp.status, "")
        entry["http_status"] = resp.status
        return entry

    text, title, home_pricing = strip_html(resp.text)
    status = classify(resp.status, text)
    entry["status"] = status
    entry["title"] = title[:200]
    entry["final_url"] = resp.final_url
    entry["pricing"] = home_pricing
    write_text(TEXT_DIR / f"site__{domain}__home.txt", text)
    entry["pages"]["/"] = {"status": status, "chars": len(text)}

    if status in ("ok", "js_only"):
        soup = BeautifulSoup(resp.body.decode("utf-8", errors="replace"), "lxml")
        found: list[str] = []
        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(resp.final_url, anchor["href"])
            parts = urlsplit(absolute)
            if registered_domain(absolute) != domain:
                continue
            path = parts.path or "/"
            if not ALLOWED_PATH_RE.match(path):
                continue
            normalized = path.rstrip("/") or "/"
            if normalized != "/" and normalized not in found and len(found) < max_subpages:
                found.append(normalized)

        found.sort(key=lambda p: (0 if "pricing" in p.lower() else 1))

        for path in found:
            sub_url = urljoin(resp.final_url, path + "/")
            try:
                sub_resp = fetch(sub_url, timeout=15.0, force_refetch=force_refetch)
            except ConnectionError:
                entry["pages"][path] = {"status": "error"}
                continue
            if not sub_resp.ok:
                entry["pages"][path] = {"status": f"http_{sub_resp.status}"}
                continue

            sub_text, _title, sub_pricing = strip_html(sub_resp.text)
            sub_status = classify(sub_resp.status, sub_text)
            fname = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")[:40]
            write_text(TEXT_DIR / f"site__{domain}__{fname}.txt", sub_text)
            entry["pages"][path] = {"status": sub_status, "chars": len(sub_text)}

            if sub_pricing.get("has_public_pricing") or (
                "pricing" in path.lower()
                and not entry["pricing"].get("has_public_pricing")
            ):
                entry["pricing"] = sub_pricing

    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return entry


def _parse_cli(limit: int | None, workers: int, refetch: bool) -> tuple[int | None, int, bool]:
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    if "--refetch" in sys.argv:
        refetch = True
    return limit, max(1, min(workers, 16)), refetch


def main(limit: int | None = None, workers: int = 4, refetch: bool = False) -> None:
    limit, workers, refetch = _parse_cli(limit, workers, refetch)
    companies = read_json(COMPANIES_PATH)
    if companies is None:
        raise FileNotFoundError(f"{COMPANIES_PATH} not found. Run scanner.fetch_articles first.")
    unique = [c for c in companies if not c.get("duplicate_of_previous")]
    sites = load_sites()
    todo = []
    for company in unique:
        domain = company.get("domain")
        if not domain:
            continue
        if domain in sites["sites"] and not refetch:
            continue
        todo.append(company)
    print(f"{len(unique)} unique companies, {len(todo)} sites to fetch (workers={workers})", flush=True)
    if limit is not None:
        todo = todo[:limit]
        print(f"limiting to {limit}", flush=True)

    def persist(company: dict, entry: dict) -> None:
        sites["sites"][company["domain"]] = entry
        save_sites(sites)

    if workers == 1:
        for index, company in enumerate(todo, 1):
            entry = fetch_site(
                company["domain"],
                company["website"],
                force_refetch=refetch,
            )
            persist(company, entry)
            if index % 25 == 0:
                print(f"  {index}/{len(todo)}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    fetch_site,
                    company["domain"],
                    company["website"],
                    MAX_SUBPAGES,
                    refetch,
                ): company
                for company in todo
            }
            for index, future in enumerate(as_completed(futures), 1):
                company = futures[future]
                try:
                    entry = future.result()
                except Exception as exc:
                    entry = {
                        "domain": company["domain"],
                        "base_url": company["website"],
                        "status": "error",
                        "error": str(exc)[:200],
                    }
                persist(company, entry)
                if index % 25 == 0:
                    print(f"  {index}/{len(todo)}", flush=True)

    statuses: dict[str, int] = {}
    for entry in sites["sites"].values():
        key = entry.get("status", "?")
        statuses[key] = statuses.get(key, 0) + 1
    print("done:", statuses)


if __name__ == "__main__":
    main()
