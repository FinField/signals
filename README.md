# finsignals

Numerai Signals from FinField P2P field data — FinFacts in, a submit-ready
`bloomberg_ticker,signal` CSV out.

- **Identity ticker map** — Numerai keys its universe on bloomberg-style composite
  tickers ("AAPL US"), the exact shape FinField uses, so no symbol translation layer.
  The live universe file is supplied by you (fetching it needs a Numerai account);
  finsignals is offline-first and hard-codes no volatile URLs.
- **Exact features** — momentum (63d/252d) and volatility from `finfield:close` facts,
  all Decimal at fixed precision (no floats, ever): same facts, same feature bytes on
  every node.
- **Features are facts** — `feature_facts` mints `finsignals:momentum_63d` etc. as
  scale-6 FinFacts whose `derived_from` lists every close CID used, so signals knit
  back into the field and, being continuous quantities, are votable via vank
  weighted-median consensus ([FinField/knit](https://github.com/FinField/knit)).
- **Consensus-first** — when the field disagrees on a price, feed the
  `finfield-consensus` fact (from `finknit.vote.float_consensus`) rather than any
  single observer's close.
- **Valid by construction** — rank r of n maps to r/(n+1), strictly inside (0,1);
  ties break on ticker sort; the CSV is byte-identical across runs.

Pure Python, stdlib only.

```bash
pip install "finsignals @ git+https://github.com/FinField/signals"
```

## End-to-end: field facts → submission.csv

```python
from finsignals import (feature_facts, fundamentals, compose_score,
                        rank_signal, write_submission, load_universe, intersect)

tickers = intersect(field_entities, load_universe("numerai_universe.csv"))

scores = {}
for ticker in tickers:
    facts = field_facts_for(ticker)          # prices + fundamentals from the field
    feats = feature_facts(f"ticker:{ticker}", facts, asof_day="2026-07-03")
    scores[ticker] = compose_score({f.concept: f.decimal for f in feats})
    # optionally weave `feats` back into the knitweb so peers can vote on them

write_submission("submission.csv", rank_signal(scores))
# bloomberg_ticker,signal — weekly eras key on a Friday date; upload as-is
```

The score recipe is fixed and documented: `momentum_252d - momentum_63d` when both
exist, else whichever momentum is available, else a neutral 0.

## Real-data example: value factor from the live feed

`examples/feed_value_factor.py` goes from the signed
[FinField/feed](https://github.com/FinField/feed) corpus to a submit-ready
file in one command — no market-data vendor:

```bash
git clone https://github.com/FinField/feed /tmp/finfield-feed
python examples/feed_value_factor.py --feed /tmp/finfield-feed/feed --out submission.csv
# decoded 87313 facts for 6500 entities (0 rejected)
# wrote submission.csv with 4182 tickers
```

The signal is the Fama-French value factor — book equity over free-float
market cap (`finfield:book_to_float_mcap`) — cross-sectionally ranked into
(0,1). Byte-identical across runs.

Part of the [FinField](https://github.com/FinField) field: [facts](https://github.com/FinField/facts) ·
[scrapers](https://github.com/FinField/scrapers) · [knit](https://github.com/FinField/knit) ·
[agents](https://github.com/FinField/agents) · [crypto](https://github.com/FinField/crypto)

## Extended factor zoo — the edge features

`finsignals.factors` adds the academically-validated cross-sectional factors that
actually move Signals correlation, all computed from the **same `finfield:close`
facts** (no new data source), all exact-Decimal and mintable back into the field
via `factor_facts` (scale-6 `pure`, `derived_from` CID chains, votable):

| factor | concept | why it has edge |
|---|---|---|
| 12-1 skip momentum | `finsignals:skipmom_252_21` | residual momentum, strips short-term reversal |
| multi-horizon momentum | `finsignals:momentum_21d` / `_126d` | captures medium-term trend |
| short-term reversal | `finsignals:reversal_5d` | 1-week mean reversion |
| downside volatility | `finsignals:downside_vol_63d` | semideviation / downside risk premium |
| lottery (MAX) | `finsignals:max_return_21d` | high-max stocks under-perform (negative predictor) |
| 52-week-high proximity | `finsignals:high_252d_ratio` | George–Hwang nearness-to-high |
| moving-average gap | `finsignals:ma_gap_50` / `_200` | trend / distance from MA |
| return skewness | `finsignals:skew_63d` | idiosyncratic-skew premium |
| long-horizon volatility | `finsignals:volatility_252d` | risk normalization |

```python
from finsignals import factor_facts
feats = factor_facts(f"ticker:{ticker}", field_facts_for(ticker), asof_day="2026-07-03")
# each fact is finsignals:<factor> at scale 6, derived_from the exact close CIDs used
```

The standard `feature_facts` pack (momentum_63d / momentum_252d / volatility_63d) is
unchanged and byte-stable; `factor_facts` is purely additive. Build your model on the
full factor matrix, or weave the facts back so peers can vote on them.
