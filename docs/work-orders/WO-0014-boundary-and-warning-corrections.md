# WO-0014 — Boundary and warning corrections: same-company tails, publication allowlist, basis-normalised comparisons

| Field | Value |
|---|---|
| **Status** | PR Open |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5 ; `DESIGN.md` §3.3, §6.1 |
| **Applicable Amendments** | AMD-0018, AMD-0019, AMD-0021 |
| **Base SHA** | main at Closure of WO-0013 |
| **Branch** | `wo/0014-boundary-and-warning-corrections` |
| **Depends on** | WO-0013 (merged — this corrects it) |
| **Parallel group** | P0-F2 — **may run concurrently with WO-0009**, which it shares no file with |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0014/` |

## 1. Objective
Four corrections from the WO-0013 review (AMD-0021), all in the
materialisation path and all **without any provider call**:

1. stop dropping the post-exit bars of companies that merely left the
   index — 118,027 bars at WO-0013 (§2B);
2. publish by **allowlist** (`status = 'ok'`) so an unjudged day can never
   reach `bars`, and make every judging failure write a log row (§2C);
3. normalise basis before comparing two sources' dividends, and divide out
   a split dated on the ex-date (§2D);
4. stop reporting an uncomputed coverage figure as `0` (§2F).

## 2. Scope (exhaustive)
```
argus/data/adjust.py          modify  (a) TAIL BOUNDARY (AMD-0021 2B, narrowing AMD-0018 2F): bound a symbol's tail only where the
                                          ticker was REASSIGNED. Discriminator is a trading gap in bars_raw across the final
                                          membership.end_date: gap <= 20 trading days -> same company, RETAIN the tail, no warning;
                                          gap > 20 trading days -> exclude the tail and warn, naming the symbol and the gap length.
                                          ticker_renames.yaml continuity still suppresses the warning. Leading history before the
                                          first start_date is retained unconditionally
                                      (b) PUBLICATION ALLOWLIST (AMD-0021 2C): admit a day only where ingest_log.status = 'ok'.
                                          Never "status <> 'quarantined'". A day with stored rows and no completed verdict is
                                          unjudged data; the remedy is `ingest revalidate`, not publication
                                      (c) dividend_disagreement (AMD-0021 2D): normalise BOTH sources to one basis with the same
                                          split_cum before comparing amounts; the 0.1%/one-cent thresholds then apply to
                                          comparable numbers
                                      (d) split on the ex-date (AMD-0021 2D): the dividend divisor takes the last bar BEFORE the
                                          ex-date, so a split effective on the ex-date is divided out (the dividend was declared
                                          before it)
                                      (e) MaterialiseReport.n_symbol_days_flag_excluded (AMD-0021 2F, CI-8): report the measured
                                          count, or NULL where not computed. NEVER 0 as a stand-in for uncomputed
argus/data/ingest_polygon.py  modify  revalidate_range: a judging failure writes an ingest_log row (status='quarantined', exception
                                      in detail) instead of returning silently in the results (AMD-0021 2C). A path that fails
                                      without recording lets a day keep a stale verdict indefinitely
argus/commands/adjust_cmds.py modify  the CLI line printing n_symbol_days_flag_excluded handles NULL (prints "not computed")
tests/test_adjust.py          modify  add the 2.5 tests
tests/test_ingest_polygon.py  modify  add the revalidate-failure test (ruling 9 as widened by AMD-0021 2G)
```

## 3. Exclusions
No provider code and **no network call of any kind**. No IBKR code
(`argus/data/providers/ibkr.py` is WO-0009's under AMD-0021 §3 — do not
touch it). No validation-rule changes in `validate.py`. No schema change
and **no `SCHEMA_VERSION` bump**. No universe or membership code. No
feature computation. No `docs/` changes by the Implementer.

## 4. Design constraints
PID §8.5, §8.9 and the ADR-0008 portability constraints. Everything
re-materialises from stored `bars_raw`, `splits` and `dividends`; **not one
`bars_raw` row may change** (CI-9, verified by checksum).

The 20-trading-day gap threshold is a named module constant carrying the
AMD-0021 §2B reasoning in a comment: a reassigned ticker's hiatus runs to
months or years, while a company leaving the index trades straight through
its `end_date`. Changeable only by Amendment.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_adjust.py::test_same_company_tail_is_retained` | a member whose `bars_raw` is continuous across its final `end_date` keeps its post-exit bars, with no boundary warning | asserts the tail rows present **and** the warning absent — the 118,027-bar defect, pinned |
| `test_adjust.py::test_reassigned_ticker_tail_is_excluded_and_warned` | a symbol with a 60-trading-day gap across the boundary loses its tail and is named in the warning with the gap length | asserts exclusion, the warning, and the reported gap |
| `test_adjust.py::test_gap_threshold_boundary` | a 20-day gap retains, a 21-day gap excludes | the boundary, both sides |
| `test_adjust.py::test_rename_continuity_suppresses_the_warning` | a mapped rename with a long gap is retained and unwarned | fails if continuity is ignored |
| `test_adjust.py::test_unjudged_day_is_not_published` | a day with `bars_raw` rows and `status='failed'` publishes **nothing** | asserts zero published rows — fails under a `<> 'quarantined'` blocklist |
| `test_adjust.py::test_only_ok_days_are_published` | `ok` publishes; `quarantined`, `failed` and an unrecognised status do not | the allowlist, including a status invented in the test |
| `test_adjust.py::test_dividend_disagreement_normalises_basis` | the same economic dividend stored `as_paid` by one source and `split_adjusted` by the other across a 2:1 split raises **no** disagreement; a genuine two-cent difference still does | both branches — fails if comparison is on raw amounts |
| `test_adjust.py::test_split_on_ex_date_is_divided_out` | a split effective on the ex-date divides the dividend; the factor matches the pre-split basis | asserts the factor value |
| `test_adjust.py::test_flag_excluded_count_is_never_a_silent_zero` | where the count is not computed the field is `None`, not `0`; where computed it equals the real count | asserts `is None` — fails if a constant 0 is reinstated |
| `test_ingest_polygon.py::test_revalidate_failure_writes_a_log_row` | `_judge` raising inside `revalidate_range` writes `status='quarantined'` with the exception in `detail` | asserts the row exists — fails on a silent return |

## 6. Acceptance criteria
- **AC1** — Re-materialising the host store **retains** the same-company tails: report the bar count recovered against WO-0013's 118,027 and the symbols recovered (AAL, AAP, ALK, K, M, WHR among them), and the remaining excluded symbols each with their gap length (operator check).
- **AC2** — Boundary warnings are reported with the two separated counters; every warned symbol is named with its gap, and each is plausibly a reassignment rather than an index exit (operator check: the list, with a one-line reason per symbol).
- **AC3** — No day with `status` other than `'ok'` contributes a row to `bars` (operator check: a join of `bars` dates against `ingest_log` statuses returning zero rows for every non-`ok` status).
- **AC4** — `dividend_disagreement` warnings fall materially from WO-0013's 228, and every remaining one is a genuine vendor amount difference, not a basis artefact (operator check: the count and the full remaining list with both amounts).
- **AC5** — `n_symbol_days_flag_excluded` is the measured count or `None`; the CLI prints "not computed" for `None` (operator check: both outputs).
- **AC6** — `bars_raw` is **byte-identical** before and after, and no provider call is made (operator check: checksum and a network-call count of zero — CI-9).
- **AC7** — Non-vacuity, mandatory (CI-6): file three mutation runs, each failing the intended test — (a) restoring the rename-continuity discriminator in place of the trading gap fails `test_same_company_tail_is_retained`; (b) restoring the `<> 'quarantined'` blocklist fails `test_unjudged_day_is_not_published`; (c) comparing raw `cash_amount` fails `test_dividend_disagreement_normalises_basis`. Those three are the defects this Work Order exists to fix.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC6 outputs), and the AC7 mutation runs.

## 8. Implementer notes
AMD-0018 §2F was written for **ticker reassignment** — STI, where the bars
after the boundary belong to a different company — and the Architect then
applied it to any membership exit, which is a different event. That is the
defect AC1 measures. Do not reintroduce rename continuity as the
discriminator: a rename is not the same thing as still trading.

The gap is measured in **trading days present in `bars_raw` for that
symbol**, not calendar days, so a holiday run does not look like a
delisting.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
