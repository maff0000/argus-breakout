"""Polygon.io provider (PID 8.6, WO-0004): grouped-daily bars, splits, dividends.

The API key travels only as the `apiKey` query parameter inside this client. It is
never logged and is stripped from every error message raised from here.
"""

import time
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import polars as pl
import structlog
from pydantic import SecretStr
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from argus.data.providers.base import CANONICAL_BAR_COLUMNS, ProviderError, RateLimiter
from argus.data.tickers import normalize

DEFAULT_BASE_URL = "https://api.polygon.io"
_DEFAULT_RETRY_AFTER = 60.0
_MAX_429_RETRIES = 3
_MAX_PAGES = 1000
_TIMEOUT = 30.0

BAR_COLUMNS = [*CANONICAL_BAR_COLUMNS, "vwap", "transactions"]
_BAR_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "vwap": pl.Float64,
    "transactions": pl.Int64,
}
_SPLIT_SCHEMA = {"symbol": pl.String, "date": pl.Date, "split_ratio": pl.Float64}
_DIV_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "cash_dividend": pl.Float64,
    "vendor_id": pl.String,
    "declaration_date": pl.Date,
    "frequency": pl.Int64,
}

log = structlog.get_logger()


class _RateLimited(ProviderError):
    def __init__(self, retry_after: float) -> None:
        super().__init__("polygon rate limited (HTTP 429)")
        self.retry_after = retry_after


class _ServerError(ProviderError):
    pass


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


class PolygonClient:
    source = "polygon"
    basis = "split"  # adjusted=true is split-adjusted

    def __init__(
        self,
        api_key: SecretStr,
        calls_per_minute: int = 5,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._key = api_key.get_secret_value()
        if not self._key:
            raise ProviderError("polygon api key is empty")
        self._base_url = base_url.rstrip("/")
        self._limiter = RateLimiter(calls_per_minute)
        self._http = httpx.Client(timeout=_TIMEOUT)
        self.last_dropped: int = 0  # invalid tickers dropped by the latest grouped_daily

    # ------------------------------------------------------------------ plumbing
    def close(self) -> None:
        self._http.close()

    def _clean(self, text: str) -> str:
        return text.replace(self._key, "***REDACTED***")

    def _send(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """One rate-limited request. Raises _RateLimited / _ServerError / ProviderError."""
        self._limiter.acquire()
        query = {**params, "apiKey": self._key}
        try:
            resp = self._http.get(self._base_url + path, params=query)
        except httpx.HTTPError as exc:
            log.warning("polygon_transport_error", path=path, error=type(exc).__name__)
            raise _ServerError(f"polygon request failed: {type(exc).__name__}") from None
        status = resp.status_code
        log.info("polygon_request", path=path, status=status)
        if status == 429:
            try:
                wait = float(resp.headers.get("Retry-After", _DEFAULT_RETRY_AFTER))
            except ValueError:
                wait = _DEFAULT_RETRY_AFTER
            raise _RateLimited(wait)
        if status >= 500:
            raise _ServerError(f"polygon HTTP {status} for {path}")
        if status >= 400:
            raise ProviderError(f"polygon HTTP {status} for {path}")
        try:
            body = resp.json()
        except ValueError:
            raise ProviderError(f"polygon returned non-JSON for {path}") from None
        if not isinstance(body, dict):
            raise ProviderError(f"polygon returned unexpected payload for {path}")
        if str(body.get("status", "OK")).upper() == "ERROR":
            raise ProviderError(self._clean(f"polygon error for {path}: {body.get('error', '')}"))
        return body

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """Request with 429 handling (Retry-After, up to 3 retries) and 5xx backoff (3x)."""
        rate_retries = 0
        while True:
            try:
                for attempt in Retrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=1, max=30),
                    retry=retry_if_exception_type(_ServerError),
                    sleep=lambda s: time.sleep(s),
                    reraise=True,
                ):
                    with attempt:
                        return self._send(path, params)
            except _RateLimited as exc:
                if rate_retries >= _MAX_429_RETRIES:
                    raise ProviderError("polygon rate limit persisted after retries") from None
                rate_retries += 1
                log.warning("polygon_rate_limited", path=path, wait_s=exc.retry_after)
                time.sleep(exc.retry_after)

    def _paged(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_path, next_params = path, params
        for _ in range(_MAX_PAGES):
            body = self._get(next_path, next_params)
            rows.extend(r for r in body.get("results") or [] if isinstance(r, dict))
            nxt = body.get("next_url")
            if not nxt:
                return rows
            # Follow only the path+query of next_url against our own base URL, so the
            # key can never be sent to a host named by the response.
            parts = urlsplit(str(nxt))
            next_path = parts.path
            next_params = {k: v for k, v in parse_qsl(parts.query) if k != "apiKey"}
        raise ProviderError(f"polygon pagination exceeded {_MAX_PAGES} pages for {path}")

    def _norm(self, ticker: Any) -> str | None:
        try:
            return normalize(str(ticker), "polygon")
        except ValueError:
            return None

    # ------------------------------------------------------------------ endpoints
    def grouped_daily(self, d: date, adjusted: bool = True) -> pl.DataFrame:
        body = self._get(
            f"/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}",
            {"adjusted": "true" if adjusted else "false"},
        )
        rows: dict[str, dict[str, Any]] = {}
        dropped = 0
        for r in body.get("results") or []:
            sym = self._norm(r.get("T"))
            if sym is None:
                dropped += 1
                continue
            rows[sym] = {
                "symbol": sym,
                "date": d,
                "open": r.get("o"),
                "high": r.get("h"),
                "low": r.get("l"),
                "close": r.get("c"),
                "volume": r.get("v"),
                "vwap": r.get("vw"),
                "transactions": r.get("n"),
            }
        self.last_dropped = dropped
        log.info("polygon_grouped_daily", date=d.isoformat(), rows=len(rows), dropped=dropped)
        return pl.DataFrame(list(rows.values()), schema=_BAR_SCHEMA).select(BAR_COLUMNS)

    def splits(self, since: date) -> pl.DataFrame:
        raw = self._paged(
            "/v3/reference/splits",
            {
                "execution_date.gte": since.isoformat(),
                "order": "asc",
                "sort": "execution_date",
                "limit": "1000",
            },
        )
        out = []
        for r in raw:
            sym = self._norm(r.get("ticker"))
            d = _parse_date(r.get("execution_date"))
            try:
                ratio = float(r["split_to"]) / float(r["split_from"])
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
            if sym is None or d is None:
                continue
            out.append({"symbol": sym, "date": d, "split_ratio": ratio})
        return pl.DataFrame(out, schema=_SPLIT_SCHEMA)

    def dividends(self, since: date) -> pl.DataFrame:
        raw = self._paged(
            "/v3/reference/dividends",
            {
                "ex_dividend_date.gte": since.isoformat(),
                "order": "asc",
                "sort": "ex_dividend_date",
                "limit": "1000",
            },
        )
        out = []
        for r in raw:
            sym = self._norm(r.get("ticker"))
            d = _parse_date(r.get("ex_dividend_date"))
            try:
                amount = float(r["cash_amount"])
            except (KeyError, TypeError, ValueError):
                continue
            vendor_id = r.get("id")
            if sym is None or d is None:
                continue
            if not isinstance(vendor_id, str) or not vendor_id:
                # `id` is on every record (WO-0015 evidence). A record without one cannot be keyed,
                # and dropping or merging it would silently change the ex-date total (AMD-0027
                # 2A): fail loudly instead.
                raise ProviderError(
                    f"polygon dividend record without an id: {sym} {d.isoformat()}"
                )
            # `declaration_date` and `frequency` are on every record (WO-0015 evidence) and are what
            # separates a genuine second dividend from a repeated one (AMD-0029 2A). Carried
            # verbatim; an absent or malformed value is None, never guessed.
            freq = r.get("frequency")
            out.append(
                {
                    "symbol": sym, "date": d, "cash_dividend": amount, "vendor_id": vendor_id,
                    "declaration_date": _parse_date(r.get("declaration_date")),
                    "frequency": freq if isinstance(freq, int) and not isinstance(freq, bool)
                    else None,
                }
            )
        return pl.DataFrame(out, schema=_DIV_SCHEMA)
