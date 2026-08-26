"""Step 6: render per-company reports + master ranking from scored.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scanner.compute import PILLARS

SCORED = Path("data/scored.json")
REPORTS_DIR = Path("reports")

CAT_NAMES = {
    1: "Commodity-stack maturity", 2: "FM/API substitutability", 3: "Minimal sellable scope",
    4: "Client-system integration complexity (inv)", 5: "Data accessibility",
    6: "Talent rarity required (inv)", 7: "Time-to-first-sellable-build (inv)",
    8: "Discrete project deliverability", 9: "Productized-package potential",
    10: "Retainer/recurring potential", 11: "Build-once-resell-many",
    12: "Per-client customization burden (inv)", 13: "Ongoing ops burden (inv)",
    14: "Low client-side dependency", 15: "Anchors to measurable impact",
    16: "Comparable price points >=$25k", 17: "Budget-line availability",
    18: "Deal-size ceiling", 19: "Upsell/expansion surface",
    20: "Economic buyer seniority (inv)", 21: "Sales-cycle length (inv)",
    22: "Lead-investor caliber", 23: "Round size as demand proxy",
    24: "Category heat/momentum", 25: "Competitor presence",
    26: "On-site monetization proof", 27: "Buyer accessibility to small agency",
    28: "Deep IP/R&D requirement (inv)", 29: "Hardware/infra dependency (inv)",
    30: "Proprietary-data moat (inv)", 31: "Network-effects dependency (inv)",
    32: "Certification/licensing (inv)", 33: "Scale threshold viability (inv)",
    34: "Regulatory exposure (inv)", 35: "Data sensitivity (inv)",
    36: "Error stakes (inv)", 37: "Security liability (inv)",
    38: "ROI provability", 39: "Reputation-damage risk (inv)",
    40: "ICP findability via outbound", 41: "Geographic constraint (inv)",
    42: "Localization barrier (inv)", 43: "Domain-expertise barrier (inv)",
    44: "Incumbent lock-in (inv)", 45: "Platform risk (inv)",
    46: "Commoditization speed (inv)", 47: "Repeat purchase potential",
    48: "Cross-industry portability", 49: "Margin sustainability vs copycats",
    50: "Lifecycle position", 51: "Storytelling/demo-ability",
    52: "Reference-customer availability",
}


def slug_to_filename(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:80] + ".md"


def company_report(s: dict, rank: int) -> str:
    cats = s["categories"]
    comb = s["category_combined_0_10"]
    lines: list[str] = []
    lines.append(f"# {s['company']} — Agency-Opportunity Report")
    lines.append("")
    lines.append(f"**Rank:** #{rank} | **Total:** {s['total']}/100 | **Tier:** {s['tier']} | **Confidence:** {s['confidence']}")
    lines.append("")
    lines.append("## Funding & Identity")
    lines.append(f"- Article: {s.get('article_url')}")
    lines.append(f"- Raised: {s.get('raised_raw')} (~${s.get('usd_equivalent'):,.0f} USD-equiv)" if s.get("usd_equivalent") else "- Raised: n/a")
    lines.append(f"- Software category: {s.get('software_category')}")
    lines.append(f"- Lead investor: {s.get('lead_investor') or 'n/a'}")
    lines.append(f"- Website: {s.get('website') or 'none found'} ({'domain: ' + str(s.get('domain'))})")
    flags = s.get("flags") or []
    if flags:
        lines.append(f"- Flags: {', '.join(flags)}")
    lines.append(f"- Archetype: `{s['archetype']}` — {s['archetype_rationale']}")
    lines.append("")
    gates = s["gates"]
    applied = [g for g in gates if g["applied"]]
    lines.append("## Hard Gates")
    if applied:
        for g in applied:
            lines.append(f"- **{g['gate']} APPLIED** — {g['rationale']}")
    else:
        lines.append("- No gates applied.")
    lines.append("")
    lines.append("## Category Scores (0–10 per head)")
    lines.append("| # | Category | H1 Build | H2 Sell | H3 Buy | H4 Risk | Combined | Evidence |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i in range(1, 53):
        c = cats[str(i)]
        lines.append(
            f"| {i} | {CAT_NAMES[i]} | {c['h1']} | {c['h2']} | {c['h3']} | {c['h4']} "
            f"| **{comb[str(i)]:.1f}** | {c['evidence']} |"
        )
    lines.append("")
    lines.append("## Pillar Rollup")
    lines.append("| Pillar | Score /10 | Raw weight | Adjusted weight |")
    lines.append("|---|---|---|---|")
    for pid, p in PILLARS.items():
        lines.append(
            f"| {pid}. {p['name']} | {s['pillar_scores_0_10'][pid]:.1f} "
            f"| {s['pillar_weights_raw'][pid]:.3f} | {s['pillar_weights_adjusted'][pid]:.3f} |"
        )
    lines.append("")
    lines.append(f"**Gate mask:** {s['gate_mask']} (applied: {', '.join(s['applied_gates']) or 'none'})")
    lines.append("")
    ap = s["agency_play"]
    lines.append("## The Agency Play")
    lines.append(f"- **What to build:** {ap['build_scope']}")
    lines.append(f"- **How to package it:** {ap['packaging']}")
    lines.append(f"- **Suggested pricing:** {ap['pricing']}")
    lines.append(f"- **First clients:** {ap['first_clients']}")
    lines.append("")
    lines.append("---")
    lines.append("*Scores: H1 Builder 30% / H2 Seller 35% / H3 Buyer 25% / H4 Risk(inverse, higher=safer) 10%. "
                 "(inv) categories score higher when the burden is lower. Framework v1 - see SCORING_SPEC.md.*")
    return "\n".join(lines)


def master_ranking(scored: list[dict]) -> str:
    tiers = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scored:
        tiers[s["tier"]] += 1
    lines: list[str] = []
    lines.append("# Master Ranking — Seed-Round Agency Opportunities")
    lines.append("")
    lines.append(f"**{len(scored)} companies evaluated** | Tiers: A={tiers['A']} (build now), B={tiers['B']}, C={tiers['C']}, D={tiers['D']} (skip)")
    lines.append("")
    lines.append("| Rank | Company | Domain | Category | Raised (USD-eq) | Archetype | Total | Tier | One-line thesis |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(scored, 1):
        thesis = s["agency_play"]["build_scope"]
        thesis = (thesis[:110] + "...") if len(thesis) > 113 else thesis
        thesis = thesis.replace("|", "/")
        raised = f"${s['usd_equivalent']/1e6:,.1f}M" if s.get("usd_equivalent") else "n/a"
        gate_note = f" (gates: {','.join(s['applied_gates'])})" if s["applied_gates"] else ""
        lines.append(
            f"| {i} | [{s['company']}](/{slug_to_filename(s['slug'])}) | {s.get('domain') or '-'} "
            f"| {(s.get('software_category') or '-')[:30]} | {raised} | {s['archetype']} "
            f"| **{s['total']}** {s['tier']}{gate_note} | {thesis} |"
        )
    lines.append("")
    lines.append("## Methodology Appendix")
    lines.append("""
### Pipeline
1. Crawled the full `/tag/seed-round/` archive of thesaasnews.com (351 tag pages, 4,203 articles, descending page order).
2. Title-parsed amounts across currencies ($ € £ ¥ ₹ Rs A$ S$ US$) with fixed FX (EUR 1.08, GBP 1.27, JPY 0.0067, AUD 0.65, SGD 0.74, INR Cr=$120k); kept strictly >$10M USD-equivalent; Pre-Seed and named later series excluded; unlabeled rounds verified against each article's Funding Details block.
3. Parsed Funding Details (company, website, raised, round, investors, category) from every qualifying article; deduped by normalized company name + domain.
4. Fetched each company website (homepage + linked pricing/product/about/customers/blog pages), stripped to text, classified ok/js_only/dead.
5. Scored every company on 52 categories x 4 heads (Builder .30 / Seller .35 / Buyer .25 / Risk-inverse .10) with cited evidence; assigned one of six archetypes (pillar-weight multipliers); evaluated hard gates G1-G5.
6. Computed totals deterministically: gate_mask x sum(adjusted_pillar_weight x pillar_score) x 100. Tiers: A>=80, B>=65, C>=50, D<50.

### Reading the scores
- Every category row cites concrete evidence from the funding article and/or company site.
- `(inv)` categories are inverse-burden: higher score = less burden = better for an agency clone play.
- Confidence `low` = site unfetchable/JS-only; evaluation leaned on the funding article alone.
- G5 (dead/parked/no-website) multiplies the total by 0.20; js-only sites were NOT gated.

### Caveats
- Amounts rely on publisher-reported figures; FX is fixed-table (see repo `scanner/amounts.py`).
- Scores reflect agency-replicability of PARTIAL functionality sold as high-ticket service - not investment quality.
""")
    return "\n".join(lines)


def main() -> None:
    payload = json.loads(SCORED.read_text())
    scored = payload["companies"]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for rank, s in enumerate(scored, 1):
        path = REPORTS_DIR / slug_to_filename(s["slug"])
        path.write_text(company_report(s, rank), encoding="utf-8")
    (REPORTS_DIR / "master-ranking.md").write_text(master_ranking(scored), encoding="utf-8")
    print(f"wrote {len(scored)} company reports + master-ranking.md to {REPORTS_DIR}/")


if __name__ == "__main__":
    main()
