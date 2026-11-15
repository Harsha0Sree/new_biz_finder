"""Y Combinator batch source adapter.

Pulls every company from the six tracked YC batches through the Algolia
index and turns the raw hits into company records.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from scanner.httpcache import fetch
from scanner.models import Company
from scanner.paths import source_articles
from scanner.sources.base import (
    domain_of,
    normalize_name,
    unique_slug,
    write_articles,
    write_companies,
    write_index,
)
from scanner.storage import read_json

SOURCE = "yc"
QUALIFICATION = "YC batch startup"


def crawl(*, force: bool = False) -> dict[str, Any]:
    """Fetch the six tracked Y Combinator batches and write index + raw hits.

    Returns the index payload describing what was crawled.
    """
    response = fetch("https://www.ycombinator.com/companies", force_refetch=force, timeout=20.0)
    if not response.ok:
        raise ConnectionError(f"yc companies page fetch failed: HTTP {response.status}")
    opts_match = re.search(r"window\.AlgoliaOpts\s*=\s*(\{.*?\});", response.text, re.S)
    if opts_match is None:
        raise ValueError("yc companies page did not contain AlgoliaOpts")
    opts = json.loads(opts_match.group(1))
    app_id = str(opts.get("app") or "45BWZJ1SGC")
    api_key = str(opts.get("key") or "")
    batches = (
        "Winter 2026",
        "Spring 2026",
        "Summer 2026",
        "Fall 2026",
        "Winter 2027",
        "Summer 2027",
    )
    hits: list[dict[str, Any]] = []
    per_batch: list[dict[str, Any]] = []
    for batch in batches:
        params = f"query=&hitsPerPage=1000&page=0&filters=batch%3A%22{batch.replace(' ', '%20')}%22"
        query_response = httpx.post(
            f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/*/queries",
            json={
                "requests": [
                    {
                        "indexName": "YCCompany_By_Launch_Date_production",
                        "params": params,
                    }
                ]
            },
            headers={
                "x-algolia-application-id": app_id,
                "x-algolia-api-key": api_key,
                "content-type": "application/json",
            },
            timeout=30.0,
        )
        if query_response.status_code != 200:
            raise ConnectionError(f"yc algolia query failed: HTTP {query_response.status_code}")
        query_body = query_response.json()
        batch_hits = query_body.get("results", [{}])[0].get("hits") or []
        hits.extend(batch_hits)
        per_batch.append({"batch": batch, "count": len(batch_hits)})

    index = {"batches": per_batch, "total": len(hits)}
    write_index(SOURCE, index)
    write_articles(SOURCE, hits)
    return index


def extract() -> list[Company]:
    """Turn the cached YC hits into company records and write companies.json."""
    payload = read_json(source_articles(SOURCE), {"articles": []})
    hits = payload.get("articles") if isinstance(payload, dict) else []
    records: list[Company] = []
    taken: set[str] = set()
    for hit in hits:
        name = str(hit.get("name") or "")
        batch = str(hit.get("batch") or "")
        slug = unique_slug(name, "yc", taken)
        website = str(hit.get("website") or "").strip()
        domain = domain_of(website)
        one_liner = str(hit.get("one_liner") or "").strip()
        long_description = str(hit.get("long_description") or "").strip()
        first_sentence = ""
        if long_description:
            first_sentence = re.split(r"(?<=[.!?])\s+", long_description, maxsplit=1)[0].strip()
        description = one_liner or first_sentence
        launched_at = hit.get("launched_at") or 0
        date_str = (
            datetime.fromtimestamp(int(launched_at), tz=UTC).strftime("%Y-%m-%d")
            if launched_at
            else ""
        )
        team_size = hit.get("team_size") or 0
        employee_range = (
            f"{team_size} employees" if isinstance(team_size, int) and team_size > 0 else ""
        )
        software_category = (
            str(hit.get("industry") or "").strip() or str(hit.get("subindustry") or "").strip()
        )
        stage = str(hit.get("stage") or "")
        tags = [str(tag) for tag in (hit.get("tags") or []) if str(tag).strip()]
        work_type = next((tag for tag in tags if tag.lower() in ("remote", "onsite", "hybrid")), "")
        flags = ["no_website"] if not website else []
        hit_slug = str(hit.get("slug") or slug)
        records.append(
            {
                "slug": slug,
                "source": SOURCE,
                "qualification": QUALIFICATION,
                "article_url": f"https://www.ycombinator.com/companies/{hit_slug}",
                "source_url": f"https://www.ycombinator.com/companies/{hit_slug}",
                "title": f"{name} ({batch})",
                "date": date_str,
                "company": name,
                "normalized_name": normalize_name(name),
                "domain": domain,
                "website": website,
                "description": description,
                "raised_raw": "",
                "usd_equivalent": 0.0,
                "round_field": stage,
                "round_source": "article",
                "funding_date": "",
                "lead_investor": "",
                "additional_investors": "",
                "software_category": software_category,
                "batch": batch,
                "upvotes": 0,
                "employee_range": employee_range,
                "work_type": work_type,
                "location": str(hit.get("all_locations") or ""),
                "flags": flags,
                "duplicate_of_previous": False,
            }
        )
    write_companies(SOURCE, records)
    return records


if __name__ == "__main__":
    print(crawl())
    print(f"companies={len(extract())}")
