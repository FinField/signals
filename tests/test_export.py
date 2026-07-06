"""Export path: rank in (0,1), deterministic ties, byte-stable submission."""
from decimal import Decimal

from finfacts.model import Entity
from finsignals import (
    compose_score,
    intersect,
    load_universe,
    plain,
    rank_signal,
    write_submission,
)


def test_rank_signal_exact_values_and_tie_break():
    scores = {"BBB US": Decimal("1"), "AAA US": Decimal("1"), "CCC US": Decimal("2")}
    ranked = rank_signal(scores)
    # tie on score 1 broken by ticker sort: AAA before BBB
    assert ranked == {"AAA US": Decimal("0.25"), "BBB US": Decimal("0.5"),
                      "CCC US": Decimal("0.75")}
    # insertion order of the input dict is irrelevant
    assert rank_signal(dict(reversed(list(scores.items())))) == ranked


def test_rank_signal_strictly_inside_unit_interval():
    assert rank_signal({"AAA US": Decimal("7")}) == {"AAA US": Decimal("0.5")}
    ranked = rank_signal({f"T{i} US": Decimal(0) for i in range(10)})
    assert len(set(ranked.values())) == 10
    assert all(Decimal(0) < s < Decimal(1) for s in ranked.values())
    assert rank_signal({}) == {}


def test_compose_score_recipe():
    m63, m252 = "finsignals:momentum_63d", "finsignals:momentum_252d"
    both = {m63: Decimal("0.1"), m252: Decimal("0.4")}
    assert compose_score(both) == Decimal("0.3")
    assert compose_score({m252: Decimal("0.4")}) == Decimal("0.4")
    assert compose_score({m63: Decimal("0.1")}) == Decimal("0.1")
    assert compose_score({}) == Decimal(0)


def test_plain_never_scientific():
    assert plain(Decimal("1E-7")) == "0.0000001"
    assert plain(Decimal("0.25")) == "0.25"
    assert plain(Decimal("2E+3")) == "2000"


def test_submission_bytes_identical_across_runs(tmp_path):
    signals = rank_signal({"BBB US": Decimal("1"), "AAA US": Decimal("2"),
                           "CCC US": Decimal("0")})
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_submission(a, signals)
    write_submission(b, dict(reversed(list(signals.items()))))
    raw = a.read_bytes()
    assert raw == b.read_bytes()
    assert raw == (b"bloomberg_ticker,signal\n"
                   b"AAA US,0.75\n"
                   b"BBB US,0.5\n"
                   b"CCC US,0.25\n")
    assert b"E" not in raw.split(b"\n", 1)[1]  # plain decimals only


def test_universe_load_and_intersect(tmp_path):
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text("bloomberg_ticker,extra\nAAPL US,x\nMSFT US,y\nAAPL US,dup\n\n",
                        encoding="utf-8")
    assert load_universe(csv_path) == ["AAPL US", "MSFT US"]
    field = [Entity(ticker="MSFT US"), "BTC CRYPTO"]  # Entities or plain tickers
    assert intersect(field, load_universe(csv_path)) == ["MSFT US"]
