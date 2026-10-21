"""WO-0008: IBKR reconciliation, IV storage, paper-port enforcement, flag-first sampling."""

from datetime import date, timedelta
from itertools import pairwise

import polars as pl
import pytest
from typer.testing import CliRunner

from argus.cli import app
from argus.commands import ibkr_cmds
from argus.data.providers import ibkr as ibkr_mod
from argus.data.providers.base import ProviderError
from argus.data.providers.ibkr import IBAsyncClient
from argus.data.reconcile import choose_sample, fetch_iv, reconcile_day
from argus.data.store import Store
from tests.fakes.fake_ib import FakeIBClient

runner = CliRunner()
ON = date(2026, 10, 16)
_BOTH = (
    ["ibkr", "reconcile", "--date", "2026-10-16"],
    ["ibkr", "iv", "--date", "2026-10-16"],
)
SYMS = ["AAPL", "BRK.B", "JPM", "MSFT", "XOM"]


def make_store(tmp_path) -> Store:
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path / "store", config_dir=config)
    store.init_schema()
    return store


def seed_bars(store: Store, df: pl.DataFrame, close: str = "ours_close", vol: str = "ours_volume"):
    store.write_bars(
        df.select(
            "symbol",
            "date",
            "open",
            "high",
            "low",
            pl.col(close).alias("close"),
            pl.col(vol).alias("volume"),
            pl.col(close).alias("adj_close"),
            pl.lit(1).alias("adj_version"),
        )
    )


@pytest.fixture
def store(tmp_path):
    return make_store(tmp_path)


@pytest.fixture
def fake():
    return FakeIBClient.from_fixtures()


def log_rows(store: Store) -> pl.DataFrame:
    return store.read("SELECT * FROM reconcile_log ORDER BY date, symbol, field")


# ---------------------------------------------------------------- sampling
def test_sample_rotates_deterministically():
    members = [f"S{i:03d}" for i in range(100)]
    d0 = date(2026, 10, 1)
    assert choose_sample(members, d0) == choose_sample(list(reversed(members)), d0)
    days = [d0 + timedelta(days=i) for i in range(5)]  # 5 x 20 = 100: exactly one wrap
    samples = [choose_sample(members, d) for d in days]
    assert all(len(s) == 20 for s in samples)
    for a, b in pairwise(samples):
        assert not set(a) & set(b)
    assert set().union(*samples) == set(members)
    # wrap: the sixth day starts the cycle again
    assert set(choose_sample(members, days[0] + timedelta(days=5))) == set(samples[0])


def test_priority_symbols_are_sampled_first_and_rotation_unchanged():
    members = [f"S{i:03d}" for i in range(100)]
    d = date(2026, 10, 1)
    plain = choose_sample(members, d)
    flagged = [m for m in members if m not in plain][:3]
    out = choose_sample(members, d, priority=[*flagged, "NOTAMEMBER"])
    assert out[:3] == flagged
    assert len(out) == 20 and len(set(out)) == 20
    assert set(out[3:]) <= set(plain) | set(members)
    assert set(plain[:17]) <= set(out)  # the rotation fills the remainder from the same offset
    # the next day is unaffected by today's priority: coverage over time is preserved
    assert choose_sample(members, d + timedelta(days=1)) == choose_sample(
        members, d + timedelta(days=1), priority=None
    )
    # a priority symbol already inside the rotation window is not duplicated
    out2 = choose_sample(members, d, priority=[plain[5]])
    assert out2[0] == plain[5] and len(set(out2)) == 20


def test_priority_larger_than_n_is_truncated():
    members = [f"S{i:03d}" for i in range(30)]
    assert choose_sample(members, ON, n=3, priority=members[10:20]) == members[10:13]


# ---------------------------------------------------------------- reconcile
def test_breaches_detected_and_logged(store, fake):
    seed_bars(store, fake.trades)
    before = store.read_bars(None, date(2026, 1, 1), ON)
    report = reconcile_day(store, fake, ON, SYMS, lookback_days=10)
    assert report.n_symbols == 5 and report.n_fields == 100
    assert report.n_breaches == 2
    assert report.breach_rate == pytest.approx(0.02)
    breaches = report.rows.filter(pl.col("breach")).sort("symbol")
    assert breaches.select("symbol", "date", "field").rows() == [
        ("JPM", date(2026, 10, 14), "volume"),
        ("MSFT", date(2026, 10, 13), "close"),
    ]
    logged = log_rows(store)
    assert logged.height == 100
    assert logged.filter(pl.col("breach")).select("symbol", "field").sort("symbol").rows() == [
        ("JPM", "volume"),
        ("MSFT", "close"),
    ]
    msft = logged.filter((pl.col("symbol") == "MSFT") & (pl.col("date") == date(2026, 10, 13)))
    assert msft.filter(pl.col("field") == "close")["pct_diff"][0] == pytest.approx(1.0, abs=0.01)
    # reconciliation never modifies bars
    assert store.read_bars(None, date(2026, 1, 1), ON).equals(before)
    # idempotent
    reconcile_day(store, fake, ON, SYMS, lookback_days=10)
    assert log_rows(store).height == 100


def _one_symbol(theirs_close, theirs_vol, ours_close, ours_vol):
    d = date(2026, 10, 16)
    trades = pl.DataFrame(
        {"symbol": ["AAPL"], "date": [d], "open": [1.0], "high": [1.0], "low": [1.0],
         "close": [theirs_close], "volume": [theirs_vol]}
    )  # fmt: skip
    ours = trades.with_columns(
        pl.lit(ours_close).alias("oc"), pl.lit(ours_vol).alias("ov")
    )
    return trades, ours


@pytest.mark.parametrize(
    ("close_ratio", "vol_ratio", "close_breach", "vol_breach"),
    [
        (1.0009, 1.09, False, False),
        (0.9991, 0.91, False, False),
        (1.0011, 1.11, True, True),
        (0.9989, 0.89, True, True),
    ],
)
def test_tolerances_boundary(tmp_path, close_ratio, vol_ratio, close_breach, vol_breach):
    store = make_store(tmp_path)
    trades, ours = _one_symbol(100.0, 1_000_000.0, 100.0 * close_ratio, 1_000_000.0 * vol_ratio)
    seed_bars(store, ours, close="oc", vol="ov")
    report = reconcile_day(store, FakeIBClient(trades), ON, ["AAPL"], lookback_days=5)
    by_field = {r["field"]: r["breach"] for r in report.rows.iter_rows(named=True)}
    assert by_field == {"close": close_breach, "volume": vol_breach}


def test_missing_symbol_is_breach(store, fake):
    seed_bars(store, fake.trades)
    report = reconcile_day(store, fake, ON, ["AAPL", "ZZZZ"], lookback_days=10)
    miss = report.rows.filter(pl.col("field") == "missing")
    assert miss.select("symbol", "date", "breach").rows() == [("ZZZZ", ON, True)]
    assert report.n_breaches == 1 and report.n_fields == 21
    assert log_rows(store).filter(pl.col("field") == "missing").height == 1


def test_no_overlapping_dates_is_missing(store, fake):
    # we hold no bars for BRK.B at all: nothing comparable, so it is a missing breach
    seed_bars(store, fake.trades.filter(pl.col("symbol") != "BRK.B"))
    report = reconcile_day(store, fake, ON, ["BRK.B"], lookback_days=10)
    assert report.rows.select("field", "breach").rows() == [("missing", True)]


# ---------------------------------------------------------------- iv
def test_iv_upsert(store, fake):
    n = fetch_iv(store, fake, date(2026, 10, 16), ["SPY", "RSP", "XLK"])
    assert n == 15
    table = store.read("SELECT * FROM iv_daily ORDER BY symbol, date")
    assert table.height == 15 and set(table["source"]) == {"ibkr"}
    assert table["iv30"].null_count() == 0 and table["hv30"].null_count() == 0
    spy = table.filter((pl.col("symbol") == "SPY") & (pl.col("date") == date(2026, 10, 12)))
    assert spy.row(0, named=True)["iv30"] == pytest.approx(0.14)
    assert spy.row(0, named=True)["hv30"] == pytest.approx(0.11)
    assert fetch_iv(store, fake, date(2026, 10, 16), ["SPY", "RSP", "XLK"]) == 15
    assert store.read("SELECT count(*) AS n FROM iv_daily")["n"][0] == 15
    assert store.read("SELECT count(*) AS n FROM reconcile_log")["n"][0] == 0


# ---------------------------------------------------------------- CLI
def _cli_env(clean_env, tmp_path, port: str | None):
    store = make_store(tmp_path)
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    clean_env.setenv("ARGUS_CONFIG_DIR", str(tmp_path / "config"))
    if port is not None:
        clean_env.setenv("IB_PORT", port)
    return store


def test_cli_requires_port(clean_env, tmp_path):
    _cli_env(clean_env, tmp_path, None)
    for cmd in _BOTH:
        result = runner.invoke(app, cmd)
        assert result.exit_code == 2
        assert "ib_port" in result.output


@pytest.mark.parametrize("port", ["7496", "4001", "1234"])
def test_live_port_exits_2_without_opening_a_socket(clean_env, tmp_path, monkeypatch, port):
    _cli_env(clean_env, tmp_path, port)
    connects, builds = [], []
    monkeypatch.setattr(IBAsyncClient, "connect", lambda self: connects.append(1))
    monkeypatch.setattr(ibkr_cmds, "_make_client", lambda settings: builds.append(1))
    for cmd in _BOTH:
        result = runner.invoke(app, cmd)
        assert result.exit_code == 2
        assert port in result.output
    assert connects == [] and builds == []


@pytest.mark.parametrize("port", ["7497", "4002"])
def test_paper_ports_accepted(clean_env, tmp_path, monkeypatch, port):
    _cli_env(clean_env, tmp_path, port)
    fake = FakeIBClient.from_fixtures()
    monkeypatch.setattr(ibkr_cmds, "_make_client", lambda settings: fake)
    result = runner.invoke(app, ["ibkr", "reconcile", "--date", "2026-10-16"])
    assert result.exit_code == 0, result.output
    assert "symbols=0" in result.output
    assert fake.calls == [("connect",), ("disconnect",)]


def test_cli_iv_and_reconcile_end_to_end(clean_env, tmp_path, monkeypatch):
    store = _cli_env(clean_env, tmp_path, "4002")
    (tmp_path / "config" / "universe.yaml").write_text(
        "benchmarks: [SPY, RSP]\nsector_etfs:\n  Information Technology: XLK\n"
    )
    fake = FakeIBClient.from_fixtures()
    seed_bars(store, fake.trades)
    store.upsert(
        "membership",
        pl.DataFrame({"symbol": SYMS, "start_date": [date(2000, 1, 1)] * 5,
                      "end_date": [None] * 5, "source": ["t"] * 5},
                     schema_overrides={"end_date": pl.Date}),
        ["symbol", "start_date"],
    )  # fmt: skip
    monkeypatch.setattr(ibkr_cmds, "_make_client", lambda settings: fake)
    iv = runner.invoke(app, ["ibkr", "iv", "--date", "2026-10-16"])
    assert iv.exit_code == 0, iv.output
    assert "symbols=3 rows=15" in iv.output
    rec = runner.invoke(app, ["ibkr", "reconcile", "--date", "2026-10-16", "--sample", "5"])
    assert rec.exit_code == 0, rec.output
    assert "symbols=5" in rec.output and "breach:" in rec.output
    assert fake.connected is False


def test_cli_disconnects_on_provider_error(clean_env, tmp_path, monkeypatch):
    _cli_env(clean_env, tmp_path, "7497")

    class Boom(FakeIBClient):
        def connect(self):
            super().connect()
            raise ProviderError("boom")

    fake = Boom()
    monkeypatch.setattr(ibkr_cmds, "_make_client", lambda settings: fake)
    result = runner.invoke(app, ["ibkr", "iv", "--date", "2026-10-16"])
    assert result.exit_code in (1, 2)
    if result.exit_code == 1:
        assert fake.calls[-1] == ("disconnect",)


def test_cli_prioritises_unresolved_previous_session_flags(clean_env, tmp_path, monkeypatch):
    store = _cli_env(clean_env, tmp_path, "7497")
    fake = FakeIBClient.from_fixtures()
    seed_bars(store, fake.trades)
    members = [f"M{i:03d}" for i in range(60)]
    store.upsert(
        "membership",
        pl.DataFrame({"symbol": members, "start_date": [date(2000, 1, 1)] * len(members),
                      "end_date": [None] * len(members), "source": ["t"] * len(members)},
                     schema_overrides={"end_date": pl.Date}),
        ["symbol", "start_date"],
    )  # fmt: skip
    on = date(2026, 10, 16)
    plain = choose_sample(members, on)
    target = next(m for m in members if m not in plain)  # outside today's rotation window
    stale = next(m for m in members if m not in plain and m != target)
    con = store.connect()
    con.execute(
        "INSERT INTO bar_flags VALUES (?, DATE '2026-10-15', 'polygon', 'jump_unexplained', ''),"
        "(?, DATE '2026-10-14', 'polygon', 'jump_unexplained', '')",
        [target, stale],
    )
    con.close()
    assert ibkr_cmds._priority_symbols(store, members, on) == [target]
    seen = []

    def stop(store_, client, d, sample, **kw):
        seen.append(sample)
        raise ProviderError("stop")

    monkeypatch.setattr(ibkr_cmds, "reconcile_day", stop)
    monkeypatch.setattr(ibkr_cmds, "_make_client", lambda settings: fake)
    runner.invoke(app, ["ibkr", "reconcile", "--date", "2026-10-16"])
    assert seen and seen[0][0] == target and len(seen[0]) == 20
    # once reconciled (a close comparison logged for the flag day) the flag is resolved
    store.upsert(
        "reconcile_log",
        pl.DataFrame({"date": [date(2026, 10, 15)], "symbol": [target], "field": ["close"],
                      "ours": [1.0], "theirs": [1.0], "pct_diff": [0.0], "breach": [False]}),
        ["date", "symbol", "field"],
    )  # fmt: skip
    assert ibkr_cmds._priority_symbols(store, members, on) == []


# ------------------------------------------------------- IBAsyncClient (stubbed ib_async IB)
class StubBar:
    def __init__(self, d, c, v=100):
        self.date, self.open, self.high, self.low, self.close, self.volume = d, c, c, c, c, v


class StubIB:
    def __init__(self, bars=()):
        self.bars, self.connect_kwargs, self.history_kwargs, self.disconnected = bars, None, [], 0

    def connect(self, host, port, **kw):
        self.connect_kwargs = kw

    def disconnect(self):
        self.disconnected += 1

    def qualifyContracts(self, *contracts):  # noqa: N802
        return list(contracts)

    def reqHistoricalData(self, contract, **kw):  # noqa: N802
        self.history_kwargs.append((contract.symbol, kw))
        return list(self.bars)


def test_async_client_connects_read_only_and_requests_daily_rth():
    from datetime import UTC, datetime

    stub = StubIB(
        [StubBar(datetime(2026, 10, 15, 4, 0, tzinfo=UTC), 10.5), StubBar(date(2026, 10, 16), 11.0)]
    )
    client = IBAsyncClient("h", 1, 7, ib=stub)
    client.connect()
    assert stub.connect_kwargs == {"clientId": 7, "readonly": True}
    df = client.daily_bars("BRK.B", ON, 5, "TRADES")
    assert df["date"].to_list() == [date(2026, 10, 15), date(2026, 10, 16)]
    sym, kw = stub.history_kwargs[0]
    assert sym == "BRK B"
    assert kw["barSizeSetting"] == "1 day" and kw["useRTH"] is True and kw["formatDate"] == 2
    assert kw["whatToShow"] == "TRADES" and kw["durationStr"] == "5 D"
    series = client.daily_series("SPY", ON, 5, "HISTORICAL_VOLATILITY")
    assert series.columns == ["date", "value"] and series.height == 2
    client.disconnect()
    assert stub.disconnected == 1


def test_async_client_without_extra_raises_provider_error(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "ib_async", None)
    with pytest.raises(ProviderError, match=r"install extras: argus\[ibkr\]"):
        IBAsyncClient("h", 1, 7).connect()


def test_pacer_never_exceeds_50_per_window():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    pacer = ibkr_mod._HistoricalPacer(clock=lambda: now[0], sleep=sleep)
    for _ in range(50):
        pacer.acquire()
    assert slept == []
    pacer.acquire()  # the 51st waits for the first to leave the 600 s window
    assert slept == [pytest.approx(600.0)]
