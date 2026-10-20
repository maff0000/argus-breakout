import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
import structlog
import yaml
from pydantic import SecretStr
from typer.testing import CliRunner

from argus.cli import app
from argus.data.providers.fmp import BASE_URL, FMPClient
from argus.data.store import Store
from argus.data.tickers import is_valid
from argus.data.universe import (
    HANSHOF_URL,
    MAX_BOUNDED_ROWS,
    WIKIPEDIA_URL,
    build_membership,
    fetch_wikipedia_constituents,
    load_hanshof_csv,
    map_industry_group,
    next_trading_day,
    parse_wikipedia_changes,
    previous_trading_day,
    refresh,
)
from argus.settings import get_settings

TESTS = Path(__file__).parent
FIX = TESTS / "fixtures"
CONFIG = TESTS.parent / "config"
WIKI_HTML = (FIX / "universe" / "wikipedia_sp500.html").read_text(encoding="utf-8")
HANSHOF_SAMPLE = FIX / "universe" / "hanshof_sample.csv"
CHANGES_TABLE = (FIX / "universe" / "wikipedia_changes_table.html").read_text(encoding="utf-8")
HISTORICAL = json.loads((FIX / "fmp" / "historical_sp500.json").read_text())
CURRENT = json.loads((FIX / "fmp" / "sp500_constituent.json").read_text())

runner = CliRunner()
PLACEHOLDER = "unit-test-placeholder"


@pytest.fixture(autouse=True)
def _reset_structlog():
    structlog.reset_defaults()  # another test may have bound structlog to a closed stdout
    yield


def _wiki_client(html: str = WIKI_HTML) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == WIKIPEDIA_URL
        return httpx.Response(200, text=html)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _intervals(df: pl.DataFrame, symbol: str) -> list[tuple]:
    sub = df.filter(pl.col("symbol") == symbol).sort("start_date")
    return [(r["start_date"], r["end_date"], r["source"]) for r in sub.iter_rows(named=True)]


@pytest.fixture
def fmp_changes(tmp_path):
    store = Store(tmp_path / "chg")
    store.init_schema()
    with respx.mock:
        respx.get(BASE_URL + "historical-sp500-constituent").mock(
            return_value=httpx.Response(200, json=HISTORICAL)
        )
        client = FMPClient(SecretStr(PLACEHOLDER), 200, store, retry_wait=0)
        return client.historical_sp500_changes()


# ---------------------------------------------------------------- wikipedia
def test_wikipedia_parse_counts():
    df = fetch_wikipedia_constituents(_wiki_client())
    assert df.columns == ["symbol", "name", "gics_sector", "gics_sub_industry", "date_added"]
    assert df.height >= 490
    assert df["gics_sector"].n_unique() == 11
    assert (df["gics_sub_industry"].str.strip_chars() != "").all()
    assert df["symbol"].n_unique() == df.height
    assert all(is_valid(s) for s in df["symbol"].to_list())
    assert "BRK.B" in df["symbol"].to_list()


def test_wikipedia_rejects_short_table():
    rows = WIKI_HTML.split("</tr>")
    short = "</tr>".join(rows[:100]) + "</tr></tbody></table></body></html>"
    with pytest.raises(ValueError, match="rows"):
        fetch_wikipedia_constituents(_wiki_client(short))


# ---------------------------------------------------------------- gics
def test_gics_yaml_integrity():
    gics = yaml.safe_load((CONFIG / "gics.yaml").read_text())
    sectors, groups, subs = gics["sectors"], gics["industry_groups"], gics["sub_industry_to_group"]
    assert len(sectors) == 11 and len(set(sectors)) == 11
    assert len(groups) == 25
    assert all(sector in sectors for sector in groups.values())
    assert set(groups.values()) == set(sectors)  # every sector owns at least one group
    assert len(subs) == 163
    assert all(group in groups for group in subs.values())
    assert set(subs.values()) == set(groups)  # every group owns at least one sub-industry


def test_every_wikipedia_sub_industry_maps():
    gics = yaml.safe_load((CONFIG / "gics.yaml").read_text())
    df = fetch_wikipedia_constituents(_wiki_client())
    for row in df.iter_rows(named=True):
        group = map_industry_group(row["gics_sub_industry"], gics)
        assert gics["industry_groups"][group] == row["gics_sector"], row["symbol"]


def test_map_industry_group_raises_on_unknown():
    gics = yaml.safe_load((CONFIG / "gics.yaml").read_text())
    assert map_industry_group("Semiconductors", gics) == "Semiconductors & Semiconductor Equipment"
    with pytest.raises(ValueError, match="unknown GICS sub-industry"):
        map_industry_group("Quantum Widgets", gics)
    with pytest.raises(ValueError):
        map_industry_group(None, gics)


# ---------------------------------------------------------------- trading days
def test_trading_day_helpers():
    assert previous_trading_day(date(2016, 3, 28)) == date(2016, 3, 24)  # Good Friday 03-25
    assert previous_trading_day(date(2017, 3, 20)) == date(2017, 3, 17)  # Monday -> Friday
    assert previous_trading_day(date(2016, 1, 19)) == date(2016, 1, 15)  # MLK Monday 01-18
    assert previous_trading_day(date(2025, 8, 23)) == date(2025, 8, 22)  # Saturday
    assert previous_trading_day(date(2025, 1, 10)) == date(2025, 1, 8)  # national day of mourning
    assert previous_trading_day(date(2023, 6, 20)) == date(2023, 6, 16)  # Juneteenth (Mon)
    assert next_trading_day(date(2020, 7, 2)) == date(2020, 7, 6)  # Jul 3 observed holiday


# ---------------------------------------------------------------- membership
def _no_changes() -> pl.DataFrame:
    return pl.DataFrame(
        schema={"date": pl.Date, "symbol": pl.String, "action": pl.String, "reason": pl.String}
    )


def test_membership_intervals():
    hanshof = load_hanshof_csv(HANSHOF_SAMPLE)
    assert hanshof.height == 10
    df = build_membership(hanshof, None, _no_changes(), start=date(2015, 1, 1))
    assert df.columns == ["symbol", "start_date", "end_date", "source"]
    # FSLR leaves in the snapshot dated Monday 2017-03-20 and returns on 2022-12-19:
    assert _intervals(df, "FSLR") == [
        (date(2015, 1, 1), date(2017, 3, 17), "hanshof"),
        (date(2022, 12, 19), None, "hanshof"),
    ]
    # DD leaves in the snapshot dated Friday 2017-09-01 and returns on 2019-06-03:
    assert _intervals(df, "DD") == [
        (date(2015, 1, 1), date(2017, 8, 31), "hanshof"),
        (date(2019, 6, 3), None, "hanshof"),
    ]
    # BRK-B / BRK.B spellings collapse to one canonical symbol with one unbroken interval
    assert _intervals(df, "BRK.B") == [(date(2015, 1, 1), None, "hanshof")]
    assert not [s for s in df["symbol"].to_list() if not is_valid(s)]
    # no overlaps, unique primary key
    assert df.select(["symbol", "start_date"]).is_duplicated().sum() == 0
    for sym in ("FSLR", "DD"):
        iv = _intervals(df, sym)
        assert iv[0][1] < iv[1][0]


def test_membership_start_clip_merge_and_holiday():
    snaps = pl.DataFrame(
        {
            "date": [date(2014, 6, 2), date(2016, 1, 19), date(2016, 6, 1), date(2016, 6, 2)],
            "symbols": [["AAA", "BBB"], ["AAA"], ["AAA", "BBB"], ["AAA", "BBB"]],
        }
    )
    df = build_membership(snaps, None, _no_changes(), start=date(2015, 1, 1))
    # start clipped to 2015-01-01; BBB removed Tue 2016-01-19, MLK Monday => end Fri 01-15
    assert _intervals(df, "BBB")[0] == (date(2015, 1, 1), date(2016, 1, 15), "hanshof")
    assert _intervals(df, "BBB")[1][0] == date(2016, 6, 1)
    assert _intervals(df, "AAA") == [(date(2015, 1, 1), None, "hanshof")]
    # an interval that ended before `start` is dropped entirely
    snaps2 = pl.DataFrame(
        {"date": [date(2013, 1, 2), date(2014, 3, 3)], "symbols": [["OLD"], ["NEW"]]}
    )
    out = build_membership(snaps2, None, _no_changes(), start=date(2015, 1, 1))
    assert out["symbol"].to_list() == ["NEW"]


def test_fmp_fills_gap_after_hanshof(fmp_changes):
    hanshof = load_hanshof_csv(HANSHOF_SAMPLE)
    assert hanshof["date"].max() == date(2025, 8, 23)
    df = build_membership(hanshof, None, fmp_changes, start=date(2015, 1, 1))
    assert _intervals(df, "IBKR") == [(date(2025, 8, 28), None, "fmp")]
    for sym in ("APP", "HOOD", "EME"):
        assert _intervals(df, sym) == [(date(2025, 9, 22), None, "fmp")]
    # WBA was a member in hanshof's last snapshot; FMP removes it Thu 2025-08-28
    assert _intervals(df, "WBA")[-1] == (date(2015, 1, 1), date(2025, 8, 27), "hanshof+fmp")
    # changes dated on or before hanshof's last snapshot are NOT taken from FMP
    old = fmp_changes.filter(pl.col("date") <= date(2025, 8, 23))
    assert old.height > 0
    fmp_only = set(df.filter(pl.col("source") == "fmp")["symbol"].to_list())
    assert fmp_only == {"IBKR", "APP", "HOOD", "EME"}


def test_fmp_change_on_or_before_last_hanshof_snapshot_is_ignored(fmp_changes):
    hanshof = load_hanshof_csv(HANSHOF_SAMPLE)
    last = hanshof["date"].max()
    baseline = build_membership(hanshof, None, fmp_changes, start=date(2015, 1, 1))
    assert _intervals(baseline, "AAPL") == [(date(2015, 1, 1), None, "hanshof")]
    stale = pl.DataFrame(
        {
            "date": [date(2025, 6, 2), date(2025, 1, 2), last],
            "symbol": ["AAPL", "ZZZZ", "MSFT"],
            "action": ["removed", "added", "removed"],
            "reason": ["stale", "stale", "same-day"],
        }
    )
    assert stale["date"].max() <= last
    out = build_membership(hanshof, None, pl.concat([fmp_changes, stale]), start=date(2015, 1, 1))
    # hanshof is primary up to its last snapshot: these FMP changes must change nothing
    assert out.sort(["symbol", "start_date"]).equals(baseline.sort(["symbol", "start_date"]))
    assert _intervals(out, "AAPL") == [(date(2015, 1, 1), None, "hanshof")]
    assert _intervals(out, "MSFT") == [(date(2015, 1, 1), None, "hanshof")]
    assert _intervals(out, "ZZZZ") == []


# ---------------------------------------------------------------- CLI / refresh
@pytest.fixture
def cli_env(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("ARGUS_CONFIG_DIR", str(CONFIG))
    clean_env.setenv("FMP_API_KEY", PLACEHOLDER)
    return tmp_path / "store"


def _mock_sources(
    wiki_html: str = WIKI_HTML,
    profile=None,
    fmp_status: int = 200,
    profile_status: int = 200,
    hanshof_text: str | None = None,
):
    """respx routes for every source; `fmp_status`!=200 makes the three non-profile endpoints
    (and `profile_status`!=200 the profile endpoint) answer with that HTTP status."""
    respx.get(WIKIPEDIA_URL).mock(return_value=httpx.Response(200, text=wiki_html))
    respx.get(HANSHOF_URL).mock(
        return_value=httpx.Response(
            200, text=hanshof_text or HANSHOF_SAMPLE.read_text(encoding="utf-8")
        )
    )
    for endpoint, body in (
        ("historical-sp500-constituent", HISTORICAL),
        ("sp500-constituent", CURRENT),
    ):
        respx.get(BASE_URL + endpoint).mock(
            return_value=httpx.Response(200, json=body)
            if fmp_status == 200
            else httpx.Response(fmp_status, json={"Error Message": "not on this plan"})
        )
    respx.get(BASE_URL + "stock-list").mock(return_value=httpx.Response(fmp_status))
    return respx.get(BASE_URL + "profile").mock(
        return_value=httpx.Response(200, json=profile if profile is not None else [])
        if profile_status == 200
        else httpx.Response(profile_status, json={"Error Message": "not on this plan"})
    )


def _fmp_calls() -> int:
    return sum(c.request.url.host == "financialmodelingprep.com" for c in respx.calls)


@respx.mock
def test_refresh_populates_symbols_and_membership(cli_env):
    _mock_sources()
    result = runner.invoke(app, ["universe", "refresh", "--date", "2025-12-31"])
    assert result.exit_code == 0, result.output
    store = Store(cli_env)
    nulls = store.read(
        "SELECT count(*) AS n FROM symbols "
        "WHERE gics_industry_group IS NULL OR gics_industry_group = ''"
    )["n"][0]
    assert nulls == 0
    etf = store.read("SELECT symbol FROM symbols WHERE gics_sector = ? ORDER BY symbol", ["ETF"])
    assert {"SPY", "RSP", "SMH", "XLK", "XLRE"} <= set(etf["symbol"].to_list())
    groups = store.read(
        "SELECT count(*) AS n FROM symbols WHERE gics_industry_group = ? AND gics_sector <> ?",
        ["ETF", "ETF"],
    )["n"][0]
    assert groups == 0
    n_current = store.read("SELECT count(*) AS n FROM symbols WHERE gics_sector <> ?", ["ETF"])
    assert n_current["n"][0] == 503
    assert all(is_valid(s) for s in store.read("SELECT symbol FROM symbols")["symbol"].to_list())
    members = store.members_on(date(2025, 12, 31))
    assert "IBKR" in members and "WBA" not in members
    assert store.members_on(date(2025, 8, 27)).count("WBA") == 1
    assert "missing industry group: 0" in result.output
    assert "membership gap route: fmp" in result.output
    assert "rows by source:" in result.output and "fmp=" in result.output
    used = store.read("SELECT SUM(rows) AS n FROM ingest_log WHERE source = ?", ["fmp-budget"])
    assert used["n"][0] <= 60
    logged = store.read("SELECT status FROM ingest_log WHERE source = ?", ["universe"])
    assert logged["status"].to_list() == ["ok"]


@respx.mock
def test_refresh_is_idempotent_and_honours_date(cli_env):
    _mock_sources()
    first = runner.invoke(app, ["universe", "refresh", "--date", "2025-09-01"])
    second = runner.invoke(app, ["universe", "refresh", "--date", "2025-09-01"])
    assert first.exit_code == 0 and second.exit_code == 0
    assert first.output == second.output
    store = Store(cli_env)
    assert store.read("SELECT count(*) AS n FROM membership")["n"][0] == int(
        first.output.split("membership rows: ")[1].split()[0]
    )
    members = store.members_on(date(2025, 9, 1))
    assert "IBKR" in members and "APP" not in members  # 2025-09-22 change is after --date


@respx.mock
def test_refresh_falls_back_to_fmp_when_wikipedia_fails(cli_env):
    _mock_sources()
    respx.get(WIKIPEDIA_URL).mock(return_value=httpx.Response(503))
    result = runner.invoke(app, ["universe", "refresh", "--date", "2025-12-31"])
    assert result.exit_code == 0, result.output
    assert "wikipedia" not in result.output.split("sources:")[1]
    assert "fmp:sp500-constituent" in result.output


@respx.mock
def test_missing_group_exits_nonzero(cli_env):
    # one constituent carries a sub-industry GICS does not know; FMP profile has nothing either
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    assert broken != WIKI_HTML
    profile = _mock_sources(wiki_html=broken, profile=[])
    result = runner.invoke(app, ["universe", "refresh", "--date", "2025-12-31"])
    assert result.exit_code == 1
    assert "missing industry group: 1" in result.output
    assert profile.call_count == 1  # the fallback was tried
    store = Store(cli_env)
    nulls = store.read(
        "SELECT count(*) AS n FROM symbols WHERE gics_industry_group IS NULL "
        "OR gics_industry_group = ''"
    )["n"][0]
    assert nulls == 1  # never a silent default
    logged = store.read("SELECT status FROM ingest_log WHERE source = ?", ["universe"])
    assert logged["status"].to_list() == ["failed"]


@respx.mock
def test_profile_fallback_can_rescue_a_symbol(cli_env):
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    _mock_sources(wiki_html=broken, profile=[{"symbol": "X", "industry": "Semiconductors"}])
    result = runner.invoke(app, ["universe", "refresh", "--date", "2025-12-31"])
    assert result.exit_code == 0, result.output
    assert "fmp:profile" in result.output


def test_refresh_requires_fmp_key(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("ARGUS_CONFIG_DIR", str(CONFIG))
    result = runner.invoke(app, ["universe", "refresh"])
    assert result.exit_code == 1
    assert "fmp_api_key" in result.output


# ---------------------------------------------------------------- AMD-0013 routing
def _run_refresh(cli_env, as_of=date(2026, 10, 20)):
    store = Store(cli_env)
    store.init_schema()
    with httpx.Client() as http:
        report = refresh(store, get_settings(), http, as_of=as_of)
    return store, report


def _hanshof_with_extra_last_members(n: int) -> str:
    """The sample, with n extra tickers in its last snapshot (absent from the wiki fixture)."""
    lines = HANSHOF_SAMPLE.read_text(encoding="utf-8").rstrip("\n").split("\n")
    assert lines[-1].startswith("2025-08-23,") and lines[-1].endswith('"')
    extras = "".join(f",ZQX{chr(65 + i)}" for i in range(n))
    lines[-1] = lines[-1][:-1] + extras + '"'
    return "\n".join(lines) + "\n"


def test_wikipedia_date_added_parsed_and_tolerant():
    df = fetch_wikipedia_constituents(_wiki_client())
    dates = dict(zip(df["symbol"].to_list(), df["date_added"].to_list(), strict=True))
    assert dates["APP"] == date(2025, 9, 22) and dates["IBKR"] == date(2025, 8, 28)
    html = WIKI_HTML.replace("<td>2025-09-22</td>", "<td></td>", 1).replace(
        "<td>2025-08-28</td>", "<td>sometime in 2025 [3]</td>", 1
    )
    assert html != WIKI_HTML
    df2 = fetch_wikipedia_constituents(_wiki_client(html))
    assert df2.height == df.height
    assert df2["date_added"].null_count() == df["date_added"].null_count() + 2
    html3 = WIKI_HTML.replace("<td>2025-09-22</td>", "<td>September 22, 2025[5]</td>", 1)
    d3 = dict(zip(*[fetch_wikipedia_constituents(_wiki_client(html3))[c].to_list()
                    for c in ("symbol", "date_added")], strict=True))
    assert d3["APP"] == date(2025, 9, 22)


def test_changes_table_detected_when_present_and_skipped_when_absent():
    assert parse_wikipedia_changes(WIKI_HTML) is None  # the live page shape: no changes table
    page = WIKI_HTML.replace("</body>", CHANGES_TABLE + "</body>")
    assert page != WIKI_HTML
    ch = parse_wikipedia_changes(page)
    assert ch is not None
    got = {(r["date"], r["symbol"], r["action"]) for r in ch.iter_rows(named=True)}
    assert (date(2025, 8, 28), "IBKR", "added") in got
    assert (date(2025, 8, 28), "WBA", "removed") in got
    assert (date(2025, 9, 22), "APP", "added") in got
    assert (date(2025, 8, 1), "OLDX", "removed") in got and ch.height == 9
    # a table without Added/Removed columns is not a changes table
    other = WIKI_HTML.replace(
        "</body>", "<table><tr><th>Date</th><th>Note</th></tr><tr><td>2025-01-01</td>"
        "<td>x</td></tr></table></body>"
    )
    assert parse_wikipedia_changes(other) is None


@respx.mock
def test_route_b_used_when_changes_table_present_and_fmp_402(cli_env):
    _mock_sources(
        wiki_html=WIKI_HTML.replace("</body>", CHANGES_TABLE + "</body>"), fmp_status=402
    )
    store, report = _run_refresh(cli_env)
    assert report.gap_route == "wikipedia-changes"
    assert report.rows_by_source.get("wikipedia-derived-bounded", 0) == 0
    iv = store.read("SELECT * FROM membership WHERE symbol IN ('IBKR','WBA') ORDER BY symbol")
    got = {
        r["symbol"]: (r["start_date"], r["end_date"], r["source"]) for r in iv.iter_rows(named=True)
    }
    assert got["IBKR"] == (date(2025, 8, 28), None, "wikipedia-changes")
    assert got["WBA"][1] == date(2025, 8, 27) and got["WBA"][2] == "hanshof+wikipedia-changes"
    assert report.rows_by_source["wikipedia-changes"] >= 4


@respx.mock
def test_gap_derivation_when_fmp_402(cli_env):
    _mock_sources(fmp_status=402)  # fixture page has NO changes table
    store, report = _run_refresh(cli_env)
    assert report.gap_route == "wikipedia-derived"
    rows = store.read("SELECT * FROM membership")
    by = {}
    for r in rows.iter_rows(named=True):
        by.setdefault(r["symbol"], []).append((r["start_date"], r["end_date"], r["source"]))
    # additions after H are exact, with the page's own Date added
    assert by["IBKR"] == [(date(2025, 8, 28), None, "wikipedia-derived-exact")]
    for sym in ("APP", "HOOD", "EME"):
        assert by[sym] == [(date(2025, 9, 22), None, "wikipedia-derived-exact")]
    # in hanshof@H but absent from the current table: bounded at H
    assert by["WBA"][-1] == (date(2015, 1, 1), date(2025, 8, 23), "wikipedia-derived-bounded")
    # untouched members keep the hanshof source
    assert by["AAPL"] == [(date(2015, 1, 1), None, "hanshof")]
    h = load_hanshof_csv(HANSHOF_SAMPLE)
    last = set(h["symbols"][-1].to_list())
    cur = set(fetch_wikipedia_constituents(_wiki_client())["symbol"].to_list())
    assert report.rows_by_source["wikipedia-derived-bounded"] == len(last - cur) == 33
    assert report.rows_by_source["hanshof"] > 500
    # exact additions: every current row with Date added in (H, as_of]
    wiki = fetch_wikipedia_constituents(_wiki_client())
    n_exact = wiki.filter(pl.col("date_added") > date(2025, 8, 23)).height
    assert report.rows_by_source["wikipedia-derived-exact"] == n_exact
    # not a member after being bounded out; a member from the exact date
    assert "WBA" not in store.members_on(date(2026, 10, 20))
    assert "APP" not in store.members_on(date(2025, 9, 21))
    assert "APP" in store.members_on(date(2025, 9, 22))


@respx.mock
def test_derivation_respects_as_of(cli_env):
    _mock_sources(fmp_status=402)
    store, report = _run_refresh(cli_env, as_of=date(2025, 9, 1))
    assert "IBKR" in store.members_on(date(2025, 9, 1)) and "APP" not in store.members_on(
        date(2025, 9, 1)
    )
    assert report.rows_by_source.get("wikipedia-derived-exact", 0) == 1  # only IBKR <= as_of


@respx.mock
def test_402_does_not_abort_refresh(cli_env):
    # every FMP endpoint is 402, including profile, and one row needs the profile fallback
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    profile = _mock_sources(wiki_html=broken, fmp_status=402, profile_status=402)
    store, report = _run_refresh(cli_env)  # must not raise
    assert report.n_symbols > 500 and report.n_members_today > 0
    assert report.n_missing_group == 1  # unmapped, counted, not an abort
    assert report.gap_route == "wikipedia-derived"
    assert profile.call_count == 1
    assert "fmp:sp500-constituent" not in report.sources_used
    assert "fmp:historical-sp500-constituent" not in report.sources_used
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 1  # only because of the unmapped group (existing rule)
    assert "membership gap route: wikipedia-derived" in result.output
    assert "rows by source:" in result.output


@respx.mock
def test_402_everywhere_exits_zero_and_stays_inside_call_budget(cli_env):
    _mock_sources(fmp_status=402, profile_status=402)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 0, result.output
    assert 0 < _fmp_calls() <= 60
    assert "wikipedia-derived-bounded=33" in result.output


@respx.mock
def test_fmp_call_count_bounded_when_many_profile_fallbacks(cli_env):
    # make >50 current members need the profile fallback; calls must still be <= 60 (AC6)
    broken = WIKI_HTML
    for sub in ("Semiconductors", "Application Software", "Health Care Equipment",
                "Regional Banks", "Systems Software"):
        broken = broken.replace(f"<td>{sub}</td>", "<td>Quantum Widgets</td>")
    profile = _mock_sources(wiki_html=broken, profile=[])
    _, report = _run_refresh(cli_env, as_of=date(2025, 12, 31))
    assert report.n_missing_group > 50
    assert profile.call_count == 50
    assert _fmp_calls() <= 60


@respx.mock
def test_bounded_removals_over_limit_is_a_stop(cli_env):
    n_base = 33
    # exactly at the limit: allowed
    _mock_sources(fmp_status=402, hanshof_text=_hanshof_with_extra_last_members(
        MAX_BOUNDED_ROWS - n_base))
    ok = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert ok.exit_code == 0, ok.output
    assert f"wikipedia-derived-bounded={MAX_BOUNDED_ROWS}" in ok.output
    respx.reset()
    # one over: stop (exit 1), still reported
    _mock_sources(fmp_status=402, hanshof_text=_hanshof_with_extra_last_members(
        MAX_BOUNDED_ROWS - n_base + 1))
    bad = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert bad.exit_code == 1
    assert f"wikipedia-derived-bounded={MAX_BOUNDED_ROWS + 1}" in bad.output
    assert "STOP" in bad.output
    logged = Store(cli_env).read(
        "SELECT status FROM ingest_log WHERE source = ? ORDER BY finished_at", ["universe"]
    )
    assert logged["status"].to_list() == ["ok", "failed"]


@respx.mock
def test_other_fmp_errors_still_abort_refresh(cli_env):
    # only 402/403 mean "unavailable"; a 500 on the changes endpoint is still a failure
    _mock_sources()
    respx.get(BASE_URL + "historical-sp500-constituent").mock(return_value=httpx.Response(500))
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 1
