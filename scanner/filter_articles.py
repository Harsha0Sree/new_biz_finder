"""Step 2: filter article index to >$10M USD-equivalent seed rounds."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from scanner.amounts import ParsedAmount, parse_amount, parse_raise_amount, parse_round, qualifies

INDEX = Path("data/articles_index.json")
OUT = Path("data/qualifying.json")


def main() -> None:
    idx = json.loads(INDEX.read_text())
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
        "threshold_usd": 10_000_000.0,
        "rule": "strictly > $10M USD-equivalent; seed or pre-series-a or unlabeled "
        "(unlabeled re-checked against article Funding Details); pre-seed and named "
        "later series excluded",
        "index_count": len(idx["articles"]),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "drop_reasons": dict(reasons),
        "qualifying": sorted(kept, key=lambda e: e["usd_equivalent"], reverse=True),
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"index={payload['index_count']} kept={len(kept)} dropped={len(dropped)}")
    print("drop reasons:", dict(reasons))
    print("top 15:")
    for e in payload["qualifying"][:15]:
        print(f"  ${e['usd_equivalent']:>13,.0f}  {e['title']}")


if __name__ == "__main__":
    main()
