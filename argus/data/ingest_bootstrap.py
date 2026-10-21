"""Resumable bootstrap of >= 10 years of daily history (WO-0005, PID 8.6/8.7).

Loads yfinance bars into `bars_raw` (source='yfinance', basis='split') and
splits into `splits` and dividends into `dividends` (AMD-0012). Safe to re-run:
symbols that already hold >= 95% of the expected rows are skipped, and a failing chunk
is recorded in `failed` without aborting the run.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import polars as pl
import structlog

from argus.data.providers.bootstrap import CHUNK_SIZE, DIVIDEND_VENDOR_ID
from argus.data.store import Store
from argus.data.tickers import is_valid

SOURCE = "yfinance"
COVERAGE_THRESHOLD = 0.95
# NYSE sessions per year (~252) over weekdays per year (~260).
_SESSIONS_PER_WEEKDAY = 252 / 260

log = structlog.get_logger(__name__)


@dataclass
class BootstrapResult:
    n_symbols: int = 0  # symbols for which bars were written
    n_rows: int = 0  # bars_raw rows written
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # AMD-0015 2B: CURRENT = active `symbols` rows (members + ETFs); HISTORICAL = every other
    # requested symbol (historical membership only, or unknown to `symbols`).
    current_written: int = 0
    current_failed: list[str] = field(default_factory=list)
    historical_written: int = 0
    historical_unavailable: list[str] = field(default_factory=list)


def _weekdays(start: date, end: date) -> int:
    n, d = 0, start
    while d <= end:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def expected_rows(start: date, end: date) -> int:
    return round(_weekdays(start, end) * _SESSIONS_PER_WEEKDAY)


def _default_symbols(store: Store) -> list[str]:
    df = store.read(
        "SELECT symbol FROM symbols UNION SELECT symbol FROM membership ORDER BY symbol"
    )
    return [s for s in df["symbol"].to_list() if s and is_valid(s)]


def current_cohort(store: Store, symbols: list[str]) -> set[str]:
    """The subset of `symbols` with an active `symbols` row (AMD-0015 2B CURRENT cohort).

    Anything else, including a symbol unknown to `symbols`, is HISTORICAL.
    """
    if not symbols:
        return set()
    df = store.read(
        "SELECT symbol FROM symbols WHERE active AND symbol IN (SELECT unnest(?))", [symbols]
    )
    return set(df["symbol"].to_list())


def _covered(store: Store, symbols: list[str], start: date, end: date) -> set[str]:
    need = COVERAGE_THRESHOLD * expected_rows(start, end)
    df = store.read(
        "SELECT symbol, count(*) AS n FROM bars_raw "
        "WHERE source = ? AND date >= ? AND date <= ? AND symbol IN (SELECT unnest(?)) "
        "GROUP BY symbol",
        [SOURCE, start, end, symbols],
    )
    return {r["symbol"] for r in df.iter_rows(named=True) if r["n"] >= need}


def bootstrap_history(
    store: Store,
    provider: Any,
    start: date,
    end: date,
    symbols: list[str] | None,
) -> BootstrapResult:
    if start > end:
        raise ValueError("start must not be after end")
    if symbols is None:
        wanted = _default_symbols(store)
    else:
        bad = [s for s in symbols if not is_valid(s)]
        if bad:
            raise ValueError(f"invalid symbols: {bad[:5]}")
        wanted = sorted(set(symbols))
    result = BootstrapResult()
    if not wanted:
        return result

    current = current_cohort(store, wanted)
    done = _covered(store, wanted, start, end)
    result.skipped = [s for s in wanted if s in done]
    todo = [s for s in wanted if s not in done]
    log.info("bootstrap_plan", wanted=len(wanted), skipped=len(result.skipped), todo=len(todo))

    chunks = [todo[i : i + CHUNK_SIZE] for i in range(0, len(todo), CHUNK_SIZE)]
    for n, chunk in enumerate(chunks, start=1):
        label = f"chunk {n}/{len(chunks)}"
        try:
            bars = provider.daily_bars(chunk, start, end)
            actions = provider.actions(chunk, start, end)
        except Exception as exc:  # fault isolation: the whole chunk fails, the run continues
            result.failed.extend(chunk)
            result.current_failed.extend(x for x in chunk if x in current)
            result.historical_unavailable.extend(x for x in chunk if x not in current)
            detail = f"{label}: {type(exc).__name__}: {str(exc)[:200]}"
            log.warning("bootstrap_chunk_failed", chunk=n, symbols=len(chunk), error=detail)
            store.log_ingest(end, SOURCE, 0, "failed", detail)
            continue
        bars = bars.filter(pl.col("symbol").is_in(chunk))
        got = set(bars["symbol"].to_list())
        missing = [s for s in chunk if s not in got]
        result.failed.extend(missing)
        result.current_failed.extend(x for x in missing if x in current)
        result.historical_unavailable.extend(x for x in missing if x not in current)
        result.current_written += sum(1 for x in got if x in current)
        result.historical_written += sum(1 for x in got if x not in current)
        rows = 0
        if bars.height:
            raw = bars.select(
                "symbol", "date", "open", "high", "low", "close", "volume"
            ).with_columns(
                pl.lit(provider.source).alias("source"),
                pl.lit(provider.basis).alias("basis"),
            )
            rows = store.write_bars_raw(raw)
        actions = actions.filter(pl.col("symbol").is_in(sorted(got)))
        if actions.height:
            src = pl.lit(provider.source).alias("source")
            splits = (
                actions.filter(pl.col("split_ratio").is_not_null())
                .select("symbol", "date", pl.col("split_ratio").cast(pl.Float64).alias("ratio"))
                .with_columns(src)
            )
            dividends = (
                actions.filter(pl.col("cash_dividend").is_not_null())
                .select(
                    "symbol", "date", pl.col("cash_dividend").cast(pl.Float64).alias("cash_amount")
                )
                .with_columns(src, pl.lit(DIVIDEND_VENDOR_ID).alias("vendor_id"))
            )
            store.upsert("splits", splits, ["symbol", "date", "source"])
            store.upsert("dividends", dividends, ["symbol", "date", "source", "vendor_id"])
        result.n_symbols += len(got)
        result.n_rows += rows
        detail = f"{label}: {len(got)} symbols, {actions.height} actions"
        if missing:
            detail += f", {len(missing)} without data"
        store.log_ingest(end, SOURCE, rows, "ok", detail)
        log.info("bootstrap_chunk_done", chunk=n, rows=rows, missing=len(missing))
    result.failed.sort()
    result.current_failed.sort()
    result.historical_unavailable.sort()
    return result
