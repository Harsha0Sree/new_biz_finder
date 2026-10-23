"""Unified LLM client supporting NVIDIA NIM and Ollama.

Provides isolated, fresh context windows per company call with robust error
handling, retries, and structured JSON parsing.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_MODEL = "openai/gpt-oss-20b"

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.1"


@dataclass
class LLMResult:
    score: int
    verdict: str
    parsed: dict[str, Any]
    raw_response: str
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def extract_json_payload(text: str) -> dict[str, Any] | None:
    """Extract and parse JSON from LLM response (handling markdown fences and preamble)."""
    text = text.strip()
    if not text:
        return None

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Try finding outermost { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def extract_fallback_score(text: str) -> int:
    """Extract a numeric score 0-100 when JSON parsing is incomplete."""
    if not text:
        return 50

    # 1. Look for explicit score field or statement
    patterns = [
        r'"score"\s*:\s*(\d{1,3})',
        r'final\s+score\s+(?:of\s+the\s+startup\s*)?[:*–-]*\s*(\d{1,3})',
        r'overall\s+(?:agency\s+)?score\s*[:*–-]*\s*(\d{1,3})',
        r'agency\s+opportunity\s+score\s*[:*–-]*\s*(\d{1,3})',
        r'\bscore\b\s*[:*–-]*\s*(\d{1,3})(?:/100)?',
        r'\b(\d{1,3})\s*/\s*100\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = int(m.group(1))
                if 0 <= val <= 100:
                    return val
            except ValueError:
                pass

    # 2. Heuristic check based on strong rejection / disqualification language
    lower = text.lower()
    if any(phrase in lower for phrase in [
        "not a viable solo-agency opportunity",
        "not a viable agency opportunity",
        "does not create a viable agency opportunity",
        "terrible agency opportunity",
        "zero agency opportunity",
        "disqualified",
    ]):
        return 15

    if any(phrase in lower for phrase in [
        "exceptional agency opportunity",
        "strong agency opportunity",
        "ideal agency opportunity",
        "high potential agency opportunity",
    ]):
        return 85

    return 50  # neutral fallback


class LLMClient:
    """Stateless client for NVIDIA NIM and Ollama with per-call isolated context."""

    def __init__(
        self,
        provider: str = "nvidia",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        client_factory: Callable[[float], httpx.Client] | None = None,
    ) -> None:
        self.provider = provider.lower().strip()
        if self.provider not in ("nvidia", "ollama"):
            raise ValueError(f"Unsupported provider: {provider!r}. Choose 'nvidia' or 'ollama'.")

        self.timeout = timeout
        self.max_retries = max_retries
        self._client_factory = client_factory or (
            lambda timeout: httpx.Client(timeout=timeout)
        )

        if self.provider == "nvidia":
            self.base_url = (
                base_url
                or os.getenv("NVIDIA_BASE_URL")
                or DEFAULT_NVIDIA_BASE_URL
            ).rstrip("/")
            self.api_key = api_key or os.getenv("NVIDIA_API_KEY", "")
            self.model = (
                model
                or os.getenv("NVIDIA_MODEL")
                or os.getenv("LLM_MODEL")
                or DEFAULT_NVIDIA_MODEL
            )
        else:  # ollama
            self.base_url = (
                base_url
                or os.getenv("OLLAMA_BASE_URL")
                or os.getenv("OLLAMA_HOST")
                or DEFAULT_OLLAMA_BASE_URL
            ).rstrip("/")
            if not self.base_url.endswith("/v1"):
                # Normalize http://localhost:11434 -> http://localhost:11434/v1
                self.base_url = f"{self.base_url}/v1"
            self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "ollama")
            self.model = (
                model
                or os.getenv("OLLAMA_MODEL")
                or os.getenv("LLM_MODEL")
                or DEFAULT_OLLAMA_MODEL
            )

    def analyze_company(
        self,
        system_prompt: str,
        company_context: str,
        temperature: float = 0.2,
        max_tokens: int = 3500,
    ) -> LLMResult:
        """Execute a single-turn analysis with a completely fresh context window."""
        if self.provider == "nvidia" and not self.api_key:
            err = "NVIDIA_API_KEY is not set. Export NVIDIA_API_KEY='nvapi-...' or pass --api-key."
            return LLMResult(
                score=0,
                verdict=f"Analysis failed: {err}",
                parsed={},
                raw_response="",
                provider=self.provider,
                model=self.model,
                usage={},
                error=err,
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": company_context},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error = None
        raw_text = ""
        usage: dict[str, int] = {}

        for attempt in range(1, self.max_retries + 1):
            try:
                with self._client_factory(self.timeout) as client:
                    resp = client.post(endpoint, headers=headers, json=payload)
                    if resp.status_code == 429:
                        last_error = (
                            f"rate limited (HTTP 429) after {self.max_retries} attempts"
                        )
                        if attempt < self.max_retries:
                            time.sleep(2.0 * (2 ** (attempt - 1)))
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = (msg.get("content") or "").strip()
                        reasoning = (msg.get("reasoning_content") or "").strip()
                        if content and len(content) > 150:
                            raw_text = content
                        elif reasoning:
                            raw_text = (content + "\n\n" + reasoning).strip() if content else reasoning
                        else:
                            raw_text = content
                    usage = data.get("usage", {})
                    last_error = None
                    break
            except httpx.HTTPStatusError as exc:
                last_error = str(exc)
                status = exc.response.status_code
                # A 4xx (other than 429, handled above) will not fix itself.
                if 400 <= status < 500:
                    break
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
            except Exception as exc:
                if self.provider == "ollama" and "connect" in str(exc).lower():
                    last_error = (
                        f"Failed to connect to Ollama at {self.base_url}. "
                        "Ensure Ollama is installed and running (`ollama serve`)."
                    )
                else:
                    last_error = str(exc)
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)

        if not raw_text:
            error = last_error or "LLM returned an empty response"
            return LLMResult(
                score=0,
                verdict=f"Analysis failed: {error}",
                parsed={},
                raw_response="",
                provider=self.provider,
                model=self.model,
                usage={},
                error=error,
            )

        parsed = extract_json_payload(raw_text) or {}
        score = parsed.get("score")
        if isinstance(score, (int, float)):
            score_int = max(0, min(100, int(score)))
        else:
            score_int = extract_fallback_score(raw_text)

        verdict = parsed.get("verdict") or ""
        if not verdict and raw_text:
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            for ln in lines:
                cleaned = re.sub(r"^[#*_\-\s]+|[#*_\-\s]+$", "", ln).strip()
                lower_cl = cleaned.lower()
                if (
                    cleaned
                    and not lower_cl.startswith("executive conclusion")
                    and not lower_cl.startswith("1. executive conclusion")
                    and not lower_cl.startswith("section")
                    and len(cleaned) > 20
                ):
                    verdict = cleaned[:250]
                    break
            if not verdict and lines:
                verdict = lines[0][:250]

        return LLMResult(
            score=score_int,
            verdict=verdict,
            parsed=parsed,
            raw_response=raw_text,
            provider=self.provider,
            model=self.model,
            usage=usage,
            error=None,
        )
