"""Shared contract for every source adapter.

An adapter is a boundary. It turns one site's bytes into `Company` records and
nothing else. It never touches the corpus, the prompt builder or the LLM.

Each adapter writes three files under `data/sources/<source>/`:

    index.json     what was crawled, and when
    articles.json  the raw items extraction ran on
    companies.json the extracted company records
"""

from __future__ import annotations

import re
import time
from typing import Any, Protocol

from scanner.models import Company
from scanner.paths import source_articles, source_companies, source_index
from scanner.storage import write_json

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")

# Hostnames that never identify the company an article is about.
NON_COMPANY_HOSTS = frozenset(
    {
        "techcrunch.com",
        "www.techcrunch.com",
        "twitter.com",
        "x.com",
        "www.x.com",
        "linkedin.com",
        "www.linkedin.com",
        "facebook.com",
        "www.facebook.com",
        "instagram.com",
        "youtube.com",
        "www.youtube.com",
        "threads.net",
        "substack.com",
        "medium.com",
        "github.com",
        "www.github.com",
        "wikipedia.org",
        "www.wikipedia.org",
        "google.com",
        "www.google.com",
        "play.google.com",
        "apps.apple.com",
        "apple.com",
        "www.apple.com",
        "amazon.com",
        "www.amazon.com",
        "microsoft.com",
        "www.microsoft.com",
        "crunchbase.com",
        "www.crunchbase.com",
        "linkedin.com/company",
        "notion.so",
        "docs.google.com",
        "calendly.com",
        "forms.gle",
        "t.co",
        "buff.ly",
        "bit.ly",
        "eventbrite.com",
        "www.eventbrite.com",
        "aol.com",
        "yahoo.com",
        "news.ycombinator.com",
        "reuters.com",
        "www.reuters.com",
        "bloomberg.com",
        "www.bloomberg.com",
        "wsj.com",
        "www.wsj.com",
        "ft.com",
        "www.ft.com",
        "cnbc.com",
        "www.cnbc.com",
        "forbes.com",
        "www.forbes.com",
        "businessinsider.com",
        "www.businessinsider.com",
        "nytimes.com",
        "www.nytimes.com",
        "npr.org",
        "www.npr.org",
        "bbc.com",
        "www.bbc.com",
        "bbc.co.uk",
        "theguardian.com",
        "www.theguardian.com",
        "fortune.com",
        "www.fortune.com",
        "time.com",
        "www.time.com",
        "axios.com",
        "www.axios.com",
        "wired.com",
        "www.wired.com",
        "theverge.com",
        "www.theverge.com",
        "arstechnica.com",
        "www.arstechnica.com",
        "cbsnews.com",
        "www.cbsnews.com",
        "engadget.com",
        "www.engadget.com",
        "zdnet.com",
        "www.zdnet.com",
        "fastcompany.com",
        "www.fastcompany.com",
        "techradar.com",
        "www.techradar.com",
        "gizmodo.com",
        "www.gizmodo.com",
        "venturebeat.com",
        "www.venturebeat.com",
        "inc.com",
        "www.inc.com",
        "gov.uk",
        "www.gov.uk",
        "whitehouse.gov",
        "europa.eu",
        "sec.gov",
        "www.sec.gov",
        "globenewswire.com",
        "www.globenewswire.com",
        "prnewswire.com",
        "www.prnewswire.com",
        "businesswire.com",
        "www.businesswire.com",
        "einnewswire.com",
        "www.einnewswire.com",
        "newsfilecorp.com",
        "accessnewswire.com",
        "benzinga.com",
        "www.benzinga.com",
        "tech.eu",
        "www.tech.eu",
    }
)


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation and legal suffixes from a company name."""
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(
        r"\s+(inc|llc|ltd|gmbh|bv|pty|co|corp|technologies|technology|labs|ai)\b.*$",
        "",
        n,
    )
    return re.sub(r"\s+", " ", n).strip()


def domain_of(url: str | None) -> str | None:
    """Host of a URL, without the www prefix."""
    if not url:
        return None
    m = re.match(r"^https?://(?:www\.)?([^/:?#]+)", url.strip())
    return m.group(1).lower() if m else None


def slugify(text: str, prefix: str = "") -> str:
    """Lowercase dash slug that satisfies `SLUG_RE`."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    base = re.sub(r"-{2,}", "-", base)[:120].strip("-")
    if prefix:
        base = f"{prefix}-{base}"
    if not base or not base[0].isalnum():
        base = f"x{base}" if base else "x"
    return base[:200]


def unique_slug(text: str, prefix: str, taken: set[str]) -> str:
    """A slug that is not already in `taken`. Appends -2, -3, ... on collision."""
    base = slugify(text, prefix)
    candidate = base
    counter = 2
    while candidate in taken:
        candidate = f"{base}-{counter}"
        counter += 1
    taken.add(candidate)
    return candidate


def is_company_host(host: str | None) -> bool:
    """True when a link host could belong to the company an article is about."""
    if not host:
        return False
    host = host.lower()
    if host in NON_COMPANY_HOSTS:
        return False
    if host.endswith(".techcrunch.com") or host.endswith(".linkedin.com"):
        return False
    if host.endswith(".gov") or host.endswith(".gov.uk"):
        return False
    return True


class SourceAdapter(Protocol):
    """What every adapter module exposes."""

    SOURCE: str

    def crawl(self, *, force: bool = False) -> dict[str, Any]:
        """Fetch the source's raw items and write index.json plus articles.json."""
        ...

    def extract(self) -> list[Company]:
        """Turn the raw items into company records and write companies.json."""
        ...


def write_index(source: str, index: dict[str, Any]) -> None:
    """Write `data/sources/<source>/index.json`."""
    payload = dict(index)
    payload.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    payload["source"] = source
    write_json(source_index(source), payload)


def write_articles(source: str, articles: list[dict[str, Any]]) -> None:
    """Write `data/sources/<source>/articles.json`."""
    write_json(
        source_articles(source),
        {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(articles),
            "articles": articles,
        },
    )


def write_companies(source: str, companies: list[Company]) -> None:
    """Write `data/sources/<source>/companies.json`."""
    write_json(source_companies(source), companies)
