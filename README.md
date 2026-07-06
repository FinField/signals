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

Part of the [FinField](https://github.com/FinField) field: [facts](https://github.com/FinField/facts) ·
[scrapers](https://github.com/FinField/scrapers) · [knit](https://github.com/FinField/knit) ·
[agents](https://github.com/FinField/agents) · [crypto](https://github.com/FinField/crypto)
