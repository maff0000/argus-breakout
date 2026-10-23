from datetime import date

import duckdb
import polars as pl
import pytest

from argus.data.schema import DDL, SCHEMA_VERSION
from argus.data.store import Store

DESIGN_TABLES = [
    "symbols", "membership", "bars_raw", "splits", "dividends", "bars", "etf_bars", "iv_daily",
    "composites", "features", "market_daily", "sector_daily", "events", "ranks",
    "evidence_packs", "briefs", "reconcile_log", "ingest_log", "bar_flags", "store_meta",
    "schema_version",
]


def _tables(store):
    df = store.read(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?", ["main"]
    )
    return set(df["table_name"].to_list())


def test_all_design_tables_present(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    assert len(DESIGN_TABLES) == 21
    assert set(DDL) == set(DESIGN_TABLES)
    assert _tables(store) == set(DESIGN_TABLES)
    assert (tmp_path / "store" / "argus.duckdb").is_file()
    assert (tmp_path / "store").stat().st_mode & 0o777 == 0o750


def test_init_idempotent(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    store.init_schema()
    sv = store.read("SELECT version FROM schema_version")
    assert sv["version"].to_list() == [SCHEMA_VERSION]
    assert _tables(store) == set(DESIGN_TABLES)
    assert store.read("SELECT count(*) AS n FROM bars_raw")["n"][0] == 0
    assert store.read("SELECT count(*) AS n FROM bars")["n"][0] == 0
    assert store.read("SELECT count(*) AS n FROM etf_bars")["n"][0] == 0


def _row(sym, d, val, src, col):
    frame = pl.DataFrame({"symbol": [sym], "date": [d], col: [val], "source": [src]})
    # dividends carry the source's record id (AMD-0027 2A); splits do not
    return frame.with_columns(pl.lit("rec-1").alias("vendor_id")) if col == "cash_amount" else frame


def test_actions_tables_keyed_by_source(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    d = date(2024, 6, 10)
    keys = ["symbol", "date", "source"]
    store.upsert("splits", _row("AAA", d, 2.0, "polygon", "ratio"), keys)
    store.upsert("splits", _row("AAA", d, 2.0, "yfinance", "ratio"), keys)
    dkeys = [*keys, "vendor_id"]
    store.upsert("dividends", _row("AAA", d, 0.25, "polygon", "cash_amount"), dkeys)
    store.upsert("dividends", _row("AAA", d, 0.25, "yfinance", "cash_amount"), dkeys)
    splits = store.read("SELECT source FROM splits ORDER BY source")
    divs = store.read("SELECT source FROM dividends ORDER BY source")
    assert splits["source"].to_list() == ["polygon", "yfinance"]
    assert divs["source"].to_list() == ["polygon", "yfinance"]
    # a split and a dividend on the same (symbol, date) coexist, none nulled
    assert store.read("SELECT ratio FROM splits WHERE source = ?", ["polygon"])["ratio"][0] == 2.0
    cash = store.read("SELECT cash_amount FROM dividends WHERE source = ?", ["polygon"])
    assert cash["cash_amount"][0] == 0.25
    total = store.read(
        "SELECT (SELECT count(*) FROM splits) + (SELECT count(*) FROM dividends) AS n"
    )
    assert total["n"][0] == 4


def test_actions_measures_not_null(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    con = store.connect()
    try:
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO splits VALUES (?, ?, NULL, ?)", ["AAA", date(2024, 1, 2), "x"])
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO dividends (symbol, date, cash_amount, basis, source, vendor_id) "
                "VALUES (?, ?, NULL, 'as_paid', ?, ?)",
                ["AAA", date(2024, 1, 2), "x", "rec-1"],
            )
    finally:
        con.close()


def test_schema_version_is_8(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    store.init_schema()
    assert SCHEMA_VERSION == 8
    sv = store.read("SELECT version FROM schema_version")
    assert sv["version"].to_list() == [8]
