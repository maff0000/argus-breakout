"""WO-0007: source choice, split baseline, dividend adjustment, membership bounding, routing."""

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
import structlog
from pydantic import SecretStr
from structlog.testing import capture_logs
from typer.testing import CliRunner

from argus.cli import app
from argus.data.adjust import (
    MaterialiseReport,
    apply_splits,
    dividend_adjusted_close,
    equal_weight_aggregate,
    materialise,
    resolve_dividends,
    resolve_splits,
    select_source,
    source_disagreements,
)
from argus.data.ingest_polygon import ingest_polygon_actions
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store, stamp_dividend_basis
from argus.diagnostics.dividends import attribute_pairs

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


def calendar_rows(start: date, n: int) -> pl.DataFrame:
    """A continuously trading symbol with no membership: the market calendar bars_raw implies
    (AMD-0021 2B measures a gap in trading days present in bars_raw)."""
    return raw_rows("CAL", weekdays(start, n), 10.0)


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
    """Rows are (symbol, date, amount, source) or (..., source, vendor_id); a row with no id gets
    'sum' for yfinance and a distinct 'rec-<n>' otherwise (one record per row)."""
    full = [
        r if len(r) == 5 else (*r, "sum" if r[3] == "yfinance" else f"rec-{n}")
        for n, r in enumerate(rows)
    ]
    store.upsert(
        "dividends",
        pl.DataFrame(
            full, schema=["symbol", "date", "cash_amount", "source", "vendor_id"], orient="row"
        ),
        ["symbol", "date", "source", "vendor_id"],
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
        bars,
        stamp_dividend_basis(
            pl.DataFrame(DIVS, schema=["symbol", "date", "cash_amount", "source"], orient="row")
        ),
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
    divs = stamp_dividend_basis(
        pl.DataFrame([("MIS", ex, 2.0, "polygon")],
                     schema=["symbol", "date", "cash_amount", "source"], orient="row")
    )
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
    divs = stamp_dividend_basis(
        pl.DataFrame([("LAT", date(2026, 3, 9), 5.0, "polygon")],
                     schema=["symbol", "date", "cash_amount", "source"], orient="row")
    )
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
    later = weekdays(date(2026, 3, 2), 15)  # an unrelated company under the same ticker
    store.write_bars_raw(
        pl.concat([raw_rows("OLD", first, 50.0), raw_rows("OLD", later, 5.0, volume=7.0),
                   calendar_rows(date(2026, 1, 2), 70)])
    )
    return first, later


def test_reassigned_ticker_is_not_concatenated(store):
    first, later = _reassigned(store)
    report = materialise(store, None)
    out = bars_of(store, "OLD")
    assert out["date"].to_list() == first  # nothing after the final membership.end_date
    assert out["close"].to_list() == [50.0] * 3
    warned = [
        w for w in report.warnings if w.startswith("bars_after_final_end_without_continuity OLD")
    ]
    assert len(warned) == 1 and "after_final_end=15" in warned[0]
    assert report.n_bars_after_final_end_without_continuity == 15
    # bars_raw keeps both companies' rows: it records what the provider served (CI-9)
    assert store.read("SELECT count(*) AS n FROM bars_raw WHERE symbol = 'OLD'")["n"][0] == 18


def test_reassigned_ticker_tail_is_excluded_and_warned(store):
    first, later = _reassigned(store)
    cal = weekdays(date(2026, 1, 2), 70)
    gap = len([d for d in cal if first[-1] < d < later[0]])
    assert gap > 20
    report = materialise(store, None)
    assert bars_of(store, "OLD")["date"].to_list() == first  # the tail is gone
    warned = [w for w in report.warnings if w.startswith("bars_after_final_end_without_continuity")]
    assert len(warned) == 1 and warned[0].split()[1] == "OLD"  # named
    assert f"gap_trading_days={gap}" in warned[0]  # with the measured gap
    assert report.n_bars_after_final_end_without_continuity == 15


def test_same_company_tail_is_retained(store):
    """A member that left the index but kept trading: the 118,027-bar defect, pinned."""
    put_membership(store, "STAY", date(2020, 1, 1), date(2026, 1, 6))
    days = weekdays(date(2025, 12, 1), 60)  # continuous straight through the end_date
    store.write_bars_raw(raw_rows("STAY", days, 20.0))
    report = materialise(store, None)
    assert bars_of(store, "STAY")["date"].to_list() == days  # post-exit bars present
    assert not [w for w in report.warnings if w.startswith("bars_after_final_end")]
    assert report.n_bars_after_final_end_without_continuity == 0


def _gap_store(tmp_path, gap):
    """GAP trades 3 days, then is absent for exactly `gap` market days, then 5 more."""
    s = make_store(tmp_path)
    cal = weekdays(date(2026, 1, 2), 3 + gap + 5)
    put_membership(s, "GAP", date(2020, 1, 1), cal[2])
    s.write_bars_raw(
        pl.concat([raw_rows("GAP", cal[:3] + cal[3 + gap :], 30.0),
                   raw_rows("CAL", cal, 10.0)])
    )
    return s


def test_gap_threshold_boundary(tmp_path):
    for gap, retained in ((20, True), (21, False)):
        s = _gap_store(tmp_path / f"g{gap}", gap)
        report = materialise(s, None)
        warned = [w for w in report.warnings if w.startswith("bars_after_final_end")]
        assert bars_of(s, "GAP").height == (8 if retained else 3), gap
        assert bool(warned) is (not retained), gap
        if warned:
            assert f"gap_trading_days={gap}" in warned[0]


def test_holiday_run_is_not_a_gap(tmp_path):
    """Gap is counted in market days present in bars_raw, not calendar days."""
    s = make_store(tmp_path)
    cal = weekdays(date(2026, 1, 2), 30)
    shut = set(cal[5:25])  # the market is closed for 20 weekdays: nobody has bars for them
    cal = [d for d in cal if d not in shut]
    put_membership(s, "HOL", date(2020, 1, 1), cal[2])
    s.write_bars_raw(raw_rows("HOL", cal, 30.0))
    materialise(s, None)
    assert bars_of(s, "HOL").height == len(cal)


def test_rename_continuity_suppresses_the_warning(tmp_path):
    s = make_store(tmp_path, renames=[("OLD", "NEW")])
    put_membership(s, "OLD", date(2020, 1, 1), date(2026, 1, 6))
    put_membership(s, "NEW", date(2026, 1, 7), None)
    first = weekdays(date(2026, 1, 2), 3)
    later = weekdays(date(2026, 3, 2), 15)  # a 38-day gap: reassigned, but for the mapping
    s.write_bars_raw(
        pl.concat([raw_rows("OLD", first, 50.0), raw_rows("OLD", later, 50.0),
                   calendar_rows(date(2026, 1, 2), 70)])
    )
    report = materialise(s, None)
    assert bars_of(s, "OLD")["date"].to_list() == first + later
    assert not [w for w in report.warnings if w.startswith("bars_after_final_end")]
    assert report.n_bars_after_final_end_without_continuity == 0


def test_actions_after_final_end_are_not_applied(store):
    _reassigned(store)
    put_splits(store, [("OLD", date(2026, 3, 10), 4.0, "polygon")])  # the successor's split
    materialise(store, None)
    assert bars_of(store, "OLD")["close"].to_list() == [50.0] * 3


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
    # continuity suppresses the AMD-0018 2F hazard: nothing counted, nothing warned
    assert report.n_bars_after_final_end_without_continuity == 0
    assert not [w for w in report.warnings if w.startswith("bars_after_final_end")]
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


def test_quarantined_day_is_not_published(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    for d in SEAM_DAYS:
        _verdict(store, d, "ok")
    _verdict(store, SEAM_DAYS[2], "quarantined")
    report = materialise(store, None)
    assert SEAM_DAYS[2] not in bars_of(store, "QQQ1")["date"].to_list()
    assert bars_of(store, "QQQ1").height == 5
    assert report.n_days_quarantined_skipped == 1 and report.n_symbol_days_flag_excluded is None
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


def test_flagged_symbol_day_is_published(store):
    """AMD-0019 2A: a jump_unexplained flag is carried, never subtracted."""
    store.write_bars_raw(
        pl.concat([raw_rows("FLG", SEAM_DAYS, 10.0, "polygon"),
                   raw_rows("OTH", SEAM_DAYS, 20.0, "polygon")])
    )
    _flag(store, "FLG", SEAM_DAYS[3], "jump_unexplained")
    report = materialise(store, None)
    assert bars_of(store, "FLG")["date"].to_list() == SEAM_DAYS  # the flagged day is present
    assert bars_of(store, "OTH").height == 6
    joined = store.read(
        "SELECT b.date, f.flag FROM bars b JOIN bar_flags f "
        "ON f.symbol = b.symbol AND f.date = b.date WHERE b.symbol = 'FLG'"
    )
    assert joined.rows() == [(SEAM_DAYS[3], "jump_unexplained")]  # joinable, as the DESIGN says
    assert report.n_symbol_days_flag_excluded is None and report.n_days_quarantined_skipped == 0
    assert report.n_symbol_days_flagged == 1
    assert report.n_members_flagged_by_date == {SEAM_DAYS[3]: 1}


def test_no_cross_source_substitution(store):
    """Polygon flagged on D and yfinance holding D: the published row is Polygon's."""
    poly = raw_rows("MIX", SEAM_DAYS, 10.0, "polygon")
    yf = raw_rows("MIX", SEAM_DAYS, 11.0, "yfinance")  # a distinguishable close
    store.write_bars_raw(pl.concat([poly, yf]))
    _flag(store, "MIX", SEAM_DAYS[3], "jump_unexplained")
    materialise(store, None)
    out = bars_of(store, "MIX")
    assert out["date"].to_list() == SEAM_DAYS
    assert out["close"].to_list() == [10.0] * 6  # every row, the flagged day included, is Polygon's


def test_quarantine_is_not_filled_from_yfinance(store):
    store.write_bars_raw(
        pl.concat([raw_rows("MIX", SEAM_DAYS, 10.0, "polygon"),
                   raw_rows("MIX", SEAM_DAYS, 11.0, "yfinance")])
    )
    _verdict(store, SEAM_DAYS[1], "quarantined")
    materialise(store, None)
    out = bars_of(store, "MIX")
    assert out["date"].to_list() == [d for d in SEAM_DAYS if d != SEAM_DAYS[1]]
    assert set(out["close"].to_list()) == {10.0}


def test_unjudged_day_is_not_published(store):
    """AMD-0021 2C: a historic 'failed' day that holds bars_raw rows was never judged."""
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    for d in SEAM_DAYS:
        _verdict(store, d, "failed")
    materialise(store, None)
    assert bars_of(store, "QQQ1").height == 0  # asserts zero rows: a blocklist would leak them
    assert store.read("SELECT count(*) AS n FROM bars_raw")["n"][0] == 6  # CI-9


def test_only_ok_days_are_published(store):
    store.write_bars_raw(raw_rows("ALW", SEAM_DAYS, 10.0, "polygon"))
    statuses = ["ok", "quarantined", "failed", "holiday", "invented_after_the_fact"]
    for d, status in zip(SEAM_DAYS, statuses, strict=False):
        _verdict(store, d, status)
    # SEAM_DAYS[5] has NO verdict at all: no judgement against it, so it publishes (WO-0007)
    report = materialise(store, None)
    assert bars_of(store, "ALW")["date"].to_list() == [SEAM_DAYS[0], SEAM_DAYS[5]]
    assert report.n_days_quarantined_skipped == 4


def test_split_reconciled_flag_does_not_exclude(store):
    store.write_bars_raw(raw_rows("SRC", SEAM_DAYS, 10.0, "polygon"))
    _flag(store, "SRC", SEAM_DAYS[3], "jump_split_reconciled")
    report = materialise(store, None)
    assert bars_of(store, "SRC").height == 6
    assert report.n_symbol_days_flag_excluded is None


def test_day_without_verdict_is_published(store):
    # yfinance bootstrap days (and pre-backfill history) have no polygon ingest_log row
    store.write_bars_raw(raw_rows("NOV", SEAM_DAYS, 10.0, "yfinance"))
    _verdict(store, SEAM_DAYS[0], "quarantined", source="other")  # another source's verdict
    report = materialise(store, None)
    assert bars_of(store, "NOV").height == 6 and report.n_days_quarantined_skipped == 0


def test_seam_rerun_is_a_no_op(store):
    store.write_bars_raw(raw_rows("QQQ1", SEAM_DAYS, 10.0, "polygon"))
    _verdict(store, SEAM_DAYS[2], "quarantined")
    _flag(store, "QQQ1", SEAM_DAYS[4], "jump_unexplained")
    first = materialise(store, None)
    before = digest(store, "bars", "QQQ1")
    second = materialise(store, None)
    assert first.n_rows == 5 and (second.n_rows, second.n_readjusted) == (0, 0)
    assert digest(store, "bars", "QQQ1") == before
    assert second.n_days_quarantined_skipped == 1 and second.n_symbol_days_flagged == 1


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
    assert (
        "0 quarantined days not published, flagged symbol-days excluded: not computed"
        in res.output
    )
    again = runner.invoke(app, ["adjust", "materialise"])
    assert "symbols=1 rows=0 readjusted=0" in again.output
    bad = runner.invoke(app, ["adjust", "materialise", "--symbols", "AAA,not valid"])
    assert bad.exit_code == 2


# ------------------------------------------------------------------------------ dividend basis
def _basis_case(store, sym, source, amount):
    """Eight bars at 100 (fetched before a 2:1 split dated after them) and one dividend paid on
    the fifth; after the split the prior close is 50, so the dividend must be worth 0.50."""
    days = weekdays(date(2026, 3, 2), 8)
    store.write_bars_raw(raw_rows(sym, days, 100.0, source, ingested=datetime(2026, 3, 20, 6, 0)))
    put_splits(store, [(sym, date(2026, 4, 1), 2.0, source)])
    put_dividends(store, [(sym, days[4], amount, source)])
    return days


def test_as_paid_dividend_is_divided_by_cumulative_split(store):
    _basis_case(store, "ASP", "polygon", 1.00)  # as paid, pre-split share count
    _basis_case(store, "SAD", "yfinance", 0.50)  # already restated onto the split-adjusted basis
    assert stamp_dividend_basis(
        pl.DataFrame({"source": ["polygon", "yfinance"]})
    )["basis"].to_list() == ["as_paid", "split_adjusted"]
    materialise(store, None)
    asp, sad = bars_of(store, "ASP"), bars_of(store, "SAD")
    assert asp["close"].to_list() == [50.0] * 8
    # factor 1 - 0.50/50 = 0.99 for the four bars before the ex-date; an undivided 1.00 would
    # give 0.98 (49.0)
    expected = [49.5] * 4 + [50.0] * 4
    assert asp["adj_close"].to_list() == pytest.approx(expected, abs=1e-9)
    assert sad["adj_close"].to_list() == pytest.approx(expected, abs=1e-9)
    assert asp["adj_close"].to_list() == sad["adj_close"].to_list()  # same arithmetic result


def test_as_paid_dividend_after_the_split_is_not_divided():
    """Only splits dated AFTER the ex-date count (split_cum is 1 for the later bars)."""
    days = weekdays(date(2026, 3, 2), 6)
    raw = raw_rows("LAT", days, 100.0, "polygon", ingested=datetime(2026, 3, 1, 6, 0))
    splits = pl.DataFrame([("LAT", days[1], 2.0, "polygon")],
                          schema=["symbol", "date", "ratio", "source"], orient="row")
    adjusted = apply_splits(raw, splits, 1)
    divs = stamp_dividend_basis(
        pl.DataFrame([("LAT", days[4], 1.0, "polygon")],
                     schema=["symbol", "date", "cash_amount", "source"], orient="row")
    )
    adj = dividend_adjusted_close(adjusted, divs)
    # bars from days[1] on are 100 (the split took effect before them); 1/100 -> factor 0.99
    assert adj.to_list()[-1] == pytest.approx(100.0)
    assert adj.to_list()[1] == pytest.approx(99.0)


def test_unrecorded_dividend_basis_raises(store):
    bars = raw_rows("BAS", weekdays(date(2026, 3, 2), 4), 100.0)
    ex = date(2026, 3, 4)
    base = pl.DataFrame([("BAS", ex, 1.0, "polygon")],
                        schema=["symbol", "date", "cash_amount", "source"], orient="row")
    for bad in (None, "", "adjusted", "AS_PAID"):
        with pytest.raises(ValueError, match="basis"):
            dividend_adjusted_close(
                bars, base.with_columns(pl.lit(bad, dtype=pl.String).alias("basis"))
            )
    with pytest.raises(ValueError, match="basis"):  # no column at all: never defaulted
        dividend_adjusted_close(bars, base)
    # and the write path refuses a source whose basis was never measured
    with pytest.raises(ValueError, match="measured dividend basis"):
        put_dividends(store, [("BAS", ex, 1.0, "fmp")])
    assert store.read("SELECT count(*) AS n FROM dividends")["n"][0] == 0
    with pytest.raises(ValueError, match="disagrees"):
        store.upsert(
            "dividends",
            base.with_columns(pl.lit("split_adjusted").alias("basis")),
            ["symbol", "date", "source"],
        )


def _disagreement_case(store, sym, yf_amount):
    """polygon declares 1.00 as paid, pre-split; yfinance restates its amount on the post-split
    basis. A 2:1 split follows the ex-date, so the same economic dividend is 0.50 adjusted."""
    days = weekdays(date(2026, 3, 2), 8)
    store.write_bars_raw(
        raw_rows(sym, days, 100.0, "polygon", ingested=datetime(2026, 3, 20, 6, 0))
    )
    put_splits(store, [(sym, date(2026, 4, 1), 2.0, "polygon")])
    put_dividends(store, [(sym, days[4], 1.00, "polygon"), (sym, days[4], yf_amount, "yfinance")])


def test_dividend_disagreement_normalises_basis(store):
    _disagreement_case(store, "SAME", 0.50)  # same economics, two bases
    _disagreement_case(store, "DIFF", 0.52)  # a genuine two-cent difference
    report = materialise(store, None)
    found = [w for w in report.warnings if w.startswith("dividend_disagreement")]
    assert [w.split()[1] for w in found] == ["DIFF"]  # SAME raises none
    assert "polygon=0.5000 yfinance=0.5200" in found[0]  # both amounts, on one basis
    # AMD-0027 2D: 0.52 is more than a cent and 2% above 0.50, so the LARGER total is applied
    assert "total_source=yfinance" in found[0]
    same, diff = bars_of(store, "SAME")["adj_close"], bars_of(store, "DIFF")["adj_close"]
    assert diff[0] < same[0]


def test_split_on_ex_date_is_divided_out(store):
    days = weekdays(date(2026, 3, 2), 8)
    ex = days[4]
    store.write_bars_raw(raw_rows("EXD", days, 100.0, "polygon", ingested=datetime(2026, 3, 2, 6)))
    put_splits(store, [("EXD", ex, 2.0, "polygon")])  # effective ON the ex-date
    put_dividends(store, [("EXD", ex, 1.00, "polygon")])  # as paid, declared before the split
    materialise(store, None)
    out = bars_of(store, "EXD")
    assert out["close"].to_list()[:4] == [50.0] * 4 and out["close"].to_list()[4:] == [100.0] * 4
    # 1.00 / 2 = 0.50 on a prior close of 50: factor 0.99 (an undivided dividend gives 0.98)
    assert out["adj_close"].to_list()[:4] == pytest.approx([49.5] * 4, abs=1e-9)
    assert out["adj_close"].to_list()[4:] == pytest.approx([100.0] * 4, abs=1e-9)


def test_flag_excluded_count_is_never_a_silent_zero(store, clean_env, tmp_path, monkeypatch):
    store.write_bars_raw(raw_rows("FLG", SEAM_DAYS, 10.0, "polygon"))
    _flag(store, "FLG", SEAM_DAYS[3], "jump_unexplained")
    report = materialise(store, None)
    assert report.n_symbol_days_flagged == 1  # a flag exists...
    assert report.n_symbol_days_flag_excluded is None  # ...but exclusion is not computed here
    assert MaterialiseReport(1, 1, 0).n_symbol_days_flag_excluded is None  # default: not 0
    # the CLI prints both shapes
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("ARGUS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()
    assert "flagged symbol-days excluded: not computed" in runner.invoke(
        app, ["adjust", "materialise"]
    ).output
    import argus.commands.adjust_cmds as cmds

    monkeypatch.setattr(
        cmds, "materialise", lambda *_a, **_k: MaterialiseReport(1, 1, 0, [], 0, 7)
    )
    assert "flagged symbol-days excluded: 7" in runner.invoke(app, ["adjust", "materialise"]).output


# ------------------------------------------------------------------------------ DOUBLE prices
def test_prices_are_float64(store):
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["SPY", "AAA"], "gics_sector": ["ETF", "Technology"]}),
        ["symbol"],
    )
    days = weekdays(date(2026, 1, 5), 3)
    exact = 187.12345678901234  # not representable in float32 (relative error ~1e-8)
    store.write_bars_raw(
        pl.concat(
            [raw_rows("SPY", days, exact, "polygon"), raw_rows("AAA", days, exact, "polygon")]
        )
    )
    materialise(store, None)
    cols = ["open", "high", "low", "close", "volume", "adj_close"]
    for etf, sym in ((False, "AAA"), (True, "SPY")):
        out = bars_of(store, sym, etf=etf)
        assert [out.schema[c] for c in cols] == [pl.Float64] * 6
        assert out["close"].to_list() == [exact] * 3  # bit-exact round trip
        assert out["adj_close"].to_list() == [exact] * 3
        table = "etf_bars" if etf else "bars"
        on_disk = pl.read_parquet(store.parquet_dir / table / f"symbol={sym}" / "part.parquet")
        assert [on_disk.schema[c] for c in cols] == [pl.Float64] * 6
    raw_close = store.read("SELECT close FROM bars_raw WHERE symbol = 'AAA'")["close"].to_list()
    assert raw_close == [exact] * 3


# ------------------------------------------------------------------------------ membership edge
def test_membership_boundary_counts_are_separated(tmp_path):
    s = make_store(tmp_path)
    # PRE: bars start 20 days before the member joined; they are history the features need
    put_membership(s, "PRE", date(2026, 2, 2), None)
    pre_days = weekdays(date(2026, 1, 5), 30)
    n_before = len([d for d in pre_days if d < date(2026, 2, 2)])
    # OLD: delisted, and 12 bars from a successor company follow its final end_date
    put_membership(s, "OLD", date(2020, 1, 1), date(2026, 1, 6))
    s.write_bars_raw(
        pl.concat([raw_rows("PRE", pre_days, 10.0),
                   raw_rows("OLD", weekdays(date(2026, 1, 2), 3), 50.0),
                   raw_rows("OLD", weekdays(date(2026, 3, 2), 12), 5.0),
                   calendar_rows(date(2026, 1, 2), 70)])
    )
    report = materialise(s, None)
    assert bars_of(s, "PRE").height == 30  # leading history is retained
    assert report.n_bars_before_first_membership == n_before and n_before > 10
    assert report.n_bars_after_final_end_without_continuity == 12
    assert [w for w in report.warnings if "PRE" in w] == []  # pre-entry history never warns
    warned = [w for w in report.warnings if w.startswith("bars_after_final_end_without_continuity")]
    assert len(warned) == 1 and warned[0].split()[1] == "OLD"  # warned per symbol, named
    assert not any(w.startswith("bars_outside_membership") for w in report.warnings)


# ------------------------------------------------------------------------------ aggregates
def test_flagged_day_excluded_from_aggregate_not_series(store):
    days = weekdays(date(2026, 4, 6), 3)
    # AAA +10% on day 2 (flagged), BBB +2%, CCC +4%
    frames = [
        raw_rows(sym, days, 1.0).with_columns(pl.Series("close", [100.0, c1, c2]))
        for sym, c1, c2 in (("AAA", 110.0, 110.0), ("BBB", 102.0, 102.0), ("CCC", 104.0, 104.0))
    ]
    store.write_bars_raw(pl.concat(frames).with_columns(pl.col("source")))
    _flag(store, "AAA", days[1], "jump_unexplained")
    materialise(store, None)
    published = store.read_bars(None, LONG_AGO, FAR)
    assert published.filter(pl.col("symbol") == "AAA").height == 3  # the series keeps its row
    flagged = store.read("SELECT symbol, date FROM bar_flags")
    agg = equal_weight_aggregate(published, flagged).filter(pl.col("date") == days[1])
    row = agg.row(0, named=True)
    assert row["n_members_flagged"] == 1 and row["n_members_with_bars"] == 3
    assert row["n_members_included"] == 2
    assert row["eq_ret"] == pytest.approx((0.02 + 0.04) / 2)  # AAA's +10% is not in the mean
    other = equal_weight_aggregate(published, flagged).filter(pl.col("date") == days[2])
    assert other["n_members_flagged"].to_list() == [0] and other["eq_ret"][0] == pytest.approx(0.0)


# ------------------------------------------------------------------------------ schema 5 migration
def _checksum(store, table):
    h = hashlib.sha256()
    for path in sorted((store.parquet_dir / table).rglob("*.parquet")):
        h.update(path.relative_to(store.parquet_dir).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _legacy_store(tmp_path):
    """A schema-4 store: old dividends table (no basis), float32 bars, a populated bars_raw."""
    import duckdb

    s = make_store(tmp_path)
    days = weekdays(date(2026, 3, 2), 6)
    s.write_bars_raw(
        pl.concat([raw_rows("AAA", days, 12.345678901, "polygon"),
                   raw_rows("AAA", days, 12.345678901, "yfinance")])
    )
    materialise(s, None)
    path = s.parquet_dir / "bars" / "symbol=AAA" / "part.parquet"
    narrow = pl.read_parquet(path).cast(
        {c: pl.Float32 for c in ("open", "high", "low", "close", "volume", "adj_close")}
    )
    narrow.write_parquet(path)
    con = duckdb.connect(str(s.db_path))
    con.execute("DROP TABLE dividends")
    con.execute(
        "CREATE TABLE dividends (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, source TEXT, "
        "PRIMARY KEY (symbol, date, source))"
    )
    con.execute(
        "INSERT INTO dividends VALUES ('AAA', ?, 0.5, 'polygon'), ('AAA', ?, 0.25, 'yfinance')",
        [days[2], days[2]],
    )
    con.execute("DELETE FROM schema_version WHERE version >= 5")
    con.close()
    return s


def test_migrate_store_is_in_place_idempotent_and_leaves_bars_raw_alone(tmp_path):
    s = _legacy_store(tmp_path)
    raw_before = _checksum(s, "bars_raw")
    rows = {t: (b, a) for t, b, a in s.migrate()}
    assert rows["dividends"] == (2, 2) and rows["bars_raw"] == (12, 12) and rows["bars"] == (6, 6)
    got = s.read("SELECT source, basis, vendor_id FROM dividends ORDER BY source")
    assert got.rows() == [
        ("polygon", "as_paid", "legacy"),  # placeholder: the real id needs a re-ingest
        ("yfinance", "split_adjusted", "sum"),
    ]
    on_disk = pl.read_parquet(s.parquet_dir / "bars" / "symbol=AAA" / "part.parquet")
    assert set(on_disk.select(pl.exclude("symbol", "date", "adj_version")).schema.values()) == {
        pl.Float64
    }
    assert _checksum(s, "bars_raw") == raw_before  # CI-9: bars_raw is byte-identical
    versions = s.read("SELECT version FROM schema_version ORDER BY version")["version"].to_list()
    assert versions[-1] == 6
    # a second run changes nothing
    bars_sum, div_rows = _checksum(s, "bars"), s.read("SELECT * FROM dividends").rows()
    again = {t: (b, a) for t, b, a in s.migrate()}
    assert again == {t: (after, after) for t, (_before, after) in rows.items()}
    assert _checksum(s, "bars") == bars_sum and s.read("SELECT * FROM dividends").rows() == div_rows
    assert _checksum(s, "bars_raw") == raw_before
    # re-materialising from the stored data now restores full precision
    materialise(s, None)
    assert bars_of(s, "AAA")["close"].to_list() == [12.345678901] * 6


def test_migrate_store_refuses_an_unmeasured_source_and_changes_nothing(tmp_path):
    import duckdb

    s = _legacy_store(tmp_path)
    con = duckdb.connect(str(s.db_path))
    con.execute("INSERT INTO dividends VALUES ('AAA', DATE '2026-03-03', 1.0, 'fmp')")
    con.close()
    with pytest.raises(ValueError, match="measured dividend basis"):
        s.migrate()
    cols = s.read(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'dividends'"
    )["column_name"].to_list()
    assert "basis" not in cols and s.read("SELECT count(*) AS n FROM dividends")["n"][0] == 3


def test_cli_migrate_store(clean_env, tmp_path):
    s = _legacy_store(tmp_path)
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    res = CliRunner().invoke(app, ["migrate-store"])
    assert res.exit_code == 0, res.output
    assert "schema 6" in res.output and "dividends: 2 -> 2" in res.output
    assert "bars_raw: 12 -> 12" in res.output
    assert s.read("SELECT count(*) AS n FROM dividends WHERE basis IS NULL")["n"][0] == 0


def test_store_has_a_single_logging_channel():
    import argus.data.store as store_module

    assert not hasattr(store_module, "_stdlog")  # AMD-0019 2H: structlog (redacted) only


# ------------------------------------------------------------------------------ WO-0016
def _flat_bars(store, sym, n=8, close=100.0, source="polygon"):
    days = weekdays(date(2026, 3, 2), n)
    store.write_bars_raw(raw_rows(sym, days, close, source, ingested=datetime(2026, 3, 20, 6, 0)))
    return days


def _ingest_polygon_dividends(store, records):
    """Run the real ingest path (client -> ingest_polygon_actions) over a mocked payload."""
    respx.get("https://api.polygon.io/v3/reference/splits").respond(
        json={"status": "OK", "results": []}
    )
    respx.get("https://api.polygon.io/v3/reference/dividends").respond(
        json={"status": "OK", "results": records}
    )
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        return ingest_polygon_actions(store, client, date(2026, 1, 1))
    finally:
        client.close()


@respx.mock
def test_two_records_one_ex_date_both_persist_and_sum(store):
    """PGR: a quarterly 0.10 and a special 13.50 on one ex-date, BOTH dividend_type "CD" (so a
    key on the type collapses them). Both rows persist and the adjustment uses their SUM, 13.60
    (AMD-0027 2A, 2B). Prior close 100 -> factor 1 - 0.136."""
    days = _flat_bars(store, "PGR")
    ex = days[4]
    _seed_symbols(store, "PGR")
    rec = {"ticker": "PGR", "ex_dividend_date": ex.isoformat(), "dividend_type": "CD"}
    _ingest_polygon_dividends(store, [
        {**rec, "cash_amount": 0.10, "frequency": 4, "id": "id-quarterly"},
        {**rec, "cash_amount": 13.50, "frequency": 1, "id": "id-special"},
    ])
    assert store.read("SELECT count(*) AS n FROM dividends")["n"][0] == 2
    materialise(store, None)
    adj = bars_of(store, "PGR")["adj_close"].to_list()
    assert adj[:4] == pytest.approx([100.0 * (1 - 13.60 / 100.0)] * 4, abs=1e-9)
    assert adj[4:] == pytest.approx([100.0] * 4, abs=1e-9)


@respx.mock
def test_same_amount_twice_does_not_collapse(store):
    """Two records with the SAME cash_amount and different ids both persist: a key that uses the
    amount (instead of the id) would merge them."""
    days = _flat_bars(store, "TWN")
    ex = days[4]
    _seed_symbols(store, "TWN")
    rec = {"ticker": "TWN", "ex_dividend_date": ex.isoformat(), "dividend_type": "CD",
           "cash_amount": 0.50}
    _ingest_polygon_dividends(store, [{**rec, "id": "id-one"}, {**rec, "id": "id-two"}])
    assert store.read("SELECT count(*) AS n FROM dividends")["n"][0] == 2
    materialise(store, None)
    assert bars_of(store, "TWN")["adj_close"].to_list()[:4] == pytest.approx(
        [99.0] * 4, abs=1e-9  # 1 - 1.00/100, not 1 - 0.50/100
    )


def test_larger_normalised_total_wins_and_warns(store):
    """FCX: Polygon returns one 0.075 record, yfinance sums 0.15 (AMD-0027 2D)."""
    days = _flat_bars(store, "FCX")
    ex = days[4]
    put_dividends(store, [("FCX", ex, 0.075, "polygon"), ("FCX", ex, 0.15, "yfinance")])
    report = materialise(store, None)
    found = [w for w in report.warnings if w.startswith("dividend_disagreement")]
    assert len(found) == 1
    assert "polygon=0.0750 yfinance=0.1500" in found[0] and "total_source=yfinance" in found[0]
    assert bars_of(store, "FCX")["adj_close"].to_list()[:4] == pytest.approx(
        [100.0 * (1 - 0.15 / 100.0)] * 4, abs=1e-9
    )
    divs = store.read_dividends(["FCX"], LONG_AGO, FAR)
    kept, _ = resolve_dividends(divs)
    assert kept["total_source"].to_list() == ["yfinance"]
    assert kept["cash_amount"].to_list() == [0.15]


def test_basis_difference_is_not_an_omission(store):
    """The same economic dividend: 1.00 as paid (Polygon) and 0.50 split-adjusted (yfinance)
    across a 2:1 split dated after the ex-date. Compared raw it reads as a 2x gap; normalised it
    is none. No warning, and Polygon's total stands."""
    days = weekdays(date(2026, 3, 2), 8)
    store.write_bars_raw(
        raw_rows("BAS2", days, 100.0, "polygon", ingested=datetime(2026, 3, 20, 6, 0))
    )
    put_splits(store, [("BAS2", date(2026, 4, 1), 2.0, "polygon")])
    put_dividends(store, [("BAS2", days[4], 1.00, "polygon"), ("BAS2", days[4], 0.50, "yfinance")])
    report = materialise(store, None)
    assert [w for w in report.warnings if w.startswith("dividend_disagreement")] == []
    cum = lambda sym, ex: 2.0  # noqa: E731 - the one 2:1 split after the ex-date
    kept, found = resolve_dividends(
        store.read_dividends(["BAS2"], LONG_AGO, FAR), cum
    )
    assert found == [] and kept["total_source"].to_list() == ["polygon"]
    assert kept["cash_amount"].to_list() == [1.00]


def test_sub_threshold_difference_changes_nothing(store):
    """Both bands of the threshold (one cent AND 2%): each alone leaves precedence untouched."""
    ex = date(2026, 3, 5)

    def resolved(poly, yf):
        rows = [("T", ex, poly, "polygon", "p1"), ("T", ex, yf, "yfinance", "sum")]
        df = stamp_dividend_basis(
            pl.DataFrame(rows, schema=["symbol", "date", "cash_amount", "source", "vendor_id"],
                         orient="row")
        )
        return resolve_dividends(df)

    # half a cent, 1%: nothing, Polygon stands
    kept, found = resolved(0.50, 0.505)
    assert found == [] and kept["total_source"].to_list() == ["polygon"]
    assert kept["cash_amount"].to_list() == [0.50]
    # under a cent but far over 2%: still nothing
    kept, found = resolved(0.10, 0.108)
    assert found == [] and kept["total_source"].to_list() == ["polygon"]
    # over a cent but within 2%: warned (as before), precedence untouched
    kept, found = resolved(1.00, 1.015)
    assert len(found) == 1 and "total_source" not in found[0]
    assert kept["total_source"].to_list() == ["polygon"] and kept["cash_amount"].to_list() == [1.0]
    # over both: the larger total
    kept, found = resolved(1.00, 1.05)
    assert kept["total_source"].to_list() == ["yfinance"] and "total_source=yfinance" in found[0]


def test_polygon_larger_total_is_kept_without_switching(store):
    """§2D takes the larger total; a vendor-invented yfinance extra is not what it protects
    against, but a LARGER Polygon total (the usual precedence winner) simply stands."""
    ex = date(2026, 3, 5)
    df = stamp_dividend_basis(
        pl.DataFrame(
            [("T", ex, 0.20, "polygon", "p1"), ("T", ex, 0.10, "yfinance", "sum")],
            schema=["symbol", "date", "cash_amount", "source", "vendor_id"], orient="row",
        )
    )
    kept, found = resolve_dividends(df)
    assert kept["total_source"].to_list() == ["polygon"] and kept["cash_amount"].to_list() == [0.2]
    assert len(found) == 1


# ---- migration to schema 6 and the legacy placeholder
def _schema5_store(tmp_path):
    import duckdb

    s = make_store(tmp_path)
    days = weekdays(date(2026, 3, 2), 6)
    s.write_bars_raw(raw_rows("AAA", days, 12.5, "polygon"))
    con = duckdb.connect(str(s.db_path))
    con.execute("DROP TABLE dividends")
    con.execute(
        "CREATE TABLE dividends (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, "
        "basis TEXT NOT NULL CHECK (basis IN ('as_paid', 'split_adjusted')), source TEXT, "
        "PRIMARY KEY (symbol, date, source))"
    )
    con.execute(
        "INSERT INTO dividends VALUES ('AAA', ?, 0.5, 'as_paid', 'polygon'), "
        "('AAA', ?, 0.25, 'split_adjusted', 'yfinance')",
        [days[2], days[2]],
    )
    con.execute("DELETE FROM schema_version WHERE version = 6")
    con.close()
    return s


def test_migration_to_schema_6_is_idempotent_and_loses_no_rows(tmp_path):
    s = _schema5_store(tmp_path)
    raw_before = _checksum(s, "bars_raw")
    rows = {t: (b, a) for t, b, a in s.migrate()}
    assert rows["dividends"] == (2, 2) and rows["bars_raw"] == (6, 6)
    got = s.read("SELECT source, vendor_id, cash_amount FROM dividends ORDER BY source")
    assert got.rows() == [("polygon", "legacy", 0.5), ("yfinance", "sum", 0.25)]
    assert s.read("SELECT max(version) AS v FROM schema_version")["v"][0] == 6
    again = {t: (b, a) for t, b, a in s.migrate()}
    assert again == {t: (after, after) for t, (_b, after) in rows.items()}
    assert s.read("SELECT source, vendor_id FROM dividends ORDER BY source").rows() == [
        ("polygon", "legacy"), ("yfinance", "sum")
    ]
    assert _checksum(s, "bars_raw") == raw_before  # CI-9


def test_cli_migrate_store_names_the_legacy_placeholder(clean_env, tmp_path):
    _schema5_store(tmp_path)
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    res = CliRunner().invoke(app, ["migrate-store"])
    assert res.exit_code == 0, res.output
    assert "dividends: 2 -> 2" in res.output
    assert "1 polygon dividend rows hold the placeholder vendor_id 'legacy'" in res.output


def _seed_symbols(store, *syms):
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": list(syms), "active": [True] * len(syms)}),
        ["symbol"],
    )


@respx.mock
def test_real_id_rows_replace_the_legacy_placeholder_not_duplicate_it(tmp_path):
    """After the migration a Polygon row is `legacy`. Re-ingesting the date's real records must
    REPLACE it: left beside them, the ex-date sum would count the dividend twice."""
    s = make_store(tmp_path)
    _seed_symbols(s, "PGR", "OTH")
    ex, other = date(2026, 1, 2), date(2026, 2, 2)
    s.upsert("dividends", pl.DataFrame(
        {"symbol": ["PGR", "OTH"], "date": [ex, other], "cash_amount": [0.10, 0.30],
         "source": ["polygon", "polygon"], "vendor_id": ["legacy", "legacy"]}),
        ["symbol", "date", "source", "vendor_id"])
    respx.get("https://api.polygon.io/v3/reference/splits").respond(
        json={"status": "OK", "results": []})
    respx.get("https://api.polygon.io/v3/reference/dividends").respond(json={"status": "OK",
        "results": [
            {"ticker": "PGR", "ex_dividend_date": ex.isoformat(), "cash_amount": 0.10,
             "dividend_type": "CD", "id": "id-q"},
            {"ticker": "PGR", "ex_dividend_date": ex.isoformat(), "cash_amount": 13.50,
             "dividend_type": "CD", "id": "id-s"},
        ]})
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        ingest_polygon_actions(s, client, date(2026, 1, 1))
        ingest_polygon_actions(s, client, date(2026, 1, 1))  # idempotent
    finally:
        client.close()
    got = s.read("SELECT symbol, vendor_id, cash_amount FROM dividends "
                 "ORDER BY symbol, vendor_id").rows()
    assert got == [("OTH", "legacy", 0.30), ("PGR", "id-q", 0.10), ("PGR", "id-s", 13.50)]


# ---- attribute_pairs (AC1): read-only, fed a mock client
def _payload(*recs):
    return {"status": "OK", "results": [
        {"dividend_type": "CD", "frequency": 4, **r} for r in recs]}


@respx.mock
def test_attribute_pairs_collapse_omission_neither_and_basis_trap(tmp_path):
    s = make_store(tmp_path)
    ex = date(2026, 1, 2)
    put_dividends(s, [
        ("PGR", ex, 0.10, "polygon", "legacy"), ("PGR", ex, 13.60, "yfinance"),
        ("FCX", ex, 0.075, "polygon", "id-f"), ("FCX", ex, 0.15, "yfinance"),
        ("SAM", ex, 0.20, "polygon", "id-s"), ("SAM", ex, 0.20, "yfinance"),
        ("SPL", ex, 1.00, "polygon", "id-p"), ("SPL", ex, 0.50, "yfinance"),  # 2:1 after ex
    ])
    put_splits(s, [("SPL", date(2026, 4, 1), 2.0, "polygon")])
    by_ticker = {
        "PGR": _payload(
            {"ticker": "PGR", "ex_dividend_date": ex.isoformat(), "cash_amount": 0.10, "id": "a"},
            {"ticker": "PGR", "ex_dividend_date": ex.isoformat(), "cash_amount": 13.50, "id": "b"},
        ),
        "FCX": _payload(
            {"ticker": "FCX", "ex_dividend_date": ex.isoformat(), "cash_amount": 0.075, "id": "c"}
        ),
        "SAM": _payload(
            {"ticker": "SAM", "ex_dividend_date": ex.isoformat(), "cash_amount": 0.20, "id": "d"}
        ),
        "SPL": _payload(
            {"ticker": "SPL", "ex_dividend_date": ex.isoformat(), "cash_amount": 1.00, "id": "e"}
        ),
    }
    route = respx.get("https://api.polygon.io/v3/reference/dividends").mock(
        side_effect=lambda req: httpx.Response(200, json=by_ticker[req.url.params["ticker"]])
    )
    before = (s.read("SELECT * FROM dividends ORDER BY ALL").rows(),
              s.read("SELECT * FROM splits ORDER BY ALL").rows())
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        out = attribute_pairs(s, client, [(t, ex) for t in by_ticker])
    finally:
        client.close()
    assert route.call_count == 4
    verdict = dict(zip(out["symbol"], out["verdict"], strict=True))
    # SPL: 1.00 as paid across a 2:1 split is 0.50 == yfinance's 0.50, not an omission
    assert verdict == {"PGR": "collapse", "FCX": "omission", "SAM": "neither", "SPL": "neither"}
    pgr = out.filter(pl.col("symbol") == "PGR").row(0, named=True)
    assert pgr["n_records"] == 2 and pgr["ids"] == ["a", "b"] and pgr["amounts"] == [0.10, 13.50]
    assert out.filter(pl.col("symbol") == "SPL")["polygon_normalised"][0] == pytest.approx(0.50)
    after = (s.read("SELECT * FROM dividends ORDER BY ALL").rows(),
             s.read("SELECT * FROM splits ORDER BY ALL").rows())
    assert before == after  # read-only
