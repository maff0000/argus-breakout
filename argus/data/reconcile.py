"""IBKR reconciliation and implied volatility (WO-0008, DESIGN 3.3, AMD-0019).

Reads `bars` and writes only `reconcile_log` and `iv_daily`. Nothing here mutates `bars`,
`bars_raw`, `splits` or `dividends` (AMD-0012).
"""

from dataclasses import dataclass
from datetime import date

import polars as pl
import structlog

from argus.data.providers.ibkr import SOURCE, IBClient
from argus.data.store import Store

CLOSE_TOLERANCE = 0.001  # 0.1% relative
VOLUME_TOLERANCE = 0.10  # 10% relative

_LOG_SCHEMA = {
    "date": pl.Date,
    "symbol": pl.String,
    "field": pl.String,
    "ours": pl.Float64,
    "theirs": pl.Float64,
    "pct_diff": pl.Float64,
    "breach": pl.Boolean,
}
_IV_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "iv30": pl.Float64,
    "hv30": pl.Float64,
    "source": pl.String,
}
_COMPARED = (("close", CLOSE_TOLERANCE), ("volume", VOLUME_TOLERANCE))

log = structlog.get_logger()


@dataclass(frozen=True)
class ReconcileReport:
    n_symbols: int
    n_fields: int  # rows written to reconcile_log, 'missing' rows included
    n_breaches: int
    breach_rate: float  # n_breaches / n_fields (0.0 when nothing was compared)
    rows: pl.DataFrame


def choose_sample(
    members: list[str], on: date, n: int = 20, priority: list[str] | None = None
) -> list[str]:
    """Deterministic rotating sample of `n` members for `on`.

    Sorted members, offset = (ordinal(on) * n) % len. `priority` symbols that are members
    (AMD-0019 2A: unresolved `jump_unexplained` flags) come first; the rotation fills the rest.
    The offset ignores `priority`, so the rotation advances as if the full sample were drawn.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    ordered = sorted(set(members))
    if not ordered:
        return []
    member_set = set(ordered)
    out: list[str] = []
    for sym in priority or []:
        if sym in member_set and sym not in out:
            out.append(sym)
    out = out[:n]
    taken = set(out)
    offset = (on.toordinal() * n) % len(ordered)
    for i in range(len(ordered)):
        if len(out) >= n:
            break
        sym = ordered[(offset + i) % len(ordered)]
        if sym not in taken:
            out.append(sym)
            taken.add(sym)
    return out


def _compare(ours: float | None, theirs: float | None, tol: float) -> tuple[float | None, bool]:
    """(pct_diff in percent of theirs, breach). A missing value is a breach."""
    if ours is None or theirs is None:
        return None, True
    diff = abs(ours - theirs)
    if theirs == 0:
        return (0.0, False) if diff == 0 else (None, True)
    return (ours - theirs) / theirs * 100.0, diff > tol * abs(theirs)


def reconcile_day(
    store: Store, client: IBClient, on: date, sample: list[str], lookback_days: int = 5
) -> ReconcileReport:
    """Compare `bars` close/volume with IBKR TRADES bars; log every comparison.

    Compared on the intersection of dates of the IBKR window ending `on`. A symbol with no
    comparable dates is logged as field='missing' (dated `on`), breach=True.
    """
    out: list[dict] = []
    for symbol in sample:
        theirs = client.daily_bars(symbol, on, lookback_days, "TRADES")
        ours = (
            store.read_bars([symbol], theirs["date"].min(), on) if theirs.height else theirs.clear()
        )
        joined = ours.join(theirs, on="date", how="inner", suffix="_ib").sort("date")
        if joined.is_empty():
            out.append(_row(on, symbol, "missing", None, None, None, True))
            continue
        for rec in joined.iter_rows(named=True):
            for field, tol in _COMPARED:
                pct, breach = _compare(rec[field], rec[f"{field}_ib"], tol)
                out.append(
                    _row(rec["date"], symbol, field, rec[field], rec[f"{field}_ib"], pct, breach)
                )
    rows = pl.DataFrame(out, schema=_LOG_SCHEMA)
    store.upsert("reconcile_log", rows, ["date", "symbol", "field"])
    n_breaches = int(rows["breach"].sum()) if rows.height else 0
    report = ReconcileReport(
        n_symbols=len(sample),
        n_fields=rows.height,
        n_breaches=n_breaches,
        breach_rate=n_breaches / rows.height if rows.height else 0.0,
        rows=rows,
    )
    log.info(
        "reconcile_day",
        on=on.isoformat(),
        symbols=report.n_symbols,
        fields=report.n_fields,
        breaches=report.n_breaches,
    )
    return report


def _row(d, symbol, field, ours, theirs, pct, breach) -> dict:
    return {
        "date": d,
        "symbol": symbol,
        "field": field,
        "ours": ours,
        "theirs": theirs,
        "pct_diff": pct,
        "breach": breach,
    }


def fetch_iv(store: Store, client: IBClient, on: date, symbols: list[str], days: int = 5) -> int:
    """Upsert iv30 / hv30 for the last `days` days ending `on` into iv_daily; returns rows."""
    frames: list[pl.DataFrame] = []
    for symbol in symbols:
        iv = client.daily_series(symbol, on, days, "OPTION_IMPLIED_VOLATILITY")
        hv = client.daily_series(symbol, on, days, "HISTORICAL_VOLATILITY")
        merged = iv.rename({"value": "iv30"}).join(
            hv.rename({"value": "hv30"}), on="date", how="full", coalesce=True
        )
        frames.append(
            merged.filter(pl.col("iv30").is_not_null() | pl.col("hv30").is_not_null()).with_columns(
                pl.lit(symbol).alias("symbol"), pl.lit(SOURCE).alias("source")
            )
        )
    if not frames:
        return 0
    df = pl.concat(frames).select(list(_IV_SCHEMA)).cast(_IV_SCHEMA)
    written = store.upsert("iv_daily", df, ["symbol", "date"])
    log.info("fetch_iv", on=on.isoformat(), symbols=len(symbols), rows=written)
    return written
