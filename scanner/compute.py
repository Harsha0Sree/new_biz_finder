"""Deterministic score computation from evaluator JSON files.

Reads SCORING_SPEC.md-consistent weights, `data/evals/<slug>.json`, and
`data/companies.json`; computes pillar rollups, archetype adjustments, gate
masks, totals, and tiers; writes `data/scored.json` and `data/scores.csv`.
Resume-safe and re-weightable: weights live here only.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from scanner.paths import CORPUS, SCORED, SCORES_CSV, source_evals
from scanner.storage import read_json, write_json, write_text

HEAD_WEIGHTS = {"h1": 0.30, "h2": 0.35, "h3": 0.25, "h4": 0.10}

PILLARS: dict[str, dict] = {
    "P1": {"name": "Build Feasibility", "weight": 0.20, "cats": list(range(1, 8))},
    "P2": {"name": "Agency Delivery Model Fit", "weight": 0.15, "cats": list(range(8, 15))},
    "P3": {"name": "High-Ticket Revenue Potential", "weight": 0.18, "cats": list(range(15, 22))},
    "P4": {"name": "Market Demand Signals", "weight": 0.12, "cats": list(range(22, 28))},
    "P5": {"name": "Technical Barrier (Moat-Inverse)", "weight": 0.10, "cats": list(range(28, 34))},
    "P6": {"name": "Risk & Liability Burden", "weight": 0.10, "cats": list(range(34, 40))},
    "P7": {"name": "Niche Accessibility", "weight": 0.08, "cats": list(range(40, 45))},
    "P8": {"name": "Durability of Opportunity", "weight": 0.07, "cats": list(range(45, 51))},
    "P9": {"name": "Bonus Signals", "weight": 0.05, "cats": [51, 52]},
}

ARCHETYPES: dict[str, dict[str, float]] = {
    # pillar -> multiplier (missing pillar = neutral 1.0)
    "ai_infra_devtools": {"P1": 1.3, "P5": 1.3, "P3": 0.9},
    "vertical_ai_saas": {},
    "fintech_regtech": {"P6": 1.4, "P5": 1.2, "P2": 0.9},
    "healthtech_bio": {"P6": 1.5, "P7": 0.9},
    "sales_marketing_cx": {"P2": 1.2, "P3": 1.1},
    "other": {},
}

GATE_MULTIPLIERS = {"G1": 0.05, "G2": 0.15, "G3": 0.10, "G4": 0.25, "G5": 0.20}
GATE_IDS = frozenset(GATE_MULTIPLIERS)

COMPANIES_OUT = CORPUS
SCORED_OUT = SCORED
CSV_OUT = SCORES_CSV

if sum(p["weight"] for p in PILLARS.values()) <= 0:
    raise ValueError("pillar weights must be positive")


def combined_head_score(cat: dict) -> float:
    return sum(HEAD_WEIGHTS[h] * cat[h] for h in HEAD_WEIGHTS)


def compute_total(eval_data: dict) -> dict:
    cats = eval_data["categories"]
    expected = {str(i) for i in range(1, 53)}
    if set(cats) != expected:
        raise ValueError(f"{eval_data.get('slug')}: expected categories 1..52")
    slug = eval_data.get("slug")
    if not slug:
        raise ValueError("evaluation is missing its slug")

    pillar_scores: dict[str, float] = {}
    for pillar_id, pillar in PILLARS.items():
        values = [combined_head_score(cats[str(c)]) for c in pillar["cats"]]
        pillar_scores[pillar_id] = sum(values) / len(values) / 10.0  # normalize to 0-1

    archetype = eval_data["archetype"]
    if archetype not in ARCHETYPES:
        raise ValueError(f"unknown archetype {archetype}")

    raw_weights = {
        pillar_id: pillar["weight"] * ARCHETYPES[archetype].get(pillar_id, 1.0)
        for pillar_id, pillar in PILLARS.items()
    }
    total_raw_weight = sum(raw_weights.values())
    adjusted_weights = {
        pillar_id: weight / total_raw_weight for pillar_id, weight in raw_weights.items()
    }

    base = sum(adjusted_weights[pid] * pillar_scores[pid] for pid in PILLARS)

    gate_ids = [gate["gate"] for gate in eval_data.get("gates", [])]
    if set(gate_ids) != GATE_IDS:
        raise ValueError(
            f"{eval_data.get('slug')}: gates must cover exactly {sorted(GATE_IDS)}, "
            f"got {sorted(gate_ids)}"
        )
    if len(gate_ids) != len(set(gate_ids)):
        raise ValueError(f"duplicate gate in {eval_data.get('slug')}")

    gate_mask = 1.0
    applied_gates = []
    for gate in eval_data.get("gates", []):
        if gate["applied"]:
            gate_mask *= GATE_MULTIPLIERS[gate["gate"]]
            applied_gates.append(gate["gate"])

    total = round(gate_mask * base * 100, 2)
    tier = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"

    return {
        "pillar_scores_0_10": {k: round(v * 10, 3) for k, v in pillar_scores.items()},
        "pillar_weights_raw": {k: round(v, 5) for k, v in raw_weights.items()},
        "pillar_weights_adjusted": {k: round(v, 5) for k, v in adjusted_weights.items()},
        "category_combined_0_10": {
            k: round(combined_head_score(v), 3) for k, v in cats.items()
        },
        "applied_gates": applied_gates,
        "gate_mask": round(gate_mask, 4),
        "total": total,
        "tier": tier,
    }


def _csv_text(scored: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    columns = [
        "rank",
        "company",
        "domain",
        "archetype",
        "usd_equivalent",
        "software_category",
        "total",
        "tier",
        "confidence",
        "applied_gates",
    ] + [f"P{n}" for n in range(1, 10)]
    writer.writerow(columns)
    for index, item in enumerate(scored, 1):
        writer.writerow(
            [
                index,
                item["company"],
                item["domain"],
                item["archetype"],
                item["usd_equivalent"],
                item["software_category"],
                item["total"],
                item["tier"],
                item["confidence"],
                ",".join(item["applied_gates"]),
            ]
            + [item["pillar_scores_0_10"][f"P{n}"] for n in range(1, 10)]
        )
    return buffer.getvalue()


def main() -> None:
    companies = read_json(COMPANIES_OUT)
    if companies is None:
        raise FileNotFoundError(f"{COMPANIES_OUT} not found.")
    scored: list[dict] = []
    missing: list[str] = []
    invalid: list[str] = []
    for company in companies:
        if company.get("duplicate_of_previous"):
            continue
        path = source_evals(company.get("source") or "") / f"{company['slug']}.json"
        if not path.exists():
            missing.append(company["slug"])
            continue
        try:
            evaluation = read_json(path)
            if evaluation.get("slug") != company["slug"]:
                raise ValueError(
                    f"eval file slug {evaluation.get('slug')!r} does not match {company['slug']!r}"
                )
            computed = compute_total(evaluation)
        except Exception as exc:  # schema/validation errors surface loudly
            invalid.append(f"{company['slug']}: {exc}")
            continue
        merged = {**evaluation, **computed}
        for key in (
            "company",
            "domain",
            "website",
            "usd_equivalent",
            "raised_raw",
            "software_category",
            "lead_investor",
            "funding_date",
            "flags",
            "pre_series_a",
            "article_url",
        ):
            merged[key] = company.get(key)
        scored.append(merged)

    scored.sort(key=lambda item: item["total"], reverse=True)
    duplicate_count = sum(1 for c in companies if c.get("duplicate_of_previous"))
    payload = {
        "framework_version": "v1",
        "evaluated_count": len(scored),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "duplicate_count": duplicate_count,
        "companies": scored,
    }
    write_json(SCORED_OUT, payload)
    if scored:
        write_text(CSV_OUT, _csv_text(scored))
    print(f"scored={len(scored)} missing={len(missing)} invalid={len(invalid)}")
    if invalid:
        print("INVALID:")
        for line in invalid[:20]:
            print(" ", line)


if __name__ == "__main__":
    main()
