import json
import re
import shutil
from datetime import date, timedelta
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
    BackDatedRefreshError,
    MembershipInvariantError,
    Rename,
    _require_members_equal_table,
    build_membership,
    check_refresh_date,
    current_members_without_open_row,
    fetch_wikipedia_constituents,
    is_trading_day,
    load_hanshof_csv,
    load_renames,
    map_industry_group,
    members_on_date,
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
_CHG_HEAD = (
    '<table class="wikitable sortable" id="changes">\n'
    '<tr><th rowspan="2">Date</th><th colspan="2">Added</th><th colspan="2">Removed</th>'
    '<th rowspan="2">Reason</th></tr>\n'
    "<tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr>\n"
)
_CHG_ROWS = (
    ("September 22, 2025", '<a href="#">APP</a>', "AppLovin", "MKTX", "MarketAxess", "scrubbed"),
    (
        "September 22, 2025", '<a href="#">HOOD</a>', "Robinhood Markets", "CZR", "Caesars",
        "scrubbed",
    ),
    ("September 22, 2025", '<a href="#">EME</a>', "Emcor", "LKQ", "LKQ Corp", "scrubbed"),
    (
        "August 28, 2025", '<a href="#">IBKR</a>', "Interactive Brokers", "WBA", "Walgreens",
        "scrubbed",
    ),
    ("August 1, 2025", "", "", "OLDX", "Pre-gap removal", "ignored: before H"),
)
CHANGES_TABLE = (  # inlined from the former wikipedia_changes_table.html fixture (WO-0003 2)
    _CHG_HEAD
    + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>\n" for r in _CHG_ROWS)
    + "</table>\n"
)
HISTORICAL = json.loads((FIX / "fmp" / "historical_sp500.json").read_text())
CURRENT = json.loads((FIX / "fmp" / "sp500_constituent.json").read_text())

runner = CliRunner()
PLACEHOLDER = "unit-test-placeholder"


@pytest.fixture(autouse=True)
def _reset_structlog():
    structlog.reset_defaults()  # another test may have bound structlog to a closed stdout
    yield


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    # The refresh date window (AMD-0015 2A) is relative to today; pin "today" so the suite does
    # not depend on the wall clock (the fixtures are a 2026-10-20 snapshot of the live page).
    monkeypatch.setattr("argus.data.universe._today_utc", lambda: date(2026, 10, 20))


def _wiki_client(html: str = WIKI_HTML) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == WIKIPEDIA_URL
        return httpx.Response(200, text=html)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _complete_history() -> tuple[list[dict], list[tuple[str, date]], list[str]]:
    """HISTORICAL completed for a today-dated run: an 'added' record for every current-table
    symbol whose Date added is after the last hanshof snapshot, and a 'removed' record for every
    hanshof@H member absent from the current table (other than the mapped renames, which the
    rename map handles). AMD-0014 makes a partial route (a)/(b) history a failure."""
    h = date(2025, 8, 23)
    wiki = fetch_wikipedia_constituents(_wiki_client()).sort(["date_added", "symbol"])
    known_added = {r["symbol"] for r in HISTORICAL}
    known_removed = {r["removedTicker"] for r in HISTORICAL if r.get("removedTicker")}
    added = [
        (r["symbol"], r["date_added"])
        for r in wiki.iter_rows(named=True)
        if r["date_added"] is not None and r["date_added"] > h and r["symbol"] not in known_added
    ]
    last = set(load_hanshof_csv(HANSHOF_SAMPLE)["symbols"][-1].to_list())
    mapped_old = {r.old for r in load_renames(CONFIG)}
    removed = sorted(last - set(wiki["symbol"].to_list()) - mapped_old - known_removed)
    body = (
        HISTORICAL
        + [{"date": d.isoformat(), "symbol": sym, "reason": "fixture"} for sym, d in added]
        + [{"date": "2025-10-01", "removedTicker": sym, "reason": "fixture"} for sym in removed]
    )
    return body, added, removed


COMPLETE_HISTORY, EXTRA_ADDITIONS, EXTRA_REMOVALS = _complete_history()


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
    history=None,
    current=None,
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
        ("historical-sp500-constituent", COMPLETE_HISTORY if history is None else history),
        ("sp500-constituent", CURRENT if current is None else current),
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


def _current_symbols() -> list[str]:
    return fetch_wikipedia_constituents(_wiki_client())["symbol"].to_list()


def _historical_only(store: Store) -> list[str]:
    """Symbols in membership that are not in the current table (nor ETFs)."""
    in_membership = store.read("SELECT DISTINCT symbol FROM membership")["symbol"].to_list()
    return sorted(set(in_membership) - set(_current_symbols()))


def _counts(store: Store) -> dict[str, int]:
    return {
        t: int(store.read(q)["n"][0])
        for t, q in (
            ("symbols", "SELECT count(*) AS n FROM symbols"),
            ("membership", "SELECT count(*) AS n FROM membership"),
            ("ingest_log", "SELECT count(*) AS n FROM ingest_log"),
        )
    }


@respx.mock
def test_refresh_populates_symbols_and_membership(cli_env):
    _mock_sources()
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 0, result.output
    store = Store(cli_env)
    # AC1 applies to current members and ETFs (active rows); historical-only rows may be NULL
    nulls = store.read(
        "SELECT count(*) AS n FROM symbols WHERE active AND "
        "(gics_industry_group IS NULL OR gics_industry_group = '')"
    )["n"][0]
    assert nulls == 0
    etf = store.read("SELECT symbol FROM symbols WHERE gics_sector = ? ORDER BY symbol", ["ETF"])
    assert {"SPY", "RSP", "SMH", "XLK", "XLRE"} <= set(etf["symbol"].to_list())
    groups = store.read(
        "SELECT count(*) AS n FROM symbols WHERE gics_industry_group = ? AND gics_sector <> ?",
        ["ETF", "ETF"],
    )["n"][0]
    assert groups == 0
    n_current = store.read(
        "SELECT count(*) AS n FROM symbols WHERE active AND gics_sector <> ?", ["ETF"]
    )
    assert n_current["n"][0] == 503
    assert all(is_valid(s) for s in store.read("SELECT symbol FROM symbols")["symbol"].to_list())
    members = store.members_on(date(2026, 10, 20))
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
    first = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-14"])
    second = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-14"])
    assert first.exit_code == 0 and second.exit_code == 0
    def report_lines(out: str) -> list[str]:  # drop timestamped structlog lines (stdout)
        return [ln for ln in out.splitlines() if not re.match(r"\d{4}-\d\d-\d\d \d\d:", ln)]

    assert report_lines(first.output) == report_lines(second.output)
    store = Store(cli_env)
    assert store.read("SELECT count(*) AS n FROM membership")["n"][0] == int(
        first.output.split("membership rows: ")[1].split()[0]
    )
    assert "members on 2026-10-14: 503" in first.output  # the report is dated by --date
    assert "IBKR" in store.members_on(date(2026, 10, 14))


@respx.mock
def test_refresh_falls_back_to_fmp_when_wikipedia_fails(cli_env):
    _mock_sources()
    respx.get(WIKIPEDIA_URL).mock(return_value=httpx.Response(503))
    # FMP-only current table carries no Date added, so only a today-dated run can be judged
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 0, result.output
    assert "wikipedia" not in result.output.split("sources:")[1]
    assert "fmp:sp500-constituent" in result.output


@respx.mock
def test_missing_group_exits_nonzero(cli_env):
    # one constituent carries a sub-industry GICS does not know; FMP profile has nothing either
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    assert broken != WIKI_HTML
    profile = _mock_sources(wiki_html=broken, profile=[])
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 1
    assert "missing industry group: 1" in result.output
    # the fallback was tried for the current member FIRST; historical-only symbols share the cap
    assert 1 <= profile.call_count <= 50
    store = Store(cli_env)
    nulls = store.read(
        "SELECT count(*) AS n FROM symbols WHERE active AND (gics_industry_group IS NULL "
        "OR gics_industry_group = '')"
    )["n"][0]
    assert nulls == 1  # never a silent default (current members and ETFs)
    logged = store.read("SELECT status FROM ingest_log WHERE source = ?", ["universe"])
    assert logged["status"].to_list() == ["failed"]


@respx.mock
def test_profile_fallback_can_rescue_a_symbol(cli_env):
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    _mock_sources(wiki_html=broken, profile=[{"symbol": "X", "industry": "Semiconductors"}])
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
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
    # the fixture changes table is partial; complete it (AMD-0014 fails a run whose members
    # differ from the current table) with the missing later additions and removals
    extra_rows = "".join(
        f'<tr><td>{d.isoformat()}</td><td><a href="#">{sym}</a></td><td>x</td><td></td><td></td>'
        "<td>fixture completion</td></tr>"
        for sym, d in EXTRA_ADDITIONS
    ) + "".join(
        f"<tr><td>2025-10-01</td><td></td><td></td><td>{sym}</td><td>x</td><td>fixture</td></tr>"
        for sym in EXTRA_REMOVALS
    )
    table = CHANGES_TABLE.replace("</table>", extra_rows + "</table>")
    assert table != CHANGES_TABLE
    _mock_sources(wiki_html=WIKI_HTML.replace("</body>", table + "</body>"), fmp_status=402)
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
    mapped_old = {r.old for r in load_renames(CONFIG)}
    assert len(mapped_old) == 5 and mapped_old <= last - cur  # AMD-0014: renames are not removals
    assert report.rows_by_source["wikipedia-derived-bounded"] == len(last - cur - mapped_old) == 28
    assert report.rows_by_source["hanshof"] > 500
    # exact additions: every current row with Date added in (H, as_of]
    wiki = fetch_wikipedia_constituents(_wiki_client())
    n_exact = wiki.filter(pl.col("date_added") > date(2025, 8, 23)).height
    assert report.rows_by_source["wikipedia-derived-exact"] == n_exact
    # not a member after being bounded out; a member from the exact date
    assert "WBA" not in store.members_on(date(2026, 10, 20))
    assert "APP" not in store.members_on(date(2025, 9, 21))
    assert "APP" in store.members_on(date(2025, 9, 22))


def test_membership_is_always_built_through_today():
    # AMD-0015 2A: build_membership has no as_of bound - a derived addition is an open row
    # whatever date the run was given (a back-dated refresh is limited to 7 days, but the
    # table is the table as of now)
    wiki = fetch_wikipedia_constituents(_wiki_client())
    table = wiki.select(["symbol", "date_added"])
    with pytest.raises(TypeError):
        build_membership(load_hanshof_csv(HANSHOF_SAMPLE), table, None, as_of=date(2025, 9, 1))
    m = build_membership(load_hanshof_csv(HANSHOF_SAMPLE), table, None)
    exact = m.filter(pl.col("source") == "wikipedia-derived-exact")
    assert exact.height == wiki.filter(pl.col("date_added") > date(2025, 8, 23)).height
    assert "APP" in members_on_date(m, date(2026, 10, 20))


@respx.mock
def test_402_does_not_abort_refresh(cli_env):
    # every FMP endpoint is 402, including profile, and one row needs the profile fallback
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    profile = _mock_sources(wiki_html=broken, fmp_status=402, profile_status=402)
    store, report = _run_refresh(cli_env)  # must not raise
    assert report.n_symbols > 500 and report.n_members_today > 0
    assert report.n_missing_group == 1  # unmapped, counted, not an abort
    assert report.gap_route == "wikipedia-derived"
    assert profile.call_count == 1  # one 402 ends the profile calls for BOTH cohorts
    assert report.n_unclassified == len(_historical_only(store)) - 5  # 5 mapped renames inherit
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
    assert "wikipedia-derived-bounded=28" in result.output  # 33 less the 5 mapped renames


@respx.mock
def test_fmp_call_count_bounded_when_many_profile_fallbacks(cli_env):
    # make >50 current members need the profile fallback; calls must still be <= 60 (AC6)
    broken = WIKI_HTML
    for sub in ("Semiconductors", "Application Software", "Health Care Equipment",
                "Regional Banks", "Systems Software"):
        broken = broken.replace(f"<td>{sub}</td>", "<td>Quantum Widgets</td>")
    profile = _mock_sources(wiki_html=broken, profile=[])
    store, report = _run_refresh(cli_env)
    assert report.n_missing_group > 50
    assert profile.call_count == 50
    assert _fmp_calls() <= 60
    # current members are classified first: every profile call was for a current member
    asked = {c.request.url.params["symbol"] for c in profile.calls}
    assert asked <= set(_current_symbols())
    assert report.n_unclassified == len(_historical_only(store)) - 5


@respx.mock
def test_bounded_removals_over_limit_is_a_stop(cli_env):
    n_base = 28  # 33 hanshof-only departures less the 5 mapped renames (AMD-0014)
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


# ---------------------------------------------------------------- AMD-0014 renames
H = date(2025, 8, 23)  # a Saturday: the last snapshot of a mini hanshof
AS_OF = date(2025, 12, 31)


def _mini_hanshof() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [date(2024, 1, 2), H],
            "symbols": [["AAA", "GONE", "OLDX"], ["AAA", "GONE", "OLDX"]],
        }
    )


def _mini_current() -> pl.DataFrame:
    # NEWX is OLDX renamed: it carries the company's ORIGINAL `Date added` (before H)
    return pl.DataFrame(
        {"symbol": ["AAA", "NEWX"], "date_added": [date(2010, 1, 4), date(2010, 1, 4)]},
        schema={"symbol": pl.String, "date_added": pl.Date},
    )


def _members_on(df: pl.DataFrame, d: date) -> set[str]:
    sub = df.filter(
        (pl.col("start_date") <= d) & (pl.col("end_date").is_null() | (pl.col("end_date") >= d))
    )
    return set(sub["symbol"].to_list())


def _trading_days(first: date, last: date):
    d = first
    while d <= last:
        if is_trading_day(d):
            yield d
        d += timedelta(days=1)


def test_rename_preserves_continuity():
    eff = date(2025, 10, 15)  # a Wednesday
    df = build_membership(
        _mini_hanshof(),
        _mini_current(),
        None,
        start=date(2015, 1, 1),
        renames=[Rename("OLDX", "NEWX", eff)],
    )
    assert _intervals(df, "OLDX") == [(date(2024, 1, 2), date(2025, 10, 14), "rename-mapped")]
    assert _intervals(df, "NEWX") == [(eff, None, "rename-mapped")]
    before, day, after = date(2025, 10, 14), eff, date(2025, 10, 16)
    assert {"OLDX", "NEWX"} & _members_on(df, before) == {"OLDX"}
    assert {"OLDX", "NEWX"} & _members_on(df, day) == {"NEWX"}
    assert {"OLDX", "NEWX"} & _members_on(df, after) == {"NEWX"}
    # no trading day since the company joined where neither ticker is a member, none where both
    for d in _trading_days(date(2024, 1, 2), AS_OF):
        assert len({"OLDX", "NEWX"} & _members_on(df, d)) == 1, d
    # the old ticker did not leave the index: it is not a bounded removal; a true departure is
    bounded = set(df.filter(pl.col("source") == "wikipedia-derived-bounded")["symbol"].to_list())
    assert "OLDX" not in bounded and bounded == {"GONE"}
    assert _intervals(df, "AAA") == [(date(2024, 1, 2), None, "hanshof")]
    assert df.select(["symbol", "start_date"]).is_duplicated().sum() == 0
    # the new ticker gets no derived-exact row in addition
    new_sources = df.filter(pl.col("symbol") == "NEWX")["source"].to_list()
    assert "wikipedia-derived-exact" not in new_sources


def test_rename_unknown_effective_is_bounded_not_added():
    df = build_membership(
        _mini_hanshof(),
        _mini_current(),
        None,
        start=date(2015, 1, 1),
        renames=[Rename("OLDX", "NEWX", None)],
    )
    nxt = next_trading_day(H)
    assert nxt == date(2025, 8, 25)
    assert _intervals(df, "OLDX") == [(date(2024, 1, 2), H, "rename-bounded")]
    assert _intervals(df, "NEWX") == [(nxt, None, "rename-bounded")]
    # exactly one of the pair is a member on EVERY trading day across H: the union has no hole
    for d in _trading_days(date(2024, 1, 2), AS_OF):
        assert len({"OLDX", "NEWX"} & _members_on(df, d)) == 1, d
    assert {"OLDX", "NEWX"} & _members_on(df, date(2025, 8, 22)) == {"OLDX"}
    assert {"OLDX", "NEWX"} & _members_on(df, H) == {"OLDX"}
    assert {"OLDX", "NEWX"} & _members_on(df, nxt) == {"NEWX"}
    # the rejected "addition" model would leave NEWX without a row before H+1 AND OLDX bounded
    assert "OLDX" not in set(
        df.filter(pl.col("source") == "wikipedia-derived-bounded")["symbol"].to_list()
    )


def test_rename_already_covered_by_change_rows_is_not_double_counted():
    # route (a)/(b): explicit rows already remove OLDX and add NEWX; the map must not touch them
    changes = pl.DataFrame(
        {
            "date": [date(2025, 10, 15), date(2025, 10, 15)],
            "symbol": ["OLDX", "NEWX"],
            "action": ["removed", "added"],
            "reason": ["rename", "rename"],
        },
        schema={"date": pl.Date, "symbol": pl.String, "action": pl.String, "reason": pl.String},
    )
    df = build_membership(
        _mini_hanshof(),
        None,
        changes,
        start=date(2015, 1, 1),
        renames=[Rename("OLDX", "NEWX", None)],
        current_symbols={"AAA", "NEWX"},
    )
    assert _intervals(df, "OLDX") == [(date(2024, 1, 2), date(2025, 10, 14), "hanshof+fmp")]
    assert _intervals(df, "NEWX") == [(date(2025, 10, 15), None, "fmp")]
    assert not {"rename-mapped", "rename-bounded"} & set(df["source"].to_list())
    # and where the change rows do NOT cover the pair, the map fills it in routes (a)/(b) too
    none = changes.clear()
    df2 = build_membership(
        _mini_hanshof(), None, none, start=date(2015, 1, 1),
        renames=[Rename("OLDX", "NEWX", None)], current_symbols={"AAA", "NEWX"},
    )
    assert _intervals(df2, "NEWX") == [(date(2025, 8, 25), None, "rename-bounded")]


def test_renames_loader_validates(tmp_path):
    assert load_renames(tmp_path) == []  # absent file = empty map
    shipped = load_renames(CONFIG)
    assert [(r.old, r.new, r.effective) for r in shipped] == [
        ("BK", "BNY", None), ("FI", "FISV", None), ("MMC", "MRSH", None),
        ("PSKY", "SKYD", None), ("EQR", "VMRK", None),
    ]
    f = tmp_path / "ticker_renames.yaml"
    f.write_text("renames:\n  - {old: AAA, new: BBB, effective: 2025-10-15}\n", encoding="utf-8")
    assert load_renames(tmp_path) == [Rename("AAA", "BBB", date(2025, 10, 15))]
    for bad in (
        "renames:\n  - {old: AAA, new: BBB}\n",  # effective missing
        "renames:\n  - {old: aaa, new: BBB, effective: null}\n",  # not a canonical symbol
        "renames:\n  - {old: AAA, new: AAA, effective: null}\n",
        "renames:\n  - {old: AAA, new: BBB, effective: soon}\n",
        "renames:\n  - {old: AAA, new: BBB, effective: null}\n"
        "  - {old: AAA, new: CCC, effective: null}\n",  # old repeated
        "renames: AAA\n",
        "- AAA\n",
    ):
        f.write_text(bad, encoding="utf-8")
        with pytest.raises(Exception, match="ticker_renames.yaml"):
            load_renames(tmp_path)


@respx.mock
def test_no_current_member_without_row(cli_env):
    _mock_sources(fmp_status=402)  # route (c): the live shape in which renames bite
    store, report = _run_refresh(cli_env)
    current = fetch_wikipedia_constituents(_wiki_client())["symbol"].to_list()
    open_syms = set(
        store.read("SELECT symbol FROM membership WHERE end_date IS NULL")["symbol"].to_list()
    )
    assert not [s for s in current if s not in open_syms]  # every current symbol, an open row
    assert report.current_members_without_row == 0
    assert report.current_members_without_row_symbols == []
    assert report.n_current_table == len(current) == 503 == report.n_members_today
    assert {"BNY", "FISV", "MRSH", "SKYD", "VMRK"} <= open_syms
    assert report.rows_by_source["rename-bounded"] == 10  # 5 pairs x (old row + new row)
    assert "rename-mapped" not in report.rows_by_source
    # each renamed company is exactly one member on every trading day across H
    for old, new in (("BK", "BNY"), ("FI", "FISV"), ("MMC", "MRSH"), ("PSKY", "SKYD"),
                     ("EQR", "VMRK")):
        # (hanshof itself lists PSKY only from H - its own PARA->PSKY step is outside the map)
        days = [date(2025, 8, 25), date(2026, 10, 20)]
        if old != "PSKY":
            days.append(date(2025, 8, 22))
        for d in days:
            members = set(store.members_on(d))
            assert len({old, new} & members) == 1, (old, new, d)
        assert old in store.members_on(H) and new not in store.members_on(H)


@respx.mock
def test_missing_rename_map_fails_loudly(cli_env, tmp_path, monkeypatch):
    # the failure path: drop the map and the five renamed companies have no current row
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    for name in ("gics.yaml", "universe.yaml"):
        shutil.copy(CONFIG / name, cfg / name)
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(cfg))
    _mock_sources(fmp_status=402)
    with pytest.raises(MembershipInvariantError) as exc:
        _run_refresh(cli_env)
    for sym in ("BNY", "FISV", "MRSH", "SKYD", "VMRK"):
        assert sym in str(exc.value)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 1
    assert "BNY" in result.output and "FISV" in result.output
    assert "exactly one open membership row" in result.output
    store = Store(cli_env)
    assert store.read("SELECT count(*) AS n FROM membership")["n"][0] == 0  # nothing persisted
    logged = store.read("SELECT status FROM ingest_log WHERE source = ?", ["universe"])
    assert logged["status"].to_list() == ["failed"]
    # AMD-0015 2A: the invariant does not depend on --date; a back-dated run (inside the
    # 7-day window) with the map dropped fails too, naming the symbols (AC9)
    respx.reset()
    _mock_sources(fmp_status=402)
    back = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-14"])
    assert back.exit_code == 1
    for sym in ("BNY", "FISV", "MRSH", "SKYD", "VMRK"):
        assert sym in back.output
    assert "exactly one open membership row" in back.output
    assert store.read("SELECT count(*) AS n FROM membership")["n"][0] == 0


@respx.mock
def test_back_dated_run_within_window_holds_the_invariant(cli_env):
    # AMD-0015 2A / AC9: the invariant is against the fetched table, whatever --date is
    _mock_sources(fmp_status=402)
    for as_of in (date(2026, 10, 14), date(2026, 10, 13)):  # 6 and exactly 7 days back
        store, report = _run_refresh(cli_env, as_of=as_of)
        assert report.current_members_without_row == 0
        assert report.current_members_without_row_symbols == []
        assert report.n_current_table == 503 == report.n_members_today
        open_syms = set(
            store.read("SELECT symbol FROM membership WHERE end_date IS NULL")["symbol"].to_list()
        )
        assert set(_current_symbols()) <= open_syms
        assert {"BNY", "FISV", "MRSH", "SKYD", "VMRK"} <= set(store.members_on(as_of))
        assert not {"BK", "FI", "MMC", "PSKY", "EQR"} & set(store.members_on(as_of))
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-14"])
    assert result.exit_code == 0, result.output
    assert "current members without row: 0" in result.output


def _current_rows(*pairs):
    return [{"symbol": s_, "date_added": d} for s_, d in pairs]


def test_open_row_invariant_is_a_plain_open_interval_test():
    # AMD-0015 2A: every current-table symbol has exactly one row with end_date IS NULL;
    # there is no as_of in the rule
    hanshof = pl.DataFrame({"date": [date(2024, 1, 2)], "symbols": [["AAA", "BBB"]]})
    m = build_membership(hanshof, None, _no_changes())
    cur = _current_rows(("AAA", date(2010, 1, 4)), ("BBB", date(2010, 1, 4)))
    assert current_members_without_open_row(m, cur) == []
    # a current symbol with no row at all, however old its Date added: named
    cur2 = cur + _current_rows(("CCC", date(2010, 1, 4)))
    assert current_members_without_open_row(m, cur2) == ["CCC"]
    # a symbol whose only interval is closed has no open row: named
    closed = pl.DataFrame(
        {"symbol": ["AAA", "BBB"], "start_date": [date(2024, 1, 2)] * 2,
         "end_date": [None, date(2024, 3, 1)], "source": ["hanshof", "hanshof"]},
        schema={"symbol": pl.String, "start_date": pl.Date, "end_date": pl.Date,
                "source": pl.String},
    )
    assert current_members_without_open_row(closed, cur) == ["BBB"]
    # two open rows is not "exactly one": named
    twice = pl.concat([m, m.filter(pl.col("symbol") == "AAA").with_columns(
        start_date=pl.lit(date(2024, 2, 1)))])
    assert current_members_without_open_row(twice, cur) == ["AAA"]
    # a symbol added after any run date is still named: no exemption exists
    late = _current_rows(("AAA", date(2010, 1, 4)), ("LATE", date(2030, 1, 1)))
    assert current_members_without_open_row(m, late) == ["LATE"]


def test_unmapped_hanshof_internal_rename_is_named():
    # PARA->PSKY-style step inside hanshof, not in the map: the later ticker has no open row
    hanshof = pl.DataFrame({"date": [date(2024, 1, 2)], "symbols": [["AAA", "PARA"]]})
    m = build_membership(hanshof, None, _no_changes())
    cur = _current_rows(("AAA", date(2010, 1, 4)), ("SKYD", date(1994, 9, 30)))
    assert current_members_without_open_row(m, cur) == ["SKYD"]


@respx.mock
def test_known_effective_in_the_future_fails_loudly(cli_env, tmp_path, monkeypatch):
    # AMD-0015 2A: a mapped rename that has not happened yet leaves the new ticker with no open
    # row, so the unconditional invariant fails and names it; nothing is written
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    for name in ("gics.yaml", "universe.yaml"):
        shutil.copy(CONFIG / name, cfg / name)
    text = (CONFIG / "ticker_renames.yaml").read_text().replace(
        "{old: BK, new: BNY, effective: null}", "{old: BK, new: BNY, effective: 2026-11-02}"
    )
    assert "2026-11-02" in text
    (cfg / "ticker_renames.yaml").write_text(text)
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(cfg))
    _mock_sources(fmp_status=402)
    with pytest.raises(MembershipInvariantError, match="BNY"):
        _run_refresh(cli_env, as_of=date(2026, 10, 20))
    assert Store(cli_env).read("SELECT count(*) AS n FROM membership")["n"][0] == 0
    # once the effective date has passed (the run date moves on) the same map passes
    monkeypatch.setattr("argus.data.universe._today_utc", lambda: date(2026, 11, 3))
    store, report = _run_refresh(cli_env, as_of=date(2026, 11, 3))
    assert report.current_members_without_row == 0
    assert store.members_on(date(2026, 11, 2)).count("BNY") == 1
    assert "BK" not in store.members_on(date(2026, 11, 2))
    assert "BK" in store.members_on(date(2026, 10, 30))


@respx.mock
def test_cli_prints_invariant_fields(cli_env):
    _mock_sources(fmp_status=402)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 0, result.output
    assert "current table symbols: 503" in result.output
    assert "unclassified historical symbols:" in result.output
    assert "current members without row: 0" in result.output
    assert "members on 2026-10-20: 503" in result.output
    assert "rename-bounded=10" in result.output


# ---------------------------------------------------------------- AC10 (AMD-0015 2A)
def test_check_refresh_date_window():
    check_refresh_date(date(2026, 10, 20))  # today
    check_refresh_date(date(2026, 10, 13))  # exactly 7 days
    check_refresh_date(date(2026, 11, 5))  # future: unchanged behaviour
    with pytest.raises(BackDatedRefreshError, match="no historical snapshot"):
        check_refresh_date(date(2026, 10, 12))  # 8 days


@respx.mock
def test_back_dated_refresh_is_refused_and_writes_nothing(cli_env):
    # first a normal run so the store has real contents to compare against
    _mock_sources(fmp_status=402)
    ok = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert ok.exit_code == 0, ok.output
    store = Store(cli_env)
    before = _counts(store)
    assert all(n > 0 for n in before.values())
    respx.reset()
    _mock_sources(fmp_status=402)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-09-20"])  # 30 days
    assert result.exit_code == 2, result.output
    assert "no historical snapshot" in result.output
    assert _counts(store) == before  # symbols, membership and ingest_log all unchanged
    assert len(respx.calls) == 0  # decided before any fetch
    # the 8th day back is refused, the 7th is not
    assert runner.invoke(app, ["universe", "refresh", "--date", "2026-10-12"]).exit_code == 2
    respx.reset()
    _mock_sources(fmp_status=402)
    assert runner.invoke(app, ["universe", "refresh", "--date", "2026-10-13"]).exit_code == 0


@respx.mock
def test_refused_refresh_does_not_even_create_the_store(cli_env):
    _mock_sources(fmp_status=402)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2025-01-01"])
    assert result.exit_code == 2
    assert not cli_env.exists()  # no Store opened or initialised
    assert len(respx.calls) == 0


@respx.mock
def test_refresh_function_refuses_back_dated_too(cli_env):
    _mock_sources(fmp_status=402)
    store = Store(cli_env)
    with httpx.Client() as http, pytest.raises(BackDatedRefreshError):
        refresh(store, get_settings(), http, as_of=date(2026, 9, 1))
    assert not cli_env.exists()


@respx.mock
def test_today_and_last_trading_day_succeed(cli_env):
    last_td = previous_trading_day(date(2026, 10, 20))
    assert last_td == date(2026, 10, 19)
    for arg in ("2026-10-20", last_td.isoformat()):
        respx.reset()
        _mock_sources(fmp_status=402)
        result = runner.invoke(app, ["universe", "refresh", "--date", arg])
        assert result.exit_code == 0, result.output
    respx.reset()
    _mock_sources(fmp_status=402)
    default = runner.invoke(app, ["universe", "refresh"])  # no --date = today (pinned)
    assert default.exit_code == 0, default.output
    assert "members on 2026-10-20: 503" in default.output


# ---------------------------------------------------------------- F1: recent changes, back-dated
RECENT = date(2026, 10, 20)  # the pinned today: after both back-dated run dates below
RECENT_ADD, RECENT_DROP = "ZNEW", "ZBRA"  # ZBRA: a hanshof@H member that leaves the index


def _recent_change_sources(*, fmp: bool):
    """Wikipedia/FMP-current with ZNEW added and ZBRA removed on RECENT. `fmp` selects the
    FMP-changes route (history carries both events) vs the derived route (page only)."""
    html = WIKI_HTML
    row = re.search(r"<tr>\s*<td><a href=\"#\">ZBRA</a></td>.*?</tr>", html, re.S)
    assert row
    new_row = (
        f'<tr>\n<td><a href="#">{RECENT_ADD}</a></td>\n<td><a href="#">New Co</a></td>\n'
        "<td>Financials</td>\n<td>Investment Banking &amp; Brokerage</td>\n"
        f"<td>{RECENT.isoformat()}</td></tr>"
    )
    html = html.replace(row.group(0), new_row)
    current = [r for r in CURRENT if r["symbol"] != RECENT_DROP] + [
        {
            "symbol": RECENT_ADD,
            "name": "New Co",
            "sector": "Financials",
            "subSector": "Investment Banking & Brokerage",
            "dateFirstAdded": RECENT.isoformat(),
        }
    ]
    history = COMPLETE_HISTORY + [
        {
            "date": RECENT.isoformat(),
            "symbol": RECENT_ADD,
            "removedTicker": RECENT_DROP,
            "reason": "fixture",
        }
    ]
    return html, history, current


def _page_changes_table() -> str:
    """The changes table (route b) completed like test_route_b_... plus the RECENT events."""
    rows = "".join(
        f'<tr><td>{d.isoformat()}</td><td><a href="#">{sym}</a></td><td>x</td><td></td><td></td>'
        "<td>fixture completion</td></tr>"
        for sym, d in EXTRA_ADDITIONS
    ) + "".join(
        f"<tr><td>2025-10-01</td><td></td><td></td><td>{sym}</td><td>x</td><td>fixture</td></tr>"
        for sym in EXTRA_REMOVALS
    )
    rows += (
        f'<tr><td>{RECENT.isoformat()}</td><td><a href="#">{RECENT_ADD}</a></td><td>New Co</td>'
        f"<td>{RECENT_DROP}</td><td>x</td><td>fixture</td></tr>"
    )
    return CHANGES_TABLE.replace("</table>", rows + "</table>")


def _assert_recent_change_invariants(store: Store, today=date(2026, 10, 20)):
    syms = _current_symbols_of(store)
    assert RECENT_ADD in syms and RECENT_DROP not in syms
    open_syms = set(
        store.read("SELECT symbol FROM membership WHERE end_date IS NULL")["symbol"].to_list()
    )
    assert open_syms >= syms and RECENT_ADD in open_syms and RECENT_DROP not in open_syms
    assert set(store.members_on(today)) == syms  # equals the fetched table, as a set


def _current_symbols_of(store: Store) -> set[str]:
    wiki_syms = set(_current_symbols())
    return (wiki_syms - {RECENT_DROP}) | {RECENT_ADD}


@respx.mock
@pytest.mark.parametrize("route", ["derived", "fmp-changes", "wikipedia-changes"])
@pytest.mark.parametrize("arg", ["2026-10-19", "2026-10-17"])  # last trading day; 3 days back
def test_back_dated_run_with_recent_add_and_removal_succeeds(cli_env, route, arg):
    fmp = route == "fmp-changes"
    html, history, current = _recent_change_sources(fmp=fmp)
    if route == "wikipedia-changes":  # route (b): FMP 402, the page's own changes table
        html = html.replace("</body>", _page_changes_table() + "</body>")
    _mock_sources(
        wiki_html=html, fmp_status=200 if fmp else 402, history=history, current=current
    )
    result = runner.invoke(app, ["universe", "refresh", "--date", arg])
    assert result.exit_code == 0, result.output
    assert "current members without row: 0" in result.output
    assert "current table symbols: 503" in result.output
    store = Store(cli_env)
    _assert_recent_change_invariants(store)
    rows = store.read(
        "SELECT * FROM membership WHERE symbol IN (?, ?)", [RECENT_ADD, RECENT_DROP]
    )
    by = {
        r["symbol"]: (r["start_date"], r["end_date"], r["source"])
        for r in rows.iter_rows(named=True)
    }
    if route == "wikipedia-changes":
        assert by[RECENT_ADD] == (RECENT, None, "wikipedia-changes")
        assert by[RECENT_DROP][1] == date(2026, 10, 19)
        assert "membership gap route: wikipedia-changes" in result.output
    elif fmp:
        assert by[RECENT_ADD] == (RECENT, None, "fmp")
        assert by[RECENT_DROP][1] == date(2026, 10, 19)  # the trading day before the removal
        assert "membership gap route: fmp" in result.output
    else:
        assert by[RECENT_ADD] == (RECENT, None, "wikipedia-derived-exact")
        assert by[RECENT_DROP][1] == date(2025, 8, 23)  # bounded at H
    # the report's "members on <date>" line is the --date's own membership: ZBRA is still a
    # member then on routes (a)/(b) (closes 10-19), already bounded out on the derived route;
    # ZNEW is not a member yet
    assert f"members on {arg}: {502 if route == 'derived' else 503}" in result.output
    # the Python API agrees
    respx.reset()
    _mock_sources(
        wiki_html=html, fmp_status=200 if fmp else 402, history=history, current=current
    )
    store2, report = _run_refresh(cli_env, as_of=date.fromisoformat(arg))
    assert report.n_members_today == report.n_current_table == 503
    assert report.current_members_without_row == 0


@respx.mock
def test_back_dated_dropped_rename_map_names_only_the_renames(cli_env, tmp_path, monkeypatch):
    # FMP-200 route, a recent add in the window, rename map dropped: still exit 1, nothing
    # written, and the message names the five renamed tickers - NOT the legitimate recent add
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    for name in ("gics.yaml", "universe.yaml"):
        shutil.copy(CONFIG / name, cfg / name)
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(cfg))
    html, history, current = _recent_change_sources(fmp=True)
    _mock_sources(wiki_html=html, history=history, current=current)
    for arg in ("2026-10-19", "2026-10-17"):
        result = runner.invoke(app, ["universe", "refresh", "--date", arg])
        assert result.exit_code == 1, result.output
        for sym in ("BNY", "FISV", "MRSH", "SKYD", "VMRK"):
            assert sym in result.output
        assert RECENT_ADD not in result.output
        assert "exactly one open membership row" in result.output
        store = Store(cli_env)
        assert store.read("SELECT count(*) AS n FROM membership")["n"][0] == 0


def test_members_must_equal_the_table_as_sets_not_counts():
    # same size, different symbols: a count comparison would pass this
    _require_members_equal_table({"A", "B"}, {"A", "B"}, date(2026, 10, 20))
    with pytest.raises(MembershipInvariantError, match="C"):
        _require_members_equal_table({"A", "B"}, {"A", "C"}, date(2026, 10, 20))


# ---------------------------------------------------------------- AMD-0016 2C classification
RENAMED = {"BK": "BNY", "FI": "FISV", "MMC": "MRSH", "PSKY": "SKYD", "EQR": "VMRK"}


@respx.mock
def test_symbols_covers_every_membership_symbol(cli_env):
    _mock_sources(fmp_status=402, profile_status=402)
    store, report = _run_refresh(cli_env)
    missing = store.read(
        "SELECT DISTINCT symbol FROM membership WHERE symbol NOT IN (SELECT symbol FROM symbols)"
    )
    assert missing.height == 0
    hist = _historical_only(store)
    assert len(hist) > 200
    active = store.read(
        "SELECT symbol, active FROM symbols WHERE symbol IN (SELECT symbol FROM membership)"
    )
    flags = dict(zip(active["symbol"].to_list(), active["active"].to_list(), strict=True))
    assert all(flags[s_] is False for s_ in hist)  # historical-only: active=false
    assert all(flags[s_] is True for s_ in _current_symbols())  # current stay active
    assert all(is_valid(s_) for s_ in store.read("SELECT symbol FROM symbols")["symbol"].to_list())
    # re-running keeps the same states (the deactivation pass leaves historical rows alone)
    store2, _ = _run_refresh(cli_env)
    again = store2.read(
        "SELECT symbol, active FROM symbols WHERE symbol IN (SELECT symbol FROM membership)"
    )
    assert dict(zip(again["symbol"].to_list(), again["active"].to_list(), strict=True)) == flags
    assert report.n_symbols == store.read("SELECT count(*) AS n FROM symbols")["n"][0]


@respx.mock
def test_mapped_old_tickers_take_the_new_tickers_group(cli_env):
    # even with profile unavailable: a rename is the same company
    _mock_sources(fmp_status=402, profile_status=402)
    store, report = _run_refresh(cli_env)
    rows = {
        r["symbol"]: (r["gics_sector"], r["gics_industry_group"], r["active"])
        for r in store.read("SELECT * FROM symbols").iter_rows(named=True)
    }
    for old, new in RENAMED.items():
        assert rows[new][1] and rows[new][0], new
        assert rows[old][:2] == rows[new][:2], (old, new)
        assert rows[old][2] is False and rows[new][2] is True
    # all the others are NULL and counted; the five renamed are not
    hist = _historical_only(store)
    assert report.n_unclassified == len(hist) - len(RENAMED)
    nulls = store.read(
        "SELECT count(*) AS n FROM symbols WHERE NOT active AND gics_industry_group IS NULL"
    )["n"][0]
    assert nulls == report.n_unclassified


@respx.mock
def test_historical_only_symbol_classified_from_profile_200(cli_env):
    profile = _mock_sources(
        fmp_status=402, profile=[{"symbol": "X", "industry": "Semiconductors"}]
    )
    # fmp_status only 402s the non-profile endpoints; profile answers 200
    store, report = _run_refresh(cli_env)
    group = "Semiconductors & Semiconductor Equipment"
    got = store.read("SELECT * FROM symbols WHERE symbol = ?", ["AAL"])  # first historical-only
    assert got["gics_industry_group"][0] == group and got["active"][0] is False
    assert got["gics_sector"][0] == "Information Technology"
    assert profile.call_count == 50  # the shared cap, spent on historical-only symbols
    hist = _historical_only(store)
    assert report.n_unclassified == len(hist) - len(RENAMED) - 50
    assert report.n_missing_group == 0 and _fmp_calls() <= 60


@respx.mock
def test_historical_profile_402_is_not_an_error_and_is_counted(cli_env):
    profile = _mock_sources(fmp_status=402, profile_status=402)
    result = runner.invoke(app, ["universe", "refresh", "--date", "2026-10-20"])
    assert result.exit_code == 0, result.output  # n_unclassified never sets an exit code
    assert profile.call_count == 1  # first 402 ends profile calls
    store = Store(cli_env)
    hist = _historical_only(store)
    assert f"unclassified historical symbols: {len(hist) - len(RENAMED)}" in result.output
    aal = store.read("SELECT * FROM symbols WHERE symbol = ?", ["AAL"])
    assert aal["gics_industry_group"][0] is None and aal["active"][0] is False
    assert "missing industry group: 0" in result.output  # current-member rule unchanged
    logged = store.read("SELECT status FROM ingest_log WHERE source = ?", ["universe"])
    assert logged["status"].to_list() == ["ok"]


@respx.mock
def test_current_members_are_classified_before_historical_ones(cli_env):
    # one current member needs the profile fallback; profile answers 200 for everyone. If the
    # historical-only symbols (a lot more than the cap) were classified first they would eat the
    # whole cap and the current member would be left without a group.
    broken = WIKI_HTML.replace("<td>Semiconductors</td>", "<td>Quantum Widgets</td>", 1)
    profile = _mock_sources(
        wiki_html=broken, fmp_status=402, profile=[{"symbol": "X", "industry": "Semiconductors"}]
    )
    wiki = fetch_wikipedia_constituents(_wiki_client(broken))
    victim = wiki.filter(pl.col("gics_sub_industry") == "Quantum Widgets")["symbol"][0]
    store, report = _run_refresh(cli_env)
    assert profile.calls[0].request.url.params["symbol"] == victim  # asked first
    assert report.n_missing_group == 0
    row = store.read("SELECT * FROM symbols WHERE symbol = ?", [victim])
    assert row["gics_industry_group"][0] == "Semiconductors & Semiconductor Equipment"
    assert row["active"][0] is True
    assert profile.call_count == 50 and _fmp_calls() <= 60
    assert len(_historical_only(store)) > 200  # ~240 historical-only symbols, 50 calls
