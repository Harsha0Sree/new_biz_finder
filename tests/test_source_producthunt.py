"""Offline tests for the Product Hunt source adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scanner.models import Company
from scanner.sources import producthunt as producthunt_source
from scanner.sources.base import normalize_name

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "source_producthunt"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _articles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    posts = ((payload or {}).get("data") or {}).get("posts") or {}
    articles: list[dict[str, Any]] = []
    for edge in posts.get("edges") or []:
        if not (isinstance(edge, dict) and isinstance(edge.get("node"), dict)):
            continue
        articles.append(producthunt_source._to_article(edge["node"]))
    return articles


def _install_fake_graphql(
    monkeypatch: Any,
    pages: list[dict[str, Any]],
) -> list[tuple[str, str, dict[str, Any]]]:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append((token, query, dict(variables)))
        return pages[min(len(calls) - 1, len(pages) - 1)]

    monkeypatch.setattr(producthunt_source, "_graphql", fake_graphql)
    monkeypatch.setattr(producthunt_source, "write_index", lambda source, index: None)
    monkeypatch.setattr(producthunt_source, "write_articles", lambda source, articles: None)
    return calls


def test_missing_token_prints_hint_and_writes_nothing(monkeypatch, capsys):
    monkeypatch.delenv("PRODUCTHUNT_TOKEN", raising=False)
    writes: list[str] = []
    monkeypatch.setattr(
        producthunt_source, "write_index", lambda source, index: writes.append("index")
    )
    monkeypatch.setattr(
        producthunt_source, "write_articles", lambda source, articles: writes.append("articles")
    )

    assert producthunt_source.crawl() == {}

    assert writes == []
    out = capsys.readouterr().out
    assert "PRODUCTHUNT_TOKEN" in out
    assert "https://www.producthunt.com/v2/api" in out


def test_crawl_sends_specified_graphql_query_and_filters_votes(monkeypatch):
    monkeypatch.setenv("PRODUCTHUNT_TOKEN", "ph-test-token")
    calls = _install_fake_graphql(
        monkeypatch,
        [_load_fixture("posts_page_1.json"), _load_fixture("posts_page_2.json")],
    )

    index = producthunt_source.crawl()

    assert len(calls) == 2
    token_used, query, variables = calls[0]
    assert token_used == "ph-test-token"
    assert query == producthunt_source._POSTS_QUERY
    assert variables == {
        "first": 100,
        "after": None,
        "order": "VOTES",
        "postedAfter": "2026-01-01T00:00:00Z",
        "postedBefore": "2027-01-01T00:00:00Z",
    }
    assert index["qualifying"] == 3


def test_crawl_stops_paging_when_lowest_votes_at_or_below_cutoff(monkeypatch):
    monkeypatch.setenv("PRODUCTHUNT_TOKEN", "ph-test-token")
    calls = _install_fake_graphql(
        monkeypatch,
        [_load_fixture("posts_page_1.json"), _load_fixture("posts_page_2.json")],
    )
    written: dict[str, Any] = {}

    def fake_write_articles(source: str, articles: list[dict[str, Any]]) -> Any:
        written["articles"] = articles
        return None

    monkeypatch.setattr(producthunt_source, "write_articles", fake_write_articles)

    producthunt_source.crawl()

    assert len(calls) == 2
    assert calls[0][2]["after"] is None
    assert calls[1][2]["after"] == "eyJkaXJlY3Qtc2l6ZToxfQ"
    assert len(written["articles"]) == 3


def test_extract_maps_articles_to_company_records(monkeypatch):
    payload = {
        "generated_at": "2026-11-14T00:00:00Z",
        "count": 3,
        "articles": _articles(_load_fixture("posts_page_1.json")),
    }
    monkeypatch.setattr(producthunt_source, "read_json", lambda path, default=None: payload)
    captured: dict[str, Any] = {}

    def fake_write_companies(source: str, companies: list[Company]) -> Any:
        captured["companies"] = companies
        return None

    monkeypatch.setattr(producthunt_source, "write_companies", fake_write_companies)

    companies = producthunt_source.extract()

    assert len(companies) == 3
    first = companies[0]
    assert first["slug"] == "producthunt-acme-ai"
    assert first["source"] == "producthunt"
    assert first["qualification"] == producthunt_source.QUALIFICATION
    assert first["article_url"] == "https://www.producthunt.com/posts/acme-ai"
    assert first["source_url"] == "https://www.producthunt.com/posts/acme-ai"
    assert first["title"] == "Acme AI"
    assert first["company"] == "Acme AI"
    assert first["date"] == "2026-06-11"
    assert first["normalized_name"] == normalize_name("Acme AI")
    assert first["domain"] == "acmeai.com"
    assert first["website"] == "https://acmeai.com"
    assert first["description"] == "Ship AI features 10x faster."
    assert first["raised_raw"] == ""
    assert first["usd_equivalent"] == 0.0
    assert first["round_field"] == ""
    assert first["round_source"] == ""
    assert first["funding_date"] == ""
    assert first["lead_investor"] == ""
    assert first["additional_investors"] == ""
    assert first["software_category"] == "Artificial Intelligence"
    assert first["batch"] == ""
    assert first["upvotes"] == 812
    assert first["employee_range"] == ""
    assert first["work_type"] == ""
    assert first["location"] == ""
    assert first["flags"] == []
    assert first["duplicate_of_previous"] is False

    second = companies[1]
    assert second["slug"] == "producthunt-loopware"
    assert second["flags"] == ["no_website"]
    assert second["website"] == "https://www.producthunt.com/posts/loopware"
    assert second["upvotes"] == 640

    third = companies[2]
    assert third["software_category"] == "SaaS"
    assert third["upvotes"] == 540
    assert captured["companies"] == companies


def test_extract_returns_empty_list_when_no_articles_saved(monkeypatch):
    monkeypatch.setattr(producthunt_source, "read_json", lambda path, default=None: None)
    captured: dict[str, Any] = {}

    def fake_write_companies(source: str, companies: list[Company]) -> Any:
        captured["companies"] = companies
        return None

    monkeypatch.setattr(producthunt_source, "write_companies", fake_write_companies)

    assert producthunt_source.extract() == []
