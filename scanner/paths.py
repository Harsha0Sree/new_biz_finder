"""Canonical paths for every pipeline artifact.

All paths are anchored to the repository root, so commands work from any
working directory. Keep path knowledge here instead of repeating relative
`Path("data/...")` constants across modules.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
CACHE = DATA / "cache"
PAGES = CACHE / "pages"
TEXT = CACHE / "text"

PROMPTS = ROOT / "prompts"
REPORTS = ROOT / "reports"

ARTICLES_INDEX = DATA / "articles_index.json"
QUALIFYING = DATA / "qualifying.json"
ARTICLES_PARSED = DATA / "articles_parsed.json"
COMPANIES = DATA / "companies.json"
REJECTED = DATA / "rejected.json"
SITES = DATA / "sites.json"
ERRORS_LOG = DATA / "errors.log"
EVAL_ORDER = DATA / "eval_order.txt"

EVALS = DATA / "evals"
SCORED = DATA / "scored.json"
SCORES_CSV = DATA / "scores.csv"

LLM_EVALS = DATA / "llm_evals"
LLM_SCORED = DATA / "llm_scored.json"
LLM_SCORES_CSV = DATA / "llm_scores.csv"
LLM_SUMMARY = DATA / "llm_eval_summary.json"

COMPANY_PROMPTS = DATA / "company_prompts"
EVAL_BATCHES = DATA / "eval_batches"

DEFAULT_PROMPT = PROMPTS / "system_prompt.txt"
LLM_RANKING_REPORT = REPORTS / "llm_opportunity_ranking.md"
MASTER_RANKING_REPORT = REPORTS / "master-ranking.md"
REPORTS_INDEX = REPORTS / "index.md"
