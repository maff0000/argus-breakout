"""One-off bootstrap history provider backed by yfinance (WO-0005, PID 8.6).

yfinance is an unofficial, optional dependency (`argus[bootstrap]`): it is
imported lazily inside methods. This provider is a bootstrap path only; it
tolerates NaN rows, missing symbols and renamed columns, and never retries a
chunk more than once.
"""

import re
import time
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any, Literal

import polars as pl
import structlog

from argus.data.providers.base import CANONICAL_BAR_COLUMNS, ProviderError
from argus.data.tickers import normalize, to_provider

CHUNK_SIZE = 50
_MISSING_DEP = "install extras: argus[bootstrap]"
_PRICE_FIELDS = ["open", "high", "low", "close", "adj_close", "volume"]
_BAR_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "adj_close": pl.Float64,
}
_ACTION_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "split_ratio": pl.Float64,
    "cash_dividend": pl.Float64,
}

# yfinance delivers one summed dividend per ex-date and no record identifier, so its
# `dividends.vendor_id` is this literal (AMD-0027 2A).
DIVIDEND_VENDOR_ID = "sum"
# It supplies neither `declaration_date` nor `frequency` either: the ingest writes no value for
# them, so they are NULL for every yfinance row (AMD-0029 2A) and the dedupe falls back to the
# amount for that source.

log = structlog.get_logger(__name__)


def _field_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class YFinanceProvider:
    source = "yfinance"
    basis: Literal["unadjusted", "split", "split_div"] = "split"

    def __init__(self, pause_s: float = 0.5) -> None:
        self.pause_s = pause_s
        self.nan_rows_dropped = 0  # cumulative count of NaN rows removed by daily_bars

    # ------------------------------------------------------------------ public
    def daily_bars(self, symbols: list[str], start: date, end: date) -> pl.DataFrame:
        """Canonical bar columns plus `adj_close`; symbols with no usable data are absent."""
        frames = [
            self._bars_from_raw(raw, chunk, start, end)
            for chunk, raw in self._download_chunks(symbols, start, end)
        ]
        if not frames:
            frames = [pl.DataFrame(schema=_BAR_SCHEMA)]
        out = pl.concat(frames).sort(["symbol", "date"])
        return out.select([*CANONICAL_BAR_COLUMNS, "adj_close"])

    def actions(self, symbols: list[str], start: date, end: date) -> pl.DataFrame:
        """Splits and dividends: [symbol, date, split_ratio|None, cash_dividend|None]."""
        frames = [
            self._actions_from_raw(raw, chunk, start, end)
            for chunk, raw in self._download_chunks(symbols, start, end)
        ]
        if not frames:
            return pl.DataFrame(schema=_ACTION_SCHEMA)
        return pl.concat(frames).sort(["symbol", "date"])

    # ------------------------------------------------------------------ download
    @staticmethod
    def _yf() -> Any:
        try:
            import yfinance
        except ImportError as exc:
            raise ProviderError(_MISSING_DEP) from exc
        return yfinance

    def _download_chunks(
        self, symbols: list[str], start: date, end: date
    ) -> Iterator[tuple[list[str], Any]]:
        yf = self._yf()
        for n, chunk in enumerate(_chunks(list(dict.fromkeys(symbols)), CHUNK_SIZE)):
            if n:
                time.sleep(self.pause_s)
            yield chunk, self._download_with_one_retry(yf, chunk, start, end)

    def _download_with_one_retry(self, yf: Any, chunk: list[str], start: date, end: date) -> Any:
        tickers = [to_provider(s, "yfinance") for s in chunk]
        kwargs = {
            "start": start.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),  # yfinance `end` is exclusive
            "auto_adjust": False,
            "actions": True,
            "threads": False,
            "progress": False,
            "group_by": "ticker",
        }
        try:
            return yf.download(tickers, **kwargs)
        except Exception as first:
            log.warning("yfinance_chunk_retry", error=type(first).__name__, symbols=len(chunk))
            time.sleep(self.pause_s)
            try:
                return yf.download(tickers, **kwargs)
            except Exception as second:
                raise ProviderError(
                    f"yfinance download failed for chunk of {len(chunk)}: "
                    f"{type(second).__name__}"
                ) from second

    # ------------------------------------------------------------------ flatten
    @staticmethod
    def _long(raw: Any, chunk: list[str]) -> pl.DataFrame:
        """yfinance wide frame -> long (symbol, date, <lower_snake fields>); tolerant."""
        if raw is None or getattr(raw, "empty", True):
            return pl.DataFrame()
        cols = raw.columns
        parts: list[tuple[str, Any]] = []
        if getattr(cols, "nlevels", 1) > 1:
            present = set(cols.get_level_values(0))
            for sym in chunk:
                ticker = to_provider(sym, "yfinance")
                if ticker in present:
                    parts.append((ticker, raw[ticker]))
        elif len(chunk) == 1:
            parts.append((to_provider(chunk[0], "yfinance"), raw))
        frames = []
        for ticker, sub in parts:
            try:
                sym = normalize(ticker, "yfinance")
            except ValueError:
                log.warning("yfinance_symbol_invalid", ticker=ticker[:12])
                continue
            try:
                flat = pl.from_pandas(sub.reset_index())
            except Exception as exc:  # malformed block: skip this symbol only
                log.warning("yfinance_symbol_unreadable", symbol=sym, error=type(exc).__name__)
                continue
            flat = flat.rename({c: _field_name(c) for c in flat.columns})
            if not flat.columns:
                continue
            flat = flat.rename({flat.columns[0]: "date"})
            dtype = flat.schema["date"]
            if isinstance(dtype, pl.Datetime):
                flat = flat.with_columns(pl.col("date").dt.date())
            elif dtype != pl.Date:
                continue
            frames.append(flat.with_columns(pl.lit(sym).alias("symbol")))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    def _bars_from_raw(self, raw: Any, chunk: list[str], start: date, end: date) -> pl.DataFrame:
        long = self._long(raw, chunk)
        required = ["open", "high", "low", "close", "volume"]
        if long.is_empty() or any(c not in long.columns for c in required):
            if not long.is_empty():
                log.warning("yfinance_columns_missing", columns=sorted(long.columns))
            return pl.DataFrame(schema=_BAR_SCHEMA)
        if "adj_close" not in long.columns:
            long = long.with_columns(pl.col("close").alias("adj_close"))
        fields = [f for f in _PRICE_FIELDS if f in long.columns]
        long = long.with_columns(
            [pl.col(f).cast(pl.Float64, strict=False).fill_nan(None) for f in fields]
        )
        usable = long.drop_nulls(required)
        self.nan_rows_dropped += long.height - usable.height
        out = usable.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        return out.select(list(_BAR_SCHEMA)).unique(
            subset=["symbol", "date"], keep="last", maintain_order=True
        )

    def _actions_from_raw(
        self, raw: Any, chunk: list[str], start: date, end: date
    ) -> pl.DataFrame:
        long = self._long(raw, chunk)
        if long.is_empty():
            return pl.DataFrame(schema=_ACTION_SCHEMA)
        for col in ("dividends", "stock_splits"):
            if col not in long.columns:
                long = long.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))
        div = pl.col("dividends").cast(pl.Float64, strict=False).fill_nan(None)
        spl = pl.col("stock_splits").cast(pl.Float64, strict=False).fill_nan(None)
        long = long.with_columns(
            pl.when(div > 0).then(div).alias("cash_dividend"),  # 0 / NaN -> None
            pl.when(spl > 0).then(spl).alias("split_ratio"),
        )
        out = long.filter(
            (pl.col("date") >= start)
            & (pl.col("date") <= end)
            & (pl.col("cash_dividend").is_not_null() | pl.col("split_ratio").is_not_null())
        )
        return out.select(list(_ACTION_SCHEMA)).cast(_ACTION_SCHEMA)
