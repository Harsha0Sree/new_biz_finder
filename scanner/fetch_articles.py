"""Step 3: fetch qualifying articles, parse Funding Details -> companies.

Writes data/articles_parsed.json (per-article facts, resumable) and
data/companies.json (deduped by normalized company name + domain).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from scanner.amounts import parse_amount, parse_raise_amount, parse_round
from scanner.filter_articles import OUT as QUALIFYING_OUT
from scanner.httpcache import fetch

PARSED_OUT = Path("data/articles_parsed.json")
COMPANIES_OUT = Path("data/companies.json")
ARTICLE_TEXT_DIR = Path("data/cache/text")
ERRORS_LOG = Path("data/errors.log")

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
    ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERRORS_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")


REF_PARAM_RE = re.compile(r"[?&]ref=thesaasnews\.com")


def clean_site_url(url: str) -> str | None:
    url = REF_PARAM_RE.sub("", url.strip()).strip()
    if not url:
        return None
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def normalize_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r"\s+(inc|llc|ltd|gmbh|bv|pty|co|corp|technologies|technology|labs|ai)\b.*$", "", n)
    return re.sub(r"\s+", " ", n).strip()


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    m = re.match(r"^https?://(?:www\.)?([^/:?#]+)", url)
    return m.group(1).lower() if m else None


def load_parsed() -> dict:
    if PARSED_OUT.exists():
        return json.loads(PARSED_OUT.read_text())
    return {"articles": {}}


def save_parsed(parsed: dict) -> None:
    PARSED_OUT.write_text(json.dumps(parsed, indent=1), encoding="utf-8")


def main() -> None:
    import sys

    qualifying = json.loads(QUALIFYING_OUT.read_text())["qualifying"]
    parsed = load_parsed()
    if "--reparse" in sys.argv:
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
        # store stripped article text for evaluation stage
        ARTICLE_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        soup = BeautifulSoup(resp.text, "lxml")
        main_el = soup.find("main") or soup
        body_text = main_el.get_text("\n", strip=True)
        (ARTICLE_TEXT_DIR / f"article__{art['slug']}.txt").write_text(body_text)
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
    for art in json.loads(QUALIFYING_OUT.read_text())["qualifying"]:
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
        if usd <= 10_000_000 and title_amt and title_amt.usd_equivalent > 10_000_000:
            # article Raised value missing/unparsable/below threshold while the
            # (pre-validated) title amount qualifies -> adopt title, flag it
            usd = title_amt.usd_equivalent
            amount_source = "title"
            flags.append(f"amount_from_title(article_raised={raised_raw!r})")

        # --- round verification: article field authoritative when present ---
        round_source = "article"
        pre_series_a_flag = False
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
            else:
                rejected.append(
                    {**art, "reject_reason": "round_unknown_and_title_unlabeled", "details": d}
                )
                continue
        elif not (has_seed or has_pre_series_a):
            rejected.append({**art, "reject_reason": f"round_field_not_seed ({round_field!r})", "details": d})
            continue
        if has_pre_series_a and not has_seed:
            pre_series_a_flag = True

        reasons = []
        if not company:
            reasons.append("no_company_name")
        if not usd > 10_000_000:
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
                "company": company,
                "normalized_name": normalize_name(company),
                "domain": dom,
                "website": site,
                "raised_raw": raised_raw,
                "usd_equivalent": round(usd, 2),
                "amount_source": amount_source,
                "round_field": round_field,
                "round_source": round_source,
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

    COMPANIES_OUT.write_text(json.dumps(companies, indent=1), encoding="utf-8")
    Path("data/rejected.json").write_text(json.dumps(rejected, indent=1), encoding="utf-8")
    kept_unique = [c for c in companies if not c["duplicate_of_previous"]]
    print(f"companies total={len(companies)} unique={len(kept_unique)} dups={dup_count} rejected={len(rejected)}")
    for r in rejected[:10]:
        print("  REJ:", r["title"], "->", r["reject_reason"])


if __name__ == "__main__":
    main()
