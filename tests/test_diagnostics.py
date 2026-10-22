"""WO-0015: read-only diagnostics for same-date dividends and undeclared renames."""

import hashlib
import json
from datetime import date, datetime, timedelta

import polars as pl
import pytest
import respx
import structlog
from pydantic import SecretStr
from typer.testing import CliRunner

from argus.cli import app
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store, StoreRelocatedError
from argus.diagnostics.dividends import dividend_disagreements, same_date_dividend_report
from argus.diagnostics.renames import severed_current_members, undeclared_rename_candidates

BASE = "https://api.polygon.io"
EX = date(2026, 1, 2)
TABLES = [
    "symbols", "membership", "splits", "dividends", "iv_daily", "events", "bar_flags",
    "ingest_log", "store_meta", "schema_version", "bars_raw", "bars", "etf_bars",
]


@pytest.fixture(autouse=True)
def _fresh_logging():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def make_store(tmp_path, renames_yaml: str | None = None) -> Store:
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    if renames_yaml is not None:
        (config / "ticker_renames.yaml").write_text(renames_yaml)
    store = Store(tmp_path / "store", config_dir=config)
    store.init_schema()
    return store


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def raw_bars(sym: str, days: list[date], close: float, source: str = "polygon") -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": sym, "date": days, "open": close, "high": close, "low": close,
            "close": close, "volume": 1000.0, "source": source, "basis": "split",
            "ingested_at": datetime(2026, 6, 1, 6, 0),
        },
        schema_overrides={"date": pl.Date, "ingested_at": pl.Datetime("us")},
    )


def pub_bars(sym: str, days: list[date], close: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": sym, "date": days, "open": close, "high": close, "low": close,
            "close": close, "volume": 1000.0, "adj_close": close, "adj_version": 1,
        },
        schema_overrides={"date": pl.Date, "adj_version": pl.Int32},
    )


def put_dividends(store: Store, rows: list[tuple[str, date, float, str]]) -> None:
    df = pl.DataFrame(
        rows, schema={"symbol": pl.String, "date": pl.Date, "cash_amount": pl.Float64,
                      "source": pl.String}, orient="row",
    ).with_columns(  # one record per (symbol, date, source) here: vendor_id is only a key part
        pl.when(pl.col("source") == "yfinance").then(pl.lit("sum")).otherwise(pl.lit("rec-1"))
        .alias("vendor_id")
    )
    store.upsert("dividends", df, ["symbol", "date", "source", "vendor_id"])


def put_membership(store: Store, rows: list[tuple[str, date, date | None]]) -> None:
    df = pl.DataFrame(
        [(s, a, b, "test") for s, a, b in rows],
        schema={"symbol": pl.String, "start_date": pl.Date, "end_date": pl.Date,
                "source": pl.String}, orient="row",
    )
    store.upsert("membership", df, ["symbol", "start_date"])


def counts(store: Store) -> dict[str, int]:
    return {t: store.read(f"SELECT COUNT(*) AS n FROM {t}")["n"][0] for t in TABLES}  # noqa: S608


def bars_raw_checksum(store: Store) -> str:
    df = store.read("SELECT * FROM bars_raw ORDER BY symbol, date, source")
    return hashlib.sha256(df.write_csv().encode()).hexdigest()


def seed_dividend_store(tmp_path) -> Store:
    store = make_store(tmp_path)
    days = weekdays(EX - timedelta(days=20), 14)
    store.write_bars(pub_bars("PGR", [d for d in days if d < EX], 280.0))
    put_dividends(
        store,
        [
            ("PGR", EX, 0.10, "polygon"), ("PGR", EX, 13.60, "yfinance"),
            ("KO", EX, 0.50, "polygon"), ("KO", EX, 0.51, "yfinance"),  # agree: not listed
            ("FCX", date(2025, 12, 15), 0.075, "polygon"),  # single source: not a pair
        ],
    )
    return store


def test_same_date_report_lists_suspect_dates(tmp_path):
    store = seed_dividend_store(tmp_path)
    rep = same_date_dividend_report(store, None)
    assert rep.columns == ["symbol", "date", "source", "n_rows_stored", "stored_amount", "note"]
    assert set(rep["symbol"]) == {"PGR"}  # KO agrees, FCX has one source
    by_src = {r["source"]: r for r in rep.iter_rows(named=True)}
    assert by_src["polygon"]["stored_amount"] == pytest.approx(0.10)
    assert by_src["yfinance"]["stored_amount"] == pytest.approx(13.60)
    assert by_src["polygon"]["date"] == EX
    assert "adj_close_err_pct=4.82" in by_src["polygon"]["note"]  # (13.6-0.1)/280
    pairs = dividend_disagreements(store)
    assert pairs.filter(pl.col("suspect")).height == 1


def test_split_basis_is_normalised_before_comparing(tmp_path):
    store = make_store(tmp_path)
    store.write_bars(pub_bars("AAA", weekdays(EX - timedelta(days=10), 5), 50.0))
    # as-paid 1.00 before a 4:1 split dated after the ex-date == 0.25 split-adjusted
    store.upsert(
        "splits",
        pl.DataFrame({"symbol": ["AAA"], "date": [EX + timedelta(days=30)], "ratio": [4.0],
                      "source": ["polygon"]}),
        ["symbol", "date", "source"],
    )
    put_dividends(store, [("AAA", EX, 1.00, "polygon"), ("AAA", EX, 0.25, "yfinance")])
    assert same_date_dividend_report(store, None).is_empty()


def two_record_payload() -> dict:
    return {
        "status": "OK", "request_id": "r1", "count": 2,
        "results": [
            {"ticker": "PGR", "ex_dividend_date": "2026-01-02", "cash_amount": 0.10,
             "dividend_type": "CD", "frequency": 4, "id": "a"},
            {"ticker": "PGR", "ex_dividend_date": "2026-01-02", "cash_amount": 13.50,
             "dividend_type": "SC", "frequency": 0, "id": "b"},
        ],
    }


@respx.mock
def test_raw_payload_record_count_is_reported(tmp_path):
    store = make_store(tmp_path)
    put_dividends(store, [("PGR", EX, 6.80, "polygon"), ("PGR", EX, 13.60, "yfinance")])
    route = respx.get(f"{BASE}/v3/reference/dividends").respond(json=two_record_payload())
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        rep = same_date_dividend_report(store, client, "PGR", EX)
    finally:
        client.close()
    assert route.call_count == 1
    params = dict(route.calls[0].request.url.params)
    assert params["ticker"] == "PGR" and params["ex_dividend_date"] == "2026-01-02"
    summary = rep.filter(pl.col("source") == "polygon_raw_summary")["note"][0]
    assert "n_records_returned=2" in summary
    assert "cash_amounts=[0.1, 13.5]" in summary
    assert 'dividend_type=["CD", "SC"]' in summary
    assert "stored_equals=neither" in summary  # 6.80 is neither a record nor 0.10+13.50
    records = rep.filter(pl.col("source") == "polygon_raw")
    assert records.height == 2
    first = json.loads(records["note"][0].split("verbatim: ", 1)[1])
    assert first == two_record_payload()["results"][0]


@respx.mock
def test_raw_classifies_equals_one_record(tmp_path):
    store = make_store(tmp_path)
    put_dividends(store, [("PGR", EX, 0.10, "polygon")])
    respx.get(f"{BASE}/v3/reference/dividends").respond(json=two_record_payload())
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        rep = same_date_dividend_report(store, client, "PGR", EX)
    finally:
        client.close()
    assert "stored_equals=equals_one_record" in rep["note"][-1]


@respx.mock
def test_raw_classifies_sum_and_single_record(tmp_path):
    store = make_store(tmp_path)
    put_dividends(store, [("PGR", EX, 13.60, "polygon")])
    respx.get(f"{BASE}/v3/reference/dividends").respond(
        json={"status": "OK", "results": [{"cash_amount": 0.10}, {"cash_amount": 13.50}]}
    )
    client = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    try:
        rep = same_date_dividend_report(store, client, "PGR", EX)
    finally:
        client.close()
    assert "stored_equals=equals_sum_of_records" in rep["note"][-1]


def test_diagnostics_never_write(tmp_path):
    store = seed_dividend_store(tmp_path)
    put_membership(store, [("OLD", date(2010, 1, 4), date(2022, 6, 3)),
                           ("NEW", date(2022, 6, 6), None)])
    store.write_bars_raw(raw_bars("NEW", weekdays(date(2012, 1, 2), 30), 100.0))
    before, checksum = counts(store), bars_raw_checksum(store)
    same_date_dividend_report(store, None)
    same_date_dividend_report(store, None, "PGR", EX)
    undeclared_rename_candidates(store)
    severed_current_members(store)
    runner = CliRunner()
    env = {"ARGUS_STORE_DIR": str(store.store_dir), "ARGUS_CONFIG_DIR": str(tmp_path / "config")}
    for args in (["diagnose", "dividends"], ["diagnose", "renames"]):
        res = runner.invoke(app, args, env=env)
        assert res.exit_code == 0, res.output
    assert counts(store) == before
    assert bars_raw_checksum(store) == checksum


def test_cli_raw_needs_key_and_symbol(tmp_path, clean_env):
    store = make_store(tmp_path)
    runner = CliRunner()
    env = {"ARGUS_STORE_DIR": str(store.store_dir)}
    assert runner.invoke(app, ["diagnose", "dividends", "--raw"], env=env).exit_code == 2
    res = runner.invoke(
        app, ["diagnose", "dividends", "--symbol", "PGR", "--date", "2026-01-02", "--raw"],
        env=env,
    )
    assert res.exit_code == 2 and "polygon_api_key" in res.output


def test_relocated_store_raises(tmp_path):
    store = make_store(tmp_path)
    moved = tmp_path / "moved"
    (tmp_path / "store").rename(moved)
    relocated = Store(moved, config_dir=tmp_path / "config")
    with pytest.raises(StoreRelocatedError):
        same_date_dividend_report(relocated, None)
    with pytest.raises(StoreRelocatedError):
        undeclared_rename_candidates(relocated)
    assert store is not None


def seed_rename_store(tmp_path, renames_yaml: str | None = None) -> Store:
    store = make_store(tmp_path, renames_yaml)
    cal = weekdays(date(2012, 1, 2), 3000)
    # OLD ended Thu 2022-06-02; NEW's membership opens Mon 2022-06-06, but NEW has
    # bars back to 2012 (the source serves the whole history under the new ticker).
    old_end, new_start = date(2022, 6, 2), date(2022, 6, 6)
    put_membership(
        store,
        [
            ("OLD", date(2012, 1, 2), old_end),
            ("NEW", new_start, None),
            ("IPO", date(2022, 6, 1), None),
        ],
    )
    store.write_bars_raw(raw_bars("NEW", [d for d in cal if d <= date(2022, 12, 30)], 100.0))
    store.write_bars_raw(raw_bars("OLD", [d for d in cal if d <= old_end], 104.0))
    ipo_days = [d for d in cal if date(2022, 6, 1) <= d <= date(2022, 12, 30)]
    store.write_bars_raw(raw_bars("IPO", ipo_days, 20.0))
    return store


def test_rename_candidate_detected_from_bars_before_membership(tmp_path):
    store = seed_rename_store(tmp_path)
    cands = undeclared_rename_candidates(store)
    assert cands.columns == [
        "old_symbol", "old_end_date", "new_symbol", "new_start_date", "gap_trading_days",
        "new_symbol_first_bar", "bars_before_new_start", "price_ratio_at_boundary", "confidence",
    ]
    row = cands.filter(pl.col("new_symbol") == "NEW").row(0, named=True)
    assert row["old_symbol"] == "OLD" and row["confidence"] == "high"
    assert row["new_symbol_first_bar"] == date(2012, 1, 2)
    assert row["bars_before_new_start"] > 2000
    assert row["gap_trading_days"] == 2  # 2022-06-03 and 2022-06-06
    assert row["price_ratio_at_boundary"] == pytest.approx(100.0 / 104.0)
    assert "NEW" in severed_current_members(store)["symbol"].to_list()


def test_genuine_new_listing_is_not_a_candidate(tmp_path):
    store = seed_rename_store(tmp_path)
    # IPO: first bar == membership start, so signal (1) is absent for it.
    cands = undeclared_rename_candidates(store)
    assert "IPO" not in cands["new_symbol"].to_list()
    assert "IPO" not in severed_current_members(store)["symbol"].to_list()


def test_renames_does_not_edit_config_or_membership(tmp_path):
    yaml_text = "renames:\n  - {old: AAA, new: BBB, effective: null}\n"
    store = seed_rename_store(tmp_path, yaml_text)
    cfg = tmp_path / "config" / "ticker_renames.yaml"
    before_cfg, before_n = cfg.read_bytes(), counts(store)["membership"]
    before_rows = store.read("SELECT * FROM membership ORDER BY symbol, start_date")
    undeclared_rename_candidates(store)
    res = CliRunner().invoke(
        app, ["diagnose", "renames", "--gap-days", "5"],
        env={"ARGUS_STORE_DIR": str(store.store_dir), "ARGUS_CONFIG_DIR": str(tmp_path / "config")},
    )
    assert res.exit_code == 0 and "NEW" in res.output
    assert cfg.read_bytes() == before_cfg
    assert counts(store)["membership"] == before_n
    assert store.read("SELECT * FROM membership ORDER BY symbol, start_date").equals(before_rows)


def test_declared_pair_is_not_reported_again(tmp_path):
    store = seed_rename_store(tmp_path, "renames:\n  - {old: OLD, new: NEW, effective: null}\n")
    assert "NEW" not in undeclared_rename_candidates(store)["new_symbol"].to_list()


def test_corroboration_outside_gap_is_not_a_candidate(tmp_path):
    store = seed_rename_store(tmp_path)
    assert "NEW" not in undeclared_rename_candidates(store, gap_days=0)["new_symbol"].to_list()


def test_missing_old_bars_gives_medium_confidence(tmp_path):
    store = make_store(tmp_path)
    put_membership(store, [("OLD", date(2012, 1, 2), date(2022, 6, 2)),
                           ("NEW", date(2022, 6, 6), None)])
    store.write_bars_raw(raw_bars("NEW", weekdays(date(2012, 1, 2), 3000), 100.0))
    row = undeclared_rename_candidates(store).row(0, named=True)
    assert row["confidence"] == "medium" and row["price_ratio_at_boundary"] is None
