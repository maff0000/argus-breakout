"""WO-0007: source choice, split baseline, dividend adjustment, membership bounding, routing."""

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
import structlog
from structlog.testing import capture_logs
from typer.testing import CliRunner

from argus.cli import app
from argus.data.adjust import (
    apply_splits,
    dividend_adjusted_close,
    materialise,
    resolve_dividends,
    resolve_splits,
    select_source,
    source_disagreements,
)
from argus.data.store import Store

FIX = Path(__file__).parent / "fixtures" / "adjust"
FAR = date(2100, 1, 1)
LONG_AGO = date(1990, 1, 1)


@pytest.fixture(autouse=True)
def _fresh_logging():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def make_store(tmp_path, renames: list[tuple[str, str]] | None = None) -> Store:
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    if renames:
        lines = [f"  - {{old: {o}, new: {n}, effective: null}}" for o, n in renames]
        (config / "ticker_renames.yaml").write_text("renames:\n" + "\n".join(lines) + "\n")
    store = Store(tmp_path / "store", config_dir=config)
    store.init_schema()
    return store


@pytest.fixture
def store(tmp_path):
    return make_store(tmp_path)


def load(name: str) -> pl.DataFrame:
    return pl.read_parquet(FIX / f"{name}.parquet")


def raw_rows(sym, days, close, source="yfinance", volume=1000.0, ingested=None):
    ingested = ingested or datetime(2026, 6, 1, 6, 0)
    return pl.DataFrame(
        {
            "symbol": sym, "date": days, "open": close - 0.5, "high": close + 1.0,
            "low": close - 1.0, "close": close, "volume": volume, "source": source,
            "basis": "split", "ingested_at": ingested,
        },
        schema_overrides={"date": pl.Date, "ingested_at": pl.Datetime("us")},
    )


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def put_membership(store, sym, start, end):
    store.upsert(
        "membership",
        pl.DataFrame(
            {"symbol": [sym], "start_date": [start], "end_date": [end], "source": ["test"]},
            schema_overrides={"end_date": pl.Date},
        ),
        ["symbol", "start_date"],
    )


def put_splits(store, rows):
    store.upsert(
        "splits",
        pl.DataFrame(rows, schema=["symbol", "date", "ratio", "source"], orient="row"),
        ["symbol", "date", "source"],
    )


def put_dividends(store, rows):
    store.upsert(
        "dividends",
        pl.DataFrame(rows, schema=["symbol", "date", "cash_amount", "source"], orient="row"),
        ["symbol", "date", "source"],
    )


def bars_of(store, sym, etf=False):
    read = store.read_etf_bars if etf else store.read_bars
    return read([sym], LONG_AGO, FAR)


def digest(store, table, sym) -> str:
    path = store.parquet_dir / table / f"symbol={sym}" / "part.parquet"
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------ source choice
def test_prefers_polygon_on_overlap(store):
    raw = load("raw_two_sources")
    sel = select_source(raw)
    assert sel.height == 5  # one row per (symbol, date)
    by_date = {r["date"]: r for r in sel.iter_rows(named=True)}
    # overlap days take the Polygon row whole: close AND volume (volume is never averaged)
    for d in (date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)):
        assert by_date[d]["source"] == "polygon" and by_date[d]["volume"] == 1000.0
    assert by_date[date(2026, 1, 7)]["close"] == 102.004
    for d in (date(2026, 1, 5), date(2026, 1, 6)):
        assert by_date[d]["source"] == "yfinance" and by_date[d]["volume"] == 900.0

    store.write_bars_raw(raw)
    materialise(store, None)
    out = bars_of(store, "AAA")
    assert out["close"].to_list() == [100.0, 101.0, 102.004, 103.0, 105.04]
    assert out["volume"].to_list() == [900.0, 900.0, 1000.0, 1000.0, 1000.0]


def test_disagreement_warns_but_keeps_polygon(store):
    raw = load("raw_two_sources")
    found = source_disagreements(raw)
    # only 2026-01-09 (105.04 vs 104.00 = 1.0%) exceeds 0.5%; 102.004 vs 102.00 does not
    assert found.rows() == [("AAA", date(2026, 1, 9), 1.0)]

    store.write_bars_raw(raw)
    report = materialise(store, None)
    assert [w for w in report.warnings if w.startswith("source_disagreement")] == [
        "source_disagreement AAA 2026-01-09 pct_diff=1.0"
    ]
    assert bars_of(store, "AAA").filter(pl.col("date") == date(2026, 1, 9))["close"][0] == 105.04
    detail = store.read("SELECT detail FROM ingest_log WHERE source = 'materialise'")["detail"][0]
    assert "source_disagreement AAA 2026-01-09 pct_diff=1.0" in json.loads(detail)["warnings"]


# ------------------------------------------------------------------------------ splits
SPLIT_D = date(2026, 2, 10)


def test_split_applied_only_to_prior_history(store):
    store.write_bars_raw(load("split_case"))
    put_splits(store, [("SPL", SPLIT_D, 2.0, "polygon")])
    materialise(store, None)
    out = bars_of(store, "SPL")
    pre, post = out.filter(pl.col("date") < SPLIT_D), out.filter(pl.col("date") >= SPLIT_D)
    # hand values: yfinance history fetched before the split, halved; volume doubled
    assert pre["close"].to_list() == [50.0, 51.0, 52.0, 53.0, 54.0]
    assert pre["open"].to_list() == [49.75, 50.75, 51.75, 52.75, 53.75]
    assert pre["high"].to_list() == [50.5, 51.5, 52.5, 53.5, 54.5]
    assert pre["low"].to_list() == [49.5, 50.5, 51.5, 52.5, 53.5]
    assert pre["volume"].to_list() == [2000.0] * 5
    # Polygon rows on and after the split date already carry it: untouched
    assert post["close"].to_list() == [55.0, 56.0]
    assert post["volume"].to_list() == [2000.0, 2000.0]
    assert out["adj_close"].to_list() == out["close"].to_list()  # no dividends


def test_split_not_double_applied(store):
    store.write_bars_raw(load("split_case"))
    materialise(store, None)  # no split known yet: first publication
    assert bars_of(store, "SPL")["adj_version"].unique().to_list() == [1]
    assert bars_of(store, "SPL")["close"][0] == 100.0

    put_splits(store, [("SPL", SPLIT_D, 2.0, "polygon")])
    second = materialise(store, None)
    assert second.n_readjusted == 1 and second.n_rows == 7
    after_split = bars_of(store, "SPL")
    assert after_split["adj_version"].unique().to_list() == [2]
    assert after_split["close"][0] == 50.0
    digest_after_split = digest(store, "bars", "SPL")

    third = materialise(store, None)  # same inputs: no re-application, no new version
    assert third.n_readjusted == 0 and third.n_rows == 0
    again = bars_of(store, "SPL")
    assert again["adj_version"].unique().to_list() == [2]
    assert again["close"].to_list() == after_split["close"].to_list()
    assert digest(store, "bars", "SPL") == digest_after_split


def test_rerun_is_a_no_op_on_unchanged_inputs(store):
    store.write_bars_raw(pl.concat([load("raw_two_sources"), load("split_case")]))
    put_splits(store, [("SPL", SPLIT_D, 2.0, "polygon")])
    first = materialise(store, None)
    assert first.n_rows == 12 and first.n_readjusted == 0  # first publication, not a re-adjust
    before = {s: digest(store, "bars", s) for s in ("AAA", "SPL")}
    rows_before = store.read("SELECT * FROM bars ORDER BY symbol, date")
    second = materialise(store, None)
    assert (second.n_rows, second.n_readjusted) == (0, 0)
    assert {s: digest(store, "bars", s) for s in ("AAA", "SPL")} == before
    assert store.read("SELECT * FROM bars ORDER BY symbol, date").equals(rows_before)
    n = store.read("SELECT count(*) AS n FROM ingest_log WHERE source = 'materialise'")["n"][0]
    assert n == 2  # every run is recorded, including the no-op


def test_new_bars_append_without_a_new_version(store):
    raw = load("split_case")
    store.write_bars_raw(raw.filter(pl.col("date") < SPLIT_D))
    materialise(store, None)
    store.write_bars_raw(raw.filter(pl.col("date") >= SPLIT_D))
    report = materialise(store, None)
    assert report.n_readjusted == 0 and report.n_rows == 7
    assert bars_of(store, "SPL")["adj_version"].unique().to_list() == [1]


def test_split_baseline_is_per_row_fetch_time():
    """A source fetched either side of the split: only the rows fetched before it need adjusting."""
    before = raw_rows("ZZZ", [date(2026, 2, 5), date(2026, 2, 6)], 100.0, "polygon",
                      ingested=datetime(2026, 2, 9, 23, 0))
    after = raw_rows("ZZZ", [date(2026, 2, 10), date(2026, 2, 11)], 50.0, "polygon",
                     ingested=datetime(2026, 2, 11, 23, 0))
    splits = pl.DataFrame(
        [("ZZZ", SPLIT_D, 2.0, "polygon")], schema=["symbol", "date", "ratio", "source"],
        orient="row",
    )
    out = apply_splits(pl.concat([before, after]), splits, 7)
    # Polygon's latest bar is after the split, yet the first two rows were fetched before it
    assert out["close"].to_list() == [50.0, 50.0, 50.0, 50.0]
    assert out["volume"].to_list() == [2000.0, 2000.0, 1000.0, 1000.0]
    assert out["adj_version"].unique().to_list() == [7]

    # no ingested_at: the per-(symbol, source) latest bar date stands in for it
    legacy = pl.concat([raw_rows("ZZZ", [date(2026, 2, 5)], 100.0, "yfinance"),
                        raw_rows("ZZZ", [date(2026, 2, 5), date(2026, 2, 11)], 50.0, "polygon")])
    out = apply_splits(legacy.drop("ingested_at"), splits, 1).sort(["source", "date"])
    assert out["close"].to_list() == [50.0, 50.0, 50.0]  # polygon's 02-05 row has bars past D


def test_source_precedence_on_actions(store):
    store.write_bars_raw(load("split_case"))
    put_splits(
        store,
        [
            ("SPL", SPLIT_D, 2.0, "polygon"),
            ("SPL", SPLIT_D, 3.0, "yfinance"),  # disagrees by 50%
            ("SPL", date(2026, 1, 5), 2.0, "polygon"),  # agrees within 0.1%: no warning
            ("SPL", date(2026, 1, 5), 2.001, "yfinance"),
        ],
    )
    report = materialise(store, None)
    assert bars_of(store, "SPL")["close"][0] == 50.0  # Polygon's 2.0, not yfinance's 3.0
    found = [w for w in report.warnings if w.startswith("split_disagreement")]
    assert found == ["split_disagreement SPL 2026-02-10 polygon=2.0000 yfinance=3.0000"]

    kept, _ = resolve_splits(store.read_splits(None, LONG_AGO, FAR))
    assert kept.filter(pl.col("date") == SPLIT_D)["source"].to_list() == ["polygon"]

    divs = pl.DataFrame(
        [("D", date(2026, 3, 5), 1.00, "polygon"), ("D", date(2026, 3, 5), 1.02, "yfinance"),
         ("D", date(2026, 3, 6), 1.00, "polygon"), ("D", date(2026, 3, 6), 1.005, "yfinance")],
        schema=["symbol", "date", "cash_amount", "source"], orient="row",
    )
    kept, found = resolve_dividends(divs)
    assert kept["cash_amount"].to_list() == [1.00, 1.00]
    assert found == ["dividend_disagreement D 2026-03-05 polygon=1.0000 yfinance=1.0200"]


# ------------------------------------------------------------------------------ dividends
DIVS = [("DIV", date(2026, 3, 5), 2.08, "yfinance"), ("DIV", date(2026, 3, 10), 1.10, "polygon")]


def test_dividend_adj_close_hand_values(store):
    """Closes 100,102,...,114 on 03-02..03-11 (fixture dividend_case).

    Ex 03-05 pays 2.08; prior trading day 03-04 closed 104 -> factor 1 - 2.08/104 = 0.98.
    Ex 03-10 pays 1.10; prior trading day 03-09 closed 110 -> factor 1 - 1.10/110 = 0.99.
    Rows before 03-05 carry both (0.98 x 0.99 = 0.9702), 03-05..03-09 only the second,
    03-10 onward neither.
    """
    raw = load("dividend_case")
    bars = raw.select("symbol", "date", "close")
    adj = dividend_adjusted_close(
        bars, pl.DataFrame(DIVS, schema=["symbol", "date", "cash_amount", "source"], orient="row")
    )
    expected = [
        100 * 0.9702, 102 * 0.9702, 104 * 0.9702,
        106 * 0.99, 108 * 0.99, 110 * 0.99,
        112.0, 114.0,
    ]
    assert adj.to_list() == pytest.approx(expected, abs=1e-6)
    assert adj.to_list()[:3] == pytest.approx([97.02, 98.9604, 100.9008], abs=1e-6)
    assert adj.to_list()[3:6] == pytest.approx([104.94, 106.92, 108.9], abs=1e-6)

    store.write_bars_raw(raw)
    put_dividends(store, DIVS)
    materialise(store, None)
    out = bars_of(store, "DIV")
    assert out["adj_close"].to_list() == pytest.approx(expected, abs=1e-6)
    assert out["close"].to_list() == raw["close"].to_list()  # close is never dividend-adjusted


def test_new_dividend_readjusts_history_with_a_new_version(store):
    store.write_bars_raw(load("dividend_case"))
    materialise(store, None)
    put_dividends(store, DIVS[:1])
    report = materialise(store, None)
    assert report.n_readjusted == 1
    assert bars_of(store, "DIV")["adj_version"].unique().to_list() == [2]


def test_missing_prior_close_skips_dividend_with_warning():
    days = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5)]
    bars = raw_rows("MIS", days, 100.0).with_columns(
        pl.Series("close", [100.0, None, 104.0, 106.0])
    )
    ex = date(2026, 3, 4)  # prior trading day (03-03) has no close
    divs = pl.DataFrame([("MIS", ex, 2.0, "polygon")],
                        schema=["symbol", "date", "cash_amount", "source"], orient="row")
    warnings: list[str] = []
    adj = dividend_adjusted_close(bars, divs, warnings)
    assert adj.to_list() == [100.0, None, 104.0, 106.0]  # unchanged: dividend skipped
    assert warnings == ["dividend_skipped_no_prior_close MIS 2026-03-04 amount=2.0000"]

    # a prior bar weeks before the ex-date is not "the prior trading day" either
    sparse = raw_rows("MIS", [date(2026, 3, 2), date(2026, 3, 30)], 100.0)
    warnings = []
    divs = divs.with_columns(pl.lit(date(2026, 3, 30)).alias("date"))
    assert dividend_adjusted_close(sparse, divs, warnings).to_list() == [100.0, 100.0]
    assert warnings == ["dividend_skipped_no_prior_close MIS 2026-03-30 amount=2.0000"]


def test_dividend_after_the_last_bar_waits():
    bars = raw_rows("LAT", [date(2026, 3, 2), date(2026, 3, 3)], 100.0)
    divs = pl.DataFrame([("LAT", date(2026, 3, 9), 5.0, "polygon")],
                        schema=["symbol", "date", "cash_amount", "source"], orient="row")
    warnings: list[str] = []
    assert dividend_adjusted_close(bars, divs, warnings).to_list() == [100.0, 100.0]
    assert warnings == []


# ------------------------------------------------------------------------------ routing
def test_etf_routed_to_etf_bars(store):
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["SPY", "AAA"], "gics_sector": ["ETF", "Technology"]}),
        ["symbol"],
    )
    days = weekdays(date(2026, 1, 5), 4)
    store.write_bars_raw(pl.concat([raw_rows("SPY", days, 500.0), raw_rows("AAA", days, 50.0)]))
    report = materialise(store, None)
    assert report.n_symbols == 2 and report.n_rows == 8
    assert bars_of(store, "SPY", etf=True).height == 4 and bars_of(store, "SPY").is_empty()
    assert bars_of(store, "AAA").height == 4 and bars_of(store, "AAA", etf=True).is_empty()
    assert store.read("SELECT DISTINCT symbol FROM etf_bars")["symbol"].to_list() == ["SPY"]
    assert store.read("SELECT DISTINCT symbol FROM bars")["symbol"].to_list() == ["AAA"]


def test_symbols_subset_only_touches_those_symbols(store):
    days = weekdays(date(2026, 1, 5), 3)
    store.write_bars_raw(pl.concat([raw_rows("AAA", days, 50.0), raw_rows("BBB", days, 60.0)]))
    report = materialise(store, ["BBB"])
    assert report.n_symbols == 1
    assert bars_of(store, "AAA").is_empty() and bars_of(store, "BBB").height == 3
    with pytest.raises(ValueError):
        materialise(store, ["bad symbol"])


# ------------------------------------------------------------------------------ AMD-0018 2F
def _reassigned(store):
    """OLD delisted on 2026-01-06; its ticker was reassigned to a different company afterwards."""
    put_membership(store, "OLD", date(2020, 1, 1), date(2026, 1, 6))
    first = weekdays(date(2026, 1, 2), 3)  # 01-02, 01-05, 01-06: the member's own life
    later = weekdays(date(2026, 2, 2), 15)  # an unrelated company under the same ticker
    store.write_bars_raw(
        pl.concat([raw_rows("OLD", first, 50.0), raw_rows("OLD", later, 5.0, volume=7.0)])
    )
    return first, later


def test_reassigned_ticker_is_not_concatenated(store):
    first, later = _reassigned(store)
    report = materialise(store, None)
    out = bars_of(store, "OLD")
    assert out["date"].to_list() == first  # nothing after the final membership.end_date
    assert out["close"].to_list() == [50.0] * 3
    warned = [w for w in report.warnings if w.startswith("bars_outside_membership OLD")]
    assert len(warned) == 1 and "after_final_end=15" in warned[0] and "excluded=15" in warned[0]
    # bars_raw keeps both companies' rows: it records what the provider served (CI-9)
    assert store.read("SELECT count(*) AS n FROM bars_raw WHERE symbol = 'OLD'")["n"][0] == 18


def test_actions_after_final_end_are_not_applied(store):
    _reassigned(store)
    put_splits(store, [("OLD", date(2026, 2, 10), 4.0, "polygon")])  # the successor's split
    materialise(store, None)
    assert bars_of(store, "OLD")["close"].to_list() == [50.0] * 3


def test_outside_warning_needs_more_than_ten_days(tmp_path):
    for n_after, warns in ((10, False), (11, True)):
        s = make_store(tmp_path / f"n{n_after}")
        put_membership(s, "OLD", date(2020, 1, 1), date(2026, 1, 6))
        later = weekdays(date(2026, 2, 2), n_after)
        s.write_bars_raw(
            pl.concat([raw_rows("OLD", weekdays(date(2026, 1, 2), 3), 50.0),
                       raw_rows("OLD", later, 5.0)])
        )
        report = materialise(s, None)
        assert any(w.startswith("bars_outside_membership") for w in report.warnings) is warns
        assert bars_of(s, "OLD").height == 3  # excluded either way


def test_rename_chain_stays_continuous(tmp_path):
    s = make_store(tmp_path, renames=[("OLD", "NEW")])
    put_membership(s, "OLD", date(2020, 1, 1), date(2026, 1, 6))
    put_membership(s, "NEW", date(2026, 1, 7), None)
    old_days = weekdays(date(2026, 1, 2), 15)  # Polygon served OLD until the real rename
    new_days = weekdays(date(2025, 12, 1), 60)  # yfinance serves the whole history as NEW
    fetched = datetime(2026, 1, 15, 6, 0)  # before the split: these rows do not carry it yet
    s.write_bars_raw(
        pl.concat(
            [raw_rows("OLD", old_days, 50.0, "polygon", ingested=fetched),
             raw_rows("NEW", new_days, 50.0, ingested=fetched)]
        )
    )
    put_splits(s, [("OLD", date(2026, 1, 20), 2.0, "polygon")])  # recorded under the old ticker
    report = materialise(s, None)
    assert bars_of(s, "OLD")["date"].to_list() == old_days  # mapped forward: continuity, not cut
    assert bars_of(s, "NEW").height == 60
    assert "excluded=0 rename_continuity=true" in next(
        w for w in report.warnings if w.startswith("bars_outside_membership OLD")
    )
    # the old ticker's split is applied to the bars now stored under the new one as well
    new = bars_of(s, "NEW")
    assert new.filter(pl.col("date") < date(2026, 1, 20))["close"].unique().to_list() == [25.0]
    assert new.filter(pl.col("date") >= date(2026, 1, 20))["close"].unique().to_list() == [50.0]


def test_resolve_symbol_follows_chain_forward_and_records_it(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "ticker_renames.yaml").write_text(
        "renames:\n  - {old: AAA, new: BBB, effective: null}\n"
        "  - {old: CCC, new: DDD, effective: 2026-01-02}\n"
    )
    s = Store(tmp_path / "store", config_dir=config)
    day = date(2026, 3, 1)
    with capture_logs() as logs:
        assert s.resolve_symbol("AAA", day) == "BBB"
        assert s.resolve_symbol("CCC", day) == "DDD"
        assert s.resolve_symbol("QQQ", day) == "QQQ"  # unmapped: unchanged, not recorded
    redirected = [(e["symbol"], e["resolved"]) for e in logs if e["event"] == "symbol_redirected"]
    assert redirected == [("AAA", "BBB"), ("CCC", "DDD")]
    with pytest.raises(ValueError):
        s.resolve_symbol("not valid", day)


def test_resolve_symbol_chain_of_two_hops(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "ticker_renames.yaml").write_text(
        "renames:\n  - {old: AAA, new: BBB, effective: null}\n"
    )
    s = Store(tmp_path / "store", config_dir=config)
    s._rename_chain = {"AAA": "BBB", "BBB": "CCC"}  # chains longer than one hop are followed
    assert s.resolve_symbol("AAA", date(2026, 1, 1)) == "CCC"
    s._rename_chain = {"AAA": "BBB", "BBB": "AAA"}  # a cycle terminates
    assert s.resolve_symbol("AAA", date(2026, 1, 1)) in {"AAA", "BBB"}


# ------------------------------------------------------------------------------ quality seam
def _verdict(store, d, status, source="polygon"):
    store.log_ingest(d, source, 1, status)


def _flag(store, sym, d, flag, source="polygon"):
    store.upsert(
        "bar_flags",
        pl.DataFrame({"symbol": [sym], "date": [d], "source": [source], "flag": [flag],
                      "detail": ["t"]}),
        ["symbol", "date", "source", "flag"],
    )


SEAM_DAYS = weekdays(date(2026, 4, 6), 6)


def test_quarantined_day_not_published(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    for d in SEAM_DAYS:
        _verdict(store, d, "ok")
    _verdict(store, SEAM_DAYS[2], "quarantined")
    report = materialise(store, None)
    assert SEAM_DAYS[2] not in bars_of(store, "QQQ1")["date"].to_list()
    assert bars_of(store, "QQQ1").height == 5
    assert report.n_days_quarantined_skipped == 1 and report.n_symbol_days_flag_excluded == 0
    # bars_raw still holds the quarantined day (CI-9)
    assert store.read("SELECT count(*) AS n FROM bars_raw")["n"][0] == 6


def test_latest_verdict_wins(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    _verdict(store, SEAM_DAYS[0], "quarantined")
    import time
    time.sleep(0.01)
    _verdict(store, SEAM_DAYS[0], "ok")  # re-judged by revalidate
    assert materialise(store, None).n_days_quarantined_skipped == 0
    assert bars_of(store, "QQQ1").height == 6


def test_flagged_symbol_day_excluded_rest_remains(store):
    store.write_bars_raw(
        pl.concat([raw_rows("FLG", SEAM_DAYS, 10.0, "polygon"),
                   raw_rows("OTH", SEAM_DAYS, 20.0, "polygon")])
    )
    _flag(store, "FLG", SEAM_DAYS[3], "jump_unexplained")
    report = materialise(store, None)
    assert bars_of(store, "FLG")["date"].to_list() == [d for d in SEAM_DAYS if d != SEAM_DAYS[3]]
    assert bars_of(store, "OTH").height == 6  # same day, other symbol: untouched
    assert report.n_symbol_days_flag_excluded == 1 and report.n_days_quarantined_skipped == 0


def test_split_reconciled_flag_does_not_exclude(store):
    store.write_bars_raw(raw_rows("SRC", SEAM_DAYS, 10.0, "polygon"))
    _flag(store, "SRC", SEAM_DAYS[3], "jump_split_reconciled")
    report = materialise(store, None)
    assert bars_of(store, "SRC").height == 6
    assert report.n_symbol_days_flag_excluded == 0


def test_day_without_verdict_is_published(store):
    # yfinance bootstrap days (and pre-backfill history) have no polygon ingest_log row
    store.write_bars_raw(raw_rows("NOV", SEAM_DAYS, 10.0, "yfinance"))
    _verdict(store, SEAM_DAYS[0], "quarantined", source="other")  # another source's verdict
    report = materialise(store, None)
    assert bars_of(store, "NOV").height == 6 and report.n_days_quarantined_skipped == 0


def test_quarantine_does_not_withhold_yfinance_row(store):
    store.write_bars_raw(
        pl.concat([raw_rows("MIX", SEAM_DAYS, 10.0, "polygon"),
                   raw_rows("MIX", SEAM_DAYS, 10.0, "yfinance")])
    )
    _verdict(store, SEAM_DAYS[1], "quarantined")
    materialise(store, None)
    out = bars_of(store, "MIX")
    assert out.height == 6  # the day is published from yfinance, which has no verdict against it


def test_seam_rerun_is_a_no_op(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    _verdict(store, SEAM_DAYS[2], "quarantined")
    _flag(store, "QQQ1", SEAM_DAYS[4], "jump_unexplained")
    first = materialise(store, None)
    before = digest(store, "bars", "QQQ1")
    second = materialise(store, None)
    assert first.n_rows == 4 and (second.n_rows, second.n_readjusted) == (0, 0)
    assert digest(store, "bars", "QQQ1") == before
    assert second.n_days_quarantined_skipped == 1 and second.n_symbol_days_flag_excluded == 1


def test_newly_quarantined_day_readjusts_published_history(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    materialise(store, None)
    _verdict(store, SEAM_DAYS[2], "quarantined")
    report = materialise(store, None)
    assert report.n_readjusted == 1 and bars_of(store, "QQQ1").height == 5


# ------------------------------------------------------------------------------ store + CLI
def test_etf_bars_roundtrip(store):
    frame = pl.DataFrame(
        {
            "symbol": ["SPY", "SPY"], "date": [date(2026, 1, 5), date(2026, 1, 6)],
            "open": [1.0, 2.0], "high": [2.0, 3.0], "low": [0.5, 1.5], "close": [1.5, 2.5],
            "volume": [10.0, 20.0], "adj_close": [1.5, 2.5], "adj_version": [1, 1],
        }
    )
    assert store.write_etf_bars(frame) == 2
    assert store.read_etf_bars(["SPY"], LONG_AGO, FAR)["close"].to_list() == [1.5, 2.5]
    assert store.read_etf_bars(["QQQ"], LONG_AGO, FAR).is_empty()
    assert store.read_bars(["SPY"], LONG_AGO, FAR).is_empty()


def test_cli_materialise(clean_env, tmp_path):
    s = make_store(tmp_path)
    s.write_bars_raw(load("split_case"))
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("ARGUS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()
    res = runner.invoke(app, ["adjust", "materialise", "--symbols", "SPL"])
    assert res.exit_code == 0, res.output
    assert "symbols=1 rows=7 readjusted=0 warnings=0" in res.output
    assert "0 quarantined days not published, 0 flagged symbol-days excluded" in res.output
    again = runner.invoke(app, ["adjust", "materialise"])
    assert "symbols=1 rows=0 readjusted=0" in again.output
    bad = runner.invoke(app, ["adjust", "materialise", "--symbols", "AAA,not valid"])
    assert bad.exit_code == 2
