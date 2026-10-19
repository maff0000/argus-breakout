import time

from argus.data.providers.base import RateLimiter


def test_blocks_after_quota(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    limiter = RateLimiter(5)
    for _ in range(5):
        limiter.acquire()
    assert sleeps == []
    limiter.acquire()
    assert len(sleeps) == 1
    assert sleeps[0] > 0
