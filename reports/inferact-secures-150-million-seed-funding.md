# Inferact — Agency-Opportunity Report

**Rank:** #14 | **Total:** 61.33/100 | **Tier:** C | **Confidence:** high

## Funding & Identity
- Article: https://www.thesaasnews.com/news/inferact-secures-150-million-seed-funding/
- Raised: $150.0M (~$150,000,000 USD-equiv)
- Software category: AI / Machine Learning Inference
- Lead investor: Andreessen Horowitz, Lightspeed Venture Partners
- Website: https://inferact.ai/ (domain: inferact.ai)
- Archetype: `ai_infra_devtools` — Commercializes vLLM, the open-source LLM inference engine - developer infrastructure.

## Hard Gates
- No gates applied.

## Category Scores (0–10 per head)
| # | Category | H1 Build | H2 Sell | H3 Buy | H4 Risk | Combined | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | Commodity-stack maturity | 7 | 6 | 6 | 7 | **6.4** | article: vLLM is open source - deployment/optimization uses commodity stack |
| 2 | FM/API substitutability | 8 | 7 | 7 | 7 | **7.3** | inference serving fully achievable with OSS vllm/sglang; no proprietary R&D needed |
| 3 | Minimal sellable scope | 7 | 7 | 7 | 7 | **7.0** | 'serve one model cheaply on your GPU fleet' is a small sellable scope |
| 4 | Client-system integration complexity (inv) | 4 | 4 | 5 | 5 | **4.3** | GPU cluster/K8s integration complexity real but standard |
| 5 | Data accessibility | 7 | 7 | 7 | 7 | **7.0** | open weights + client models; no external data dependency |
| 6 | Talent rarity required (inv) | 5 | 5 | 5 | 6 | **5.1** | MLSys/GPU engineers scarce-ish but hireable |
| 7 | Time-to-first-sellable-build (inv) | 5 | 6 | 6 | 6 | **5.7** | weeks-months to first optimized deployment |
| 8 | Discrete project deliverability | 6 | 6 | 6 | 6 | **6.0** | discrete deployment/optimization projects |
| 9 | Productized-package potential | 6 | 7 | 6 | 6 | **6.3** | 'self-hosted LLM stack' fixed-scope package viable |
| 10 | Retainer/recurring potential | 7 | 7 | 7 | 7 | **7.0** | inference ops/SLO management = natural retainer |
| 11 | Build-once-resell-many | 7 | 7 | 7 | 7 | **7.0** | Terraform/helm templates reusable across clients |
| 12 | Per-client customization burden (inv) | 5 | 5 | 5 | 5 | **5.0** | hardware/model variance per client moderate |
| 13 | Ongoing ops burden (inv) | 5 | 5 | 5 | 5 | **5.0** | 24/7 GPU serving ops burden real |
| 14 | Low client-side dependency | 5 | 5 | 5 | 5 | **5.0** | client needs platform engineer, not ML team |
| 15 | Anchors to measurable impact | 8 | 8 | 8 | 8 | **8.0** | article mission 'cheaper and faster' inference = direct cost anchor |
| 16 | Comparable price points >=$25k | 7 | 7 | 7 | 7 | **7.0** | MLOps/infra consultancies bill $50k+ for LLM-serving builds |
| 17 | Budget-line availability | 6 | 6 | 7 | 6 | **6.2** | cloud/compute budget lines well-funded |
| 18 | Deal-size ceiling | 6 | 6 | 7 | 6 | **6.2** | $50-150k builds + ongoing ops plausible |
| 19 | Upsell/expansion surface | 6 | 6 | 7 | 6 | **6.2** | every new model/product = re-engagement |
| 20 | Economic buyer seniority (inv) | 6 | 6 | 6 | 6 | **6.0** | VP Eng/platform leads reachable |
| 21 | Sales-cycle length (inv) | 6 | 6 | 6 | 6 | **6.0** | infra projects close moderately fast |
| 22 | Lead-investor caliber | 10 | 10 | 10 | 9 | **9.9** | article: a16z + Lightspeed co-led; Sequoia, Altimeter, Redpoint |
| 23 | Round size as demand proxy | 9 | 9 | 9 | 9 | **9.0** | article: $150M seed at $800M valuation |
| 24 | Category heat/momentum | 8 | 8 | 8 | 8 | **8.0** | inference-cost optimization is a top enterprise pain 2026 |
| 25 | Competitor presence | 5 | 5 | 5 | 5 | **5.0** | crowded inference market validates demand |
| 26 | On-site monetization proof | 3 | 3 | 4 | 5 | **3.5** | site thin; OSS repo is the real proof |
| 27 | Buyer accessibility to small agency | 5 | 5 | 5 | 5 | **5.0** | enterprises self-hosting LLMs findable |
| 28 | Deep IP/R&D requirement (inv) | 5 | 5 | 5 | 5 | **5.0** | vLLM itself open - moat is operational scale |
| 29 | Hardware/infra dependency (inv) | 6 | 6 | 6 | 6 | **6.0** | GPU hardware dependency at clients, managed remotely |
| 30 | Proprietary-data moat (inv) | 7 | 7 | 7 | 7 | **7.0** | open source - no data moat blocking agencies |
| 31 | Network-effects dependency (inv) | 5 | 5 | 5 | 5 | **5.0** | no direct evidence found |
| 32 | Certification/licensing (inv) | 6 | 6 | 6 | 6 | **6.0** | no certifications needed |
| 33 | Scale threshold viability (inv) | 6 | 6 | 6 | 6 | **6.0** | works per-client at any scale |
| 34 | Regulatory exposure (inv) | 6 | 6 | 6 | 6 | **6.0** | low regulatory exposure |
| 35 | Data sensitivity (inv) | 5 | 5 | 5 | 5 | **5.0** | client prompts flow through; standard care needed |
| 36 | Error stakes (inv) | 6 | 6 | 6 | 6 | **6.0** | outages costly not catastrophic |
| 37 | Security liability (inv) | 5 | 5 | 5 | 5 | **5.0** | serving stack security standard |
| 38 | ROI provability | 8 | 8 | 8 | 7 | **7.9** | tokens/sec + $/token metrics provable instantly |
| 39 | Reputation-damage risk (inv) | 6 | 6 | 6 | 6 | **6.0** | moderate |
| 40 | ICP findability via outbound | 6 | 6 | 6 | 6 | **6.0** | self-hosting enterprises identifiable via job posts/oss usage |
| 41 | Geographic constraint (inv) | 7 | 7 | 7 | 7 | **7.0** | remote-deliverable global market |
| 42 | Localization barrier (inv) | 7 | 7 | 7 | 7 | **7.0** | English-first |
| 43 | Domain-expertise barrier (inv) | 4 | 4 | 4 | 5 | **4.1** | deep GPU/systems expertise barrier |
| 44 | Incumbent lock-in (inv) | 5 | 5 | 5 | 5 | **5.0** | managed platforms (Bedrock etc.) compete for the same spend |
| 45 | Platform risk (inv) | 5 | 5 | 5 | 5 | **5.0** | serving layer persists regardless of model winner |
| 46 | Commoditization speed (inv) | 4 | 4 | 4 | 5 | **4.1** | OSS tooling commoditizes fast; services persist |
| 47 | Repeat purchase potential | 7 | 7 | 7 | 7 | **7.0** | model churn forces continuous upgrades |
| 48 | Cross-industry portability | 6 | 6 | 7 | 6 | **6.2** | any industry hosting LLMs |
| 49 | Margin sustainability vs copycats | 4 | 4 | 4 | 5 | **4.1** | many MSPs can learn vLLM; margin pressure |
| 50 | Lifecycle position | 7 | 7 | 7 | 7 | **7.0** | inference-infrastructure wave mid-rise |
| 51 | Storytelling/demo-ability | 6 | 6 | 6 | 6 | **6.0** | latency/cost dashboards demo convincingly |
| 52 | Reference-customer availability | 7 | 7 | 7 | 7 | **7.0** | vLLM community + funded adopters are warm leads |

## Pillar Rollup
| Pillar | Score /10 | Raw weight | Adjusted weight |
|---|---|---|---|
| P1. Build Feasibility | 6.1 | 0.260 | 0.232 |
| P2. Agency Delivery Model Fit | 5.9 | 0.150 | 0.134 |
| P3. High-Ticket Revenue Potential | 6.5 | 0.162 | 0.144 |
| P4. Market Demand Signals | 6.7 | 0.120 | 0.107 |
| P5. Technical Barrier (Moat-Inverse) | 5.8 | 0.130 | 0.116 |
| P6. Risk & Liability Burden | 6.0 | 0.100 | 0.089 |
| P7. Niche Accessibility | 5.8 | 0.080 | 0.071 |
| P8. Durability of Opportunity | 5.6 | 0.070 | 0.062 |
| P9. Bonus Signals | 6.5 | 0.050 | 0.045 |

**Gate mask:** 1.0 (applied: none)

## The Agency Play
- **What to build:** Partial functionality: private LLM-serving stacks for mid-market firms using OSS vLLM - model selection, quantization, autoscaling, cost dashboards - Inferact's exact domain without building the engine.
- **How to package it:** Fixed-scope 'Private GPT in 30 days' deployment package; inference-cost-audit upsell; managed-SLO retainer.
- **Suggested pricing:** Deployment $40-80k; audit $10-20k; retainer $5-12k/mo per environment.
- **First clients:** Series B+ SaaS and fintechs whose per-seat API bills exploded and whose lawyers want data residency.

---
*Scores: H1 Builder 30% / H2 Seller 35% / H3 Buyer 25% / H4 Risk(inverse, higher=safer) 10%. (inv) categories score higher when the burden is lower. Framework v1 - see SCORING_SPEC.md.*