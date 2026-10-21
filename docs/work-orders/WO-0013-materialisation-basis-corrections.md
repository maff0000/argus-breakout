# WO-0013 — Materialisation basis corrections: flags carried not subtracted, dividend basis, DOUBLE prices

| Field | Value |
|---|---|
| **Status** | PR Open |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5, §8.6 ; `DESIGN.md` §3.2, §3.3, §6.1 ; ADR-0003 |
| **Applicable Amendments** | AMD-0012, AMD-0018, AMD-0019 |
| **Base SHA** | main at the commit introducing AMD-0019 |
| **Branch** | `wo/0013-materialisation-basis-corrections` |
| **Depends on** | WO-0007 (merged) — this corrects it; see DELIVERY-CHAIN §9 |
| **Parallel group** | P0-E2 — **may run concurrently with WO-0008**, which it shares no file with |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0013/` |

## 1. Objective
Four corrections to the `bars_raw` → `bars` seam, all found in the P0-D
review (AMD-0019):

1. a `bar_flags` row **no longer withholds** a symbol-day from `bars`, and
   no source substitution fills a flagged day;
2. a dividend amount is brought onto the **price basis** before it is used
   in the adjustment factor, with each source's basis **measured** and
   recorded;
3. price columns are stored **DOUBLE**, as DESIGN §3.2 specifies;
4. the membership-boundary warning separates the benign case from the
   AMD-0018 §2F hazard, and a judging failure after the raw write records
   `quarantined` rather than `failed`.

**No provider call is made by any part of this Work Order.** Every
correction re-materialises from data already in `bars_raw`, `splits` and
`dividends`.

## 2. Scope (exhaustive)
```
argus/data/schema.py        modify  dividends: add `basis TEXT NOT NULL` (values 'as_paid' | 'split_adjusted'), PK unchanged
                                      (symbol, date, source)
                                    bars and etf_bars: every price column and adj_close stored DOUBLE (float64), not float32
                                    bump SCHEMA_VERSION to 5
                                    (count/version assertions in tests/test_schema.py and tests/test_cli.py follow under
                                     DELIVERY-CHAIN §9 ruling 9 — in scope, no ruling needed)
argus/data/adjust.py        modify  (a) PUBLICATION: withhold a day whose ingest_log.status = 'quarantined'; NEVER withhold a
                                        symbol-day for carrying a bar_flags row (AMD-0019 §2A — AMD-0018 §2A's exclusion
                                        clause is withdrawn). Remove the cross-source substitution path entirely: source
                                        precedence alone decides which source supplies a symbol's series, and a flag does
                                        not re-open that choice
                                    (b) DIVIDEND BASIS: before use in the factor, divide an 'as_paid' cash_amount by the
                                        cumulative split ratio applied to that symbol between the ex-date and the
                                        adjustment reference date — the same cumulative factor that split-adjusts the
                                        prices; use a 'split_adjusted' amount as stored. A dividend whose source basis is
                                        not recorded raises, never defaults (AMD-0019 §2B)
                                    (c) dtype: build price columns as pl.Float64 end to end; no float32 cast anywhere
                                    (d) MaterialiseReport: replace bars_outside_membership with
                                          n_bars_before_first_membership            (counted, never warned — pre-entry
                                                                                     history is required by the features)
                                          n_bars_after_final_end_without_continuity  (warned per symbol — the §2F hazard;
                                                                                     ticker_renames.yaml continuity suppresses)
                                        and add n_members_flagged per date to the published coverage figures (CI-8,
                                        DESIGN §6.1)
                                    (e) AGGREGATES exclude, series do not: flagged symbol-days are excluded from the
                                        equal-weight means feeding composites / market_daily / sector_daily, and the
                                        excluded count is reported per date. A symbol's own series keeps the row
argus/data/ingest_polygon.py modify  _judge raising AFTER the bars_raw write records ingest_log.status='quarantined' with the
                                     exception in detail — the rows ARE stored and unpublished, which is what quarantine
                                     means. 'failed' stays reserved for nothing-fetched, so the backfill does not re-fetch
                                     rows it already holds (AMD-0019 §2E)
argus/data/store.py         modify  resolve AMD-0019 §2H: state what `_stdlog` emits and whether it passes the structlog
                                     redaction processor. If nothing requires it, REMOVE it. If something does, route it
                                     through redaction. One structured JSON channel to stdout (PID §8.3, CI-7)
argus/commands/store_cmds.py modify  `migrate-store` (or the existing init-store path) performs the in-place column-type
                                     widening and the dividends.basis backfill idempotently, from stored data only, with
                                     before/after row counts printed per table
tests/test_adjust.py        modify  add the §5 tests
tests/test_schema.py        modify  count/version assertions only (ruling 9)
tests/test_cli.py           modify  count/version assertions only (ruling 9)
```

## 3. Exclusions
No provider code and **no network call of any kind**. No Polygon, yfinance,
FMP or IBKR client changes. No validation-rule changes (`validate.py` is
untouched — the jump rule itself is correct; only what publication does
with its output changes). No universe or membership code. No feature
computation. No `docs/` changes by the Implementer.

## 4. Design constraints
PID §8.5, §8.9 and the ADR-0008 portability constraints.

**The dividend basis is established by measurement, never by assumption.**
For each source, pick a symbol with a split inside that source's window and
dividends on both sides of it, and compare the stored `cash_amount` against
the amount the company declared for that ex-date. Record the symbol, the
split, both amounts and the conclusion in
`docs/evidence/WO-0013/dividend-basis.md`. **A source whose basis cannot be
established is a stop, not a default** — the last design built on an
unverified vendor assumption cost four Work Orders (ADR-0003, AMD-0013).

The migration runs on stored data: no re-fetch, no re-ingest. It must be
idempotent and must not alter a single `bars_raw` row (CI-9).

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_adjust.py::test_flagged_symbol_day_is_published` | a member with a `jump_unexplained` flag on day D has its row in `bars` for D, with the flag joinable from `bar_flags` | asserts the row is present — this is the AMD-0018 §2A defect, pinned |
| `test_adjust.py::test_quarantined_day_is_not_published` | a day with `status='quarantined'` publishes no rows | the other half of the rule: day-level verdicts still withhold |
| `test_adjust.py::test_no_cross_source_substitution` | Polygon flagged on day D and yfinance holding day D → the published row is **Polygon's**, and its `source` says so | asserts source identity, not just presence |
| `test_adjust.py::test_as_paid_dividend_is_divided_by_cumulative_split` | a $1.00 `as_paid` dividend before a 2:1 split contributes a factor computed on $0.50; a `split_adjusted` $0.50 contributes the same | both branches on `basis`, same arithmetic result |
| `test_adjust.py::test_unrecorded_dividend_basis_raises` | a `dividends` row with a null/unknown `basis` raises rather than defaulting | asserts the raise |
| `test_adjust.py::test_prices_are_float64` | every price column and `adj_close` in `bars` and `etf_bars` has dtype `Float64`, and a Polygon close round-trips bit-exactly | dtype assertion + exact equality |
| `test_adjust.py::test_membership_boundary_counts_are_separated` | pre-entry history lands in `n_bars_before_first_membership` and raises no warning; a post-final-end run with no rename continuity warns per symbol | both counters, and the warning list |
| `test_adjust.py::test_flagged_day_excluded_from_aggregate_not_series` | a flagged member-day is absent from that date's equal-weight composite and the excluded count is reported, while the symbol's own `bars` row is present | both halves in one assertion pair |
| `test_ingest_polygon.py::test_judge_failure_records_quarantined` | `_judge` raising after the raw write → `status='quarantined'`, rows present in `bars_raw`, exception text in `detail` | asserts status **and** row presence |

## 6. Acceptance criteria
- **AC1** — Re-materialising the host store publishes every previously withheld flagged symbol-day and makes **no** provider call (operator check: row-count delta per table, the count of flagged symbol-days now published against the 128 measured at WO-0007, and a network-call count of zero).
- **AC2** — `docs/evidence/WO-0013/dividend-basis.md` states, with the comparison that establishes it, whether Polygon and yfinance store `as_paid` or `split_adjusted` amounts. Both `dividends.basis` values are populated with no nulls (operator check: count per source per basis).
- **AC3** — For a symbol with a split and dividends on both sides, `adj_close` is recomputed and the **change from the pre-correction value is reported** (operator check: the symbol, the split ratio, and the before/after `adj_close` on three dates — the magnitude AMD-0019 §1(b) predicts, measured).
- **AC4** — Every price column and `adj_close` in `bars` and `etf_bars` is `DOUBLE`; WO-0007 AC2's original wording now holds **exactly** for published rows (operator check: the 20-symbol sample re-run, reporting identical-row count and the unpublished count, which §2A should have reduced from 48,069).
- **AC5** — `MaterialiseReport` reports the two separated counters; the warned count is far below WO-0007's 3,403 and every warned symbol is named (operator check: both figures and the warned list).
- **AC6** — AMD-0019 §2H answered in `docs/evidence/WO-0013/logging.md`: what `_stdlog` emitted, whether it passed redaction, and what was done. One structured JSON channel to stdout afterwards (Auditor check).
- **AC7** — `SCHEMA_VERSION` is 5; the migration is idempotent and loses no data (operator check on a copy: row counts per table before and after, and a second run changing nothing). **`bars_raw` is byte-identical before and after** (operator check: checksum — CI-9).
- **AC8** — Non-vacuity, mandatory (CI-6): file two mutation runs, each failing the intended test — (a) restoring the flag exclusion in publication makes `test_flagged_symbol_day_is_published` fail; (b) using an `as_paid` amount without the split division makes `test_as_paid_dividend_is_divided_by_cumulative_split` fail. Those are the two defects this Work Order exists to fix.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC2, AC3, AC4, AC5, AC7 outputs),
`dividend-basis.md`, `logging.md`, and the AC8 mutation runs.

## 8. Implementer notes
The flag-exclusion clause this removes was an Architect error, recorded as
such in AMD-0019 §1(a): a symbol-level advisory was being used as a filter,
and the measured evidence — 51 of 51 flagged symbol-days agreeing with an
independent source to 1e-5 — says those were real price moves. Do not
reintroduce any form of "drop the suspicious row": the correct handling is
to carry the flag and let the consumer decide, and the aggregates are the
only consumer that excludes.

The cumulative split factor for the dividend division is the **same**
factor already computed to split-adjust that symbol's prices. Reuse it;
computing it a second time by another route is how the two drift apart.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
