import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from argus.data.store import Store, StoreRelocatedError

SAMPLE = Path(__file__).parent / "fixtures" / "bars" / "sample_bars.parquet"
QUOTED = "O'Brien; DROP TABLE symbols;--"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "store")
    s.init_schema()
    return s


def _symbols_df(names):
    return pl.DataFrame(
        {
            "symbol": names,
            "name": [f"{n} Inc" for n in names],
            "active": [True] * len(names),
        }
    )


def test_upsert_is_idempotent(store):
    df = _symbols_df(["AAA", "BBB"])
    store.upsert("symbols", df, ["symbol"])
    store.upsert("symbols", df, ["symbol"])
    assert store.read("SELECT count(*) AS n FROM symbols")["n"][0] == 2
    changed = df.with_columns(pl.lit("Renamed").alias("name"))
    store.upsert("symbols", changed, ["symbol"])
    out = store.read("SELECT name FROM symbols ORDER BY symbol")
    assert out["name"].to_list() == ["Renamed", "Renamed"]


def test_upsert_rejects_bad_input(store):
    with pytest.raises(ValueError):
        store.upsert("symbols", _symbols_df(["bad symbol"]), ["symbol"])
    with pytest.raises(ValueError):
        store.upsert("bars", _symbols_df(["AAA"]), ["symbol"])
    with pytest.raises(ValueError):
        store.upsert("symbols", _symbols_df(["AAA"]).rename({"name": "x; DROP"}), ["symbol"])


def test_bars_raw_roundtrip_and_dedupe(store, tmp_path):
    sample = pl.read_parquet(SAMPLE)
    assert sample.height == 90
    store.write_bars_raw(sample)
    store.write_bars_raw(sample)
    out = store.read_bars_raw(None, date(2024, 1, 1), date(2024, 12, 31), None)
    assert out.height == 90
    assert out.select(["symbol", "date", "source"]).is_unique().all()
    expected = sample.sort(["symbol", "date", "source"])
    assert out["close"].to_list() == expected["close"].to_list()
    assert (tmp_path / "store" / "parquet" / "bars_raw" / "year=2024").is_dir()
    # a later ingest of the same key wins
    newer = sample.head(1).with_columns(
        pl.lit(999.0).alias("close"), pl.lit(datetime(2025, 1, 1)).alias("ingested_at")
    )
    store.write_bars_raw(newer)
    got = store.read_bars_raw(["AAA"], date(2024, 1, 2), date(2024, 1, 2), "fixture")
    assert got.height == 1
    assert got["close"][0] == 999.0
    assert store.read_bars_raw(None, date(2024, 1, 1), date(2024, 12, 31), None).height == 90


def test_bars_roundtrip_replaces_symbol_partition(store):
    sample = pl.read_parquet(SAMPLE).drop(["source", "basis", "ingested_at"])
    bars = sample.with_columns(
        pl.col("close").alias("adj_close"), pl.lit(1, dtype=pl.Int32).alias("adj_version")
    )
    store.write_bars(bars)
    assert store.read_bars(None, date(2024, 1, 1), date(2024, 12, 31)).height == 90
    store.write_bars(bars.filter(pl.col("symbol") == "AAA").head(5))
    out = store.read_bars(None, date(2024, 1, 1), date(2024, 12, 31))
    assert out.filter(pl.col("symbol") == "AAA").height == 5
    assert out.filter(pl.col("symbol") == "BBB").height == 30


def test_read_is_parameterised(store):
    df = _symbols_df(["AAA", "BBB"]).with_columns(pl.Series("name", [QUOTED, "Other"]))
    store.upsert("symbols", df, ["symbol"])
    got = store.read("select * from symbols where symbol = ?", ["AAA"])
    assert got.height == 1
    assert got["name"][0] == QUOTED
    by_name = store.read("select symbol from symbols where name = ?", [QUOTED])
    assert by_name["symbol"].to_list() == ["AAA"]
    assert store.read("select count(*) as n from symbols")["n"][0] == 2
    with pytest.raises(ValueError):
        store.read_bars_raw(["AAA' OR '1'='1"], date(2024, 1, 1), date(2024, 12, 31), None)


def test_members_on(store):
    m = pl.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "start_date": [date(2020, 1, 1), date(2021, 6, 1), date(2022, 1, 1)],
            "end_date": [None, date(2022, 12, 31), date(2023, 6, 30)],
            "source": ["t", "t", "t"],
        },
        schema_overrides={"end_date": pl.Date},
    )
    store.upsert("membership", m, ["symbol", "start_date"])
    assert set(store.members_on(date(2020, 6, 1))) == {"AAA"}
    assert set(store.members_on(date(2022, 3, 1))) == {"AAA", "BBB", "CCC"}
    assert set(store.members_on(date(2023, 1, 1))) == {"AAA", "CCC"}
    assert set(store.members_on(date(2024, 1, 1))) == {"AAA"}


def test_members_on_boundaries(store):
    s, e = date(2021, 3, 10), date(2021, 9, 20)
    s2 = date(2022, 4, 5)
    m = pl.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "start_date": [s, s2],
            "end_date": [e, None],
            "source": ["t", "t"],
        },
        schema_overrides={"end_date": pl.Date},
    )
    store.upsert("membership", m, ["symbol", "start_date"])
    # closed interval [s, e] is inclusive at both ends
    assert "AAA" in store.members_on(s)
    assert "AAA" in store.members_on(e)
    assert "AAA" not in store.members_on(s - timedelta(days=1))
    assert "AAA" not in store.members_on(e + timedelta(days=1))
    # open-ended interval (NULL end_date)
    assert "BBB" in store.members_on(s2)
    assert "BBB" in store.members_on(date(2099, 12, 31))


def test_log_ingest(store):
    store.log_ingest(date(2024, 1, 2), "fixture", 90, "ok")
    out = store.read("SELECT source, rows, status, detail FROM ingest_log")
    assert out.rows() == [("fixture", 90, "ok", "")]


def test_read_splits_and_dividends(store):
    keys = ["symbol", "date", "source"]
    splits = pl.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB"],
            "date": [date(2024, 1, 5), date(2024, 3, 5), date(2024, 1, 5)],
            "ratio": [2.0, 3.0, 4.0],
            "source": ["polygon", "polygon", "yfinance"],
        }
    )
    divs = pl.DataFrame(
        {
            "symbol": ["AAA", "BBB", "BBB"],
            "date": [date(2024, 1, 5), date(2024, 1, 5), date(2024, 6, 5)],
            "cash_amount": [0.1, 0.2, 0.3],
            "source": ["polygon", "yfinance", "yfinance"],
            "vendor_id": ["rec-1", "sum", "sum"],
        }
    )
    store.upsert("splits", splits, keys)
    store.upsert("dividends", divs, [*keys, "vendor_id"])
    a, b = date(2024, 1, 1), date(2024, 2, 1)
    s_all = store.read_splits(None, a, date(2024, 12, 31))
    assert s_all.height == 3
    assert set(s_all.columns) == {"symbol", "date", "ratio", "source"}
    s_aaa = store.read_splits(["AAA"], a, b)
    assert s_aaa.height == 1
    assert s_aaa["ratio"].to_list() == [2.0]
    d_all = store.read_dividends(None, a, date(2024, 12, 31))
    assert d_all.height == 3
    assert set(d_all.columns) == {
        "symbol", "date", "cash_amount", "basis", "source", "vendor_id",
        "declaration_date", "frequency",
    }
    assert store.read_dividends(["BBB"], a, b).height == 1
    with pytest.raises(ValueError):
        store.read_splits(["AAA' OR '1'='1"], a, b)
    with pytest.raises(ValueError):
        store.read_dividends(["bad symbol"], a, b)


# ---------------------------------------------------------------------- relocation (WO-0012)
def _bars_raw_row(sym, close):
    return pl.DataFrame(
        {
            "symbol": [sym],
            "date": [date(2024, 1, 2)],
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [1.0],
            "source": ["fixture"],
            "basis": ["unadjusted"],
        }
    )


def _count_raw(s):
    return s.read("SELECT count(*) AS n FROM bars_raw")["n"][0]


@pytest.fixture
def relocated(tmp_path):
    """An initialised store with 1 bars_raw row, copied to a new directory with 0 rows."""
    old = Store(tmp_path / "old")
    old.init_schema()
    old.write_bars_raw(_bars_raw_row("OLD", 1.0))
    shutil.copytree(old.store_dir, tmp_path / "new")
    return old, Store(tmp_path / "new")


def test_relocated_store_read_only_raises(relocated):
    old, new = relocated
    with pytest.raises(StoreRelocatedError) as exc:
        new.read("SELECT count(*) FROM bars_raw")
    assert str(old.store_dir.resolve()) in str(exc.value)
    assert str(new.store_dir.resolve()) in str(exc.value)
    assert "init-store" in str(exc.value)
    # the original is not a relocation
    assert _count_raw(old) == 1


def test_relocated_store_read_write_repairs(relocated):
    old, new = relocated
    # a plain read-write connect (not init_schema) is what repairs the views
    new.connect().close()
    assert new.repaired_from == str(old.store_dir.resolve())
    assert new.recorded_store_dir() == str(new.store_dir.resolve())
    new.write_bars_raw(_bars_raw_row("NEW1", 2.0))
    new.write_bars_raw(_bars_raw_row("NEW2", 3.0))
    new.write_bars_raw(_bars_raw_row("NEW3", 4.0))
    # copy carried OLD (1 row) + 3 new rows = 4, read from the new directory's files
    assert _count_raw(new) == 4
    assert _count_raw(old) == 1  # old store untouched by new writes
    assert old.recorded_store_dir() == str(old.store_dir.resolve())


def test_relocated_store_does_not_read_old_path(relocated):
    old, new = relocated
    new.connect().close()  # read-write connect repairs the views
    # data present ONLY in the old directory, written after the copy
    old.write_bars_raw(_bars_raw_row("ONLYOLD", 9.0))
    assert _count_raw(old) == 2
    seen = new.read("SELECT symbol FROM bars_raw ORDER BY symbol")["symbol"].to_list()
    assert seen == ["OLD"]
    assert "ONLYOLD" not in seen


def test_fresh_and_legacy_store_are_not_relocations(tmp_path):
    s = Store(tmp_path / "s")
    s.init_schema()
    assert s.repaired_from is None
    # a pre-schema-4 store (no store_meta) is first use, not a relocation
    con = s.connect()
    con.execute("DROP TABLE store_meta")
    con.close()
    assert s.read("SELECT count(*) AS n FROM symbols")["n"][0] == 0
    s.init_schema()
    assert s.repaired_from is None
    assert s.recorded_store_dir() == str(s.store_dir.resolve())
