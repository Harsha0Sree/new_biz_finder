"""Step 2: filter article index to seed-stage rounds at or above $10M USD-equivalent."""

from __future__ import annotations

import time
from collections import Counter

from scanner.amounts import (
    THRESHOLD_USD,
    meets_threshold,
    parse_raise_amount,
    parse_round,
    qualifies,
)
from scanner.paths import ARTICLES_INDEX, QUALIFYING
from scanner.storage import read_json, write_json

INDEX = ARTICLES_INDEX
OUT = QUALIFYING


def main() -> None:
    idx = read_json(INDEX)
    if not idx:
        raise FileNotFoundError(f"{INDEX} not found. Run scanner.crawl_index first.")
    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: Counter = Counter()

    for a in idx["articles"]:
        title = a["title"]
        ok, why = qualifies(title)
        amt, val_amt = parse_raise_amount(title)
        shown_amt = amt or val_amt
        rnd = parse_round(title)
        entry = {
            **a,
            "amount_raw": shown_amt.raw_match if shown_amt else None,
            "currency": shown_amt.currency if shown_amt else None,
            "amount_native": shown_amt.amount_native if shown_amt else None,
            "unit_label": shown_amt.amount_unit_label if shown_amt else None,
            "usd_equivalent": round(shown_amt.usd_equivalent, 2) if shown_amt else None,
            "round_kind": rnd.kind,
            "pre_series_a": rnd.flagged,
            "filter_reason": why,
        }
        if ok:
            kept.append(entry)
        else:
            dropped.append(entry)
            reasons[why.split(" (")[0]] += 1

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "threshold_usd": THRESHOLD_USD,
        "rule": "at least $10M USD-equivalent; seed, pre-seed, pre-series-a, or "
        "unlabeled (unlabeled and valuation-only titles re-checked against the "
        "article Funding Details); named later series excluded",
        "index_count": len(idx["articles"]),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "drop_reasons": dict(reasons),
        "qualifying": sorted(
            kept,
            key=lambda e: e["usd_equivalent"] if e["usd_equivalent"] is not None else 0.0,
            reverse=True,
        ),
    }
    below = [
        e["slug"]
        for e in kept
        if e["filter_reason"] != "check_article_valuation_only"
        and not meets_threshold(e["usd_equivalent"] or 0)
    ]
    if below:
        raise ValueError(f"kept articles below threshold: {below[:5]}")

    write_json(OUT, payload)
    print(f"index={payload['index_count']} kept={len(kept)} dropped={len(dropped)}")
    print("drop reasons:", dict(reasons))
    print("top 15:")
    for e in payload["qualifying"][:15]:
        print(f"  ${e['usd_equivalent']:>13,.0f}  {e['title']}")


if __name__ == "__main__":
    main()
