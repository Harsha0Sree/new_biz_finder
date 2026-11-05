# Resume runbook

Operational notes for picking the project back up. Artifact counts below are a
snapshot. `uv run python -m scanner.validate` prints the authoritative current
numbers.

## Current state

- `data/articles_index.json`: 4,583 articles from the `/tag/seed-round/` and
  `/tag/pre-seed/` archives (351 seed-round pages).
- `data/qualifying.json`: 571 title-level candidates at or above $10M
  USD-equivalent (seed, pre-seed, pre-Series-A, or deferred valuation-only).
- `data/companies.json`: 556 rows, 550 unique companies after Funding Details
  verification and dedupe.
- `data/rejected.json`: 15 candidates rejected after article verification
  (below threshold, unknown or non-seed round).
- `data/sites.json`: 548 site records (488 `ok`, 28 `js_only`, 32 `dead`).
- `data/evals/<slug>.json`: 67 completed deep evaluations.
- `data/scored.json`: 67 evaluated, 483 unique companies still missing,
  0 invalid.
- `data/llm_evals/<slug>.json`: 52 LLM quick-pass records (1 verified,
  4 unverified, 47 errored; only verified records are ranked).
- `data/llm_scored.json`: 1 verified LLM evaluation, ranked.
- `data/llm_eval_summary.json`: counts, models, invalid file list,
  verified-latency/token stats.
- `reports/`: 67 per-company reports, `master-ranking.md`, `index.md`, and
  `llm_opportunity_ranking.md`.

## Routine commands

```bash
uv run python -m scanner.validate          # artifact gate; non-zero on errors
uv run pytest -q                           # 88 tests
uv run ruff check .                        # lint
make check                                 # lint + tests + validation
```

After changing evaluations or rankings:

```bash
uv run python -m scanner.compute           # rebuild scored.json + scores.csv
uv run python -m scanner.reports           # rebuild reports/
uv run python main.py --aggregate-only     # rebuild LLM aggregate/report
```

After changing crawl/filter/company data, re-run the affected downstream steps
in order (`main.py --step ...` or the individual modules). Do not run
`scanner.compute` against a stale `companies.json`.

## Continuing the deep evaluation pass

Deep evaluations are manual/LLM-assisted records in `data/evals/`. A company is
considered evaluated when `data/evals/<slug>.json` exists and passes
`scanner.compute` validation.

1. Pick the next company from `data/companies.json` that has no eval file
   (prefer descending `usd_equivalent`; `data/eval_order.txt` is a historical
   ordering artifact, not authoritative).
2. Read evidence:
   - `data/cache/text/article__<slug>.txt` (always)
   - `data/cache/text/site__<domain>__*.txt` (when available/useful)
3. Write the evaluation per [`SCORING_SPEC.md`](SCORING_SPEC.md):
   52 categories × h1–h4 integer scores with evidence, archetype, gates G1–G5,
   agency play, confidence.
4. Validate and rebuild:
   ```bash
   uv run python scripts/validate_evals.py
   uv run python -m scanner.compute
   uv run python -m scanner.reports
   uv run python -m scanner.validate
   ```

## Continuing the LLM quick pass

Errored records are retried automatically:

```bash
uv run python main.py --limit 10 --llm-workers 2
```

Useful flags:

- `--no-retry-errors`: skip files that previously errored.
- `--force`: re-evaluate successes too.
- `--no-resume`: do not skip existing files.
- `--aggregate-only`: rebuild rankings without API calls.
- `--include-errors`: write `llm_scored_with_errors.json` (diagnostics
  only); the ranked artifacts are left untouched.

The current 47 errors are mostly HTTP 404 (invalid/unavailable model endpoint)
and timeouts. The pipeline now preflights the endpoint (`/v1/models` plus a
one-token chat probe) and stops before burning a batch when the endpoint
cannot answer. Measured on the free NVIDIA endpoint: `openai/gpt-oss-20b`
passes preflight (model listed, key accepted) but every chat completion call
timed out (45s probe and 600s x 3 batch attempts), so no live evaluation
completes there right now. Check whether your key reaches a chat completion
before retrying a large batch:

```bash
uv run python -m scanner.llm_analyzer --provider nvidia --model <available-model> --limit 1
```

Only records with a parsed score JSON block rank. The 4 pre-fix "successful"
records (fallback-derived scores 45/47/15/0) are listed as unverified and are
re-evaluated on the next run; they were never honestly scored.

## Documented decisions and deviations

- Qualification threshold is **inclusive**: `>= $10M` USD-equivalent.
- **Pre-seed is included**; named later series (`Series A`, `Series B`, and
  later named series) are excluded.
- Valuation-only headlines are deferred to article-level Funding Details rather
  than treated as raise amounts.
- `is_raised_in_year` prefers a real `funding_date`/`date` over title, URL, or
  slug years. A 2025 round republished in 2026 is not counted as 2026.
- P9 is a 5% bonus pillar, so raw pillar weights sum to **1.05**; totals are
  normalized by the computation. Do not assert they sum to 1.0.
- Two evaluators coexist: the 52-category deep pass (`data/evals`) and the LLM
  quick pass (`data/llm_evals`). Their scores are not merged.
- Errored LLM evaluations remain on disk as diagnostics, are excluded from
  rankings, and are retried by default.
- Amount-source discrepancies and title-round fallbacks are recorded in each
  company's `flags` field.
- All artifact writes are atomic and all paths are anchored to the repository
  root, so runs are safe from any working directory.
