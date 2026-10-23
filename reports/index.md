# Reports

Two evaluation passes are produced by this repository:

- [Master ranking](master-ranking.md) — 67 companies scored on the 52-category deterministic framework.
- [LLM quick ranking](llm_opportunity_ranking.md) — faster, single-score pass; error records are listed separately and excluded from the ranking.

## Data status

- Deep evaluations: 67
- LLM evaluations: 5 successful, 47 errored

Regenerate with `uv run python -m scanner.compute && uv run python -m scanner.reports` for the deep pass, or `uv run python main.py --aggregate-only` for the LLM pass.
