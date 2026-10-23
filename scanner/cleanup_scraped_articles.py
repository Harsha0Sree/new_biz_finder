"""Truncate cached article text after the Source field.

Removes author footers, newsletter prompts, "read more" cards, and unrelated
article teasers from every `data/cache/text/article__*.txt` file.
"""

from __future__ import annotations

from scanner.fetch_articles import clean_article_text
from scanner.paths import TEXT
from scanner.storage import write_text

TEXT_DIR = TEXT


def cleanup_all_article_texts() -> int:
    files = list(TEXT_DIR.glob("article__*.txt"))
    print(f"Cleaning {len(files)} cached article text files...")

    cleaned_count = 0
    for path in files:
        raw = path.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_article_text(raw)
        if cleaned != raw:
            write_text(path, cleaned)
            cleaned_count += 1

    print(f"Successfully cleaned {cleaned_count} / {len(files)} article text files.")
    return cleaned_count


if __name__ == "__main__":
    cleanup_all_article_texts()
