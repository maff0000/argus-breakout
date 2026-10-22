import hashlib
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
    revalidate_range,
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


def _payload(mutate=None):
    """Deep copy of the grouped-daily fixture with `mutate(row)` applied to each result row."""
    body = json.loads(json.dumps(GROUPED))
    if mutate:
        for r in body["results"]:
            mutate(r)
    return body


def _stored_count(store, d):
    return store.read(
        "SELECT count(*) AS n FROM bars_raw WHERE date = ? AND source = 'polygon'", [d]
    )["n"][0]


def _flags(store, d):
    return store.read(
        "SELECT symbol, flag, detail FROM bar_flags WHERE date = ? ORDER BY symbol, flag", [d]
    )


def _last_status(store, d):
    return store.read(
        "SELECT status FROM ingest_log WHERE date = ? ORDER BY finished_at DESC LIMIT 1", [d]
    )["status"][0]


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
    assert "jump_rule_applied=False" in res.detail  # first-ever date: recorded, not a pass


@respx.mock
def test_quarantined_day_is_still_stored(store, client):
    """CI-9: a quarantine verdict never prevents a fetched row being stored."""
    day1 = date(2026, 10, 15)
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    # day 2: ~80% coverage (quarantine) and three members move +50% (flags)
    payload = _truncated(400)
    for r in payload["results"]:
        if r["T"] in ("MAA", "MAB", "MAC"):
            r["c"] = r["c"] * 1.5
    _grouped_route(lambda req: httpx.Response(200, json=payload))
    res = ingest_polygon_day(store, client, D)
    fetched = {r["T"] for r in payload["results"]} & set(MEMBERS + ETFS)
    assert res.status == "quarantined" and "coverage" in res.detail
    assert res.rows == len(fetched) > 0
    assert _stored_count(store, D) == len(fetched)  # every fetched row is present
    row = _log(store, D).row(0, named=True)
    assert row["status"] == "quarantined" and row["rows"] == len(fetched)
    assert "jump_unexplained=3" in row["detail"]
    fl = _flags(store, D)
    assert fl["symbol"].to_list() == ["MAA", "MAB", "MAC"]
    assert set(fl["flag"]) == {"jump_unexplained"}


@respx.mock
def test_missing_group_member_quarantined_but_stored(store, client):
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["MAA"], "gics_industry_group": [None], "active": [True]}),
        ["symbol"],
    )
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "quarantined" and "industry group" in res.detail
    assert _stored_count(store, D) == res.rows == len(MEMBERS) + len(ETFS)


def _add_historical(store, n=10, group=None):
    """Delisted members: closed interval covering D, in `symbols` inactive, no bars today."""
    hist = [f"HX{i}" for i in range(n)]
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": hist, "gics_industry_group": [group] * n, "active": [False] * n}),
        ["symbol"],
    )
    store.upsert(
        "membership",
        pl.DataFrame(
            {
                "symbol": hist,
                "start_date": [date(2015, 1, 1)] * n,
                "end_date": [date(2026, 12, 31)] * n,
                "source": ["test"] * n,
            }
        ),
        ["symbol", "start_date"],
    )
    return hist


@respx.mock
def test_historical_unclassified_members_day_stored(store, client):
    _add_historical(store, 10)
    assert len(store.members_on(D)) == len(MEMBERS) + 10
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "ok" and res.rows == len(MEMBERS) + len(ETFS)
    assert "unclassified=10" in res.detail
    row = _log(store, D).row(0, named=True)
    assert row["status"] == "ok" and "unclassified=10" in row["detail"]
    assert store.read_bars_raw(None, D, D, "polygon").height == res.rows


@respx.mock
def test_current_member_without_group_quarantines_amid_historical(store, client):
    _add_historical(store, 10)
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["MAA"], "gics_industry_group": [None], "active": [True]}),
        ["symbol"],
    )
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "quarantined" and "current member" in res.detail
    assert store.read_bars_raw(None, D, D, "polygon").height == res.rows > 0


@respx.mock
def test_coverage_gate_still_quarantines_with_historical_members(store, client):
    _add_historical(store, 10)
    _grouped_route(lambda req: httpx.Response(200, json=_truncated(400)))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "quarantined" and "coverage" in res.detail


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
def test_judge_failure_records_quarantined(store, client, monkeypatch):
    """AMD-0019 2E: _judge raising AFTER the raw write is a quarantine (rows stored, unpublished),
    so 'failed' stays reserved for nothing-fetched and the backfill never re-fetches the day."""
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))

    def boom(*args, **kwargs):
        raise RuntimeError("judge exploded")

    monkeypatch.setattr("argus.data.ingest_polygon.validate_day", boom)
    res = ingest_polygon_day(store, client, D)
    assert res.status == "quarantined" and "judge exploded" in res.detail
    row = _log(store, D).row(0, named=True)
    assert row["status"] == "quarantined" and "judge exploded" in row["detail"]
    assert _stored_count(store, D) == len(MEMBERS) + len(ETFS) == res.rows  # rows ARE stored
    # the backfill resumes past it: no second fetch
    calls = []
    _grouped_route(lambda req: calls.append(1) or httpx.Response(200, json=GROUPED))
    assert backfill_polygon(store, client, D, D) == [] and calls == []


@respx.mock
def test_one_member_jump_is_a_flag_not_a_quarantine(store, client):
    day1 = date(2026, 10, 15)
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    jumped = _payload(lambda r: r.update(c=r["c"] * 1.5) if r["T"] == "MAA" else None)
    _grouped_route(lambda req: httpx.Response(200, json=jumped))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "ok" and "jump_unexplained=1" in res.detail
    fl = _flags(store, D)
    assert fl.row(0)[:2] == ("MAA", "jump_unexplained") and fl.height == 1


@respx.mock
def test_jump_with_consistent_split_is_reconciled(store, client):
    day1 = date(2026, 10, 15)
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    halved = _payload(lambda r: r.update(c=r["c"] * 0.5) if r["T"] == "MAA" else None)
    _grouped_route(lambda req: httpx.Response(200, json=halved))
    store.upsert(
        "splits",
        pl.DataFrame({"symbol": ["MAA"], "date": [D], "ratio": [2.0], "source": ["polygon"]}),
        ["symbol", "date", "source"],
    )
    res = ingest_polygon_day(store, client, D)
    assert res.status == "ok" and "jump_reconciled=1" in res.detail
    assert _flags(store, D).row(0)[:2] == ("MAA", "jump_split_reconciled")


@respx.mock
def test_breadth_of_jumps_quarantines_but_stores(store, client):
    day1 = date(2026, 10, 15)
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    hit = set(MEMBERS[:110])  # 110 of 501 members (> 20%)
    wild = _payload(lambda r: r.update(c=r["c"] * 1.6) if r["T"] in hit else None)
    _grouped_route(lambda req: httpx.Response(200, json=wild))
    res = ingest_polygon_day(store, client, D)
    assert res.status == "quarantined" and "jump_unexplained" in res.detail
    assert _stored_count(store, D) == res.rows
    assert _flags(store, D).height == 110


@respx.mock
def test_prior_close_comes_from_a_quarantined_day(store, client):
    """D2 (AMD-0018): day 1 is quarantined; day 2 must still compare against day 1's close."""
    day1 = date(2026, 10, 15)

    def day1_mutation(r):
        if r["T"] in MEMBERS[:20]:
            r["v"] = 0  # 20 of 501 members at zero volume (> 2%): quarantine
        if r["T"] == "MAA":
            r["c"] = r["c"] * 1.5

    _grouped_route(lambda req: httpx.Response(200, json=_payload(day1_mutation)))
    assert ingest_polygon_day(store, client, day1).status == "quarantined"
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    res = ingest_polygon_day(store, client, D)
    # No cascade: day 1's verdict does not reach day 2 ...
    assert res.status == "ok", res.detail
    # ... and the comparison was against day 1's (quarantined) close, not an older one.
    fl = _flags(store, D)
    assert fl.row(0)[:2] == ("MAA", "jump_unexplained") and fl.height == 1
    assert "-0.33" in fl["detail"][0]


def _days_called(route):
    return {c.request.url.path.rsplit("/", 1)[1] for c in route.calls}


@respx.mock
def test_backfill_resumable(store, client, monkeypatch):
    monkeypatch.setattr("argus.data.providers.polygon.time.sleep", lambda s: None)
    start, end = date(2026, 10, 12), date(2026, 10, 18)  # Mon..Sun
    state = {"failing": "2026-10-16"}

    def handler(req):
        d = req.url.path.rsplit("/", 1)[1]
        if d == "2026-10-12":
            return httpx.Response(200, json={"status": "OK", "resultsCount": 0})
        if d == state["failing"]:
            return httpx.Response(500)
        if d == "2026-10-14":
            return httpx.Response(200, json=_truncated(100))  # quarantined (coverage)
        return httpx.Response(200, json=GROUPED)

    route = _grouped_route(handler)
    first = backfill_polygon(store, client, start, end)
    assert _days_called(route) == {f"2026-10-{n}" for n in (12, 13, 14, 15, 16)}  # weekdays only
    assert sorted(r.status for r in first) == ["failed", "holiday", "ok", "ok", "quarantined"]
    log = store.read("SELECT date, status FROM ingest_log ORDER BY date")
    assert log.height == 5 and all(d.weekday() < 5 for d in log["date"])
    assert _stored_count(store, date(2026, 10, 14)) > 0  # the quarantined day is stored

    route.reset()
    second = backfill_polygon(store, client, start, end)
    # ok/holiday/quarantined are skipped; only 'failed' is retried (the client retries 5xx itself)
    assert _days_called(route) == {"2026-10-16"}
    assert [r.status for r in second] == ["failed"]

    state["failing"] = "none"
    route.reset()
    third = backfill_polygon(store, client, start, end)
    assert [r.status for r in third] == ["ok"] and _days_called(route) == {"2026-10-16"}
    assert route.call_count == 1

    route.reset()
    assert backfill_polygon(store, client, start, end) == []
    assert route.call_count == 0


def _bars_raw_digest(store):
    h = hashlib.sha256()
    for f in sorted((store.parquet_dir / "bars_raw").rglob("*.parquet")):
        h.update(f.relative_to(store.parquet_dir).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


@respx.mock
def test_revalidate_makes_no_provider_call(store, client):
    day1 = date(2026, 10, 15)
    route = _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, day1).status == "ok"
    jumped = _payload(lambda r: r.update(c=r["c"] * 1.5) if r["T"] == "MAA" else None)
    _grouped_route(lambda req: httpx.Response(200, json=jumped))
    assert ingest_polygon_day(store, client, D).status == "ok"
    assert _flags(store, D).row(0)[:2] == ("MAA", "jump_unexplained")

    # Knowledge changes after the fetch: a split on D consistent with the move, and a current
    # member loses its classification (a day-level fault).
    store.upsert(
        "splits",
        pl.DataFrame({"symbol": ["MAA"], "date": [D], "ratio": [2 / 3], "source": ["polygon"]}),
        ["symbol", "date", "source"],
    )
    store.upsert(
        "symbols",
        pl.DataFrame({"symbol": ["MAB"], "gics_industry_group": [None], "active": [True]}),
        ["symbol"],
    )
    digest, rows = _bars_raw_digest(store), store.read("SELECT * FROM bars_raw ORDER BY ALL")
    route.reset()
    results = revalidate_range(store, day1, D)

    assert route.call_count == 0  # no HTTP at all
    assert [r.status for r in results] == ["quarantined", "quarantined"]
    assert _last_status(store, D) == "quarantined" and _last_status(store, day1) == "quarantined"
    fl = _flags(store, D)  # the old unexplained row is replaced, not accumulated
    assert fl.height == 1 and fl.row(0)[:2] == ("MAA", "jump_split_reconciled")
    assert _bars_raw_digest(store) == digest  # bars_raw byte-identical
    assert store.read("SELECT * FROM bars_raw ORDER BY ALL").equals(rows)


@respx.mock
def test_revalidate_failure_writes_a_log_row(store, client, monkeypatch):
    """AMD-0021 2C: a judging failure is recorded, not merely returned."""
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, D).status == "ok"

    def boom(*_a, **_k):
        raise RuntimeError("judge exploded")

    monkeypatch.setattr("argus.data.ingest_polygon._judge", boom)
    digest = _bars_raw_digest(store)
    results = revalidate_range(store, D, D)
    assert [r.status for r in results] == ["quarantined"]
    assert _last_status(store, D) == "quarantined"  # the stale 'ok' no longer stands
    detail = store.read(
        "SELECT detail FROM ingest_log WHERE date = ? ORDER BY finished_at DESC LIMIT 1", [D]
    )["detail"][0]
    assert "RuntimeError" in detail and "judge exploded" in detail
    assert _bars_raw_digest(store) == digest


@respx.mock
def test_cli_revalidate_needs_no_key_and_no_network(clean_env, store, client):
    _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    assert ingest_polygon_day(store, client, D).status == "ok"
    clean_env.setenv("ARGUS_STORE_DIR", str(store.store_dir))  # no POLYGON_API_KEY
    route = _grouped_route(lambda req: httpx.Response(200, json=GROUPED))
    route.reset()
    res = CliRunner().invoke(
        app, ["ingest", "revalidate", "--start", "2026-10-01", "--end", "2026-10-31"]
    )
    assert res.exit_code == 0, res.output
    assert "days=1" in res.output and "ok=1" in res.output
    assert route.call_count == 0
    bad = CliRunner().invoke(
        app, ["ingest", "revalidate", "--start", "2026-10-31", "--end", "2026-10-01"]
    )
    assert bad.exit_code == 2


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
    # splits MAA/MAB/MAC (3) + dividends MAA(same day as split)/MAD/BRK.B (3); NAA not in symbols
    assert n == 6
    spl = store.read("SELECT * FROM splits ORDER BY symbol, date")
    dv = store.read("SELECT * FROM dividends ORDER BY symbol, date")
    assert spl.height == 3 and dv.height == 3
    assert spl.filter(pl.col("symbol") == "MAB")["ratio"][0] == 0.1
    assert set(spl["source"]) == {"polygon"} and set(dv["source"]) == {"polygon"}
    assert "MAD" not in spl["symbol"].to_list()
    # Mutation: writing both measures to one table / keying on (symbol,date) loses MAA's
    # split or dividend -> one of these two assertions fails.
    maa_s = spl.filter(pl.col("symbol") == "MAA").row(0, named=True)
    maa_d = dv.filter(pl.col("symbol") == "MAA").row(0, named=True)
    assert maa_s["ratio"] == 4.0 and maa_d["cash_amount"] == 0.25
    assert maa_s["date"] == maa_d["date"]
    # idempotent. Mutation: plain INSERT (no upsert) would double the counts.
    assert ingest_polygon_actions(store, client, date(2026, 1, 1)) == 6
    assert store.read("SELECT count(*) AS n FROM splits")["n"][0] == 3
    assert store.read("SELECT count(*) AS n FROM dividends")["n"][0] == 3


@respx.mock
def test_actions_two_sources_both_persist(store, client):
    """Mutation that fails this: keying upsert on ["symbol","date"] (drops source) -> the
    pre-existing yfinance rows are overwritten by polygon and the count falls to 1 each."""
    d = date(2026, 3, 2)
    store.upsert(
        "splits",
        pl.DataFrame({"symbol": ["MAA"], "date": [d], "ratio": [4.0], "source": ["yfinance"]}),
        ["symbol", "date", "source"],
    )
    store.upsert(
        "dividends",
        pl.DataFrame(
            {"symbol": ["MAA"], "date": [d], "cash_amount": [0.25], "source": ["yfinance"],
             "vendor_id": ["sum"]}
        ),
        ["symbol", "date", "source", "vendor_id"],
    )
    respx.get(f"{BASE}/v3/reference/splits").respond(json={"status": "OK", "results": [
        {"ticker": "MAA", "execution_date": d.isoformat(), "split_from": 1, "split_to": 4}]})
    respx.get(f"{BASE}/v3/reference/dividends").respond(json={"status": "OK", "results": [
        {"ticker": "MAA", "ex_dividend_date": d.isoformat(), "cash_amount": 0.25,
         "id": "rec-maa"}]})
    assert ingest_polygon_actions(store, client, date(2026, 1, 1)) == 2
    sq = "SELECT source FROM splits WHERE symbol = 'MAA' ORDER BY source"
    dq = "SELECT source FROM dividends WHERE symbol = 'MAA' ORDER BY source"
    for q in (sq, dq):
        assert store.read(q)["source"].to_list() == ["polygon", "yfinance"]


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
