"""Export all formatted LLM user prompts for the companies in the corpus.

Saves each company's exact LLM prompt into data/company_prompts/<source>/<slug>.md,
along with a per-source INDEX.md and a top-level manifest.json.
"""

from __future__ import annotations

import time

from scanner.llm_analyzer import assemble_company_context, get_pipeline_companies
from scanner.paths import COMPANY_PROMPTS, source_prompts
from scanner.storage import write_json, write_text


def export_all_prompts(year: str = "2026") -> list[dict]:
    """Write one prompt dossier per company, grouped into per-source folders."""
    COMPANY_PROMPTS.mkdir(parents=True, exist_ok=True)
    companies = get_pipeline_companies(year)
    print(f"Exporting prompts for {len(companies)} companies to {COMPANY_PROMPTS}/...")

    manifest = []
    t0 = time.time()

    for rank, comp in enumerate(companies, 1):
        slug = comp["slug"]
        source = comp.get("source") or "thesaasnews"
        name = comp.get("company") or slug
        date = comp.get("date") or comp.get("funding_date") or ""
        usd = comp.get("usd_equivalent") or 0.0
        round_field = comp.get("round_field") or ""
        category = comp.get("software_category") or ""
        website = comp.get("website") or ""

        prompt_content = assemble_company_context(comp)

        out_dir = source_prompts(source)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{slug}.md"
        write_text(out_file, prompt_content)

        manifest.append({
            "rank": rank,
            "source": source,
            "company": name,
            "slug": slug,
            "date": date,
            "usd_equivalent": usd,
            "round": round_field,
            "category": category,
            "website": website,
            "prompt_file": str(out_file.relative_to(COMPANY_PROMPTS.parent.parent)),
            "prompt_chars": len(prompt_content),
        })

        if rank % 250 == 0 or rank == len(companies):
            print(f"  [{rank}/{len(companies)}] Saved {slug}.md ({len(prompt_content):,} chars)")

    write_json(COMPANY_PROMPTS / "manifest.json", manifest, indent=2)

    by_source: dict[str, list[dict]] = {}
    for item in manifest:
        by_source.setdefault(item["source"], []).append(item)

    for source, items in by_source.items():
        lines = [
            f"# {source} — LLM User Prompts Index",
            "",
            f"**Total Companies**: {len(items)}  ",
            f"**Exported At**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
            f"**Directory**: `data/company_prompts/{source}/`  ",
            "",
            "Each file is the exact, isolated user prompt sent to the LLM for one company.",
            "",
            "| Rank | Date | Company | Round | Raised (USD) | Category | Prompt File |",
            "|:---:|:---:|:---|:---|:---:|:---|:---|",
        ]
        for item in items:
            usd_str = f"${item['usd_equivalent']:,.0f}" if item["usd_equivalent"] else "n/a"
            lines.append(
                f"| #{item['rank']} | {item['date']} | **{item['company']}** | "
                f"{item['round'] or 'n/a'} | {usd_str} | {item['category'] or 'n/a'} | "
                f"[{item['slug']}.md]({item['slug']}.md) |"
            )
        write_text(source_prompts(source) / "INDEX.md", "\n".join(lines) + "\n")

    elapsed = time.time() - t0
    print(f"\nSuccessfully exported {len(companies)} prompts in {elapsed:.2f}s.")
    print(f"Manifest: {COMPANY_PROMPTS / 'manifest.json'}")
    return manifest


if __name__ == "__main__":
    export_all_prompts()
