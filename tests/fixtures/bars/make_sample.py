"""Generate sample_bars.parquet: 3 symbols x 30 weekdays, deterministic, synthetic.

Usage: python tests/fixtures/bars/make_sample.py
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

SYMBOLS = ["AAA", "BBB", "CCC"]
START = date(2024, 1, 2)
DAYS = 30
INGESTED_AT = datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC).replace(tzinfo=None)


def build() -> pl.DataFrame:
    days: list[date] = []
    d = START
    while len(days) < DAYS:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    rows = []
    for si, sym in enumerate(SYMBOLS):
        base = 100.0 * (si + 1)
        for i, day in enumerate(days):
            close = base + i * 0.5 + si
            rows.append(
                {
                    "symbol": sym,
                    "date": day,
                    "open": close - 0.25,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000_000.0 + 1000.0 * i + 10.0 * si,
                    "source": "fixture",
                    "basis": "split",
                    "ingested_at": INGESTED_AT,
                }
            )
    return pl.DataFrame(rows).with_columns(
        pl.col("date").cast(pl.Date), pl.col("ingested_at").cast(pl.Datetime("us"))
    )


if __name__ == "__main__":
    out = Path(__file__).with_name("sample_bars.parquet")
    build().write_parquet(out)
    print(f"wrote {out}")
