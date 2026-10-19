"""Polygon ingestion (WO-0004): daily bars into bars_raw, splits/dividends into adjustments."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import polars as pl
import structlog

from argus.data.providers.base import ProviderError
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store
from argus.data.validate import validate_day

SOURCE = "polygon"
_PRIOR_WINDOW_DAYS = 14

log = structlog.get_logger()


@dataclass(frozen=True)
class IngestResult:
    rows: int
    status: Literal["ok", "rejected", "failed", "holiday"]
    detail: str = ""


def _finish(store: Store, d: date, result: IngestResult) -> IngestResult:
    store.log_ingest(d, SOURCE, result.rows, result.status, result.detail)
    log.info(
        "ingest_polygon_day",
        date=d.isoformat(),
        status=result.status,
        rows=result.rows,
        detail=result.detail,
    )
    return result


def _prior_close(store: Store, d: date) -> pl.DataFrame:
    return store.read(
        "SELECT symbol, close FROM bars_raw WHERE source = ? AND date < ? AND date >= ? "
        "QUALIFY row_number() OVER (PARTITION BY symbol ORDER BY date DESC) = 1",
        [SOURCE, d, d - timedelta(days=_PRIOR_WINDOW_DAYS)],
    )


def ingest_polygon_day(store: Store, client: PolygonClient, d: date) -> IngestResult:
    try:
        raw = client.grouped_daily(d)
    except ProviderError as exc:
        return _finish(store, d, IngestResult(0, "failed", f"provider error: {exc}"))
    except Exception as exc:  # noqa: BLE001 - logged as failed, never raised past the log row
        return _finish(store, d, IngestResult(0, "failed", f"{type(exc).__name__}: {exc}"))
    if raw.is_empty():
        return _finish(store, d, IngestResult(0, "holiday", "empty grouped-daily response"))
    try:
        sym = store.read("SELECT symbol, gics_industry_group FROM symbols")
        bars = raw.filter(pl.col("symbol").is_in(sym["symbol"].to_list()))
        members = store.members_on(d)
        splits_today = set(
            store.read(
                "SELECT symbol FROM adjustments "
                "WHERE date = ? AND split_ratio IS NOT NULL AND split_ratio <> 1",
                [d],
            )["symbol"].to_list()
        )
        result = validate_day(bars, members, _prior_close(store, d), splits_today, sym)
        if not result.ok:
            return _finish(store, d, IngestResult(0, "rejected", "; ".join(result.reasons)))
        written = store.write_bars_raw(
            bars.select("symbol", "date", "open", "high", "low", "close", "volume").with_columns(
                pl.lit(client.source).alias("source"), pl.lit(client.basis).alias("basis")
            )
        )
        detail = (
            f"members={len(members)} coverage={result.coverage:.4f} "
            f"dropped_tickers={client.last_dropped}"
        )
        return _finish(store, d, IngestResult(written, "ok", detail))
    except Exception as exc:  # noqa: BLE001 - recorded as failed in ingest_log
        return _finish(store, d, IngestResult(0, "failed", f"{type(exc).__name__}: {exc}"))


def backfill_polygon(
    store: Store, client: PolygonClient, start: date, end: date
) -> list[IngestResult]:
    """Ingest every weekday in [start, end] not already ok/holiday in ingest_log."""
    done = set(
        store.read(
            "SELECT DISTINCT date FROM ingest_log WHERE source = ? AND status IN ('ok', 'holiday')",
            [SOURCE],
        )["date"].to_list()
    )
    results: list[IngestResult] = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in done:
            results.append(ingest_polygon_day(store, client, d))
        d += timedelta(days=1)
    return results


def ingest_polygon_actions(store: Store, client: PolygonClient, since: date) -> int:
    """Upsert splits and dividends (for symbols in `symbols`) into adjustments."""
    known = store.read("SELECT symbol FROM symbols")["symbol"].to_list()
    splits = client.splits(since).filter(pl.col("symbol").is_in(known))
    divs = client.dividends(since).filter(pl.col("symbol").is_in(known))
    splits = splits.unique(subset=["symbol", "date"], keep="last", maintain_order=True)
    divs = divs.unique(subset=["symbol", "date"], keep="last", maintain_order=True)
    merged = splits.join(divs, on=["symbol", "date"], how="full", coalesce=True).with_columns(
        pl.lit(SOURCE).alias("source")
    )
    n = store.upsert(
        "adjustments", merged.select("symbol", "date", "split_ratio", "cash_dividend", "source"),
        ["symbol", "date"],
    )
    log.info("ingest_polygon_actions", since=since.isoformat(), rows=n)
    return n
