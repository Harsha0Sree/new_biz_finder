"""Offline mapping tests for the Y Combinator source adapter."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scanner.sources.yc as yc_source
from scanner.models import Company
from scanner.sources.base import SLUG_RE, domain_of, normalize_name
from scanner.storage import write_json

FIXTURE = Path(__file__).parent / "fixtures" / "source_yc" / "algolia_winter_2026.json"
BATCH = "Winter 2026"
SOURCE_URL = "https://www.ycombinator.com/companies/"


def _hits() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["results"][0]["hits"]


def _install_articles(monkeypatch, hits: list[dict[str, Any]], tmp_path: Path) -> None:
    articles_path = tmp_path / "articles.json"
    write_json(
        articles_path,
        {"generated_at": "2026-11-14T00:00:00Z", "count": len(hits), "articles": hits},
    )
    monkeypatch.setattr(yc_source, "source_articles", lambda source: articles_path)
    monkeypatch.setattr(yc_source, "write_companies", lambda source, companies: None)


def test_source_exposes_the_yc_adapter_contract() -> None:
    assert yc_source.SOURCE == "yc"
    assert isinstance(yc_source.QUALIFICATION, str) and yc_source.QUALIFICATION
    assert callable(yc_source.crawl)
    assert callable(yc_source.extract)


def test_extract_maps_fixture_hits(tmp_path, monkeypatch) -> None:
    hits = _hits()
    _install_articles(monkeypatch, hits, tmp_path)
    records: list[Company] = yc_source.extract()

    assert len(records) == len(hits) == 198
    slugs: set[str] = set()
    for hit, record in zip(hits, records, strict=False):
        name = str(hit.get("name") or "")
        batch = str(hit.get("batch") or BATCH)
        assert record["source"] == "yc"
        assert record["qualification"] == yc_source.QUALIFICATION
        assert record["batch"] == batch
        assert batch in (
            "Winter 2026",
            "Spring 2026",
            "Summer 2026",
            "Fall 2026",
            "Winter 2027",
            "Summer 2027",
        )
        assert record["company"] == name
        assert record["normalized_name"] == normalize_name(name)
        assert record["slug"].startswith("yc-")
        assert len(record["slug"]) <= 200
        assert SLUG_RE.match(record["slug"])
        assert record["slug"] not in slugs
        slugs.add(record["slug"])
        assert record["title"] == f"{name} ({batch})"
        launched_at = hit.get("launched_at") or 0
        expected_date = (
            datetime.fromtimestamp(int(launched_at), tz=UTC).strftime("%Y-%m-%d")
            if launched_at
            else ""
        )
        assert record["date"] == expected_date
        assert record["round_source"] == "article"
        assert record["round_field"] == str(hit.get("stage") or "")
        assert record["usd_equivalent"] == 0.0
        assert record["raised_raw"] == ""
        assert record["funding_date"] == ""
        assert record["lead_investor"] == ""
        assert record["additional_investors"] == ""
        assert record["duplicate_of_previous"] is False
        assert record["upvotes"] == 0
        hit_slug = str(hit.get("slug") or "")
        expected_url = f"{SOURCE_URL}{hit_slug}"
        assert record["source_url"] == expected_url
        assert record["article_url"] == expected_url
        assert record["website"] == str(hit.get("website") or "")
        assert record["domain"] == domain_of(record["website"])
        one_liner = str(hit.get("one_liner") or "").strip()
        long_description = str(hit.get("long_description") or "").strip()
        first_sentence = (
            re.split(r"(?<=[.!?])\s+", long_description, maxsplit=1)[0].strip()
            if long_description
            else ""
        )
        assert record["description"] == (one_liner or first_sentence)
        team_size = hit.get("team_size") or 0
        expected_employee_range = (
            f"{team_size} employees" if isinstance(team_size, int) and team_size > 0 else ""
        )
        assert record["employee_range"] == expected_employee_range
        tags = [str(tag) for tag in (hit.get("tags") or []) if str(tag).strip()]
        expected_work_type = next(
            (tag for tag in tags if tag.lower() in ("remote", "onsite", "hybrid")), ""
        )
        assert record["work_type"] == expected_work_type
        expected_flags = ["no_website"] if not str(hit.get("website") or "").strip() else []
        assert record["flags"] == expected_flags

    no_website_count = sum(1 for hit in hits if not str(hit.get("website") or "").strip())
    assert len([r for r in records if r["flags"]]) == no_website_count
