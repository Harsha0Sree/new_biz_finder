"""Amount/round parsing from article titles + fixed-FX USD conversion.

FX table (documented planning constants):
    EUR 1.08, GBP 1.27, JPY 0.0067, AUD 0.65, SGD 0.74,
    INR: Rs 1 Cr (crore) ~= $120k ; Rs 1 Lakh ~= $1.2k
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FX_USD_PER_UNIT = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0067,
    "AUD": 0.65,
    "SGD": 0.74,
}
INR_USD_PER_CRORE = 120_000.0
INR_USD_PER_LAKH = 1_200.0

THRESHOLD_USD = 10_000_000.0


def meets_threshold(usd_equivalent: float) -> bool:
    """Single source of truth for the qualification threshold (inclusive)."""
    return usd_equivalent >= THRESHOLD_USD


# first capture group = currency, second = numeric amount (commas/dots allowed)
_MONEY_RE = re.compile(
    r"""
    (?P<cur>US\$|[$€£¥₹]|(?<![A-Za-z])AU\$|(?<![A-Za-z])A\$|(?<![A-Za-z])S\$|\bRs\b)
    \s?
    (?P<num>\d[\d,]*(?:\.\d+)?)
    \s*
    (?P<unit>
        Billions?\b|Bn\b|B\b|
        Trillions?\b|Tn\b|T\b|
        Millions?\b|Mn\b|M\b|
        Thousands?\b|K\b|
        Crores?\b|Cr\b|
        Lakhs?\b|Lacs?\b|L\b
    )?
    """,
    re.IGNORECASE | re.VERBOSE,
)

@dataclass
class ParsedAmount:
    currency: str
    amount_native: float
    amount_unit_label: str | None
    usd_equivalent: float
    raw_match: str


def _unit_multiplier(unit: str | None) -> float:
    if unit is None:
        return 1.0
    u = unit.lower().rstrip(".")
    if u in ("b", "bn", "billion", "billions"):
        return 1_000_000_000.0
    if u in ("t", "tn", "trillion", "trillions"):
        return 1_000_000_000_000.0
    if u in ("m", "mn", "million", "millions"):
        return 1_000_000.0
    if u in ("k", "thousand", "thousands"):
        return 1_000.0
    # crore/lakh units are handled with INR FX; multiplier stays 1 here
    return 1.0


def parse_amount(title: str) -> ParsedAmount | None:
    """Parse the FIRST monetary amount in a title (the raise amount leads)."""
    m = _MONEY_RE.search(title)
    if not m:
        return None
    cur_raw = m.group("cur")
    num_raw = m.group("num").replace(",", "")
    try:
        number = float(num_raw)
    except ValueError:
        return None
    unit = m.group("unit")

    if cur_raw in ("$", "US$"):
        currency = "USD"
        usd = number * _unit_multiplier(unit)
        label = unit
    elif cur_raw in ("A$", "AU$"):
        currency = "AUD"
        usd = number * _unit_multiplier(unit) * FX_USD_PER_UNIT["AUD"]
        label = unit or ""
    elif cur_raw == "S$":
        currency = "SGD"
        usd = number * _unit_multiplier(unit) * FX_USD_PER_UNIT["SGD"]
        label = unit or ""
    elif cur_raw == "€":
        currency, fx = "EUR", FX_USD_PER_UNIT["EUR"]
        usd = number * _unit_multiplier(unit) * fx
        label = unit or ""
    elif cur_raw == "£":
        currency, fx = "GBP", FX_USD_PER_UNIT["GBP"]
        usd = number * _unit_multiplier(unit) * fx
        label = unit or ""
    elif cur_raw == "¥":
        currency, fx = "JPY", FX_USD_PER_UNIT["JPY"]
        usd = number * _unit_multiplier(unit) * fx
        label = unit or ""
    else:  # Rs / ₹
        currency = "INR"
        u = (unit or "").lower().rstrip(".")
        if u in ("cr", "crore", "crores"):
            usd = number * INR_USD_PER_CRORE
            label = unit
        elif u in ("l", "lac", "lacs", "lakh", "lakhs"):
            usd = number * INR_USD_PER_LAKH
            label = unit
        else:
            # bare rupee figure without crore/lakh unit — treat as rupees
            usd = number * 0.012
            label = None
    return ParsedAmount(
        currency=currency,
        amount_native=number,
        amount_unit_label=label,
        usd_equivalent=usd,
        raw_match=m.group(0),
    )


def _is_valuation_context(title: str, match: re.Match) -> bool:
    """True if a money match sits inside an 'at $X valuation' style phrase."""
    window_start = max(0, match.start() - 25)
    tail = title[match.end() : match.end() + 20].lower()
    head = title[window_start : match.start()].lower()
    if re.search(r"valua?tion|valu(ed|ing)", tail):
        return True
    # 'at $500M valuation' -> the words between 'at' and number then valuation after
    return bool(
        re.search(r"\b(?:at|@)\s*(?:a\s+)?$", head)
        and re.search(r"^\s*(?:post[- ]-money\s*)?valua?tion", tail)
    )


def parse_raise_amount(title: str) -> tuple[ParsedAmount | None, ParsedAmount | None]:
    """Return (raise_amount, valuation_amount) parsed from a title.

    The raise amount is the first money mention NOT inside a valuation phrase;
    the first valuation-context mention (if any) is returned separately.
    """
    raise_amt: ParsedAmount | None = None
    val_amt: ParsedAmount | None = None
    for m in _MONEY_RE.finditer(title):
        if _is_valuation_context(title, m):
            if val_amt is None:
                val_amt = parse_amount(m.group(0))
            continue
        if raise_amt is None:
            raise_amt = parse_amount(m.group(0))
    return raise_amt, val_amt


@dataclass
class RoundLabel:
    kind: str  # "seed" | "pre-series-a" | "pre-seed" | "other-series" | "unlabeled"
    flagged: bool


def parse_round(title: str) -> RoundLabel:
    t = title.lower()
    if re.search(r"pre-?seed", t):
        return RoundLabel("pre-seed", False)
    if re.search(r"pre-?series[- ]?a", t):
        return RoundLabel("pre-series-a", True)
    if re.search(r"\bseries\s+[a-z]\b", t):
        return RoundLabel("other-series", False)
    if re.search(r"\bseed\b", t):
        return RoundLabel("seed", False)
    return RoundLabel("unlabeled", False)


def qualifies(title: str) -> tuple[bool, str]:
    """Return (qualifies, reason).

    Qualifies = seed/pre-seed/pre-series-a AND at least $10M USD-equivalent.
    Reasons starting with "check_article_" mean the title alone cannot decide
    and the article's Funding Details block must be consulted.
    """
    amt, val_amt = parse_raise_amount(title)
    rnd = parse_round(title)
    if rnd.kind == "other-series":
        return False, f"round_{rnd.kind}"
    if amt is None:
        if val_amt is not None:
            return True, "check_article_valuation_only"
        # Seed-stage titles that omit the amount are deferred, not dropped:
        # fetch_articles reads the Funding Details block and keeps the
        # company only if the actual raise clears the threshold.
        return True, "check_article_no_amount"
    if not meets_threshold(amt.usd_equivalent):
        return False, f"amount_below_threshold ({amt.usd_equivalent:.0f} USD)"
    if rnd.kind == "unlabeled":
        return True, "ok_unlabeled_check_round_in_article"
    if rnd.kind == "pre-series-a":
        return True, "ok_pre_series_a_flagged"
    if rnd.kind == "pre-seed":
        return True, "ok_pre_seed"
    return True, "ok"
