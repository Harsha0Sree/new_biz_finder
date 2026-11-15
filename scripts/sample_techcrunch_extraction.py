"""Sample the TechCrunch extractor and print what it decided.

Runs the classifier over a random slice of the 2026 articles and prints the
article title, the verdict and the resolved company so the result can be read
by eye. Use it to judge precision on a real slice of the corpus.

    python scripts/sample_techcrunch_extraction.py --sample 60 --model <id>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.env import load_dotenv
from scanner.paths import source_articles
from scanner.sources.techcrunch import classify
from scanner.storage import read_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--model", default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--show-links", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    payload = read_json(source_articles("techcrunch")) or {}
    articles = payload.get("articles") or []
    random.seed(args.seed)
    picks = random.sample(articles, min(args.sample, len(articles)))

    import httpx

    base_url = "https://integrate.api.nvidia.com/v1"
    api_key = ""
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("NVIDIA_API_KEY="):
            api_key = line.split("=", 1)[1].strip()
    model = args.model or "nvidia/nemotron-3.5-lightning-30b-a3b"

    counts: dict[str, int] = {}
    with httpx.Client(timeout=120.0) as client:
        for article in picks:
            verdict = classify(article, client, base_url, api_key, model)
            key = verdict.get("verdict", "?")
            counts[key] = counts.get(key, 0) + 1
            names = ", ".join(
                f"{c.get('name')}[{c.get('domain') or '-'}]" for c in verdict.get("companies") or []
            )
            print("=" * 100)
            print(f"TITLE    {article.get('title')}")
            print(f"VERDICT  {key} | {names}")
            print(f"REASON   {verdict.get('reason')}")
            if verdict.get("rejected"):
                print(f"REJECTED {verdict['rejected']}")
            if args.show_links:
                for link in (article.get("links") or [])[:8]:
                    print(f"  LINK   {link.get('name')!r} -> {link.get('domain')} lead={link.get('lead')}")
    print("=" * 100)
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
