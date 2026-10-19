import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
import structlog
from pydantic import SecretStr
from typer.testing import CliRunner

from argus.cli import app
from argus.data.ingest_polygon import (
    backfill_polygon,
    ingest_polygon_actions,
    ingest_polygon_day,
)
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store

FIX = Path(__file__).parent / "fixtures" / "polygon"
BASE = "https://api.polygon.io"
GROUPED = json.loads((FIX / "grouped_daily_2026-10-16.json").read_text())
MEMBERS = [f"M{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(500)] + ["BRK.B"]
ETFS = ["SPY", "RSP", "XLK"]
D = date(2026, 10, 16)


@pytest.fixture(autouse=True)
def _fresh_logging():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "store")
    s.init_schema()
    s.upsert(
        "symbols",
        pl.DataFrame(
            {
                "symbol": MEMBERS + ETFS,
                "gics_industry_group": ["Software"] * len(MEMBERS) + [None] * len(ETFS),
                "active": [True] * (len(MEMBERS) + len(ETFS)),
            }
        ),
        ["symbol"],
    )
    s.upsert(
        "membership",
        pl.DataFrame(
            {
                "symbol": MEMBERS,
                "start_date": [date(2020, 1, 1)] * len(MEMBERS),
                "end_date": [None] * len(MEMBERS),
                "source": ["test"] * len(MEMBERS),
            },
            schema_overrides={"end_date": pl.Date},
        ),
        ["symbol", "start_date"],
    )
    return s


@pytest.fixture
def client():
    c = PolygonClient(SecretStr("unit-test-dummy"), calls_per_minute=6000)
    yield c
    c.close()


def _truncated(keep_members: int) -> dict:
    """Grouped-daily payload retaining only the first `keep_members` members (others removed)."""
    drop = set(MEMBERS[keep_members:])
    body = dict(GROUPED)
    body["results"] = [r for r in GROUPED["results"] if r["T"] not in drop]
    return body


def _grouped_route(handler):
    return respx.get(url__regex=r".*/v2/aggs/grouped/locale/us/market/stocks/.*").mock(
        side_effect=handler
    )


def _log(store, d):
    return store.read("SELECT status, rows, detail FROM ingest_log WHERE date = ?", [d])


@respx.mock
def test_ok_day_written(store, client):
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "ok" and res.rows == len(MEMBERS) + len(ETFS)
    df = store.read_bars_raw(None, D, D, "polygon")
    assert df.height == res.rows
    assert set(df["basis"]) == {"split"} and set(df["source"]) == {"polygon"}
    assert "NAA" not in df["symbol"].to_list()  # not in `symbols`
    assert _log(store, D).row(0)[0] == "ok"


@respx.mock
def test_rejected_day_not_written(store, client):
    # pre-existing data for another day must stay untouched
    store.write_bars_raw(
        pl.DataFrame(
            {
                "symbol": ["SPY"], "date": [date(2026, 10, 15)], "open": [1.0], "high": [1.0],
                "low": [1.0], "close": [1.0], "volume": [1.0], "source": ["polygon"],
                "basis": ["split"],
            }
        )
    )
    before = store.read("SELECT count(*) AS n FROM bars_raw")["n"][0]
    _grouped_route(lambda req: httpx.Response(200, json=_truncated(400)))  # ~80% coverage
    res = ingest_polygon_day(store, client, D)
    assert res.status == "rejected" and res.rows == 0 and "coverage" in res.detail
    assert store.read("SELECT count(*) AS n FROM bars_raw")["n"][0] == before
    assert store.read_bars_raw(None, D, D, None).is_empty()
    row = _log(store, D).row(0, named=True)
    assert row["status"] == "rejected" and row["rows"] == 0


@respx.mock
def test_missing_group_member_rejected_not_written(store, client):
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["MAA"], "gics_industry_group": [None], "active": [True]}),
        ["symbol"],
    )
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "rejected" and "industry group" in res.detail
    assert store.read_bars_raw(None, D, D, None).is_empty()


@respx.mock
def test_holiday_logged(store, client):
    _grouped_route(lambda req: httpx.Response(200, json={"status": "OK", "resultsCount": 0}))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "holiday" and res.rows == 0
    assert _log(store, D).row(0)[0] == "holiday"


@respx.mock
def test_provider_failure_logged_failed(store, client, monkeypatch):
    monkeypatch.setattr("argus.data.providers.polygon.time.sleep", lambda s: None)
    _grouped_route(lambda req: httpx.Response(500))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "failed"
    assert _log(store, D).row(0)[0] == "failed"


@respx.mock
def test_jump_without_split_rejected_with_split_ok(store, client):
    day1, day2 = date(2026, 10, 15), D
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    jumped = json.loads(json.dumps(GROUPED))
    for r in jumped["results"]:
        if r["T"] == "MAA":
            r["c"] = r["c"] * 1.5
    _grouped_route(lambda req: httpx.Response(200, json=jumped))
    assert ingest_polygon_day(store, client, day2).status == "rejected"
    store.upsert(
        "adjustments",
        pl.DataFrame(
            {"symbol": ["MAA"], "date": [day2], "split_ratio": [2.0], "cash_dividend": [None],
             "source": ["polygon"]},
            schema_overrides={"cash_dividend": pl.Float64},
        ),
        ["symbol", "date"],
    )
    assert ingest_polygon_day(store, client, day2).status == "ok"


@respx.mock
def test_backfill_resumable(store, client):
    start, end = date(2026, 10, 12), date(2026, 10, 18)  # Mon..Sun
    state = {"rejected_day": "2026-10-14"}

    def handler(req):
        d = req.url.path.rsplit("/", 1)[1]
        if d == "2026-10-12":
            return httpx.Response(200, json={"status": "OK", "resultsCount": 0})
        if d == state["rejected_day"]:
            return httpx.Response(200, json=_truncated(100))
        return httpx.Response(200, json=GROUPED)

    route = _grouped_route(handler)
    first = backfill_polygon(store, client, start, end)
    assert route.call_count == 5  # weekdays only
    assert sorted(r.status for r in first) == ["holiday", "ok", "ok", "ok", "rejected"]
    log = store.read("SELECT date, status FROM ingest_log ORDER BY date")
    assert log.height == 5 and all(d.weekday() < 5 for d in log["date"])

    route.reset()
    second = backfill_polygon(store, client, start, end)
    assert route.call_count == 1  # only the rejected day is retried
    assert route.calls[0].request.url.path.endswith("2026-10-14")
    assert [r.status for r in second] == ["rejected"]

    state["rejected_day"] = "none"
    route.reset()
    third = backfill_polygon(store, client, start, end)
    assert [r.status for r in third] == ["ok"] and route.call_count == 1

    route.reset()
    assert backfill_polygon(store, client, start, end) == []
    assert route.call_count == 0


@respx.mock
def test_actions_upsert(store, client):
    def splits(req):
        name = "splits_page2.json" if "cursor" in req.url.params else "splits_page1.json"
        return httpx.Response(200, json=json.loads((FIX / name).read_text()))

    respx.get(f"{BASE}/v3/reference/splits").mock(side_effect=splits)
    respx.get(f"{BASE}/v3/reference/dividends").respond(
        json=json.loads((FIX / "dividends.json").read_text())
    )
    n = ingest_polygon_actions(store, client, date(2026, 1, 1))
    # splits MAA/MAB/MAC + dividends MAA(same day as split)/MAD/BRK.B; NAA not in symbols
    assert n == 5
    adj = store.read("SELECT * FROM adjustments ORDER BY symbol, date")
    maa = adj.filter(pl.col("symbol") == "MAA").row(0, named=True)
    assert maa["split_ratio"] == 4.0 and maa["cash_dividend"] == 0.25 and maa["source"] == "polygon"
    assert adj.filter(pl.col("symbol") == "MAB")["split_ratio"][0] == 0.1
    assert adj.filter(pl.col("symbol") == "MAD")["split_ratio"][0] is None
    # idempotent
    assert ingest_polygon_actions(store, client, date(2026, 1, 1)) == 5
    assert store.read("SELECT count(*) AS n FROM adjustments")["n"][0] == 5


def test_cli_requires_key(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    runner = CliRunner()
    res = runner.invoke(app, ["ingest", "polygon", "--date", "2026-10-16"])
    assert res.exit_code == 2
    assert "polygon_api_key" in res.output
    res = runner.invoke(app, ["ingest", "polygon-actions", "--since", "2024-01-01"])
    assert res.exit_code == 2


def test_cli_argument_validation(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("POLYGON_API_KEY", "unit-test-dummy")
    runner = CliRunner()
    assert runner.invoke(app, ["ingest", "polygon"]).exit_code == 2
    both = ["ingest", "polygon", "--date", "2026-10-16", "--backfill", "2026-10-01", "2026-10-02"]
    assert runner.invoke(app, both).exit_code == 2
    assert runner.invoke(app, ["ingest", "polygon", "--date", "nonsense"]).exit_code == 2
    assert runner.invoke(
        app, ["ingest", "polygon", "--backfill", "2026-10-05", "2026-10-01"]
    ).exit_code == 2


@respx.mock
def test_cli_date_end_to_end(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("POLYGON_API_KEY", "unit-test-dummy")
    Store(tmp_path / "store").init_schema()
    respx.get(url__regex=r".*/grouped/.*").respond(json={"status": "OK", "resultsCount": 0})
    res = CliRunner().invoke(app, ["ingest", "polygon", "--date", "2026-10-16"])
    assert res.exit_code == 0, res.output
    assert "holiday=1" in res.output
