"""Master orchestrator for the seed-round opportunity pipeline.

Steps:
1. Crawl the article index from thesaasnews.com.
2. Filter qualifying rounds (at least $10M USD-equivalent).
3. Fetch article bodies and parse Funding Details into companies.json.
4. Scrape company websites, recover SPA text, and extract pricing into sites.json.
5. Export isolated prompt dossiers for each company.
6. Run the LLM evaluation loop and rebuild rankings/reports.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from scanner.env import load_dotenv
from scanner.paths import ARTICLES_INDEX, DEFAULT_PROMPT, SITES

load_dotenv()


def run_pipeline(
    step: str = "all",
    provider: str = os.getenv("LLM_PROVIDER", "nvidia"),
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    prompt_file: Path = DEFAULT_PROMPT,
    year: str = os.getenv("EVAL_YEAR", "2026"),
    limit: int | None = None,
    force_llm: bool = False,
    resume_llm: bool = True,
    refetch_index: bool = False,
    skip_crawl: bool = False,
    skip_scrape: bool = False,
    aggregate_only: bool = False,
    site_workers: int = 4,
    llm_workers: int = 1,
    retry_errors: bool = True,
    include_errors: bool = False,
    max_tokens: int = 6000,
    temperature: float = 0.2,
    timeout: float = 120.0,
    preflight: bool = True,
    dry_run: bool = False,
) -> None:
    print("=" * 72)
    print("       NEW BIZ FINDER — END-TO-END OPPORTUNITY PIPELINE")
    print("=" * 72)
    started = time.time()

    if dry_run:
        print(f"DRY RUN step={step} aggregate_only={aggregate_only} limit={limit}")
        print(f"  provider={provider} model={model or '<default>'} year={year} workers(site={site_workers},llm={llm_workers})")
        print(f"  crawl={'skip' if skip_crawl else 'run'} scrape={'skip' if skip_scrape else 'run'} refetch_index={refetch_index}")
        print("DRY RUN complete: no artifacts were written.")
        return

    if step in ("all", "crawl") and not aggregate_only:
        if skip_crawl and ARTICLES_INDEX.exists():
            print("\n[Step 1/6] Skipping index crawl (--skip-crawl set)")
        else:
            print("\n[Step 1/6] Crawling article index (seed-round & pre-seed)...")
            from scanner.crawl_index import main as crawl_main

            crawl_main(refetch=refetch_index)

    if step in ("all", "filter") and not aggregate_only:
        print("\n[Step 2/6] Filtering qualifying rounds (at least $10M USD-equivalent)...")
        from scanner.filter_articles import main as filter_main

        filter_main()

    if step in ("all", "fetch-articles") and not aggregate_only:
        print("\n[Step 3/6] Fetching article text and extracting funding details...")
        from scanner.fetch_articles import main as fetch_articles_main

        fetch_articles_main()

    if step in ("all", "fetch-sites") and not aggregate_only:
        if skip_scrape and SITES.exists():
            print("\n[Step 4/6] Skipping site scrape (--skip-scrape set)")
        else:
            print("\n[Step 4/6] Scraping company websites and extracting pricing...")
            from scanner.fetch_sites import main as fetch_sites_main

            fetch_sites_main(workers=site_workers)

    if step in ("all", "export-prompts") and not aggregate_only:
        print("\n[Step 5/6] Exporting isolated company prompts...")
        from scanner.export_prompts import export_all_prompts

        export_all_prompts(year=year)

    if step in ("all", "llm") or aggregate_only:
        print("\n[Step 6/6] Running LLM evaluation and ranking...")
        from scanner.llm_analyzer import aggregate_scores, run_llm_pipeline

        if aggregate_only:
            print("  Aggregate-only mode (no LLM calls)...")
            evaluations, json_path, csv_path = aggregate_scores(
                include_errors=include_errors
            )
            print(f"  Aggregated {len(evaluations)} evaluations.")
            print(f"  JSON:   {json_path}")
            print(f"  CSV:    {csv_path}")
            print("  Report: reports/llm_opportunity_ranking.md")
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
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                preflight=preflight,
                workers=llm_workers,
                retry_errors=retry_errors,
            )

    if step == "validate":
        print("\n[Validate] Checking committed artifacts...")
        from scanner.validate import main as validate_main

        if validate_main() != 0:
            raise SystemExit(1)

    elapsed = time.time() - started
    print("\n" + "=" * 72)
    print(f"PIPELINE COMPLETED in {elapsed:.1f}s")
    print("=" * 72)

    try:
        from scanner.runlog import append_run_log

        append_run_log(
            {
                "event": "pipeline_completed",
                "step": step,
                "aggregate_only": aggregate_only,
                "dry_run": dry_run,
                "provider": provider,
                "model": model,
                "year": year,
                "limit": limit,
                "duration_s": round(elapsed, 1),
            }
        )
    except OSError:
        pass


def _env_limit() -> int | None:
    raw = os.getenv("EVAL_LIMIT")
    return int(raw) if raw else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="New Biz Finder — unified seed-startup agency opportunity pipeline"
    )
    parser.add_argument(
        "--step",
        choices=["all", "crawl", "filter", "fetch-articles", "fetch-sites", "export-prompts", "llm", "validate"],
        default="all",
        help="Pipeline step to execute (default: all)",
    )
    parser.add_argument("--skip-crawl", action="store_true", help="Skip crawling if the index exists")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip website scraping if sites.json exists")
    parser.add_argument("--refetch-index", action="store_true", help="Force a full index re-crawl")

    default_provider = os.getenv("LLM_PROVIDER", "nvidia")
    default_year = os.getenv("EVAL_YEAR", "2026")
    parser.add_argument(
        "--provider",
        choices=["nvidia", "ollama"],
        default=default_provider,
        help=f"LLM provider (default: {default_provider})",
    )
    parser.add_argument("--model", default=None, help="LLM model override")
    parser.add_argument("--api-key", default=None, help="NVIDIA NIM API key")
    parser.add_argument("--base-url", default=None, help="Custom LLM base endpoint URL")
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=DEFAULT_PROMPT,
        help="Path to the system prompt file",
    )
    parser.add_argument("--year", default=default_year, help=f"Funding year filter (default: {default_year})")
    parser.add_argument("--limit", type=int, default=_env_limit(), help="Limit companies evaluated")
    parser.add_argument("--site-workers", type=int, default=4, help="Concurrent site fetchers (1-16)")
    parser.add_argument("--llm-workers", type=int, default=1, help="Concurrent LLM evaluations (1-16)")
    parser.add_argument("--max-tokens", type=int, default=6000, help="Token cap for the LLM completion")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds per attempt")
    parser.add_argument("--skip-preflight", dest="preflight", action="store_false", help="Skip the endpoint preflight (/v1/models + chat probe)")
    parser.add_argument("--force", action="store_true", help="Re-evaluate already evaluated companies")
    parser.add_argument(
        "--no-resume", dest="resume", action="store_false", help="Do not skip existing eval files"
    )
    parser.add_argument(
        "--no-retry-errors",
        dest="retry_errors",
        action="store_false",
        help="Skip LLM eval files that previously errored",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Rebuild scores.csv, scored.json, and reports without calling the LLM",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned run and exit without writing any artifacts",
    )
    parser.add_argument(
        "--include-errors",
        action="store_true",
        help="Include LLM error records in aggregate output (diagnostics only)",
    )

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
        site_workers=args.site_workers,
        llm_workers=args.llm_workers,
        retry_errors=args.retry_errors,
        include_errors=args.include_errors,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout=args.timeout,
        preflight=args.preflight,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
