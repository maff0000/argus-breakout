"""Undeclared ticker-rename candidates (WO-0015, AMD-0025 1b). READ-ONLY, wholly offline.

CI-2 verifies continuity only for the pairs in config/ticker_renames.yaml. This module looks in
the STORED data for renames nobody declared and returns RANKED CANDIDATES FOR OPERATOR REVIEW.
It never edits the rename map, never writes `membership`, never merges an interval: asserting
that two tickers are one company is a judgement (AMD-0025 2C).

Signals (none decisive alone):
  (1) a current member whose membership start is materially later than its FIRST STORED BAR
      (both free sources serve a renamed company's whole history under the NEW ticker, AMD-0016
      2D, so bars predating the interval suggest the interval begins at a rename, not a listing);
  (2) another symbol's interval ended within `gap_days` trading days before that start;
  (3) the two symbols' closes at the boundary lie within 10% of each other.
A candidate needs signal (1) AND signal (2): (1) alone names a severed member (see
`severed_current_members`, AC4) but gives no partner to pair it with, and (2)/(3) alone describe
every ordinary index replacement.
"""

from bisect import bisect_right
from datetime import date, timedelta

import polars as pl

from argus.data.store import Store

DEFAULT_GAP_DAYS = 10
MATERIAL_DAYS = 30  # signal (1): first stored bar this many calendar days before the start
PRICE_TOLERANCE = 0.10  # signal (3)
_PRICE_WINDOW_DAYS = 7
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}

CANDIDATE_SCHEMA = {
    "old_symbol": pl.String,
    "old_end_date": pl.Date,
    "new_symbol": pl.String,
    "new_start_date": pl.Date,
    "gap_trading_days": pl.Int64,
    "new_symbol_first_bar": pl.Date,
    "bars_before_new_start": pl.Int64,
    "price_ratio_at_boundary": pl.Float64,
    "confidence": pl.String,
}
SEVERED_SCHEMA = {
    "symbol": pl.String,
    "membership_start": pl.Date,
    "first_stored_bar": pl.Date,
    "bars_before_membership_start": pl.Int64,
    "calendar_days_before": pl.Int64,
}


def severed_current_members(store: Store) -> pl.DataFrame:
    """Signal (1) alone: every CURRENT member whose membership start is materially later than
    its first stored bar (the CI-2 severance case, AC4). `membership_start` is the symbol's
    earliest interval start; bars_raw is read as-is (any source, any day)."""
    df = store.read(
        "WITH m AS (SELECT symbol, MIN(start_date) AS start_date FROM membership "
        "GROUP BY symbol HAVING bool_or(end_date IS NULL)) "
        "SELECT m.symbol AS symbol, m.start_date AS membership_start, "
        "MIN(b.date) AS first_stored_bar, "
        "COUNT(DISTINCT b.date) FILTER (WHERE b.date < m.start_date) AS bars_before, "
        "m.start_date - MIN(b.date) AS days_before "
        "FROM m LEFT JOIN bars_raw b ON b.symbol = m.symbol "
        "GROUP BY m.symbol, m.start_date ORDER BY m.symbol"
    )
    out = df.rename(
        {"bars_before": "bars_before_membership_start", "days_before": "calendar_days_before",
         "first_stored_bar": "first_stored_bar"}
    ).with_columns(
        pl.col("bars_before_membership_start").fill_null(0).cast(pl.Int64),
        pl.col("calendar_days_before").cast(pl.Int64),
    )
    out = out.filter(pl.col("calendar_days_before") > MATERIAL_DAYS)
    return out.select(list(SEVERED_SCHEMA)).cast(SEVERED_SCHEMA).sort(
        "calendar_days_before", descending=True
    )


def _gap_trading_days(calendar: list[date], end: date, start: date) -> int:
    """Trading days in (end, start]: from the stored calendar when it spans both dates,
    otherwise weekdays (holidays unknown outside the stored range)."""
    if calendar and calendar[0] <= end and start <= calendar[-1]:
        return bisect_right(calendar, start) - bisect_right(calendar, end)
    n, d = 0, end + timedelta(days=1)
    while d <= start:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def _boundary_ratio(store: Store, old: str, new: str, end: date) -> float | None:
    """new close / old close at the old symbol's last bar within a week up to its end date."""
    bars = store.read(
        "SELECT symbol, date, close, source FROM bars_raw "
        "WHERE symbol IN (?, ?) AND date BETWEEN ? AND ?",
        [old, new, end - timedelta(days=_PRICE_WINDOW_DAYS), end],
    )
    if bars.is_empty():
        return None
    bars = bars.with_columns((pl.col("source") != "polygon").alias("_r")).sort(
        "symbol", "date", "_r"
    ).unique(subset=["symbol", "date"], keep="first")
    old_rows = bars.filter(pl.col("symbol") == old).sort("date")
    new_rows = bars.filter(pl.col("symbol") == new).sort("date")
    if old_rows.is_empty() or new_rows.is_empty():
        return None
    old_date, old_close = old_rows.row(-1)[1], old_rows.row(-1)[2]
    same = new_rows.filter(pl.col("date") == old_date)
    new_close = same["close"][0] if same.height else new_rows["close"][-1]
    if not old_close or not new_close or old_close <= 0 or new_close <= 0:
        return None
    return float(new_close / old_close)


def undeclared_rename_candidates(
    store: Store, gap_days: int = DEFAULT_GAP_DAYS
) -> pl.DataFrame:
    """Ranked (best first) candidates for operator review; pairs already in the yaml are left out.

    confidence: high = all three signals; medium = (1)+(2) with no price comparison possible
    (e.g. the old ticker has no stored bars, which is what a rename looks like when the sources
    serve the whole history under the new ticker); low = (1)+(2) with closes more than 10% apart.
    """
    if gap_days < 0:
        raise ValueError("gap_days must not be negative")
    severed = severed_current_members(store)
    if severed.is_empty():
        return pl.DataFrame(schema=CANDIDATE_SCHEMA)
    ends = store.read(
        "SELECT symbol, end_date FROM membership WHERE end_date IS NOT NULL "
        "ORDER BY symbol, end_date"
    )
    if ends.is_empty():
        return pl.DataFrame(schema=CANDIDATE_SCHEMA)
    calendar = store.read("SELECT DISTINCT date FROM bars_raw ORDER BY date")["date"].to_list()
    declared = set(store._renames().items())  # noqa: SLF001 - read-only view of the yaml
    rows = []
    for new in severed.iter_rows(named=True):
        start = new["membership_start"]
        for old_symbol, old_end in ends.iter_rows():
            if old_symbol == new["symbol"] or old_end > start:
                continue
            if (start - old_end).days > 3 * gap_days + 10:
                continue
            gap = _gap_trading_days(calendar, old_end, start)
            if gap > gap_days:
                continue
            if (old_symbol, new["symbol"]) in declared:
                continue
            ratio = _boundary_ratio(store, old_symbol, new["symbol"], old_end)
            if ratio is None:
                confidence = "medium"
            elif abs(ratio - 1.0) <= PRICE_TOLERANCE:
                confidence = "high"
            else:
                confidence = "low"
            rows.append(
                {
                    "old_symbol": old_symbol, "old_end_date": old_end,
                    "new_symbol": new["symbol"], "new_start_date": start,
                    "gap_trading_days": gap,
                    "new_symbol_first_bar": new["first_stored_bar"],
                    "bars_before_new_start": new["bars_before_membership_start"],
                    "price_ratio_at_boundary": ratio, "confidence": confidence,
                }
            )
    rows.sort(
        key=lambda r: (_CONFIDENCE_ORDER[r["confidence"]], r["gap_trading_days"], r["new_symbol"])
    )
    return pl.DataFrame(rows, schema=CANDIDATE_SCHEMA)
