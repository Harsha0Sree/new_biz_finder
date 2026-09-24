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


def registered_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def extract_pricing(soup: BeautifulSoup, text: str) -> dict:
    """Extract public pricing information, pricing tiers, price points, and sales-led CTAs."""
    # 1. Price points like $29, $49/mo, $199/month, $1,200/yr, etc.
    price_matches = re.findall(
        r"\$\s*\d[\d,]*(?:\.\d{2})?\s*(?:/(?:mo(?:nth)?|yr|year|user|seat|agent|dev|member))?",
        text,
        re.IGNORECASE,
    )
    valid_prices: list[str] = []
    for p in price_matches:
        p_clean = re.sub(r"\s+", "", p)
        if re.search(r"[mbk]$", p_clean, re.I):  # skip $10M, $50M
            continue
        if p_clean in ("$2020", "$2021", "$2022", "$2023", "$2024", "$2025", "$2026", "$2027"):
            continue
        if p_clean not in valid_prices:
            valid_prices.append(p_clean)

    # 2. Plan names: Free, Starter, Pro, Growth, Team, Enterprise, Custom
    plans: list[str] = []
    for m in re.finditer(
        r"\b(Free(?:\s+Tier)?|Starter|Pro|Professional|Growth|Business|Team|Enterprise|Custom|Usage-based)\b",
        text,
        re.IGNORECASE,
    ):
        plan = m.group(1).title()
        if plan not in plans:
            plans.append(plan)

    # 3. Sales-led vs self-serve CTAs
    sales_led_markers = re.findall(
        r"\b(book\s+a\s+demo|request\s+(?:a\s+)?demo|contact\s+sales|talk\s+to\s+(?:sales|expert)|schedule\s+(?:a\s+)?demo|custom\s+pricing|get\s+a\s+quote)\b",
        text,
        re.IGNORECASE,
    )
    has_sales_led = len(sales_led_markers) > 0
    has_public_pricing = len(valid_prices) > 0 and any("/" in p or (p.startswith("$") and p[1:].isdigit() and int(p[1:]) < 5000) for p in valid_prices)

    summary_parts = []
    if has_public_pricing:
        summary_parts.append(f"Public Pricing: {', '.join(valid_prices[:5])}")
        if plans:
            summary_parts.append(f"Tiers: {', '.join(plans[:5])}")
    elif has_sales_led:
        summary_parts.append("Sales-Led / Enterprise: No public self-serve pricing (CTAs: 'Book a Demo' / 'Contact Sales')")
    else:
        summary_parts.append("No public pricing published on website.")

    return {
        "has_public_pricing": has_public_pricing,
        "price_points": valid_prices[:10],
        "plans": plans[:8],
        "is_sales_led": has_sales_led,
        "summary": " | ".join(summary_parts),
    }


def strip_html(html: str) -> tuple[str, str, dict]:
    """Return (clean_text, title, pricing_info). Recovers SPA state from __NEXT_DATA__ and JSON-LD."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_desc = ""
    desc_tag = (
        soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        or soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
        or soup.find("meta", attrs={"name": re.compile(r"twitter:description", re.I)})
    )
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()

    # Next.js SPA pre-rendered state
    next_data_text = ""
    next_tag = soup.find("script", id="__NEXT_DATA__")
    if next_tag and next_tag.string:
        try:
            nd = json.loads(next_tag.string)
            props = nd.get("props", {}).get("pageProps", {})

            def extract_strings(obj, depth=3):
                if depth <= 0:
                    return []
                res = []
                if isinstance(obj, str) and len(obj.strip()) > 20 and not obj.strip().startswith(("http", "data:", "{", "[")):
                    res.append(obj.strip())
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        if k not in ("_id", "id", "slug", "image", "icon", "url", "href"):
                            res.extend(extract_strings(v, depth - 1))
                elif isinstance(obj, list):
                    for it in obj[:15]:
                        res.extend(extract_strings(it, depth - 1))
                return res

            strings = extract_strings(props)
            if strings:
                next_data_text = "\n".join(dict.fromkeys(strings))[:4000]
        except Exception:
            pass

    # JSON-LD structured data
    json_ld_text = ""
    for script in soup.find_all("script", type="application/ld+json"):
        if script.string:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    desc = data.get("description") or data.get("headline")
                    if desc:
                        json_ld_text += f"\nStructured Info: {desc}"
            except Exception:
                pass

    headings: list[str] = []
    for h in soup.find_all(["h1", "h2", "h3"])[:12]:
        htxt = h.get_text(" ", strip=True)
        if htxt and len(htxt) < 120 and htxt not in headings:
            headings.append(htxt)

    # Decompose script/style tags
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

    pricing_info = extract_pricing(soup, text)
    return text, title, pricing_info


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
            if norm != "/" and norm not in found and len(found) < max_subpages:
                found.append(norm)

        # Prioritize /pricing subpages first
        found.sort(key=lambda p: (0 if "pricing" in p.lower() else 1))

        for n, path in enumerate(found):
            sub_url = urljoin(resp.final_url, path + "/")
            try:
                sub_resp = fetch(sub_url, timeout=15.0, force_refetch=force_refetch)
            except ConnectionError:
                entry["pages"][path] = {"status": "error"}
                continue
            if not sub_resp.ok:
                entry["pages"][path] = {"status": f"http_{sub_resp.status}"}
                continue

            sub_text, _t, sub_pricing = strip_html(sub_resp.text)
            sub_status = classify(sub_resp.status, sub_text)
            fname = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")[:40]
            (TEXT_DIR / f"site__{domain}__{fname}.txt").write_text(sub_text)
            entry["pages"][path] = {"status": sub_status, "chars": len(sub_text)}

            # If pricing subpage found, upgrade pricing summary
            if sub_pricing.get("has_public_pricing") or "pricing" in path.lower():
                if sub_pricing.get("has_public_pricing") or not entry["pricing"].get("has_public_pricing"):
                    entry["pricing"] = sub_pricing

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
