"""Polygon ingestion (WO-0004): bars into bars_raw, splits and dividends into their tables."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import polars as pl
import structlog

from argus.data.providers.base import ProviderError
from argus.data.providers.polygon import PolygonClient
from argus.data.schema import LEGACY_VENDOR_ID
from argus.data.store import Store
from argus.data.validate import validate_day

SOURCE = "polygon"
_PRIOR_WINDOW_DAYS = 14

log = structlog.get_logger()


@dataclass(frozen=True)
class IngestResult:
    rows: int
    status: Literal["ok", "quarantined", "holiday", "failed"]
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
    """Each symbol's latest stored close before `d`, whatever verdict that day received.

    Reads bars_raw, which holds every fetched row (CI-9), so no verdict can reach the next
    day's comparison (AMD-0018 2A, D2). A symbol absent on the previous day falls back to its
    last stored close inside the window, so a thin day does not blind the day after it.
    """
    return store.read(
        "SELECT symbol, close FROM bars_raw WHERE source = ? AND date < ? AND date >= ? "
        "QUALIFY row_number() OVER (PARTITION BY symbol ORDER BY date DESC) = 1",
        [SOURCE, d, d - timedelta(days=_PRIOR_WINDOW_DAYS)],
    )


def _is_first_date(store: Store, d: date) -> bool:
    """True only when bars_raw holds no earlier row for this source (AMD-0017 2B)."""
    n = store.read(
        "SELECT count(*) AS n FROM bars_raw WHERE source = ? AND date < ?", [SOURCE, d]
    )["n"][0]
    return n == 0


def _write_flags(store: Store, d: date, flags: pl.DataFrame) -> None:
    """Replace this day's bar_flags (a re-judgement supersedes the previous one), atomically."""
    con = store.connect()
    try:
        con.execute("BEGIN")
        try:
            con.execute("DELETE FROM bar_flags WHERE date = ? AND source = ?", [d, SOURCE])
            if not flags.is_empty():
                df = flags.with_columns(pl.lit(d).alias("date"), pl.lit(SOURCE).alias("source"))
                df = df.select("symbol", "date", "source", "flag", "detail")
                con.register("incoming_flags", df.to_arrow())
                try:
                    con.execute(
                        "INSERT INTO bar_flags SELECT symbol, date, source, flag, detail "
                        "FROM incoming_flags"
                    )
                finally:
                    con.unregister("incoming_flags")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def _judge(store: Store, d: date, bars: pl.DataFrame, extra: str = "") -> IngestResult:
    """Run validate_day over `bars` (already stored), record flags and the ingest_log verdict."""
    sym = store.read("SELECT symbol, gics_industry_group FROM symbols")
    members = store.members_on(d)
    splits_today = dict(
        store.read(
            "SELECT symbol, ratio FROM splits WHERE date = ? AND ratio <> 1 ORDER BY source",
            [d],
        ).iter_rows()
    )
    # "Current" = has an open membership interval (end_date IS NULL); only these must be
    # classified (AMD-0016 2C). Historical-only members are counted, never quarantining.
    open_symbols = set(
        store.read("SELECT DISTINCT symbol FROM membership WHERE end_date IS NULL")[
            "symbol"
        ].to_list()
    )
    result = validate_day(
        bars,
        members,
        _prior_close(store, d),
        splits_today,
        sym,
        _is_first_date(store, d),
        current_members=open_symbols,
    )
    _write_flags(store, d, result.flags)
    summary = (
        f"members={len(members)} coverage={result.coverage:.4f}{extra} "
        f"unclassified={result.n_unclassified_members} "
        f"jump_unexplained={result.n_jump_unexplained} "
        f"jump_reconciled={result.n_jump_reconciled} flags={result.flags.height} "
        f"jump_rule_applied={result.jump_rule_applied}"
    )
    if result.ok:
        return _finish(store, d, IngestResult(bars.height, "ok", summary))
    detail = "; ".join(result.reasons) + " | " + summary
    return _finish(store, d, IngestResult(bars.height, "quarantined", detail))


def ingest_polygon_day(store: Store, client: PolygonClient, d: date) -> IngestResult:
    """Fetch one day, store EVERY fetched row, then judge it (CI-9, AMD-0018 2A)."""
    try:
        raw = client.grouped_daily(d)
    except ProviderError as exc:
        return _finish(store, d, IngestResult(0, "failed", f"provider error: {exc}"))
    except Exception as exc:  # noqa: BLE001 - logged as failed, never raised past the log row
        return _finish(store, d, IngestResult(0, "failed", f"{type(exc).__name__}: {exc}"))
    if raw.is_empty():
        return _finish(store, d, IngestResult(0, "holiday", "empty grouped-daily response"))
    try:
        known = store.read("SELECT symbol FROM symbols")["symbol"].to_list()
        bars = raw.filter(pl.col("symbol").is_in(known))
        # Stored BEFORE validation: no verdict may prevent a fetched row being stored.
        store.write_bars_raw(
            bars.select("symbol", "date", "open", "high", "low", "close", "volume").with_columns(
                pl.lit(client.source).alias("source"), pl.lit(client.basis).alias("basis")
            )
        )
    except Exception as exc:  # noqa: BLE001 - nothing (reliably) stored: 'failed' is retried
        return _finish(store, d, IngestResult(0, "failed", f"{type(exc).__name__}: {exc}"))
    try:
        return _judge(store, d, bars, extra=f" dropped_tickers={client.last_dropped}")
    except Exception as exc:  # noqa: BLE001 - the rows ARE stored and unpublished: quarantined
        # AMD-0019 2E: 'failed' is reserved for nothing-fetched, so the backfill never re-fetches
        # rows it already holds.
        detail = f"judging failed after the raw write: {type(exc).__name__}: {exc}"
        return _finish(store, d, IngestResult(bars.height, "quarantined", detail))


def backfill_polygon(
    store: Store, client: PolygonClient, start: date, end: date
) -> list[IngestResult]:
    """Ingest every weekday in [start, end] not already ok/holiday/quarantined in ingest_log.

    A quarantined day is already stored and re-fetching cannot change its verdict; re-judging
    is revalidate_range's job (AMD-0018 2E).
    """
    done = set(
        store.read(
            "SELECT date FROM ingest_log WHERE source = ? "
            "QUALIFY row_number() OVER (PARTITION BY date ORDER BY finished_at DESC) = 1 "
            "AND status IN ('ok', 'holiday', 'quarantined')",
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


def revalidate_range(store: Store, start: date, end: date) -> list[IngestResult]:
    """Re-judge every stored day in [start, end]: no provider call, bars_raw never written.

    Rewrites ingest_log and bar_flags only (AMD-0018 2D). A day that cannot be judged gets a
    'quarantined' row carrying the exception (AMD-0021 2C).
    """
    dates = store.read(
        "SELECT DISTINCT date FROM bars_raw WHERE source = ? AND date >= ? AND date <= ? "
        "ORDER BY date",
        [SOURCE, start, end],
    )["date"].to_list()
    results: list[IngestResult] = []
    for d in dates:
        try:
            bars = store.read(
                "SELECT symbol, close, volume FROM bars_raw WHERE source = ? AND date = ?",
                [SOURCE, d],
            )
            results.append(_judge(store, d, bars))
        except Exception as exc:  # noqa: BLE001 - recorded as quarantined in ingest_log
            # AMD-0021 2C: a judging failure always writes a log row, or the day keeps a stale
            # verdict indefinitely. 'quarantined', not 'failed': the day IS stored, and a
            # 'failed' row would make the backfill re-fetch it (AMD-0019 2E).
            log.error("revalidate_failed", date=d.isoformat(), error=type(exc).__name__)
            detail = f"revalidation failed: {type(exc).__name__}: {exc}"
            results.append(_finish(store, d, IngestResult(0, "quarantined", detail)))
    return results


def _supersede_legacy_dividends(store: Store) -> int:
    """Delete `legacy` Polygon dividend rows for every (symbol, date) that now has real-id rows.

    The schema-6 migration backfills `vendor_id = 'legacy'` for Polygon rows whose `id` was never
    stored. Left beside the real records they would be counted a second time by the ex-date sum,
    so a real record for a (symbol, date) REPLACES that date's placeholder (WO-0016 8). A
    placeholder for a date Polygon no longer returns is left alone. Returns rows deleted."""
    con = store.connect()
    try:
        con.execute("BEGIN")
        try:
            n = con.execute(
                "SELECT count(*) FROM dividends d WHERE d.source = ? AND d.vendor_id = ? "
                "AND EXISTS (SELECT 1 FROM dividends r WHERE r.symbol = d.symbol "
                "AND r.date = d.date AND r.source = d.source AND r.vendor_id <> ?)",
                [SOURCE, LEGACY_VENDOR_ID, LEGACY_VENDOR_ID],
            ).fetchone()[0]
            con.execute(
                "DELETE FROM dividends WHERE source = ? AND vendor_id = ? "
                "AND EXISTS (SELECT 1 FROM dividends r WHERE r.symbol = dividends.symbol "
                "AND r.date = dividends.date AND r.source = dividends.source "
                "AND r.vendor_id <> ?)",
                [SOURCE, LEGACY_VENDOR_ID, LEGACY_VENDOR_ID],
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        return int(n)
    finally:
        con.close()


def ingest_polygon_actions(store: Store, client: PolygonClient, since: date) -> int:
    """Upsert splits -> `splits` and dividends -> `dividends` (symbols in `symbols` only).

    `splits` is keyed (symbol, date, source) so a same-date split and dividend both persist
    (AMD-0012). `dividends` is keyed (symbol, date, source, vendor_id): every Polygon record of
    an ex-date persists, a quarterly beside a special (AMD-0027 2A). Real-id rows then supersede
    the migration's `legacy` placeholder for their (symbol, date). Returns the total rows written
    across both tables.
    """
    known = store.read("SELECT symbol FROM symbols")["symbol"].to_list()
    keys = ["symbol", "date", "source"]
    splits = (
        client.splits(since)
        .filter(pl.col("symbol").is_in(known))
        .unique(subset=["symbol", "date"], keep="last", maintain_order=True)
        .rename({"split_ratio": "ratio"})
        .with_columns(pl.lit(SOURCE).alias("source"))
        .select("symbol", "date", "ratio", "source")
    )
    divs = (
        client.dividends(since)
        .filter(pl.col("symbol").is_in(known))
        .unique(subset=["symbol", "date", "vendor_id"], keep="last", maintain_order=True)
        .rename({"cash_dividend": "cash_amount"})
        .with_columns(pl.lit(SOURCE).alias("source"))
        .select("symbol", "date", "cash_amount", "source", "vendor_id")
    )
    n_splits = store.upsert("splits", splits, keys)
    n_divs = store.upsert("dividends", divs, [*keys, "vendor_id"])
    superseded = _supersede_legacy_dividends(store)
    log.info(
        "ingest_polygon_actions",
        since=since.isoformat(),
        splits=n_splits,
        dividends=n_divs,
        legacy_superseded=superseded,
    )
    return n_splits + n_divs
