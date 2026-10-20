import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
from pydantic import SecretStr
from typer.testing import CliRunner

from argus.cli import app
from argus.data.providers.fmp import BASE_URL, FMPClient
from argus.data.store import Store
from argus.events.earnings import days_to_earnings, next_earnings, refresh_events

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"
KEY = "k3y-VALUE-0123456789"
TODAY = date(2026, 10, 20)
EARN_URL = BASE_URL + "earnings-calendar"
DIV_URL = BASE_URL + "dividends-calendar"
runner = CliRunner()


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


ACTIVE = ["GE", "GM", "WMT", "NVDA", "TGT", "GS", "KO", "LMT", "JNJ"]  # DOCU, BABA are absent


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "store")
    s.init_schema()
    s.upsert(
        "symbols", pl.DataFrame({"symbol": ACTIVE, "active": [True] * len(ACTIVE)}), ["symbol"]
    )
    return s


def _client(store):
    return FMPClient(SecretStr(KEY), 200, store, retry_wait=0)


def _mock_ok():
    e = respx.get(EARN_URL).mock(
        return_value=httpx.Response(200, json=_fixture("earnings_calendar.json"))
    )
    d = respx.get(DIV_URL).mock(
        return_value=httpx.Response(200, json=_fixture("dividends_calendar.json"))
    )
    return e, d


def _events(store):
    return store.read("SELECT * FROM events ORDER BY type, symbol, date")


def _bars(store, dates):
    rows = [
        {
            "symbol": "AAPL",
            "date": d,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
            "source": "t",
            "basis": "unadjusted",
        }
        for d in dates
    ]
    store.write_bars_raw(pl.DataFrame(rows))


def _mock_inline(earn, div):
    respx.get(EARN_URL).mock(return_value=httpx.Response(200, json=earn))
    respx.get(DIV_URL).mock(return_value=httpx.Response(200, json=div))


@respx.mock
def test_refresh_upserts_members_only(store):
    _mock_ok()  # recorded real responses: 5 member + 2 non-member (DOCU, BABA) earnings rows
    report = refresh_events(store, _client(store), TODAY)
    ev = _events(store)
    earn = ev.filter(pl.col("type") == "earnings")
    assert sorted(earn["symbol"].to_list()) == ["GE", "GM", "NVDA", "TGT", "WMT"]
    assert report.n_earnings == 5
    assert sorted(ev.filter(pl.col("type") == "exdiv")["symbol"].to_list()) == [
        "GS", "JNJ", "KO", "LMT",
    ]  # fmt: skip
    assert report.n_exdiv == 4
    assert set(ev["source"].to_list()) == {"fmp"}
    # coverage travels with the aggregate (CI-8): GE and GM report today, the rest are later
    assert report.n_symbols_with_upcoming_earnings == 5
    assert report.n_active_symbols == 9
    assert report.unavailable == ()


@respx.mock
def test_dividends_non_members_dropped_synthetic(store):
    # synthetic: the recorded dividends sample contains no non-member row
    div = _fixture("dividends_calendar.json") + [
        {"symbol": "ZZZZ", "date": "2026-11-12", "dividend": 0.1},
        {"symbol": "QQQQ", "date": "2026-11-13", "dividend": 0.2},
    ]
    _mock_inline([], div)
    report = refresh_events(store, _client(store), TODAY)
    assert report.n_exdiv == 4
    assert sorted(_events(store)["symbol"].to_list()) == ["GS", "JNJ", "KO", "LMT"]


@respx.mock
def test_real_payload_has_no_time_of_day(store):
    raw = _fixture("earnings_calendar.json")
    assert all("time" not in r for r in raw)  # the recorded payload carries no time field
    _mock_ok()
    report = refresh_events(store, _client(store), TODAY)
    earn = _events(store).filter(pl.col("type") == "earnings")
    assert earn.height == 5
    assert earn["time_of_day"].to_list() == [None] * 5
    assert report.n_earnings_with_time == 0


@respx.mock
def test_confirmed_from_recorded_actuals(store):
    _mock_ok()
    refresh_events(store, _client(store), TODAY)
    earn = _events(store).filter(pl.col("type") == "earnings")
    conf = dict(zip(earn["symbol"].to_list(), earn["confirmed"].to_list(), strict=True))
    assert conf == {"GE": True, "GM": True, "NVDA": False, "TGT": False, "WMT": False}


SYNTHETIC_EARN = [  # synthetic: the real payload carries no time field
    {"symbol": "GE", "date": "2026-10-29", "time": "bmo", "epsEstimated": 1.0},
    {"symbol": "GM", "date": "2026-10-30", "time": "amc", "epsEstimated": 1.0},
    {"symbol": "WMT", "date": "2026-11-02", "time": "", "epsEstimated": 1.0},
    {"symbol": "NVDA", "date": "2026-11-03", "time": "dmh", "epsEstimated": 1.0},
    {"symbol": "TGT", "date": "2026-11-04", "epsEstimated": 1.0},
]


@respx.mock
def test_time_of_day_mapping_synthetic(store):
    # synthetic: the real payload carries no time field; the mapping stays supported in code
    _mock_inline(SYNTHETIC_EARN, [])
    report = refresh_events(store, _client(store), TODAY)
    earn = _events(store)
    tod = dict(zip(earn["symbol"].to_list(), earn["time_of_day"].to_list(), strict=True))
    assert tod == {"GE": "bmo", "GM": "amc", "WMT": None, "NVDA": None, "TGT": None}
    assert report.n_earnings_with_time == 2


@respx.mock
def test_past_dated_row_is_confirmed_even_without_actual_eps(store):
    body = [  # synthetic: neither row has epsActual
        {"symbol": "GE", "date": "2026-10-15", "epsEstimated": 1.7},
        {"symbol": "GM", "date": "2026-10-29", "epsEstimated": 4.9},
    ]
    _mock_inline(body, [])
    refresh_events(store, _client(store), TODAY)
    earn = _events(store).filter(pl.col("type") == "earnings")
    conf = dict(zip(earn["symbol"].to_list(), earn["confirmed"].to_list(), strict=True))
    assert conf == {"GE": True, "GM": False}


@respx.mock
def test_refresh_idempotent(store):
    _mock_ok()
    refresh_events(store, _client(store), TODAY)
    first = _events(store)
    refresh_events(store, _client(store), TODAY)
    second = _events(store)
    assert first.height == second.height == 9
    assert first.equals(second)


@respx.mock
def test_past_rows_without_fmp_record_are_kept(store):
    _mock_ok()
    _put_earnings(store, "GE", date(2026, 10, 12))
    refresh_events(store, _client(store), TODAY)
    assert _events(store).filter(pl.col("date") == date(2026, 10, 12)).height == 1


@respx.mock
def test_uses_exactly_two_calls(store):
    e, d = _mock_ok()
    report = refresh_events(store, _client(store), TODAY, days_ahead=45)
    assert e.call_count == 1
    assert d.call_count == 1
    assert report.calls_used == 2
    assert _client(store).calls_today() == 2
    params = e.calls[0].request.url.params
    assert params["from"] == "2026-10-10"
    assert params["to"] == "2026-12-04"


@pytest.mark.parametrize("status", [402, 403])
@pytest.mark.parametrize("dead", ["earnings", "exdiv"])
@respx.mock
def test_unavailable_half_is_reported_not_an_error(store, status, dead):
    e = respx.get(EARN_URL).mock(
        return_value=httpx.Response(
            status if dead == "earnings" else 200, json=_fixture("earnings_calendar.json")
        )
    )
    d = respx.get(DIV_URL).mock(
        return_value=httpx.Response(
            status if dead == "exdiv" else 200, json=_fixture("dividends_calendar.json")
        )
    )
    report = refresh_events(store, _client(store), TODAY)
    assert report.unavailable == (dead,)
    assert (report.n_earnings if dead == "earnings" else report.n_exdiv) == 0
    assert (report.n_exdiv if dead == "earnings" else report.n_earnings) > 0
    assert e.call_count == d.call_count == 1


@respx.mock
def test_cli_refresh_reports_unavailable_and_exits_zero(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("FMP_API_KEY", KEY)
    store = Store(tmp_path / "store")
    store.init_schema()
    store.upsert("symbols", pl.DataFrame({"symbol": ["GS"], "active": [True]}), ["symbol"])
    respx.get(EARN_URL).mock(return_value=httpx.Response(402))
    respx.get(DIV_URL).mock(
        return_value=httpx.Response(200, json=_fixture("dividends_calendar.json"))
    )
    result = runner.invoke(app, ["events", "refresh", "--days", "45"])
    assert result.exit_code == 0, result.output
    assert "UNAVAILABLE: earnings calendar" in result.output
    assert "symbols with upcoming earnings: 0 of 1 active" in result.output
    assert KEY not in result.output


def _cli_store(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("FMP_API_KEY", KEY)
    st = Store(tmp_path / "store")
    st.init_schema()
    st.upsert(
        "symbols", pl.DataFrame({"symbol": ACTIVE, "active": [True] * len(ACTIVE)}), ["symbol"]
    )


@respx.mock
def test_cli_reports_time_of_day_coverage_real_payload(clean_env, tmp_path):
    _cli_store(clean_env, tmp_path)
    _mock_ok()
    result = runner.invoke(app, ["events", "refresh"])
    assert result.exit_code == 0, result.output
    assert "time of day known for 0 of 5 earnings rows" in result.output


@respx.mock
def test_cli_reports_time_of_day_coverage_synthetic(clean_env, tmp_path):
    _cli_store(clean_env, tmp_path)  # synthetic: the real payload carries no time field
    _mock_inline(SYNTHETIC_EARN, [])
    result = runner.invoke(app, ["events", "refresh"])
    assert result.exit_code == 0, result.output
    assert "time of day known for 2 of 5 earnings rows" in result.output


def test_cli_refresh_requires_key(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    result = runner.invoke(app, ["events", "refresh"])
    assert result.exit_code == 1
    assert "fmp_api_key" in result.output


def _put_earnings(store, sym, d):
    store.upsert(
        "events",
        pl.DataFrame(
            {
                "symbol": [sym],
                "date": [d],
                "type": ["earnings"],
                "time_of_day": [None],
                "source": ["fmp"],
                "confirmed": [False],
            },
            schema_overrides={"time_of_day": pl.String},
        ),
        ["symbol", "date", "type"],
    )


def test_next_earnings(store):
    _put_earnings(store, "AAPL", date(2026, 10, 29))
    _put_earnings(store, "AAPL", date(2026, 10, 10))
    assert next_earnings(store, "AAPL", date(2026, 10, 20)) == date(2026, 10, 29)
    assert next_earnings(store, "AAPL", date(2026, 10, 29)) == date(2026, 10, 29)
    assert next_earnings(store, "AAPL", date(2026, 10, 30)) is None
    assert next_earnings(store, "JPM", date(2026, 10, 20)) is None


def test_days_to_earnings_trading_days(store):
    # Mon 2026-11-02 .. Fri 2026-11-13 with Wed 2026-11-11 absent (a holiday), plus the prior week
    days = [
        date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29),
        date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4),
        date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10),
        date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16),
    ]  # fmt: skip
    _bars(store, days)
    _put_earnings(store, "AAPL", date(2026, 11, 13))
    _put_earnings(store, "JPM", date(2026, 10, 27))
    out = days_to_earnings(store, ["AAPL", "JPM", "XOM"], date(2026, 11, 10))
    rows = {r["symbol"]: r for r in out.iter_rows(named=True)}
    # (Nov 10, Nov 13] = Nov 12, 13; the missing Nov 11 is not counted (weekdays would give 3)
    assert rows["AAPL"]["days_to_earnings"] == 2
    assert rows["AAPL"]["days_since_earnings"] is None
    assert rows["AAPL"]["approx"] is False
    # (Oct 27, Nov 10] = Oct 28,29,30, Nov 2,3,4,5,6,9,10
    assert rows["JPM"]["days_since_earnings"] == 10
    assert rows["JPM"]["days_to_earnings"] is None
    assert rows["XOM"]["days_to_earnings"] is None
    assert rows["XOM"]["days_since_earnings"] is None


def test_days_to_earnings_weekday_fallback_is_marked_approx(store):
    _put_earnings(store, "AAPL", date(2026, 11, 13))
    out = days_to_earnings(store, ["AAPL"], date(2026, 11, 10))  # no bars at all
    assert out["days_to_earnings"].to_list() == [3]  # Nov 11, 12, 13 as weekdays
    assert out["approx"].to_list() == [True]
    _bars(store, [date(2026, 11, 9), date(2026, 11, 10)])  # bars end before the event
    out = days_to_earnings(store, ["AAPL"], date(2026, 11, 10))
    assert out["days_to_earnings"].to_list() == [3]
    assert out["approx"].to_list() == [True]


def test_days_to_earnings_rejects_bad_symbol(store):
    with pytest.raises(ValueError):
        days_to_earnings(store, ["aapl; DROP"], TODAY)
    with pytest.raises(ValueError):
        next_earnings(store, "bad symbol", TODAY)
