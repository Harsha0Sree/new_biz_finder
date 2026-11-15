"""startups.gallery adapter: every company listed on the gallery.

The site is a Framer build that ships server-rendered HTML. The crawl reads
the companies section of the sitemap and then each company page; the
extraction turns the funding, investor, location, work-type and industry facts
the page itself renders into a company record.

A page that cannot be parsed still yields a record, named after the page slug,
so a single bad page never drops a company from the corpus.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from bs4 import BeautifulSoup

from scanner.httpcache import Response, fetch
from scanner.models import Company
from scanner.paths import (
    SOURCE_STARTUPS_GALLERY,
    source_articles,
    source_index,
)
from scanner.sources.base import (
    domain_of,
    normalize_name,
    unique_slug,
    write_articles,
    write_companies,
    write_index,
)
from scanner.storage import read_json

SOURCE = SOURCE_STARTUPS_GALLERY
QUALIFICATION = "every company listed on startups.gallery"

_BASE_URL = "https://startups.gallery"
_SITEMAP_URL = f"{_BASE_URL}/sitemap.xml"
_COMPANIES_PATH = "/companies/"
_WORK_TYPE_VALUES = ("Remote", "Hybrid", "Onsite")
_EN_DASH_RE = re.compile(r"\d+\s*[\u2010-\u2015]\s*\d+")
_RAISED_RE = re.compile(
    r"^Raised(?:\s+\$?(?P<amount>[\d.,]+)(?:\s*(?P<unit>[MmBb]))?)?\s+"
    r"(?P<stage>[^\n]+?)\s+on\s+(?P<written>[A-Za-z]+\s+\d{1,2},\s*\d{4})\s*$"
)
_AMOUNT_RE = re.compile(r"^\$(?P<num>[\d.,]+)(?P<unit>[MmBb])?$")
_SITEMAP_LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.IGNORECASE)
_UNIT_MULTIPLIERS = {"m": 1_000_000.0, "b": 1_000_000_000.0, "k": 1_000.0}


def _clean(value: Any) -> str:
    """Collapse whitespace and stringify, dropping the empty case."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json_ld(soup: BeautifulSoup) -> tuple[dict[str, Any], str]:
    """The Organization node and the industry breadcrumb from the JSON-LD."""
    organization: dict[str, Any] = {}
    industry = ""
    for script in soup.find_all("script", type="application/ld+json"):
        payload = json.loads(script.string or "{}")
        graph = payload.get("@graph") if isinstance(payload, dict) else None
        if not isinstance(graph, list):
            continue
        for entry in graph:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") == "Organization" and not organization:
                organization = entry
            if entry.get("@type") == "BreadcrumbList":
                for item in entry.get("itemListElement") or []:
                    if not isinstance(item, dict):
                        continue
                    link = str(item.get("item") or "")
                    if "/categories/industries/" in link:
                        industry = _clean(item.get("name"))
    return organization, industry


def _funding(soup: BeautifulSoup) -> dict[str, Any]:
    """The most recent round the page states, or the bootstrapped chip."""
    rounds: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for container in soup.find_all("div", attrs={"data-framer-name": "Amount Raised"}):
        for time_tag in container.find_all("time"):
            text = _clean(time_tag.get_text(" ", strip=True))
            if not text.startswith("Raised "):
                continue
            key = (str(time_tag.get("datetime") or ""), text)
            if key in seen:
                continue
            seen.add(key)
            rounds.append({"datetime": str(time_tag.get("datetime") or ""), "text": text})
    round_entry = max(rounds, key=lambda item: item["datetime"]) if rounds else None
    if round_entry is None:
        return {
            "round_field": _bootstrapped(soup),
            "raised_raw": "",
            "usd_equivalent": 0.0,
            "date": "",
            "funding_date": "",
        }
    match = _RAISED_RE.match(round_entry["text"])
    if not match:
        return {
            "round_field": "",
            "raised_raw": "",
            "usd_equivalent": 0.0,
            "date": "",
            "funding_date": "",
        }
    amount = _AMOUNT_RE.match(f"${match.group('amount')}{match.group('unit') or ''}")
    unit = (amount.group("unit") or "m").lower() if amount else "m"
    number = float(str(amount.group("num")).replace(",", "")) if amount else 0.0
    stage = _clean(match.group("stage"))
    return {
        "round_field": stage,
        "raised_raw": f"${amount.group('num')}{amount.group('unit') or ''}" if amount else "",
        "usd_equivalent": number * _UNIT_MULTIPLIERS.get(unit, _UNIT_MULTIPLIERS["m"]),
        "date": round_entry["datetime"][:10],
        "funding_date": _clean(match.group("written")),
    }


def _bootstrapped(soup: BeautifulSoup) -> str:
    """The stage chip a company without a round shows, e.g. Bootstrapped."""
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not href.startswith("../categories/stages/"):
            continue
        if _clean(anchor.get_text(" ", strip=True)) == "Bootstrapped":
            return "Bootstrapped"
    return ""


def _investors(soup: BeautifulSoup) -> list[str]:
    """Lead and additional investor names, in the order the page lists them."""
    names: list[str] = []
    seen: set[str] = set()
    previous = ""
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        match = re.match(r"^\.\./investors/([^/?#]+)$", href)
        if not match:
            continue
        slug = match.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        image = anchor.find("img")
        alt = _clean(image.get("alt")) if image is not None else ""
        name = _investor_name(slug, alt, previous)
        previous = name
        names.append(name)
    return names


def _investor_name(slug: str, alt: str, previous: str) -> str:
    """Display name for one investor, correcting consecutive logo mix-ups."""
    name = _clean(alt)
    if name.lower().startswith("logo of"):
        name = name[len("logo of") :].strip()
    if not name or name.lower() in {"n/a", "none", "null", "unknown"}:
        name = _slug_words(slug)
    if previous and name.lower() == previous.lower():
        name = _slug_words(slug)
    return name


def _slug_words(slug: str) -> str:
    """An investor slug turned into words, e.g. seq-capital -> Seq Capital."""
    words = [part for part in re.split(r"[-_]+", slug) if part]
    return " ".join(word.capitalize() for word in words) or slug


def _work_type(soup: BeautifulSoup) -> str:
    """The work type the company page reports for itself."""
    for element in soup.find_all(
        string=lambda value: value is not None and str(value).strip() in _WORK_TYPE_VALUES
    ):
        chain: list[str] = []
        node: Any = element
        while node is not None and len(chain) < 40:
            name = getattr(node, "name", None)
            chain.append(str(name) if name else "")
            node = node.parent
        names = [name for name in reversed(chain) if name]
        if "footer" in names:
            continue
        return str(element).strip()
    return ""


def _employee_range(soup: BeautifulSoup) -> str:
    """The headcount range the page shows, e.g. 51-200."""
    for element in soup.find_all(string=_EN_DASH_RE):
        text = _clean(element)
        return re.sub(r"\s*[\u2010-\u2015]\s*", "-", text)
    return ""


def _parse_page(url: str, text: str, slug: str) -> dict[str, Any]:
    """The source-specific facts scraped from one company page."""
    facts: dict[str, Any] = {
        "slug": slug,
        "source_url": url,
        "company": _slug_words(slug),
        "website": "",
        "description": "",
        "raised_raw": "",
        "usd_equivalent": 0.0,
        "round_field": "",
        "round_source": None,
        "funding_date": "",
        "date": "",
        "lead_investor": "",
        "additional_investors": "",
        "software_category": "",
        "location": "",
        "employee_range": "",
        "work_type": "",
        "flags": ["parse_failed"],
    }
    if not text.strip():
        return facts
    try:
        soup = BeautifulSoup(text, "lxml")
        organization, industry = _json_ld(soup)
        name = _clean(organization.get("name"))
        website = _clean(organization.get("url"))
        if website and "?r=0" in website:
            website = website.split("?")[0]
        address = organization.get("address") or {}
        city = _clean(address.get("addressLocality"))
        country = _clean(address.get("addressCountry"))
        funding = _funding(soup)
        investors = _investors(soup)
        flags: list[str] = []
        if not website:
            flags.append("no_website")
        facts.update(
            {
                "company": name,
                "website": website,
                "description": _clean(organization.get("description")),
                "round_field": funding["round_field"],
                "round_source": "article" if funding["round_field"] else None,
                "raised_raw": funding["raised_raw"],
                "usd_equivalent": float(funding["usd_equivalent"] or 0.0),
                "funding_date": funding["funding_date"],
                "date": funding["date"],
                "lead_investor": investors[0] if investors else "",
                "additional_investors": ", ".join(investors[1:]) if len(investors) > 1 else "",
                "software_category": industry,
                "location": f"{city}, {country}" if city and country else (city or country or ""),
                "employee_range": _employee_range(soup),
                "work_type": _work_type(soup),
                "flags": flags,
            }
        )
    except Exception:
        return facts
    facts["flags"] = flags
    return facts


def _article_from_url(url: str) -> dict[str, Any]:
    """The scraped facts for one startups.gallery company page."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    text = ""
    response: Response | None = fetch(url)
    if response is not None and response.ok:
        text = response.text
    return _parse_page(url, text, slug)


def _company_urls() -> list[str]:
    """Every startups.gallery company page URL from the sitemap."""
    response = fetch(_SITEMAP_URL)
    if not response.ok:
        raise ConnectionError(f"startups.gallery sitemap fetch failed: {response.status}")
    urls = [
        loc.strip()
        for loc in _SITEMAP_LOC_RE.findall(response.text)
        if _COMPANIES_PATH in loc.strip()
    ]
    return urls


def crawl(*, force: bool = False) -> dict[str, Any]:
    """Fetch every startups.gallery company page and write index plus articles."""
    if not force:
        existing = read_json(source_articles(SOURCE))
        if isinstance(existing, dict) and existing.get("articles"):
            return read_json(source_index(SOURCE)) or {}

    urls = _company_urls()
    articles: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for article in pool.map(_article_from_url, urls):
            articles.append(article)

    index = {
        "source": SOURCE,
        "api": _SITEMAP_URL,
        "company_pages": len(urls),
        "fetched_total": len(articles),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_index(SOURCE, index)
    write_articles(SOURCE, articles)
    print(f"startups_gallery: {len(articles)} companies from {len(urls)} pages", flush=True)
    return index


def _company_record(article: dict[str, Any], taken: set[str]) -> Company:
    """The corpus record for one startups.gallery company page."""
    company = _clean(article.get("company"))
    slug = unique_slug(company or _slug_words(str(article.get("slug") or "")), SOURCE, taken)
    round_field = _clean(article.get("round_field"))
    return {
        "slug": slug,
        "source": SOURCE,
        "qualification": QUALIFICATION,
        "article_url": str(article.get("source_url") or ""),
        "source_url": str(article.get("source_url") or ""),
        "title": f"{company} ({round_field})" if round_field else company,
        "date": _clean(article.get("date"))[:10],
        "company": company,
        "normalized_name": normalize_name(company),
        "domain": domain_of(str(article.get("website") or "")) or None,
        "website": str(article.get("website") or ""),
        "description": _clean(article.get("description")),
        "raised_raw": _clean(article.get("raised_raw")),
        "usd_equivalent": float(article.get("usd_equivalent") or 0.0),
        "round_field": round_field,
        "round_source": "article" if round_field else None,
        "funding_date": _clean(article.get("funding_date")),
        "lead_investor": _clean(article.get("lead_investor")),
        "additional_investors": _clean(article.get("additional_investors")),
        "software_category": _clean(article.get("software_category")),
        "batch": "",
        "upvotes": 0,
        "employee_range": _clean(article.get("employee_range")),
        "work_type": _clean(article.get("work_type")),
        "location": _clean(article.get("location")),
        "flags": list(article.get("flags") or []),
        "duplicate_of_previous": False,
    }


def extract() -> list[Company]:
    """Turn the crawled articles into company records and write companies.json."""
    payload = read_json(source_articles(SOURCE)) or {}
    articles = payload.get("articles") or []
    if not articles:
        raise FileNotFoundError(f"{source_articles(SOURCE)} has no articles. Run the crawl first.")

    records: list[Company] = []
    taken: set[str] = set()
    for article in articles:
        records.append(_company_record(article, taken))

    write_companies(SOURCE, records)
    print(f"startups_gallery: {len(records)} company records", flush=True)
    return records


def main() -> None:
    """Run the startups.gallery crawl followed by extraction."""
    crawl()
    extract()


if __name__ == "__main__":
    main()
