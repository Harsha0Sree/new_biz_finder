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
    # "ok" when the score came from a parsed JSON block. "unparseable" when no
    # machine-readable score existed; those records never rank.
    parse_status: str = "ok"
    truncated: bool = False


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


def _parse_score(parsed: dict[str, Any] | None) -> int | None:
    score = (parsed or {}).get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return max(0, min(100, int(score)))


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

    def preflight(self) -> tuple[bool, str]:
        """Verify the endpoint serves the configured model before a batch run.

        A hard `False` means every call in the batch would fail the same way,
        so the caller must stop instead of burning an entire run on HTTP 404s.
        Unverifiable checks (unreachable or unusable /models) warn and proceed.
        """
        if self.provider == "nvidia" and not self.api_key:
            return False, "NVIDIA_API_KEY is not set. Export it or pass --api-key."
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with self._client_factory(self.timeout) as client:
                resp = client.get(f"{self.base_url}/models", headers=headers)
        except Exception as exc:
            return True, f"preflight warning: cannot reach {self.base_url}/models ({exc}); continuing"
        if resp.status_code == 401:
            return False, "preflight failed: HTTP 401 unauthorized; check the API key"
        if resp.status_code == 403:
            return False, "preflight failed: HTTP 403 forbidden; the key lacks endpoint access"
        if resp.status_code != 200:
            return True, f"preflight warning: /models returned HTTP {resp.status_code}; continuing"
        try:
            ids = {
                str(item.get("id"))
                for item in (resp.json().get("data") or [])
                if isinstance(item, dict) and item.get("id")
            }
        except (ValueError, AttributeError):
            return True, "preflight warning: /models payload unparsable; continuing"
        if not ids:
            return True, "preflight warning: /models returned an empty list; continuing"
        if self.model in ids or any(m.endswith(f"/{self.model}") for m in ids):
            return True, f"preflight ok: {self.model} is served by {self.base_url}"
        short = self.model.split("/")[-1]
        close = sorted(m for m in ids if short and short in m)[:5]
        examples = ", ".join(close or sorted(ids)[:5])
        return False, (
            f"preflight failed: model {self.model!r} not found at {self.base_url}. "
            f"Closest available: {examples}. Fix NVIDIA_MODEL or pass --model."
        )

    def analyze_company(
        self,
        system_prompt: str,
        company_context: str,
        temperature: float = 0.2,
        max_tokens: int = 6000,
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
                        # Keep both channels; the score JSON may land in either.
                        raw_text = "\n\n".join(t for t in (content, reasoning) if t)
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
                parse_status="error",
            )

        completed_tokens = (usage or {}).get("completion_tokens")
        truncated = (
            isinstance(completed_tokens, int)
            and not isinstance(completed_tokens, bool)
            and completed_tokens >= max_tokens
        )
        parsed = extract_json_payload(raw_text)
        score_int = _parse_score(parsed)
        if score_int is None:
            if truncated:
                error = (
                    f"LLM output hit the max_tokens cap ({max_tokens}) before emitting "
                    "the score JSON block"
                )
            else:
                error = "LLM output contained no machine-readable score JSON block"
            return LLMResult(
                score=0,
                verdict=f"Analysis failed: {error}",
                parsed=parsed or {},
                raw_response=raw_text,
                provider=self.provider,
                model=self.model,
                usage=usage,
                error=error,
                parse_status="unparseable",
                truncated=truncated,
            )

        verdict = str((parsed or {}).get("verdict") or "")
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
            parsed=parsed or {},
            raw_response=raw_text,
            provider=self.provider,
            model=self.model,
            usage=usage,
            error=None,
            parse_status="ok",
            truncated=truncated,
        )
