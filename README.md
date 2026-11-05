# Seed-Round Agency Opportunity Scanner

A resumable Python pipeline that discovers recently funded seed-stage SaaS/AI
startups, verifies their funding details, scrapes company websites and pricing,
and evaluates each business as a potential productized agency opportunity.

The repository produces **two independent evaluation passes**:

| Pass | Input | What it is | Current records |
|---|---|---|---|
| **Deep evaluation** | `data/evals/*.json` | 52-category deterministic framework (Builder/Seller/Buyer/Risk), hard gates G1–G5, six archetypes | 67 completed |
| **LLM quick pass** | `data/llm_evals/*.json` | Fast single-score second opinion from an LLM with isolated, bounded evidence | 52 files: 1 verified, 4 unverified, 47 errored |

Only records with a parsed score JSON block rank. A record without one is
listed as **unverified** and re-evaluated on the next run; it never counts
as a score. Errored LLM evaluations stay on disk for diagnostics, are
omitted from rankings, and are retried by default on the next run.

---

## Quick start

```bash
uv sync
uv run python main.py                 # crawl -> filter -> articles -> sites -> prompts -> LLM
uv run python main.py --aggregate-only  # rebuild LLM rankings without API calls
uv run python -m scanner.validate      # check every committed artifact
```

Common variations:

```bash
uv run python main.py --skip-crawl --skip-scrape   # reuse cached data
uv run python main.py --limit 5                    # evaluate only five companies
uv run python main.py --step fetch-sites           # run one pipeline step
uv run python main.py --step validate              # validation-only, non-zero on failure
uv run python main.py --llm-workers 4              # concurrent LLM calls
```

Individual modules can still be run directly:

```bash
uv run python -m scanner.crawl_index
uv run python -m scanner.filter_articles
uv run python -m scanner.fetch_articles
uv run python -m scanner.fetch_sites
uv run python -m scanner.export_prompts
uv run python -m scanner.llm_analyzer --aggregate-only
uv run python -m scanner.compute
uv run python -m scanner.reports
uv run python -m scanner.validate
```

---

## Current data snapshot

As of the latest committed artifacts:

- **Index**: 4,583 article cards from the `/tag/seed-round/` and
  `/tag/pre-seed/` archives (351 seed-round pages).
- **Qualifying**: 887 articles (571 with an amount at or above **$10M
  USD-equivalent**, plus 316 seed-stage titles with no amount in the title
  that are deferred to article verification).
- **Dropped**: 3,696 articles (3,694 below threshold, 2 named later series).
- **Companies**: 556 rows, 550 unique after name/domain dedupe.
- **Sites**: 548 records (488 `ok`, 28 `js_only`, 32 `dead`).
- **Rejected after article verification**: 15 (below threshold, unknown round, etc.).
- **Deep evaluations**: 67, with `data/scored.json` and per-company reports.
- **LLM evaluations**: 52 files; 1 verified, 4 unverified, 47 errored/retryable.
- **2026 selection**: 210 unique companies by real funding date.
- **Note on past LLM runs**: evaluations written before the scoring fix used a
  heuristic fallback that recorded a fabricated `50/100` on unparseable output.
  Those records are now excluded from the ranking as unverified and will be
  re-evaluated on the next run.

Numbers move as the archive grows; the validator and report headers always show
the current counts.

### Qualification rule

A round qualifies when:

1. The headline round is **seed, pre-seed, pre-Series-A, or unlabeled**.
   Pre-seed is included. Named later series (`Series A`, `Series B`, and later
   named series) are excluded.
2. The **raise amount** is **at least $10M USD-equivalent** (inclusive).
3. Valuation-only titles are not accepted on the valuation number, and
   seed-stage titles with no amount are not dropped on that absence alone.
   Both are passed to `fetch_articles`, which reads the Funding Details
   block and keeps the company only if the actual raise clears the
   threshold. Every indexed title lands in exactly one of
   `data/qualifying.json` or `data/dropped.json`, and the validator
   checks the partition.

Fixed FX planning constants live in `scanner/amounts.py`. Amount parsing handles
`$`, `€`, `£`, `¥`, `₹`, `Rs`, `A$`, `S$`, and `US$`, with thousand/million/
billion/trillion and crore/lakh units.

---

## How it works

```
thesaasnews.com /tag/seed-round/ + /tag/pre-seed/
        │
        │ 1. scanner.crawl_index
        ▼
data/articles_index.json
        │
        │ 2. scanner.filter_articles + scanner.amounts
        ▼
data/qualifying.json
        │
        │ 3. scanner.fetch_articles
        ▼
data/companies.json  +  data/cache/text/article__<slug>.txt
        │
        │ 4. scanner.fetch_sites
        ▼
data/sites.json      +  data/cache/text/site__<domain>__*.txt
        │
        │ 5. scanner.export_prompts
        ▼
data/company_prompts/
        │
        │ 6. scanner.llm_analyzer
        ▼
data/llm_evals/<slug>.json -> data/llm_scored.json + reports/
```

Separately, the deterministic pass reads `data/evals/*.json`, computes totals,
and writes `data/scored.json`, `data/scores.csv`, and `reports/*.md`.

### Reliability behavior

- All artifact paths are anchored to the repository root (`scanner/paths.py`),
  so commands work from any directory.
- JSON, CSV, and text writes are atomic (`scanner/storage.py`), preventing a
  truncated artifact if a long run is interrupted.
- HTTP responses are cached on disk. 2xx, 3xx, and 4xx responses other
  than 403/404/408/410/425/429 are cached; transient failures and negative
  results are retried and **not** cached, so a later run can recover and a
  growing archive is never blocked by a stale 404.
- Requests are throttled per host. Site and LLM work can run concurrently
  (`--site-workers`, `--llm-workers`), with independent hosts progressing in
  parallel.
- LLM evaluation resumes by slug. Existing verified records are skipped;
  errored or unverified files are retried unless `--no-retry-errors` is set.
- Scraped article/site text is wrapped in `<untrusted_web_content>` and the
  prompt explicitly tells the model to ignore instructions embedded in it.

---

## Project structure

```
.
├── data/
│   ├── articles_index.json      # Article metadata from the index crawl
│   ├── qualifying.json          # Title-level candidates (>= $10M, seed stage)
│   ├── articles_parsed.json     # Per-article Funding Details (resumable)
│   ├── companies.json           # Deduplicated company registry
│   ├── rejected.json            # Candidates rejected after article verification
│   ├── sites.json               # Website status + extracted pricing
│   ├── evals/                   # Deep 52-category evaluation records
│   ├── llm_evals/               # LLM quick-pass records (including errors)
│   ├── llm_scored.json          # Successful LLM evaluations, ranked
│   ├── llm_scores.csv           # Spreadsheet export
│   ├── llm_eval_summary.json    # Counts + invalid/errored file list
│   └── cache/                   # HTTP page cache + extracted text (gitignored)
├── prompts/system_prompt.txt    # Production LLM evaluation prompt
├── reports/
│   ├── index.md                 # Entry point for both ranking passes
│   ├── master-ranking.md        # Deep-evaluation ranking
│   ├── llm_opportunity_ranking.md
│   └── <company-slug>.md        # Per-company deep reports
├── scanner/
│   ├── amounts.py               # Currency parsing, FX, threshold, round labels
│   ├── compute.py               # 52-category deterministic scoring
│   ├── crawl_index.py           # Index crawler and pagination discovery
│   ├── enrich.py                # Company <-> site join (pricing/status)
│   ├── env.py                   # .env loader
│   ├── export_prompts.py        # Isolated prompt dossiers
│   ├── fetch_articles.py        # Funding Details parser + company registry
│   ├── fetch_sites.py           # Site/subpage scraper, pricing extraction
│   ├── filter_articles.py       # Title-level qualification filter
│   ├── httpcache.py             # Cached, throttled, retrying HTTP client
│   ├── llm.py                   # NVIDIA NIM / Ollama client + JSON extraction
│   ├── llm_analyzer.py          # LLM evaluation loop + aggregation
│   ├── models.py                # TypedDict schemas for artifacts/records
│   ├── paths.py                 # Canonical project paths
│   ├── reports.py               # Deep-pass report renderer
│   ├── storage.py               # Atomic JSON/text/bytes writers
│   └── validate.py              # End-to-end artifact validator
├── scripts/                     # One-off probes and independent checks
├── tests/                       # Pytest suite
├── main.py                      # Unified pipeline entry point
├── Makefile                     # test / lint / validate / check targets
└── pyproject.toml
```

---

## Installation

Requirements: Python `>= 3.12` and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Harsha0Sree/new_biz_finder.git
cd new_biz_finder
uv sync
```

With plain `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify:

```bash
uv run pytest -q
uv run ruff check .
uv run python -m scanner.validate
```

---

## Environment configuration

Copy `.env.example` to `.env` and fill in your provider settings. `main.py`,
`scanner.llm_analyzer`, and `scanner.env` load it automatically.

```bash
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=openai/gpt-oss-20b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

EVAL_YEAR=2026
# EVAL_LIMIT=5
```

### NVIDIA NIM

1. Create a key at <https://build.nvidia.com/>.
2. Set `NVIDIA_API_KEY` and choose a model available to your account.
3. Run:

```bash
uv run python -m scanner.llm_analyzer --provider nvidia --model openai/gpt-oss-20b
```

The pipeline runs a **preflight** before any evaluation: it queries
`/v1/models`, confirms the configured model is listed, and then sends a
one-token chat probe to confirm completions actually return. It stops
before burning a batch when either check fails; pass `--skip-preflight` to
run anyway. A `404` from `/models` is a hard failure and means the base
URL or provider is wrong, not merely that the model ID is unavailable.

Measured on a free-tier key: `openai/gpt-oss-20b` passes both preflights,
but every chat completion timed out (a trivial 16-token probe at 45s and
a full evaluation at 600s × 3 attempts), so no live evaluation completes
on that endpoint right now. `z-ai/glm-5.3-flash` returned HTTP 404 for
every call and is not servable there; do not point the pipeline at it.
The preflight exists to make those failures cheap instead of a wasted
batch.

### Ollama

```bash
ollama serve
ollama pull llama3.1:8b
uv run python -m scanner.llm_analyzer \
  --provider ollama \
  --model llama3.1:8b \
  --base-url http://localhost:11434/v1
```

For a remote Ollama host, set `OLLAMA_HOST=0.0.0.0` on the server and point
`--base-url` at `http://<host>:11434/v1`.

---

## Pipeline steps

### 1. Crawl the article index

```bash
uv run python -m scanner.crawl_index
uv run python -m scanner.crawl_index --refetch   # force fresh pages
```

Crawls `/tag/seed-round/` and `/tag/pre-seed/`, discovers the last page, and
writes `data/articles_index.json`. Incremental mode always re-downloads the
head pages (the ones carrying new posts) and stops after two consecutive
pages yield no unseen slugs; articles backfilled deep in the past only
surface with `--refetch`. In `main.py`, use `--refetch-index`.

### 2. Filter qualifying rounds

```bash
uv run python -m scanner.filter_articles
```

Writes `data/qualifying.json` with the parsed amount, USD equivalent, round
label, qualification reason, and drop-reason counts.

### 3. Fetch articles and build the company registry

```bash
uv run python -m scanner.fetch_articles
```

Parses the structured Funding Details block, verifies the raise amount and round
against the article, stores clean article text, and writes `companies.json` plus
`rejected.json`. Runs are resumable via `articles_parsed.json`; use
`--reparse` to re-fetch.

### 4. Scrape company websites

```bash
uv run python -m scanner.fetch_sites --workers 4
uv run python -m scanner.fetch_sites --refetch
```

Fetches homepages and linked pricing/product/about/customer pages, recovers
Next.js/JSON-LD data, extracts pricing signals, and merges results into
`sites.json`. `--workers` controls concurrency (1–16).

### 5. Export isolated prompts

```bash
uv run python -m scanner.export_prompts
```

Writes one self-contained prompt dossier per company to
`data/company_prompts/`.

### 6. Run LLM evaluation and aggregate

```bash
uv run python -m scanner.llm_analyzer --provider nvidia --year 2026
uv run python main.py --aggregate-only
```

Each company gets a fresh context with bounded article/source/site evidence,
joined pricing data, and an explicit JSON output schema. Evaluation records are
saved per slug. Errored records are retried by default. Aggregation writes
`data/llm_scored.json`, `data/llm_scores.csv`, `data/llm_eval_summary.json`, and
`reports/llm_opportunity_ranking.md`.

### Deterministic deep pass

```bash
uv run python -m scanner.compute
uv run python -m scanner.reports
```

`compute` validates every deep evaluation, recomputes totals independently of
the evaluation file, and writes `data/scored.json` + `data/scores.csv`.
`reports` writes per-company reports, `reports/master-ranking.md`, and
`reports/index.md`.

---

## CLI reference

### `main.py`

| Flag | Default | Description |
|---|---|---|
| `--step` | `all` | `all`, `crawl`, `filter`, `fetch-articles`, `fetch-sites`, `export-prompts`, `llm`, `validate` |
| `--skip-crawl` | off | Reuse the existing index |
| `--skip-scrape` | off | Reuse `sites.json` and skip missing-site scraping |
| `--refetch-index` | off | Force a full index re-crawl |
| `--provider` | env / `nvidia` | `nvidia` or `ollama` |
| `--model` | provider default | Model override |
| `--api-key` | env | NVIDIA NIM key |
| `--base-url` | provider default | Custom endpoint |
| `--prompt-file` | `prompts/system_prompt.txt` | System prompt path |
| `--year` | env / `2026` | Funding year filter |
| `--limit` | env / none | Max companies to evaluate |
| `--site-workers` | `4` | Concurrent site fetchers (1–16) |
| `--llm-workers` | `1` | Concurrent LLM evaluations (1–16) |
| `--force` | off | Re-evaluate existing companies |
| `--no-resume` | off | Do not skip existing eval files |
| `--no-retry-errors` | off | Skip previously errored LLM evaluations |
| `--aggregate-only` | off | Rebuild rankings without LLM calls |
| `--include-errors` | off | Write `llm_scored_with_errors.json` (diagnostics only); ranked artifacts untouched |
| `--max-tokens` | `6000` | Token cap for the LLM completion |
| `--temperature` | `0.2` | Sampling temperature |
| `--timeout` | `120.0` | HTTP timeout in seconds per attempt |
| `--skip-preflight` | off | Skip the endpoint preflight (/v1/models + one-token chat probe) |
| `--dry-run` | off | Print the planned run and exit without writing artifacts |

### `scanner.llm_analyzer`

Same core LLM flags as above (`--provider`, `--model`, `--api-key`,
`--base-url`, `--prompt-file`, `--year`, `--limit`, `--force`, `--no-resume`,
`--workers`, `--no-retry-errors`, `--aggregate-only`, `--include-errors`,
`--max-tokens`, `--temperature`, `--timeout`, `--skip-preflight`,
`--no-prefetch-sources`).

The LLM pipeline prefetches the press-release cache before evaluation so
workers only read from disk; pass `--no-prefetch-sources` to skip that.

### `scanner.fetch_sites`

`--workers N`, `--refetch`, `--limit N`.

---

## Evaluation framework (deep pass)

The deterministic pass scores 52 categories across four heads:

- **H1 Builder (30%)**: can a solo operator reproduce the core value?
- **H2 Seller (35%)**: is there a reachable, high-ticket buyer?
- **H3 Buyer (25%)**: economic pain, budget, and measurable outcome.
- **H4 Risk, inverse (10%)**: compliance, security, platform, and support risk.

Categories marked `(inv)` reward lower burden. Six archetypes apply pillar-level
multipliers. Hard gates G1–G5 can cap or scale the total; G5 (dead/parked/no
website) multiplies by 0.20. Tiers: **A ≥ 80, B ≥ 65, C ≥ 50, D < 50**.

See [`SCORING_SPEC.md`](SCORING_SPEC.md) for the full schema. The pillar weights
sum to 1.05 because P9 is a 5% bonus pillar added before renormalization; totals
are normalized when computed.

The LLM quick pass is a separate, faster signal. It is **not** a replacement for
the deep evaluation and its scores are not merged into `scored.json`.

---

## Data, cache, and validation

### Cache semantics

- `data/cache/pages/<hash>.meta.json` + `.body`: raw HTTP cache.
- `data/cache/text/article__<slug>.txt`: cleaned funding articles.
- `data/cache/text/site__<domain>__*.txt`: cleaned site pages.
- Delete a specific cache entry (or pass `--refetch`) to force a re-fetch.
- Transient HTTP failures and 403/404/410 are never cached; entries written
  before that rule shipped are treated as misses.

### Validation gate

```bash
uv run python -m scanner.validate
```

Checks article counts/slugs (including an allowlist on every slug),
qualifying amounts and deferred valuation cases, company uniqueness and
round provenance, site statuses/pricing shapes plus presence of a record
per domain, deep eval schema and gate coverage (the scored artifacts are
recomputed from the eval files and compared), LLM eval records against
the ranked file field-by-field, the LLM summary against disk, report
links, and fetch-error volume. Exit code is non-zero on errors.

### Tests and lint

```bash
uv run pytest -q                 # 88 tests
uv run ruff check .
make check                       # lint + tests + artifact validation
```

The suite covers amount parsing (billion/trillion/crore/lakh), inclusive
threshold behavior, Funding Details variants, retry/cache semantics, atomic
storage, site-pricing enrichment, prompt-injection isolation, date precedence,
errored-eval retry/aggregation, report links, validator corruption cases, and
the 404-must-not-be-cached rule that keeps the archive probe honest.

---

## Known limitations

- Amounts and dates rely on publisher-reported figures; FX is a fixed planning
  table, not live market data.
- Some sites are JS-only or bot-blocked; those companies are scored from article
  evidence with lower confidence.
- The LLM quick pass requires a working provider/model. The committed 47 errored
  records and 4 unverified records are retryable diagnostics, not scores; only
  records with a parsed score JSON block are ranked.
- Deep evaluations are expensive; the pass is resumable by file existence and
  `scanner.compute` validates every record before ranking.
- **Incremental index crawl** re-downloads the head pages each run and
  stops after two pages with no unseen slugs; articles backfilled deep in
  the archive require `uv run python -m scanner.crawl_index --refetch`.
