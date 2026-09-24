# Seed-Round Agency Opportunity Scanner & LLM Analyzer

A high-throughput intelligence pipeline that discovers recently funded seed-stage SaaS and AI startups, ingests verified funding details, scrapes and parses company websites (with bot-block mitigation, Next.js SPA data extraction, and pricing tier detection), and evaluates each business using an LLM-driven agency opportunity scoring framework.

---

## Table of Contents

- [Quick Start: Single-Command Pipeline](#quick-start-single-command-pipeline)
- [Environment Configuration (.env)](#environment-configuration-env)
- [Overview & Architecture](#overview--architecture)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [LLM Provider Configuration](#llm-provider-configuration)
  - [Option A: NVIDIA NIM (Cloud / Hosted)](#option-a-nvidia-nim-cloud--hosted)
  - [Option B: Ollama (Local / Self-Hosted GPU)](#option-b-ollama-local--self-hosted-gpu)
- [End-to-End Automation Walkthrough](#end-to-end-automation-walkthrough)
  - [Step 1: Crawl Article Index](#step-1-crawl-article-index)
  - [Step 2: Filter Qualifying Rounds](#step-2-filter-qualifying-rounds)
  - [Step 3: Fetch Article Bodies & Build Company Registry](#step-3-fetch-article-bodies--build-company-registry)
  - [Step 4: Scrape Company Websites & Extract Pricing](#step-4-scrape-company-websites--extract-pricing)
  - [Step 5: Run the LLM Evaluation Loop](#step-5-run-the-llm-evaluation-loop)
  - [Step 6: Aggregate Scores & Generate Rankings](#step-6-aggregate-scores--generate-rankings)
- [CLI Reference](#cli-reference)
- [Understanding the Evaluation Framework](#understanding-the-evaluation-framework)
- [Data Storage & Cache Management](#data-storage--cache-management)
- [Testing & Quality Assurance](#testing--quality-assurance)

---

## Quick Start: Single-Command Pipeline

Instead of manually running 5 separate scripts in sequence, you can execute the entire end-to-end pipeline with **a single command**:

```bash
uv run python main.py
```

This single command automatically:
1. Crawls the SaaS news archive index (skips if cached).
2. Filters seed rounds strictly $> \$10\text{M}$ USD-equivalent.
3. Fetches article HTML and extracts verified Funding Details into `companies.json`.
4. Scrapes company homepages and subpages, extracts pricing tiers, and recovers SPA state into `sites.json`.
5. Runs the LLM opportunity evaluation for qualifying 2026 companies, saving individual evaluation JSONs, aggregating [`data/llm_scores.csv`](file:///home/mikeysama/products/new_biz_finder/data/llm_scores.csv), and writing the ranking report [`reports/llm_opportunity_ranking.md`](file:///home/mikeysama/products/new_biz_finder/reports/llm_opportunity_ranking.md).

### Useful Command Variations

```bash
# Run using already cached scraped data directly to LLM evaluation:
uv run python main.py --skip-crawl --skip-scrape

# Run a quick test on the top 5 companies:
uv run python main.py --limit 5

# Re-generate CSV and ranking reports from existing evals without calling the LLM:
uv run python main.py --aggregate-only

# Run an individual step if needed:
uv run python main.py --step fetch-sites
```

*(Note: All individual modular scripts in `scanner/` remain available to run standalone as well.)*

---

## Environment Configuration (`.env`)

The project includes an auto-loaded [`.env`](file:///home/mikeysama/products/new_biz_finder/.env) file (which is ignored by Git to protect your API keys). A template is provided in [`.env.example`](file:///home/mikeysama/products/new_biz_finder/.env.example).

Open `.env` and set your preferred LLM provider, API key, and model:

All values in `.env` are automatically loaded on startup by `main.py` and `scanner.llm_analyzer`.

---

## Overview & Architecture

The objective of this pipeline is to analyze seed-stage startups through the lens of an **agency opportunity**:
> *Can a solo technical operator package the core value proposition of this startup as a high-ticket B2B service ($1k–$15k+) using modern AI/automation stacks in 1–2 days, delivering measurable client ROI without proprietary IP or enterprise credentials?*

### Pipeline Workflow

```
 ┌──────────────────────┐
 │  thesaasnews.com     │ (350+ archive pages)
 └──────────┬───────────┘
            │ 1. crawl_index.py
            ▼
 ┌──────────────────────┐
 │ articles_index.json  │ (4,200+ raw article cards)
 └──────────┬───────────┘
            │ 2. filter_articles.py & amounts.py
            ▼
 ┌──────────────────────┐
 │   qualifying.json    │ (Strictly > $10M USD-equiv, seed/pre-series-A)
 └──────────┬───────────┘
            │ 3. fetch_articles.py
            ▼
 ┌──────────────────────┐   ┌───────────────────────────┐
 │   companies.json     │ + │ cache/text/article__*.txt │
 └──────────┬───────────┘   └───────────────────────────┘
            │ 4. fetch_sites.py (Browser headers, SPA recovery, pricing extraction)
            ▼
 ┌──────────────────────┐   ┌───────────────────────────┐
 │     sites.json       │ + │ cache/text/site__*__*.txt │
 └──────────┬───────────┘   └─────────────┬─────────────┘
            │                             │
            └──────────────┬──────────────┘
                           │ 5. llm_analyzer.py (assemble context + system prompt)
                           ▼
            ┌─────────────────────────────┐
            │  LLM (NVIDIA NIM / Ollama)  │
            └──────────────┬──────────────┘
                           │ 6. save_evaluation & aggregate_scores
                           ▼
 ┌──────────────────────┐   ┌───────────────────────┐   ┌─────────────────────────┐
 │   llm_evals/*.json   │   │     llm_scores.csv    │   │  reports/ranking.md     │
 └──────────────────────┘   └───────────────────────┘   └─────────────────────────┘
```

---

## Project Structure

```
.
├── data/
│   ├── articles_index.json      # Discovered article metadata from the index crawl
│   ├── qualifying.json          # Filtered articles meeting the >$10M seed threshold
│   ├── companies.json           # Canonical deduplicated company registry with funding facts
│   ├── sites.json               # Website status (ok/js_only/dead) & extracted pricing info
│   ├── cache/
│   │   ├── pages/               # Raw HTTP response cache (.meta.json + .body)
│   │   └── text/                # Clean extracted text for articles and website subpages
│   ├── evals/                   # Legacy 52-category deterministic evaluation records
│   ├── llm_evals/               # Individual JSON evaluation dossiers produced by LLMs
│   ├── llm_scored.json          # Master aggregated JSON of all LLM evaluations
│   └── llm_scores.csv           # Tabular export for spreadsheets and CRM imports
├── prompts/
│   └── system_prompt.txt        # The production market evaluation prompt (Iman persona)
├── reports/
│   └── llm_opportunity_ranking.md # Formatted Markdown ranking report
├── scanner/
│   ├── amounts.py               # Currency parsing, fixed FX normalization, valuation detector
│   ├── compute.py               # Deterministic mathematical rollup engine (52 categories)
│   ├── crawl_index.py           # Spider for index pages (binary searches last page)
│   ├── fetch_articles.py        # Ingests article bodies and extracts Funding Details
│   ├── fetch_sites.py           # Scrapes homepages/subpages, extracts pricing and SPA data
│   ├── filter_articles.py       # Title-level qualification filter
│   ├── httpcache.py             # Disk-cached polite HTTP client with browser headers
│   ├── llm.py                   # Unified client abstraction for NVIDIA NIM and Ollama
│   ├── llm_analyzer.py          # Orchestration runner for LLM evaluation loop
│   └── reports.py               # Report generator for legacy evaluation passes
├── scripts/
│   ├── make_eval_batches.py     # Partitions companies into batch files
│   ├── validate_evals.py        # Schema validator for evaluation JSON records
│   └── validate_totals.py       # Independent mathematical recomputation check
├── tests/                       # Complete Pytest suite (amounts, funding details, LLM, pricing)
├── main.py                      # Main entrypoint (aliases scanner.llm_analyzer.main)
├── pyproject.toml               # Package configuration and dependencies
└── README.md                    # This document
```

---

## Installation & Setup

### Requirements
- **Python**: `>= 3.12`
- **uv** (recommended) or **pip**

### 1. Clone the Repository
```bash
git clone https://github.com/Harsha0Sree/new_biz_finder.git
cd new_biz_finder
```

### 2. Install Dependencies

Using `uv` (recommended):
```bash
uv sync
```

Using standard `pip`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Verify the Installation
Run the test suite to ensure parser and network modules are functioning:
```bash
uv run pytest tests/ -v
```
All unit tests should pass.

---

## LLM Provider Configuration

The analyzer supports both **NVIDIA NIM** (cloud-hosted high-throughput API) and **Ollama** (local or on-premise GPU hosting). Both provide completely isolated context windows for each evaluated startup.

---

### Option A: NVIDIA NIM (Cloud / Hosted)

NVIDIA NIM provides access to state-of-the-art open models with high throughput.

#### 1. Obtain an API Key
1. Go to [build.nvidia.com](https://build.nvidia.com/).
2. Sign up or log in.
3. Select any instruct model (e.g. `nvidia/llama-3.1-nemotron-70b-instruct`).
4. Click **"Get API Key"** and generate a key beginning with `nvapi-...`.

#### 2. Configure Environment Variables
Add to your environment or `.env`:
```bash
export NVIDIA_API_KEY="nvapi-your-actual-key-here"
export LLM_PROVIDER="nvidia"
export NVIDIA_MODEL="nvidia/llama-3.1-nemotron-70b-instruct"
```

#### 3. Recommended NVIDIA Models
- `nvidia/llama-3.1-nemotron-70b-instruct` *(Default: exceptional structured reasoning & skepticism)*
- `meta/llama-3.3-70b-instruct` *(Strong B2B analysis and fast generation)*
- `mistralai/mistral-large-2-instruct` *(Detailed code and workflow breakdown)*

#### 4. Run the Analyzer with NVIDIA
```bash
uv run python -m scanner.llm_analyzer \
  --provider nvidia \
  --api-key "$NVIDIA_API_KEY" \
  --model "nvidia/llama-3.1-nemotron-70b-instruct"
```

---

### Option B: Ollama (Local / Self-Hosted GPU)

If you have a local workstation with an NVIDIA/Apple Silicon GPU or want zero-cost evaluations:

#### 1. Install Ollama
- **Linux**:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```
- **macOS / Windows**:
  Download installer from [ollama.com/download](https://ollama.com/download).

#### 2. Pull an Instruct Model
```bash
# Recommended for workstations with >= 48GB VRAM:
ollama pull llama3.1:70b

# Recommended for laptops or machines with 16GB–32GB RAM/VRAM:
ollama pull llama3.1:8b

# Strong alternative:
ollama pull qwen2.5:32b
```

#### 3. Start the Ollama Service
Ensure the Ollama daemon is running and listening on port `11434`:
```bash
ollama serve
```

Verify that the local API is responding:
```bash
curl -s http://localhost:11434/api/tags
```

#### 4. Run the Analyzer with Ollama
```bash
uv run python -m scanner.llm_analyzer \
  --provider ollama \
  --model "llama3.1:8b" \
  --base-url "http://localhost:11434/v1"
```

#### Running on a Remote GPU Machine on your LAN
If Ollama is running on a dedicated server at `192.168.1.50`:
1. On the server, set `OLLAMA_HOST=0.0.0.0` in its environment.
2. Run the client on your local machine:
   ```bash
   uv run python -m scanner.llm_analyzer \
     --provider ollama \
     --model "llama3.1:70b" \
     --base-url "http://192.168.1.50:11434/v1"
   ```

---

## End-to-End Automation Walkthrough

Here is the exact step-by-step sequence to run the entire pipeline from scratch.

### Step 1: Crawl Article Index
Discovers all seed-round announcements from *The SaaS News* archive.
```bash
uv run python -m scanner.crawl_index
```
- **Inputs**: Online website `https://www.thesaasnews.com/tag/seed-round/`
- **Output**: [`data/articles_index.json`](file:///home/mikeysama/products/new_biz_finder/data/articles_index.json)
- **Features**: Binary-searches pagination boundary and crawls in descending order to minimize newly published post drift.

---

### Step 2: Filter Qualifying Rounds
Applies strict qualification rules ($> \$10\text{M}$ USD-equivalent, seed / pre-series-A).
```bash
uv run python -m scanner.filter_articles
```
- **Inputs**: [`data/articles_index.json`](file:///home/mikeysama/products/new_biz_finder/data/articles_index.json)
- **Output**: [`data/qualifying.json`](file:///home/mikeysama/products/new_biz_finder/data/qualifying.json)
- **Features**: Multi-currency regex parsing (`$`, `€`, `£`, `¥`, `₹`, `A$`, `S$`), valuation filter exclusion, fixed FX conversion.

---

### Step 3: Fetch Article Bodies & Build Company Registry
Fetches full article HTML, parses structured Funding Details, and creates the deduplicated company list.
```bash
uv run python -m scanner.fetch_articles
```
- **Inputs**: [`data/qualifying.json`](file:///home/mikeysama/products/new_biz_finder/data/qualifying.json)
- **Outputs**:
  - [`data/companies.json`](file:///home/mikeysama/products/new_biz_finder/data/companies.json) (Registry of unique companies)
  - [`data/cache/text/article__<slug>.txt`](file:///home/mikeysama/products/new_biz_finder/data/cache/text/) (Clean article bodies)
- **Features**: Tolerant heuristic parsing for split table labels, domain extraction, name normalization.

---

### Step 4: Scrape Company Websites & Extract Pricing
Fetches homepages and linked subpages (`/pricing`, `/product`, `/solutions`, etc.) for every unique domain.
```bash
uv run python -m scanner.fetch_sites
```
- **Inputs**: [`data/companies.json`](file:///home/mikeysama/products/new_biz_finder/data/companies.json)
- **Outputs**:
  - [`data/sites.json`](file:///home/mikeysama/products/new_biz_finder/data/sites.json) (Domain status and pricing summaries)
  - [`data/cache/text/site__<domain>__*.txt`](file:///home/mikeysama/products/new_biz_finder/data/cache/text/) (Extracted subpage content)
- **Features**:
  - **Bot-block bypass**: Uses realistic Chrome browser headers.
  - **SPA recovery**: Extracts Next.js pre-rendered state (`__NEXT_DATA__`) and JSON-LD structured schemas.
  - **Pricing extraction**: Automatically parses pricing tiers, dollar amounts, or detects sales-led CTAs (*"Book a Demo"*).
  - **Polite caching**: Re-runs skip already fetched `ok` domains.

---

### Step 5: Run the LLM Evaluation Loop
Builds an isolated context dossier for each company and executes the evaluation using the system prompt.
```bash
# Evaluate all qualifying 2026 companies using NVIDIA NIM:
uv run python -m scanner.llm_analyzer \
  --provider nvidia \
  --api-key "$NVIDIA_API_KEY" \
  --year 2026

# Or test a small batch of 3 companies using local Ollama:
uv run python -m scanner.llm_analyzer \
  --provider ollama \
  --model "llama3.1:8b" \
  --limit 3
```
- **Inputs**:
  - [`prompts/system_prompt.txt`](file:///home/mikeysama/products/new_biz_finder/prompts/system_prompt.txt)
  - Data from [`data/companies.json`](file:///home/mikeysama/products/new_biz_finder/data/companies.json), `article__*.txt`, `site__*.txt`
- **Outputs**:
  - [`data/llm_evals/<slug>.json`](file:///home/mikeysama/products/new_biz_finder/data/llm_evals/) (Individual evaluation JSONs)

---

### Step 6: Aggregate Scores & Generate Rankings
If you need to re-generate the CSV and Markdown rankings from existing evaluation files without making LLM calls:
```bash
uv run python -m scanner.llm_analyzer --aggregate-only
```
- **Outputs**:
  - [`data/llm_scored.json`](file:///home/mikeysama/products/new_biz_finder/data/llm_scored.json)
  - [`data/llm_scores.csv`](file:///home/mikeysama/products/new_biz_finder/data/llm_scores.csv)
  - [`reports/llm_opportunity_ranking.md`](file:///home/mikeysama/products/new_biz_finder/reports/llm_opportunity_ranking.md)

---

## CLI Reference

### `scanner.llm_analyzer` (or `main.py`)

| Flag | Type | Default | Description |
|---|---|---|---|
| `--provider` | `string` | `nvidia` | LLM backend: `nvidia` or `ollama` (or set `LLM_PROVIDER`) |
| `--model` | `string` | *provider default* | Model name override |
| `--api-key` | `string` | `None` | NVIDIA NIM API key (or set `NVIDIA_API_KEY`) |
| `--base-url` | `string` | *provider default* | Custom endpoint URL |
| `--prompt-file`| `path` | `prompts/system_prompt.txt` | Path to system prompt |
| `--year` | `string` | `2026` | Funding year filter (e.g. `2026`, `2025`, `all`) |
| `--limit` | `int` | `None` | Max number of companies to evaluate |
| `--force` | `flag` | `False` | Force re-evaluation even if eval file exists |
| `--no-resume` | `flag` | `False` | Overwrite existing eval files rather than resuming |
| `--no-scrape` | `flag` | `False` | Do not fetch missing website text during context build |
| `--aggregate-only` | `flag` | `False` | Re-generate CSV and report from existing evaluations without API calls |

---

## Understanding the Evaluation Framework

The system prompt ([`prompts/system_prompt.txt`](file:///home/mikeysama/products/new_biz_finder/prompts/system_prompt.txt)) enforces the **Iman persona**—a brutally realistic market analyst evaluating opportunities for a solo operator:

### Core Scoring Dimensions (0–5 per criterion)
1. **Problem Severity & Frequency**: Is this a daily business catastrophe or an optional luxury?
2. **Existing Manual Pain**: What messy manual steps exist before software?
3. **Buyer Purchasing Power & High-Ticket Ceiling**: Plausible willingness to pay $1k–$15k+ for outcome delivery.
4. **AI Replicability & 48-Hour Feasibility**: Can modern LLMs, automations, and no-code tools deliver 80% of the outcome in 1–2 days?
5. **No-Case-Study Sellability**: Can an unknown provider sell this via audits, diagnostic teardowns, or outcome pilots?
6. **India-Origin Friction**: Trust barriers, timezone compatibility, and cold outreach realism.
7. **Solo-Agency Fit**: Can 1 person realistically sell, build, deploy, and support the service?

### Hard-Reality Tests
- **Test A (The 48-Hour Replication Test)**: Requires explicit specification of workflow, LLM role, automation role, and manual tasks.
- **Test B (The $5,000 Buyer Test)**: Reality check on whether a real buyer pays $5k to an unknown agency.
- **Test C (The No-Case-Study Test)**: Viable demo, diagnostic, or sample deliverables.
- **Test D (The "Why Not Do It Internally?" Test)**: Why the client doesn't just use ChatGPT or an internal employee.
- **Test E (The Painkiller Test)**: Classification into *Vitamin*, *Painkiller*, or *Fire Extinguisher*.
- **Test F (Sell the Outcome)**: Formulating an outcome-based offer rather than generic "AI services."

---

## Data Storage & Cache Management

### Disk Caching
- **Raw Web Pages**: Stored in `data/cache/pages/<hash>.meta.json` and `<hash>.body`. Re-fetching an already cached URL takes 0 network requests.
- **Text Cache**: Stored in `data/cache/text/`:
  - `article__<slug>.txt`: Plaintext funding announcements.
  - `site__<domain>__home.txt` & `site__<domain>__<subpage>.txt`: Clean extracted text from websites.
- **Purging Cache**: If you need to re-download a specific website or article, simply remove the corresponding file from `data/cache/text/` and `data/cache/pages/`.

### Keeping Only Filtered Records
The pipeline strictly preserves disk space and evaluation clarity by retaining only the articles for companies that pass the qualification criteria. Non-qualifying articles are automatically pruned.

---

## Testing & Quality Assurance

Run the entire unit test suite:
```bash
uv run pytest tests/ -v
```

### What the Test Suite Validates
- **`tests/test_amounts.py`**: Validates monetary regex parsing, multi-currency conversions (EUR, GBP, JPY, AUD, SGD, INR Cr/Lakh), threshold filtering, and valuation phrase exclusion.
- **`tests/test_funding_details.py`**: Tests extraction of irregular funding table structures from HTML.
- **`tests/test_pricing_and_spa.py`**: Validates detection of self-serve pricing tiers, sales-led demo markers, and recovery of Next.js SPA pre-rendered state.
- **`tests/test_llm.py`**: Tests payload extraction, fallback score parsing, context assembly, and provider initialization.
- **`scripts/validate_totals.py`**: Provides independent mathematical verification of weighted score rollups.
