"""The merged company corpus.

Every source writes its own records under `data/sources/<source>/`. This
module merges them into `data/corpus.json`, which is the single list the
downstream steps read. A company that appears in more than one source is kept
once; the later copies are marked `duplicate_of_previous` and the winner
absorbs any fact the winner was missing.
"""

from __future__ import annotations

from typing import Any

from scanner.models import Company
from scanner.paths import ALL_SOURCES, CORPUS, source_companies
from scanner.sources.base import domain_of, normalize_name
from scanner.storage import read_json, write_json

# Fields a duplicate may donate to the record that wins.
MERGEABLE_FIELDS = (
    "description",
    "website",
    "domain",
    "raised_raw",
    "usd_equivalent",
    "amount_source",
    "round_field",
    "round_source",
    "funding_date",
    "lead_investor",
    "additional_investors",
    "software_category",
    "batch",
    "upvotes",
    "employee_range",
    "work_type",
    "location",
)

# How a record got into the corpus. Each source states its own rule; the
# thesaasnews records predate the source folders, so their rule lives here.
QUALIFICATIONS = {
    "thesaasnews": "seed-stage round of at least $10M USD-equivalent",
}


def load_source_companies(source: str) -> list[Company]:
    """Records for one source. Empty when that source has not been crawled."""
    payload = read_json(source_companies(source))
    if not payload:
        return []
    if not isinstance(payload, list):
        return []
    return [c for c in payload if isinstance(c, dict)]


def _identity_key(company: dict[str, Any]) -> tuple[str, str]:
    """Key that says whether two records are the same company.

    A domain is proof of identity. Without one, an exact name match is the
    only signal available, so it is used on its own.
    """
    domain = str(company.get("domain") or "")
    name = normalize_name(str(company.get("company") or ""))
    return (domain, name) if domain else ("", name)


def _merge_into(winner: dict[str, Any], other: dict[str, Any]) -> None:
    """Copy facts the winner is missing from a duplicate record."""
    for field in MERGEABLE_FIELDS:
        if not winner.get(field) and other.get(field):
            winner[field] = other[field]
    if not winner.get("domain") and other.get("domain"):
        winner["domain"] = other["domain"]
    if not winner.get("website") and other.get("website"):
        winner["website"] = other["website"]
    extra_sources = list(winner.get("also_in_sources") or [])
    if other.get("source") and other["source"] != winner.get("source"):
        extra_sources.append(other["source"])
    if extra_sources:
        winner["also_in_sources"] = sorted(set(extra_sources))


def merge_sources(
    per_source: dict[str, list[Company]],
) -> list[Company]:
    """Merge per-source records into one deduplicated corpus.

    Sources are merged in the order given, so the first source that knows a
    company keeps the record. Later copies are marked as duplicates and hand
    their missing facts to the winner.
    """
    merged: list[Company] = []
    by_domain: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    for source, records in per_source.items():
        for record in records:
            company = dict(record)
            company.setdefault("source", source)
            domain = str(company.get("domain") or "")
            name = normalize_name(str(company.get("company") or ""))
            winner = by_domain.get(domain) if domain else None
            if winner is None and name:
                winner = by_name.get(name)
            if winner is not None:
                company["duplicate_of_previous"] = True
                _merge_into(winner, company)
                merged.append(company)
                continue
            company["duplicate_of_previous"] = False
            merged.append(company)
            if domain:
                by_domain[domain] = company
            if name:
                by_name.setdefault(name, company)

    return merged


def build_corpus() -> list[Company]:
    """Merge every source on disk and write `data/corpus.json`."""
    per_source: dict[str, list[Company]] = {}
    for source in ALL_SOURCES:
        records = load_source_companies(source)
        for record in records:
            record.setdefault("source", source)
            record.setdefault("qualification", QUALIFICATIONS.get(source, ""))
            if not record.get("domain"):
                record["domain"] = domain_of(record.get("website"))
        per_source[source] = records
    merged = merge_sources(per_source)
    write_json(CORPUS, merged)
    return merged


def load_corpus() -> list[Company]:
    """The merged corpus. Builds it on disk when it is missing."""
    payload = read_json(CORPUS)
    if isinstance(payload, list) and payload:
        return [c for c in payload if isinstance(c, dict)]
    return build_corpus()


def unique_companies(companies: list[Company]) -> list[Company]:
    """Records that carry the company, with the duplicates dropped."""
    return [c for c in companies if not c.get("duplicate_of_previous")]
