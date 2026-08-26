# Agency-Opportunity Transformer — Scoring Specification v1

This document defines the complete scoring framework for evaluating seed-funded
companies on **how easy it is for an agency to build a partial-functionality
version of their product and sell it as a high-ticket service (not SaaS)**.

You (the evaluator) read each company's evidence files, then produce one JSON
evaluation file per company following the schema at the end. All numeric
combination into totals is done deterministically by code — you ONLY provide
per-category head scores (0–10), archetype, gates, and written judgment fields.

## Perspective: the client of the agency

The agency sells to businesses that want AI/software capabilities similar to
the company's product, without paying enterprise SaaS prices or waiting for
vendor roadmaps. The agency builds a *partial* version (enough functionality
to deliver an outcome) and sells it as a project/retainer ("service as
software"). High-ticket = engagements plausibly $25k–$250k+.

## Layer 1 — Evaluation Heads

Score EVERY category through four independent head perspectives (0–10):

- **H1 Builder (weight 0.30)** — engineering ease of building the partial
  product with commodity stacks/APIs, integration effort, data access,
  talent needed, time to first sellable build.
- **H2 Seller (weight 0.35)** — how easily an agency can package, demo, and
  close this as a high-ticket offer; differentiation story; sales-cycle fit.
- **H3 Buyer (weight 0.25)** — target-client willingness & capacity to pay:
  budget lines, measurable ROI, economic-buyer accessibility, urgency.
- **H4 Risk (weight 0.10)** — downside adjustment: HIGHER score = LESS risk
  (low liability, low regulatory exposure, forgiving error stakes).

Per category: `combined = 0.30*H1 + 0.35*H2 + 0.25*H3 + 0.10*H4` → 0–10.

### Universal scoring anchors (apply per head)

| Score | Meaning |
|---|---|
| 9–10 | Exceptionally favorable; strong concrete evidence |
| 7–8 | Favorable; clear reasoning from evidence |
| 5–6 | Moderate / mixed / no real evidence either way (use exactly 5 when nothing in article or site supports either direction) |
| 3–4 | Unfavorable signals present |
| 0–2 | Severely unfavorable; hard blocker for this dimension |

Rules:
1. Every category needs a one-sentence `evidence` string citing something
   CONCRETE from the article text or site text (quote fragments, name pages
   seen like "site:/pricing", "article: led by a16z"). Never invent sources;
   if you have nothing, write "no direct evidence found" and score 5 unless a
   related signal justifies deviation (explain in evidence).
2. Categories marked **(inv)** are inverse-burden items: MORE burden = LOWER
   score. You always score so that higher = better agency opportunity.
3. Score heads independently; do not average mentally before writing.

## Layer 2 — Pillars & Categories (52)

Within-pillar weights are equal (documented default; re-weightable later).
Pillar weight shown after pillar name. Bonus categories form pillar P9.

**P1 Build Feasibility — 20%**
1. Commodity-stack maturity (no research-grade tech needed)
2. Foundation-model/API substitutability for core R&D
3. Minimal sellable scope (size of partial-functionality MVP)
4. Client-system integration complexity (inv)
5. Data accessibility (public/commodity vs proprietary-required)
6. Talent rarity required (inv)
7. Time-to-first-sellable-build (inv)

**P2 Agency Delivery Model Fit — 15%**
8. Discrete project deliverability
9. Productized-package potential (fixed-scope offer)
10. Retainer/recurring-service potential
11. Build-once-resell-many (white-label reuse across clients)
12. Per-client customization burden (inv)
13. Ongoing ops/support burden (inv)
14. Low client-side dependency (client doesn't need big internal team)

**P3 High-Ticket Revenue Potential — 18%**
15. Anchors to measurable revenue/cost impact
16. Comparable agency/consulting price points exist ≥$25k
17. Budget-line availability at target buyers
18. Deal-size ceiling ($50k–$250k+ engagements plausible)
19. Upsell/expansion surface per account
20. Economic buyer seniority (reachable, not C-suite-only) — penalty if too senior (inv)
21. Sales-cycle length (inv)

**P4 Market Demand Signals — 12%**
22. Lead-investor caliber (top-tier fund = validated demand)
23. Round size as demand proxy
24. Category heat/trend momentum
25. Competitor presence (validates market, penalized if saturated)
26. On-site monetization proof (pricing page, case studies, customer logos)
27. Target-buyer accessibility to a small agency (SMB/mid-market reachability)

**P5 Technical Barrier (Moat-Inverse) — 10%**
28. Deep IP/R&D requirement (inv)
29. Hardware/robotics/specialized-infrastructure dependency (inv)
30. Proprietary-data moat requirement (inv)
31. Network-effects dependency (inv)
32. Certification/licensing requirements (inv)
33. Scale threshold for product viability (inv)

**P6 Risk & Liability Burden — 10%**
34. Regulatory exposure (HIPAA/FINRA/GDPR-heavy) (inv)
35. Data-sensitivity of processed data (inv)
36. Error stakes (wrong output = catastrophe) (inv)
37. Security liability exposure (inv)
38. ROI provability (agency can demonstrate results)
39. Reputation-damage risk on failure (inv)

**P7 Niche Accessibility — 8%**
40. ICP findability via outbound (lists, directories, associations)
41. Geographic constraint severity (inv)
42. Localization/language barrier (inv)
43. Domain-expertise barrier (inv)
44. Incumbent-contract lock-in at buyers (inv)

**P8 Durability of Opportunity — 7%**
45. Platform risk (a foundation-model feature kills it) (inv)
46. Commoditization speed (inv)
47. Repeat/ongoing purchase potential
48. Cross-industry portability of the service offer
49. Margin sustainability under copycat competition
50. Lifecycle position (emerging > mature > declining)

**P9 Bonus Signals — 5%**
51. Storytelling/demo-ability (service is demoable in a sales call)
52. Reference-customer availability (funded startups + peers are warm leads)

## Layer 3 — Archetype Attention Profiles

Assign EXACTLY ONE archetype:

| Key | Archetype | Pillar multipliers |
|---|---|---|
| ai_infra_devtools | AI infrastructure / devtools | P1×1.3, P5×1.3, P3×0.9 |
| vertical_ai_saas | Vertical AI/SaaS app | neutral (all ×1.0) |
| fintech_regtech | Fintech / regtech | P6×1.4, P5×1.2, P2×0.9 |
| healthtech_bio | Healthtech / bio | P6×1.5, P7×0.9 |
| sales_marketing_cx | Sales / marketing / CX tech | P2×1.2, P3×1.1 |
| other | Other / unclear | neutral |

Guidance: pick by what the PRODUCT does for users (not by funding story).
Developer-facing tooling → ai_infra_devtools. Industry-specific business app
(legal, real estate, logistics, retail…) → vertical_ai_saas. Money movement/
compliance → fintech_regtech. Clinical/biotech/diagnostics → healthtech_bio.
CRM/outbound/support/marketing automation → sales_marketing_cx.

## Layer 4 — Hard Gates

Apply gates as multipliers on the final total; record rationale for each gate
evaluated (applied true/false):

- **G1** Physical product/hardware manufacturing required → ×0.05
- **G2** License the agency can't realistically hold (bank/broker-dealer/
  medical-device class) → ×0.15
- **G3** Deep-science risk (biotech wet-lab, fusion, chips) → ×0.10
- **G4** Pure consumer B2C play → ×0.25
- **G5** No working website / parked-defunct domain → ×0.20 (+ confidence=low)

Notes: `js_only` sites are NOT G5 (evaluate from article + whatever meta text
exists; set confidence=low). Companies whose article listed NO website get G5.
Multiple applicable gates MULTIPLY (rare). A hardware-adjacent software play
(e.g., drone analytics software) is not automatically G1 — G1 requires the
agency to physically manufacture/specialized-hardware-deploy to deliver.

## Output Schema (data/evals/<slug>.json)

```json
{
  "slug": "<article slug>",
  "company": "<name>",
  "domain": "<domain or null>",
  "archetype": "<key>",
  "archetype_rationale": "one sentence",
  "confidence": "high|medium|low",
  "gates": [
    {"gate": "G1", "applied": false, "rationale": "..."},
    {"gate": "G2", "applied": false, "rationale": "..."},
    {"gate": "G3", "applied": false, "rationale": "..."},
    {"gate": "G4", "applied": false, "rationale": "..."},
    {"gate": "G5", "applied": false, "rationale": "..."}
  ],
  "categories": {
    "1": {"h1": 7, "h2": 6, "h3": 7, "h4": 8, "evidence": "..."},
    ... all keys "1".."52" ...
  },
  "agency_play": {
    "build_scope": "which partial functionality an agency builds",
    "packaging": "how it is packaged/productized as a service",
    "pricing": "suggested engagement pricing + structure",
    "first_clients": "who to sell to first and why"
  },
  "sources_read": ["article__<slug>.txt", "site__<domain>__home.txt"]
}
```

All four head scores are integers 0–10. Evidence ≤ 200 chars. Do not add
other top-level keys.
