import json
import traceback
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
import structlog
from pydantic import SecretStr

from argus.data.providers.base import ProviderError
from argus.data.providers.fmp import BASE_URL, FMPClient, ProviderUnavailable
from argus.data.store import Store
from argus.logging import configure_logging

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"
KEY = "k3y-VALUE-0123456789"


@pytest.fixture(autouse=True)
def _reset_structlog():
    structlog.reset_defaults()  # configure_logging() binds the stdout of whichever test ran it
    yield
    structlog.reset_defaults()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "store")
    s.init_schema()
    return s


def _client(store, budget=200, **kw):
    return FMPClient(SecretStr(KEY), budget, store, retry_wait=0, **kw)


@respx.mock
def test_budget_enforced(store):
    route = respx.get(BASE_URL + "profile").mock(return_value=httpx.Response(200, json=[]))
    client = _client(store, budget=200)
    for _ in range(200):
        client.get("profile", {"symbol": "AAPL"})
    assert route.call_count == 200
    with pytest.raises(ProviderError, match="fmp daily budget exhausted"):
        client.get("profile", {"symbol": "AAPL"})
    assert route.call_count == 200  # the 201st call never left the process
    # the counter lives in the store, so a brand-new client is also refused
    with pytest.raises(ProviderError, match="fmp daily budget exhausted"):
        _client(store, budget=200).get("profile", {"symbol": "AAPL"})
    counted = store.read(
        "SELECT SUM(rows) AS n FROM ingest_log WHERE source = ?", ["fmp-budget"]
    )["n"][0]
    assert counted == 200


@respx.mock
def test_key_not_in_logs_or_errors(store, capsys):
    configure_logging("DEBUG")
    route = respx.get(BASE_URL + "profile").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError) as info:
        _client(store).get("profile", {"symbol": "AAPL"})
    assert route.call_count == 3  # retried 3x on 5xx
    # the key was really sent as a query parameter ...
    assert route.calls[0].request.url.params["apikey"] == KEY
    # ... and appears nowhere in what we raise or print
    rendered = "".join(traceback.format_exception(info.value))
    assert KEY not in str(info.value)
    assert KEY not in repr(info.value)
    assert KEY not in rendered
    assert "apikey" not in rendered
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert "fmp_retry" in captured.out  # something was logged, and it is key-free


@respx.mock
def test_transport_error_message_has_no_key(store):
    respx.get(BASE_URL + "profile").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ProviderError) as info:
        _client(store).get("profile", {"symbol": "AAPL"})
    assert KEY not in "".join(traceback.format_exception(info.value))


@respx.mock
def test_client_error_is_not_retried(store):
    route = respx.get(BASE_URL + "profile").mock(return_value=httpx.Response(404, text="no"))
    with pytest.raises(ProviderError, match="status 404"):
        _client(store).get("profile", {"symbol": "AAPL"})
    assert route.call_count == 1


@respx.mock
def test_retry_then_success(store):
    route = respx.get(BASE_URL + "profile").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=[{"symbol": "AAPL"}])]
    )
    assert _client(store).get("profile", {"symbol": "AAPL"}) == [{"symbol": "AAPL"}]
    assert route.call_count == 2


@respx.mock
def test_historical_sp500_changes_parses_fixture(store):
    body = json.loads((FIXTURES / "historical_sp500.json").read_text())
    respx.get(BASE_URL + "historical-sp500-constituent").mock(
        return_value=httpx.Response(200, json=body)
    )
    df = _client(store).historical_sp500_changes()
    assert df.columns == ["date", "symbol", "action", "reason"]
    assert df.schema["date"] == pl.Date
    assert set(df["action"].unique()) == {"added", "removed"}
    assert len(body) >= 20
    ibkr = df.filter(pl.col("symbol") == "IBKR")
    assert ibkr["date"].to_list() == [date(2025, 8, 28)]
    assert ibkr["action"].to_list() == ["added"]


@respx.mock
def test_current_sp500_and_profile(store):
    body = json.loads((FIXTURES / "sp500_constituent.json").read_text())
    respx.get(BASE_URL + "sp500-constituent").mock(return_value=httpx.Response(200, json=body))
    prof = respx.get(BASE_URL + "profile").mock(
        return_value=httpx.Response(200, json=[{"symbol": "BRK-B", "industry": "x"}])
    )
    client = _client(store)
    df = client.current_sp500()
    assert df.columns == ["symbol", "name", "sector", "sub_industry"]
    assert df.height >= 490
    assert client.profile("BRK.B")["industry"] == "x"
    assert prof.calls[0].request.url.params["symbol"] == "BRK.B"  # FMP uses the dot form


@pytest.mark.parametrize("status", [402, 403])
@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.historical_sp500_changes(),
        lambda c: c.current_sp500(),
        lambda c: c.profile("AAPL"),
    ],
)
@respx.mock
def test_402_403_raise_provider_unavailable_without_key(store, capsys, status, call):
    endpoint_routes = [
        respx.get(BASE_URL + p).mock(return_value=httpx.Response(status, text="plan"))
        for p in ("historical-sp500-constituent", "sp500-constituent", "profile")
    ]
    structlog.reset_defaults()
    configure_logging()
    client = _client(store)
    with pytest.raises(ProviderUnavailable) as err:
        call(client)
    assert isinstance(err.value, ProviderError)
    assert str(status) in str(err.value)
    blob = "".join(traceback.format_exception(err.value)) + capsys.readouterr().out
    assert KEY not in blob and "apikey" not in blob.lower()
    assert sum(r.call_count for r in endpoint_routes) == 1  # unavailable is not retried


@respx.mock
def test_other_4xx_and_5xx_are_not_unavailable(store):
    respx.get(BASE_URL + "profile").mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderError) as err:
        _client(store).profile("AAPL")
    assert not isinstance(err.value, ProviderUnavailable)
    respx.get(BASE_URL + "profile").mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderError) as err2:
        _client(store).profile("AAPL")
    assert not isinstance(err2.value, ProviderUnavailable)
