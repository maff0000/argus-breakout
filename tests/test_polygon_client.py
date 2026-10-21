import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
import structlog
from pydantic import SecretStr

from argus.data.providers import polygon as polygon_mod
from argus.data.providers.base import ProviderError
from argus.data.providers.polygon import PolygonClient
from argus.logging import configure_logging

FIX = Path(__file__).parent / "fixtures" / "polygon"
KEY = "unit-test-dummy"
BASE = "https://api.polygon.io"
D = date(2026, 10, 16)


def _fx(name: str) -> dict:
    return json.loads((FIX / name).read_text())


@pytest.fixture(autouse=True)
def _fresh_logging():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture
def client():
    c = PolygonClient(SecretStr(KEY), calls_per_minute=6000)
    yield c
    c.close()


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(polygon_mod.time, "sleep", lambda s: calls.append(s))
    return calls


@respx.mock
def test_grouped_daily_parses_and_filters(client):
    route = respx.get(f"{BASE}/v2/aggs/grouped/locale/us/market/stocks/2026-10-16").respond(
        json=_fx("grouped_daily_2026-10-16.json")
    )
    df = client.grouped_daily(D)
    assert df.columns == [
        "symbol", "date", "open", "high", "low", "close", "volume", "vwap", "transactions",
    ]
    assert df.height == 634  # 642 fixture rows - 8 junk tickers
    assert client.last_dropped == 8
    assert "BRK.B" in df["symbol"].to_list()
    assert {"ZZZ WS", "AB/CD", "abc", "TOOLONGTICKER1", "A..B"}.isdisjoint(df["symbol"].to_list())
    assert set(df["date"].to_list()) == {D}
    assert route.calls[0].request.url.params["adjusted"] == "true"
    assert route.calls[0].request.url.params["apiKey"] == KEY
    assert client.source == "polygon" and client.basis == "split"


@respx.mock
def test_grouped_daily_empty_is_empty_frame(client):
    respx.get(url__regex=r".*/grouped/.*").respond(
        json={"status": "OK", "resultsCount": 0, "queryCount": 0}
    )
    df = client.grouped_daily(D)
    assert df.is_empty() and "symbol" in df.columns


@respx.mock
def test_splits_pagination(client):
    route = respx.get(f"{BASE}/v3/reference/splits").mock(
        side_effect=[
            httpx.Response(200, json=_fx("splits_page1.json")),
            httpx.Response(200, json=_fx("splits_page2.json")),
        ]
    )
    df = client.splits(date(2026, 1, 1)).sort("symbol")
    assert df.height == 3
    ratios = dict(zip(df["symbol"], df["split_ratio"], strict=True))
    assert ratios == {"MAA": 4.0, "MAB": 0.1, "MAC": 3.0}
    assert df.columns == ["symbol", "date", "split_ratio"]
    assert route.call_count == 2
    second = route.calls[1].request.url
    assert second.params["cursor"] == "page2token"
    assert second.params["apiKey"] == KEY
    assert second.host == "api.polygon.io"


@respx.mock
def test_next_url_cannot_redirect_key_to_other_host(client):
    page = _fx("splits_page1.json")
    page["next_url"] = "https://evil.invalid/v3/reference/splits?cursor=x"
    route = respx.get(f"{BASE}/v3/reference/splits").mock(
        side_effect=[
            httpx.Response(200, json=page),
            httpx.Response(200, json=_fx("splits_page2.json")),
        ]
    )
    client.splits(date(2026, 1, 1))
    assert {c.request.url.host for c in route.calls} == {"api.polygon.io"}


@respx.mock
def test_dividends(client):
    respx.get(f"{BASE}/v3/reference/dividends").respond(json=_fx("dividends.json"))
    df = client.dividends(date(2026, 1, 1))
    assert df.columns == ["symbol", "date", "cash_dividend", "vendor_id"]
    assert df.height == 4
    row = df.filter(df["symbol"] == "MAA").row(0, named=True)
    assert row["date"] == date(2026, 3, 2) and row["cash_dividend"] == 0.25


@respx.mock
def test_vendor_id_carried_from_payload(client):
    """PGR 2026-01-02: two records, both dividend_type "CD", one ex-date (AMD-0027 2A).

    Fails if the id is not carried, or if dividend_type (identical here) stands in for it."""
    rec = {"ticker": "PGR", "ex_dividend_date": "2026-01-02", "dividend_type": "CD"}
    respx.get(f"{BASE}/v3/reference/dividends").respond(
        json={
            "status": "OK",
            "results": [
                {**rec, "cash_amount": 0.10, "frequency": 4, "id": "id-quarterly"},
                {**rec, "cash_amount": 13.50, "frequency": 1, "id": "id-special"},
            ],
        }
    )
    df = client.dividends(date(2026, 1, 1))
    assert df.height == 2
    assert sorted(df["vendor_id"].to_list()) == ["id-quarterly", "id-special"]
    assert sorted(df["cash_dividend"].to_list()) == [0.10, 13.50]


@respx.mock
def test_dividend_record_without_id_fails_loudly(client):
    respx.get(f"{BASE}/v3/reference/dividends").respond(
        json={"status": "OK", "results": [
            {"ticker": "PGR", "ex_dividend_date": "2026-01-02", "cash_amount": 0.10}]}
    )
    with pytest.raises(ProviderError, match="without an id"):
        client.dividends(date(2026, 1, 1))


@respx.mock
def test_429_retry_after(client, sleeps):
    route = respx.get(url__regex=r".*/grouped/.*").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=_fx("grouped_daily_2026-10-16.json")),
        ]
    )
    df = client.grouped_daily(D)
    assert df.height == 634
    assert route.call_count == 2
    assert sleeps == [7.0]


@respx.mock
def test_429_default_wait_and_give_up(client, sleeps):
    route = respx.get(url__regex=r".*/grouped/.*").respond(429)
    with pytest.raises(ProviderError):
        client.grouped_daily(D)
    assert route.call_count == 4  # first try + 3 retries
    assert sleeps == [60.0, 60.0, 60.0]


@respx.mock
def test_5xx_retried_three_times(client, sleeps):
    route = respx.get(url__regex=r".*/grouped/.*").respond(503)
    with pytest.raises(ProviderError):
        client.grouped_daily(D)
    assert route.call_count == 3
    assert len(sleeps) == 2 and sleeps[0] < sleeps[1]


@respx.mock
def test_4xx_not_retried(client, sleeps):
    route = respx.get(url__regex=r".*/grouped/.*").respond(403)
    with pytest.raises(ProviderError):
        client.grouped_daily(D)
    assert route.call_count == 1 and sleeps == []


@respx.mock
def test_key_not_leaked(client, sleeps, capsys):
    configure_logging("DEBUG")
    route = respx.get(url__regex=r".*/grouped/.*").respond(
        500, text=f"boom apiKey={KEY} {KEY}"
    )
    with pytest.raises(ProviderError) as info:
        client.grouped_daily(D)
    # the key really was sent (so the assertions below are meaningful) ...
    assert route.calls[0].request.url.params["apiKey"] == KEY
    # ... and appears nowhere in the error or the logs
    assert KEY not in str(info.value)
    assert KEY not in repr(info.value)
    out = capsys.readouterr()
    assert "polygon_request" in out.out  # logging was live, and carries no key
    assert KEY not in out.out and KEY not in out.err


@respx.mock
def test_key_not_leaked_on_transport_error(client, sleeps, capsys):
    configure_logging("DEBUG")
    respx.get(url__regex=r".*/grouped/.*").mock(
        side_effect=httpx.ConnectError(f"cannot connect https://x/?apiKey={KEY}")
    )
    with pytest.raises(ProviderError) as info:
        client.grouped_daily(D)
    assert KEY not in str(info.value)
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err


def test_empty_key_rejected():
    with pytest.raises(ProviderError):
        PolygonClient(SecretStr(""))
