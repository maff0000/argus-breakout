"""Same-date dividend diagnostics (WO-0015, AMD-0025 1a). READ-ONLY.

Establishes by measurement whether the `dividends` key (symbol, date, source) collapses two
Polygon dividends that share an ex-date. Without a client it reports stored data only (the
population where Polygon and yfinance disagree by more than 2x after basis normalisation). With a
Polygon client it also fetches the RAW /v3/reference/dividends payload for ONE (symbol, ex_date)
and records the records exactly as the API returned them. Nothing is written, nothing is fixed.
"""

import json
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl

from argus.data.adjust import resolve_splits, totals_materially_differ
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store
from argus.data.tickers import is_valid, to_provider

DISAGREEMENT_FACTOR = 2.0  # AC2: Polygon and yfinance differ by more than 2x after normalisation
_MAX_PRIOR_GAP_DAYS = 5  # same "prior trading day" window adjust.py uses
_AMOUNT_TOL = 1e-6
_RAW_PATH = "/v3/reference/dividends"

REPORT_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "source": pl.String,
    "n_rows_stored": pl.Int64,
    "stored_amount": pl.Float64,
    "note": pl.String,
}
_PAIR_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "polygon_stored": pl.Float64,
    "polygon_normalised": pl.Float64,
    "yfinance_stored": pl.Float64,
    "ratio": pl.Float64,
    "prior_close": pl.Float64,
    "adj_close_err_pct": pl.Float64,
    "suspect": pl.Boolean,
}


@dataclass(frozen=True)
class RawDividendPayload:
    """The API's answer for one (symbol, ex_date); `records` are the unmodified result dicts."""

    records: list[Any]
    status: str | None
    count: int | None
    has_next_url: bool


def fetch_raw_dividend_records(
    client: PolygonClient, symbol: str, ex_date: date
) -> RawDividendPayload:
    """ONE Polygon call: GET /v3/reference/dividends?ticker=S&ex_dividend_date=D&limit=1000.

    Uses the client's rate-limited, retrying, key-redacting HTTP layer `PolygonClient._get`
    (private; the public `dividends()` reduces records to (symbol, date, amount) and cannot show
    the raw fields). `results` is returned exactly as the API sent it: no field is dropped,
    renamed, coerced or filtered. Pagination is deliberately NOT followed (one call); a
    `next_url` is reported instead.
    """
    if not is_valid(symbol):
        raise ValueError(f"invalid symbol: {symbol!r}")
    body = client._get(  # noqa: SLF001 - read-only raw accessor, WO-0015 section 4
        _RAW_PATH,
        {
            "ticker": to_provider(symbol, "polygon"),
            "ex_dividend_date": ex_date.isoformat(),
            "limit": "1000",
        },
    )
    results = body.get("results") or []
    return RawDividendPayload(
        records=list(results),
        status=body.get("status"),
        count=body.get("count"),
        has_next_url=bool(body.get("next_url")),
    )


def classify_stored_vs_raw(stored: float | None, amounts: list[float]) -> str:
    """Whether the stored amount equals one raw record, their sum, or neither."""
    if stored is None:
        return "no_stored_polygon_row"
    if not amounts:
        return "no_raw_records"

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= _AMOUNT_TOL

    if len(amounts) == 1:
        return "equals_the_single_record" if close(stored, amounts[0]) else "neither"
    if close(stored, sum(amounts)):
        return "equals_sum_of_records"
    if any(close(stored, a) for a in amounts):
        return "equals_one_record"
    return "neither"


def _cash_amounts(records: list[Any]) -> list[float]:
    out = []
    for r in records:
        try:
            out.append(float(r["cash_amount"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _prior_bars(
    pairs: pl.DataFrame, bars: pl.DataFrame
) -> dict[tuple[str, date], tuple[date | None, float | None]]:
    """(symbol, ex) -> (date, close) of the last published bar BEFORE ex, if within 5 days."""
    by_sym: dict[str, tuple[list[date], list[float | None]]] = {}
    for s, d, c in bars.select("symbol", "date", "close").sort("symbol", "date").iter_rows():
        ds, cs = by_sym.setdefault(s, ([], []))
        ds.append(d)
        cs.append(c)
    out: dict[tuple[str, date], tuple[date | None, float | None]] = {}
    for sym, ex in pairs.select("symbol", "date").iter_rows():
        ds, cs = by_sym.get(sym, ([], []))
        i = bisect_left(ds, ex)
        if i > 0 and (ex - ds[i - 1]).days <= _MAX_PRIOR_GAP_DAYS:
            out[(sym, ex)] = (ds[i - 1], cs[i - 1])
        else:
            out[(sym, ex)] = (None, None)
    return out


def _normalisation(
    store: Store, pairs: pl.DataFrame
) -> tuple[dict[tuple[str, date], float], dict[tuple[str, date], tuple[date | None, float | None]]]:
    """The one split normalisation: (symbol, ex) -> cumulative ratio of splits after the prior bar.

    An 'as_paid' amount (Polygon) divided by it is on the price basis adjust.py uses; a
    'split_adjusted' amount (yfinance) is used as stored. Also returns each pair's prior bar.
    Shared by the disagreement report and `attribute_pairs`, so there is one rule, not two."""
    syms = pairs["symbol"].unique().to_list()
    splits = store.read(
        "SELECT symbol, date, ratio, source FROM splits WHERE symbol IN (SELECT unnest(?))",
        [syms],
    )
    resolved = resolve_splits(splits)[0] if not splits.is_empty() else splits
    ratios: dict[str, list[tuple[date, float]]] = {}
    for s, d, r in resolved.select("symbol", "date", "ratio").iter_rows():
        if r is not None and r > 0:
            ratios.setdefault(s, []).append((d, r))
    bars = store.read(
        "SELECT symbol, date, close FROM bars WHERE symbol IN (SELECT unnest(?))", [syms]
    )
    prior = _prior_bars(pairs, bars)
    cums: dict[tuple[str, date], float] = {}
    for sym, ex in pairs.select("symbol", "date").iter_rows():
        prior_date = prior[(sym, ex)][0]
        after = prior_date if prior_date is not None else ex - timedelta(days=1)
        cum = 1.0
        for sd, r in ratios.get(sym, []):
            if sd > after:
                cum *= r
        cums[(sym, ex)] = cum
    return cums, prior


def dividend_disagreements(
    store: Store, symbol: str | None = None, on_date: date | None = None
) -> pl.DataFrame:
    """Every (symbol, ex_date) with BOTH sources stored; `suspect` = differ by more than 2x.

    Polygon's amount ('as_paid') is divided by the split_cum of the last bar before the ex-date
    (the rule adjust.py's `dividend_adjusted_close` uses: the product of the resolved split
    ratios dated after that bar, so a split on the ex-date is included) so both amounts are on
    the price basis; yfinance's ('split_adjusted') is used as stored. `adj_close_err_pct` is
    |polygon_normalised - yfinance| / prior_close x 100: how far apart the two sources put the
    adj_close factor at that ex-date as a share of price. It does not say which source is right.
    """
    sql = (
        "SELECT symbol, date, sum(cash_amount) AS cash_amount, source FROM dividends "
        "WHERE source IN (?, ?)"
    )
    params: list = ["polygon", "yfinance"]
    if symbol is not None:
        sql += " AND symbol = ?"
        params.append(symbol)
    if on_date is not None:
        sql += " AND date = ?"
        params.append(on_date)
    # One total per (symbol, date, source): a source may hold several records for an ex-date.
    div = store.read(sql + " GROUP BY symbol, date, source ORDER BY symbol, date", params)
    if div.is_empty():
        return pl.DataFrame(schema=_PAIR_SCHEMA)
    pg = div.filter(pl.col("source") == "polygon").select(
        "symbol", "date", pl.col("cash_amount").alias("polygon_stored")
    )
    yf = div.filter(pl.col("source") == "yfinance").select(
        "symbol", "date", pl.col("cash_amount").alias("yfinance_stored")
    )
    both = pg.join(yf, on=["symbol", "date"], how="inner").sort("symbol", "date")
    if both.is_empty():
        return pl.DataFrame(schema=_PAIR_SCHEMA)
    cums, prior = _normalisation(store, both)
    rows = []
    for rec in both.iter_rows(named=True):
        sym, ex = rec["symbol"], rec["date"]
        _prior_date, prior_close = prior[(sym, ex)]
        pg_norm = rec["polygon_stored"] / cums[(sym, ex)]
        yf_amt = rec["yfinance_stored"]
        lo, hi = sorted((pg_norm, yf_amt))
        ratio = 1.0 if hi <= 0 else (float("inf") if lo <= 0 else hi / lo)
        err = None
        if prior_close and prior_close > 0:
            err = abs(pg_norm - yf_amt) / prior_close * 100.0
        rows.append(
            {
                "symbol": sym, "date": ex, "polygon_stored": rec["polygon_stored"],
                "polygon_normalised": pg_norm, "yfinance_stored": yf_amt, "ratio": ratio,
                "prior_close": prior_close, "adj_close_err_pct": err,
                "suspect": ratio > DISAGREEMENT_FACTOR,
            }
        )
    return pl.DataFrame(rows, schema=_PAIR_SCHEMA)


def _fmt(x: float | None, spec: str = ".6g") -> str:
    return "n/a" if x is None else format(x, spec)


def same_date_dividend_report(
    store: Store,
    client: PolygonClient | None,
    symbol: str | None = None,
    on_date: date | None = None,
) -> pl.DataFrame:
    """[symbol, date, source, n_rows_stored, stored_amount, note]; never writes.

    No client: stored data only. With no symbol/date, the AC2 population (suspect pairs, both
    amounts and the adj_close error); with a symbol and date, that key's stored rows. With a
    client (requires symbol and date): additionally the raw API records for that key, one row per
    record (verbatim JSON in `note`) and a `polygon_raw_summary` row stating n_records_returned
    and whether the stored polygon amount equals one record, their sum, or neither.
    """
    if client is not None and (symbol is None or on_date is None):
        raise ValueError("--raw needs both a symbol and a date")
    if (symbol is None) != (on_date is None):
        raise ValueError("give both --symbol and --date, or neither")
    if symbol is not None and not is_valid(symbol):
        raise ValueError(f"invalid symbol: {symbol!r}")
    keyed = symbol is not None
    pairs = dividend_disagreements(store, symbol, on_date)
    shown = pairs if keyed else pairs.filter(pl.col("suspect"))
    rows: list[dict] = []
    for p in shown.iter_rows(named=True):
        note = (
            f"normalised polygon={_fmt(p['polygon_normalised'])} "
            f"yfinance={_fmt(p['yfinance_stored'])} ratio={_fmt(p['ratio'], '.4g')}x "
            f"prior_close={_fmt(p['prior_close'], '.4f')} "
            f"adj_close_err_pct={_fmt(p['adj_close_err_pct'], '.3f')} suspect={p['suspect']}"
        )
        for src, amt in (("polygon", p["polygon_stored"]), ("yfinance", p["yfinance_stored"])):
            rows.append(
                {"symbol": p["symbol"], "date": p["date"], "source": src, "n_rows_stored": 1,
                 "stored_amount": amt, "note": note}
            )
    if keyed:
        have = {(r["symbol"], r["source"]) for r in rows}
        stored = store.read(
            "SELECT symbol, date, source, cash_amount FROM dividends "
            "WHERE symbol = ? AND date = ? ORDER BY source",
            [symbol, on_date],
        )
        for r in stored.iter_rows(named=True):
            if (r["symbol"], r["source"]) not in have:
                rows.append(
                    {"symbol": r["symbol"], "date": r["date"], "source": r["source"],
                     "n_rows_stored": 1, "stored_amount": r["cash_amount"],
                     "note": "stored row; no counterpart from the other source"}
                )
        if stored.is_empty():
            rows.append(
                {"symbol": symbol, "date": on_date, "source": "none", "n_rows_stored": 0,
                 "stored_amount": None, "note": "no dividends row stored for this key"}
            )
    if client is not None:
        assert symbol is not None and on_date is not None  # noqa: S101 - checked above
        payload = fetch_raw_dividend_records(client, symbol, on_date)
        pg_rows = store.read(
            "SELECT cash_amount FROM dividends WHERE symbol = ? AND date = ? AND source = ?",
            [symbol, on_date, "polygon"],
        )
        n_stored = pg_rows.height
        stored_amount = pg_rows["cash_amount"].sum() if n_stored else None  # all records
        amounts = _cash_amounts(payload.records)
        n = len(payload.records)
        for i, rec in enumerate(payload.records, start=1):
            amt = rec.get("cash_amount") if isinstance(rec, dict) else None
            rows.append(
                {"symbol": symbol, "date": on_date, "source": "polygon_raw",
                 "n_rows_stored": n_stored,
                 "stored_amount": float(amt) if isinstance(amt, int | float) else None,
                 "note": f"record {i}/{n} verbatim: {json.dumps(rec)}"}
            )

        def collect(field: str) -> list[Any]:
            return [r.get(field) if isinstance(r, dict) else None for r in payload.records]

        rows.append(
            {"symbol": symbol, "date": on_date, "source": "polygon_raw_summary",
             "n_rows_stored": n_stored, "stored_amount": stored_amount,
             "note": (
                 f"n_records_returned={n}; cash_amounts={json.dumps(collect('cash_amount'))}; "
                 f"dividend_type={json.dumps(collect('dividend_type'))}; "
                 f"frequency={json.dumps(collect('frequency'))}; "
                 f"response_status={payload.status}; response_count={payload.count}; "
                 f"next_url_present={payload.has_next_url}; "
                 f"stored_polygon_amount={stored_amount}; "
                 f"stored_equals={classify_stored_vs_raw(stored_amount, amounts)}"
             )}
        )
    return pl.DataFrame(rows, schema=REPORT_SCHEMA)


ATTRIBUTION_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "n_records": pl.Int64,
    "amounts": pl.List(pl.Float64),
    "ids": pl.List(pl.String),
    "raw_sum": pl.Float64,
    "stored_polygon": pl.Float64,
    "n_stored_polygon": pl.Int64,
    "yfinance_stored": pl.Float64,
    "split_cum": pl.Float64,
    "polygon_normalised": pl.Float64,
    "yfinance_normalised": pl.Float64,
    "verdict": pl.String,
    "note": pl.String,
}


def _verdict(n: int, polygon_norm: float | None, yf: float | None) -> tuple[str, str]:
    """collapse | omission | neither for ONE pair, from the raw record count and normalised totals.

    collapse: several records for the ex-date (the store keeps one) and their normalised SUM
    agrees with yfinance (within the AMD-0027 2D bands, or yfinance has no row).
    omission: ONE record whose normalised amount is materially smaller than yfinance's total.
    neither: anything else (no record; one record that matches or exceeds yfinance; several
    records whose sum still disagrees). 'neither' is a stop, never a residual (WO-0016 AC1)."""
    if n == 0:
        return "neither", "no raw record returned"
    if n > 1:
        if yf is None or not totals_materially_differ(polygon_norm, yf):
            return "collapse", f"{n} records for one ex-date; summed total matches the other source"
        return "neither", f"{n} records but their summed total still differs from yfinance"
    if yf is None:
        return "neither", "one record and no yfinance row to compare"
    if totals_materially_differ(polygon_norm, yf) and polygon_norm < yf:
        return "omission", "one record, smaller than yfinance's normalised total"
    return "neither", "one record that does not fall short of yfinance's normalised total"


def attribute_pairs(
    store: Store, client: PolygonClient, pairs: list[tuple[str, date]]
) -> pl.DataFrame:
    """Attribute each (symbol, ex_date) to collapse / omission / neither. READ-ONLY.

    One raw Polygon call per pair (the client's rate limiter paces them; `client` may be a mock).
    The stored `dividends` rows are only read. Raw 'as_paid' amounts are put on the same basis as
    yfinance's 'split_adjusted' total by the shared `_normalisation` before comparing, so a
    split ratio is never read as a completeness gap (AMD-0027 2D)."""
    for sym, _ex in pairs:
        if not is_valid(sym):
            raise ValueError(f"invalid symbol: {sym!r}")
    if not pairs:
        return pl.DataFrame(schema=ATTRIBUTION_SCHEMA)
    frame = pl.DataFrame(pairs, schema=["symbol", "date"], orient="row")
    cums, _prior = _normalisation(store, frame)
    rows = []
    for sym, ex in pairs:
        payload = fetch_raw_dividend_records(client, sym, ex)
        amounts = _cash_amounts(payload.records)
        ids = [str(r.get("id")) if isinstance(r, dict) else "" for r in payload.records]
        stored = store.read(
            "SELECT source, sum(cash_amount) AS total, count(*) AS n FROM dividends "
            "WHERE symbol = ? AND date = ? GROUP BY source",
            [sym, ex],
        )
        by_src = {r["source"]: r for r in stored.iter_rows(named=True)}
        pg, yf = by_src.get("polygon"), by_src.get("yfinance")
        cum = cums[(sym, ex)]
        raw_sum = sum(amounts)
        pg_norm = raw_sum / cum
        yf_amt = None if yf is None else yf["total"]
        verdict, note = _verdict(len(payload.records), pg_norm, yf_amt)
        rows.append(
            {
                "symbol": sym, "date": ex, "n_records": len(payload.records),
                "amounts": amounts, "ids": ids, "raw_sum": raw_sum,
                "stored_polygon": None if pg is None else pg["total"],
                "n_stored_polygon": 0 if pg is None else pg["n"],
                "yfinance_stored": yf_amt, "split_cum": cum, "polygon_normalised": pg_norm,
                "yfinance_normalised": yf_amt, "verdict": verdict, "note": note,
            }
        )
    return pl.DataFrame(rows, schema=ATTRIBUTION_SCHEMA)
