"""finsignals — Numerai Signals from FinField P2P field data.

Turns FinFacts (prices + fundamentals; prefer finfield-consensus facts when
the field disagrees) into exact-Decimal features, a cross-sectional rank
strictly inside (0,1), and a submit-ready ``bloomberg_ticker,signal`` CSV.

Numerai keys its Signals universe on bloomberg-style composite tickers —
the same "AAPL US" shape FinField uses — so the bridge between the two
worlds is the identity map. No floats anywhere: features are Decimals at a
fixed precision, minted back into the field as scale-6 FinFacts whose CIDs
are byte-stable, so signals themselves are votable (finknit.vote).
"""
from .export import (  # noqa: F401
    compose_score,
    plain,
    rank_signal,
    write_submission,
)
from .features import (  # noqa: F401
    closes,
    feature_facts,
    fundamentals,
    momentum,
    volatility,
)
from .factors import (  # noqa: F401
    downside_volatility,
    factor_facts,
    high_ratio,
    ma_gap,
    max_return,
    reversal,
    skew,
    skip_momentum,
)
from .universe import intersect, load_universe  # noqa: F401

__version__ = "0.1.0"
