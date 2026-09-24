"""2026 Company LLM Analysis Runner.

Loops through all companies that raised money in 2026 matching criteria,
assembles rich isolated context per company, executes an isolated LLM evaluation
via NVIDIA NIM or Ollama, and records structured agency opportunity scores.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from scanner.env import load_dotenv
from scanner.fetch_articles import fetch_source_pr
from scanner.fetch_sites import fetch_site
from scanner.llm import LLMClient, LLMResult

load_dotenv()

COMPANIES_PATH = Path("data/companies.json")
ARTICLE_TEXT_DIR = Path("data/cache/text")
EVALS_DIR = Path("data/llm_evals")
SCORED_JSON_PATH = Path("data/llm_scored.json")
SCORED_CSV_PATH = Path("data/llm_scores.csv")
REPORTS_DIR = Path("reports")
DEFAULT_PROMPT_PATH = Path("prompts/system_prompt.txt")


def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_PATH) -> str:
    """Load the user's system prompt from disk."""
    if prompt_path.exists():
        prompt = prompt_path.read_text(encoding="utf-8").strip()
        if prompt:
            return prompt
    raise FileNotFoundError(
        f"System prompt file not found or empty at {prompt_path}. "
        "Please create prompts/system_prompt.txt."
    )


def is_raised_in_year(company: dict[str, Any], year: str = "2026") -> bool:
    """Check if the company funding occurred in the specified year."""
    funding_date = company.get("funding_date") or ""
    if year in funding_date:
        return True

    date = company.get("date") or ""
    if year in date:
        return True

    # Check source URL or title if funding_date is vague
    source_url = company.get("source_url") or ""
    if f"/{year}/" in source_url:
        return True

    title = company.get("title") or ""
    if f" {year}" in title or f"/{year}" in title:
        return True

    slug = company.get("slug") or ""
    if f"-{year}-" in slug or slug.endswith(f"-{year}"):
        return True

    return False


def get_qualifying_2026_companies(year: str = "2026") -> list[dict[str, Any]]:
    """Get all deduplicated companies meeting criteria that raised in the target year.
    
    No heuristic or gate narrowing is done here; all qualifying companies are returned.
    Prioritizes latest funding rounds by sorting date descending, then raise amount descending.
    """
    if not COMPANIES_PATH.exists():
        raise FileNotFoundError(f"{COMPANIES_PATH} not found. Run previous pipeline steps first.")

    all_companies: list[dict[str, Any]] = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    qualifying_2026 = [
        c for c in all_companies
        if not c.get("duplicate_of_previous") and is_raised_in_year(c, year)
    ]
    # Prioritize latest funding rounds first by date descending, then amount descending
    qualifying_2026.sort(
        key=lambda c: (
            c.get("date") or c.get("funding_date") or "",
            c.get("usd_equivalent") or 0.0,
        ),
        reverse=True,
    )
    return qualifying_2026


def assemble_company_context(company: dict[str, Any], scrape_missing: bool = True) -> str:
    """Assemble all scraped data for a single company into a rich, isolated context markdown."""
    slug = company["slug"]
    domain = company.get("domain")
    website = company.get("website")
    source_url = company.get("source_url")

    # 1. Scrape missing site or source if requested
    if scrape_missing:
        if domain and website:
            home_txt = ARTICLE_TEXT_DIR / f"site__{domain}__home.txt"
            if not home_txt.exists():
                try:
                    fetch_site(domain, website)
                except Exception:
                    pass

        if source_url:
            source_txt = ARTICLE_TEXT_DIR / f"source__{slug}.txt"
            if not source_txt.exists():
                fetch_source_pr(source_url, slug)

    # 2. Collect files
    article_file = ARTICLE_TEXT_DIR / f"article__{slug}.txt"
    if article_file.exists():
        raw_art = article_file.read_text(encoding="utf-8", errors="replace")
        # Strip HTML blocks and UI artifacts
        raw_art = re.sub(r"<div\b[^>]*>[\s\S]*?</div>", "", raw_art, flags=re.IGNORECASE)
        raw_art = re.sub(r"<a\b[^>]*>[\s\S]*?</a>", "", raw_art, flags=re.IGNORECASE)
        raw_art = re.sub(r"<[^>]+>", "", raw_art)
        cleaned_lines = [
            ln.strip() for ln in raw_art.splitlines()
            if ln.strip() and not ln.strip().lower().startswith(("link copied", "copy failed", "get funding alerts"))
        ]
        article_text = "\n".join(cleaned_lines)
    else:
        article_text = "No article text available."

    source_file = ARTICLE_TEXT_DIR / f"source__{slug}.txt"
    source_text = source_file.read_text(encoding="utf-8", errors="replace") if source_file.exists() else None

    site_texts: list[tuple[str, str]] = []
    if domain:
        site_pattern = f"site__{domain}__*.txt"
        for p in sorted(ARTICLE_TEXT_DIR.glob(site_pattern)):
            name = p.stem.replace(f"site__{domain}__", "")
            content = p.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                site_texts.append((name, content))

    # 3. Build Markdown Document
    sections: list[str] = []
    sections.append(f"# Company Analysis Target: {company.get('company')}")
    sections.append("")
    sections.append("## Overview & Verified Funding Facts")
    sections.append(f"- **Company Name**: {company.get('company')}")
    sections.append(f"- **Website**: {company.get('website') or 'None provided'}")
    sections.append(f"- **Domain**: {company.get('domain') or 'None'}")
    sections.append(f"- **Funding Round**: {company.get('round_field')} (source: {company.get('round_source')})")
    sections.append(f"- **Amount Raised**: {company.get('raised_raw')} (~${company.get('usd_equivalent', 0):,.0f} USD-equivalent)")
    sections.append(f"- **Funding Date**: {company.get('funding_date') or 'Unknown'}")
    sections.append(f"- **Lead Investor(s)**: {company.get('lead_investor') or 'Not specified'}")
    sections.append(f"- **Additional Investors**: {company.get('additional_investors') or 'None listed'}")
    sections.append(f"- **Software Category**: {company.get('software_category') or 'Unclassified'}")
    if source_url:
        sections.append(f"- **Original Source / Press Release URL**: {source_url}")
    sections.append("")

    pricing = company.get("pricing") or {}
    sections.append("## Pricing & Buyer Economics (from Website)")
    sections.append(f"- **Pricing Summary**: {pricing.get('summary', 'No pricing published on website.')}")
    if pricing.get("price_points"):
        sections.append(f"- **Detected Price Points**: {', '.join(pricing['price_points'])}")
    if pricing.get("plans"):
        sections.append(f"- **Detected Plans / Tiers**: {', '.join(pricing['plans'])}")
    sales_motion = (
        "Sales-led (demo/contact sales required)"
        if pricing.get("is_sales_led")
        else ("Self-serve / public tiers" if pricing.get("has_public_pricing") else "Undetermined / hidden")
    )
    sections.append(f"- **Sales Model**: {sales_motion}")
    sections.append("")

    sections.append("## Funding Article Content")
    sections.append(article_text.strip())
    sections.append("")

    if source_text:
        sections.append("## External Press Release / Source Announcement")
        sections.append(source_text.strip()[:6000])  # limit length if verbose
        sections.append("")

    if site_texts:
        sections.append("## Scraped Company Website Content")
        for page_name, text in site_texts:
            sections.append(f"### Subpage: /{page_name}")
            sections.append(text[:5000])  # keep each subpage concise and punchy
            sections.append("")
    else:
        sections.append("## Scraped Company Website Content")
        sections.append("No website content available (site unreachable, bot-blocked, or no domain provided).")

    sections.append("")
    sections.append("---")
    sections.append("## EVALUATION INSTRUCTIONS & REQUIRED OUTPUT FORMAT")
    sections.append("Conduct your complete, brutal, evidence-backed evaluation following all system prompt criteria.")
    sections.append("At the very end of your response, you MUST provide a machine-readable JSON code block in this exact schema:")
    sections.append("```json")
    sections.append("{")
    sections.append('  "score": <overall opportunity score as an integer from 0 to 100>,')
    sections.append('  "verdict": "<one-sentence executive verdict summarizing why this is or is not a viable agency opportunity>",')
    sections.append('  "can_reproduce_48h": <true or false>,')
    sections.append('  "agency_tier": "<Tier 1 | Tier 2 | Tier 3 | Disqualified>",')
    sections.append('  "primary_risk": "<concise statement of primary business risk>",')
    sections.append('  "target_service_offer": "<concise description of the packageable service, or N/A>"')
    sections.append("}")
    sections.append("```")

    return "\n".join(sections)


def save_evaluation(
    company: dict[str, Any],
    result: LLMResult,
    evals_dir: Path = EVALS_DIR,
) -> Path:
    """Save an individual company evaluation to disk."""
    evals_dir.mkdir(parents=True, exist_ok=True)
    slug = company["slug"]
    out_path = evals_dir / f"{slug}.json"

    data = {
        "slug": slug,
        "company": company.get("company"),
        "domain": company.get("domain"),
        "website": company.get("website"),
        "usd_equivalent": company.get("usd_equivalent"),
        "raised_raw": company.get("raised_raw"),
        "round_field": company.get("round_field"),
        "funding_date": company.get("funding_date"),
        "lead_investor": company.get("lead_investor"),
        "software_category": company.get("software_category"),
        "pricing": company.get("pricing"),
        "in_previous_67": (Path("data/evals") / f"{slug}.json").exists(),
        "provider": result.provider,
        "model": result.model,
        "score": result.score,
        "verdict": result.verdict,
        "parsed": result.parsed,
        "raw_response": result.raw_response,
        "usage": result.usage,
        "error": result.error,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_path


def aggregate_scores(evals_dir: Path = EVALS_DIR) -> tuple[list[dict[str, Any]], Path, Path]:
    """Aggregate all completed evaluations into data/llm_scored.json and data/llm_scores.csv."""
    files = list(evals_dir.glob("*.json"))
    evals: list[dict[str, Any]] = []
    for f in files:
        try:
            evals.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass

    # Sort descending by score, then raised amount
    evals.sort(key=lambda e: (e.get("score") or 0, e.get("usd_equivalent") or 0), reverse=True)

    # Write JSON
    SCORED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORED_JSON_PATH.write_text(json.dumps(evals, indent=2), encoding="utf-8")

    # Write CSV
    with SCORED_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "company", "domain", "score", "category", "raised_usd",
            "pricing_on_site", "in_previous_67", "verdict", "model", "evaluated_at",
        ])
        for rank, e in enumerate(evals, 1):
            pricing_data = e.get("pricing") or {}
            pricing_str = pricing_data.get("summary") or ""
            writer.writerow([
                rank,
                e.get("company", ""),
                e.get("domain", ""),
                e.get("score", 0),
                e.get("software_category", ""),
                f"${e.get('usd_equivalent', 0):,.0f}",
                pricing_str,
                "yes" if e.get("in_previous_67") else "no",
                e.get("verdict", "").replace("\n", " "),
                e.get("model", ""),
                e.get("evaluated_at", ""),
            ])

    # Write markdown summary report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_md = REPORTS_DIR / "llm_opportunity_ranking.md"
    lines: list[str] = [
        "# 2026 Seed-Round Agency Opportunity Rankings (LLM Evaluated)",
        "",
        f"**Evaluated Companies**: {len(evals)}",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
        "| Rank | Score | Company | Category | Raised | On-Site Pricing | Prior 67? | Verdict |",
        "|:---:|:---:|:---|:---|:---|:---|:---:|:---|",
    ]
    for rank, e in enumerate(evals, 1):
        v = (e.get("verdict") or "").replace("|", "-")
        pricing_data = e.get("pricing") or {}
        pr_str = pricing_data.get("summary") or "None"
        pr_short = (pr_str[:45] + "...") if len(pr_str) > 48 else pr_str
        prior_str = "✓" if e.get("in_previous_67") else "new"
        lines.append(
            f"| #{rank} | **{e.get('score', 0)}/100** | {e.get('company')} | {e.get('software_category') or 'n/a'} | ${e.get('usd_equivalent', 0):,.0f} | {pr_short} | {prior_str} | {v} |"
        )
    report_md.write_text("\n".join(lines), encoding="utf-8")

    return evals, SCORED_JSON_PATH, SCORED_CSV_PATH


def run_llm_pipeline(
    provider: str = "nvidia",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    prompt_file: Path = DEFAULT_PROMPT_PATH,
    year: str = "2026",
    limit: int | None = None,
    resume: bool = True,
    force: bool = False,
    scrape_missing: bool = True,
) -> None:
    """Run the 2026 LLM analysis loop with isolated company contexts."""
    print(f"=== Starting 2026 Agency Opportunity Analysis ({provider.upper()}) ===")
    system_prompt = load_system_prompt(prompt_file)
    print(f"Loaded system prompt from {prompt_file} ({len(system_prompt)} chars)")

    client = LLMClient(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
    print(f"Provider: {client.provider} | Model: {client.model} | Base URL: {client.base_url}")

    companies = get_qualifying_2026_companies(year)
    print(f"Found {len(companies)} qualifying companies that raised in {year}.")

    if limit is not None and limit > 0:
        companies = companies[:limit]
        print(f"Execution limited to {limit} companies.")

    todo: list[dict[str, Any]] = []
    for c in companies:
        out_file = EVALS_DIR / f"{c['slug']}.json"
        if resume and not force and out_file.exists():
            continue
        todo.append(c)

    print(f"Pending evaluation: {len(todo)} (Skipped already evaluated: {len(companies) - len(todo)})")

    for idx, c in enumerate(todo, 1):
        name = c.get("company", c["slug"])
        usd = c.get("usd_equivalent", 0)
        print(f"[{idx}/{len(todo)}] Evaluating: {name} (${usd:,.0f})...", flush=True)

        t_start = time.time()
        context = assemble_company_context(c, scrape_missing=scrape_missing)
        result = client.analyze_company(
            system_prompt=system_prompt,
            company_context=context,
        )
        elapsed = time.time() - t_start

        out_path = save_evaluation(c, result)
        print(f"    -> Score: {result.score}/100 | Verdict: {result.verdict[:80]}... ({elapsed:.1f}s)")
        if result.error:
            print(f"    [!] Error encountered: {result.error}")

    print("\nAggregating final rankings and reports...")
    evals, json_path, csv_path = aggregate_scores(EVALS_DIR)
    print(f"Successfully processed {len(evals)} evaluations.")
    print(f"Saved ranked JSON: {json_path}")
    print(f"Saved ranked CSV:  {csv_path}")
    print(f"Saved summary:     reports/llm_opportunity_ranking.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM Agency Opportunity Analysis for 2026 Seed Companies")
    parser.add_argument("--provider", choices=["nvidia", "ollama"], default=os.getenv("LLM_PROVIDER", "nvidia"),
                        help="LLM provider: 'nvidia' or 'ollama'")
    parser.add_argument("--model", default=None, help="Model name (optional override)")
    parser.add_argument("--api-key", default=None, help="API key for NVIDIA NIM (or use NVIDIA_API_KEY env)")
    parser.add_argument("--base-url", default=None, help="Base URL for LLM endpoint")
    parser.add_argument("--prompt-file", type=Path, default=DEFAULT_PROMPT_PATH,
                        help="Path to system prompt file")
    default_year = os.getenv("EVAL_YEAR", "2026")
    default_limit = int(os.getenv("EVAL_LIMIT")) if os.getenv("EVAL_LIMIT") else None
    parser.add_argument("--year", default=default_year, help=f"Funding year to filter for (default: {default_year})")
    parser.add_argument("--limit", type=int, default=default_limit, help="Limit number of companies to evaluate")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation of existing companies")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Do not skip existing eval files")
    parser.add_argument("--no-scrape", dest="scrape_missing", action="store_false",
                        help="Do not attempt to scrape missing websites/sources")
    parser.add_argument("--aggregate-only", action="store_true", help="Only rebuild scored.json and CSV from existing evals")

    args = parser.parse_args()

    if args.aggregate_only:
        evals, jpath, cpath = aggregate_scores()
        print(f"Aggregated {len(evals)} evaluations into {jpath} and {cpath}")
        return

    run_llm_pipeline(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        prompt_file=args.prompt_file,
        year=args.year,
        limit=args.limit,
        resume=args.resume,
        force=args.force,
        scrape_missing=args.scrape_missing,
    )


if __name__ == "__main__":
    main()
