"""End-to-end artifact validation.

This is the repository's quality gate for data, not just code. It checks the
shapes the pipeline promises: article index, qualifying rounds, companies,
sites, deep evaluations, LLM evaluations, and report links. Run it after any
pipeline step:

    uv run python -m scanner.validate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scanner.amounts import THRESHOLD_USD, parse_round
from scanner.compute import ARCHETYPES, GATE_IDS, compute_total
from scanner.llm import is_verified_record
from scanner.paths import ROOT
from scanner.storage import read_json

CONFIDENCE_LEVELS = {"high", "medium", "low"}
SITE_STATUSES = {"ok", "js_only", "dead", "dead_parked", "error"}
AGENCY_PLAY_KEYS = ("build_scope", "packaging", "pricing", "first_clients")
LOCAL_LINK_RE = re.compile(r"\]\(([^)#]+\.md)\)")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _load(path: Path, report: Report, label: str) -> Any:
    if not path.exists():
        report.error(f"{label}: missing file {path}")
        return None
    try:
        return read_json(path)
    except (ValueError, OSError) as exc:
        report.error(f"{label}: unreadable JSON: {exc}")
        return None


def _as_list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []


def validate_articles(payload: Any, report: Report) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        report.error("articles_index.json: expected an object")
        return []
    articles = _as_list(payload.get("articles"))
    report.checks["index_articles"] = len(articles)
    if payload.get("count") != len(articles):
        report.error(
            f"articles_index.json: count={payload.get('count')} "
            f"but articles={len(articles)}"
        )
    seen: set[str] = set()
    for index, article in enumerate(articles):
        if not isinstance(article, dict):
            report.error(f"articles_index.json: article {index} is not an object")
            continue
        slug = article.get("slug")
        if not slug:
            report.error(f"articles_index.json: article {index} has no slug")
            continue
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            report.error(f"articles_index.json: unsafe slug {slug!r}")
        if slug in seen:
            report.error(f"articles_index.json: duplicate slug {slug}")
        seen.add(slug)
        for key in ("url", "title"):
            if not article.get(key):
                report.error(f"articles_index.json: {slug} missing {key}")
    return [a for a in articles if isinstance(a, dict)]


def validate_qualifying(
    payload: Any,
    index_count: int,
    resolved_slugs: set[str],
    report: Report,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        report.error("qualifying.json: expected an object")
        return []
    qualifying = _as_list(payload.get("qualifying"))
    report.checks["qualifying"] = len(qualifying)
    if payload.get("kept_count") != len(qualifying):
        report.error(
            f"qualifying.json: kept_count={payload.get('kept_count')} "
            f"but qualifying={len(qualifying)}"
        )
    if payload.get("index_count") not in (None, index_count):
        report.warn(
            f"qualifying.json: index_count={payload.get('index_count')} "
            f"but articles_index has {index_count}; re-run scanner.filter_articles"
        )
    for index, article in enumerate(qualifying):
        if not isinstance(article, dict):
            report.error(f"qualifying.json: entry {index} is not an object")
            continue
        usd = article.get("usd_equivalent")
        reason = article.get("filter_reason") or ""
        slug = article.get("slug")
        if usd is None:
            report.error(f"qualifying.json: {slug} has no usd_equivalent")
        elif not isinstance(usd, (int, float)) or isinstance(usd, bool):
            report.error(f"qualifying.json: {slug} has non-numeric usd_equivalent {usd!r}")
        elif usd < THRESHOLD_USD:
            # Valuation-only titles are deliberately deferred: filter_articles
            # cannot tell the raise from the valuation, so fetch_articles parses
            # the Funding Details block and either keeps or rejects the company.
            if reason == "check_article_valuation_only":
                if slug not in resolved_slugs:
                    report.warn(
                        f"qualifying.json: {slug} is an unresolved valuation-only "
                        "candidate; re-run scanner.fetch_articles"
                    )
            else:
                report.error(f"qualifying.json: {slug} is below threshold ({usd})")
        if article.get("round_kind") == "other-series":
            report.error(
                f"qualifying.json: {article.get('slug')} is a named later series"
            )
    return [a for a in qualifying if isinstance(a, dict)]


def validate_companies(payload: Any, qualifying_count: int, report: Report) -> list[dict[str, Any]]:
    companies = _as_list(payload)
    report.checks["companies"] = len(companies)
    if not companies:
        report.error("companies.json: expected a non-empty list")
        return []
    unique = [c for c in companies if isinstance(c, dict) and not c.get("duplicate_of_previous")]
    report.checks["companies_unique"] = len(unique)
    if len(unique) > qualifying_count:
        report.warn(
            f"companies.json: {len(unique)} unique companies from "
            f"{qualifying_count} qualifying articles"
        )
    seen_slugs: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    for index, company in enumerate(companies):
        if not isinstance(company, dict):
            report.error(f"companies.json: entry {index} is not an object")
            continue
        slug = company.get("slug")
        if not slug:
            report.error(f"companies.json: entry {index} has no slug")
            continue
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            report.error(f"companies.json: unsafe slug {slug!r}")
        if slug in seen_slugs:
            report.error(f"companies.json: duplicate slug {slug}")
        seen_slugs.add(slug)
        for key in ("company", "article_url", "title", "usd_equivalent"):
            if company.get(key) in (None, ""):
                report.error(f"companies.json: {slug} missing {key}")
        round_source = company.get("round_source")
        if round_source not in (None, "article", "title"):
            report.error(f"companies.json: {slug} has bad round_source {round_source!r}")
        if not company.get("round_field") and round_source != "title":
            report.error(
                f"companies.json: {slug} has no round_field and did not infer one "
                "from the title"
            )
        if round_source == "title" and parse_round(str(company.get("title") or "")).kind in (
            "unlabeled",
            "other-series",
        ):
            report.error(
                f"companies.json: {slug} round_source=title but the title has no "
                "seed-stage label"
            )
        usd = company.get("usd_equivalent")
        if isinstance(usd, (int, float)) and usd < THRESHOLD_USD:
            report.error(f"companies.json: {slug} is below threshold ({usd})")
        domain = company.get("domain")
        website = company.get("website")
        if website and not domain:
            report.error(f"companies.json: {slug} has website but no domain")
        key = (str(company.get("normalized_name") or ""), str(domain or ""))
        if key in seen_keys and not company.get("duplicate_of_previous"):
            report.error(f"companies.json: {slug} repeats company/domain key {key}")
        seen_keys.add(key)
    return unique


def validate_sites(payload: Any, companies: list[dict[str, Any]], report: Report) -> None:
    if not isinstance(payload, dict):
        report.error("sites.json: expected an object")
        return
    sites = payload.get("sites")
    if not isinstance(sites, dict):
        report.error("sites.json: sites must be an object")
        return
    report.checks["sites"] = len(sites)
    for domain, record in sites.items():
        if not isinstance(record, dict):
            report.error(f"sites.json: {domain} is not an object")
            continue
        if record.get("domain") not in (None, domain):
            report.error(f"sites.json: {domain} record has domain={record.get('domain')}")
        status = record.get("status")
        if status not in SITE_STATUSES:
            report.error(f"sites.json: {domain} has unknown status {status!r}")
        pricing = record.get("pricing")
        if pricing is not None and not isinstance(pricing, dict):
            report.error(f"sites.json: {domain} pricing is not an object")
    missing = [
        c.get("domain")
        for c in companies
        if c.get("domain") and c.get("domain") not in sites
    ]
    if missing:
        report.error(
            f"sites.json: {len(missing)} company domains have no site record "
            f"(e.g. {', '.join(map(str, missing[:5]))})"
        )


def validate_eval_record(record: Any, name: str, report: Report) -> None:
    if not isinstance(record, dict):
        report.error(f"evals/{name}: expected an object")
        return
    for key in (
        "slug",
        "company",
        "archetype",
        "confidence",
        "gates",
        "categories",
        "agency_play",
    ):
        if key not in record:
            report.error(f"evals/{name}: missing key {key}")
    if record.get("archetype") not in ARCHETYPES:
        report.error(f"evals/{name}: bad archetype {record.get('archetype')!r}")
    slug_val = record.get("slug")
    if slug_val is not None and (
        not isinstance(slug_val, str) or not SLUG_RE.match(slug_val)
    ):
        report.error(f"evals/{name}: unsafe slug {slug_val!r}")
    if record.get("confidence") not in CONFIDENCE_LEVELS:
        report.error(f"evals/{name}: bad confidence {record.get('confidence')!r}")
    gates = record.get("gates")
    if not isinstance(gates, list):
        report.error(f"evals/{name}: gates must be a list")
    else:
        gate_ids = [g.get("gate") for g in gates if isinstance(g, dict)]
        if set(gate_ids) != GATE_IDS:
            report.error(f"evals/{name}: gates must cover exactly {sorted(GATE_IDS)}")
        if len(gate_ids) != len(set(gate_ids)):
            report.error(f"evals/{name}: duplicate gates")
        for gate in gates:
            if not isinstance(gate, dict):
                report.error(f"evals/{name}: gate entry is not an object")
                continue
            if not isinstance(gate.get("applied"), bool):
                report.error(f"evals/{name}: gate {gate.get('gate')} applied is not bool")
            if not str(gate.get("rationale") or "").strip():
                report.error(f"evals/{name}: gate {gate.get('gate')} has no rationale")
    categories = record.get("categories")
    if not isinstance(categories, dict) or set(categories) != {str(i) for i in range(1, 53)}:
        report.error(f"evals/{name}: categories must be exactly 1..52")
    else:
        for number, category in categories.items():
            if not isinstance(category, dict):
                report.error(f"evals/{name}: category {number} is not an object")
                continue
            for head in ("h1", "h2", "h3", "h4"):
                value = category.get(head)
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10:
                    report.error(f"evals/{name}: category {number} has bad {head}={value!r}")
            if len(str(category.get("evidence") or "").strip()) < 5:
                report.error(f"evals/{name}: category {number} has weak evidence")
    agency_play = record.get("agency_play")
    if not isinstance(agency_play, dict):
        report.error(f"evals/{name}: agency_play must be an object")
    else:
        for key in AGENCY_PLAY_KEYS:
            if len(str(agency_play.get(key) or "").strip()) < 10:
                report.error(f"evals/{name}: agency_play.{key} is too short")


_NBSP_CHARS = "\u00a0\u202f"


def _norm_domain(value: Any) -> str:
    text = str(value or "").strip().lower()
    for nbsp in _NBSP_CHARS:
        text = text.replace(nbsp, "")
    return text.rstrip(".")


def validate_deep_evals(
    evals_dir: Path,
    report: Report,
    companies: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not evals_dir.exists():
        report.error(f"missing evals directory {evals_dir}")
        return records
    by_slug = {
        c.get("slug"): c for c in (companies or []) if isinstance(c, dict) and c.get("slug")
    }
    files = sorted(evals_dir.glob("*.json"))
    report.checks["deep_evals"] = len(files)
    for path in files:
        record = _load(path, report, f"evals/{path.name}")
        if not isinstance(record, dict):
            continue
        validate_eval_record(record, path.name, report)
        if record.get("slug") and record["slug"] != path.stem:
            report.error(f"evals/{path.name}: slug {record['slug']} does not match filename")
        comp = by_slug.get(path.stem)
        if comp is not None:
            doma, domb = _norm_domain(record.get("domain")), _norm_domain(comp.get("domain"))
            if doma and domb and doma != domb:
                report.error(
                    f"evals/{path.name}: domain {doma!r} does not match registry domain {domb!r}"
                )
        records[path.stem] = record
    return records


def _verify_scored_against_eval(
    item: Any, record: dict[str, Any], report: Report
) -> None:
    slug = record.get("slug")
    try:
        recomputed = compute_total(record)
    except Exception as exc:
        report.error(f"scored.json: {slug} could not be recomputed: {exc}")
        return

    def close(got: Any, want: float, tol: float) -> bool:
        return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) <= tol

    for key in ("total", "gate_mask"):
        if not close(item.get(key), recomputed[key], 1e-6):
            report.error(
                f"scored.json: {slug} {key}={item.get(key)} != recomputed {recomputed[key]}"
            )
    if item.get("tier") != recomputed["tier"]:
        report.error(
            f"scored.json: {slug} tier {item.get('tier')} != recomputed {recomputed['tier']}"
        )
    if sorted(item.get("applied_gates") or []) != sorted(recomputed["applied_gates"]):
        report.error(f"scored.json: {slug} applied_gates != recomputed")
    got_pillars = item.get("pillar_scores_0_10") or {}
    for pillar_id, want in recomputed["pillar_scores_0_10"].items():
        got = got_pillars.get(pillar_id)
        if not close(got, want, 1e-3):
            report.error(
                f"scored.json: {slug} pillar {pillar_id}={got} != recomputed {want}"
            )


def validate_scored(payload: Any, companies: list[dict[str, Any]], evals: dict, report: Report) -> None:
    if not isinstance(payload, dict):
        report.error("scored.json: expected an object")
        return
    scored = _as_list(payload.get("companies"))
    report.checks["scored"] = len(scored)
    if payload.get("evaluated_count") != len(scored):
        report.error(
            f"scored.json: evaluated_count={payload.get('evaluated_count')} "
            f"but companies={len(scored)}"
        )
    invalid_count = payload.get("invalid_count") or 0
    expected_missing = max(0, len(companies) - len(scored) - invalid_count)
    if payload.get("missing_count") != expected_missing:
        report.error(
            f"scored.json: missing_count={payload.get('missing_count')} but "
            f"{expected_missing} unique companies lack a valid evaluation; "
            "re-run scanner.compute"
        )
    live_invalid = _as_list(payload.get("invalid")) if isinstance(payload, dict) else []
    if live_invalid or payload.get("invalid_count"):
        report.error(
            f"scored.json: {payload.get('invalid_count')} invalid evaluation files; fix them or remove them"
        )
    expected = {
        c.get("slug")
        for c in companies
        if c.get("slug") and (c.get("slug") in evals)
    }
    scored_slugs = {s.get("slug") for s in scored if isinstance(s, dict)}
    missing = expected - scored_slugs
    if missing:
        report.error(f"scored.json: missing evaluated companies {sorted(missing)[:5]}")
    stale = scored_slugs - set(evals)
    if stale:
        report.error(f"scored.json: entries without a deep eval file {sorted(stale)[:5]}")
    for item in scored:
        if not isinstance(item, dict):
            report.error("scored.json: company entry is not an object")
            continue
        slug = item.get("slug")
        if not isinstance(item.get("total"), (int, float)):
            report.error(f"scored.json: {slug} has no numeric total")
        if item.get("tier") not in {"A", "B", "C", "D"}:
            report.error(f"scored.json: {slug} has bad tier {item.get('tier')!r}")
        record = evals.get(slug) if isinstance(slug, str) else None
        if record:
            _verify_scored_against_eval(item, record, report)


def validate_llm_evals(
    payload: Any,
    evals_dir: Path,
    report: Report,
    summary_path: Path | None = None,
    known: set[str] | None = None,
) -> None:
    if not isinstance(payload, list):
        report.error("llm_scored.json: expected a list")
        return
    scored = payload
    report.checks["llm_scored"] = len(scored)
    successful: set[str] = set()
    errored: set[str] = set()
    unverified: set[str] = set()
    eval_records: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []
    file_count = 0
    if evals_dir.exists():
        for path in sorted(evals_dir.glob("*.json")):
            file_count += 1
            record = _load(path, report, f"llm_evals/{path.name}")
            if not isinstance(record, dict):
                invalid.append(path.name)
                continue
            for key in ("slug", "company", "provider", "model", "score"):
                if record.get(key) in (None, ""):
                    report.error(f"llm_evals/{path.name}: missing {key}")
            slug_val = record.get("slug")
            if slug_val is not None and (
                not isinstance(slug_val, str) or not SLUG_RE.match(slug_val)
            ):
                report.error(f"llm_evals/{path.name}: unsafe slug {slug_val!r}")
            if isinstance(slug_val, str) and slug_val != path.stem:
                report.error(f"llm_evals/{path.name}: slug {slug_val} does not match filename")
            if known is not None and path.stem not in known:
                report.error(f"llm_evals/{path.name}: no matching company or rejected candidate")
            eval_records[path.stem] = record
            if is_verified_record(record):
                successful.add(path.stem)
                continue
            if record.get("error"):
                errored.add(path.stem)
                continue
            unverified.add(path.stem)
            score = record.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                if not 0 <= score <= 100:
                    report.error(f"llm_evals/{path.name}: bad score {score!r}")
            else:
                report.error(f"llm_evals/{path.name}: bad score {score!r}")
    scored_slugs = {item.get("slug") for item in scored if isinstance(item, dict)}
    for index, item in enumerate(scored):
        if not isinstance(item, dict):
            report.error(f"llm_scored.json: entry {index} is not an object")
            continue
        record = eval_records.get(item.get("slug") or "")
        if known is not None and isinstance(item.get("slug"), str) and item["slug"] not in known:
            report.error(f"llm_scored.json: {item['slug']} has no matching company")
        if record is None:
            continue
        for key in ("slug", "score", "model", "provider"):
            if item.get(key) != record.get(key):
                report.error(f"llm_scored.json: {item.get('slug')} {key} does not match its llm_evals record")
        if str(item.get("verdict")) != str(record.get("verdict")):
            report.error(f"llm_scored.json: {item.get('slug')} verdict does not match its llm_evals record")
        usd_item, usd_record = item.get("usd_equivalent"), record.get("usd_equivalent")
        if (
            usd_item is not None
            and usd_record is not None
            and float(usd_item) != float(usd_record)
        ):
            report.error(f"llm_scored.json: {item.get('slug')} usd_equivalent does not match")
    if scored_slugs != successful:
        report.error(
            "llm_scored.json: does not match successful llm_evals "
            f"(scored={len(scored_slugs)}, successful={len(successful)}); "
            "run `python main.py --aggregate-only`"
        )
    if errored:
        report.warn(f"llm_evals: {len(errored)} errored records will be retried on the next run")
    if unverified:
        report.warn(f"llm_evals: {len(unverified)} unverified records (no parsed score) will be retried on the next run")
    if summary_path is not None:
        summary = _load(summary_path, report, "llm_eval_summary.json")
        if isinstance(summary, dict):
            expected = {
                "files": file_count,
                "successful": len(successful),
                "errored": len(errored),
                "unverified": len(unverified),
                "included": len(successful),
            }
            for key, want in expected.items():
                got = summary.get(key)
                if got != want:
                    report.error(
                        f"llm_eval_summary.json: {key}={got} but disk yields {want}"
                    )
            if list(summary.get("invalid") or []) != invalid:
                report.error(
                    f"llm_eval_summary.json: invalid={summary.get('invalid')} but disk yields {invalid}"
                )


def validate_reports(reports_dir: Path, report: Report, scored_count: int | None = None) -> None:
    for name in ("master-ranking.md", "index.md"):
        path = reports_dir / name
        if not path.exists():
            report.error(f"reports/{name}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for link in LOCAL_LINK_RE.findall(text):
            if "://" in link or link.startswith(("#", "mailto:")):
                continue
            target = (reports_dir / link).resolve()
            if not target.exists():
                report.error(f"reports/{name}: broken link {link}")
    llm_report = reports_dir / "llm_opportunity_ranking.md"
    if not llm_report.exists():
        report.error("reports/llm_opportunity_ranking.md: missing")


def validate_repo(root: str | Path = ROOT) -> Report:
    root = Path(root)
    data = root / "data"
    reports = root / "reports"
    report = Report()

    articles_payload = _load(data / "articles_index.json", report, "articles_index.json")
    articles = validate_articles(articles_payload, report)
    qualifying_payload = _load(data / "qualifying.json", report, "qualifying.json")
    companies_payload = _load(data / "companies.json", report, "companies.json")
    rejected_payload = _load(data / "rejected.json", report, "rejected.json")
    rejected = _as_list(rejected_payload)
    report.checks["rejected"] = len(rejected)
    resolved = {c.get("slug") for c in _as_list(companies_payload) if isinstance(c, dict)}
    resolved |= {r.get("slug") for r in rejected if isinstance(r, dict)}
    qualifying = validate_qualifying(
        qualifying_payload, len(articles), resolved, report
    )
    companies = validate_companies(companies_payload, len(qualifying), report)
    for article in qualifying:
        if article.get("slug") not in resolved:
            report.warn(
                f"qualifying.json: {article.get('slug')} is not represented in "
                "companies.json or rejected.json"
            )
    for index, item in enumerate(rejected):
        if not isinstance(item, dict):
            report.error(f"rejected.json: entry {index} is not an object")
        elif not item.get("reject_reason"):
            report.error(f"rejected.json: {item.get('slug')} has no reject_reason")
    sites_payload = _load(data / "sites.json", report, "sites.json")
    validate_sites(sites_payload, companies, report)
    known = {c.get("slug") for c in companies}
    known |= {r.get("slug") for r in rejected if isinstance(r, dict)}
    evals = validate_deep_evals(data / "evals", report, companies)
    for stem in evals:
        if stem not in known:
            report.error(f"evals/{stem}.json: no matching company or rejected candidate")
    scored_payload = _load(data / "scored.json", report, "scored.json")
    for item in _as_list((scored_payload or {}).get("companies") if isinstance(scored_payload, dict) else []):
        if isinstance(item, dict) and item.get("slug") not in known:
            report.error(f"scored.json: {item.get('slug')} has no matching company")
    validate_scored(scored_payload, companies, evals, report)
    llm_payload = _load(data / "llm_scored.json", report, "llm_scored.json")
    validate_llm_evals(llm_payload, data / "llm_evals", report, data / "llm_eval_summary.json", known)
    if isinstance(articles_payload, dict) and articles_payload.get("errors"):
        report.error(
            f"articles_index.json: {len(articles_payload['errors'])} crawl fetch errors recorded"
        )
    scored_count = len(_as_list((scored_payload or {}).get("companies") if isinstance(scored_payload, dict) else []))
    validate_reports(reports, report, scored_count)

    errors_log = data / "errors.log"
    if errors_log.exists():
        lines = [line for line in errors_log.read_text(encoding="utf-8").splitlines() if line]
        report.checks["error_log_lines"] = len(lines)
        if lines:
            report.warn(f"errors.log has {len(lines)} recorded fetch/parse failures")

    return report


def main() -> int:
    report = validate_repo()
    for check, count in report.checks.items():
        print(f"  {check}: {count}")
    for warning in report.warnings:
        print(f"WARN {warning}")
    for error in report.errors:
        print(f"ERROR {error}")
    print(
        f"\nvalidation: {len(report.errors)} errors, "
        f"{len(report.warnings)} warnings, {len(report.checks)} checks"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
