"""One-off probe: post-card markup + last-page boundary."""

import re

from scanner.httpcache import load_cached
from bs4 import BeautifulSoup


def main() -> None:
    resp = load_cached("https://www.thesaasnews.com/tag/seed-round/")
    soup = BeautifulSoup(resp.text, "lxml")
    # find the container holding post cards
    cards = [a for a in soup.find_all("a", href=True) if re.match(r"^/news/[^/]+/$", a["href"])]
    print("card anchors:", len(cards))
    if cards:
        a = cards[0]
        # walk up to the card root
        node = a
        for _ in range(6):
            if node.parent and node.parent.name != "main" and "gh-post" not in " ".join(
                node.get("class") or []
            ):
                node = node.parent
            else:
                break
        # print the outermost wrapper of the first two cards
        wrappers = soup.select("main div")
        big = [d for d in wrappers if d.find("a", href=re.compile(r"^/news/"))]
        card_root = None
        for d in big:
            cls = " ".join(d.get("class") or [])
            if "gh-post" in cls:
                card_root = d
                break
        if card_root is not None:
            print("--- card root class ---", card_root.get("class"))
            print(str(card_root)[:1200])
    # date nodes
    times = soup.find_all("time")
    print("time nodes:", [(t.get("datetime"), t.get_text(strip=True)) for t in times[:3]])


if __name__ == "__main__":
    main()
