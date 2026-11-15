"""TechCrunch adapter: every company named in a 2026 TechCrunch article.

Two stages. The crawl pulls every 2026 post from the WordPress REST API and
keeps the title, the body opening and the outbound links. The extraction
names the company each article is about. A deterministic pass proposes
candidate name and domain pairs from the article's own links, then one short
LLM call per article picks the pair and rules on whether the article is about
a company at all. Every article keeps a verdict on disk, so a missed article
shows up as a gap instead of disappearing.

Funding facts never gate inclusion here. A company named in a 2026 article
enters the corpus whether or not the article reports an amount.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from bs4 import BeautifulSoup

from scanner.amounts import parse_raise_amount
from scanner.env import load_dotenv
from scanner.llm import extract_json_object
from scanner.models import Company
from scanner.paths import SOURCE_TECHCRUNCH, source_articles, source_index
from scanner.sources.base import (
    domain_of,
    is_company_host,
    normalize_name,
    slugify,
    unique_slug,
    write_articles,
    write_companies,
    write_index,
)
from scanner.storage import read_json, write_json

SOURCE = SOURCE_TECHCRUNCH
QUALIFICATION = "every company named in a 2026 TechCrunch article"

API_ROOT = "https://techcrunch.com/wp-json/wp/v2"
POSTS_URL = f"{API_ROOT}/posts"
CATEGORIES_URL = f"{API_ROOT}/categories"
YEAR = 2026
PER_PAGE = 100
BODY_LIMIT = 6_000
LLM_BODY_LIMIT = 1_100
MAX_CANDIDATES = 30
MAX_COMPANY_WORDS = 6

EXTRACTION_SYSTEM = (
    "You read TechCrunch articles and identify the company each one is about. "
    "You reply with one JSON object and nothing else."
)

EXTRACTION_TEMPLATE = """Article title: {title}

Article opening:
{body}

Links that appear in the article:
{candidates}

Reply with one JSON object and nothing else:
{{"companies": [{{"name": "<exact company name>", "candidate": <number or null>, "is_startup": true}}], "reason": "<short clause>"}}

- companies lists every startup or privately held company the article is mainly about.
  It is empty when the article has no company subject.
- is_startup is false for a public corporation, a division or product of a bigger
  company, a media or entertainment brand, an investment firm or fund, and a
  government body.
- candidate is the number of the link that is the company's own website, or null
  when no listed link is it.
- Never pick a link that points at a publication, a government site, a social
  network, a video, a document, or a different company's article.
- When the article profiles or lists several companies, list every one of them.
- Write each name exactly as the article writes it."""

COMPANY_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "to",
        "in",
        "on",
        "at",
        "by",
        "with",
        "its",
        "it",
        "labs",
        "lab",
        "ai",
        "app",
        "apps",
        "inc",
        "llc",
        "ltd",
        "group",
        "company",
        "startup",
        "startups",
        "tech",
        "technology",
        "systems",
        "software",
        "platform",
        "open",
        "noise",
        "london",
        "new",
        "y",
        "combinator",
        "y combinator",
    }
)


def _strip_html(raw: str) -> str:
    """Plain text from a fragment of HTML."""
    soup = BeautifulSoup(raw or "", "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def _plain_name(raw: str) -> str:
    """Anchor text cleaned into a display name."""
    text = html.unescape(_strip_html(raw)).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,.;:!?'\"()[]")


def _looks_like_company_name(name: str) -> bool:
    """Cheap shape test for a name that could belong to a company."""
    if not name or len(name) > 60:
        return False
    words = name.split()
    if not 1 <= len(words) <= MAX_COMPANY_WORDS:
        return False
    if "," in name:
        return False
    if not any(ch.isalpha() for ch in name):
        return False
    if re.match(r"^\d", name):
        return False
    if re.search(r"\b\d{2,}\b", name):
        return False
    if name.lower() in COMPANY_STOPWORDS:
        return False
    return True


def _name_tokens(name: str) -> set[str]:
    return {
        token
        for token in normalize_name(name).split()
        if len(token) >= 3 and token not in COMPANY_STOPWORDS
    }


def _domain_carries_name(name: str, domain: str) -> bool:
    """True when the domain looks like it belongs to the named company."""
    label = domain.split(".")[0].lower().replace("-", "")
    if not label:
        return False
    compact = label
    for token in _name_tokens(name):
        if token in compact:
            return True
    return False


def _names_compatible(left: str, right: str) -> bool:
    """True when two names could be the same company."""
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


def _category_names() -> dict[str, str]:
    """Map of TechCrunch category id to name."""
    response = httpx.get(
        CATEGORIES_URL,
        params={"per_page": 100},
        headers={"User-Agent": "new-biz-finder/1.0"},
        timeout=30.0,
    )
    response.raise_for_status()
    return {
        str(item["id"]): str(item["name"])
        for item in response.json()
        if isinstance(item, dict) and "id" in item
    }


def _fetch_posts(page: int) -> list[dict[str, Any]]:
    """One page of 2026 posts, oldest first."""
    response = httpx.get(
        POSTS_URL,
        params={
            "per_page": PER_PAGE,
            "page": page,
            "after": f"{YEAR}-01-01T00:00:00",
            "before": f"{YEAR + 1}-01-01T00:00:00",
            "orderby": "id",
            "order": "asc",
            "_fields": "id,date,link,title,excerpt,content,categories,yoast_head_json",
        },
        headers={"User-Agent": "new-biz-finder/1.0"},
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _expected_total() -> int:
    """The post count the API reports for the window."""
    response = httpx.get(
        POSTS_URL,
        params={
            "per_page": 1,
            "after": f"{YEAR}-01-01T00:00:00",
            "before": f"{YEAR + 1}-01-01T00:00:00",
        },
        headers={"User-Agent": "new-biz-finder/1.0"},
        timeout=30.0,
    )
    response.raise_for_status()
    return int(response.headers.get("x-wp-total", 0))


def _article_from_post(
    post: dict[str, Any], category_names: dict[str, str]
) -> dict[str, Any]:
    """Turn one API post into the article record the extractor works on."""
    content = (post.get("content") or {}).get("rendered") or ""
    soup = BeautifulSoup(content, "html.parser")
    paragraphs = soup.find_all("p")
    lead_text = ""
    lead_links: set[int] = set()
    for index, paragraph in enumerate(paragraphs[:1]):
        lead_text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
        lead_links = {id(anchor) for anchor in paragraph.find_all("a")}

    links: list[dict[str, Any]] = []
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        host = domain_of(href)
        if not host or not is_company_host(host):
            continue
        name = _plain_name(anchor.get_text(" ", strip=True))
        if not name:
            continue
        links.append(
            {
                "name": name,
                "domain": host,
                "href": href,
                "lead": id(anchor) in lead_links,
            }
        )

    meta = (post.get("yoast_head_json") or {}).get("description") or ""
    description = html.unescape(_strip_html(meta))[:400]
    if not description:
        description = _strip_html((post.get("excerpt") or {}).get("rendered") or "")[:400]

    return {
        "id": post.get("id"),
        "url": post.get("link"),
        "date": post.get("date"),
        "title": _plain_name((post.get("title") or {}).get("rendered") or ""),
        "description": description,
        "categories": [
            category_names.get(str(cid), str(cid))
            for cid in (post.get("categories") or [])
        ],
        "body": _strip_html(content)[:BODY_LIMIT],
        "links": links,
    }


def crawl(*, force: bool = False) -> dict[str, Any]:
    """Fetch every 2026 post and write index.json and articles.json."""
    if not force:
        existing = read_json(source_articles(SOURCE))
        if isinstance(existing, dict) and existing.get("articles"):
            return read_json(source_index(SOURCE)) or {}

    total_expected = _expected_total()
    category_names = _category_names()
    articles: list[dict[str, Any]] = []
    page = 1
    max_pages = total_expected // PER_PAGE + 5
    while page <= max_pages:
        posts = _fetch_posts(page)
        if not posts:
            break
        for post in posts:
            articles.append(_article_from_post(post, category_names))
        print(f"  techcrunch page {page}: {len(articles)} articles", flush=True)
        if len(posts) < PER_PAGE:
            break
        page += 1

    index = {
        "source": SOURCE,
        "year": YEAR,
        "api": POSTS_URL,
        "expected_total": total_expected,
        "fetched_total": len(articles),
        "pages": page,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_index(SOURCE, index)
    write_articles(SOURCE, articles)
    print(
        f"techcrunch: expected {total_expected} posts, fetched {len(articles)}",
        flush=True,
    )
    return index


def build_candidates(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Name and domain pairs the article's own links offer, in order."""
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for link in article.get("links") or []:
        name = str(link.get("name") or "")
        domain = str(link.get("domain") or "")
        if not name or not domain or not is_company_host(domain):
            continue
        key = (normalize_name(name), domain)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "name": name,
                "domain": domain,
                "href": link.get("href"),
                "lead": bool(link.get("lead")),
            }
        )
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def _prompt_for(article: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    lines = []
    for index, candidate in enumerate(candidates):
        lines.append(
            f"{index}. {candidate['name']} - {candidate['domain']}"
        )
    if not lines:
        lines.append("(no outbound links)")
    return EXTRACTION_TEMPLATE.format(
        title=article.get("title") or "",
        body=(article.get("body") or "")[:LLM_BODY_LIMIT],
        candidates="\n".join(lines),
    )


def _call_llm(
    prompt: str,
    client: httpx.Client,
    base_url: str,
    api_key: str,
    model: str,
    attempts: int = 6,
) -> tuple[dict[str, Any] | None, str]:
    """One extraction call. Returns the parsed object and the failure reason.

    The shared endpoint answers 429 under load, so a call is retried with a
    growing pause. A call that comes back without JSON is retried with a
    stricter instruction.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    reason = "no attempt made"
    for attempt in range(attempts):
        try:
            response = client.post(
                f"{base_url}/chat/completions", headers=headers, json=payload
            )
        except httpx.HTTPError as exc:
            reason = f"transport error: {type(exc).__name__}"
            time.sleep(min(20.0, 1.5 * (2**attempt)))
            continue
        if response.status_code == 429:
            reason = "HTTP 429"
            time.sleep(min(20.0, 2.0 * (2**attempt)))
            continue
        if response.status_code != 200:
            reason = f"HTTP {response.status_code}"
            break
        try:
            message = response.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            reason = "unreadable response body"
            break
        text = "\n".join(
            part
            for part in (message.get("content"), message.get("reasoning_content"))
            if part
        )
        parsed = extract_json_object(text)
        if isinstance(parsed, dict):
            return parsed, ""
        reason = "no JSON object in the answer"
        payload["messages"][1]["content"] = (
            prompt + "\n\nAnswer with the JSON object only. No prose."
        )
        time.sleep(1.0)
    return None, reason


def _match_key(text: str) -> str:
    """Lowercase, punctuation-free text for substring matching."""
    lowered = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", lowered).strip()


def _name_in_article(text: str, name: str) -> bool:
    """True when the named company actually appears in the given text."""
    target = _match_key(name)
    if not target:
        return False
    return target in _match_key(text)


def _resolve_domain(
    company: str,
    chosen_index: Any,
    candidates: list[dict[str, Any]],
) -> tuple[str | None, list[str]]:
    """Pick the domain for the named company from the article's own links.

    A domain that carries the company's own name is proof enough. Failing
    that, the anchor has to name the company and the link has to sit in the
    opening paragraph, which is where a publisher links the subject's site
    rather than a cited article.
    """
    flags: list[str] = []
    compatible = [
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if _names_compatible(company, candidate["name"])
    ]
    chosen: tuple[int, dict[str, Any]] | None = None
    if isinstance(chosen_index, int) and 0 <= chosen_index < len(candidates):
        candidate = candidates[chosen_index]
        if _names_compatible(company, candidate["name"]) or _domain_carries_name(
            company, candidate["domain"]
        ):
            chosen = (chosen_index, candidate)
    if chosen is None and compatible:
        named = [pair for pair in compatible if _domain_carries_name(company, pair[1]["domain"])]
        chosen = named[0] if named else compatible[0]
    if chosen is None:
        return None, flags

    domain = chosen[1]["domain"]
    if _domain_carries_name(company, domain):
        return domain, flags
    better = [
        pair for pair in compatible if _domain_carries_name(company, pair[1]["domain"])
    ]
    if better:
        return better[0][1]["domain"], flags
    if chosen[1].get("lead"):
        return domain, flags
    flags.append("domain_unverified")
    return None, flags


def _fallback_company(
    article: dict[str, Any], candidates: list[dict[str, Any]]
) -> tuple[str, str | None]:
    """Deterministic answer when the model call did not come back."""
    for candidate in candidates:
        if candidate.get("lead") and _looks_like_company_name(candidate["name"]):
            return candidate["name"], candidate["domain"]
    for candidate in candidates:
        if _looks_like_company_name(candidate["name"]):
            return candidate["name"], candidate["domain"]
    return "", None


def _named_companies(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """The list of company objects the model returned, whatever its shape."""
    raw = parsed.get("companies")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    single = parsed.get("company")
    if isinstance(single, str) and single.strip():
        return [
            {
                "name": single,
                "candidate": parsed.get("candidate"),
                "is_startup": parsed.get("is_company", True),
            }
        ]
    return []


def _judge_article(
    article: dict[str, Any],
    candidates: list[dict[str, Any]],
    parsed: dict[str, Any] | None,
) -> dict[str, Any]:
    """Turn a model answer plus the article into a verdict."""
    verdict: dict[str, Any] = {
        "verdict": "no_company",
        "reason": "",
        "companies": [],
        "method": "llm",
    }
    if not parsed:
        name, domain = _fallback_company(article, candidates)
        verdict.update(
            {
                "method": "deterministic_fallback",
                "verdict": "llm_unavailable",
                "reason": "model call failed; used the first link candidate",
            }
        )
        if name:
            verdict["companies"] = [{"name": name, "domain": domain or "", "flags": []}]
        else:
            verdict["verdict"] = "llm_unavailable_no_candidate"
        return verdict

    verdict["reason"] = str(parsed.get("reason") or "")
    named = _named_companies(parsed)
    if not named:
        verdict["verdict"] = "no_company_named"
        return verdict

    text = f"{article.get('title') or ''} {article.get('body') or ''}"
    resolved: list[dict[str, Any]] = []
    rejected: list[str] = []
    for item in named:
        name = _plain_name(str(item.get("name") or ""))
        if not name or name.upper() in {"NONE", "N/A", "NULL"}:
            rejected.append("no_name")
            continue
        if not item.get("is_startup", True):
            rejected.append(f"not_a_startup:{name}")
            continue
        if not _looks_like_company_name(name):
            rejected.append(f"name_not_a_company_name:{name}")
            continue
        if not _name_in_article(text, name):
            rejected.append(f"name_not_in_article:{name}")
            continue
        domain, flags = _resolve_domain(name, item.get("candidate"), candidates)
        resolved.append({"name": name, "domain": domain or "", "flags": flags})

    verdict["companies"] = resolved
    verdict["rejected"] = rejected
    verdict["verdict"] = "company_found" if resolved else "no_company_qualified"
    return verdict


def classify(
    article: dict[str, Any],
    client: httpx.Client,
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Name the company an article is about and record why."""
    candidates = build_candidates(article)
    parsed, error = _call_llm(
        _prompt_for(article, candidates), client, base_url, api_key, model
    )
    verdict = _judge_article(article, candidates, parsed)
    verdict["candidate_count"] = len(candidates)
    if error:
        verdict["llm_error"] = error
    return verdict


_TITLE_STAGE_RE = re.compile(
    r"\b(pre-seed|pre-series\s+a|seed\s+round|seed|series\s+[a-j]\b|angel\s+round)",
    re.IGNORECASE,
)


def _stage_from_title(title: str) -> str:
    """The round label the headline states, when it states one."""
    match = _TITLE_STAGE_RE.search(title)
    if not match:
        return ""
    label = re.sub(r"\s+", " ", match.group(1)).strip().lower()
    if label.startswith("pre-series"):
        return "Pre-Series A"
    if label.startswith("pre-seed"):
        return "Pre-Seed"
    if label.startswith("seed round") or label == "seed":
        return "Seed"
    if label.startswith("angel"):
        return "Angel"
    return label.title()


def _company_record(
    article: dict[str, Any], found: dict[str, Any], slug: str
) -> Company:
    """The corpus record for one company named in one article."""
    title = article.get("title") or ""
    amount, valuation = parse_raise_amount(title)
    shown = amount or valuation
    round_field = _stage_from_title(title)
    round_source = "title" if round_field else None
    body = article.get("body") or ""
    if not round_field:
        stage = _stage_from_body(body, found.get("name") or "")
        if stage:
            round_field = stage
            round_source = "article"
    if shown is None:
        body_amount, body_valuation = parse_raise_amount(body)
        shown = body_amount or body_valuation
    company = found.get("name") or ""
    domain = found.get("domain") or ""
    return {
        "slug": slug,
        "source": SOURCE,
        "qualification": QUALIFICATION,
        "article_url": article.get("url"),
        "source_url": article.get("url"),
        "title": title,
        "date": (article.get("date") or "")[:10],
        "company": company,
        "normalized_name": normalize_name(company),
        "domain": domain or None,
        "website": f"https://{domain}" if domain else None,
        "description": article.get("description") or "",
        "raised_raw": shown.raw_match if shown else "",
        "usd_equivalent": shown.usd_equivalent if shown else 0.0,
        "amount_source": "title" if amount else ("article" if shown else ""),
        "round_field": round_field,
        "round_source": round_source,
        "funding_date": (article.get("date") or "")[:10],
        "lead_investor": "",
        "additional_investors": "",
        "software_category": _category_of(article),
        "flags": list(found.get("flags") or []),
        "duplicate_of_previous": False,
    }


_STAGE_RE = re.compile(
    r"\b(pre-seed|seed round|seed funding|seed|series\s+[a-j]|series\s+\d|"
    r"pre-series\s+a|angel round|strategic investment)\b",
    re.IGNORECASE,
)


def _stage_from_body(body: str, company: str) -> str:
    """The round label the article body states, when it states one."""
    window = body[:1_200]
    match = _STAGE_RE.search(window)
    if not match:
        return ""
    label = match.group(1)
    if label.lower() == "seed round" or label.lower() == "seed funding":
        return "Seed"
    if label.lower() == "pre-seed":
        return "Pre-Seed"
    if label.lower() == "pre-series a":
        return "Pre-Series A"
    if label.lower() == "angel round":
        return "Angel"
    return label.title()


def _category_of(article: dict[str, Any]) -> str:
    """The TechCrunch category that best describes the article."""
    categories = [str(c) for c in (article.get("categories") or [])]
    for preferred in ("Startups", "Venture", "Fundraising", "Artificial Intelligence", "Apps"):
        for category in categories:
            if category.lower() == preferred.lower():
                return category
    return categories[0] if categories else ""


def extract(
    *,
    workers: int = 8,
    limit: int | None = None,
    force: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[Company]:
    """Name the company in every article and write the company records."""
    load_dotenv()
    payload = read_json(source_articles(SOURCE)) or {}
    articles = payload.get("articles") or []
    if not articles:
        raise FileNotFoundError(
            f"{source_articles(SOURCE)} has no articles. Run the crawl first."
        )
    if limit is not None:
        articles = articles[:limit]

    api_key = api_key or os.getenv("NVIDIA_API_KEY", "")
    base_url = (base_url or os.getenv("NVIDIA_BASE_URL") or
                "https://integrate.api.nvidia.com/v1").rstrip("/")
    model = (
        model
        or os.getenv("EXTRACTION_MODEL")
        or "nvidia/nemotron-3.5-lightning-30b-a3b"
    )
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set; the LLM tier cannot run.")

    pending = [
        article
        for article in articles
        if force or not (article.get("verdict") or {}).get("verdict")
    ]
    print(
        f"techcrunch: {len(articles)} articles, {len(pending)} to classify "
        f"(workers={workers}, model={model})",
        flush=True,
    )

    done = 0
    started = time.time()
    with httpx.Client(timeout=120.0) as client:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(
                    classify, article, client, base_url, api_key, model
                ): article
                for article in pending
            }
            for future in as_completed(futures):
                article = futures[future]
                try:
                    article["verdict"] = future.result()
                except Exception as exc:
                    article["verdict"] = {
                        "verdict": "error",
                        "reason": str(exc)[:200],
                        "company": "",
                        "domain": "",
                    }
                done += 1
                if done % 200 == 0 or done == len(pending):
                    elapsed = time.time() - started
                    rate = done / elapsed if elapsed else 0.0
                    print(
                        f"  {done}/{len(pending)} classified "
                        f"({rate:.1f}/s, {elapsed:.0f}s)",
                        flush=True,
                    )
                    write_articles(SOURCE, articles)

    records: list[Company] = []
    taken: set[str] = set()
    for article in articles:
        verdict = article.get("verdict") or {}
        for found in verdict.get("companies") or []:
            slug = unique_slug(str(found.get("name") or ""), SOURCE, taken)
            records.append(_company_record(article, found, slug))

    counts: dict[str, int] = {}
    for article in articles:
        key = str((article.get("verdict") or {}).get("verdict") or "unclassified")
        counts[key] = counts.get(key, 0) + 1
    index = read_json(source_index(SOURCE)) or {}
    index["verdicts"] = counts
    index["company_count"] = len(records)
    write_index(SOURCE, index)
    write_companies(SOURCE, records)
    print(f"techcrunch: {len(records)} company records", flush=True)
    print(f"techcrunch verdicts: {counts}", flush=True)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="TechCrunch source adapter")
    parser.add_argument("--crawl", action="store_true", help="Fetch the 2026 posts")
    parser.add_argument("--extract", action="store_true", help="Name the companies")
    parser.add_argument("--force", action="store_true", help="Reclassify every article")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    if not args.crawl and not args.extract:
        args.crawl = True
        args.extract = True
    if args.crawl:
        crawl(force=args.force)
    if args.extract:
        extract(
            workers=args.workers,
            limit=args.limit,
            force=args.force,
            model=args.model,
        )


if __name__ == "__main__":
    main()
