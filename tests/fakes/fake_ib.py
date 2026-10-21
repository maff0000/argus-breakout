"""In-process IBClient for tests (WO-0008). No network, no ib_async."""

from datetime import date
from pathlib import Path

import polars as pl

from argus.data.providers.ibkr import BAR_SCHEMA, SERIES_SCHEMA, IBClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ibkr"
_BAR_COLS = list(BAR_SCHEMA)


class FakeIBClient(IBClient):
    """Serves `trades` (symbol, date, open..volume) and `iv` (symbol, date, iv30, hv30).

    `duration_days` is honoured as "the last N rows on or before `end`" (trading days).
    Every call is recorded in `calls`.
    """

    def __init__(self, trades: pl.DataFrame | None = None, iv: pl.DataFrame | None = None) -> None:
        empty_trades = pl.DataFrame(schema={"symbol": pl.String, **BAR_SCHEMA})
        empty_iv = pl.DataFrame(
            schema={"symbol": pl.String, "date": pl.Date, "iv30": pl.Float64, "hv30": pl.Float64}
        )
        self.trades = empty_trades if trades is None else trades
        self.iv = empty_iv if iv is None else iv
        self.calls: list[tuple] = []
        self.connected = False

    @classmethod
    def from_fixtures(cls) -> "FakeIBClient":
        return cls(
            pl.read_parquet(FIXTURES / "trades_sample.parquet"),
            pl.read_parquet(FIXTURES / "iv_sample.parquet"),
        )

    def connect(self) -> None:
        self.calls.append(("connect",))
        self.connected = True

    def disconnect(self) -> None:
        self.calls.append(("disconnect",))
        self.connected = False

    def daily_bars(self, symbol: str, end: date, duration_days: int, what) -> pl.DataFrame:
        self.calls.append(("daily_bars", symbol, end, duration_days, what))
        part = self.trades.filter((pl.col("symbol") == symbol) & (pl.col("date") <= end))
        return part.sort("date").tail(duration_days).select(_BAR_COLS)

    def daily_series(self, symbol: str, end: date, duration_days: int, what) -> pl.DataFrame:
        self.calls.append(("daily_series", symbol, end, duration_days, what))
        column = "iv30" if what == "OPTION_IMPLIED_VOLATILITY" else "hv30"
        part = self.iv.filter((pl.col("symbol") == symbol) & (pl.col("date") <= end))
        return (
            part.sort("date").tail(duration_days).select("date", pl.col(column).alias("value"))
            .cast(SERIES_SCHEMA)
        )
