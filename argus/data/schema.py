"""DuckDB schema for the Argus store (DESIGN.md 3.2, PID 8.5).

Types: DATE for dates, DOUBLE for prices/volumes, TIMESTAMP (UTC, naive) for
timestamps, TEXT for strings, JSON stored as TEXT.

`bars_raw`, `bars` and `etf_bars` are VIEWs over Parquet directories; their
DDL contains the placeholder `__GLOB__`, which `Store.init_schema` replaces
with the quoted parquet glob under the configured store directory.
"""

# 3: bar_flags (AMD-0018). 4: store_meta (AMD-0017/AMD-0018 2G, store relocation identity).
# 5: dividends.basis (AMD-0019 2B); bars/etf_bars price columns DOUBLE on disk (AMD-0019 2C).
SCHEMA_VERSION = 5

DIVIDEND_BASES = ("as_paid", "split_adjusted")

# Price columns of the parquet-backed bars / etf_bars tables (all float64 on disk).
BAR_PRICE_COLUMNS = ("open", "high", "low", "close", "volume", "adj_close")

_BAR_VIEW = (
    "CREATE OR REPLACE VIEW {name} AS SELECT {cols} "
    "FROM read_parquet(__GLOB__, hive_partitioning = true, union_by_name = true)"
)

_BARS_COLS = "symbol, date, open, high, low, close, volume, adj_close, adj_version"
_BARS_CAST = (
    "CAST(symbol AS TEXT) AS symbol, CAST(date AS DATE) AS date, "
    "CAST(open AS DOUBLE) AS open, CAST(high AS DOUBLE) AS high, "
    "CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close, "
    "CAST(volume AS DOUBLE) AS volume, CAST(adj_close AS DOUBLE) AS adj_close, "
    "CAST(adj_version AS INTEGER) AS adj_version"
)

# Columns of the parquet-backed bar tables, in order (used by Store).
BARS_RAW_COLUMNS = [
    "symbol", "date", "open", "high", "low", "close", "volume", "source", "basis", "ingested_at",
]
BARS_COLUMNS = _BARS_COLS.split(", ")

# Parquet-backed views: table name -> (parquet sub-directory, partition column).
VIEW_PARQUET_DIRS = {
    "bars_raw": ("bars_raw", "year"),
    "bars": ("bars", "symbol"),
    "etf_bars": ("etf_bars", "symbol"),
}

VIEWS = frozenset(VIEW_PARQUET_DIRS)

DDL: dict[str, str] = {
    "symbols": """CREATE TABLE IF NOT EXISTS symbols (
        symbol TEXT PRIMARY KEY, name TEXT, gics_sector TEXT, gics_industry_group TEXT,
        exchange TEXT, first_date DATE, last_date DATE, active BOOLEAN)""",
    "membership": """CREATE TABLE IF NOT EXISTS membership (
        symbol TEXT, start_date DATE, end_date DATE, source TEXT,
        PRIMARY KEY (symbol, start_date))""",
    "bars_raw": _BAR_VIEW.format(
        name="bars_raw",
        cols=(
            "CAST(symbol AS TEXT) AS symbol, CAST(date AS DATE) AS date, "
            "CAST(open AS DOUBLE) AS open, CAST(high AS DOUBLE) AS high, "
            "CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close, "
            "CAST(volume AS DOUBLE) AS volume, CAST(source AS TEXT) AS source, "
            "CAST(basis AS TEXT) AS basis, CAST(ingested_at AS TIMESTAMP) AS ingested_at"
        ),
    ),
    "splits": """CREATE TABLE IF NOT EXISTS splits (
        symbol TEXT, date DATE, ratio DOUBLE NOT NULL, source TEXT,
        PRIMARY KEY (symbol, date, source))""",
    "dividends": """CREATE TABLE IF NOT EXISTS dividends (
        symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL,
        basis TEXT NOT NULL CHECK (basis IN ('as_paid', 'split_adjusted')), source TEXT,
        PRIMARY KEY (symbol, date, source))""",
    "bars": _BAR_VIEW.format(name="bars", cols=_BARS_CAST),
    "etf_bars": _BAR_VIEW.format(name="etf_bars", cols=_BARS_CAST),
    "iv_daily": """CREATE TABLE IF NOT EXISTS iv_daily (
        symbol TEXT, date DATE, iv30 DOUBLE, hv30 DOUBLE, source TEXT,
        PRIMARY KEY (symbol, date))""",
    "composites": """CREATE TABLE IF NOT EXISTS composites (
        date DATE, group_id TEXT, level TEXT, eq_close DOUBLE, eq_ret DOUBLE, n_members INTEGER,
        pct_above_20 DOUBLE, pct_above_50 DOUBLE, pct_above_200 DOUBLE, nh20 INTEGER,
        nl20 INTEGER, nh252 INTEGER, nl252 INTEGER, adv INTEGER, dec INTEGER, dollar_vol DOUBLE,
        PRIMARY KEY (date, group_id))""",
    # Feature columns are defined by the feature-engine Work Order (DESIGN 3.2 leaves them open).
    "features": """CREATE TABLE IF NOT EXISTS features (
        date DATE, symbol TEXT, PRIMARY KEY (date, symbol))""",
    "market_daily": """CREATE TABLE IF NOT EXISTS market_daily (
        date DATE PRIMARY KEY, regime TEXT, pct_above_20 DOUBLE, pct_above_50 DOUBLE,
        pct_above_200 DOUBLE, ad_line DOUBLE, nhnl20 INTEGER, nhnl252 INTEGER,
        mcclellan DOUBLE, mcclellan_sum DOUBLE, pct_rsi_gt50 DOUBLE, rsp_spy DOUBLE,
        rsp_spy_slope20 DOUBLE, dispersion21 DOUBLE, avg_corr21 DOUBLE, ratio_z TEXT)""",
    "sector_daily": """CREATE TABLE IF NOT EXISTS sector_daily (
        date DATE, group_id TEXT, level TEXT, rs_ratio DOUBLE, rs_mom DOUBLE,
        d_rs_mom5 DOUBLE, quadrant TEXT, heading_deg DOUBLE, rank_rs21 INTEGER,
        rank_delta10 INTEGER, dist_days25 INTEGER, updown_vol20 DOUBLE, vol_share DOUBLE,
        vol_share_z DOUBLE, divergence BOOLEAN, rotation_score DOUBLE, flag TEXT,
        PRIMARY KEY (date, group_id))""",
    "events": """CREATE TABLE IF NOT EXISTS events (
        symbol TEXT, date DATE, type TEXT, time_of_day TEXT, source TEXT, confirmed BOOLEAN,
        PRIMARY KEY (symbol, date, type))""",
    "ranks": """CREATE TABLE IF NOT EXISTS ranks (
        date DATE, symbol TEXT, playbook TEXT, composite DOUBLE, verdict TEXT, reasons TEXT,
        PRIMARY KEY (date, symbol, playbook))""",
    "evidence_packs": """CREATE TABLE IF NOT EXISTS evidence_packs (
        date DATE PRIMARY KEY, tokens INTEGER, json TEXT)""",
    "briefs": """CREATE TABLE IF NOT EXISTS briefs (
        date DATE, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, text TEXT,
        grade TEXT, PRIMARY KEY (date, model))""",
    "reconcile_log": """CREATE TABLE IF NOT EXISTS reconcile_log (
        date DATE, symbol TEXT, field TEXT, ours DOUBLE, theirs DOUBLE, pct_diff DOUBLE,
        breach BOOLEAN, PRIMARY KEY (date, symbol, field))""",
    "ingest_log": """CREATE TABLE IF NOT EXISTS ingest_log (
        date DATE, source TEXT, rows INTEGER, status TEXT, detail TEXT, finished_at TIMESTAMP,
        PRIMARY KEY (date, source, finished_at))""",
    # Per-symbol-day data-quality findings (AMD-0018 2C). flag: jump_unexplained |
    # jump_split_reconciled; the set is enumerated in argus/data/validate.py.
    "bar_flags": """CREATE TABLE IF NOT EXISTS bar_flags (
        symbol TEXT, date DATE, source TEXT, flag TEXT, detail TEXT,
        PRIMARY KEY (symbol, date, source, flag))""",
    # Store identity: key 'store_dir' = resolved store directory the views were built against.
    "store_meta": """CREATE TABLE IF NOT EXISTS store_meta (
        key TEXT PRIMARY KEY, value TEXT)""",
    "schema_version": """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY, applied_at TIMESTAMP)""",
}
