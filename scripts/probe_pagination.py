"""One-off probe: inspect pagination markup on a cached tag page."""

import sys

from scanner.httpcache import load_cached


def main(page: int) -> None:
    url = "https://www.thesaasnews.com/tag/seed-round/"
    if page != 1:
        url = f"https://www.thesaasnews.com/tag/seed-round/page/{page}/"
    resp = load_cached(url)
    text = resp.text
    print("url:", url)
    for marker in ["older", "Load More", "page/2", "load-more"]:
        idx = text.find(marker)
        while idx != -1:
            snippet = text[max(0, idx - 300) : idx + 400]
            print(f"--- {marker!r} @ {idx} ---")
            print(snippet.replace("\n", " ")[:700])
            nxt = text.find(marker, idx + len(marker))
            if nxt == idx or nxt - idx < len(marker):
                break
            idx = text.find(marker, idx + len(marker))
            # only show first two occurrences per marker
            break


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
