import json

from scanner import validate
from scanner.storage import write_text


def _report():
    return validate.Report()


def test_validate_articles_detects_count_mismatch_and_duplicates():
    report = _report()
    payload = {
        "count": 4,
        "articles": [
            {"slug": "a", "url": "https://x/a", "title": "A"},
            {"slug": "a", "url": "https://x/a", "title": "A"},
            {"slug": "b", "url": "https://x/b"},
        ],
    }

    validate.validate_articles(payload, report)

    joined = "\n".join(report.errors)
    assert "count=4 but articles=3" in joined
    assert "duplicate slug a" in joined
    assert "b missing title" in joined


def test_validate_qualifying_rejects_below_threshold():
    report = _report()
    payload = {
        "kept_count": 1,
        "qualifying": [
            {
                "slug": "small",
                "usd_equivalent": 9_000_000,
                "round_kind": "seed",
                "filter_reason": "ok",
            }
        ],
    }

    validate.validate_qualifying(payload, 10, {"small"}, report)

    assert any("below threshold" in error for error in report.errors)


def test_validate_qualifying_allows_resolved_valuation_only_candidate():
    report = _report()
    payload = {
        "kept_count": 1,
        "index_count": 10,
        "qualifying": [
            {
                "slug": "valuation-only",
                "usd_equivalent": 3_000_000,
                "round_kind": "pre-seed",
                "filter_reason": "check_article_valuation_only",
            }
        ],
    }

    validate.validate_qualifying(payload, 10, {"valuation-only"}, report)

    assert report.errors == []
    assert report.warnings == []


def test_validate_qualifying_warns_on_unresolved_valuation_only_candidate():
    report = _report()
    payload = {
        "kept_count": 1,
        "index_count": 10,
        "qualifying": [
            {
                "slug": "valuation-only",
                "usd_equivalent": 3_000_000,
                "round_kind": "pre-seed",
                "filter_reason": "check_article_valuation_only",
            }
        ],
    }

    validate.validate_qualifying(payload, 10, set(), report)

    assert report.errors == []
    assert any("unresolved valuation-only" in warning for warning in report.warnings)


def _company(**overrides):
    company = {
        "slug": "acme-seed",
        "company": "Acme",
        "article_url": "https://example.com/acme",
        "title": "Acme Raises $12M Seed",
        "usd_equivalent": 12_000_000,
        "round_field": "Seed",
        "round_source": "article",
        "normalized_name": "acme",
        "domain": "acme.io",
        "website": "https://acme.io",
    }
    company.update(overrides)
    return company


def test_validate_companies_accepts_title_inferred_round():
    report = _report()

    validate.validate_companies(
        [_company(round_field="", round_source="title")], 1, report
    )

    assert report.errors == []


def test_validate_companies_rejects_empty_round_without_title_fallback():
    report = _report()

    validate.validate_companies(
        [_company(round_field="", round_source="article")], 1, report
    )

    assert any("no round_field" in error for error in report.errors)


def test_validate_companies_rejects_unlabeled_title_fallback():
    report = _report()

    validate.validate_companies(
        [
            _company(
                round_field="",
                round_source="title",
                title="Acme Raises $12M in Funding",
            )
        ],
        1,
        report,
    )

    assert any("no seed-stage label" in error for error in report.errors)


def test_validate_scored_detects_stale_missing_count():
    report = _report()
    payload = {
        "evaluated_count": 1,
        "missing_count": 0,
        "invalid_count": 0,
        "companies": [{"slug": "acme", "total": 75, "tier": "B"}],
    }
    companies = [{"slug": "acme"}, {"slug": "beta"}]

    validate.validate_scored(payload, companies, {"acme": {}}, report)

    assert any("missing_count=0 but 1 unique companies" in error for error in report.errors)


def test_validate_llm_evals_requires_aggregate_to_match_successes(tmp_path):
    evals = tmp_path / "llm_evals"
    evals.mkdir()
    write_text(
        evals / "ok.json",
        json.dumps(
            {
                "slug": "ok",
                "company": "Ok",
                "provider": "nvidia",
                "model": "m",
                "score": 80,
                "verdict": "test verdict",
                "parsed": {
                    "score": 80,
                    "verdict": "test verdict",
                    "can_reproduce_48h": True,
                    "agency_tier": "Tier 2",
                    "primary_risk": "risk",
                    "target_service_offer": "offer",
                },
                "status": "ok",
            }
        ),
    )
    write_text(
        evals / "bad.json",
        json.dumps(
            {
                "slug": "bad",
                "company": "Bad",
                "provider": "nvidia",
                "model": "m",
                "score": 0,
                "error": "timeout",
            }
        ),
    )
    report = _report()

    validate.validate_llm_evals([{"slug": "bad"}], evals, report)

    assert any("does not match successful" in error for error in report.errors)
    assert any("1 errored records" in warning for warning in report.warnings)

    report = _report()
    validate.validate_llm_evals(
        [
            {
                "slug": "ok",
                "score": 80,
                "model": "m",
                "provider": "nvidia",
                "verdict": "test verdict",
                "usd_equivalent": 10_000_000.0,
            }
        ],
        evals,
        report,
    )
    assert report.errors == []


def test_validate_reports_detects_broken_links(tmp_path):
    write_text(tmp_path / "master-ranking.md", "[Missing](missing.md)\n")
    write_text(tmp_path / "index.md", "# Reports\n")
    write_text(tmp_path / "llm_opportunity_ranking.md", "# ok\n")
    report = _report()

    validate.validate_reports(tmp_path, report)

    assert any("broken link missing.md" in error for error in report.errors)


def test_validate_reports_accepts_existing_relative_links(tmp_path):
    write_text(tmp_path / "company.md", "# Company\n")
    write_text(
        tmp_path / "master-ranking.md",
        "[Company](company.md) and [External](https://example.com/x.md)\n",
    )
    write_text(tmp_path / "index.md", "[Company](company.md)\n")
    write_text(tmp_path / "llm_opportunity_ranking.md", "# ok\n")
    report = _report()

    validate.validate_reports(tmp_path, report)

    assert report.errors == []


def test_validate_filter_reconciliation_detects_gaps():
    report = _report()
    articles = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
    qualifying = [{"slug": "a"}]
    dropped_payload = {"dropped_count": 1, "dropped": [{"slug": "b"}]}

    validate.validate_filter_reconciliation(articles, qualifying, dropped_payload, report)

    joined = "\n".join(report.errors)
    assert "1 index slugs are neither kept nor dropped" in joined
    assert report.checks["dropped"] == 1


def test_validate_filter_reconciliation_accepts_exact_partition():
    report = _report()
    articles = [{"slug": "a"}, {"slug": "b"}]

    validate.validate_filter_reconciliation(
        articles, [{"slug": "a"}], {"dropped_count": 1, "dropped": [{"slug": "b"}]}, report
    )

    assert report.errors == []
