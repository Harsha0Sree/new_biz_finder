"""Export all formatted LLM user prompts for qualifying 2026 companies.

Saves each company's exact LLM prompt into data/company_prompts/{slug}.md,
along with an INDEX.md and manifest.json for easy consumption elsewhere.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scanner.llm_analyzer import assemble_company_context, get_qualifying_2026_companies

PROMPTS_DIR = Path("data/company_prompts")


def export_all_prompts(year: str = "2026") -> list[dict]:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    companies = get_qualifying_2026_companies(year)
    print(f"Exporting prompts for {len(companies)} qualifying {year} companies to {PROMPTS_DIR}/...")

    manifest = []
    t0 = time.time()

    for rank, comp in enumerate(companies, 1):
        slug = comp["slug"]
        name = comp.get("company") or slug
        date = comp.get("date") or comp.get("funding_date") or ""
        usd = comp.get("usd_equivalent") or 0.0
        round_field = comp.get("round_field") or ""
        category = comp.get("software_category") or ""
        website = comp.get("website") or ""

        # Assemble the exact markdown prompt that goes to the LLM
        prompt_content = assemble_company_context(comp, scrape_missing=False)

        # File name by slug
        out_file = PROMPTS_DIR / f"{slug}.md"
        out_file.write_text(prompt_content, encoding="utf-8")

        manifest.append({
            "rank": rank,
            "company": name,
            "slug": slug,
            "date": date,
            "usd_equivalent": usd,
            "round": round_field,
            "category": category,
            "website": website,
            "prompt_file": str(out_file.relative_to(PROMPTS_DIR.parent.parent)),
            "prompt_chars": len(prompt_content),
        })

        if rank % 50 == 0 or rank == len(companies):
            print(f"  [{rank}/{len(companies)}] Saved {slug}.md ({len(prompt_content):,} chars)")

    # Save manifest.json
    manifest_path = PROMPTS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Generate an INDEX.md
    index_lines = [
        f"# Qualifying {year} Startups — LLM User Prompts Index",
        "",
        f"**Total Companies**: {len(companies)}  ",
        f"**Exported At**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
        f"**Directory**: `data/company_prompts/`  ",
        "",
        "This directory contains the exact, isolated user prompts sent to the LLM for agency opportunity evaluation.",
        "Each file aggregates verified funding details, source announcement press releases, pricing economics, and scraped website content.",
        "",
        "| Rank | Date | Company | Round | Raised (USD) | Category | Prompt File |",
        "|:---:|:---:|:---|:---|:---:|:---|:---|",
    ]

    for item in manifest:
        usd_str = f"${item['usd_equivalent']:,.0f}"
        file_link = f"[{item['slug']}.md]({item['slug']}.md)"
        index_lines.append(
            f"| #{item['rank']} | {item['date']} | **{item['company']}** | {item['round']} | {usd_str} | {item['category'] or 'n/a'} | {file_link} |"
        )

    (PROMPTS_DIR / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    elapsed = time.time() - t0
    print(f"\nSuccessfully exported {len(companies)} prompts in {elapsed:.2f}s.")
    print(f"Manifest: {manifest_path}")
    print(f"Index:    {PROMPTS_DIR / 'INDEX.md'}")
    return manifest


if __name__ == "__main__":
    export_all_prompts()
