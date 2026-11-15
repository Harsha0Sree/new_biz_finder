from pathlib import Path

from scanner.sources.base import unique_slug
from scanner.sources.startups_gallery import _parse_page, _slug_words

FIXTURES = Path(__file__).parent / "fixtures" / "source_startups_gallery"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_company_page_funding_and_facts() -> None:
    facts = _parse_page(
        "https://startups.gallery/companies/langchain",
        _load("langchain.html"),
        "langchain",
    )
    assert facts["company"] == "LangChain"
    assert facts["website"] == "https://www.langchain.com/"
    assert facts["description"] == "Easily integrate LLMs into your apps."
    assert facts["round_field"] == "Series C"
    assert facts["raised_raw"] == "$300M"
    assert facts["usd_equivalent"] == 300000000.0
    assert facts["date"] == "2026-11-13"
    assert facts["funding_date"] == "November 13, 2026"
    assert facts["lead_investor"] == "Sequoia Capital"
    assert facts["work_type"] == "Onsite"
    assert facts["employee_range"] == "201-500"
    assert facts["software_category"] == "DevTools"
    assert facts["location"] == "San Francisco, United States"
    assert facts["flags"] == []


def test_parses_bootstrapped_company_page() -> None:
    facts = _parse_page(
        "https://startups.gallery/companies/lightpage",
        _load("lightpage.html"),
        "lightpage",
    )
    assert facts["round_field"] == "Bootstrapped"
    assert facts["round_source"] == "article"
    assert facts["raised_raw"] == ""
    assert facts["usd_equivalent"] == 0.0
    assert facts["date"] == ""
    assert facts["funding_date"] == ""


def test_unparseable_page_keeps_slug_derived_record() -> None:
    facts = _parse_page("https://startups.gallery/companies/does-not-exist", "", "does-not-exist")
    assert facts["company"] == _slug_words("does-not-exist")
    assert facts["flags"] == ["parse_failed"]


def test_company_slug_uses_source_prefix() -> None:
    taken: set[str] = set()
    assert unique_slug("LangChain", "startups_gallery", taken) == "startups_gallery-langchain"
    assert unique_slug("LangChain", "startups_gallery", taken) == "startups_gallery-langchain-2"
