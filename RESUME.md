# Resume Runbook — Seed-Round Agency-Opportunity Scanner

State (this session): pipeline complete end-to-end; **67 of 423 companies
fully evaluated** (all raise sizes >$34M done; ordered descending by raise).
Everything is cached and resumable. Subagent (`task`) tooling was unstable
earlier in the project; inline evaluation is proven and produces 0-invalid files.

## Current state

- `data/articles_index.json` — 4,203 articles from 351 tag pages (complete)
- `data/qualifying.json` — 437 qualifying articles >$10M USD-equiv (complete)
- `data/companies.json` — 423 unique companies after Funding-Details verification + dedupe (complete)
- `data/sites.json` — website fetch status for all 421 domains: 367 ok / 29 js_only / 26 dead*
- `data/evals/<slug>.json` — completed evaluations (**resume marker: file existence**)
- `data/scored.json`, `data/scores.csv`, `reports/*.md` — regenerated after every batch

*dead = mostly bot-blocks (403), SSL/DNS quirks, rate-limits — NOT parked domains.
Per SCORING_SPEC.md, G5 applies only to truly dead/parked/no-website cases;
js_only and bot-blocked sites are evaluated from article text with confidence=low.

## How to continue the evaluation pass

Companies are processed in `data/eval_order.txt` order (descending raise size).
For each company without `data/evals/<slug>.json`:

1. Read its evidence files:
   - `data/cache/text/article__<slug>.txt` (always)
   - `data/cache/text/site__<domain>__*.txt` (when useful; skip if thin article suffices)
2. Write `data/evals/<slug>.json` per the schema in `SCORING_SPEC.md`
   (52 categories x h1-h4 integer scores + evidence, archetype, gates G1-G5,
   agency_play, confidence).
3. Periodically:
   ```
   uv run python scripts/validate_evals.py   # must report 0 invalid
   uv run python -m scanner.compute          # rebuilds scored.json + scores.csv
   uv run python -m scanner.reports          # rebuilds reports/
   ```

## Validation (rerunnable)

```
uv run pytest tests/ -q               # parser unit tests incl. ground truth
uv run python scripts/validate_totals.py   # independent recompute vs scored.json
```

## Known documented deviations

- Plan validation list marked "Arc Raises $10.76M Seed" as excluded; this
  contradicts the plan's formal rule "strictly >$10M USD-equivalent".
  The formal rule wins -> Arc included (see tests/test_amounts.py).
- Within-pillar category weights set to equal (plan gave no numbers); pillar P9
  (bonus cats 51-52) added at 5% with renormalization - all in scanner/compute.py.
- Amount-source discrepancies (7 companies) and round-from-title fallbacks (2)
  are flagged in each company's `flags` field.
