# WO-0004 — Polygon provider: grouped-daily, splits, dividends; ingest CLI; validation

| Field | Value |
|---|---|
| **Status** | Closed |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.6, §8.7 (`ingest polygon`, `ingest polygon-actions`) ; `DESIGN.md` §3.1, §3.3 ; ADR-0003 |
| **Applicable Amendments** | AMD-0002, AMD-0012, AMD-0016, AMD-0017, AMD-0018 |
| **Base SHA** | 9a7a505 (main with AMD-0018) |
| **Branch** | `wo/0004-polygon-provider` |
| **Depends on** | WO-0002 |
| **Parallel group** | P0-C (with WO-0003, WO-0005) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0004/` |

## 1. Objective
Nightly and backfill ingestion of whole-market daily bars from Polygon's
grouped-daily endpoint into `bars_raw` (restricted to symbols present in
`symbols`), plus splits into `splits` and dividends into `dividends`
(AMD-0012), with the DESIGN §3.3 validation **record** — not gate — in
`ingest_log` and `bar_flags`.

**AMD-0018 delta (pre-merge).** `bars_raw` is never filtered by a
validation verdict (CI-9); the 25%-jump rule is recorded for every fetched
symbol and decided over `members_on(d)` only; a jump is a **per-symbol
flag**, with a day-level quarantine only on breadth; and re-validation must
not require re-fetching. AMD-0017 §2B's applied-versus-inapplicable
distinction moves here from WO-0012 (AMD-0018 §2G), because one Work Order
rewrites `validate_day` and two do not.

## 2. Scope (exhaustive)
```
argus/data/providers/polygon.py      create  class PolygonClient(api_key: SecretStr, calls_per_minute: int = 5):
                                               grouped_daily(d: date, adjusted: bool = True) -> pl.DataFrame  (canonical bar columns + vwap, transactions;
                                                 GET /v2/aggs/grouped/locale/us/market/stocks/{d}?adjusted=…; tickers normalised; invalid tickers dropped and counted)
                                               splits(since: date) -> pl.DataFrame[symbol, date(execution_date), split_ratio = split_to/split_from]  (GET /v3/reference/splits, paginated via next_url)
                                               dividends(since: date) -> pl.DataFrame[symbol, date(ex_dividend_date), cash_dividend]  (GET /v3/reference/dividends, paginated)
                                               source = "polygon"; basis = "split"  (adjusted=true is split-adjusted)
                                               429 → wait per Retry-After (default 60 s) and retry up to 3; other 5xx → tenacity 3x exponential
argus/data/schema.py                 modify  add DDL for `bar_flags (symbol TEXT, date DATE, source TEXT, flag TEXT, detail TEXT)`,
                                               PK (symbol, date, source, flag); bump SCHEMA_VERSION to 3 (AMD-0018 §2G assigns 3 here
                                               and 4 to WO-0012's store_meta, so the two cannot collide)
argus/data/validate.py               create  validate_day(bars: pl.DataFrame, members: list[str], prior_close: pl.DataFrame,
                                                 splits_today: dict[str, float], groups: pl.DataFrame, is_first_date: bool) -> ValidationResult(
                                                   ok: bool, reasons: list[str], coverage: float, n_zero_vol: int,
                                                   n_jump_unexplained: int, n_jump_reconciled: int, n_unclassified_members: int,
                                                   n_without_prior_close: int, jump_rule_applied: bool,
                                                   flags: pl.DataFrame[symbol, flag, detail])
                                               `ok=False` means QUARANTINE (stored in bars_raw, not published to bars) — never "not stored".
                                               Rules exactly DESIGN §3.3 as amended:
                                                 - coverage: members_on(d) with a bar >= 95%
                                                 - zero volume: <= 2% of members_on(d)
                                                 - jump: computed for EVERY symbol in `bars` and emitted as a flag row; a symbol is
                                                   `jump_split_reconciled` when splits_today holds a ratio r for it and
                                                   |(close_today / close_prior) * r - 1| <= 0.05 (the nightly basis boundary: yesterday was
                                                   fetched pre-split, today post-split), `jump_unexplained` otherwise.
                                                   DAY-LEVEL: quarantine only when symbols flagged `jump_unexplained` AND in members_on(d)
                                                   number >= `_JUMP_DAY_QUARANTINE_FRACTION` (0.20) of members_on(d). A non-member — a former
                                                   member whose ticker was reassigned, or a configured ETF — contributes a flag and never a
                                                   day-level verdict (AMD-0018 §2B).
                                                 - inapplicable (AMD-0017 §2B): when is_first_date is False and prior_close is missing for
                                                   > 5% of members_on(d), quarantine with reason
                                                   'jump rule inapplicable: prior_close missing for N of M members'; jump_rule_applied is
                                                   False only when is_first_date is True, where it is recorded, never counted as a pass
                                                 - classification: CURRENT members only — a historical-only member without an industry
                                                   group never quarantines a day; return n_unclassified_members and store (AMD-0016 §2C)
                                               Thresholds are module constants beside _COVERAGE_MIN_PCT, each carrying the AMD-0018 §2C
                                               reasoning in a comment; changeable only by Amendment
argus/data/ingest_polygon.py         create  ingest_polygon_day(store, client, d) -> IngestResult(rows, status{'ok','quarantined','holiday','failed'}, detail)
                                               (filters grouped_daily to symbols ∪ ETFs in `symbols`; writes EVERY fetched row to bars_raw
                                               BEFORE validating — CI-9, AMD-0018 §2A: no verdict may prevent a fetched row being stored;
                                               then runs validate_day, writes its flags to bar_flags, and writes ingest_log with
                                               status='ok' or 'quarantined' and the flag counts in detail. 'failed' means nothing was
                                               fetched. 'rejected' is retired)
                                               prior_close comes from the previous trading day present in bars_raw — unconditionally, whatever
                                               verdict that day received. That is what stops one day's verdict reaching the next (AMD-0018 §2A)
                                             backfill_polygon(store, client, start, end) -> list[IngestResult]  (trading days only; resumes past
                                               ingest_log.status in ('ok','holiday','quarantined') — a quarantined day is already stored and
                                               re-fetching cannot change its verdict; honours rate limit)
                                             revalidate_range(store, start, end) -> list[IngestResult]  (re-runs validate_day over bars already in
                                               bars_raw and rewrites ingest_log and bar_flags for those dates; makes NO provider call and never
                                               writes, alters or deletes a bars_raw row — AMD-0018 §2D)
                                             ingest_polygon_actions(store, client, since) -> int
                                               (writes splits() -> `splits` and dividends() -> `dividends`, each upsert keyed
                                                ["symbol","date","source"]; a same-date split AND dividend must both persist — AMD-0012)
argus/commands/ingest_polygon.py     create  `ingest polygon --date D | --backfill START END`, `ingest polygon-actions --since D`,
                                               `ingest revalidate --start A --end B` (registers onto argus.commands.ingest.app).
                                               `revalidate` takes no API key and must run with no network
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
IBKR, no universe code, no `docs/` changes by the Implementer.

**Schema: the `bar_flags` DDL and `SCHEMA_VERSION = 3` are now in scope**
(AMD-0018 §2C, §2G) — and nothing else. No other table's DDL, no
`store_meta` (that is WO-0012, at version 4), no data migration: the
backfill re-runs, so no existing `ingest_log` row carrying the retired
`'rejected'` status needs converting.

The AMD-0018 §2F ticker-reassignment bound on `bars` is **recorded, not
built here**. It belongs to WO-0007, where materialisation happens.

## 4. Design constraints
PID §8.6, §8.9. API key only as the `apiKey` query parameter inside the
client; redacted in logs and stripped from exception text. Trading-day
calendar: use `pandas_market_calendars`? **No** — no new dependency:
treat weekdays as candidate days and let an empty grouped-daily response
(`resultsCount == 0`) mark a holiday, logged `status='holiday'`.
`backfill_polygon` must be resumable (skip dates with `ingest_log.status
in ('ok','holiday','quarantined')`). Rate limiting is enforced inside the
client so callers cannot bypass it. `validate_day` stays pure: it reads,
returns a verdict and a flag frame, and mutates nothing.

**`bars_raw` is written before validation runs, and no verdict prevents a
fetched row being stored (CI-9, AMD-0018 §2A).** The earlier instruction —
"rejected days are kept out of `bars_raw` entirely" — was an Architect
error, contradicting DESIGN §3.3's own "not published to `bars`". It is
withdrawn. Gating the raw layer destroyed the evidence a rejection has to
be diagnosed from, made a rule change cost a full re-fetch, and made the
validator's input depend on its own verdicts.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_polygon_client.py::test_grouped_daily_parses_and_filters` | fixture → canonical columns; junk tickers dropped and counted | column set + counts |
| `test_polygon_client.py::test_splits_pagination` | two pages merged; ratio = to/from | row count + ratio value |
| `test_polygon_client.py::test_429_retry_after` | 429 then 200 → success; sleep called with Retry-After | monkeypatched sleep asserted |
| `test_polygon_client.py::test_key_not_leaked` | error text and logs on a 500 lack the key | string assertions |
| `test_validate.py::test_coverage_rule` | 94% coverage → quarantined; 96% → ok | threshold boundary |
| `test_validate.py::test_one_member_jump_does_not_quarantine_the_day` | a single member moving 30% with no split → `ok is True`, one `jump_unexplained` flag row | asserts ok AND the flag — the defect this delta fixes |
| `test_validate.py::test_breadth_of_jumps_quarantines_the_day` | 20% of members flagged `jump_unexplained` → quarantined; 19% → ok | the 0.20 boundary, both sides |
| `test_validate.py::test_non_member_jump_never_reaches_the_verdict` | a symbol in `bars` but not in `members_on(d)` (a reassigned delisted ticker) moving 90%, repeated past 20% of the member count → `ok is True`, flags present | fails if the rule is computed over `bars` rather than members — the D1 defect |
| `test_validate.py::test_jump_with_consistent_split_is_reconciled` | a −50% move with ratio 2.0 in `splits_today` → `jump_split_reconciled`, not `jump_unexplained`; ratio 3.0 → `jump_unexplained` | both branches, on the ratio value |
| `test_validate.py::test_zero_volume_rule` | 3% zero-volume → quarantined | boundary |
| `test_validate.py::test_missing_group_rule` | one **current** member with empty group → quarantined; a historical-only member without one → ok | both branches (AMD-0016 §2C) |
| `test_validate.py::test_missing_prior_close_quarantines_non_initial_day` | `is_first_date=False` and > 5% of members lacking `prior_close` → quarantined with the inapplicable-jump-rule reason | asserts `ok is False` and the reason string (AMD-0017 §2B) |
| `test_validate.py::test_first_ever_date_records_rule_not_applied` | `is_first_date=True` → `jump_rule_applied is False` and no quarantine for that reason | asserts both fields |
| `test_ingest_polygon.py::test_quarantined_day_is_still_stored` | validation quarantine → every fetched row **present** in `bars_raw`, `ingest_log.status='quarantined'`, flags in `bar_flags` | row counts in `bars_raw` — this is CI-9 |
| `test_ingest_polygon.py::test_prior_close_comes_from_a_quarantined_day` | day 1 quarantined, day 2 ingested → day 2's `prior_close` is day 1's close, so day 1's verdict does not reach day 2 | asserts no cascade: day 2 is `ok`. This is the 268-day defect, pinned |
| `test_ingest_polygon.py::test_backfill_resumable` | second run skips ok/holiday/quarantined days (client call count) | respx call count |
| `test_ingest_polygon.py::test_revalidate_makes_no_provider_call` | `revalidate_range` over stored days rewrites `ingest_log`/`bar_flags`, leaves `bars_raw` byte-identical, and issues zero HTTP requests | respx call count 0 + `bars_raw` checksum |

## 6. Acceptance criteria
- **AC1** — `argus ingest polygon --date <last trading day>` on the host writes ≥ 95% of members to `bars_raw` with `source='polygon'`, `basis='split'` (operator check with counts).
- **AC2** — `argus ingest polygon --backfill <2 years ago> <today>` completes within rate limits and is resumable; `ingest_log` shows one row per weekday with status ok/holiday/quarantined/failed. **Every weekday's bars are in `bars_raw` whatever its status** (CI-9) — operator check: a count of distinct dates in `bars_raw` equal to ok + quarantined. **Quarantines are confined to days with a genuine data-quality failure**: a single member's real price move must not quarantine a day (AMD-0018), and a historical-only member lacking an industry group must not either (AMD-0016 §2C). Operator check: summary counts, wall time, the reason for every quarantined day, and the per-day count of `jump_unexplained` flags among members.
- **AC6** — `jump_unexplained` flags are present in `bar_flags` across the backfill and are listed with their symbols and dates; **STI, AIV and NKTR appear in no day-level verdict** (operator check: the per-day verdict reasons, grepped for each). Zero flags across 520 days means the rule is not firing and is a delivery defect, not a pass.
- **AC7** — `argus ingest revalidate --start <2 years ago> --end <today>` re-runs the verdicts over stored bars with **no network and no API key**, reproduces the same statuses, and leaves `bars_raw` unchanged (operator check: row count and a checksum of `bars_raw` before and after, plus wall time — this is the cost that §2D removes from every future rule change).
- **AC3** — `argus ingest polygon-actions --since 2024-01-01` populates `splits` and `dividends` for members (operator check: counts per table; at least one known 2026 split present). The same-date split-and-dividend retention case is satisfied by the unit tests plus WO-0005's yfinance pairs where Polygon's window contains no such pair — the criterion is that the system retains both rows, not that this provider exhibits one (AMD-0012, ratified AMD-0016 §2E).
- **AC4** — All validation rules enforced (tests in §5). **Non-vacuity, mandatory (CI-6):** file two mutation runs, each failing the intended test — (a) computing the jump rule over `bars` instead of `members_on(d)` makes `test_non_member_jump_never_reaches_the_verdict` fail; (b) taking `prior_close` from the last **ok** day instead of the last stored day makes `test_prior_close_comes_from_a_quarantined_day` fail. Those two are the defects this delta exists to fix, so they are the two that must be shown capable of failing.
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
