from pathlib import Path

import httpx
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


class _FakeHTTPResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return self._responses.pop(0)


class _Fake404Response:
    status_code = 404

    def raise_for_status(self):
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("404 Not Found", request=request, response=response)

    def json(self):
        return {}


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


def test_llm_429_exhaustion_is_an_error_not_a_neutral_score(monkeypatch):
    responses = [_FakeHTTPResponse(429), _FakeHTTPResponse(429)]
    client = LLMClient(
        provider="nvidia",
        api_key="test_key",
        max_retries=2,
        client_factory=lambda _timeout: _FakeHTTPClient(responses),
    )
    monkeypatch.setattr("scanner.llm.time.sleep", lambda _seconds: None)

    result = client.analyze_company("system prompt", "company context")

    assert result.error is not None
    assert "rate limited" in result.error
    assert result.score == 0


def test_llm_does_not_retry_permanent_4xx(monkeypatch):
    fake_client = _FakeHTTPClient(
        [_Fake404Response(), _Fake404Response(), _Fake404Response()]
    )
    client = LLMClient(
        provider="nvidia",
        api_key="test_key",
        max_retries=3,
        client_factory=lambda _timeout: fake_client,
    )
    monkeypatch.setattr("scanner.llm.time.sleep", lambda _seconds: None)

    result = client.analyze_company("system prompt", "company context")

    assert result.error is not None
    assert "404" in result.error
    assert len(fake_client._responses) == 2


def test_llm_successful_fenced_json_is_parsed():
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "Here is my verdict.\n```json\n"
                        '{"score": 92, "verdict": "Strong niche service play"}\n'
                        "```"
                    )
                }
            }
        ],
        "usage": {"total_tokens": 42},
    }
    client = LLMClient(
        provider="nvidia",
        api_key="test_key",
        client_factory=lambda _timeout: _FakeHTTPClient(
            [_FakeHTTPResponse(200, payload)]
        ),
    )

    result = client.analyze_company("system prompt", "company context")

    assert result.error is None
    assert result.score == 92
    assert result.verdict == "Strong niche service play"
    assert result.usage == {"total_tokens": 42}
