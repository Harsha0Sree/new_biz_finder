from pathlib import Path
import json
import pytest

from scanner.llm import (
    LLMClient,
    extract_fallback_score,
    extract_json_payload,
)
from scanner.llm_analyzer import (
    assemble_company_context,
    get_qualifying_2026_companies,
    is_raised_in_year,
    load_system_prompt,
)


def test_is_raised_in_year():
    assert is_raised_in_year({"funding_date": "March 10, 2026"}, "2026") is True
    assert is_raised_in_year({"funding_date": "October 2024"}, "2026") is False
    assert is_raised_in_year({"title": "Company Raises $12M Seed in 2026"}, "2026") is True
    assert is_raised_in_year({"source_url": "https://example.com/2026/02/raise.html"}, "2026") is True


def test_get_qualifying_2026_companies():
    companies = get_qualifying_2026_companies("2026")
    assert len(companies) > 0
    # Every company must have raised >= 10M USD and be 2026
    for c in companies:
        assert c["usd_equivalent"] >= 10_000_000
        assert is_raised_in_year(c, "2026")
        assert not c.get("duplicate_of_previous")


def test_load_system_prompt():
    prompt = load_system_prompt(Path("prompts/system_prompt.txt"))
    assert len(prompt) > 100
    assert "agency" in prompt.lower()
    assert "score" in prompt.lower()


def test_extract_json_payload():
    direct = '{"score": 88, "verdict": "Great service play"}'
    parsed = extract_json_payload(direct)
    assert parsed is not None
    assert parsed["score"] == 88

    fenced = """Here is the evaluation:
```json
{
  "score": 92,
  "verdict": "High-ticket enterprise offer"
}
```
Hope this helps!"""
    parsed_fenced = extract_json_payload(fenced)
    assert parsed_fenced is not None
    assert parsed_fenced["score"] == 92

    bad = "Not a json response"
    assert extract_json_payload(bad) is None


def test_extract_fallback_score():
    assert extract_fallback_score('"score": 75') == 75
    assert extract_fallback_score('Overall Score: 85/100') == 85
    assert extract_fallback_score('No numbers here') == 50


def test_assemble_company_context():
    sample_company = {
        "slug": "test-ai-seed",
        "company": "Test AI",
        "website": "https://testai.example.com",
        "domain": "testai.example.com",
        "round_field": "Seed",
        "round_source": "article",
        "raised_raw": "$25M",
        "usd_equivalent": 25000000.0,
        "funding_date": "January 15, 2026",
        "lead_investor": "Top Tier Ventures",
        "additional_investors": "Angel Fund",
        "software_category": "AI Automation",
    }
    context = assemble_company_context(sample_company, scrape_missing=False)
    assert "# Company Analysis Target: Test AI" in context
    assert "$25M" in context
    assert "Top Tier Ventures" in context
    assert "January 15, 2026" in context
    # Brand new company should not mention other companies
    assert "Ineffable Intelligence" not in context


def test_llm_client_initialization():
    client_nvidia = LLMClient(provider="nvidia", api_key="test_key")
    assert client_nvidia.provider == "nvidia"
    assert "integrate.api.nvidia.com" in client_nvidia.base_url
    assert client_nvidia.api_key == "test_key"

    client_ollama = LLMClient(provider="ollama")
    assert client_ollama.provider == "ollama"
    assert "localhost:11434" in client_ollama.base_url

    with pytest.raises(ValueError):
        LLMClient(provider="unknown_provider")
