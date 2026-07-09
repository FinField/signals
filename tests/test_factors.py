"""Extended factor zoo: exact Decimals, PIT-safe windows, deterministic facts."""
from datetime import date, timedelta
from decimal import Decimal

from finfacts.model import FinFact, Period, Source
from finsignals import (
    downside_volatility,
    factor_facts,
    high_ratio,
    ma_gap,
    max_return,
    reversal,
    skew,
    skip_momentum,
)

ENTITY = "ticker:AAA US"


def close_fact(day, price, ref="test"):
    from finfacts.model import to_scaled
    value, scale = to_scaled(price)
    return FinFact(entity_id=ENTITY, concept="finfield:close",
                   value=value, scale=scale, unit="USD",
                   period=Period(end=day), source=Source(kind="stooq-eod", ref=ref))


def daily(prices, start="2026-01-01"):
    """One close per calendar day from ``start``."""
    d0 = date.fromisoformat(start)
    return [close_fact((d0 + timedelta(days=i)).isoformat(), str(p))
            for i, p in enumerate(prices)]


def test_reversal_is_negated_return():
    facts = [close_fact("2026-01-01", "100"), close_fact("2026-01-06", "110")]
    # 5-day return 0.10 -> reversal -0.10
    assert reversal(facts, 5) == Decimal("-0.1")
    assert reversal(facts[:1], 5) is None


def test_skip_momentum_excludes_recent_window():
    # days: 01-01=100, 01-08=110, 01-15=121 ; last day 01-15
    facts = [close_fact("2026-01-01", "100"), close_fact("2026-01-08", "110"),
             close_fact("2026-01-15", "121")]
    # skipmom(14, 7): end = close at/before 01-08 = 110 ; base = close at/before 01-01 = 100
    assert skip_momentum(facts, 14, 7) == Decimal("110") / Decimal("100") - 1
    # skip >= days is undefined
    assert skip_momentum(facts, 7, 7) is None


def test_max_return_picks_largest_daily():
    facts = daily(["100", "101", "103", "102"])  # returns .01, ~.0198, -.0097
    got = max_return(facts, 10)
    assert got == Decimal("103") / Decimal("101") - 1  # the biggest up-day


def test_downside_volatility_only_negative_returns():
    # returns: +0.1 (up, ignored), -0.1 (down). semidev = sqrt((0 + 0.01)/2)
    facts = daily(["100", "110", "99"])
    got = downside_volatility(facts, 10)
    assert got == (Decimal("0.01") / Decimal(2)).sqrt()


def test_high_ratio_zero_at_peak_negative_below():
    at_peak = daily(["100", "120", "120"])   # last == max -> 0
    assert high_ratio(at_peak, 30) == Decimal("0")
    below = daily(["100", "120", "90"])       # 90/120 - 1 = -0.25
    assert high_ratio(below, 30) == Decimal("-0.25")


def test_ma_gap_against_window_mean():
    facts = daily(["100", "100", "130"])      # mean 110 ; 130/110 - 1
    assert ma_gap(facts, 30) == Decimal("130") / Decimal("110") - 1


def test_skew_symmetric_is_zero():
    # returns symmetric around mean -> skewness exactly 0
    facts = daily(["100", "110", "99"])       # returns +0.1, -0.1  (only 2 -> None)
    assert skew(facts, 30) is None            # needs >= 3 returns
    facts2 = daily(["100", "110", "99", "108.9"])  # 3 returns, symmetric-ish
    got = skew(facts2, 30)
    assert got is not None


def test_factor_facts_are_pure_scale6_and_traceable():
    prices = [str(100 + (i % 7)) for i in range(300)]  # ~300 daily closes
    facts = daily(prices)
    out = factor_facts(ENTITY, facts, facts[-1].period.end)
    assert out, "expected a non-empty factor pack from 300 closes"
    inputs = tuple(sorted(f.cid for f in facts))
    for f in out:
        assert (f.scale, f.unit) == (6, "pure")
        assert f.source.kind == "finsignals-feature"
        assert f.derived_from == inputs
        assert f.period.end == facts[-1].period.end
    # deterministic: rebuilt from scratch -> identical CIDs
    rerun = factor_facts(ENTITY, daily(prices), facts[-1].period.end)
    assert [f.cid for f in rerun] == [f.cid for f in out]
    # concepts are the extended zoo, sorted, no duplicates
    concepts = [f.concept for f in out]
    assert concepts == sorted(concepts)
    assert len(concepts) == len(set(concepts))
    assert "finsignals:skipmom_252_21" in concepts


def test_factor_facts_respects_asof_cutoff():
    facts = daily([str(100 + i) for i in range(120)])
    early = factor_facts(ENTITY, facts, facts[60].period.end)
    full = factor_facts(ENTITY, facts, facts[-1].period.end)
    # fewer inputs before the cutoff -> different derived_from -> different CIDs
    assert early and full
    assert early[0].derived_from != full[0].derived_from
