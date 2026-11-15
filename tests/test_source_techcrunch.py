import json
from pathlib import Path

from scanner.sources import techcrunch as tc

FIXTURE = Path(__file__).parent / "fixtures" / "source_techcrunch" / "articles_sample.json"


def _articles():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _by_title(fragment):
    return next(a for a in _articles() if a["title"].startswith(fragment))


def test_looks_like_company_name_rejects_junk():
    assert tc._looks_like_company_name("Aseon Labs") is True
    assert tc._looks_like_company_name("Cast AI") is True
    assert tc._looks_like_company_name("Noise, Garmin") is False
    assert tc._looks_like_company_name("Being Heumann") is True
    assert tc._looks_like_company_name("Executive Order 12333") is False
    assert tc._looks_like_company_name("London") is False
    assert tc._looks_like_company_name("2023, 2024") is False
    assert tc._looks_like_company_name("") is False


def test_name_in_article_matches_across_punctuation():
    text = "A New York-based startup called Shade is building a cloud storage platform."
    assert tc._name_in_article(text, "Shade") is True
    assert tc._name_in_article(text, "Cast AI") is False
    assert tc._name_in_article("Cast AI raises $20M", "Cast AI") is True


def test_build_candidates_drops_publishers_and_keeps_lead_first():
    article = _by_title("Wonderful raises")
    candidates = tc.build_candidates(article)
    assert candidates[0]["name"] == "Wonderful"
    assert candidates[0]["lead"] is True

    unicorns = tc.build_candidates(_by_title("Meet the new European unicorns"))
    domains = [c["domain"] for c in unicorns]
    assert "globenewswire.com" not in domains
    assert "prnewswire.com" not in domains
    assert "tech.eu" not in domains
    assert "aikido.dev" in domains


def test_resolve_domain_prefers_the_domain_that_carries_the_name():
    candidates = [
        {"name": "Aikido Security", "domain": "aikido.dev", "href": "", "lead": False},
        {"name": "blog post", "domain": "aikido.dev", "href": "", "lead": False},
    ]
    domain, flags = tc._resolve_domain("Aikido Security", 1, candidates)
    assert domain == "aikido.dev"
    assert flags == []


def test_resolve_domain_drops_a_publisher_link():
    candidates = [
        {"name": "Ford", "domain": "cbsnews.com", "href": "", "lead": False},
    ]
    domain, flags = tc._resolve_domain("Ford", 0, candidates)
    assert domain is None
    assert "domain_unverified" in flags


def test_judge_accepts_every_company_the_model_lists():
    article = _by_title("Meet the new European unicorns")
    candidates = tc.build_candidates(article)
    parsed = {
        "companies": [
            {"name": "Aikido Security", "candidate": 0, "is_startup": True},
            {"name": "Cast AI", "candidate": None, "is_startup": True},
        ],
        "reason": "roundup",
    }
    verdict = tc._judge_article(article, candidates, parsed)
    assert verdict["verdict"] == "company_found"
    names = [c["name"] for c in verdict["companies"]]
    assert names == ["Aikido Security", "Cast AI"]
    domains = {c["name"]: c["domain"] for c in verdict["companies"]}
    assert domains["Aikido Security"] == "aikido.dev"
    assert domains["Cast AI"] == "cast.ai"


def test_judge_rejects_a_company_that_is_not_a_startup():
    article = _by_title("The iPhone just had its best quarter ever")
    candidates = tc.build_candidates(article)
    parsed = {
        "companies": [{"name": "Apple", "candidate": None, "is_startup": False}],
        "reason": "public corporation",
    }
    verdict = tc._judge_article(article, candidates, parsed)
    assert verdict["verdict"] == "no_company_qualified"
    assert verdict["companies"] == []
    assert verdict["rejected"] == ["not_a_startup:Apple"]


def test_judge_rejects_a_name_that_is_not_in_the_article():
    article = _by_title("The iPhone just had its best quarter ever")
    candidates = tc.build_candidates(article)
    parsed = {
        "companies": [{"name": "Invented Labs", "candidate": None, "is_startup": True}],
        "reason": "made up",
    }
    verdict = tc._judge_article(article, candidates, parsed)
    assert verdict["verdict"] == "no_company_qualified"
    assert verdict["rejected"] == ["name_not_in_article:Invented Labs"]


def test_judge_falls_back_to_a_link_when_the_model_call_fails():
    article = _by_title("Wonderful raises")
    candidates = tc.build_candidates(article)
    verdict = tc._judge_article(article, candidates, None)
    assert verdict["verdict"] == "llm_unavailable"
    assert verdict["companies"][0]["name"] == "Wonderful"
    assert verdict["companies"][0]["domain"] == "wonderful.ai"


def test_company_record_carries_the_facts():
    article = _by_title("Wonderful raises")
    record = tc._company_record(
        article, {"name": "Wonderful", "domain": "wonderful.ai", "flags": []}, "techcrunch-wonderful"
    )
    assert record["slug"] == "techcrunch-wonderful"
    assert record["source"] == "techcrunch"
    assert record["company"] == "Wonderful"
    assert record["domain"] == "wonderful.ai"
    assert record["website"] == "https://wonderful.ai"
    assert record["usd_equivalent"] == 150_000_000
    assert record["raised_raw"] == "$150M"
    assert record["round_field"] == "Series B"
