"""Financial Modeling Prep client (WO-0003; PID 8.6, 8.9).

The API key is added to the query string inside `FMPClient.get` and nowhere
else. It is never logged and never placed in an exception message. Every HTTP
attempt (including retries) counts against a per-UTC-day budget that is
persisted in `ingest_log` (source `fmp-budget`, one row per attempt).
"""

from datetime import UTC, date, datetime

import duckdb
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

from argus.data.providers.base import ProviderError, RateLimiter
from argus.data.store import Store
from argus.data.tickers import normalize, to_provider

BASE_URL = "https://financialmodelingprep.com/stable/"
BUDGET_SOURCE = "fmp-budget"
_CALLS_PER_SECOND = 4
_ATTEMPTS = 3
_TIMEOUT = 30.0

log = structlog.get_logger()


class _Retryable(Exception):  # noqa: N818 - internal control-flow signal
    """A 5xx / 429 / transport failure; carries no URL and no key."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class FMPClient:
    def __init__(
        self,
        api_key: SecretStr,
        budget: int,
        store: Store,
        http: httpx.Client | None = None,
        base_url: str = BASE_URL,
        retry_wait: float = 1.0,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("fmp api key is empty")
        if budget <= 0:
            raise ValueError("fmp budget must be positive")
        self._key = api_key
        self._budget = budget
        self._store = store
        self._http = http if http is not None else httpx.Client(timeout=_TIMEOUT)
        self._base = base_url if base_url.endswith("/") else base_url + "/"
        self._retry_wait = retry_wait
        self._limiter = RateLimiter(_CALLS_PER_SECOND * 60)

    # ------------------------------------------------------------------ budget
    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    def calls_today(self) -> int:
        df = self._store.read(
            "SELECT COALESCE(SUM(rows), 0) AS n FROM ingest_log WHERE date = ? AND source = ?",
            [self._today(), BUDGET_SOURCE],
        )
        return int(df["n"][0])

    def _spend_one(self) -> None:
        """Raise at budget; otherwise persist one call before it is made."""
        if self.calls_today() >= self._budget:
            raise ProviderError("fmp daily budget exhausted")
        for attempt in range(3):
            try:
                self._store.log_ingest(self._today(), BUDGET_SOURCE, 1, "ok")
                return
            except duckdb.ConstraintException:
                if attempt == 2:  # same-microsecond primary-key clash; retry, then give up
                    raise

    # ------------------------------------------------------------------ transport
    def _request_once(self, path: str, params: dict | None) -> dict | list:
        self._spend_one()
        self._limiter.acquire()
        query = dict(params or {})
        query["apikey"] = self._key.get_secret_value()  # the only place the key is attached
        try:
            resp = self._http.get(self._base + path.lstrip("/"), params=query, timeout=_TIMEOUT)
        except httpx.TransportError as exc:
            raise _Retryable(f"transport error {type(exc).__name__}") from None
        status = resp.status_code
        if status == 429 or status >= 500:
            raise _Retryable(f"status {status}")
        if status >= 400:
            raise ProviderError(f"fmp {path} failed with status {status}")
        try:
            body = resp.json()
        except ValueError:
            raise ProviderError(f"fmp {path} returned a non-JSON body") from None
        if isinstance(body, dict) and ("Error Message" in body or "error" in body):
            raise ProviderError(f"fmp {path} returned an error payload")
        return body

    def get(self, path: str, params: dict | None = None) -> dict | list:
        retrying = Retrying(
            stop=stop_after_attempt(_ATTEMPTS),
            wait=wait_exponential(multiplier=self._retry_wait, max=8),
            retry=retry_if_exception_type(_Retryable),
            reraise=True,
        )
        try:
            for attempt in retrying:
                with attempt:
                    try:
                        return self._request_once(path, params)
                    except _Retryable as exc:
                        log.warning("fmp_retry", path=path, reason=exc.detail)
                        raise
        except _Retryable as exc:
            raise ProviderError(
                f"fmp {path} failed after {_ATTEMPTS} attempts ({exc.detail})"
            ) from None
        raise ProviderError(f"fmp {path} failed")  # pragma: no cover - loop always returns/raises

    # ------------------------------------------------------------------ endpoints
    def historical_sp500_changes(self) -> pl.DataFrame:
        """One row per added/removed symbol: [date, symbol, action, reason]."""
        body = self.get("historical-sp500-constituent")
        if not isinstance(body, list):
            raise ProviderError("fmp historical-sp500-constituent: unexpected payload")
        rows: list[dict] = []
        skipped = 0
        for rec in body:
            when = _record_date(rec)
            if when is None:
                skipped += 1
                continue
            reason = str(rec.get("reason") or "")
            for field, action in (("symbol", "added"), ("removedTicker", "removed")):
                raw = (rec.get(field) or "").strip()
                if not raw:
                    continue
                try:
                    sym = normalize(raw, "fmp")
                except ValueError:
                    skipped += 1
                    continue
                rows.append({"date": when, "symbol": sym, "action": action, "reason": reason})
        if skipped:
            log.warning("fmp_changes_skipped", count=skipped)
        return pl.DataFrame(
            rows,
            schema={
                "date": pl.Date,
                "symbol": pl.String,
                "action": pl.String,
                "reason": pl.String,
            },
        )

    def current_sp500(self) -> pl.DataFrame:
        """Current constituents: [symbol, name, sector, sub_industry]."""
        body = self.get("sp500-constituent")
        if not isinstance(body, list):
            raise ProviderError("fmp sp500-constituent: unexpected payload")
        rows = []
        for rec in body:
            try:
                sym = normalize((rec.get("symbol") or "").strip(), "fmp")
            except ValueError:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "name": rec.get("name"),
                    "sector": rec.get("sector"),
                    "sub_industry": rec.get("subSector"),
                }
            )
        return pl.DataFrame(
            rows,
            schema={
                "symbol": pl.String,
                "name": pl.String,
                "sector": pl.String,
                "sub_industry": pl.String,
            },
        )

    def profile(self, symbol: str) -> dict:
        """Company profile for one canonical symbol (fallback only); {} if none."""
        body = self.get("profile", {"symbol": to_provider(symbol, "fmp")})
        if isinstance(body, list):
            return dict(body[0]) if body and isinstance(body[0], dict) else {}
        return dict(body)


def _record_date(rec: dict) -> date | None:
    raw = rec.get("date")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    added = rec.get("dateAdded")
    if added:
        try:
            return datetime.strptime(str(added), "%B %d, %Y").date()
        except ValueError:
            return None
    return None
