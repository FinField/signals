"""Value factor from the live FinField feed -> Numerai Signals submission.

End-to-end over real field data, no market-data vendor involved:

    feed shards (signed finfact-records)
      -> finknit.from_record            # decode + invariant-check
      -> finfacts.derive.derive_all     # finfield:book_to_float_mcap (B/M on free float)
      -> finsignals.rank_signal         # cross-sectional rank into (0,1)
      -> submission.csv                 # bloomberg_ticker,signal

The signal is the classic Fama-French value factor: rank of book equity over
free-float market cap (dei:EntityPublicFloat). Higher signal = cheaper on B/M;
invert the ranks if your model wants the opposite orientation.

Usage (from a checkout with the sibling repos, or pip-installed packages):

    git clone https://github.com/FinField/feed /tmp/finfield-feed
    python examples/feed_value_factor.py --feed /tmp/finfield-feed/feed --out submission.csv

Optionally intersect with your Numerai live universe first:

    python examples/feed_value_factor.py --feed ... --universe numerai_universe.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

for sibling in ("facts", "knit"):  # sibling-checkout fallback; harmless when pip-installed
    p = Path(__file__).resolve().parents[2] / sibling / "src"
    if p.is_dir():
        sys.path.insert(0, str(p))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finfacts.model import Entity, FactSet
from finfacts.derive import derive_all
from finknit import from_record
from finsignals import load_universe, rank_signal, write_submission

VALUE = "finfield:book_to_float_mcap"


def load_feed(feed_dir: Path) -> dict[str, list]:
    """Decode every finfact-record shard line into per-entity fact lists."""
    per_entity: dict[str, list] = {}
    decoded = rejected = 0
    for shard in sorted(feed_dir.glob("records-*.jsonl")):
        for line in shard.open(encoding="utf-8"):
            rec = json.loads(line, parse_float=Decimal)
            if rec.get("kind") != "finfact-record":
                continue
            try:
                fact = from_record(rec)
            except Exception:
                rejected += 1
                continue
            decoded += 1
            per_entity.setdefault(fact.entity_id, []).append(fact)
    print(f"decoded {decoded} facts for {len(per_entity)} entities "
          f"({rejected} rejected)", file=sys.stderr)
    return per_entity


def value_scores(per_entity: dict[str, list]) -> dict[str, Decimal]:
    scores: dict[str, Decimal] = {}
    for entity_id, facts in per_entity.items():
        ticker = entity_id.removeprefix("ticker:")
        fs = FactSet(entity=Entity(ticker=ticker), facts=list(facts))
        for fact in derive_all(fs):
            if fact.concept == VALUE:
                scores[ticker] = fact.decimal
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feed", required=True, type=Path,
                    help="feed/ dir of a FinField/feed clone (records-*.jsonl)")
    ap.add_argument("--out", default="submission.csv", type=Path)
    ap.add_argument("--universe", type=Path,
                    help="optional Numerai universe CSV to intersect with")
    args = ap.parse_args()

    scores = value_scores(load_feed(args.feed))
    if args.universe:
        keep = set(load_universe(args.universe))
        scores = {t: s for t, s in scores.items() if t in keep}
    if not scores:
        print("no value scores derived — is the feed dir right?", file=sys.stderr)
        return 1
    write_submission(args.out, rank_signal(scores))
    print(f"wrote {args.out} with {len(scores)} tickers", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
