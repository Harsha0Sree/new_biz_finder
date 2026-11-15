"""Product Hunt source adapter.

Pulls every Product Hunt post from calendar year 2026 with more than 500
upvotes through the official GraphQL API and turns the qualifying posts into
company records.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

from scanner.env import load_dotenv
from scanner.models import Company
from scanner.paths import source_articles
from scanner.sources.base import (
    domain_of,
    normalize_name,
    unique_slug,
    write_articles,
    write_companies,
    write_index,
)
from scanner.storage import read_json

load_dotenv()

SOURCE = "producthunt"
QUALIFICATION = "Product Hunt post with more than 500 upvotes in 2026"

_GRAPHQL_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
_POSTS_QUERY = """query Posts($first: Int!, $after: String, $order: PostsOrder!, $postedAfter: DateTime!, $postedBefore: DateTime!) {
  posts(first: $first, after: $after, order: $order, postedAfter: $postedAfter, postedBefore: $postedBefore) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        tagline
        description
        url
        website
        votesCount
        commentsCount
        createdAt
        featuredAt
        topics(first: 5) { edges { node { name slug } } }
        makers { id name }
      }
    }
  }
}"""
_POSTS_VARIABLES: dict[str, Any] = {
    "first": 100,
    "after": None,
    "order": "VOTES",
    "postedAfter": "2026-01-01T00:00:00Z",
    "postedBefore": "2027-01-01T00:00:00Z",
}
_YEAR = "2026"
_VOTE_CUTOFF = 500


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """POST one GraphQL query to the Product Hunt API and return the response."""
    response = httpx.post(
        _GRAPHQL_ENDPOINT,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _first_sentence(text: str) -> str:
    """First sentence of a text, or the cleaned text when it has no sentence end."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0].strip()
    return sentence.rstrip(".!?").strip()


def _to_article(node: dict[str, Any]) -> dict[str, Any]:
    """Flatten one GraphQL post node into the raw article shape extract consumes."""
    topics: list[dict[str, str]] = []
    topic_edges = (node.get("topics") or {}).get("edges") or []
    for edge in topic_edges:
        topic = edge.get("node") or {}
        if topic.get("name"):
            topics.append({"name": str(topic["name"]), "slug": str(topic.get("slug") or "")})
    return {
        "id": str(node.get("id") or ""),
        "name": str(node.get("name") or ""),
        "tagline": str(node.get("tagline") or ""),
        "description": str(node.get("description") or ""),
        "url": str(node.get("url") or ""),
        "website": str(node.get("website") or ""),
        "votesCount": int(node.get("votesCount") or 0),
        "createdAt": str(node.get("createdAt") or ""),
        "topics": topics,
    }


def _fetch_qualifying_articles(token: str) -> list[dict[str, Any]]:
    """Return 2026 posts ordered by votes that cleared the 500-upvote cut."""
    collected: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        variables: dict[str, Any] = dict(_POSTS_VARIABLES)
        variables["after"] = after
        payload = _graphql(token, _POSTS_QUERY, variables)
        posts = ((payload or {}).get("data") or {}).get("posts") or {}
        page_info = posts.get("pageInfo") or {}
        edges = posts.get("edges") or []
        nodes = [
            edge["node"]
            for edge in edges
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
        ]
        if not nodes:
            break
        collected.extend(
            _to_article(node) for node in nodes if int(node.get("votesCount") or 0) > _VOTE_CUTOFF
        )
        votes = [int(node.get("votesCount") or 0) for node in nodes]
        if not page_info.get("hasNextPage") or min(votes) <= _VOTE_CUTOFF:
            break
        after = page_info.get("endCursor")
    return collected


def crawl(*, force: bool = False) -> dict[str, Any]:
    """Fetch the 2026 qualifying Product Hunt posts and write the crawl artifacts.

    Writes `articles.json` with the qualifying raw posts and `index.json` with
    the crawl summary, and returns that index. Returns an empty dict when
    `PRODUCTHUNT_TOKEN` is missing, without writing anything.
    """
    token = (os.environ.get("PRODUCTHUNT_TOKEN") or "").strip()
    if not token:
        print(
            "PRODUCTHUNT_TOKEN is not set; create a Product Hunt API token at https://www.producthunt.com/v2/api"
        )
        return {}
    articles = _fetch_qualifying_articles(token)
    index = {
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "year": _YEAR,
        "qualifying": len(articles),
    }
    write_articles(SOURCE, articles)
    write_index(SOURCE, index)
    return index


def _company_from_article(article: dict[str, Any], taken: set[str]) -> Company:
    """Map one saved Product Hunt post onto a Company record."""
    name = str(article.get("name") or "")
    website = str(article.get("website") or article.get("url") or "")
    source_url = str(article.get("url") or "")
    description = str(article.get("tagline") or "").strip()
    if not description:
        description = _first_sentence(str(article.get("description") or ""))
    software_category = ""
    topics = article.get("topics") or []
    if isinstance(topics, list) and topics:
        first = topics[0] or {}
        if isinstance(first, dict):
            software_category = str(first.get("name") or "")
    return {
        "slug": unique_slug(name, "producthunt", taken),
        "source": SOURCE,
        "qualification": QUALIFICATION,
        "article_url": source_url,
        "source_url": source_url,
        "title": name,
        "date": str(article.get("createdAt") or "")[:10],
        "company": name,
        "normalized_name": normalize_name(name),
        "domain": domain_of(website),
        "website": website,
        "description": description,
        "raised_raw": "",
        "usd_equivalent": 0.0,
        "round_field": "",
        "round_source": "",
        "funding_date": "",
        "lead_investor": "",
        "additional_investors": "",
        "software_category": software_category,
        "batch": "",
        "upvotes": int(article.get("votesCount") or 0),
        "employee_range": "",
        "work_type": "",
        "location": "",
        "flags": ["no_website"] if not article.get("website") else [],
        "duplicate_of_previous": False,
    }


def extract() -> list[Company]:
    """Turn the saved Product Hunt articles into company records.

    Reads `articles.json`, maps every raw post onto a Company record, writes
    `companies.json`, and returns the list of records.
    """
    payload = read_json(source_articles(SOURCE))
    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        return []
    companies: list[Company] = []
    taken: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        companies.append(_company_from_article(article, taken))
    write_companies(SOURCE, companies)
    return companies


if __name__ == "__main__":
    _index = crawl()
    if _index:
        _companies = extract()
        print(f"producthunt: wrote {len(_companies)} company records")
