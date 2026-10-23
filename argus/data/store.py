"""DuckDB + Parquet store (PID 8.5, DESIGN 3.2).

Small tables live in `<store_dir>/argus.duckdb`; `bars_raw`, `bars` and
`etf_bars` are VIEWs over Parquet directories under `<store_dir>/parquet/`.
All SQL carrying external values is parameterised. The only text spliced into
SQL is (a) table/column identifiers validated against the schema and quoted,
and (b) the store-derived parquet glob, with quotes doubled.
"""

import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import polars as pl
import structlog

from argus.data import schema
from argus.data.tickers import is_valid

log = structlog.get_logger()

DB_NAME = "argus.duckdb"
_EMPTY_YEAR = "year=1900"
_EMPTY_SYMBOL = "symbol=_EMPTY_"
_PARTITION_FILE = "part.parquet"

_BARS_RAW_POLARS = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "source": pl.String,
    "basis": pl.String,
    "ingested_at": pl.Datetime("us"),
}
_BARS_POLARS = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "adj_close": pl.Float64,
    "adj_version": pl.Int32,
}
_BASES = {"unadjusted", "split", "split_div"}

# Whether each source's dividend `cash_amount` is on the share count of the ex-date ('as_paid')
# or already restated onto the current basis ('split_adjusted'). MEASURED on the stored data
# (WO-0013, docs/evidence/WO-0013/dividend-basis.md), never assumed (AMD-0019 2B). The one place
# the mapping lives: the write path (`Store.upsert`) and the schema-5 migration both use it.
DIVIDEND_BASIS_BY_SOURCE: dict[str, str] = {"polygon": "as_paid", "yfinance": "split_adjusted"}


def dividend_basis(source: str | None) -> str:
    """The basis of a source's dividend amounts; an unknown source RAISES (never a default)."""
    try:
        return DIVIDEND_BASIS_BY_SOURCE[source]  # type: ignore[index]
    except KeyError:
        raise ValueError(f"no measured dividend basis for source {source!r}") from None


def stamp_dividend_basis(df: pl.DataFrame) -> pl.DataFrame:
    """Add `basis` from each row's `source`; a supplied `basis` must agree with it."""
    if "source" not in df.columns:
        raise ValueError("dividends need a source column to carry a basis")
    basis = pl.Series("basis", [dividend_basis(s) for s in df["source"].to_list()], dtype=pl.String)
    if "basis" in df.columns and not df["basis"].equals(basis):
        raise ValueError("dividends.basis disagrees with the measured basis of its source")
    return df.with_columns(basis)


def _backfill_vendor_id(source: str | None) -> str:
    """The migration's vendor_id for a pre-6 row: 'sum' (yfinance) or the 'legacy' placeholder."""
    if source == "yfinance":
        return schema.SUMMED_VENDOR_ID
    if source == "polygon":
        return schema.LEGACY_VENDOR_ID
    raise ValueError(f"no vendor_id backfill for dividend source {source!r}")


def check_dividend_vendor_id(df: pl.DataFrame) -> None:
    """A dividends write must name the source's own record id on every row (AMD-0027 2A)."""
    if "vendor_id" not in df.columns:
        raise ValueError("dividends need a vendor_id column (the source's own record id)")
    if any(not isinstance(v, str) or not v for v in df["vendor_id"].to_list()):
        raise ValueError("dividends.vendor_id must be a non-empty string on every row")


class StoreRelocatedError(RuntimeError):
    """The store was copied/moved: its recorded directory differs from the one in use."""


def _utcnow() -> datetime:
    """Naive datetime holding the current UTC time (DuckDB TIMESTAMP is UTC by convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _quote_ident(name: str) -> str:
    return "\"" + name.replace("\"", "\"\"") + "\""


def _check_symbols(symbols: list[str]) -> None:
    bad = [s for s in symbols if not is_valid(s)]
    if bad:
        raise ValueError(f"invalid symbols: {bad[:5]}")


def _atomic_write_parquet(df: pl.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    os.close(fd)
    try:
        df.write_parquet(tmp_name)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, store_dir: Path, config_dir: Path | None = None) -> None:
        self.store_dir = Path(store_dir)
        self.db_path = self.store_dir / DB_NAME
        self.parquet_dir = self.store_dir / "parquet"
        # Only `resolve_symbol` reads config; None means settings.argus_config_dir at call time.
        self._config_dir = None if config_dir is None else Path(config_dir)
        self._rename_chain: dict[str, str] | None = None
        # Set to the previously recorded store_dir when a read-write connect repaired a relocation.
        self.repaired_from: str | None = None

    # ------------------------------------------------------------------ connection
    def connect(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        if not read_only:
            self._ensure_store_dir()
        con = duckdb.connect(str(self.db_path), read_only=read_only)
        try:
            self._check_identity(con, read_only)
        except BaseException:
            con.close()
            raise
        return con

    def _check_identity(self, con: duckdb.DuckDBPyConnection, read_only: bool) -> None:
        """Compare the recorded store_dir with the one in use (one small local SELECT)."""
        try:
            row = con.execute(
                "SELECT value FROM store_meta WHERE key = ?", ["store_dir"]
            ).fetchone()
        except duckdb.CatalogException:
            return  # brand-new store, or one created before schema 4: first use
        if row is None:
            return
        recorded, current = row[0], str(self.store_dir.resolve())
        if recorded == current:
            return
        if read_only:
            raise StoreRelocatedError(
                f"store relocated: recorded {recorded!r}, now {current!r}; "
                "a read-write `argus init-store` repairs it"
            )
        self._ensure_parquet_dirs()
        con.execute("BEGIN")
        try:
            self._create_views(con)
            self._record_store_dir(con)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        self.repaired_from = recorded
        log.warning("store_relocated", recorded=recorded, current=current, action="views_recreated")

    def _create_views(self, con: duckdb.DuckDBPyConnection) -> None:
        for name in schema.VIEWS:
            literal = "\x27" + self._glob(name).replace("\x27", "\x27\x27") + "\x27"
            con.execute(schema.DDL[name].replace("__GLOB__", literal))

    def _record_store_dir(self, con: duckdb.DuckDBPyConnection) -> None:
        con.execute(
            "INSERT INTO store_meta VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ["store_dir", str(self.store_dir.resolve())],
        )

    def recorded_store_dir(self) -> str | None:
        """The store_dir recorded in store_meta (None if absent)."""
        df = self.read("SELECT value FROM store_meta WHERE key = ?", ["store_dir"])
        return df["value"][0] if df.height else None

    def _ensure_store_dir(self) -> None:
        if not self.store_dir.exists():
            self.store_dir.mkdir(parents=True, mode=0o750, exist_ok=True)
            os.chmod(self.store_dir, 0o750)  # noqa: S103 - owner+group only, per WO-0002 4

    # ------------------------------------------------------------------ schema
    def _glob(self, table: str) -> str:
        sub, _ = schema.VIEW_PARQUET_DIRS[table]
        return str((self.parquet_dir / sub).resolve() / "**" / "*.parquet")

    def _ensure_parquet_dirs(self) -> None:
        raw_empty = self.parquet_dir / "bars_raw" / _EMPTY_YEAR / "empty.parquet"
        if not raw_empty.exists():
            _atomic_write_parquet(pl.DataFrame(schema={**_BARS_RAW_POLARS}), raw_empty)
        for sub in ("bars", "etf_bars"):
            empty = self.parquet_dir / sub / _EMPTY_SYMBOL / "empty.parquet"
            if not empty.exists():
                _atomic_write_parquet(pl.DataFrame(schema={**_BARS_POLARS}), empty)

    def init_schema(self) -> None:
        """Create directories, tables and views if missing; record schema_version once."""
        self._ensure_store_dir()
        self._ensure_parquet_dirs()
        con = self.connect()
        try:
            con.execute("BEGIN")
            self._migrate_dividends(con)
            for name, ddl in schema.DDL.items():
                if name not in schema.VIEWS:
                    con.execute(ddl)
            self._create_views(con)
            self._record_store_dir(con)
            con.execute(
                "INSERT INTO schema_version SELECT ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = ?)",
                [schema.SCHEMA_VERSION, _utcnow(), schema.SCHEMA_VERSION],
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _migrate_dividends(self, con: duckdb.DuckDBPyConnection) -> bool:
        """Schemas 5, 6 and 7: rebuild an older `dividends` table to the current columns.

        `basis` is backfilled per source (schema 5). `vendor_id` (schema 6, AMD-0027 2A) is
        'sum' for yfinance, whose figure is already one summed total per ex-date, and 'legacy'
        for a stored Polygon row: its real `id` was never recorded and cannot be derived locally,
        so 'legacy' is a PLACEHOLDER that keeps NOT NULL true; `ingest polygon-actions`
        replaces it with the real records (see `ingest_polygon_actions`). `declaration_date` and
        `frequency` (schema 7, AMD-0029 2A) are backfilled NULL: neither can be derived locally,
        and `ingest polygon-actions` populates them by upserting over the existing primary key.
        Idempotent (a table with every column is left alone); runs inside the caller's
        transaction; all-or-nothing: an unknown source raises before anything is dropped.
        Returns True when it rebuilt."""
        cols = [
            r[0]
            for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = 'dividends'"
            ).fetchall()
        ]
        if not cols or all(
            c in cols for c in ("basis", "vendor_id", "declaration_date", "frequency")
        ):
            return False
        keep = [
            c
            for c in (
                "symbol", "date", "cash_amount", "basis", "source", "vendor_id",
                "declaration_date", "frequency",
            )
            if c in cols
        ]
        old = con.execute("SELECT " + ", ".join(keep) + " FROM dividends").pl()  # noqa: S608
        filled = old if "basis" in cols else stamp_dividend_basis(old)
        if "vendor_id" not in cols:
            ids = [_backfill_vendor_id(src) for src in filled["source"].to_list()]
            filled = filled.with_columns(pl.Series("vendor_id", ids, dtype=pl.String))
        if "declaration_date" not in cols:
            filled = filled.with_columns(pl.lit(None, dtype=pl.Date).alias("declaration_date"))
        if "frequency" not in cols:
            filled = filled.with_columns(pl.lit(None, dtype=pl.Int64).alias("frequency"))
        filled = filled.select(
            "symbol", "date", "cash_amount", "basis", "source", "vendor_id",
            "declaration_date", "frequency",
        )
        con.execute("DROP TABLE dividends")
        con.execute(schema.DDL["dividends"])
        con.register("old_dividends", filled.to_arrow())
        try:
            con.execute(
                "INSERT INTO dividends (symbol, date, cash_amount, basis, source, vendor_id, "
                "declaration_date, frequency) "
                "SELECT symbol, date, cash_amount, basis, source, vendor_id, "
                "declaration_date, CAST(frequency AS INTEGER) FROM old_dividends"
            )
        finally:
            con.unregister("old_dividends")
        return True

    def migrate(self) -> list[tuple[str, int, int]]:
        """Bring a store up to the current schema in place, from stored data only (WO-0013).

        Rebuilds `dividends` with a backfilled `basis`, `vendor_id`, `declaration_date` and
        `frequency`, widens any float32 price
        column of the `bars` / `etf_bars` parquet to float64, records the schema version. Never
        reads or writes `bars_raw` beyond a row count. Idempotent.
        Returns (table, rows_before, rows_after)."""
        self.connect().close()  # a read-write connect first repairs a relocated COPY's views
        before = self._row_counts()
        self.init_schema()  # includes the dividends rebuild, transactionally
        for sub in ("bars", "etf_bars"):
            self._widen_parquet(sub)
        return [(t, n, self._row_counts()[t]) for t, n in before.items()]

    def _row_counts(self) -> dict[str, int]:
        con = self.connect(read_only=True)
        try:
            names = [
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main' ORDER BY table_name"
                ).fetchall()
            ]
            return {
                n: con.execute("SELECT count(*) FROM " + _quote_ident(n)).fetchone()[0]  # noqa: S608
                for n in names
            }
        finally:
            con.close()

    def _widen_parquet(self, sub: str) -> int:
        """Rewrite (atomically) any `<sub>` parquet file holding a float32 price column."""
        n = 0
        for path in sorted((self.parquet_dir / sub).rglob("*.parquet")):
            cols = [
                c for c, t in pl.read_parquet_schema(path).items()
                if c in schema.BAR_PRICE_COLUMNS and t == pl.Float32
            ]
            if cols:
                df = pl.read_parquet(path).cast({c: pl.Float64 for c in cols})
                _atomic_write_parquet(df, path)
                n += 1
        return n

    # ------------------------------------------------------------------ generic access
    def read(self, sql: str, params: list | None = None) -> pl.DataFrame:
        """Run a read query; external values must be passed in `params` (`?` placeholders)."""
        con = self.connect(read_only=True)
        try:
            return con.execute(sql, params or []).pl()
        finally:
            con.close()

    def upsert(self, table: str, df: pl.DataFrame, keys: list[str]) -> int:
        """INSERT ... ON CONFLICT DO UPDATE in one transaction; returns rows written."""
        if table not in schema.DDL or table in schema.VIEWS:
            raise ValueError(f"cannot upsert into {table!r}")
        if df.is_empty():
            return 0
        if "symbol" in df.columns:
            _check_symbols(df["symbol"].to_list())
        if table == "dividends":
            df = stamp_dividend_basis(df)  # every dividends row carries its source's basis
            check_dividend_vendor_id(df)
        con = self.connect()
        try:
            known = [
                r[0]
                for r in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = \x27main\x27 AND table_name = ?",
                    [table],
                ).fetchall()
            ]
            cols = list(df.columns)
            if not keys or any(c not in known for c in cols) or any(k not in cols for k in keys):
                raise ValueError(f"columns/keys not valid for {table!r}")
            df = df.unique(subset=keys, keep="last", maintain_order=True)
            q_cols = ", ".join(_quote_ident(c) for c in cols)
            q_keys = ", ".join(_quote_ident(k) for k in keys)
            updates = [c for c in cols if c not in keys]
            if updates:
                action = "DO UPDATE SET " + ", ".join(
                    _quote_ident(c) + " = EXCLUDED." + _quote_ident(c) for c in updates
                )
            else:
                action = "DO NOTHING"
            # identifiers: schema-validated + quoted; values travel via the registered relation
            stmt = (
                "INSERT INTO " + _quote_ident(table) + " (" + q_cols + ") SELECT " + q_cols  # noqa: S608
                + " FROM incoming ON CONFLICT (" + q_keys + ") " + action
            )
            con.register("incoming", df.to_arrow())
            con.execute("BEGIN")
            try:
                con.execute(stmt)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                con.unregister("incoming")
            return df.height
        finally:
            con.close()

    # ------------------------------------------------------------------ bars_raw
    def write_bars_raw(self, df: pl.DataFrame) -> int:
        """Dedupe on (symbol,date,source) keeping latest ingested_at; write per year partition."""
        if df.is_empty():
            return 0
        missing = [c for c in schema.BARS_RAW_COLUMNS if c not in df.columns and c != "ingested_at"]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        if "ingested_at" not in df.columns:
            df = df.with_columns(pl.lit(_utcnow()).alias("ingested_at"))
        df = df.select(schema.BARS_RAW_COLUMNS).cast(_BARS_RAW_POLARS)
        _check_symbols(df["symbol"].unique().to_list())
        bad_basis = set(df["basis"].unique().to_list()) - _BASES
        if bad_basis:
            raise ValueError(f"invalid basis: {sorted(bad_basis)}")
        keys = ["symbol", "date", "source"]
        df = df.sort("ingested_at", maintain_order=True).unique(
            subset=keys, keep="last", maintain_order=True
        )
        years = df["date"].dt.year()
        for year in sorted(years.unique().to_list()):
            part = df.filter(years == year)
            target = self.parquet_dir / "bars_raw" / f"year={year:04d}" / _PARTITION_FILE
            if target.exists():
                existing = pl.read_parquet(target).cast(_BARS_RAW_POLARS)
                part = pl.concat([existing, part]).sort("ingested_at", maintain_order=True)
                part = part.unique(subset=keys, keep="last", maintain_order=True)
            _atomic_write_parquet(part.sort(keys), target)
        return df.height

    def read_bars_raw(
        self, symbols: list[str] | None, start: date, end: date, source: str | None
    ) -> pl.DataFrame:
        sql = "SELECT * FROM bars_raw WHERE date >= ? AND date <= ?"
        params: list = [start, end]
        if symbols is not None:
            _check_symbols(symbols)
            sql += " AND symbol IN (SELECT unnest(?))"
            params.append(symbols)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        return self.read(sql + " ORDER BY symbol, date, source", params)

    # ------------------------------------------------------------------ bars / etf_bars
    def _write_bar_table(self, sub: str, df: pl.DataFrame) -> int:
        """Replace the partition of every symbol present in `df` (`<sub>/symbol=<SYM>`)."""
        if df.is_empty():
            return 0
        missing = [c for c in schema.BARS_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        df = df.select(schema.BARS_COLUMNS).cast(_BARS_POLARS)
        _check_symbols(df["symbol"].unique().to_list())
        df = df.unique(subset=["symbol", "date"], keep="last", maintain_order=True)
        for (sym,), part in df.partition_by("symbol", as_dict=True, maintain_order=True).items():
            target = self.parquet_dir / sub / f"symbol={sym}" / _PARTITION_FILE
            _atomic_write_parquet(part.sort("date"), target)
        return df.height

    def _read_bar_table(
        self, table: str, symbols: list[str] | None, start: date, end: date
    ) -> pl.DataFrame:
        # `table` is one of two constant names chosen by the callers below.
        sql = "SELECT * FROM " + table + " WHERE date >= ? AND date <= ?"  # noqa: S608
        params: list = [start, end]
        if symbols is not None:
            _check_symbols(symbols)
            sql += " AND symbol IN (SELECT unnest(?))"
            params.append(symbols)
        return self.read(sql + " ORDER BY symbol, date", params)

    def write_bars(self, df: pl.DataFrame) -> int:
        """Replace the partition of every symbol present in `df` (symbol=<SYM>)."""
        return self._write_bar_table("bars", df)

    def read_bars(self, symbols: list[str] | None, start: date, end: date) -> pl.DataFrame:
        return self._read_bar_table("bars", symbols, start, end)

    def write_etf_bars(self, df: pl.DataFrame) -> int:
        """As `write_bars`, for symbols classified as ETFs (`etf_bars`)."""
        return self._write_bar_table("etf_bars", df)

    def read_etf_bars(self, symbols: list[str] | None, start: date, end: date) -> pl.DataFrame:
        return self._read_bar_table("etf_bars", symbols, start, end)

    # ------------------------------------------------------------------ corporate actions
    def _read_actions(
        self, table: str, symbols: list[str] | None, start: date, end: date
    ) -> pl.DataFrame:
        # `table` is one of two constant names chosen by the callers below.
        sql = "SELECT * FROM " + table + " WHERE date >= ? AND date <= ?"  # noqa: S608
        params: list = [start, end]
        if symbols is not None:
            _check_symbols(symbols)
            sql += " AND symbol IN (SELECT unnest(?))"
            params.append(symbols)
        return self.read(sql + " ORDER BY symbol, date, source", params)

    def read_splits(self, symbols: list[str] | None, start: date, end: date) -> pl.DataFrame:
        return self._read_actions("splits", symbols, start, end)

    def read_dividends(self, symbols: list[str] | None, start: date, end: date) -> pl.DataFrame:
        return self._read_actions("dividends", symbols, start, end)

    # ------------------------------------------------------------------ quality verdicts
    def read_ingest_verdicts(self, source: str) -> pl.DataFrame:
        """(date, status): the latest ingest_log verdict per day for `source`."""
        return self.read(
            "SELECT date, status FROM ingest_log WHERE source = ? "
            "QUALIFY row_number() OVER (PARTITION BY date ORDER BY finished_at DESC) = 1",
            [source],
        )

    def read_bar_flags(self, symbols: list[str] | None, flags: list[str]) -> pl.DataFrame:
        """(symbol, date, source, flag) rows of bar_flags carrying one of `flags`."""
        sql = "SELECT symbol, date, source, flag FROM bar_flags WHERE flag IN (SELECT unnest(?))"
        params: list = [flags]
        if symbols is not None:
            _check_symbols(symbols)
            sql += " AND symbol IN (SELECT unnest(?))"
            params.append(symbols)
        return self.read(sql + " ORDER BY symbol, date, source, flag", params)

    # ------------------------------------------------------------------ renames (AMD-0016 2D)
    def _renames(self) -> dict[str, str]:
        """old ticker -> new ticker from config/ticker_renames.yaml (read once per Store)."""
        if self._rename_chain is None:
            # Imported here: argus.data.universe imports this module.
            from argus.data.universe import load_renames
            from argus.settings import get_settings

            config_dir = self._config_dir or get_settings().argus_config_dir
            self._rename_chain = {r.old: r.new for r in load_renames(config_dir)}
        return self._rename_chain

    def resolve_symbol(self, symbol: str, as_of: date) -> str:
        """The symbol under which bars for `symbol` on `as_of` are stored.

        Follows the `config/ticker_renames.yaml` chain FORWARD to the current symbol: the free
        sources serve a renamed company's whole history under its new ticker (AMD-0016 2D), so
        the redirection does not depend on `as_of`, which only labels the logged record. An
        unmapped symbol is returned unchanged; the caller counts one with no bars as
        `without bars`. Every redirection is logged (`symbol_redirected`).
        """
        _check_symbols([symbol])
        renames = self._renames()
        resolved, seen = symbol, {symbol}
        while resolved in renames and renames[resolved] not in seen:
            resolved = renames[resolved]
            seen.add(resolved)
        if resolved != symbol:
            log.info(
                "symbol_redirected", symbol=symbol, resolved=resolved, as_of=as_of.isoformat()
            )
        return resolved

    # ------------------------------------------------------------------ catalog helpers
    def members_on(self, d: date) -> list[str]:
        """Symbols in the index on `d`: start_date <= d and (end_date is NULL or d <= end_date)."""
        df = self.read(
            "SELECT DISTINCT symbol FROM membership "
            "WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?) ORDER BY symbol",
            [d, d],
        )
        return df["symbol"].to_list()

    def log_ingest(self, date: date, source: str, rows: int, status: str, detail: str = "") -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO ingest_log (date, source, rows, status, detail, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [date, source, rows, status, detail, _utcnow()],
            )
        finally:
            con.close()
