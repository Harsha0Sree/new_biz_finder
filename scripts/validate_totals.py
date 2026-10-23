"""Independent total re-computation (validation plan check 3).

Deliberately re-implements the formula from the spec text rather than
importing scanner.compute, then diffs against data/scored.json.
"""

from __future__ import annotations

from scanner.paths import EVALS, SCORED
from scanner.storage import read_json

HEADS = [("h1", 0.30), ("h2", 0.35), ("h3", 0.25), ("h4", 0.10)]
PILLAR_WEIGHT = {"P1": 0.20, "P2": 0.15, "P3": 0.18, "P4": 0.12,
                 "P5": 0.10, "P6": 0.10, "P7": 0.08, "P8": 0.07, "P9": 0.05}
PILLAR_CATS = {
    "P1": range(1, 8), "P2": range(8, 15), "P3": range(15, 22),
    "P4": range(22, 28), "P5": range(28, 34), "P6": range(34, 40),
    "P7": range(40, 45), "P8": range(45, 51), "P9": [51, 52],
}
MULT = {
    "ai_infra_devtools": {"P1": 1.3, "P5": 1.3, "P3": 0.9},
    "fintech_regtech": {"P6": 1.4, "P5": 1.2, "P2": 0.9},
    "healthtech_bio": {"P6": 1.5, "P7": 0.9},
    "sales_marketing_cx": {"P2": 1.2, "P3": 1.1},
    "vertical_ai_saas": {}, "other": {},
}
GATES = {"G1": 0.05, "G2": 0.15, "G3": 0.10, "G4": 0.25, "G5": 0.20}


def independent_total(ev: dict) -> float:
    pscore = {}
    for pid, cats in PILLAR_CATS.items():
        tot = 0.0
        for cnum in cats:
            c = ev["categories"][str(cnum)]
            combined = sum(w * c[h] for h, w in HEADS)
            tot += combined / 10.0
        pscore[pid] = tot / len(list(cats))
    raw = {p: PILLAR_WEIGHT[p] * MULT[ev["archetype"]].get(p, 1.0) for p in PILLAR_WEIGHT}
    z = sum(raw.values())
    base = sum((raw[p] / z) * pscore[p] for p in PILLAR_WEIGHT)
    mask = 1.0
    for g in ev["gates"]:
        if g["applied"]:
            mask *= GATES[g["gate"]]
    return round(mask * base * 100, 2)


def main() -> int:
    scored = read_json(SCORED)["companies"]
    bad = 0
    for s in scored:
        ev = read_json(EVALS / f"{s['slug']}.json")
        t = independent_total(ev)
        if abs(t - s["total"]) > 0.01:
            bad += 1
            print(f"MISMATCH {s['slug']}: independent={t} reported={s['total']}")
    print(f"CHECK 3 - independent recompute: {len(scored)} totals checked, {bad} mismatches")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
