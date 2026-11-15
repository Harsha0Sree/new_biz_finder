"""Step 3: fetch qualifying articles, parse Funding Details -> companies.

Writes data/articles_parsed.json (per-article facts, resumable) and
data/companies.json (deduped by normalized company name + domain).
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from scanner.amounts import meets_threshold, parse_amount, parse_raise_amount, parse_round
from scanner.filter_articles import OUT as QUALIFYING_OUT
from scanner.httpcache import fetch
from scanner.paths import (
    ARTICLES_PARSED,
    REJECTED,
    SOURCE_TBSAASNEWS,
    TEXT,
    source_companies,
)
from scanner.paths import (
    ERRORS_LOG as ERRORS_LOG_PATH,
)
from scanner.sources.base import domain_of, normalize_name
from scanner.storage import append_text, read_json, write_json, write_text

PARSED_OUT = ARTICLES_PARSED
COMPANIES_OUT = source_companies(SOURCE_TBSAASNEWS)
ARTICLE_TEXT_DIR = TEXT
ERRORS_LOG = ERRORS_LOG_PATH

LABELS = [
    "Company Website",
    "Company",
    "Raised",
    "Round",
    "Funding Date",
    "Funding Month",
    "Lead Investors",
    "Lead Investor",
    "Additional Investors",
    "Software Category",
    "Source",
]
# canonical key per label alias (longest-first matching prevents prefix collisions)
LABEL_ALIASES: list[tuple[str, str]] = [
    ("company website", "website"),
    ("funding date", "funding_date"),
    ("funding month", "funding_date"),
    ("lead investors", "lead_investor"),
    ("lead investor", "lead_investor"),
    ("additional investors", "additional_investors"),
    ("software category", "software_category"),
    ("company", "company"),
    ("raised", "raised"),
    ("round", "round"),
    ("source", "source"),
]
SINGLE_LINE_KEYS = {
    "website",
    "raised",
    "round",
    "funding_date",
    "software_category",
    "lead_investor",
    "company",
}
STOP_PREFIXES = (
    "about the company",
    "about ",
    "by",
    "updated",
    "link copied",
    "copy failed",
    "latest news",
    "read more",
    "subscribe",
)


def _match_label(line_lower: str) -> tuple[str, str] | None:
    for alias, key in LABEL_ALIASES:
        if line_lower.startswith(alias + ":"):
            return alias, key
    return None


def parse_details_text(text: str) -> dict[str, str] | None:
    """Line-scan labeled fields; supports 'Label:' + next-line values,
    inline 'Label: value', and label/colon split across two lines
    ('Company' \\n ': Value'). Returns canonical-key -> value."""
    raw_lines = [ln.strip() for ln in text.splitlines()]
    # merge split-label forms: 'Company' followed by ': Gain.pro-B.V.'
    lines: list[str] = []
    i = 0
    while i < len(raw_lines):
        cur = raw_lines[i]
        if (
            i + 1 < len(raw_lines)
            and raw_lines[i + 1].startswith(":")
            and _match_label((cur + ":").lower()) is not None
            and _match_label(cur.lower()) is None
        ):
            merged = cur + raw_lines[i + 1]
            lines.append(merged)
            i += 2
            continue
        lines.append(cur)
        i += 1

    found: dict[str, str] = {}
    i = 0
    while i < len(lines):
        low = lines[i].lower()
        hit = _match_label(low)
        if hit is None:
            i += 1
            continue
        alias, key = hit
        inline = lines[i][len(alias) + 1 :].strip()
        vals: list[str] = []
        if inline:
            vals.append(inline)
        j = i + 1
        while not inline and j < len(lines):
            nxt = lines[j]
            if not nxt:
                if vals:
                    break
                j += 1
                continue
            nxt_low = nxt.lower()
            if _match_label(nxt_low) is not None:
                break
            if any(nxt_low.startswith(sp) or nxt_low == sp for sp in STOP_PREFIXES):
                break
            vals.append(nxt)
            j += 1
            if key in SINGLE_LINE_KEYS:
                break
        value = "\n".join(vals).strip()
        if key not in found:
            found[key] = value
        i = j if value else i + 1
    return found or None


def extract_funding_details(html: str) -> dict | None:
    """Parse the structured funding block.

    Primary path: nodes following an explicit 'Funding Details' heading.
    Fallback: labeled-field scan over the whole page text (older layout
    variant embeds fields directly in the body, sometimes with different
    labels such as 'Funding Month:' / plural 'Lead Investors:').
    """
    soup = BeautifulSoup(html, "lxml")
    main_el = soup.find("main") or soup
    full_text = main_el.get_text("\n", strip=True)

    details: dict[str, str] | None = None
    heading = soup.find(string=lambda s: s and s.strip() == "Funding Details")
    if heading is not None:
        parts: list[str] = []
        node = heading
        for _ in range(400):
            node = node.find_next()
            if node is None:
                break
            cls = node.get("class") or []
            if any("author" in c or "share" in c for c in cls):
                break
            if node.name in ("p", "br", "h2", "h3", "strong", "em", "span", "li"):
                txt = node.get_text("\n", strip=True)
                if txt:
                    parts.append(txt)
        block_text = "\n".join(parts)
        details = parse_details_text(block_text)

    required = ("company", "raised", "round", "website")
    if details is None or any(not details.get(k) for k in required):
        fallback = parse_details_text(full_text)
        if fallback is not None and (
            details is None
            or sum(bool(fallback.get(k)) for k in required)
            > sum(bool(details.get(k)) for k in required)
        ):
            details = fallback
    return details


def log_error(msg: str) -> None:
    append_text(ERRORS_LOG, f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")


REF_PARAM_RE = re.compile(r"[?&]ref=thesaasnews\.com")


def clean_site_url(url: str) -> str | None:
    url = REF_PARAM_RE.sub("", url.strip()).strip()
    if not url:
        return None
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def fetch_source_pr(source_url: str | None, slug: str) -> str | None:
    """Fetch external source link (PR/news) and cache clean text for LLM context."""
    if not source_url:
        return None
    url = clean_site_url(source_url)
    if not url:
        return None
    target = ARTICLE_TEXT_DIR / f"source__{slug}.txt"
    if target.exists():
        cached = target.read_text(encoding="utf-8", errors="replace")
        if cached.strip():
            return cached
    return _fetch_source_pr(url, target)


def _fetch_source_pr(url: str, target: Path) -> str | None:
    """Fetch and cache the PR. Failures leave no placeholder, so a later run retries."""
    try:
        resp = fetch(url, timeout=8.0, retries=1)
    except Exception:
        return None
    if not resp.ok:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer"]):
        tag.decompose()
    main_el = soup.find("article") or soup.find("main") or soup
    text = main_el.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= 100:
        return None
    header = f"Source Title: {title}\nSource URL: {url}\n\n" if title else f"Source URL: {url}\n\n"
    content = header + text
    write_text(target, content)
    return content


def clean_article_text(raw: str) -> str:
    """Truncate article text immediately after the Source field, discarding footers/sidebars."""
    # 1. Truncate at Source line (Source: https://... or Source:\nhttps://...)
    m = re.search(r"(?i)\bSource\s*:\s*(?:https?://[^\s\n]+|[^\n]+)", raw)
    if m:
        cut = raw[: m.end()].strip()
    else:
        # Fallback if no Source field: cut before post footer markers
        m2 = re.search(r"(?i)\n(?:by\s*\n\s*[A-Z][a-z]+|latest news|read more)", raw)
        cut = raw[: m2.start()].strip() if m2 else raw.strip()

    # 2. Remove author byline block near top if present
    cut = re.sub(
        r"(?i)\nby\s*\n\s*[A-Za-z\s.-]+\n\s*(?:Updated\s*\n\s*)?[A-Za-z]+ \d{1,2},? \d{4}\s*\n",
        "\n",
        cut,
    )

    # 3. Strip HTML blocks and UI artifacts
    cut = re.sub(r"<div\b[^>]*>[\s\S]*?</div>", "", cut, flags=re.IGNORECASE)
    cut = re.sub(r"<a\b[^>]*>[\s\S]*?</a>", "", cut, flags=re.IGNORECASE)
    cut = re.sub(r"<[^>]+>", "", cut)

    lines = []
    for line in cut.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in ("link copied!", "copy failed!", "link copied", "copy failed"):
            continue
        lines.append(stripped)

    return "\n".join(lines)


def load_parsed() -> dict:
    return read_json(PARSED_OUT, {"articles": {}})


def save_parsed(parsed: dict) -> None:
    write_json(PARSED_OUT, parsed)


def main(reparse: bool = False) -> None:
    qualifying = read_json(QUALIFYING_OUT)["qualifying"]
    parsed = load_parsed()
    if reparse:
        parsed = {"articles": {}}
    todo = [a for a in qualifying if a["slug"] not in parsed["articles"]]
    print(f"{len(qualifying)} qualifying, {len(todo)} to fetch")

    for n, art in enumerate(todo, 1):
        try:
            resp = fetch(art["url"])
        except ConnectionError as exc:
            log_error(f"article fetch failed {art['url']}: {exc}")
            parsed["articles"][art["slug"]] = {"fetch": "error"}
            save_parsed(parsed)
            continue
        if not resp.ok:
            log_error(f"article HTTP {resp.status} {art['url']}")
            parsed["articles"][art["slug"]] = {"fetch": f"http_{resp.status}"}
            save_parsed(parsed)
            continue
        details = extract_funding_details(resp.text)
        if not details:
            log_error(f"no funding-details block parsed {art['url']}")
            details = {}
        # store stripped article text for evaluation stage, cut strictly after Source
        soup = BeautifulSoup(resp.text, "lxml")
        art_el = soup.find("article", class_="gh-post-page__article") or soup.find("main") or soup
        body_text = clean_article_text(art_el.get_text("\n", strip=True))
        write_text(ARTICLE_TEXT_DIR / f"article__{art['slug']}.txt", body_text)
        parsed["articles"][art["slug"]] = {
            "fetch": "ok",
            "details": details,
            "title": art["title"],
            "url": art["url"],
            "date": art["date"],
            "filter_reason": art["filter_reason"],
        }
        save_parsed(parsed)
        if n % 25 == 0:
            print(f"  {n}/{len(todo)}", flush=True)

    # ---- verify & build company list ----
    companies: list[dict] = []
    rejected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    dup_count = 0
    for art in read_json(QUALIFYING_OUT)["qualifying"]:
        p = parsed["articles"].get(art["slug"], {})
        if p.get("fetch") != "ok":
            rejected.append({**art, "reject_reason": f"fetch_{p.get('fetch', 'missing')}"})
            continue
        d = p.get("details", {})
        company = (d.get("company") or "").strip().rstrip(",;")
        site_raw = (d.get("website") or "").splitlines()[0] if d.get("website") else ""
        site = clean_site_url(site_raw)
        raised_raw = (d.get("raised") or "").strip()
        round_field = (d.get("round") or "").strip()
        rnd_title = parse_round(art["title"])
        title_amt, _val = parse_raise_amount(art["title"])

        # --- amount verification (tolerant of site-side formatting bugs) ---
        amount_source = "article"
        flags: list[str] = []
        s_clean = re.sub(r"\s+", "", raised_raw)
        s_clean = re.sub(r"(\d+\.\d+)\.(\d+)", r"\1", s_clean)  # $13.5.0M -> $13.5M
        amt_article = parse_amount(s_clean)
        usd = amt_article.usd_equivalent if amt_article else 0.0
        if not meets_threshold(usd) and title_amt and meets_threshold(title_amt.usd_equivalent):
            # article Raised value missing/unparsable/below threshold while the
            # (pre-validated) title amount qualifies -> adopt title, flag it
            usd = title_amt.usd_equivalent
            amount_source = "title"
            flags.append(f"amount_from_title(article_raised={raised_raw!r})")

        # --- round verification: article field authoritative when present ---
        round_source = "article"
        pre_series_a_flag = False
        pre_seed_flag = False
        has_pre_seed = bool(re.search(r"pre-?\s?seed", round_field, re.I))
        rf_clean = re.sub(r"pre-?\s?seed", "", round_field, flags=re.I)
        has_seed = bool(re.search(r"\bseed\b", rf_clean, re.I))
        has_pre_series_a = bool(re.search(r"pre-?\s?series\s*-?\s*a", round_field, re.I))
        round_missing = not round_field or round_field.lower() in ("unknown", "n/a", "tbd")
        if round_missing:
            round_source = "title"
            if rnd_title.kind == "seed":
                has_seed = True
            elif rnd_title.kind == "pre-series-a":
                has_pre_series_a = True
                pre_series_a_flag = True
            elif rnd_title.kind == "pre-seed":
                has_pre_seed = True
                pre_seed_flag = True
            else:
                rejected.append(
                    {**art, "reject_reason": "round_unknown_and_title_unlabeled", "details": d}
                )
                continue
        elif not (has_seed or has_pre_series_a or has_pre_seed):
            rejected.append({**art, "reject_reason": f"round_field_not_seed_or_pre_seed ({round_field!r})", "details": d})
            continue
        if has_pre_series_a and not (has_seed or has_pre_seed):
            pre_series_a_flag = True
        if has_pre_seed:
            pre_seed_flag = True

        reasons = []
        if not company:
            reasons.append("no_company_name")
        if not meets_threshold(usd):
            reasons.append(f"raised_below_threshold ({usd:.0f} USD from {raised_raw!r})")
        if not site:
            # no website in article: keep, evaluate from article text with G5 gate
            flags.append("no_website_g5_candidate")
        if reasons:
            rejected.append({**art, "reject_reason": "; ".join(reasons), "details": d})
            continue
        if usd < 12_000_000:
            flags.append("near_boundary")

        dom = domain_of(site)
        key = (normalize_name(company), dom or "")
        dup = key in seen
        if dup:
            dup_count += 1
            flags.append("duplicate_article_same_company")
        seen.add(key)
        companies.append(
            {
                "slug": art["slug"],
                "article_url": art["url"],
                "title": art["title"],
                "date": art.get("date") or "",
                "company": company,
                "normalized_name": normalize_name(company),
                "domain": dom,
                "website": site,
                "raised_raw": raised_raw,
                "usd_equivalent": round(usd, 2),
                "amount_source": amount_source,
                "round_field": round_field,
                "round_source": round_source,
                "pre_seed": pre_seed_flag,
                "pre_series_a": pre_series_a_flag,
                "flags": flags,
                "funding_date": d.get("funding_date", ""),
                "lead_investor": d.get("lead_investor", ""),
                "additional_investors": d.get("additional_investors", ""),
                "software_category": d.get("software_category", ""),
                "source_url": clean_site_url(d.get("source", "")) or d.get("source", ""),
                "duplicate_of_previous": dup,
            }
        )

    write_json(COMPANIES_OUT, companies)
    write_json(REJECTED, rejected)
    kept_unique = [c for c in companies if not c["duplicate_of_previous"]]
    print(f"companies total={len(companies)} unique={len(kept_unique)} dups={dup_count} rejected={len(rejected)}")
    for r in rejected[:10]:
        print("  REJ:", r["title"], "->", r["reject_reason"])


def _cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 3: fetch qualifying articles")
    parser.add_argument("--reparse", action="store_true", help="Re-download and re-parse every article")
    return parser.parse_args()


if __name__ == "__main__":
    main(reparse=_cli().reparse)
