"""One-off probe: inspect tag-page structure for the index crawler."""


from bs4 import BeautifulSoup

from scanner.httpcache import load_cached


def main(page: int) -> None:
    url = "https://www.thesaasnews.com/tag/seed-round/"
    if page != 1:
        url = f"https://www.thesaasnews.com/tag/seed-round/page/{page}/"
    resp = load_cached(url)
    print("url:", url, "status:", resp.status if resp else None)
    soup = BeautifulSoup(resp.text, "lxml")
    # find all internal links that are not /news/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = " ".join(a.get_text(" ", strip=True))[:40]
        if "/news/" in href:
            continue
        if "seed-round" in href or "page" in href:
            print(f"{href!r:70} {text!r}")
    print("=== scripts/classes sample ===")
    body_classes = soup.find("body").get("class") if soup.find("body") else None
    print("body class:", body_classes)
    main_el = soup.find("main") or soup.find(id="main")
    print("has <main>:", bool(main_el))
    if main_el:
        kids = [c.name for c in main_el.find_all(recursive=False)]
        print("main children:", kids[:20])
    # look for section headers with 'Posts' or nav
    for nav in soup.find_all("nav"):
        cls = nav.get("class")
        print("<nav>", cls, str(nav)[:200].replace("\n", " "))


if __name__ == "__main__":
    main(int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 1)
