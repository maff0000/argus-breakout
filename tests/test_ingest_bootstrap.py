"""bootstrap_history tests: real YFinanceProvider over a mocked yfinance module."""

import math
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from argus.cli import app
from argus.commands.ingest_bootstrap import meets_threshold
from argus.data.ingest_bootstrap import (
    COVERAGE_THRESHOLD,
    BootstrapResult,
    bootstrap_history,
    expected_rows,
)
from argus.data.providers.bootstrap import YFinanceProvider
from argus.data.store import Store

pd = pytest.importorskip("pandas")

FIXTURES = Path(__file__).parent / "fixtures" / "bootstrap"
START, END = date(2024, 1, 2), date(2024, 3, 25)


def _wide(fixture: str, tickers: list[str]):
    long = pl.read_parquet(FIXTURES / fixture).filter(pl.col("Ticker").is_in(tickers))
    if long.is_empty():
        return pd.DataFrame()
    pdf = long.to_pandas()
    pdf["Date"] = pd.to_datetime(pdf["Date"])
    return pdf.pivot(index="Date", columns="Ticker").swaplevel(axis=1).sort_index(axis=1)


@pytest.fixture
def calls(monkeypatch):
    log: list[list[str]] = []

    def download(tickers, **kwargs):
        log.append(list(tickers))
        if "BOOM" in tickers:
            raise RuntimeError("down")
        return _wide("yf_actions_sample.parquet", list(tickers))

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    return log


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "store")
    s.init_schema()
    s.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["AAA", "BBB", "BRK.B"], "active": [True] * 3}),
        ["symbol"],
    )
    return s


def _provider():
    return YFinanceProvider(pause_s=0)


def test_loads_bars_actions_and_log(store, calls):
    res = bootstrap_history(store, _provider(), START, END, None)
    assert (res.n_symbols, res.n_rows, res.failed, res.skipped) == (3, 180, [], [])
    bars = store.read_bars_raw(None, START, END, "yfinance")
    assert bars.height == 180
    assert set(bars["basis"].unique()) == {"split"}
    # AMD-0012: splits -> `splits`, dividends -> `dividends` (was one `adjustments` table)
    splits = store.read_splits(None, START, END)
    assert splits.select("symbol", "date", "ratio", "source").rows() == [
        ("AAA", date(2024, 2, 1), 4.0, "yfinance")
    ]
    divs = store.read_dividends(None, START, END)
    assert divs.height == 3 and set(divs["source"]) == {"yfinance"}
    assert sorted(divs["cash_amount"].to_list()) == [0.25, 0.25, 0.25]
    log = store.read("SELECT source, rows, status FROM ingest_log")
    assert log.rows() == [("yfinance", 180, "ok")]


def test_resumable_skips_complete_symbols(store, calls):
    first = bootstrap_history(store, _provider(), START, END, ["AAA"])
    assert first.n_symbols == 1 and first.skipped == []
    calls.clear()

    second = bootstrap_history(store, _provider(), START, END, None)
    assert second.skipped == ["AAA"]
    assert second.n_symbols == 2
    assert calls and all("AAA" not in c for c in calls)  # provider called with fewer symbols
    assert {t for c in calls for t in c} == {"BBB", "BRK-B"}
    calls.clear()

    third = bootstrap_history(store, _provider(), START, END, None)
    assert third.skipped == ["AAA", "BBB", "BRK.B"]
    assert third.n_rows == 0 and calls == []  # nothing left: provider never called


def test_failed_symbol_does_not_abort_run(store, calls, monkeypatch):
    monkeypatch.setattr("argus.data.ingest_bootstrap.CHUNK_SIZE", 1)
    monkeypatch.setattr("argus.data.providers.bootstrap.CHUNK_SIZE", 1)
    real = sys.modules["yfinance"].download

    def download(tickers, **kwargs):
        if "BBB" in tickers:
            raise RuntimeError("down")
        return real(tickers, **kwargs)

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    res = bootstrap_history(store, _provider(), START, END, None)
    assert res.failed == ["BBB"]
    assert res.n_symbols == 2 and res.n_rows == 120
    written = store.read("SELECT DISTINCT symbol FROM bars_raw ORDER BY symbol")["symbol"]
    assert [s for s in written.to_list() if s != "_EMPTY_"] == ["AAA", "BRK.B"]
    log = store.read("SELECT status FROM ingest_log ORDER BY status")["status"].to_list()
    assert log == ["failed", "ok", "ok"]


def test_symbol_without_data_is_failed(store, calls):
    store.upsert("symbols", pl.DataFrame({"symbol": ["ZZZ"], "active": [True]}), ["symbol"])
    res = bootstrap_history(store, _provider(), START, END, None)
    assert res.failed == ["ZZZ"] and res.n_symbols == 3


def test_membership_symbols_included_and_bad_symbols_rejected(store, calls):
    store.upsert(
        "membership",
        pl.DataFrame(
            {"symbol": ["AAA"], "start_date": [date(2020, 1, 1)], "end_date": [None],
             "source": ["t"]}
        ),
        ["symbol", "start_date"],
    )
    res = bootstrap_history(store, _provider(), START, END, None)
    assert res.n_symbols == 3  # AAA deduplicated across symbols and membership
    with pytest.raises(ValueError):
        bootstrap_history(store, _provider(), START, END, ["bad symbol"])


def test_cli_bootstrap(clean_env, tmp_path, calls):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    runner = CliRunner()
    assert runner.invoke(app, ["init-store"]).exit_code == 0
    res = runner.invoke(
        app,
        ["ingest", "bootstrap", "--start", "2024-01-02", "--end", "2024-03-25",
         "--symbols", "AAA,BRK.B"],
    )
    assert res.exit_code == 0, res.output
    assert "symbols=2 rows=120 skipped=0 failed=0" in res.output
    bad = runner.invoke(app, ["ingest", "bootstrap", "--start", "nope"])
    assert bad.exit_code != 0


# ------------------------------------------------ AMD-0012: same-date split + dividend
def test_same_date_split_and_dividend_retain_both(store, monkeypatch):
    """A split and a dividend on one (symbol, date) land in separate tables and both survive.

    Fails if both were written to one table keyed (symbol, date) with nullable measures
    (the pre-AMD-0012 defect), or if either write is dropped.
    """
    wide = _wide("yf_actions_sample.parquet", ["AAA"])
    day = pd.Timestamp("2024-01-17")  # fixture: AAA dividend 0.25 on this day
    wide.loc[day, ("AAA", "Stock Splits")] = 4.0
    monkeypatch.setitem(
        sys.modules, "yfinance", types.SimpleNamespace(download=lambda tickers, **kw: wide)
    )
    bootstrap_history(store, _provider(), START, END, ["AAA"])
    same = date(2024, 1, 17)
    assert store.read_splits(["AAA"], same, same).select("ratio", "source").rows() == [
        (4.0, "yfinance")
    ]
    assert store.read_dividends(["AAA"], same, same).select("cash_amount", "source").rows() == [
        (0.25, "yfinance")
    ]
    # re-running must not duplicate or lose either row (idempotent upsert on the 3-part key)
    bootstrap_history(store, _provider(), date(2024, 1, 2), date(2024, 3, 25), ["AAA"])
    assert store.read_splits(["AAA"], START, END).height == 2
    assert store.read_dividends(["AAA"], START, END).height == 1


# ---------------------------------------------------------------- resume rule: both directions
def _seed_bars(store, symbol, n, source="yfinance", first=START):
    """Write n weekday bars for `symbol` starting at `first`."""
    days, d = [], first
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    store.write_bars_raw(
        pl.DataFrame(
            {
                "symbol": symbol,
                "date": days,
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100.0,
                "source": source,
                "basis": "split",
            }
        )
    )


def _need() -> int:
    return math.ceil(COVERAGE_THRESHOLD * expected_rows(START, END))


def test_resume_skips_symbol_with_complete_data(store, calls):
    """Skips a symbol holding exactly the 95% minimum.

    Mutation that breaks it: tighten `>= need` to `>= need + 1` in `_covered` (the boundary
    symbol is re-downloaded) or make `_covered` return an empty set (nothing is ever skipped).
    """
    _seed_bars(store, "AAA", _need())
    res = bootstrap_history(store, _provider(), START, END, ["AAA"])
    assert res.skipped == ["AAA"] and res.n_symbols == 0 and calls == []


def test_resume_does_not_skip_symbol_with_incomplete_data(store, calls):
    """Re-downloads a symbol one row short of the minimum, and ignores non-qualifying rows.

    Mutations that break it: lower COVERAGE_THRESHOLD to ~0 or `>= need` to `>= need - 1`
    (short symbol skipped); drop the `source = ?` filter (BBB's other-source rows count);
    drop the date-range filter (CCC's out-of-range rows count).
    """
    _seed_bars(store, "AAA", _need() - 1)  # one row short
    _seed_bars(store, "BBB", _need() + 10, source="polygon")  # plenty, but wrong source
    _seed_bars(store, "BRK.B", _need() + 10, first=date(2022, 1, 3))  # plenty, out of range
    res = bootstrap_history(store, _provider(), START, END, ["AAA", "BBB", "BRK.B"])
    assert res.skipped == []
    assert res.n_symbols == 3
    assert {t for c in calls for t in c} == {"AAA", "BBB", "BRK-B"}


# ---------------------------------------------------------------- exit threshold (AMD-0012)
@pytest.mark.parametrize(
    ("written", "failed", "ok"),
    [
        (98, 2, True),  # exactly 98%: passes
        (49, 1, True),  # 98% on a small run
        (97, 3, False),  # 97%: just below
        (48, 2, False),  # 96%
        (100, 0, True),
        (0, 0, True),  # nothing requested
        (0, 5, False),
    ],
)
def test_meets_threshold_boundary(written, failed, ok):
    """Fails if the comparison is `>`/`<` flipped or the percentage drifts from 98."""
    assert meets_threshold(written, failed) is ok


@pytest.mark.parametrize(("written", "failed", "code"), [(98, 2, 0), (97, 3, 1)])
def test_cli_exit_code_at_threshold(clean_env, tmp_path, monkeypatch, written, failed, code):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    names = [f"F{i}" for i in range(failed)]
    monkeypatch.setattr(
        "argus.commands.ingest_bootstrap.bootstrap_history",
        lambda *a, **k: BootstrapResult(n_symbols=written, n_rows=1, failed=names),
    )
    res = CliRunner().invoke(app, ["ingest", "bootstrap", "--start", "2024-01-02"])
    assert res.exit_code == code, res.output
    assert "failed: " + ",".join(names) in res.output  # failed list reported either way
