"""Extended cross-sectional factor zoo for Numerai Signals — exact Decimal.

Additive to :mod:`finsignals.features`: the standard pack there (momentum_63d /
momentum_252d / volatility_63d) stays byte-stable; this module adds the
academically-validated factors that actually move Signals correlation, all
computed from the same ``finfield:close`` facts already in the field (no new
data source), all exact-Decimal and deterministic, and all mintable as scale-6
``pure`` FinFacts via :func:`factor_facts` so they knit back and are votable.

Every window is calendar-days (not sessions), resolved with the same
"nearest available close at or before the target day" rule as
:func:`finsignals.features.momentum`, so the math is total on any gap pattern.

Factors
-------
skip_momentum(days, skip)     r from t-days to t-skip (e.g. 252/21 = 12-1 momentum):
                              momentum minus the most-recent ``skip`` days, the
                              residual-momentum factor that strips short-term reversal.
reversal(days)                -1 x the trailing ``days`` return (short-term reversal).
downside_volatility(days)     sqrt(mean(min(r,0)^2)) — semideviation / downside risk.
max_return(days)              largest single-day return in the window — the lottery
                              (MAX) factor, a negative cross-sectional predictor.
high_ratio(days)              close[t] / max(close over trailing days) - 1 in (-1, 0];
                              proximity to the N-day high (52-week high = days≈365).
ma_gap(days)                  close[t] / mean(close over trailing days) - 1 (trend gap).
skew(days)                    sample skewness of the trailing daily returns.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from typing import Optional

from finfacts.model import FinFact, Period, Source

from .features import _close_facts, closes

FACTOR = Source(kind="finsignals-feature", ref="finsignals.factors")
FEATURE_SCALE = 6
PRECISION = 28


def _at_or_before(pairs: list[tuple[str, Decimal]], target: str) -> Optional[Decimal]:
    """Close on the latest available day at or before ``target`` (None if none)."""
    base = None
    for day, value in pairs:
        if day > target:
            break
        base = value
    return base


def _returns(window: list[Decimal]) -> Optional[list[Decimal]]:
    """Consecutive simple returns within a price window (None if any base is 0)."""
    out = []
    for prev, cur in zip(window, window[1:]):
        if prev == 0:
            return None
        out.append(cur / prev - 1)
    return out


def _window(pairs: list[tuple[str, Decimal]], days: int) -> list[Decimal]:
    """Close values on days >= t-days (t = latest day)."""
    if not pairs:
        return []
    start = (date.fromisoformat(pairs[-1][0]) - timedelta(days=days)).isoformat()
    return [v for d, v in pairs if d >= start]


def skip_momentum(facts, days: int, skip: int) -> Optional[Decimal]:
    """Return from ``t-days`` to ``t-skip`` — momentum excluding the most recent
    ``skip`` days. days=252, skip=21 is the classic 12-1 residual momentum."""
    pairs = closes(facts)
    if len(pairs) < 2 or skip >= days:
        return None
    last_day = date.fromisoformat(pairs[-1][0])
    end = _at_or_before(pairs, (last_day - timedelta(days=skip)).isoformat())
    base = _at_or_before(pairs, (last_day - timedelta(days=days)).isoformat())
    if base is None or end is None or base == 0:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        return end / base - 1


def reversal(facts, days: int) -> Optional[Decimal]:
    """Short-term reversal = -(close[t]/close[t-days] - 1)."""
    pairs = closes(facts)
    if len(pairs) < 2:
        return None
    last_day, last = pairs[-1]
    target = (date.fromisoformat(last_day) - timedelta(days=days)).isoformat()
    base = _at_or_before(pairs, target)
    if base is None or base == 0:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        return -(last / base - 1)


def downside_volatility(facts, days: int) -> Optional[Decimal]:
    """Semideviation: sqrt(mean(min(r,0)^2)) over the trailing return window."""
    window = _window(closes(facts), days)
    if len(window) < 3:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        returns = _returns(window)
        if returns is None:
            return None
        n = Decimal(len(returns))
        downside = sum(((r if r < 0 else Decimal(0)) ** 2 for r in returns), Decimal(0))
        return (downside / n).sqrt()


def max_return(facts, days: int) -> Optional[Decimal]:
    """Largest single-day simple return in the trailing window (lottery/MAX)."""
    window = _window(closes(facts), days)
    if len(window) < 2:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        returns = _returns(window)
        if not returns:
            return None
        return max(returns)


def high_ratio(facts, days: int) -> Optional[Decimal]:
    """close[t] / max(close over trailing ``days``) - 1, in (-1, 0].

    Proximity to the trailing-window high (George & Hwang 52-week-high factor
    at days≈365). 0 means at the high; more negative means further below it.
    """
    window = _window(closes(facts), days)
    if not window:
        return None
    peak = max(window)
    if peak == 0:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        return window[-1] / peak - 1


def ma_gap(facts, days: int) -> Optional[Decimal]:
    """close[t] / mean(close over trailing ``days``) - 1 (distance from MA)."""
    window = _window(closes(facts), days)
    if len(window) < 2:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        mean = sum(window, Decimal(0)) / Decimal(len(window))
        if mean == 0:
            return None
        return window[-1] / mean - 1


def skew(facts, days: int) -> Optional[Decimal]:
    """Sample skewness of the trailing daily returns (idiosyncratic skew factor).

    skew = (1/n Σ (r-mean)^3) / sigma^3 ; None if fewer than 3 returns or the
    return series has zero dispersion.
    """
    window = _window(closes(facts), days)
    if len(window) < 4:
        return None
    with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
        returns = _returns(window)
        if returns is None or len(returns) < 3:
            return None
        n = Decimal(len(returns))
        mean = sum(returns, Decimal(0)) / n
        m2 = sum(((r - mean) ** 2 for r in returns), Decimal(0)) / n
        m3 = sum(((r - mean) ** 3 for r in returns), Decimal(0)) / n
        if m2 == 0:
            return None
        sigma = m2.sqrt()
        return m3 / (sigma ** 3)


def factor_facts(entity_id: str, facts, asof_day: str) -> list[FinFact]:
    """The extended factor pack as scale-6 ``pure`` FinFacts dated ``asof_day``.

    Only closes on days <= ``asof_day`` feed the windows (no lookahead).
    ``derived_from`` lists the sorted CIDs of every close considered, so each
    factor is traceable to raw prices and votable via vank consensus.

    Emitted concepts (data permitting):
      finsignals:momentum_21d, finsignals:momentum_126d,
      finsignals:skipmom_252_21, finsignals:reversal_5d,
      finsignals:downside_vol_63d, finsignals:max_return_21d,
      finsignals:high_252d_ratio, finsignals:ma_gap_50, finsignals:ma_gap_200,
      finsignals:skew_63d, finsignals:volatility_252d
    """
    from .features import momentum, volatility  # local import: standard pack

    used = _close_facts(facts, asof_day=asof_day)
    inputs = tuple(sorted(f.cid for f in used))

    values = {
        "finsignals:momentum_21d": momentum(used, 21),
        "finsignals:momentum_126d": momentum(used, 126),
        "finsignals:skipmom_252_21": skip_momentum(used, 252, 21),
        "finsignals:reversal_5d": reversal(used, 5),
        "finsignals:downside_vol_63d": downside_volatility(used, 63),
        "finsignals:max_return_21d": max_return(used, 21),
        "finsignals:high_252d_ratio": high_ratio(used, 252),
        "finsignals:ma_gap_50": ma_gap(used, 50),
        "finsignals:ma_gap_200": ma_gap(used, 200),
        "finsignals:skew_63d": skew(used, 63),
        "finsignals:volatility_252d": volatility(used, 252),
    }

    out: list[FinFact] = []
    for concept in sorted(values):
        value = values[concept]
        if value is None:
            continue
        with localcontext(prec=PRECISION, rounding=ROUND_HALF_EVEN):
            scaled = int((value * 10 ** FEATURE_SCALE).to_integral_value())
        out.append(FinFact(
            entity_id=entity_id, concept=concept,
            value=scaled, scale=FEATURE_SCALE, unit="pure",
            period=Period(end=asof_day), source=FACTOR,
            derived_from=inputs,
        ))
    return out
