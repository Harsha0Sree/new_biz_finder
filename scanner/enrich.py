"""Join company records with the site data collected in step 4.

`companies.json` is written before websites are fetched, so pricing and site
status live only in `sites.json`. Evaluators need both on the company record.
Keeping the join here means every consumer sees the same shape.
"""

from __future__ import annotations

import threading
from typing import Any

from scanner.paths import SITES
from scanner.storage import read_json, write_json

_sites_lock = threading.Lock()


def load_sites(path=SITES) -> dict[str, dict[str, Any]]:
    payload = read_json(path, {"sites": {}})
    if not isinstance(payload, dict):
        return {}
    sites = payload.get("sites", {})
    return sites if isinstance(sites, dict) else {}


def enrich_company(company: dict[str, Any], sites: dict[str, dict[str, Any]]) -> dict[str, Any]:
    domain = company.get("domain")
    site = sites.get(domain) if domain else None
    if not site:
        return dict(company)
    return {
        **company,
        "site_status": site.get("status"),
        "pricing": site.get("pricing") or {},
    }


def enrich_companies(
    companies: list[dict[str, Any]],
    sites: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    site_index = load_sites() if sites is None else sites
    return [enrich_company(company, site_index) for company in companies]


def update_site(
    domain: str,
    record: dict[str, Any],
    path=SITES,
) -> None:
    """Merge one site record into sites.json under a process-wide lock."""
    with _sites_lock:
        payload = read_json(path, {"sites": {}})
        sites = payload.setdefault("sites", {})
        sites[domain] = record
        write_json(path, payload)
