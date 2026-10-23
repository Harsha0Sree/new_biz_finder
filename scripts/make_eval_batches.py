"""Partition unique companies into evaluator batch files."""

from __future__ import annotations

import sys

from scanner.paths import COMPANIES, EVAL_BATCHES, SITES, TEXT
from scanner.storage import read_json, write_json

OUT_DIR = EVAL_BATCHES


def site_files(domain: str | None) -> list[str]:
    if not domain:
        return []
    return sorted(
        p.name for p in TEXT.glob(f"site__{domain}__*.txt")
    )


def main() -> None:
    batch_size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 8
    companies = read_json(COMPANIES)
    sites = read_json(SITES)["sites"]
    uniq = [c for c in companies if not c.get("duplicate_of_previous")]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("batch_*.json"):
        old.unlink()
    batches = []
    for i in range(0, len(uniq), batch_size):
        chunk = uniq[i : i + batch_size]
        items = []
        for c in chunk:
            items.append(
                {
                    "slug": c["slug"],
                    "company": c["company"],
                    "domain": c["domain"],
                    "article_text": f"data/cache/text/article__{c['slug']}.txt",
                    "site_texts": site_files(c["domain"]),
                    "site_status": sites.get(c["domain"], {}).get("status", "none"),
                    "funding": {
                        "raised_raw": c["raised_raw"],
                        "usd_equivalent": c["usd_equivalent"],
                        "lead_investor": c["lead_investor"],
                        "additional_investors": c["additional_investors"],
                        "software_category": c["software_category"],
                        "round_field": c["round_field"],
                    },
                }
            )
        path = OUT_DIR / f"batch_{len(batches):03d}.json"
        write_json(path, items)
        batches.append(path.name)
    print(f"wrote {len(batches)} batches x ~{batch_size} companies to {OUT_DIR}")


if __name__ == "__main__":
    main()
