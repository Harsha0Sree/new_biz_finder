import pytest

from scanner.amounts import parse_amount, parse_raise_amount, parse_round, qualifies

GROUND_TRUTH = [
    # (title, should_qualify)
    ("Callosum Raises $100M Seed", True),
    ("Veeda AI Raises $90M Seed", True),
    ("Asteromorph Raises $31.4M Seed", True),
    ("Twin1 AI Raises $20M Seed", True),
    ("Drafted Raises $16M Seed", True),
    ("CasaPerks Technologies, Inc. Raises $15.8M Seed", True),
    ("NeoSoul Raises $11M Pre-Series A", True),  # include + flag
    ("idler Raises $9M Seed", False),
    ("ARC Intelligence Raises €4M Seed", False),
    ("UnlimiTech Raises ¥180M Seed", False),  # ~$1.2M
    ("Ubiqedge Raises Rs 10 Cr Seed", False),  # ~$1.2M
]


@pytest.mark.parametrize("title,expected", GROUND_TRUTH)
def test_ground_truth(title, expected):
    ok, reason = qualifies(title)
    assert ok == expected, f"{title}: {reason}"


def test_threshold_at_least_10m():
    assert qualifies("Arc Raises $10.76M Seed")[0] is True
    assert qualifies("X Raises $10,000,000 Seed")[0] is True
    assert qualifies("Metacognition Raises $10M Pre-seed")[0] is True
    assert qualifies("X Raises $9,999,999 Seed")[0] is False


def test_currency_conversion():
    assert parse_amount("A Raises €13M Seed").usd_equivalent == pytest.approx(14_040_000)
    assert parse_amount("A Raises £2.3M Seed").usd_equivalent == pytest.approx(2_921_000)
    assert parse_amount("A Raises ¥70M Seed").usd_equivalent == pytest.approx(469_000)
    assert parse_amount("FreightFox Raises ₹5Cr Pre-Series A").usd_equivalent == pytest.approx(600_000)
    assert parse_amount("BazaarNow Raises ₹72Cr Seed").usd_equivalent == pytest.approx(8_640_000)


def test_prefixed_dollar_currencies():
    a = parse_amount("Constantinople Raises A$32 Million in Seed Round")
    assert a.currency == "AUD"
    assert a.usd_equivalent == pytest.approx(32_000_000 * 0.65)
    assert parse_amount("X Raises AU$5M Seed").currency == "AUD"
    s = parse_amount("Y Raises S$10M Seed")
    assert s.currency == "SGD" and s.usd_equivalent == pytest.approx(7_400_000)


def test_formats():
    a = parse_amount("YardOps Raises £500,000 Seed")
    assert a.usd_equivalent == pytest.approx(635_000)
    a = parse_amount("DiscreteStack Raises €800K Seed")
    assert a.usd_equivalent == pytest.approx(800_000 * 1.08)
    a = parse_amount("X Raises $1B Seed")
    assert a.usd_equivalent == pytest.approx(1_000_000_000)
    a = parse_amount("Celery Raises $6.25 Million in Seed Round")
    assert a.usd_equivalent == pytest.approx(6_250_000)
    a = parse_amount("Workroom Automation Raises ₹6.2 Crore Seed Round")
    assert a.usd_equivalent == pytest.approx(744_000)
    a = parse_amount("Roopya Raises Rs 4 Cr Seed Round")
    assert a.usd_equivalent == pytest.approx(480_000)


def test_valuation_not_matched_instead_of_raise():
    a = parse_amount("humans& Raises $480M Seed at $4.48B Valuation")
    assert a.amount_native == 480
    assert a.usd_equivalent == pytest.approx(480_000_000)


def test_no_amount():
    assert parse_amount("MODEPICK Raises Seed Funding") is None
    assert parse_amount("MemoraX AI Raises ¥Hundreds of millions Seed") is None


def test_valuation_only_titles_deferred_to_article():
    ok, why = qualifies("Pathway Raises Funding at $500M Valuation")
    assert ok is True and why == "check_article_valuation_only"
    amt, val = parse_raise_amount("Pathway Raises Funding at $500M Valuation")
    assert amt is None and val is not None and val.usd_equivalent == 500_000_000


def test_valuation_ignored_when_raise_present():
    amt, val = parse_raise_amount("humans& Raises $480M Seed at $4.48B Valuation")
    assert amt.usd_equivalent == pytest.approx(480_000_000)
    assert val.usd_equivalent == pytest.approx(4_480_000_000)


def test_round_labels():
    r = parse_round("NeoSoul Raises $11M Pre-Series A")
    assert (r.kind, r.flagged) == ("pre-series-a", True)
    r = parse_round("Superleap Raises ₹36Cr pre-Series A")
    assert r.kind == "pre-series-a"
    assert parse_round("KERYS Software Raises €6.2 Million in Pre-Seed Round").kind == "pre-seed"
    assert parse_round("Altan Raises $2.5 Million in Pre-Seed Round").kind == "pre-seed"
    assert parse_round("Callosum Raises $100M Seed").kind == "seed"
    assert parse_round("Maxed Raises $850K in Funding").kind == "unlabeled"


def test_pre_seed_included_when_large():
    ok, why = qualifies("BigCo Raises $25 Million in Pre-Seed Round")
    assert ok is True and why == "ok_pre_seed"
    assert qualifies("Metacognition Raises $10M Pre-seed")[0] is True
    assert qualifies("SmallCo Raises $2 Million in Pre-Seed Round")[0] is False
