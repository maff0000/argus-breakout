"""bootstrap_history tests: real YFinanceProvider over a mocked yfinance module."""

import sys
import types
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from argus.cli import app
from argus.data.ingest_bootstrap import bootstrap_history
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
    adj = store.read("SELECT * FROM adjustments WHERE source = ?", ["yfinance"])
    assert adj.height == 4
    assert adj.filter(pl.col("split_ratio").is_not_null()).height == 1
    assert adj.filter(pl.col("cash_dividend").is_not_null()).height == 3
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
