"""Earnings and ex-dividend events from the FMP calendars (WO-0006; PID 8.7).

`refresh_events` keeps the `events` table current for every active symbol. It
only ever upserts: rows for dates now in the past that FMP no longer returns
are left as they are, never deleted.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta

import polars as pl
import structlog

from argus.data.providers.fmp import FMPClient, ProviderUnavailable
from argus.data.store import Store
from argus.data.tickers import is_valid

SOURCE = "fmp"
EARNINGS = "earnings"
EXDIV = "exdiv"

log = structlog.get_logger()


@dataclass(frozen=True)
class EventsReport:
    n_earnings: int
    n_exdiv: int
    n_symbols_with_upcoming_earnings: int
    calls_used: int
    # Coverage travels with the aggregate (CI-8): the denominator for the figure above.
    n_active_symbols: int = 0
    # Calendars the plan did not serve (AMD-0013): a half that could not fire is named, not hidden.
    unavailable: tuple[str, ...] = field(default_factory=tuple)


def _active_symbols(store: Store) -> set[str]:
    return set(store.read("SELECT symbol FROM symbols WHERE active")["symbol"].to_list())


def refresh_events(
    store: Store,
    fmp: FMPClient,
    today: date,
    days_ahead: int = 45,
    days_back: int = 10,
) -> EventsReport:
    """Upsert earnings and ex-dividend events for active symbols in [today-back, today+ahead]."""
    start = today - timedelta(days=days_back)
    end = today + timedelta(days=days_ahead)
    active = _active_symbols(store)
    calls_before = fmp.calls_today()
    unavailable: list[str] = []

    try:
        earnings = fmp.earnings_calendar(start, end)
    except ProviderUnavailable:
        earnings = None
        unavailable.append("earnings")
    try:
        dividends = fmp.dividends_calendar(start, end)
    except ProviderUnavailable:
        dividends = None
        unavailable.append("exdiv")

    n_earnings = 0
    n_symbols = 0
    if earnings is not None:
        e = earnings.filter(pl.col("symbol").is_in(sorted(active)))
        e = e.unique(subset=["symbol", "date"], keep="last", maintain_order=True)
        out = e.select(
            "symbol",
            "date",
            pl.lit(EARNINGS).alias("type"),
            "time_of_day",
            pl.lit(SOURCE).alias("source"),
            (pl.col("confirmed") | (pl.col("date") <= today)).alias("confirmed"),
        )
        n_earnings = store.upsert("events", out, ["symbol", "date", "type"])
        n_symbols = e.filter(pl.col("date") >= today)["symbol"].n_unique()

    n_exdiv = 0
    if dividends is not None:
        d = dividends.filter(pl.col("symbol").is_in(sorted(active)))
        d = d.unique(subset=["symbol", "date"], keep="last", maintain_order=True)
        out = d.select(
            "symbol",
            "date",
            pl.lit(EXDIV).alias("type"),
            pl.lit(None, dtype=pl.String).alias("time_of_day"),
            pl.lit(SOURCE).alias("source"),
            pl.lit(True).alias("confirmed"),  # a calendar ex-date is declared, not estimated
        )
        n_exdiv = store.upsert("events", out, ["symbol", "date", "type"])

    report = EventsReport(
        n_earnings=n_earnings,
        n_exdiv=n_exdiv,
        n_symbols_with_upcoming_earnings=n_symbols,
        calls_used=fmp.calls_today() - calls_before,
        n_active_symbols=len(active),
        unavailable=tuple(unavailable),
    )
    log.info(
        "events_refreshed",
        n_earnings=report.n_earnings,
        n_exdiv=report.n_exdiv,
        n_symbols_with_upcoming_earnings=report.n_symbols_with_upcoming_earnings,
        n_active_symbols=report.n_active_symbols,
        calls_used=report.calls_used,
        unavailable=list(report.unavailable),
    )
    return report


def next_earnings(store: Store, symbol: str, on: date) -> date | None:
    """The first earnings date on or after `on`, or None when none is known."""
    if not is_valid(symbol):
        raise ValueError(f"invalid symbol: {symbol!r}")
    df = store.read(
        "SELECT MIN(date) AS d FROM events WHERE symbol = ? AND type = ? AND date >= ?",
        [symbol, EARNINGS, on],
    )
    return df["d"][0]


class _TradingCalendar:
    """Trading days from the dates present in `bars_raw` (any source); weekdays elsewhere.

    Inside the span covered by bars a missing weekday (a holiday) is not a trading day.
    Outside that span, or with no bars at all, weekdays stand in and the count is approximate.
    """

    def __init__(self, bar_dates: list[date]) -> None:
        self._dates = sorted(set(bar_dates))

    @property
    def has_bars(self) -> bool:
        return bool(self._dates)

    def count(self, after: date, upto: date) -> tuple[int, bool]:
        """Trading days d with after < d <= upto, and whether any day used the weekday fallback."""
        if upto <= after:
            return 0, not self.has_bars
        if not self._dates:
            return _weekdays(after, upto), True
        lo, hi = self._dates[0], self._dates[-1]
        n = 0
        approx = False
        # part before the covered span
        if after < lo:
            edge = min(upto, lo - timedelta(days=1))
            n += _weekdays(after, edge)
            approx = True
        # part after the covered span
        if upto > hi:
            edge = max(after, hi)
            n += _weekdays(edge, upto)
            approx = True
        # part inside the span: real bar dates
        a, b = max(after, lo - timedelta(days=1)), min(upto, hi)
        if b > a:
            n += bisect_right(self._dates, b) - bisect_right(self._dates, a)
        return n, approx


def _weekdays(after: date, upto: date) -> int:
    n = 0
    d = after + timedelta(days=1)
    while d <= upto:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def days_to_earnings(store: Store, symbols: list[str], on: date) -> pl.DataFrame:
    """[symbol, days_to_earnings, days_since_earnings, approx] in trading days.

    `days_to_earnings` counts trading days in (on, next earnings date]; `days_since_earnings`
    counts trading days in (last earnings date, on]. Either is None when unknown. `approx`
    is True when any count (or, with no bars at all, the whole result) used the weekday
    fallback instead of recorded bar dates.
    """
    bad = [s for s in symbols if not is_valid(s)]
    if bad:
        raise ValueError(f"invalid symbols: {bad[:5]}")
    cal = _TradingCalendar(store.read("SELECT DISTINCT date FROM bars_raw")["date"].to_list())
    nxt: dict[str, date] = {}
    prev: dict[str, date] = {}
    if symbols:
        ev = store.read(
            "SELECT symbol, date FROM events "
            "WHERE type = ? AND symbol IN (SELECT unnest(?)) ORDER BY symbol, date",
            [EARNINGS, symbols],
        )
        for sym, dates in ev.group_by("symbol", maintain_order=True).agg("date").iter_rows():
            i = bisect_left(dates, on)
            if i < len(dates):
                nxt[sym] = dates[i]
            j = bisect_right(dates, on)
            if j > 0:
                prev[sym] = dates[j - 1]
    rows = []
    for sym in symbols:
        to_n = since_n = None
        approx = not cal.has_bars
        if sym in nxt:
            to_n, a = cal.count(on, nxt[sym])
            approx = approx or a
        if sym in prev:
            since_n, a = cal.count(prev[sym], on)
            approx = approx or a
        rows.append(
            {
                "symbol": sym,
                "days_to_earnings": to_n,
                "days_since_earnings": since_n,
                "approx": approx,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "symbol": pl.String,
            "days_to_earnings": pl.Int64,
            "days_since_earnings": pl.Int64,
            "approx": pl.Boolean,
        },
    )
