# WO-0006 — FMP calendars → events (earnings, ex-dividend)

| Field | Value |
|---|---|
| **Status** | Closed |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.7 (`events refresh`) ; `DESIGN.md` §3.1, §3.2 (`events`) ; ADR-0003 |
| **Applicable Amendments** | AMD-0002 |
| **Base SHA** | 46086e6 |
| **Branch** | `wo/0006-fmp-calendars-events` |
| **Depends on** | WO-0003 |
| **Parallel group** | P0-D (with WO-0007) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0006/` |

## 1. Objective
`argus events refresh --days 45` keeps the `events` table current with
earnings dates (and before/after-market flag where provided) and
ex-dividend dates for every active symbol for the next N days, plus a
trailing 10-day window so recently passed events are confirmed, using two
FMP calls per run.

## 2. Scope (exhaustive)
```
argus/data/providers/fmp.py          modify  add earnings_calendar(start, end) -> pl.DataFrame[symbol, date, time_of_day{'bmo','amc',None}, eps_estimate, confirmed]
                                                 (GET /stable/earnings-calendar?from=&to=)
                                             add dividends_calendar(start, end) -> pl.DataFrame[symbol, date(ex-date), cash_dividend]
                                                 (GET /stable/dividends-calendar?from=&to=)
argus/events/__init__.py             create
argus/events/earnings.py             create  refresh_events(store, fmp, today: date, days_ahead: int = 45, days_back: int = 10) -> EventsReport(
                                               n_earnings, n_exdiv, n_symbols_with_upcoming_earnings, calls_used)
                                               (filters to symbols in `symbols`; upsert into events with type 'earnings'/'exdiv', source='fmp';
                                                rows for dates now in the past with no FMP record are left as-is, never deleted)
                                             next_earnings(store, symbol, on: date) -> date | None
                                             days_to_earnings(store, symbols: list[str], on: date) -> pl.DataFrame[symbol, days_to_earnings, days_since_earnings]
                                               (trading-day counts; None when unknown)
argus/commands/events_cmds.py        create  `events refresh --days N` → prints EventsReport (registers onto argus.commands.events.app)
argus/cli.py                         modify  add exactly one import line for argus.commands.events_cmds in the append-only block (AMD-0002)
tests/fixtures/fmp/earnings_calendar.json      create  scrubbed; includes bmo/amc/null times and non-member symbols
tests/fixtures/fmp/dividends_calendar.json     create
tests/test_events.py                 create  see §5 (respx)
```

## 3. Exclusions
No feature computation, no Polygon/yfinance/IBKR code, no schema changes,
no changes to universe logic, no `docs/`.

## 4. Design constraints
PID §8.9; FMP budget via the existing `FMPClient` counter (two calls per
run). Non-member symbols in the calendar are dropped before upsert.
Trading-day arithmetic uses the dates present in `bars_raw` (any source)
as the trading calendar; when no bars exist yet, fall back to weekdays and
mark the result `approx=True` in the DataFrame.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_events.py::test_refresh_upserts_members_only` | fixture with 3 members + 2 non-members → 3 earnings rows | counts |
| `test_events.py::test_time_of_day_mapping` | `bmo`/`amc`/null preserved | values |
| `test_events.py::test_refresh_idempotent` | second refresh changes no row counts | counts |
| `test_events.py::test_days_to_earnings_trading_days` | with a bars calendar containing a holiday, days_to_earnings excludes it | exact integer |
| `test_events.py::test_uses_exactly_two_calls` | one refresh → two FMP calls | respx call count |

## 6. Acceptance criteria
- **AC1** — On the host, `argus events refresh --days 45` populates upcoming earnings for ≥ 60% of active members within the next 45 days during earnings season (operator check with counts and date).
- **AC2** — `days_to_earnings` returns trading-day counts (test).
- **AC3** — Exactly two FMP calls per run (test; operator check via ingest_log counter).
- **AC4** — Idempotent (test).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC3 outputs).

## 8. Implementer notes
FMP's earnings calendar field names in the stable API: `symbol`, `date`,
`epsEstimated`, `time` (values like `bmo`, `amc`, or empty). Dividends:
`symbol`, `date` (ex-date), `dividend`. Confirm against the fixtures the
Delivery Controller recorded; if field names differ, report `blocked` with
the actual payload shape rather than guessing.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
