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


def _json_candidates(text: str) -> list[dict[str, Any]]:
    """Every JSON object in the text, outermost span last."""
    text = text.strip()
    if not text:
        return []

    candidates: list[dict[str, Any]] = []

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            candidates.append(data)
    except json.JSONDecodeError:
        pass

    for m in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            candidates.append(data)

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(text[first_brace : last_brace + 1])
            if isinstance(data, dict):
                candidates.append(data)
        except json.JSONDecodeError:
            pass

    return candidates


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Return the last parsable JSON object in the text, whatever its shape.

    `extract_json_payload` only accepts the six-key scoring contract. This one
    accepts any object, for tasks whose output schema is something else.
    """
    for candidate in reversed(_json_candidates(text)):
        return candidate
    return None


def extract_json_payload(text: str) -> dict[str, Any] | None:
    """Return the last schema-complete JSON object in the model's output.

    Candidates are tried in reverse order of appearance (the outermost
    brace span first, then fenced blocks from last to first, then a
    direct parse). An earlier block that happens to match the schema
    is accepted only because it is the last one that does; a block
    missing the six-key contract is ignored even when it carries a
    score, so an echoed injection block cannot stand in for the
    model's own answer.
    """
    text = text.strip()
    if not text:
        return None

    for candidate in reversed(_json_candidates(text)):
        if schema_valid_score(candidate) is not None:
            return candidate
    return None


_SCHEMA_KEYS = (
    "score",
    "verdict",
    "can_reproduce_48h",
    "agency_tier",
    "primary_risk",
    "target_service_offer",
)


def schema_valid_score(parsed: dict[str, Any] | None) -> int | None:
    """Validate the six-key output contract; return the int score or None."""
    if not isinstance(parsed, dict):
        return None
    for key in _SCHEMA_KEYS:
        if key not in parsed:
            return None
    score = parsed["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if isinstance(score, float) and not score.is_integer():
        return None
    if not 0 <= score <= 100:
        return None
    if not isinstance(parsed["verdict"], str):
        return None
    if not isinstance(parsed["can_reproduce_48h"], bool):
        return None
    for key in ("agency_tier", "primary_risk", "target_service_offer"):
        if not isinstance(parsed[key], str):
            return None
    return int(score)


def is_verified_record(data: Any) -> bool:
    """True only for records whose score came from a parsed score JSON.

    The stored score must agree with the parsed score, both must be
    in-range numbers, and the parsed block must satisfy the six-key
    schema. Records without a parsed score are diagnostics, not scores.
    """
    if not isinstance(data, dict) or data.get("error"):
        return False
    parsed_score = schema_valid_score(data.get("parsed"))
    if parsed_score is None:
        return False
    stored = data.get("score")
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return False
    if isinstance(stored, float) and not stored.is_integer():
        return False
    if not 0 <= stored <= 100:
        return False
    return int(stored) == parsed_score


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

    def preflight(self, *, probe_chat: bool = True) -> tuple[bool, str]:
        """Verify the endpoint serves the configured model before a batch run.

        `False` means every call in the batch would fail the same way, so the
        caller must stop instead of burning an entire run. The /models listing
        confirms availability; a one-token chat probe confirms completions
        actually stream back, which is what the 404/timeout failures lacked.
        Transport blips on /models warn and proceed.
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
            return self._probe_chat(
                f"preflight warning: cannot reach {self.base_url}/models ({exc}); verifying with chat probe"
            )
        if resp.status_code == 401:
            return False, "preflight failed: HTTP 401 unauthorized; check the API key"
        if resp.status_code == 403:
            return False, "preflight failed: HTTP 403 forbidden; the key lacks endpoint access"
        if resp.status_code in (404, 405):
            return False, (
                f"preflight failed: HTTP {resp.status_code} at {self.base_url}/models; "
                "the base URL or provider is wrong"
            )
        if resp.status_code != 200:
            return self._probe_chat(
                f"preflight warning: /models returned HTTP {resp.status_code}; verifying with chat probe"
            )
        try:
            raw = resp.json()
            ids = {
                str(item.get("id"))
                for item in (raw.get("data") or [])
                if isinstance(item, dict) and item.get("id")
            }
        except (ValueError, AttributeError):
            return self._probe_chat(
                "preflight warning: /models payload unparsable; verifying with chat probe"
            )
        if not ids:
            return False, f"preflight failed: /models at {self.base_url} lists no models"
        if self.model in ids or any(m.endswith(f"/{self.model}") for m in ids):
            listed = f"preflight ok: {self.model} is served by {self.base_url}"
            if not probe_chat:
                return True, listed + " (chat probe skipped)"
            return self._probe_chat(listed)
        short = self.model.split("/")[-1]
        close = sorted(m for m in ids if short and short in m)[:5]
        examples = ", ".join(close or sorted(ids)[:5])
        return False, (
            f"preflight failed: model {self.model!r} not found at {self.base_url}. "
            f"Closest available: {examples}. Fix NVIDIA_MODEL or pass --model."
        )

    def _probe_chat(self, listed: str) -> tuple[bool, str]:
        endpoint = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "temperature": 0,
            "max_tokens": 4,
        }
        try:
            with self._client_factory(min(self.timeout, 60.0)) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
        except Exception as exc:
            return False, (
                f"preflight failed: chat probe could not connect ({exc}); every evaluation "
                "would fail. Fix the endpoint or pass --skip-preflight."
            )
        if resp.status_code != 200:
            return False, (
                f"preflight failed: chat probe returned HTTP {resp.status_code}; every "
                "evaluation would fail. Fix the model/endpoint or pass --skip-preflight."
            )
        try:
            message = (resp.json().get("choices") or [{}])[0].get("message") or {}
            text = (message.get("content") or message.get("reasoning_content") or "").strip()
        except (ValueError, IndexError, AttributeError, TypeError):
            text = ""
        if not text:
            return False, (
                "preflight failed: chat probe returned an empty completion; every "
                "evaluation would fail. Pass --skip-preflight to run anyway."
            )
        return True, f"{listed}; chat probe answered"

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
        score_int = schema_valid_score(parsed)
        if score_int is None:
            if truncated:
                error = (
                    f"LLM output hit the max_tokens cap ({max_tokens}) before emitting "
                    "the score JSON block"
                )
            else:
                error = "LLM output contained no schema-complete score JSON block"
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
