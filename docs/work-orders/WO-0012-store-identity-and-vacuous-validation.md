# WO-0012 — Store relocation safety and the vacuous-jump-rule defect

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5 ; `DESIGN.md` §3.2, §3.3 ; ADR-0008 |
| **Applicable Amendments** | AMD-0017 |
| **Base SHA** | main at Closure of WO-0004 (by reference, DELIVERY-CHAIN §6.3) |
| **Branch** | `wo/0012-store-identity-and-vacuous-validation` |
| **Depends on** | WO-0004 (shares `argus/data/validate.py`; sequenced after it to avoid a file conflict, **not** because of a logical dependency) |
| **Parallel group** | P0-D2 — may run concurrently with WO-0006 and WO-0007 |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0012/` |

## 1. Objective
Make a relocated store **fail loudly instead of reading the wrong data**,
and make a validation rule that cannot fire **a failure instead of a silent
pass**. Both found by the Delivery Controller during WO-0004's live
backfill.

## 2. Scope (exhaustive)
```
argus/data/schema.py     modify  add DDL for `store_meta (key TEXT PRIMARY KEY, value TEXT)`; bump SCHEMA_VERSION to 3
argus/data/store.py      modify  init_schema(): after creating the parquet views, record
                                   store_meta['store_dir'] = str(self.store_dir.resolve())
                                 add class StoreRelocatedError(RuntimeError)
                                 connect(read_only): compare store_meta['store_dir'] with self.store_dir.resolve():
                                   - equal, or store_meta absent on a brand-new store  -> proceed
                                   - different and read_only=False -> recreate every parquet view against the current
                                     store_dir, update the record, log one WARNING naming both paths, proceed
                                   - different and read_only=True  -> raise StoreRelocatedError naming both paths and
                                     stating that a read-write `argus init-store` repairs it
argus/data/validate.py   modify  validate_day() distinguishes a rule that PASSED from a rule that COULD NOT BE APPLIED:
                                   - add fields n_without_prior_close: int and jump_rule_applied: bool to ValidationResult
                                   - for a non-initial date (one with any earlier row in bars_raw), if prior_close is
                                     missing for > 5% of the day's members, the day is REJECTED with reason
                                     'jump rule inapplicable: prior_close missing for N of M members'
                                   - jump_rule_applied is False only on a genuine first-ever ingest date, where it is
                                     recorded as such rather than counted as a pass
argus/commands/store_cmds.py  modify  `init-store` prints the recorded store_dir and, when it repaired a relocated
                                      store, says so explicitly
tests/test_store.py      modify  add the three §5 store tests
tests/test_validate.py   modify  add the two §5 validation tests
```

## 3. Exclusions
No provider code, no ingest code, no adjustment logic, no CLI beyond the
`init-store` message, no other table's DDL, no changes to the coverage or
zero-volume or split rules, no data migration, no changes under `docs/` by
the Implementer.

## 4. Design constraints
PID §8.5, §8.9 and the ADR-0008 portability constraints. The relocation
check must not require network or secrets and must add no measurable
latency to `connect()` — one small `SELECT` against a local table. A
brand-new store with no `store_meta` row is not a relocation: treat a
missing record as first use and write it. `StoreRelocatedError`'s message
names both paths and the remedy; it must not include anything beyond
filesystem paths already visible to the operator.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_store.py::test_relocated_store_read_only_raises` | copying an initialised store to a new directory and opening it `read_only=True` raises `StoreRelocatedError` naming both paths | asserts the exception type and that both paths appear in the message |
| `test_store.py::test_relocated_store_read_write_repairs` | the same copy opened read-write recreates the views, updates `store_meta`, and a subsequent read returns the **new** directory's rows | asserts row counts from the new directory, not the old |
| `test_store.py::test_relocated_store_does_not_read_old_path` | after relocation and repair, rows written only into the **old** directory are **not** visible | fails if the view still globs the old path — this is the silent-wrong-data case |
| `test_validate.py::test_missing_prior_close_rejects_non_initial_day` | with > 5% of members lacking `prior_close` on a date that has earlier rows, the day is rejected with the inapplicable-jump-rule reason | asserts `ok is False` and the reason string |
| `test_validate.py::test_first_ever_date_records_rule_not_applied` | on a genuine first ingest date, `jump_rule_applied is False` and the day is **not** rejected for that reason | asserts both fields |

## 6. Acceptance criteria
- **AC1** — A relocated store opened read-only raises `StoreRelocatedError`; opened read-write it repairs itself and reads the new directory (tests 1–3).
- **AC2** — `test_relocated_store_does_not_read_old_path` passes: after repair, data present only in the old directory is invisible (the silent-wrong-data case).
- **AC3** — A non-initial day missing `prior_close` for > 5% of members is **rejected** with the inapplicable-jump-rule reason (test 4). A genuine first date records `jump_rule_applied = False` without rejecting (test 5).
- **AC4** — Non-vacuity, mandatory (CI-6): with the §5 tests in place, (a) removing the relocation comparison makes tests 1–3 fail, and (b) reverting `validate_day` to treat missing `prior_close` as a vacuous pass makes test 4 fail. File both mutation runs and their failure output.
- **AC5** — `argus init-store` on the host prints the recorded `store_dir`; copying the store and re-running reports the repair explicitly (operator check: both outputs filed, paths as filesystem paths only).
- **AC6** — `SCHEMA_VERSION` is 3, `init-store` remains idempotent, and an existing store upgrades without data loss (operator check on a copy of the host store: row counts per table before and after).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC5, AC6 outputs), and the AC4 mutation runs.

## 8. Implementer notes
The defect this fixes was found in practice: a copied store kept
`read_parquet` globs pointing at the original directory, so the views
returned the seed directory's empty contents and `prior_close` came back
empty — which made the jump rule unable to fire while nothing reported
that. The dangerous variant is a relocation where the old path still holds
**stale but populated** data: then the views return wrong rows rather than
none. Test 3 is the one that pins that case, so do not weaken it.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
