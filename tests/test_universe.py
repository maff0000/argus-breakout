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
    WIKIPEDIA_URL,
    build_membership,
    fetch_wikipedia_constituents,
    load_hanshof_csv,
    map_industry_group,
    next_trading_day,
    previous_trading_day,
)

TESTS = Path(__file__).parent
FIX = TESTS / "fixtures"
CONFIG = TESTS.parent / "config"
WIKI_HTML = (FIX / "universe" / "wikipedia_sp500.html").read_text(encoding="utf-8")
HANSHOF_SAMPLE = FIX / "universe" / "hanshof_sample.csv"
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
    assert df.columns == ["symbol", "name", "gics_sector", "gics_sub_industry"]
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
    df = build_membership(hanshof, _no_changes(), start=date(2015, 1, 1))
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
    df = build_membership(snaps, _no_changes(), start=date(2015, 1, 1))
    # start clipped to 2015-01-01; BBB removed Tue 2016-01-19, MLK Monday => end Fri 01-15
    assert _intervals(df, "BBB")[0] == (date(2015, 1, 1), date(2016, 1, 15), "hanshof")
    assert _intervals(df, "BBB")[1][0] == date(2016, 6, 1)
    assert _intervals(df, "AAA") == [(date(2015, 1, 1), None, "hanshof")]
    # an interval that ended before `start` is dropped entirely
    snaps2 = pl.DataFrame(
        {"date": [date(2013, 1, 2), date(2014, 3, 3)], "symbols": [["OLD"], ["NEW"]]}
    )
    out = build_membership(snaps2, _no_changes(), start=date(2015, 1, 1))
    assert out["symbol"].to_list() == ["NEW"]


def test_fmp_fills_gap_after_hanshof(fmp_changes):
    hanshof = load_hanshof_csv(HANSHOF_SAMPLE)
    assert hanshof["date"].max() == date(2025, 8, 23)
    df = build_membership(hanshof, fmp_changes, start=date(2015, 1, 1))
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
    baseline = build_membership(hanshof, fmp_changes, start=date(2015, 1, 1))
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
    out = build_membership(hanshof, pl.concat([fmp_changes, stale]), start=date(2015, 1, 1))
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


def _mock_sources(wiki_html: str = WIKI_HTML, profile=None):
    respx.get(WIKIPEDIA_URL).mock(return_value=httpx.Response(200, text=wiki_html))
    respx.get(HANSHOF_URL).mock(
        return_value=httpx.Response(200, text=HANSHOF_SAMPLE.read_text(encoding="utf-8"))
    )
    respx.get(BASE_URL + "historical-sp500-constituent").mock(
        return_value=httpx.Response(200, json=HISTORICAL)
    )
    respx.get(BASE_URL + "sp500-constituent").mock(return_value=httpx.Response(200, json=CURRENT))
    return respx.get(BASE_URL + "profile").mock(
        return_value=httpx.Response(200, json=profile if profile is not None else [])
    )


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
