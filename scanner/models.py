"""Typed shapes for the pipeline's JSON artifacts.

These are documentation with teeth: every boundary that reads or writes one of
these files has a name for what it expects. Runtime validation lives in
`scanner.validate`, because JSON on disk is untrusted input.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

RoundKind = Literal["seed", "pre-seed", "pre-series-a", "other-series", "unlabeled"]
SiteStatus = Literal["ok", "js_only", "dead", "dead_parked", "error"]


class ArticleIndexEntry(TypedDict, total=False):
    slug: str
    url: str
    title: str
    date: str | None
    tag: str
    tag_page: int


class FundingDetails(TypedDict, total=False):
    company: str
    website: str
    raised: str
    round: str
    funding_date: str
    lead_investor: str
    additional_investors: str
    software_category: str
    source: str


class Company(TypedDict, total=False):
    slug: str
    article_url: str
    title: str
    date: str
    company: str
    normalized_name: str
    domain: str | None
    website: str | None
    raised_raw: str
    usd_equivalent: float
    amount_source: str
    round_field: str
    round_source: str
    pre_seed: bool
    pre_series_a: bool
    flags: list[str]
    funding_date: str
    lead_investor: str
    additional_investors: str
    software_category: str
    source_url: str
    duplicate_of_previous: bool
    pricing: dict[str, Any]
    site_status: str


class PricingInfo(TypedDict, total=False):
    has_public_pricing: bool
    price_points: list[str]
    plans: list[str]
    is_sales_led: bool
    summary: str


class SiteRecord(TypedDict, total=False):
    domain: str
    base_url: str
    pages: dict[str, dict[str, Any]]
    pricing: PricingInfo
    fetched_at: str | None
    status: SiteStatus
    title: str
    final_url: str
    error: str
    http_status: int


class GateResult(TypedDict):
    gate: str
    applied: bool
    rationale: str


class CategoryScore(TypedDict):
    h1: int
    h2: int
    h3: int
    h4: int
    evidence: str


class AgencyPlay(TypedDict, total=False):
    build_scope: str
    packaging: str
    pricing: str
    first_clients: str


class Evaluation(TypedDict, total=False):
    slug: str
    company: str
    domain: str | None
    archetype: str
    archetype_rationale: str
    confidence: str
    gates: list[GateResult]
    categories: dict[str, CategoryScore]
    agency_play: AgencyPlay
    sources_read: list[str]


class LLMEvaluation(TypedDict, total=False):
    slug: str
    company: str
    domain: str | None
    website: str | None
    usd_equivalent: float
    raised_raw: str
    round_field: str
    funding_date: str
    lead_investor: str
    software_category: str
    pricing: PricingInfo
    provider: str
    model: str
    score: int
    verdict: str
    parsed: dict[str, Any]
    raw_response: str
    usage: dict[str, int]
    error: str | None
    status: Literal["ok", "error"]
    context_chars: int
    evaluated_at: str
