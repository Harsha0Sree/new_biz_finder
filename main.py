"""Master Orchestrator — New Biz Finder Pipeline.

Runs the entire intelligence and evaluation pipeline end-to-end with a single command:
1. Crawl article index (from thesaasnews.com)
2. Filter qualifying rounds (>= $10M USD-equivalent, seed / pre-seed / pre-series-a)
3. Fetch article bodies & parse verified Funding Details -> companies.json
4. Scrape company websites, recover SPA text, extract pricing info -> sites.json
5. Run LLM evaluation loop using system prompt -> llm_evals/, scores.csv, and report
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from scanner.env import load_dotenv

# Ensure .env is loaded
load_dotenv()


def run_pipeline(
    step: str = "all",
    provider: str = os.getenv("LLM_PROVIDER", "nvidia"),
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    prompt_file: Path = Path("prompts/system_prompt.txt"),
    year: str = os.getenv("EVAL_YEAR", "2026"),
    limit: int | None = None,
    force_llm: bool = False,
    resume_llm: bool = True,
    refetch_index: bool = False,
    skip_crawl: bool = False,
    skip_scrape: bool = False,
    aggregate_only: bool = False,
) -> None:
    print("=" * 72)
    print("       NEW BIZ FINDER — END-TO-END OPPORTUNITY PIPELINE")
    print("=" * 72)
    t0 = time.time()

    # Step 1: Crawl Index
    if step in ("all", "crawl") and not aggregate_only:
        if skip_crawl and Path("data/articles_index.json").exists():
            print("\n[Step 1/5] Skipping index crawl (--skip-crawl set and articles_index.json exists)")
        else:
            print("\n[Step 1/5] Crawling article index from thesaasnews.com (seed-round & pre-seed)...")
            if refetch_index and "--refetch" not in sys.argv:
                sys.argv.append("--refetch")
            from scanner.crawl_index import main as crawl_main
            crawl_main()

    # Step 2: Filter Qualifying Rounds
    if step in ("all", "filter") and not aggregate_only:
        print("\n[Step 2/5] Filtering qualifying rounds (>= $10M USD seed / pre-seed / pre-series-a)...")
        from scanner.filter_articles import main as filter_main
        filter_main()

    # Step 3: Fetch Articles & Parse Funding Details
    if step in ("all", "fetch-articles") and not aggregate_only:
        print("\n[Step 3/5] Fetching article text & extracting funding details into companies.json...")
        from scanner.fetch_articles import main as fetch_art_main
        fetch_art_main()

    # Step 4: Scrape Sites, Recover SPA text & Extract Pricing
    if step in ("all", "fetch-sites") and not aggregate_only:
        if skip_scrape and Path("data/sites.json").exists():
            print("\n[Step 4/5] Skipping site scraping (--skip-scrape set and sites.json exists)")
        else:
            print("\n[Step 4/5] Scraping company websites, recovering SPA state & extracting pricing...")
            from scanner.fetch_sites import main as fetch_sites_main
            fetch_sites_main()

    # Step: Export LLM User Prompts
    if step in ("all", "export-prompts") and not aggregate_only:
        print("\n[Export] Generating isolated company LLM user prompts -> data/company_prompts/...")
        from scanner.export_prompts import export_all_prompts
        export_all_prompts(year=year)

    # Step 5: Run LLM Evaluation & Opportunity Ranking
    if step in ("all", "llm") or aggregate_only:
        print("\n[Step 5/5] Running LLM Agency Opportunity Evaluation & Ranking...")
        from scanner.llm_analyzer import aggregate_scores, run_llm_pipeline

        if aggregate_only:
            print("  Running aggregate-only mode (rebuilding scored.json, scores.csv, and reports)...")
            evals, jpath, cpath = aggregate_scores()
            print(f"  Aggregated {len(evals)} evaluations.")
            print(f"  JSON:   {jpath}")
            print(f"  CSV:    {cpath}")
            print(f"  Report: reports/llm_opportunity_ranking.md")
        else:
            run_llm_pipeline(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                prompt_file=prompt_file,
                year=year,
                limit=limit,
                resume=resume_llm,
                force=force_llm,
                scrape_missing=True,
            )

    elapsed = time.time() - t0
    print("\n" + "=" * 72)
    print(f"PIPELINE COMPLETED in {elapsed:.1f}s")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="New Biz Finder — Unified End-to-End Seed Startup Agency Opportunity Pipeline"
    )
    # Execution steps
    parser.add_argument(
        "--step",
        choices=["all", "crawl", "filter", "fetch-articles", "fetch-sites", "export-prompts", "llm"],
        default="all",
        help="Pipeline step to execute (default: all)",
    )
    parser.add_argument("--skip-crawl", action="store_true", help="Skip crawling if data/articles_index.json exists")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip website scrape if data/sites.json exists")
    parser.add_argument("--refetch-index", action="store_true", help="Force re-crawling of all index pages")

    # LLM Settings (defaults pulled from .env)
    default_provider = os.getenv("LLM_PROVIDER", "nvidia")
    default_year = os.getenv("EVAL_YEAR", "2026")
    default_limit = int(os.getenv("EVAL_LIMIT")) if os.getenv("EVAL_LIMIT") else None

    parser.add_argument("--provider", choices=["nvidia", "ollama"], default=default_provider,
                        help=f"LLM provider: 'nvidia' or 'ollama' (default: {default_provider})")
    parser.add_argument("--model", default=None, help="LLM model override (defaults from .env / provider)")
    parser.add_argument("--api-key", default=None, help="NVIDIA NIM API key (defaults to NVIDIA_API_KEY from .env)")
    parser.add_argument("--base-url", default=None, help="Custom LLM base endpoint URL")
    parser.add_argument("--prompt-file", type=Path, default=Path("prompts/system_prompt.txt"),
                        help="Path to system prompt file")
    parser.add_argument("--year", default=default_year, help=f"Funding year filter (default: {default_year})")
    parser.add_argument("--limit", type=int, default=default_limit, help="Limit number of companies to evaluate")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation of already evaluated companies")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Do not resume/skip evaluated files")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Rebuild scores.csv, scored.json, and ranking reports without calling LLM")

    args = parser.parse_args()

    run_pipeline(
        step=args.step,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        prompt_file=args.prompt_file,
        year=args.year,
        limit=args.limit,
        force_llm=args.force,
        resume_llm=args.resume,
        refetch_index=args.refetch_index,
        skip_crawl=args.skip_crawl,
        skip_scrape=args.skip_scrape,
        aggregate_only=args.aggregate_only,
    )


if __name__ == "__main__":
    main()
