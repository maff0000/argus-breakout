# WO-0006 — Operator checks (live, 2026-10-20)

Run by the Delivery Controller on the execution host against code head `9d6e192` (the later delta `9a841b0` changes fixtures, tests and a coverage line, not the FMP calls or the stored rows; the
counts below are re-derivable from the table). The store is a copy of the WO-0003 seed (518 active symbols) with `init_schema()` re-run. The FMP key is used, never printed. The first attempts were
blocked by HTTP 429 (the day's allowance had been spent by earlier verification runs); a watcher retried until FMP answered 200.

```
probe status=200 after 8 probes at 2026-10-20T19:05:47Z
host=dell-debian head=9d6e192172b844b500451844445f68b5b7aebb01
$ argus events refresh --days 45
earnings rows: 46
ex-dividend rows: 12
symbols with upcoming earnings: 39 of 518 active
fmp calls used: 2
exit=0
events by type: [('exdiv', 12, datetime.date(2026, 10, 15), datetime.date(2026, 12, 2), 12), ('earnings', 46, datetime.date(2026, 10, 13), datetime.date(2026, 11, 19), 11)]
time_of_day: [(None, 46)]
distinct symbols with earnings >= today: [(39,)]
active symbols: [(518,)]
fmp-budget rows today: [(54,)]
ingest_log events: [('ok', '', 58)]
E6_DONE
```

## Direct look at the real payloads (status codes and shapes only; no key)
| Endpoint | Window | Rows | Keys |
|---|---|---|---|
| `/stable/earnings-calendar` | today-10d .. today+45d | **70** (46 for active symbols, 24 not) | date, epsActual, epsEstimated, lastUpdated, revenueActual, revenueEstimated, symbol — **no `time`** |
| `/stable/earnings-calendar` | 2026-10-26 .. 2026-10-30 (peak week) | **27** (also 27 with `limit=4000`; `page=1` returns 0) | same |
| `/stable/dividends-calendar` | today-10d .. today+45d | 12 (all active) | adjDividend, date, declarationDate, dividend, frequency, paymentDate, recordDate, symbol, yield |

## Per-AC reading
- **AC1** (≥ 60% of active symbols with upcoming earnings): **not met on this plan, 39 of 518 = 7.5%.** Cause: the provider's calendar is a thin sample, not a defect in the code. Recorded under standing ruling 7 in `spec-defects.md`.
- **AC2** (trading-day counts): met by test (`test_days_to_earnings_trading_days`, holiday excluded); not an operator check.
- **AC3** (two FMP calls per run): **met live, `fmp calls used: 2`** (one per endpoint, both 200).
- **AC4** (idempotent): met by test; the 46 + 12 rows are upserted by `(symbol, date, type)`.
- Observation: `time_of_day` is None for all 46 earnings rows (bmo/amc is not provided by this endpoint on this plan); 11 of the 46 rows are `confirmed` (actual EPS present or date ≤ today).
