from argus.data.schema import DDL, SCHEMA_VERSION
from argus.data.store import Store

DESIGN_TABLES = [
    "symbols", "membership", "bars_raw", "adjustments", "bars", "etf_bars", "iv_daily",
    "composites", "features", "market_daily", "sector_daily", "events", "ranks",
    "evidence_packs", "briefs", "reconcile_log", "ingest_log", "schema_version",
]


def _tables(store):
    df = store.read(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?", ["main"]
    )
    return set(df["table_name"].to_list())


def test_all_design_tables_present(tmp_path):
    store = Store(tmp_path / "store")
    store.init_schema()
    assert len(DESIGN_TABLES) == 18
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
