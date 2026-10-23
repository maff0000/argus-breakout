# WO-0024 — A pending day is not a holiday: the market calendar and the retry

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.6, §8.7 ; `DESIGN.md` §3.1, §3.3, §10 |
| **Applicable Amendments** | AMD-0018, AMD-0032, AMD-0036 |
| **Base SHA** | main at the commit introducing this file |
| **Branch** | `wo/0024-pending-days-and-the-market-calendar` |
| **Depends on** | WO-0004 (merged — this corrects it) |
| **Parallel group** | **P0-H — URGENT, precedes WO-0009's remaining criteria** |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0024/` |

## 1. Objective
Stop the nightly from losing a trading day and reporting success.

Today, `resultsCount == 0` is logged `holiday`, a holiday makes the night
`ok=True`, the resume logic skips it, and the staleness alarm stays quiet
because a report was written. **So a real trading day whose data the vendor
has not published yet is silently dropped** (AMD-0036 §1b). The nightly is
installed and firing, so this precedes everything else in WO-0009.

Three changes:
1. a **`pending`** status for a trading day that is not ready — retried,
   never skipped;
2. the **exchange calendar from Polygon's own endpoint**, so "holiday"
   means the calendar says so rather than "the response was empty";
3. a **retry** until the data exists, so the schedule need not be a lucky
   guess.

## 2. Scope (exhaustive)
```
argus/data/schema.py            modify  add `market_calendar (date DATE PRIMARY KEY, is_trading BOOLEAN NOT NULL,
                                          early_close BOOLEAN NOT NULL, source TEXT NOT NULL, fetched_at TIMESTAMP)`;
                                          bump SCHEMA_VERSION to 11
argus/data/providers/polygon.py modify  market_status_upcoming() -> pl.DataFrame[date, is_trading, early_close]
                                          (GET /v1/marketstatus/upcoming — exchange holidays and early closes, same
                                           vendor and key as the bars, so AMD-0036 §2B keeps WO-0004 §4's
                                           no-new-dependency decision while fixing its implementation)
                                        market_status_now() -> dict  (GET /v1/marketstatus/now)
argus/data/calendar.py          create  refresh_calendar(store, client) -> int  (upserts market_calendar; weekly)
                                        is_trading_day(store, d) -> bool | None
                                          True/False from the calendar; **None when the calendar does not cover d**
                                          — and a None must be treated as PENDING, never holiday (AMD-0036 §2B):
                                          a pending day is retried, a wrongly-marked holiday is lost
argus/data/ingest_polygon.py    modify  ingest_polygon_day: on `resultsCount == 0`, consult is_trading_day(d):
                                          False               -> status='holiday'   (the calendar says so)
                                          True or None        -> status='pending'   (not published yet)
                                        resume/skip set becomes ('ok','holiday','quarantined') ONLY — 'pending' and
                                          'failed' are always retried (AMD-0036 §2A)
argus/pipeline.py               modify  a 'pending' ingest makes the run report ok=False with reason 'pending', so the
                                          night is visibly unfinished rather than falsely complete. Downstream
                                          required steps are skipped, not failed
argus/commands/nightly_cmds.py  modify  `nightly-status`: the last trading day per market_calendar is INCOMPLETE until
                                          its ingest_log status is 'ok' or 'quarantined'; 'pending' exits 1
                                        add `calendar refresh` and `market-status` (diagnostic, prints the publication
                                          state for a date; used by AC4)
ops/argus-nightly-retry.timer   create  every 30 minutes from the scheduled run until a 06:00 UK cutoff; the unit
                                          re-runs `argus nightly --date <target>`, which is already idempotent and
                                          resumable. No application logic in ops/ (ADR-0008 constraint 5)
ops/argus-nightly-retry.service create  as above; MemoryMax/MemoryHigh as AMD-0035 §2C
tests/test_calendar.py          create  see §5
tests/test_ingest_polygon.py    modify  see §5
tests/test_schema.py            modify  count/version assertions only (ruling 9)
tests/test_cli.py               modify  count/version assertions only (ruling 9)
```

## 3. Exclusions
No new third-party dependency — the calendar comes from Polygon
(AMD-0036 §2B). No change to validation rules, adjustment, features,
reconciliation or the IBKR path. No change to what a **genuine** holiday
does: it still reports `ok=True` and no alarm (AMD-0032 §2B). No `docs/` by
the Implementer.

## 4. Design constraints
PID §8.6, §8.9 and ADR-0008. The calendar refresh is **weekly** and cached;
the nightly reads `market_calendar` and makes **no** extra call per run.
`market_status_now` is used by the AC4 measurement and the diagnostic
command, not by the nightly path.

**The safe direction is `pending`.** Where the calendar is missing,
unparseable or does not cover the date, the day is `pending`. A pending day
costs a retry; a wrongly-marked holiday costs the day's bars and says
nothing.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_ingest_polygon.py::test_empty_response_on_trading_day_is_pending` | calendar says trading, response empty → `status='pending'`, **not** `holiday` | asserts the status — the defect, pinned |
| `test_ingest_polygon.py::test_empty_response_on_calendar_holiday_is_holiday` | calendar says non-trading → `holiday` and `ok=True` | the other branch; fails if everything becomes pending |
| `test_ingest_polygon.py::test_unknown_calendar_date_is_pending_not_holiday` | calendar does not cover the date → `pending` | asserts the safe default |
| `test_ingest_polygon.py::test_pending_day_is_retried_not_skipped` | a `pending` day is re-fetched on the next run; an `ok`/`holiday` day is not | asserts the client call counts both ways |
| `test_pipeline.py::test_pending_ingest_makes_the_night_not_ok` | a pending ingest → `report.ok is False` with reason `pending` | asserts `ok is False` — a night that lost a day must not read as complete |
| `test_calendar.py::test_refresh_upserts_and_is_idempotent` | two refreshes leave one row per date | counts |
| `test_calendar.py::test_early_close_is_recorded` | an early-close date is `is_trading=True, early_close=True` | asserts both flags |
| `test_cli.py::test_nightly_status_exits_1_on_pending_last_trading_day` | last trading day `pending` → `nightly-status` exits 1 | asserts the exit code; fails if pending counts as done |

## 6. Acceptance criteria
- **AC1** — `calendar refresh` on the host populates `market_calendar` with the exchange's upcoming holidays and early closes; row count and the next three non-trading dates filed.
- **AC2** — A trading day with an empty grouped-daily response records **`pending`**, the night reports **`ok=False`**, the retry timer re-attempts, and the day completes when the vendor publishes (operator check: the `ingest_log` sequence for one such date, with timestamps).
- **AC3** — A genuine calendar holiday still records `holiday` with `ok=True` and no alarm (operator check: a real upcoming holiday or the most recent one).
- **AC4** — **The vendor's publication time is measured** (AMD-0036 §2D): poll `market-status` and the grouped-daily endpoint at intervals through one session and file **the time the day's data first appears**, with the polling log. The schedule and the retry window are then set from that figure, and the figure is written into `DESIGN.md` §10 by the Architect. **No overnight wait is used to establish it.**
- **AC5** — `nightly-status` exits 1 while the last trading day is `pending` and 0 once it is `ok` (operator check: both).
- **AC6** — `SCHEMA_VERSION` is 11; the migration is idempotent; every other table is byte-identical (checksum, CI-9).
- **AC7** — Non-vacuity, mandatory (CI-6): four mutation runs — (a) classifying an empty response on a trading day as `holiday` fails `test_empty_response_on_trading_day_is_pending`; (b) defaulting an unknown calendar date to `holiday` fails `test_unknown_calendar_date_is_pending_not_holiday`; (c) adding `pending` to the resume skip set fails `test_pending_day_is_retried_not_skipped`; (d) letting a pending ingest report `ok=True` fails `test_pending_ingest_makes_the_night_not_ok`.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC6), the AC4 polling log, and the AC7 mutation
runs.

## 8. Implementer notes
This corrects two Architect decisions, and the second is the dangerous one.

WO-0004 §4 rejected a market-calendar dependency and substituted an
inference — *empty response means holiday* — which is false for every
trading day the vendor has not published yet. AMD-0032 §2B then made a
holiday a success. Together they let the nightly drop a trading day and
report `ok=True`, with the resume logic skipping it afterwards and the
staleness alarm silent because a report existed.

**The no-dependency instinct was right and is kept**: Polygon serves the
calendar itself, on the key already in use.

The four mutations in AC7 are the four ways to reintroduce the defect, and
they are listed because each one looks like a simplification.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-23
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
