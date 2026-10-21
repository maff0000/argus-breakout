"""Adjustment and materialisation of `bars` / `etf_bars` (WO-0007; DESIGN 3.3).

`bars_raw` is read as-is and never written (CI-9). Every publish is re-derived from it plus
`splits` and `dividends`, so a run is a pure function of its inputs: running it twice cannot
apply a split twice. `adj_version` records when already-published history had to change.

Baseline of the split rule (WO-0007 8). Both free sources deliver history that is split-
adjusted *as of the day it was fetched*. A split with effective date D therefore needs applying
to a stored row only if the row predates D (`date < D`) AND was fetched before D
(`ingested_at` date < D): a row fetched on or after D already carries the split. This is the
WO's "split later than the latest ingested bar of the supplying source" rule evaluated per row
rather than per source, so a source fetched in two runs either side of D (Polygon's daily
ingest after a yfinance bootstrap) gets the right answer for each row. Where `ingested_at` is
absent the per-(symbol, source) latest bar date stands in for it, which is the WO's wording.

Quality seam (AMD-0018 2A, AMD-0019 2A). `bars_raw` is read whole. Source precedence picks the
row for each (symbol, day); a Polygon row of a day whose latest `ingest_log` verdict for source
'polygon' is 'quarantined' is then withheld, and NOTHING takes its place (no cross-source
substitution). A `bar_flags` row never withholds anything: a flag is carried, joinable on
(symbol, date, source), and only the equal-weight AGGREGATES exclude flagged symbol-days
(`equal_weight_aggregate`). bars_raw itself is never altered (CI-9). Counts travel in the
report (CI-8).

Dividend basis (AMD-0019 2B). A dividend is brought onto the price basis before it enters the
factor: an 'as_paid' amount is divided by the cumulative split ratio of the splits dated after
its ex-date (`split_cum`, computed in `apply_splits` beside the price divisor), a
'split_adjusted' amount is used as stored, and any other basis raises.
"""

import json
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import polars as pl
import structlog

from argus.data.store import Store
from argus.data.tickers import is_valid
from argus.data.universe import ETF_LABEL

log = structlog.get_logger()

SOURCE = "materialise"

# Polygon over yfinance, on bars and on corporate actions alike (AMD-0012).
_PRECEDENCE = {"polygon": 0, "yfinance": 1}
_UNRANKED = 2
_SUPPORTED_BASIS = "split"
POLYGON = "polygon"

# Flags whose symbol-days the equal-weight AGGREGATES exclude (AMD-0019 2A). A symbol's own
# series never drops a flagged day. `jump_split_reconciled` is absent: the split explains the
# move, so the day is sound (AMD-0018 2C).
AGGREGATE_EXCLUDING_FLAGS = frozenset({"jump_unexplained"})
_QUARANTINED = "quarantined"
_DIVIDEND_BASES = frozenset({"as_paid", "split_adjusted"})

_PCT_THRESHOLD = 0.5  # close disagreement between sources, percent (WO-0007 4)
_RATIO_TOLERANCE = 0.001  # split ratio disagreement, relative (0.1%, AMD-0012)
_DIVIDEND_TOLERANCE = 0.01  # dividend disagreement, one cent (AMD-0012)
_OUTSIDE_TRADING_DAYS = 10  # AMD-0018 2F
_MAX_PRIOR_GAP_DAYS = 5  # a prior bar older than this is not "the prior trading day"
_CHANGE_TOLERANCE = 1e-9
_BATCH = 50
_LOG_WARNINGS = 200

_MIN_DATE = date(1900, 1, 1)
_MAX_DATE = date(9999, 12, 31)
_OHLCV = ["open", "high", "low", "close", "volume"]
_VALUE_COLS = [*_OHLCV, "adj_close"]


@dataclass(frozen=True)
class MaterialiseReport:
    """n_symbols: symbols processed. n_rows: rows written this run (0 on a no-op re-run).
    n_readjusted: symbols whose already-published rows changed, so adj_version incremented.
    warnings: one string per finding, `<kind> <symbol> <date|-> <detail>`.

    n_days_quarantined_skipped: distinct days whose Polygon rows were withheld.
    n_symbol_days_flag_excluded: ALWAYS 0 since AMD-0019 2A (a flag never withholds a published
      symbol-day); kept only so the CLI summary line keeps its shape.
    n_symbol_days_flagged: published symbol-days carrying an excluding flag (carried, not dropped).
    n_members_flagged_by_date: per date, the number of published symbols flagged that day
      (the `n_members_flagged` coverage figure, DESIGN 6.1); only dates with >= 1 are listed.
    n_bars_before_first_membership: pre-entry bars, retained and merely counted (AMD-0019 2D).
    n_bars_after_final_end_without_continuity: bars dropped after a delisted member's final end
      with no rename continuity (the AMD-0018 2F hazard); a run of more than ten warns per symbol.
    """

    n_symbols: int
    n_rows: int
    n_readjusted: int
    warnings: list[str] = field(default_factory=list)
    n_days_quarantined_skipped: int = 0
    n_symbol_days_flag_excluded: int = 0
    n_symbol_days_flagged: int = 0
    n_members_flagged_by_date: dict[date, int] = field(default_factory=dict)
    n_bars_before_first_membership: int = 0
    n_bars_after_final_end_without_continuity: int = 0


def _warn(kind: str, symbol: str, d: date | None, detail: str) -> str:
    return f"{kind} {symbol} {d.isoformat() if d else '-'} {detail}"


# ---------------------------------------------------------------------------- source choice
def _rank_expr() -> pl.Expr:
    return pl.col("source").replace_strict(_PRECEDENCE, default=_UNRANKED, return_dtype=pl.Int8)


def select_source(raw: pl.DataFrame) -> pl.DataFrame:
    """One row per (symbol, date): Polygon where it has the day, else yfinance. Never averaged."""
    if raw.is_empty():
        return raw
    return (
        raw.with_columns(_rank_expr().alias("_rank"))
        .sort(["symbol", "date", "_rank"])
        .unique(subset=["symbol", "date"], keep="first", maintain_order=True)
        .drop("_rank")
        .sort(["symbol", "date"])
    )


def source_disagreements(raw: pl.DataFrame, threshold_pct: float = _PCT_THRESHOLD) -> pl.DataFrame:
    """(symbol, date, pct_diff) where Polygon and yfinance closes differ by more than the
    threshold. Closes are compared at 4 decimal places; pct_diff is relative to yfinance."""
    cols = ["symbol", "date", "pct_diff"]
    empty = pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date, "pct_diff": pl.Float64})
    if raw.is_empty():
        return empty
    poly = raw.filter(pl.col("source") == "polygon").select(
        "symbol", "date", pl.col("close").round(4).alias("p")
    )
    yf = raw.filter(pl.col("source") == "yfinance").select(
        "symbol", "date", pl.col("close").round(4).alias("y")
    )
    both = poly.join(yf, on=["symbol", "date"])
    if both.is_empty():
        return empty
    both = both.with_columns(
        pl.when(pl.col("y") == 0)
        .then(pl.when(pl.col("p") == 0).then(0.0).otherwise(float("inf")))
        .otherwise(((pl.col("p") - pl.col("y")).abs() / pl.col("y").abs() * 100).round(4))
        .alias("pct_diff")
    )
    return both.filter(pl.col("pct_diff") > threshold_pct).select(cols).sort(["symbol", "date"])


# ---------------------------------------------------------------------------- corporate actions
def _resolve_actions(
    actions: pl.DataFrame, value: str, kind: str, disagrees
) -> tuple[pl.DataFrame, list[str]]:
    """One row per (symbol, date), Polygon over yfinance; a warning where the sources disagree."""
    warnings: list[str] = []
    if actions.is_empty():
        return actions, warnings
    ranked = actions.with_columns(_rank_expr().alias("_rank")).sort(["symbol", "date", "_rank"])
    for _key, grp in ranked.group_by(["symbol", "date"], maintain_order=True):
        if grp.height < 2:
            continue
        win = grp.row(0, named=True)
        for k, other in enumerate(grp.iter_rows(named=True)):
            if k > 0 and disagrees(win[value], other[value]):
                warnings.append(
                    _warn(
                        kind, win["symbol"], win["date"],
                        f"{win['source']}={win[value]:.4f} {other['source']}={other[value]:.4f}",
                    )
                )
    kept = ranked.unique(subset=["symbol", "date"], keep="first", maintain_order=True)
    return kept.drop("_rank").sort(["symbol", "date"]), warnings


def resolve_splits(splits: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    """Duplicates resolved by precedence; ratios more than 0.1% apart are warned (AMD-0012)."""
    return _resolve_actions(
        splits, "ratio", "split_disagreement",
        lambda a, b: abs(round(a, 4) - round(b, 4)) > _RATIO_TOLERANCE * abs(round(b, 4)),
    )


def resolve_dividends(dividends: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    """Duplicates resolved by precedence; amounts more than one cent apart are warned."""
    return _resolve_actions(
        dividends, "cash_amount", "dividend_disagreement",
        lambda a, b: abs(round(a, 4) - round(b, 4)) > _DIVIDEND_TOLERANCE + 1e-9,
    )


def apply_splits(bars: pl.DataFrame, splits: pl.DataFrame, as_of_version: int) -> pl.DataFrame:
    """Split-adjust `bars` and stamp `adj_version = as_of_version` on every row.

    `bars` carries symbol, date, open, high, low, close, volume and, ideally, `ingested_at`
    (and `source`). For a split dated D with ratio r (to/from, 2.0 for a 2:1) every row with
    date < D that was fetched before D has open/high/low/close divided by r and volume
    multiplied by r (see the module docstring for why "fetched before D"). Rows from a source
    that already delivered D are untouched, so a split is never applied twice.

    Also stamps `split_cum`: per row, the product of the ratios of every split dated after the row
    (regardless of when the row was fetched). It is the factor that carries an 'as_paid' dividend
    onto the same share count as the adjusted price (AMD-0019 2B); `dividend_adjusted_close`
    reads it, so the dividend and the price are divided by splits from this one loop.
    """
    out = bars.sort(["symbol", "date"]).with_columns(
        pl.lit(1.0, dtype=pl.Float64).alias("_div"),
        pl.lit(1.0, dtype=pl.Float64).alias("split_cum"),
        pl.lit(as_of_version, dtype=pl.Int32).alias("adj_version"),
    )
    if out.is_empty() or splits.is_empty():
        return out.drop("_div")
    if "ingested_at" in out.columns and out["ingested_at"].null_count() == 0:
        fetched = pl.col("ingested_at").dt.date()
    else:
        group = [c for c in ("symbol", "source") if c in out.columns]
        fetched = pl.col("date").max().over(group)
    out = out.with_columns(fetched.alias("_fetched"))
    resolved, _ = resolve_splits(splits)
    for sym, d, ratio in resolved.select("symbol", "date", "ratio").iter_rows():
        if ratio is None or not ratio > 0:
            continue
        applies = (pl.col("symbol") == sym) & (pl.col("date") < d) & (pl.col("_fetched") < d)
        later = (pl.col("symbol") == sym) & (pl.col("date") < d)
        out = out.with_columns(
            pl.when(applies).then(pl.col("_div") * ratio).otherwise(pl.col("_div")).alias("_div"),
            pl.when(later)
            .then(pl.col("split_cum") * ratio)
            .otherwise(pl.col("split_cum"))
            .alias("split_cum"),
        )
    out = out.with_columns(
        *(pl.col(c) / pl.col("_div") for c in ("open", "high", "low", "close")),
        pl.col("volume") * pl.col("_div"),
    )
    return out.drop("_div", "_fetched")


def _require_dividend_basis(dividends: pl.DataFrame) -> None:
    """Raise unless every dividend row records a known basis (AMD-0019 2B: never default)."""
    if dividends.is_empty():
        return
    if "basis" not in dividends.columns:
        raise ValueError("dividends carry no basis column; the basis is never defaulted")
    bad = {b for b in dividends["basis"].to_list() if b not in _DIVIDEND_BASES}
    if bad:
        raise ValueError(f"dividend basis not recorded or unknown: {sorted(map(str, bad))}")


def dividend_adjusted_close(
    bars: pl.DataFrame, dividends: pl.DataFrame, warnings: list[str] | None = None
) -> pl.Series:
    """adj_close = close x PROD over ex-dates E > date of (1 - dividend / close[prior bar of E]).

    `bars` is one symbol's split-adjusted series; the result is aligned to its row order. Each
    dividend is first put on the price basis (AMD-0019 2B): `as_paid` amounts are divided by the
    `split_cum` of the first bar on or after the ex-date (splits dated after the ex-date; a
    `bars` frame without the column has no splits), `split_adjusted` amounts are used as stored.
    A `dividends` frame without a `basis` column, or a row whose basis is null or not one of the
    two, raises ValueError: the basis is never defaulted. The
    prior close is the last bar before the ex-date. If there is none within five calendar days
    or it is not a positive number, the dividend is skipped and a warning appended to
    `warnings`. A dividend with no bar before it adjusts nothing and is ignored; one with an
    ex-date after the last bar waits until its ex-date bar exists.
    """
    n = bars.height
    if n == 0:
        return pl.Series("adj_close", [], dtype=pl.Float64)
    _require_dividend_basis(dividends)
    sym = bars["symbol"][0]
    order = bars["date"].arg_sort().to_list()
    all_dates, all_closes = bars["date"].to_list(), bars["close"].to_list()
    all_cum = bars["split_cum"].to_list() if "split_cum" in bars.columns else [1.0] * n
    dates = [all_dates[i] for i in order]
    closes = [all_closes[i] for i in order]
    cums = [all_cum[i] for i in order]
    boundary = [1.0] * n  # boundary[k]: factor owed by every row at or before k
    resolved, found = resolve_dividends(dividends.filter(pl.col("symbol") == sym))
    sink = warnings if warnings is not None else []
    sink.extend(found)
    for ex, amount, basis in resolved.select("date", "cash_amount", "basis").iter_rows():
        if ex > dates[-1]:
            continue
        i = bisect_left(dates, ex)  # rows [0, i) precede the ex-date
        if i == 0:
            continue
        if basis == "as_paid":
            amount = amount / cums[i]  # onto the split-adjusted share count of the prices
        prior = closes[i - 1]
        if (ex - dates[i - 1]).days > _MAX_PRIOR_GAP_DAYS or not (prior and prior > 0):
            sink.append(_warn("dividend_skipped_no_prior_close", sym, ex, f"amount={amount:.4f}"))
            continue
        factor = 1.0 - amount / prior
        if not factor > 0:
            sink.append(_warn("dividend_skipped_exceeds_close", sym, ex, f"amount={amount:.4f}"))
            continue
        boundary[i - 1] *= factor
    cumulative = [1.0] * n
    running = 1.0
    for k in range(n - 1, -1, -1):
        running *= boundary[k]
        cumulative[k] = running
    adj = [None] * n
    for pos, row in enumerate(order):
        c = closes[pos]
        adj[row] = None if c is None else c * cumulative[pos]
    return pl.Series("adj_close", adj, dtype=pl.Float64)


# ---------------------------------------------------------------------------- materialise
def _bound_by_membership(
    sel: pl.DataFrame,
    member: pl.DataFrame,
    symbol: str,
    continuity: bool,
    warnings: list[str],
    stats: dict,
) -> pl.DataFrame:
    """AMD-0018 2F / AMD-0019 2D: a symbol's bars end with its listing life.

    Bars BEFORE the first membership are required history: kept and only counted
    (`stats["before_first"]`). Bars after a delisted member's final end_date are dropped unless
    the symbol is mapped forward as a rename (continuity); they are counted in
    `stats["after_final"]` and a run of more than ten warns, per symbol."""
    if member.is_empty() or sel.is_empty():
        return sel
    starts = member["start_date"].to_list()
    ends = member["end_date"].to_list()
    stats["before_first"] += sel.filter(pl.col("date") < min(starts)).height
    if None in ends or continuity:
        return sel
    final_end = max(ends)
    after = sel.filter(pl.col("date") > final_end).height
    stats["after_final"] += after
    if after > _OUTSIDE_TRADING_DAYS:
        warnings.append(
            _warn(
                "bars_after_final_end_without_continuity", symbol, None,
                f"after_final_end={after} final_end={final_end.isoformat()} "
                "rename_continuity=false",
            )
        )
    return sel.filter(pl.col("date") <= final_end)


def _changed(existing: pl.DataFrame, new: pl.DataFrame) -> bool:
    """True if any already-published row vanished or changed in value (a re-adjustment)."""
    joined = existing.join(new, on="date", how="left", suffix="_n")
    if joined.filter(pl.col("close_n").is_null() & pl.col("close").is_not_null()).height:
        return True
    for c in _VALUE_COLS:
        a, b = pl.col(c), pl.col(c + "_n")
        moved = (a.is_null() != b.is_null()) | ((a - b).abs() > _CHANGE_TOLERANCE * (a.abs() + 1))
        if joined.filter(moved.fill_null(False)).height:
            return True
    return False


def _materialise_symbol(
    sym: str,
    raw: pl.DataFrame,
    existing: pl.DataFrame,
    splits: pl.DataFrame,
    dividends: pl.DataFrame,
    member: pl.DataFrame,
    continuity: bool,
    warnings: list[str],
    quarantined: frozenset[date],
    flags: pl.DataFrame,
    stats: dict,
) -> tuple[pl.DataFrame | None, bool]:
    """(frame to write or None when unchanged, whether published rows were re-adjusted).

    `quarantined`: days whose Polygon rows are withheld; `flags`: this symbol's excluding
    bar_flags rows, which are only counted (`stats["flagged"]`), never used to drop a row."""
    ok = raw.filter(pl.col("basis") == _SUPPORTED_BASIS)
    if ok.height != raw.height:
        warnings.append(
            _warn("unsupported_basis_skipped", sym, None, f"rows={raw.height - ok.height}")
        )
    sel = select_source(ok)
    # A quarantined Polygon day is withheld and NOT filled from yfinance (AMD-0019 2A).
    held = sel.filter((pl.col("source") == POLYGON) & pl.col("date").is_in(sorted(quarantined)))
    if held.height:
        stats["skipped_days"].update(held["date"])
        sel = sel.join(held.select("symbol", "date"), on=["symbol", "date"], how="anti")
    sel = _bound_by_membership(sel, member, sym, continuity, warnings, stats)
    if sel.is_empty():
        warnings.append(_warn("no_bars", sym, None, "nothing to publish"))
        return None, False
    ends = member["end_date"].to_list()
    if ends and None not in ends and not continuity:
        # a delisted member's actions after its final end_date belong to a successor company
        splits = splits.filter(pl.col("date") <= max(ends))
        dividends = dividends.filter(pl.col("date") <= max(ends))
    carried = flags.join(sel.select("symbol", "date", "source"), on=["symbol", "date", "source"])
    stats["flagged"].update((sym, d) for d in carried["date"])
    kept = ok.join(sel.select("symbol", "date"), on=["symbol", "date"])
    for row in source_disagreements(kept).iter_rows(named=True):
        detail = f"pct_diff={row['pct_diff']}"
        warnings.append(_warn("source_disagreement", sym, row["date"], detail))
    _, found = resolve_splits(splits)
    warnings.extend(found)

    prev = int(existing["adj_version"].max()) if existing.height else 0
    adjusted = apply_splits(sel, splits, max(prev, 1))
    adj_close = dividend_adjusted_close(adjusted, dividends, warnings)
    new = (
        adjusted.with_columns(adj_close.alias("adj_close"))
        .select("symbol", "date", *_OHLCV, "adj_close", "adj_version")
        .cast({c: pl.Float64 for c in _VALUE_COLS})  # DESIGN 3.2: DOUBLE end to end
    )
    if not existing.height:
        return new, False
    if _changed(existing, new):
        return new.with_columns(pl.lit(prev + 1, dtype=pl.Int32).alias("adj_version")), True
    if new.height == existing.height:
        return None, False
    return new, False


def materialise(store: Store, symbols: list[str] | None = None) -> MaterialiseReport:
    """Build `bars` (and `etf_bars` for symbols with gics_sector='ETF') from `bars_raw`."""
    if symbols is not None:
        bad = [s for s in symbols if not is_valid(s)]
        if bad:
            raise ValueError(f"invalid symbols: {bad[:5]}")
        targets = sorted(set(symbols))
    else:
        targets = store.read("SELECT DISTINCT symbol FROM bars_raw ORDER BY symbol")[
            "symbol"
        ].to_list()
    warnings: list[str] = []
    # A day with NO ingest_log verdict for 'polygon' (every yfinance-bootstrap day, or history
    # older than the Polygon backfill) has no judgement against it, so it is publishable. Only a
    # 'quarantined' verdict withholds a day (AMD-0019 2A); 'failed' means nothing was fetched.
    verdicts = store.read_ingest_verdicts(POLYGON)
    quarantined = frozenset(verdicts.filter(pl.col("status") == _QUARANTINED)["date"].to_list())
    flagged = store.read_bar_flags(targets, sorted(AGGREGATE_EXCLUDING_FLAGS))
    stats: dict = {
        "skipped_days": set(), "flagged": set(), "before_first": 0, "after_final": 0,
    }
    etfs = set(
        store.read("SELECT symbol FROM symbols WHERE gics_sector = ?", [ETF_LABEL])["symbol"]
    )
    membership = store.read("SELECT symbol, start_date, end_date FROM membership")
    splits = store.read_splits(None, _MIN_DATE, _MAX_DATE)
    dividends = store.read_dividends(None, _MIN_DATE, _MAX_DATE)
    # Actions recorded under an old ticker belong to the symbol its bars now live under
    # (AMD-0016 2D); the old-ticker partition keeps its own copy.
    redirect = {
        s: store.resolve_symbol(s, d)
        for s, d in {*zip(splits["symbol"], splits["date"], strict=True),
                     *zip(dividends["symbol"], dividends["date"], strict=True)}
    }

    def actions_for(table: pl.DataFrame, sym: str) -> pl.DataFrame:
        mine = [s for s, to in redirect.items() if s == sym or to == sym]
        return table.filter(pl.col("symbol").is_in(mine)).with_columns(pl.lit(sym).alias("symbol"))

    n_rows = n_readjusted = 0
    for lo in range(0, len(targets), _BATCH):
        batch = targets[lo : lo + _BATCH]
        raw_all = store.read_bars_raw(batch, _MIN_DATE, _MAX_DATE, None)
        old_bars = store.read_bars(batch, _MIN_DATE, _MAX_DATE)
        old_etf = store.read_etf_bars(batch, _MIN_DATE, _MAX_DATE)
        out_bars, out_etf = [], []
        for sym in batch:
            raw = raw_all.filter(pl.col("symbol") == sym)
            if raw.is_empty():
                warnings.append(_warn("no_bars_raw", sym, None, "symbol has no bars_raw rows"))
                continue
            is_etf = sym in etfs
            existing = (old_etf if is_etf else old_bars).filter(pl.col("symbol") == sym)
            continuity = store.resolve_symbol(sym, raw["date"].max()) != sym
            frame, readjusted = _materialise_symbol(
                sym, raw, existing, actions_for(splits, sym), actions_for(dividends, sym),
                membership.filter(pl.col("symbol") == sym), continuity, warnings,
                quarantined, flagged.filter(pl.col("symbol") == sym), stats,
            )
            n_readjusted += readjusted
            if frame is not None:
                (out_etf if is_etf else out_bars).append(frame)
        for frames, write in ((out_bars, store.write_bars), (out_etf, store.write_etf_bars)):
            if frames:
                n_rows += write(pl.concat(frames))
    by_date: dict[date, int] = {}
    for _sym, d in stats["flagged"]:
        by_date[d] = by_date.get(d, 0) + 1
    by_date = dict(sorted(by_date.items()))
    n_skipped = len(stats["skipped_days"])
    report = MaterialiseReport(
        len(targets), n_rows, n_readjusted, warnings, n_skipped, 0, len(stats["flagged"]),
        by_date, stats["before_first"], stats["after_final"],
    )
    detail = json.dumps(
        {
            "n_symbols": report.n_symbols, "n_rows": n_rows, "n_readjusted": n_readjusted,
            "n_days_quarantined_skipped": n_skipped,
            "n_symbol_days_flagged": report.n_symbol_days_flagged,
            "n_bars_before_first_membership": report.n_bars_before_first_membership,
            "n_bars_after_final_end_without_continuity": (
                report.n_bars_after_final_end_without_continuity
            ),
            "n_members_flagged_by_date": {d.isoformat(): n for d, n in by_date.items()},
            "n_warnings": len(warnings), "warnings": warnings[:_LOG_WARNINGS],
        }
    )
    store.log_ingest(datetime.now(UTC).date(), SOURCE, n_rows, "ok", detail)
    log.info(
        "materialise", n_symbols=report.n_symbols, n_rows=n_rows, n_readjusted=n_readjusted,
        n_warnings=len(warnings), n_days_quarantined_skipped=n_skipped,
        n_symbol_days_flagged=report.n_symbol_days_flagged,
        n_bars_before_first_membership=report.n_bars_before_first_membership,
        n_bars_after_final_end_without_continuity=report.n_bars_after_final_end_without_continuity,
    )
    return report


def equal_weight_aggregate(bars: pl.DataFrame, flagged: pl.DataFrame) -> pl.DataFrame:
    """Per-date equal-weight daily return over published symbol-days, flagged ones excluded.

    `bars`: published rows (symbol, date, adj_close). `flagged`: (symbol, date) pairs from
    `bar_flags` (see `AGGREGATE_EXCLUDING_FLAGS`). Only the aggregate excludes (AMD-0019 2A); the
    symbols' own series are untouched. Columns: date, n_members_with_bars, n_members_flagged
    (the DESIGN 6.1 coverage figure), n_members_included, eq_ret (mean of adj_close / prior
    adj_close - 1 over included symbols with a prior bar; null where there are none).
    """
    out_schema = {
        "date": pl.Date, "n_members_with_bars": pl.Int64, "n_members_flagged": pl.Int64,
        "n_members_included": pl.Int64, "eq_ret": pl.Float64,
    }
    if bars.is_empty():
        return pl.DataFrame(schema=out_schema)
    marks = flagged.select("symbol", "date").unique().with_columns(pl.lit(True).alias("_flagged"))
    frame = (
        bars.sort(["symbol", "date"])
        .with_columns(
            (pl.col("adj_close") / pl.col("adj_close").shift(1).over("symbol") - 1).alias("ret")
        )
        .join(marks, on=["symbol", "date"], how="left")
        .with_columns(pl.col("_flagged").fill_null(False))
    )
    return (
        frame.group_by("date")
        .agg(
            pl.len().alias("n_members_with_bars"),
            pl.col("_flagged").sum().alias("n_members_flagged"),
            (~pl.col("_flagged")).sum().alias("n_members_included"),
            pl.col("ret").filter(~pl.col("_flagged")).mean().alias("eq_ret"),
        )
        .cast(out_schema)
        .sort("date")
    )
