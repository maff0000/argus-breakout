"""YFinanceProvider tests: yfinance is mocked at the module boundary (no network)."""

import sys
import types
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from argus.data.providers.base import CANONICAL_BAR_COLUMNS, ProviderError
from argus.data.providers.bootstrap import YFinanceProvider

pd = pytest.importorskip("pandas")

FIXTURES = Path(__file__).parent / "fixtures" / "bootstrap"
START, END = date(2024, 1, 2), date(2024, 3, 25)
SYMBOLS = ["AAA", "BBB", "BRK.B"]


def _wide(fixture: str, tickers: list[str]):
    """Rebuild the yfinance download shape: DatetimeIndex, columns (ticker, field)."""
    long = pl.read_parquet(FIXTURES / fixture).filter(pl.col("Ticker").is_in(tickers))
    if long.is_empty():
        return pd.DataFrame()
    pdf = long.to_pandas()
    pdf["Date"] = pd.to_datetime(pdf["Date"])
    wide = pdf.pivot(index="Date", columns="Ticker").swaplevel(axis=1).sort_index(axis=1)
    return wide


def install_fake_yfinance(monkeypatch, fixture: str, calls: list | None = None, fail=None):
    def download(tickers, **kwargs):
        if calls is not None:
            calls.append({"tickers": list(tickers), **kwargs})
        if fail is not None:
            fail(tickers)
        return _wide(fixture, list(tickers))

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))


def test_canonical_columns_from_fixture(monkeypatch):
    calls: list = []
    install_fake_yfinance(monkeypatch, "yf_download_sample.parquet", calls)
    out = YFinanceProvider(pause_s=0).daily_bars(SYMBOLS, START, END)
    assert out.columns == [*CANONICAL_BAR_COLUMNS, "adj_close"]
    assert set(out["symbol"].unique()) == set(SYMBOLS)  # BRK-B -> BRK.B
    assert out.schema["date"] == pl.Date
    assert all(out.schema[c] == pl.Float64 for c in [*CANONICAL_BAR_COLUMNS[2:], "adj_close"])
    assert out.filter(pl.col("symbol") == "BRK.B").height == 60
    assert calls[0]["tickers"] == ["AAA", "BBB", "BRK-B"]
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["actions"] is True
    assert calls[0]["threads"] is False


def test_nan_rows_dropped_and_counted(monkeypatch):
    install_fake_yfinance(monkeypatch, "yf_download_sample.parquet")
    provider = YFinanceProvider(pause_s=0)
    out = provider.daily_bars(SYMBOLS, START, END)
    assert out.height == 178
    assert out.filter(pl.col("symbol") == "BBB").height == 58
    assert provider.nan_rows_dropped == 2
    assert out.drop_nulls().height == out.height


def test_actions_split_and_dividends(monkeypatch):
    install_fake_yfinance(monkeypatch, "yf_actions_sample.parquet")
    out = YFinanceProvider(pause_s=0).actions(SYMBOLS, START, END)
    assert out.columns == ["symbol", "date", "split_ratio", "cash_dividend"]
    splits = out.filter(pl.col("split_ratio").is_not_null())
    assert splits.rows() == [("AAA", date(2024, 2, 1), 4.0, None)]
    divs = out.filter(pl.col("cash_dividend").is_not_null()).sort("symbol", "date")
    assert divs.select("symbol", "date", "cash_dividend").rows() == [
        ("AAA", date(2024, 1, 17), 0.25),
        ("BBB", date(2024, 2, 14), 0.25),
        ("BBB", date(2024, 3, 13), 0.25),
    ]
    assert out.height == 4


def test_missing_dependency_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", None)  # import raises ImportError
    with pytest.raises(ProviderError, match=r"install extras: argus\[bootstrap\]"):
        YFinanceProvider(pause_s=0).daily_bars(["AAA"], START, END)
    with pytest.raises(ProviderError, match=r"argus\[bootstrap\]"):
        YFinanceProvider(pause_s=0).actions(["AAA"], START, END)


def test_missing_symbol_is_absent_not_fatal(monkeypatch):
    install_fake_yfinance(monkeypatch, "yf_download_sample.parquet")
    out = YFinanceProvider(pause_s=0).daily_bars(["AAA", "ZZZ"], START, END)
    assert set(out["symbol"].unique()) == {"AAA"}


def test_renamed_columns_tolerated(monkeypatch):
    def download(tickers, **kwargs):
        wide = _wide("yf_download_sample.parquet", list(tickers))
        return wide.rename(columns={"Close": "Settle"}, level=1)  # required column gone

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    out = YFinanceProvider(pause_s=0).daily_bars(["AAA"], START, END)
    assert out.is_empty()
    assert out.columns == [*CANONICAL_BAR_COLUMNS, "adj_close"]


def test_one_retry_per_chunk_then_provider_error(monkeypatch):
    attempts: list = []

    def flaky_then_ok(tickers):
        if len(attempts) == 1:
            raise RuntimeError("transient")

    install_fake_yfinance(monkeypatch, "yf_download_sample.parquet", attempts, fail=flaky_then_ok)
    out = YFinanceProvider(pause_s=0).daily_bars(["AAA"], START, END)
    assert len(attempts) == 2 and out.height == 60

    attempts.clear()

    def always(tickers):
        raise RuntimeError("down")

    install_fake_yfinance(monkeypatch, "yf_download_sample.parquet", attempts, fail=always)
    with pytest.raises(ProviderError):
        YFinanceProvider(pause_s=0).daily_bars(["AAA"], START, END)
    assert len(attempts) == 2
