"""Numerai Signals universe handling.

Numerai keys its Signals universe on bloomberg-style composite tickers
("AAPL US") — the exact shape FinField already uses as Entity.ticker, so
the mapping between the two worlds is the identity function.

The live universe file is supplied by the user: downloading it needs a
Numerai account/API key and its endpoint shifts over time, so this module
is offline-first and hard-codes no volatile URLs. Export the file via
numerapi (or the Numerai UI) and hand its path to ``load_universe``.
"""
from __future__ import annotations

import csv
from typing import Iterable

TICKER_COLUMNS = ("bloomberg_ticker", "ticker")


def load_universe(path) -> list[str]:
    """Tickers from a Numerai universe CSV — file order, duplicates dropped.

    Accepts either a ``bloomberg_ticker`` or a ``ticker`` column (first
    match in ``TICKER_COLUMNS`` wins). Raises ValueError when neither is
    present.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        column = next((c for c in TICKER_COLUMNS if c in fields), None)
        if column is None:
            raise ValueError(f"no ticker column in {path}; expected one of {TICKER_COLUMNS}")
        seen: dict[str, None] = {}
        for row in reader:
            ticker = (row.get(column) or "").strip()
            if ticker:
                seen.setdefault(ticker, None)
    return list(seen)


def intersect(field_entities: Iterable, numerai_tickers: Iterable[str]) -> list[str]:
    """Ordered overlap: numerai_tickers order, kept when the field has them.

    ``field_entities`` may be finfacts Entities or plain ticker strings —
    tickers are identical on both sides (identity mapping), so membership
    is a straight set lookup.
    """
    field = {getattr(e, "ticker", e) for e in field_entities}
    out: list[str] = []
    emitted: set[str] = set()
    for ticker in numerai_tickers:
        if ticker in field and ticker not in emitted:
            out.append(ticker)
            emitted.add(ticker)
    return out
