"""Rank transform and Numerai Signals submission file.

Numerai scores the cross-sectional *order* of a signal, not its magnitude,
so the export path is: compose one Decimal score per ticker, rank the cross
section with total tie-breaking, map rank r (1-based) to r/(n+1) — strictly
inside (0,1) as the upload validator requires — and write
``bloomberg_ticker,signal`` rows sorted by ticker. Every step is exact
Decimal, so the submission file is byte-identical across runs and nodes.
"""
from __future__ import annotations

from decimal import Decimal, localcontext

PRECISION = 28

MOMENTUM_63D = "finsignals:momentum_63d"
MOMENTUM_252D = "finsignals:momentum_252d"
VOLATILITY_63D = "finsignals:volatility_63d"


def compose_score(features: dict[str, Decimal]) -> Decimal:
    """One score per ticker from its feature dict. Fixed, documented recipe:

    ``momentum_252d - momentum_63d`` when both are present (the classic
    12-month trend with the noisy trailing quarter stripped out); otherwise
    whichever momentum exists; otherwise ``Decimal(0)`` — a neutral score,
    so thin-data tickers rank by tie-break instead of being dropped.
    """
    m252 = features.get(MOMENTUM_252D)
    m63 = features.get(MOMENTUM_63D)
    if m252 is not None and m63 is not None:
        with localcontext(prec=PRECISION):
            return m252 - m63
    if m252 is not None:
        return m252
    if m63 is not None:
        return m63
    return Decimal(0)


def rank_signal(scores: dict[str, Decimal]) -> dict[str, Decimal]:
    """Cross-sectional rank map: rank r (1-based) -> ``Decimal(r)/(n+1)``.

    Ordered by ``(score, ticker)`` ascending — the ticker breaks ties, so
    the ranking is a total, deterministic order. Every output lies strictly
    in (0,1): the minimum is 1/(n+1), the maximum n/(n+1).
    """
    ordered = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(ordered)
    out: dict[str, Decimal] = {}
    with localcontext(prec=PRECISION):
        for rank, (ticker, _) in enumerate(ordered, start=1):
            out[ticker] = Decimal(rank) / Decimal(n + 1)
    return out


def plain(value: Decimal) -> str:
    """Render a Decimal without an exponent (never ``1E-7``): plain digits."""
    return format(value, "f")


def write_submission(path, signals: dict[str, Decimal]) -> None:
    """Write the Numerai Signals upload CSV.

    Exactly the columns Numerai expects — ``bloomberg_ticker,signal`` —
    rows sorted by ticker, signals rendered as plain decimal strings,
    ``\\n`` line endings. Same signals in, same bytes out.
    """
    lines = ["bloomberg_ticker,signal"]
    for ticker in sorted(signals):
        lines.append(f"{ticker},{plain(signals[ticker])}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
