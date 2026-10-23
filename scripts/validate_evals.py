"""Validate evaluator JSON files against the scoring spec schema."""

from __future__ import annotations

from pathlib import Path

from scanner.paths import EVALS
from scanner.storage import read_json

EVALS_DIR = EVALS
ARCHETYPES = {
    "ai_infra_devtools", "vertical_ai_saas", "fintech_regtech",
    "healthtech_bio", "sales_marketing_cx", "other",
}
GATES = {"G1", "G2", "G3", "G4", "G5"}


def validate(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        ev = read_json(path)
    except (ValueError, OSError) as exc:
        return [f"{path.name}: unreadable JSON: {exc}"]
    if not isinstance(ev, dict):
        return [f"{path.name}: expected an object"]
    for key in ("slug", "company", "archetype", "confidence", "gates",
                "categories", "agency_play"):
        if key not in ev:
            errs.append(f"missing key {key}")
    if ev.get("archetype") not in ARCHETYPES:
        errs.append(f"bad archetype {ev.get('archetype')!r}")
    if ev.get("confidence") not in ("high", "medium", "low"):
        errs.append(f"bad confidence {ev.get('confidence')!r}")
    gates = {g.get("gate") for g in ev.get("gates", [])}
    if gates != GATES:
        errs.append(f"gates must cover exactly G1..G5, got {sorted(gates)}")
    cats = ev.get("categories", {})
    want_keys = {str(i) for i in range(1, 53)}
    missing = want_keys - set(cats)
    extra = set(cats) - want_keys
    if missing:
        errs.append(f"missing categories: {sorted(missing, key=int)[:10]}")
    if extra:
        errs.append(f"extra categories: {sorted(extra)[:10]}")
    for k in sorted(set(cats) & want_keys, key=int):
        c = cats[k]
        for h in ("h1", "h2", "h3", "h4"):
            v = c.get(h)
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 10:
                errs.append(f"cat {k}: bad head score {v!r}")
        ev_text = c.get("evidence", "")
        if not isinstance(ev_text, str) or len(ev_text) < 5:
            errs.append(f"cat {k}: weak/missing evidence")
    ap = ev.get("agency_play", {})
    for key in ("build_scope", "packaging", "pricing", "first_clients"):
        if not isinstance(ap.get(key), str) or len(ap[key]) < 10:
            errs.append(f"agency_play.{key} too short/missing")
    return errs


def main() -> int:
    files = sorted(EVALS_DIR.glob("*.json")) if EVALS_DIR.exists() else []
    bad = 0
    for p in files:
        errs = validate(p)
        if errs:
            bad += 1
            print(f"FAIL {p.name}")
            for e in errs:
                print("   ", e)
    print(f"{len(files)} eval files checked, {bad} invalid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
