"""Provider contract (PID 8.6): rate limiter, error type, bars protocol."""

import time
from datetime import date
from typing import Literal, Protocol

import polars as pl

CANONICAL_BAR_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"]


class ProviderError(RuntimeError):
    """Raised when a provider call fails."""


class RateLimiter:
    """Token bucket: `calls_per_minute` tokens, refilled continuously.

    `acquire()` returns immediately while tokens remain; once exhausted it
    sleeps (via `time.sleep`) for the time needed to earn the next token.
    """

    def __init__(self, calls_per_minute: int) -> None:
        if calls_per_minute <= 0:
            raise ValueError("calls_per_minute must be positive")
        self.calls_per_minute = calls_per_minute
        self._rate = calls_per_minute / 60.0  # tokens per second
        self._tokens = float(calls_per_minute)
        self._last = time.monotonic()

    def acquire(self) -> None:
        now = time.monotonic()
        self._tokens = min(
            float(self.calls_per_minute), self._tokens + (now - self._last) * self._rate
        )
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return
        wait = (1.0 - self._tokens) / self._rate
        time.sleep(wait)
        # The wait earned exactly the missing fraction of a token, which is spent now.
        self._last = now + wait
        self._tokens = 0.0


class BarsProvider(Protocol):
    source: str
    basis: Literal["unadjusted", "split", "split_div"]

    def daily_bars(self, symbols: list[str], start: date, end: date) -> pl.DataFrame:
        """Return canonical columns (CANONICAL_BAR_COLUMNS); float64 prices, pl.Date date."""
        ...
