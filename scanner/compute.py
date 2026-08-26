"""Deterministic score computation from evaluator JSON files.

Reads SCORING_SPEC.md-consistent weights, data/evals/<slug>.json files, and
data/companies.json; computes combined scores, pillar rollups, archetype
adjustments, gate masks, totals, tiers; writes data/scored.json and
data/scores.csv. Resume-safe and re-weightable (weights live here only).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HEAD_WEIGHTS = {"h1": 0.30, "h2": 0.35, "h3": 0.25, "h4": 0.10}

PILLARS: dict[str, dict] = {
    "P1": {
        "name": "Build Feasibility",
        "weight": 0.20,
        "cats": list(range(1, 8)),
    },
    "P2": {
        "name": "Agency Delivery Model Fit",
        "weight": 0.15,
        "cats": list(range(8, 15)),
    },
    "P3": {
        "name": "High-Ticket Revenue Potential",
        "weight": 0.18,
        "cats": list(range(15, 22)),
    },
    "P4": {
        "name": "Market Demand Signals",
        "weight": 0.12,
        "cats": list(range(22, 28)),
    },
    "P5": {
        "name": "Technical Barrier (Moat-Inverse)",
        "weight": 0.10,
        "cats": list(range(28, 34)),
    },
    "P6": {
        "name": "Risk & Liability Burden",
        "weight": 0.10,
        "cats": list(range(34, 40)),
    },
    "P7": {
        "name": "Niche Accessibility",
        "weight": 0.08,
        "cats": list(range(40, 45)),
    },
    "P8": {
        "name": "Durability of Opportunity",
        "weight": 0.07,
        "cats": list(range(45, 51)),
    },
    "P9": {
        "name": "Bonus Signals",
        "weight": 0.05,
        "cats": [51, 52],
    },
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

EVALS_DIR = Path("data/evals")
COMPANIES_OUT = Path("data/companies.json")
SCORED_OUT = Path("data/scored.json")
CSV_OUT = Path("data/scores.csv")


def combined_head_score(cat: dict) -> float:
    return sum(HEAD_WEIGHTS[h] * cat[h] for h in HEAD_WEIGHTS)


def compute_total(eval_data: dict) -> dict:
    cats = eval_data["categories"]
    assert set(cats.keys()) == {str(i) for i in range(1, 53)}, (
        f"{eval_data.get('slug')}: expected categories 1..52"
    )

    pillar_scores: dict[str, float] = {}
    for pid, p in PILLARS.items():
        vals = [combined_head_score(cats[str(c)]) for c in p["cats"]]
        pillar_scores[pid] = sum(vals) / len(vals) / 10.0  # normalize to 0-1

    arch = eval_data["archetype"]
    assert arch in ARCHETYPES, f"unknown archetype {arch}"
    raw_w = {pid: p["weight"] * ARCHETYPES[arch].get(pid, 1.0) for pid, p in PILLARS.items()}
    z = sum(raw_w.values())
    adj_w = {pid: w / z for pid, w in raw_w.items()}

    base = sum(adj_w[pid] * pillar_scores[pid] for pid in PILLARS)

    gate_mask = 1.0
    applied_gates = []
    for g in eval_data.get("gates", []):
        if g["applied"]:
            gate_mask *= GATE_MULTIPLIERS[g["gate"]]
            applied_gates.append(g["gate"])

    total = round(gate_mask * base * 100, 2)
    tier = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"

    return {
        "pillar_scores_0_10": {k: round(v * 10, 3) for k, v in pillar_scores.items()},
        "pillar_weights_raw": {k: round(v, 5) for k, v in raw_w.items()},
        "pillar_weights_adjusted": {k: round(v, 5) for k, v in adj_w.items()},
        "category_combined_0_10": {
            k: round(combined_head_score(v), 3) for k, v in cats.items()
        },
        "applied_gates": applied_gates,
        "gate_mask": round(gate_mask, 4),
        "total": total,
        "tier": tier,
    }


def main() -> None:
    companies = json.loads(COMPANIES_OUT.read_text())
    by_slug = {c["slug"]: c for c in companies}
    scored: list[dict] = []
    missing: list[str] = []
    invalid: list[str] = []
    for c in companies:
        if c.get("duplicate_of_previous"):
            continue
        path = EVALS_DIR / f"{c['slug']}.json"
        if not path.exists():
            missing.append(c["slug"])
            continue
        try:
            ev = json.loads(path.read_text())
            computed = compute_total(ev)
        except Exception as exc:  # schema/validation errors surface loudly
            invalid.append(f"{c['slug']}: {exc}")
            continue
        merged = {**ev, **computed}
        # attach funding facts for reports/csv
        for k in ("company", "domain", "website", "usd_equivalent", "raised_raw",
                  "software_category", "lead_investor", "funding_date", "flags",
                  "pre_series_a", "article_url"):
            merged[k] = c.get(k)
        scored.append(merged)

    scored.sort(key=lambda s: s["total"], reverse=True)
    payload = {
        "framework_version": "v1",
        "evaluated_count": len(scored),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "companies": scored,
    }
    SCORED_OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    if scored:
        with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            cols = ["rank", "company", "domain", "archetype", "usd_equivalent",
                    "software_category", "total", "tier", "confidence",
                    "applied_gates"] + [
                f"P{n}" for n in range(1, 10)
            ]
            w.writerow(cols)
            for i, s in enumerate(scored, 1):
                w.writerow(
                    [i, s["company"], s["domain"], s["archetype"],
                     s["usd_equivalent"], s["software_category"], s["total"],
                     s["tier"], s["confidence"], ",".join(s["applied_gates"])]
                    + [s["pillar_scores_0_10"][f"P{n}"] for n in range(1, 10)]
                )
    print(
        f"scored={len(scored)} missing={len(missing)} invalid={len(invalid)}"
    )
    if invalid:
        print("INVALID:")
        for line in invalid[:20]:
            print(" ", line)


if __name__ == "__main__":
    main()
