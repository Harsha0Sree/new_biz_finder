import re

from scanner.paths import REPORTS, SCORED
from scanner.reports import master_ranking, reports_index, slug_to_filename
from scanner.storage import read_json


def _scored_records(limit=2):
    payload = read_json(SCORED)
    assert payload and payload.get("companies")
    return payload["companies"][:limit]


def test_slug_to_filename_is_stable_and_safe():
    assert slug_to_filename("Acme Raises $12M Seed!") == "acme-raises-12m-seed.md"
    assert slug_to_filename("a/b/c") == "a-b-c.md"
    assert len(slug_to_filename("x" * 200)) <= 83


def test_master_ranking_uses_relative_links_that_exist():
    records = _scored_records()
    text = master_ranking(records)

    links = re.findall(r"\]\(([^)]+)\)", text)
    assert links
    for link in links:
        assert not link.startswith("/")
        assert link.endswith(".md")
    for record in records:
        assert f"]({slug_to_filename(record['slug'])})" in text
        assert (REPORTS / slug_to_filename(record["slug"])).exists()


def test_reports_index_links_to_both_evaluation_passes():
    text = reports_index(_scored_records(), {"successful": 1, "unverified": 4, "errored": 47})

    assert "[Master ranking](master-ranking.md)" in text
    assert "[LLM quick ranking](llm_opportunity_ranking.md)" in text
    assert "1 verified, 4 unverified, 47 errored" in text
