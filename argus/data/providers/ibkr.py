"""IBKR provider (WO-0008, ADR-0006): read-only daily bars and volatility series.

The seam is `IBClient`; `IBAsyncClient` implements it over `ib_async` (an optional extra,
imported lazily). Connections are always read-only. Only historical-data requests are issued;
nothing here touches orders, accounts or positions.

Pacing: IBKR allows at most 50 historical-data requests per 10 minutes. `_HistoricalPacer`
enforces that as a true sliding window (a token bucket would permit a burst plus refill).

Scale notes (verify on the paper gateway, AC1/AC5): with `useRTH=True` daily volume is in
shares; with `formatDate=2` bar timestamps are UTC epoch seconds, converted here to the
exchange (US/Eastern) calendar date.
"""

import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime
from datetime import time as dtime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import polars as pl

from argus.data.providers.base import ProviderError
from argus.data.tickers import to_provider

SOURCE = "ibkr"
BASIS_BY_WHAT = {"TRADES": "split", "ADJUSTED_LAST": "split_div"}

MAX_REQUESTS = 50
WINDOW_SECONDS = 600.0
_EXCHANGE_TZ = ZoneInfo("America/New_York")

BAR_SCHEMA = {
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
}
SERIES_SCHEMA = {"date": pl.Date, "value": pl.Float64}

BarsWhat = Literal["TRADES", "ADJUSTED_LAST"]
SeriesWhat = Literal["OPTION_IMPLIED_VOLATILITY", "HISTORICAL_VOLATILITY"]


class IBClient(Protocol):
    """What reconciliation and IV fetching need from IBKR. Symbols are canonical (PID 8.4)."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def daily_bars(
        self, symbol: str, end: date, duration_days: int, what: BarsWhat
    ) -> pl.DataFrame:
        """Columns BAR_SCHEMA (date, open, high, low, close, volume); empty if no data."""
        ...

    def daily_series(
        self, symbol: str, end: date, duration_days: int, what: SeriesWhat
    ) -> pl.DataFrame:
        """Columns SERIES_SCHEMA (date, value); empty if no data."""
        ...


class _HistoricalPacer:
    """At most `max_calls` acquisitions in any `window` seconds; sleeps when full."""

    def __init__(
        self,
        max_calls: int = MAX_REQUESTS,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_calls <= 0 or window <= 0:
            raise ValueError("max_calls and window must be positive")
        self._max = max_calls
        self._window = window
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        while self._stamps and now - self._stamps[0] >= self._window:
            self._stamps.popleft()
        if len(self._stamps) >= self._max:
            self._sleep(self._stamps[0] + self._window - now)
            now = self._clock()
            while self._stamps and now - self._stamps[0] >= self._window:
                self._stamps.popleft()
        self._stamps.append(now)


def _bar_date(value: Any) -> date:
    """IBKR bar timestamp -> exchange calendar date."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(_EXCHANGE_TZ).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class IBAsyncClient(IBClient):
    """`IBClient` over ib_async. Host, port and client id are supplied by the caller (settings)."""

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        *,
        ib: Any = None,
        pacer: _HistoricalPacer | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib = ib
        self._pacer = pacer or _HistoricalPacer()

    def connect(self) -> None:
        if self._ib is None:
            try:
                import ib_async
            except ImportError as exc:
                raise ProviderError("install extras: argus[ibkr]") from exc
            self._ib = ib_async.IB()
        try:
            self._ib.connect(self._host, self._port, clientId=self._client_id, readonly=True)
        except Exception as exc:
            raise ProviderError(f"ibkr connect failed: {type(exc).__name__}") from exc

    def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()

    def _history(self, symbol: str, end: date, duration_days: int, what: str) -> list[Any]:
        if self._ib is None:
            raise ProviderError("ibkr client is not connected")
        if duration_days <= 0:
            raise ValueError("duration_days must be positive")
        try:
            import ib_async
        except ImportError as exc:
            raise ProviderError("install extras: argus[ibkr]") from exc
        contract = ib_async.Stock(to_provider(symbol, SOURCE), "SMART", "USD")
        self._pacer.acquire()
        try:
            self._ib.qualifyContracts(contract)
            return list(
                self._ib.reqHistoricalData(
                    contract,
                    endDateTime=datetime.combine(end, dtime(23, 59, 59)),
                    durationStr=f"{duration_days} D",
                    barSizeSetting="1 day",
                    whatToShow=what,
                    useRTH=True,
                    formatDate=2,
                )
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"ibkr history failed: {type(exc).__name__}") from exc

    def daily_bars(
        self, symbol: str, end: date, duration_days: int, what: BarsWhat
    ) -> pl.DataFrame:
        if what not in BASIS_BY_WHAT:
            raise ValueError(f"unsupported bar type: {what!r}")
        rows = [
            {
                "date": _bar_date(b.date),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in self._history(symbol, end, duration_days, what)
        ]
        return pl.DataFrame(rows, schema=BAR_SCHEMA).sort("date")

    def daily_series(
        self, symbol: str, end: date, duration_days: int, what: SeriesWhat
    ) -> pl.DataFrame:
        if what not in ("OPTION_IMPLIED_VOLATILITY", "HISTORICAL_VOLATILITY"):
            raise ValueError(f"unsupported series type: {what!r}")
        rows = [
            {"date": _bar_date(b.date), "value": float(b.close)}
            for b in self._history(symbol, end, duration_days, what)
        ]
        return pl.DataFrame(rows, schema=SERIES_SCHEMA).sort("date")
