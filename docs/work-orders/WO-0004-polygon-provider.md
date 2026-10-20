# WO-0004 — Polygon provider: grouped-daily, splits, dividends; ingest CLI; validation

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.6, §8.7 (`ingest polygon`, `ingest polygon-actions`) ; `DESIGN.md` §3.1, §3.3 ; ADR-0003 |
| **Applicable Amendments** | AMD-0002, AMD-0012, AMD-0016 |
| **Base SHA** | main at Closure of WO-0002 |
| **Branch** | `wo/0004-polygon-provider` |
| **Depends on** | WO-0002 |
| **Parallel group** | P0-C (with WO-0003, WO-0005) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0004/` |

## 1. Objective
Nightly and backfill ingestion of whole-market daily bars from Polygon's
grouped-daily endpoint into `bars_raw` (restricted to symbols present in
`symbols`), plus splits into `splits` and dividends into `dividends` (AMD-0012), with the DESIGN
§3.3 validation gate and `ingest_log` records.

## 2. Scope (exhaustive)
```
argus/data/providers/polygon.py      create  class PolygonClient(api_key: SecretStr, calls_per_minute: int = 5):
                                               grouped_daily(d: date, adjusted: bool = True) -> pl.DataFrame  (canonical bar columns + vwap, transactions;
                                                 GET /v2/aggs/grouped/locale/us/market/stocks/{d}?adjusted=…; tickers normalised; invalid tickers dropped and counted)
                                               splits(since: date) -> pl.DataFrame[symbol, date(execution_date), split_ratio = split_to/split_from]  (GET /v3/reference/splits, paginated via next_url)
                                               dividends(since: date) -> pl.DataFrame[symbol, date(ex_dividend_date), cash_dividend]  (GET /v3/reference/dividends, paginated)
                                               source = "polygon"; basis = "split"  (adjusted=true is split-adjusted)
                                               429 → wait per Retry-After (default 60 s) and retry up to 3; other 5xx → tenacity 3x exponential
argus/data/validate.py               create  validate_day(bars: pl.DataFrame, members: list[str], prior_close: pl.DataFrame, splits_today: set[str],
                                               groups: pl.DataFrame) -> ValidationResult(ok: bool, reasons: list[str], coverage: float, n_zero_vol: int, n_jump: int)
                                               rules exactly DESIGN §3.3: coverage ≥ 0.95; no |close/prior_close − 1| > 0.25 without a split;
                                               zero-volume ≤ 2%; the classification check applies to CURRENT members only — a
                                               historical-only member without an industry group never rejects a day; return
                                               n_unclassified_members and store the day (AMD-0016 §2C)
argus/data/ingest_polygon.py         create  ingest_polygon_day(store, client, d) -> IngestResult(rows, status{'ok','rejected','failed'}, detail)
                                               (filters grouped_daily to symbols ∪ ETFs in `symbols`; runs validate_day; writes bars_raw only when ok;
                                               always writes ingest_log)
                                             backfill_polygon(store, client, start, end) -> list[IngestResult]  (trading days only; skips days already present; honours rate limit)
                                             ingest_polygon_actions(store, client, since) -> int
                                               (writes splits() -> `splits` and dividends() -> `dividends`, each upsert keyed
                                                ["symbol","date","source"]; a same-date split AND dividend must both persist — AMD-0012)
argus/commands/ingest_polygon.py     create  `ingest polygon --date D | --backfill START END`, `ingest polygon-actions --since D` (registers onto argus.commands.ingest.app)
argus/cli.py                         modify  add exactly one import line for argus.commands.ingest_polygon in the append-only block (AMD-0002)
tests/fixtures/polygon/grouped_daily_2026-10-16.json   create  scrubbed sample: ≥ 600 tickers incl. members, ETFs, junk tickers (warrants, units)
tests/fixtures/polygon/splits_page1.json, splits_page2.json  create  pagination sample with next_url
tests/fixtures/polygon/dividends.json                   create
tests/test_polygon_client.py         create  see §5 (respx)
tests/test_validate.py               create  see §5
tests/test_ingest_polygon.py         create  see §5
```

## 3. Exclusions
No adjustment/materialisation logic (WO-0007), no yfinance, no FMP, no
IBKR, no universe code, no schema changes, no `docs/` changes.

## 4. Design constraints
PID §8.6, §8.9. API key only as the `apiKey` query parameter inside the
client; redacted in logs and stripped from exception text. Trading-day
calendar: use `pandas_market_calendars`? **No** — no new dependency:
treat weekdays as candidate days and let an empty grouped-daily response
(`resultsCount == 0`) mark a holiday, logged `status='holiday'`.
`backfill_polygon` must be resumable (skip dates with `ingest_log.status in
('ok','holiday')`). Rate limiting is enforced inside the client so callers
cannot bypass it. Validation never mutates data; rejected days are kept
out of `bars_raw` entirely.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_polygon_client.py::test_grouped_daily_parses_and_filters` | fixture → canonical columns; junk tickers dropped and counted | column set + counts |
| `test_polygon_client.py::test_splits_pagination` | two pages merged; ratio = to/from | row count + ratio value |
| `test_polygon_client.py::test_429_retry_after` | 429 then 200 → success; sleep called with Retry-After | monkeypatched sleep asserted |
| `test_polygon_client.py::test_key_not_leaked` | error text and logs on a 500 lack the key | string assertions |
| `test_validate.py::test_coverage_rule` | 94% coverage → rejected; 96% → ok | threshold boundary |
| `test_validate.py::test_jump_requires_split` | 30% jump without split → rejected; with split → ok | both branches |
| `test_validate.py::test_zero_volume_rule` | 3% zero-volume → rejected | boundary |
| `test_validate.py::test_missing_group_rule` | one member with empty group → rejected | presence |
| `test_ingest_polygon.py::test_rejected_day_not_written` | validation failure → `bars_raw` unchanged, `ingest_log.status='rejected'` | counts |
| `test_ingest_polygon.py::test_backfill_resumable` | second run skips ok/holiday days (client call count) | respx call count |

## 6. Acceptance criteria
- **AC1** — `argus ingest polygon --date <last trading day>` on the host writes ≥ 95% of members to `bars_raw` with `source='polygon'`, `basis='split'` (operator check with counts).
- **AC2** — `argus ingest polygon --backfill <2 years ago> <today>` completes within rate limits and is resumable; `ingest_log` shows one row per weekday with status ok/holiday/rejected, and **rejections are confined to days with a genuine data-quality failure** — a historical-only member lacking an industry group must not reject a day (AMD-0016 §2C). Operator check: summary counts, wall time, and the reason for every rejected day.
- **AC3** — `argus ingest polygon-actions --since 2024-01-01` populates `splits` and `dividends` for members (operator check: counts per table; at least one known 2026 split present). The same-date split-and-dividend retention case is satisfied by the unit tests plus WO-0005's yfinance pairs where Polygon's window contains no such pair — the criterion is that the system retains both rows, not that this provider exhibits one (AMD-0012, ratified AMD-0016 §2E).
- **AC4** — All validation rules enforced (tests in §5).
- **AC5** — API key appears nowhere in logs or errors (test_key_not_leaked; Auditor grep of host logs sample).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC3 outputs, including backfill wall time).

## 8. Implementer notes
The grouped-daily response field names are `T` (ticker), `o h l c v vw n t`.
`t` is a Unix ms timestamp for the bar date (America/New_York); the bar
date is the requested `d`. Splits: `execution_date`, `split_from`,
`split_to`. Dividends: `ex_dividend_date`, `cash_amount`. Keep the client
synchronous (`httpx.Client`); no asyncio in this phase.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
