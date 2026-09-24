"""Clean up all existing data/cache/text/article__*.txt files.

Truncates every article strictly after the Source field (discarding author footer,
newsletter alerts, 'read more', and unrelated article cards).
"""

from __future__ import annotations

import glob
from pathlib import Path

from scanner.fetch_articles import clean_article_text

TEXT_DIR = Path("data/cache/text")


def cleanup_all_article_texts() -> int:
    files = list(TEXT_DIR.glob("article__*.txt"))
    print(f"Cleaning {len(files)} cached article text files...")

    cleaned_count = 0
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_article_text(raw)
        if cleaned != raw:
            f.write_text(cleaned, encoding="utf-8")
            cleaned_count += 1

    print(f"Successfully cleaned {cleaned_count} / {len(files)} article text files.")
    return cleaned_count


if __name__ == "__main__":
    cleanup_all_article_texts()
