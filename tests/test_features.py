"""Feature math: exact Decimals, deterministic dedupe, stable CIDs."""
from datetime import date, timedelta
from decimal import Decimal

from finfacts.model import FinFact, Period, Source, to_scaled
from finsignals import closes, feature_facts, fundamentals, momentum, volatility

ENTITY = "ticker:AAA US"


def close_fact(day, price, ref="test", entity_id=ENTITY):
    value, scale = to_scaled(price)
    return FinFact(entity_id=entity_id, concept="finfield:close",
                   value=value, scale=scale, unit="USD",
                   period=Period(end=day),
                   source=Source(kind="stooq-eod", ref=ref))


def weekly_series(entity_id=ENTITY):
    """11 closes, one per 7 days from 2026-01-05, price 100 + 2i."""
    return [close_fact((date(2026, 1, 5) + timedelta(days=7 * i)).isoformat(),
                       str(100 + 2 * i), entity_id=entity_id)
            for i in range(11)]


def test_closes_ordered_and_deduped():
    facts = [close_fact("2026-01-02", "101"), close_fact("2026-01-01", "100"),
             # same day, higher scale wins over scale 0
             close_fact("2026-01-02", "101.25")]
    assert closes(facts) == [("2026-01-01", Decimal("100")),
                             ("2026-01-02", Decimal("101.25"))]


def test_closes_same_scale_tie_breaks_on_latest_cid():
    a = close_fact("2026-01-02", "101.25", ref="a")
    b = close_fact("2026-01-02", "102.75", ref="b")
    winner = max([a, b], key=lambda f: f.cid)
    assert closes([a, b]) == [("2026-01-02", winner.decimal)]
    assert closes([b, a]) == closes([a, b])  # input order irrelevant


def test_momentum_exact_and_calendar_nearest_base():
    facts = [close_fact("2026-01-01", "100"), close_fact("2026-01-05", "110"),
             close_fact("2026-01-11", "125")]
    # target day 2026-01-01 exists: 125/100 - 1
    assert momentum(facts, 10) == Decimal("0.25")
    # target day 2026-01-04 absent: nearest prior is 2026-01-01
    assert momentum(facts, 7) == Decimal("0.25")
    # target day 2026-01-05 exists: base 110
    assert momentum(facts, 6) == Decimal("125") / Decimal("110") - 1
    # no close at or before 2025-12-27
    assert momentum(facts, 15) is None
    assert momentum(facts[:1], 5) is None


def test_volatility_exact_and_windowed():
    facts = [close_fact("2026-01-01", "100"), close_fact("2026-01-02", "110"),
             close_fact("2026-01-03", "99")]
    # returns 0.1, -0.1 -> mean 0, population var 0.01, stddev exactly 0.1
    assert volatility(facts, 10) == Decimal("0.1")
    # an old close outside the window changes nothing
    assert volatility([close_fact("2025-01-01", "50")] + facts, 10) == Decimal("0.1")
    # fewer than 3 closes in the window
    assert volatility(facts[1:], 10) is None


def test_feature_determinism_two_runs_identical():
    one, two = weekly_series(), weekly_series()
    assert momentum(one, 63) == momentum(two, 63)
    assert volatility(one, 63) == volatility(two, 63)
    assert volatility(one, 63) is not None


def test_fundamentals_latest_wins():
    def ratio(concept, end, value):
        return FinFact(entity_id=ENTITY, concept=concept, value=value, scale=6,
                       unit="pure", period=Period(end=end),
                       source=Source(kind="finfield-derived"))

    facts = [ratio("finfield:net_margin_ttm", "2025-09-30", 240000),
             ratio("finfield:net_margin_ttm", "2025-12-31", 250000),
             ratio("finfield:revenue_yoy", "2025-12-31", 61000)]
    assert fundamentals(facts) == {"net_margin_ttm": Decimal("0.25"),
                                   "revenue_yoy": Decimal("0.061")}
    assert fundamentals([]) == {}


def test_feature_facts_shape_and_stable_cids():
    facts = weekly_series()
    out = feature_facts(ENTITY, facts, "2026-03-16")
    # 70-day history: 63d momentum + volatility computable, 252d not
    assert [f.concept for f in out] == ["finsignals:momentum_63d",
                                        "finsignals:volatility_63d"]
    expected_inputs = tuple(sorted(f.cid for f in facts))
    for f in out:
        assert (f.scale, f.unit) == (6, "pure")
        assert f.period.end == "2026-03-16"
        assert f.source.kind == "finsignals-feature"
        assert f.derived_from == expected_inputs
    # 120/102 - 1 = 0.17647058... -> 176471 at scale 6
    assert out[0].value == 176471
    # CID pinned: any payload or math drift must be deliberate
    assert out[0].cid == "ff1:104865576b7c9b4f9ca31ab37deebb4a29b736761a9fd972c85620e91ab70257"
    # rebuilt from scratch -> byte-identical facts
    rerun = feature_facts(ENTITY, weekly_series(), "2026-03-16")
    assert [f.cid for f in rerun] == [f.cid for f in out]


def test_feature_facts_respects_asof_cutoff():
    facts = weekly_series()
    out = feature_facts(ENTITY, facts, "2026-03-09")  # drops the last close
    assert all(len(f.derived_from) == 10 for f in out)
    full = feature_facts(ENTITY, facts, "2026-03-16")
    assert [f.cid for f in out] != [f.cid for f in full]


def test_consensus_fact_beats_raw_observation():
    """A finfield-consensus fact wins the per-day dedupe over any raw close."""
    from finsignals.features import _close_facts

    day = "2026-07-03"
    raw = FinFact(entity_id="ticker:AAA US", concept="finfield:close",
                  value=2140599, scale=4, unit="USD", period=Period(end=day),
                  source=Source(kind="stooq-eod", ref="obs", fetched="2026-07-04"))
    consensus = FinFact(entity_id="ticker:AAA US", concept="finfield:close",
                        value=21405, scale=2, unit="USD", period=Period(end=day),
                        source=Source(kind="finfield-consensus", ref="finknit.vote"))
    # raw has the finer scale, but consensus must still win
    assert _close_facts([raw, consensus]) == [consensus]
    assert _close_facts([consensus, raw]) == [consensus]
