"""Canonical paths for every pipeline artifact.

All paths are anchored to the repository root, so commands work from any
working directory. Keep path knowledge here instead of repeating relative
`Path("data/...")` constants across modules.

Every source keeps its own folder under `data/sources/`. The merged corpus in
`data/corpus.json` is what the downstream steps read.
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

SOURCES = DATA / "sources"

SOURCE_TBSAASNEWS = "thesaasnews"
SOURCE_TECHCRUNCH = "techcrunch"
SOURCE_STARTUPS_GALLERY = "startups_gallery"
SOURCE_YC = "yc"
SOURCE_PRODUCTHUNT = "producthunt"

ALL_SOURCES = (
    SOURCE_TBSAASNEWS,
    SOURCE_TECHCRUNCH,
    SOURCE_STARTUPS_GALLERY,
    SOURCE_YC,
    SOURCE_PRODUCTHUNT,
)

# thesaasnews artifacts
ARTICLES_INDEX = SOURCES / SOURCE_TBSAASNEWS / "articles_index.json"
QUALIFYING = SOURCES / SOURCE_TBSAASNEWS / "qualifying.json"
DROPPED = SOURCES / SOURCE_TBSAASNEWS / "dropped.json"
ARTICLES_PARSED = SOURCES / SOURCE_TBSAASNEWS / "articles_parsed.json"
REJECTED = SOURCES / SOURCE_TBSAASNEWS / "rejected.json"

# The merged, deduplicated pipeline input.
CORPUS = DATA / "corpus.json"

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
RUN_LOG = DATA / "run_log.jsonl"

DEFAULT_PROMPT = PROMPTS / "system_prompt.txt"
LLM_RANKING_REPORT = REPORTS / "llm_opportunity_ranking.md"
MASTER_RANKING_REPORT = REPORTS / "master-ranking.md"
REPORTS_INDEX = REPORTS / "index.md"


def source_dir(source: str) -> Path:
    """Folder that holds one source's index, articles and company records."""
    return SOURCES / source


def source_index(source: str) -> Path:
    return source_dir(source) / "index.json"


def source_articles(source: str) -> Path:
    return source_dir(source) / "articles.json"


def source_companies(source: str) -> Path:
    return source_dir(source) / "companies.json"


def source_prompts(source: str) -> Path:
    return COMPANY_PROMPTS / source


def source_llm_evals(source: str) -> Path:
    return LLM_EVALS / source


def source_evals(source: str) -> Path:
    return EVALS / source
