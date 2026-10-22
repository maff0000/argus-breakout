# WO-0017 — Duplicate-record guard: distinguish a second dividend from a duplicated one

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5, §8.6 ; `DESIGN.md` §3.2, §3.3 |
| **Applicable Amendments** | AMD-0019, AMD-0021, AMD-0027, AMD-0029, **AMD-0031 (delta, pre-merge)** |
| **Base SHA** | main at Closure of WO-0016 |
| **Branch** | `wo/0017-dividend-duplicate-guard` |
| **Depends on** | WO-0016 (merged — this guards an exposure it opened) |
| **Parallel group** | P0-F5 — **may run concurrently with WO-0009**; shares no file with it |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0017/` |

## 1. Objective
WO-0016 keyed `dividends` on the vendor record id so a genuine second
dividend on an ex-date is no longer discarded. That removed an **accidental
guard**: the old collapsing key also suppressed a *duplicated* record.
Two §2D hits show the exposure — **TEL 2024-11-22 (1.30 against 0.65)** and
**SKYD 2026-09-15 (0.05 against 0.10)**, both **exact 2× multiples**, which
is the duplicate signature rather than the omission one.

Restore the guard deliberately, on payload fields rather than by
collapsing:

1. store `declaration_date` and `frequency`, which are what separate a
   second dividend from a repeat;
2. deduplicate before summing;
3. stop §2D preferring the larger total where the ratio is an integer
   multiple;
4. **attribute TEL and SKYD from raw payloads** — neither was ever fetched.

## 2. Scope (exhaustive)
```
argus/data/schema.py            modify  dividends: add `declaration_date DATE NULL`, `frequency INT NULL`;
                                          PK unchanged (symbol, date, source, vendor_id);
                                          bump SCHEMA_VERSION to 7
argus/data/providers/polygon.py modify  dividends(): carry `declaration_date` and `frequency` through from the
                                          payload (both present on every record — WO-0015 evidence)
argus/data/providers/bootstrap.py modify  yfinance: both fields NULL (not supplied)
argus/data/adjust.py            modify  (a) RESOLVE BEFORE SUMMING (AMD-0031 §2A, replacing AMD-0029 §2B).
                                            Records differing in cash_amount, declaration_date OR frequency are
                                            DISTINCT dividends and are summed.
                                            Records identical in all three, differing only in vendor_id, are
                                            AMBIGUOUS — NOT duplicates: TEL 2024-11-22 (a duplicate) and
                                            DVN 2024-09-13 (a genuine fixed + variable pair, both 0.22, declared
                                            2024-08-06, frequency 4) share the signature exactly, so no payload
                                            field separates them. Resolve against the OTHER source's
                                            basis-normalised total for that (symbol, date):
                                              within 1c of the SINGLE amount -> duplicate, collapse
                                              within 1c of the SUM           -> genuine, keep both
                                              neither, or no second source   -> COLLAPSE, warn, and COUNT it
                                            The default collapses because an overstated dividend shrinks historical
                                            adj_close and so INFLATES measured returns (AMD-0031 §2B).
                                            Needs NO vendor call: both sources' rows are already in `dividends`.
                                            Record each ambiguous group's resolution and its evidence in
                                            MaterialiseReport.warnings. Where a source supplies neither
                                            declaration_date nor frequency, fall back to cash_amount equality for
                                            that source and warn the resolution was weakened
                                        (b) §2D NARROWED (AMD-0029 §2C): the larger-total rule does NOT apply where
                                            one source's total is an integer multiple of the other's within one
                                            cent. Warn, leave on source precedence, and name the pair in the
                                            materialise report for attribution. With (a) resolving DVN as genuine
                                            this fires on 12 pairs (the FCX omissions, R9), not 13
                                        (c) MaterialiseReport: add `n_ambiguous_groups_resolved_by_default`,
                                            REPORTED with every run and not merely logged (AMD-0031 §2B)
argus/data/store.py             modify  the migration backfills the two columns NULL and is idempotent, printing
                                          before/after counts; a re-run of `ingest polygon-actions` populates them
argus/diagnostics/dividends.py  modify  the raw report also records `declaration_date` and `frequency` per record
                                          (it already prints the payload verbatim; this surfaces them in the summary)
tests/test_adjust.py            modify  add the §5 tests
tests/test_polygon_client.py    modify  add the two-field carry-through test
tests/test_schema.py            modify  count/version assertions only (ruling 9 as widened, AMD-0021 §2G)
tests/test_cli.py               modify  count/version assertions only (ruling 9)
```

## 3. Exclusions
No rename work (closed, AMD-0027 §2E) and `renames.py` untouched. No
`providers/ibkr.py`, `reconcile.py` or `pipeline.py` — those are WO-0009's.
No validation-rule change. No feature computation. No `docs/` by the
Implementer.

**Do not widen the dedupe beyond §2A's three fields.** Deduplicating on
`cash_amount` alone would discard a genuine pair of equal special
dividends; that is the failure this Work Order exists to avoid in the other
direction.

## 4. Design constraints
PID §8.5, §8.6, §8.9 and ADR-0008's portability constraints. The two
attribution fetches are **two Polygon calls** through the existing pacer,
with the key never printed. Everything else re-materialises from stored
data: **no `bars_raw` row may change** (CI-9, checksum).

Record the raw payloads **verbatim** in the evidence, to the WO-0013
`dividend-basis.md` standard: the question is what the vendor actually
sent, and a paraphrase is not a measurement.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_polygon_client.py::test_declaration_date_and_frequency_carried` | both fields arrive from a fixture payload | asserts both values |
| `test_adjust.py::test_duplicate_record_is_deduplicated` | two records with the same amount, declaration date and frequency but different ids sum as **one** | asserts the factor uses one, not two — the TEL exposure, pinned |
| `test_adjust.py::test_genuine_pair_survives_dedupe` | PGR's real pair — 0.10 freq 4 declared 2025-12-08, and 13.50 freq 1 declared 2025-12-05 — sums to **13.60** | asserts 13.60; fails if the dedupe is too aggressive, which is the opposite failure |
| `test_adjust.py::test_equal_specials_with_different_declarations_both_count` | two 0.50 records with **different** declaration dates both count | asserts 1.00; fails if dedupe keys on amount alone |
| `test_adjust.py::test_integer_multiple_does_not_trigger_larger_wins` | totals of 0.65 and 1.30 leave source precedence untouched and warn | asserts the chosen total **and** the warning |
| `test_adjust.py::test_non_multiple_omission_still_takes_larger` | 0.075 against 0.15 is 2× → **excluded** by §2C; 0.075 against 0.20 still takes the larger | both sides of the narrowing, including that FCX's exact doubling now falls out |
| `test_adjust.py::test_null_fields_weaken_dedupe_and_warn` | a source with NULL declaration/frequency dedupes on amount alone **and** warns it was weakened | asserts the warning |
| `test_adjust.py::test_ambiguous_group_resolved_genuine_by_second_source` | **DVN's shape** — two identical-signature records at 0.22 with the other source at 0.44 → both count, total **0.44** | asserts 0.44; the case AMD-0029's rule got wrong |
| `test_adjust.py::test_ambiguous_group_resolved_duplicate_by_second_source` | **TEL's shape** — other source equals **one** record → collapse to 0.65 | asserts 0.65: same code path, opposite verdict |
| `test_adjust.py::test_ambiguous_group_defaults_to_collapse_and_counts_it` | no second source → collapse, warn, and `n_ambiguous_groups_resolved_by_default` increments | asserts the total, the warning **and** the counter |

## 6. Acceptance criteria
- **AC1** — `docs/evidence/WO-0017/attribution.md` attributes **TEL 2024-11-22, SKYD 2026-09-15 and DVN 2024-09-13** (AMD-0031 §3) from verbatim raw payloads: record count, amounts, ids, declaration dates and frequencies, and a verdict of **duplicate**, **genuine second dividend**, or **omission**. A verdict of "cannot tell" is acceptable **only** with the payload showing why.
- **AC2** — Store-wide: the count of groups collapsed, the count of genuine multi-record ex-dates preserved, **and the count resolved by the §2B default**, reported separately. **PGR 2026-01-02 and DVN 2024-09-13 must both appear in the preserved count, not the collapsed one** (operator check).
- **AC3** — Every pair where one total is an integer multiple of the other is listed, left on source precedence, and warned (operator check: the list).
- **AC4** — `adj_close` before and after for TEL and SKYD, and **unchanged for PGR** at the −5.931% WO-0016 established (operator check: the figures). A change in PGR means the dedupe is wrong.
- **AC5** — `bars_raw` **byte-identical** before and after (checksum, CI-9); `SCHEMA_VERSION` is 7; the migration is idempotent and loses no rows.
- **AC6** — Non-vacuity, mandatory (CI-6): file **four** mutation runs — (a) removing the dedupe fails `test_duplicate_record_is_deduplicated`; (b) deduplicating on `cash_amount` alone fails both `test_genuine_pair_survives_dedupe` and `test_equal_specials_with_different_declarations_both_count`; (c) dropping the integer-multiple exclusion fails `test_integer_multiple_does_not_trigger_larger_wins`; (d) **resolving an ambiguous group as *genuine* by default** fails `test_ambiguous_group_defaults_to_collapse_and_counts_it` (AMD-0031 §3).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC2–AC5), `attribution.md` (AC1), and the AC6
mutation runs.

## 8. Implementer notes
This Work Order exists because the Architect's previous fix removed a guard
it had not noticed it was relying on. The old collapsing key discarded a
genuine second dividend — the defect WO-0016 fixed — and also suppressed a
duplicated one, which nobody had designed for.

So there are **two opposite failures** here, and the tests are deliberately
paired against both: dedupe too little and TEL's dividend doubles; dedupe
too much and PGR's 13.50 special disappears again. `test_genuine_pair_
survives_dedupe` and `test_equal_specials_with_different_declarations_both_
count` are the guards against over-correction — do not weaken them to make
the dedupe simpler.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
