"""Exact-Decimal Signals features from one entity's FinFacts.

All arithmetic runs in Decimal under ``localcontext(prec=28)`` — a fixed
precision makes division and ``Decimal.sqrt()`` bit-identical on every node,
so feature facts mint stable CIDs and can be voted on like any other
continuous quantity (float-natured values take vank weighted-median
consensus, see finknit.vote).

Windows are calendar days, not trading days: with ``t`` the latest close
day, ``momentum(days=k)`` compares close[t] against the close on the nearest
available day at or before ``t - k``. That rule is total and deterministic on
any gap pattern (weekends, halts, sparse feeds).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from typing import Optional

from finfacts.model import FinFact, Period, Source

FEATURE = Source(kind="finsignals-feature", ref="finsignals.features")
FEATURE_SCALE = 6
PRECISION = 28

CLOSE = "finfield:close"
FUNDAMENTALS = {
    "net_margin_ttm": "finfield:net_margin_ttm",
    "revenue_yoy": "finfield:revenue_yoy",
}


def _rank(f: FinFact) -> tuple:
    return (f.source.kind == "finfield-consensus", f.scale, f.cid)


def _close_facts(facts, asof_day: Optional[str] = None) -> list[FinFact]:
    """Deduped ``finfield:close`` facts ordered by day.

    Per day the winner is ``max((is_consensus, scale, cid))``: a
    ``finfield-consensus`` fact (the vank-voted value, see finknit.vote)
    beats any raw observation, then the finest scale, then the
    lexicographically-latest CID — a total order, so every node keeps the
    same fact.
    """
    best: dict[str, FinFact] = {}
    for f in facts:
        if f.concept != CLOSE:
            continue
        day = f.period.end
        if asof_day is not None and day > asof_day:
            continue
        cur = best.get(day)
        if cur is None or _rank(f) > _rank(cur):
            best[day] = f
    return [best[day] for day in sorted(best)]


def closes(facts) -> list[tuple[str, Decimal]]:
    """Ordered ``(iso_day, Decimal close)`` pairs, exactly one per day."""
    return [(f.period.end, f.decimal) for f in _close_facts(facts)]


def _momentum(pairs: list[tuple[str, Decimal]], days: int) -> Optional[Decimal]:
    if len(pairs) < 2:
        return None
    last_day, last = pairs[-1]
    target = (date.fromisoformat(last_day) - timedelta(days=days)).isoformat()
    base = None
    for day, value in pairs:
        if day > target:
            break
        base = value
    if base is None or base == 0:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        return last / base - 1


def momentum(facts, days: int) -> Optional[Decimal]:
    """``close[t] / close[t-days] - 1`` with a calendar-nearest prior base.

    ``t`` is the latest close day; the base is the close on the latest
    available day <= ``t - days``. None when no such base exists or the
    base is zero.
    """
    return _momentum(closes(facts), days)


def _volatility(pairs: list[tuple[str, Decimal]], days: int) -> Optional[Decimal]:
    if not pairs:
        return None
    start = (date.fromisoformat(pairs[-1][0]) - timedelta(days=days)).isoformat()
    window = [value for day, value in pairs if day >= start]
    if len(window) < 3:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        returns = []
        for prev, cur in zip(window, window[1:]):
            if prev == 0:
                return None
            returns.append(cur / prev - 1)
        n = Decimal(len(returns))
        mean = sum(returns, Decimal(0)) / n
        variance = sum(((r - mean) ** 2 for r in returns), Decimal(0)) / n
        return variance.sqrt()


def volatility(facts, days: int) -> Optional[Decimal]:
    """Population stddev of daily simple returns over the trailing window.

    Window = closes on days >= ``t - days`` (``t`` = latest close day);
    returns run between consecutive available closes inside it. Needs at
    least 3 closes (2 returns), else None. Decimal throughout, sqrt via
    ``Decimal.sqrt()`` — deterministic.
    """
    return _volatility(closes(facts), days)


def fundamentals(facts) -> dict[str, Decimal]:
    """Latest net_margin_ttm / revenue_yoy Decimals, when the field has them.

    Latest = max ``(period.end, cid)`` per concept — total order, so ties
    resolve identically everywhere.
    """
    out: dict[str, Decimal] = {}
    for key in sorted(FUNDAMENTALS):
        rows = [f for f in facts if f.concept == FUNDAMENTALS[key]]
        if rows:
            out[key] = max(rows, key=lambda f: (f.period.end, f.cid)).decimal
    return out


def feature_facts(entity_id: str, facts, asof_day: str) -> list[FinFact]:
    """Features as FinFacts, so signals knit back into the field.

    Emits ``finsignals:momentum_63d`` / ``finsignals:momentum_252d`` /
    ``finsignals:volatility_63d`` at scale 6 (unit "pure") for whatever is
    computable from closes on days <= ``asof_day``. ``derived_from``
    carries the sorted CIDs of every close fact considered, so the chain
    from a signal back to raw prices is machine-checkable — and features,
    being continuous quantities, are votable via vank weighted-median
    consensus (finknit.vote.float_consensus).
    """
    used = _close_facts(facts, asof_day=asof_day)
    pairs = [(f.period.end, f.decimal) for f in used]
    values = {
        "finsignals:momentum_63d": _momentum(pairs, 63),
        "finsignals:momentum_252d": _momentum(pairs, 252),
        "finsignals:volatility_63d": _volatility(pairs, 63),
    }
    inputs = tuple(sorted(f.cid for f in used))
    out = []
    for concept in sorted(values):
        value = values[concept]
        if value is None:
            continue
        with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
            scaled = int((value * 10**FEATURE_SCALE).to_integral_value())
        out.append(FinFact(
            entity_id=entity_id, concept=concept,
            value=scaled, scale=FEATURE_SCALE, unit="pure",
            period=Period(end=asof_day), source=FEATURE,
            derived_from=inputs,
        ))
    return out
