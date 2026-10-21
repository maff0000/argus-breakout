# WO-0012 — Store relocation safety and the vacuous-jump-rule defect

| Field | Value |
|---|---|
| **Status** | In Progress |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5 ; `DESIGN.md` §3.2, §3.3 ; ADR-0008 |
| **Applicable Amendments** | AMD-0017, AMD-0018 |
| **Base SHA** | 4321d92eeea6546a8095ecda3f22e5065837cae4 |
| **Branch** | `wo/0012-store-identity-and-vacuous-validation` |
| **Depends on** | WO-0004 — a real dependency now: `bar_flags` takes `SCHEMA_VERSION = 3` in the WO-0004 delta and `store_meta` takes **4** here (AMD-0018 §2G) |
| **Parallel group** | P0-D2 — may run concurrently with WO-0006 and WO-0007 |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0012/` |

## 1. Objective
Make a relocated store **fail loudly instead of reading the wrong data**.

**Narrowed by AMD-0018 §2G.** The second half of this Work Order — making
a validation rule that cannot fire a failure rather than a silent pass
(AMD-0017 §2B) — **moves into the WO-0004 delta**, because WO-0004 is
rewriting `validate_day` anyway and one Work Order rewrites a function
while two collide over it. That obligation is unchanged in substance and
still binds; it is simply discharged there. Nothing in `argus/data/`
outside `schema.py` and `store.py` is this Work Order's business.

## 2. Scope (exhaustive)
```
argus/data/schema.py     modify  add DDL for `store_meta (key TEXT PRIMARY KEY, value TEXT)`; bump SCHEMA_VERSION to 4
                                 (3 is taken by `bar_flags` in the WO-0004 delta — AMD-0018 §2G)
argus/data/store.py      modify  init_schema(): after creating the parquet views, record
                                   store_meta['store_dir'] = str(self.store_dir.resolve())
                                 add class StoreRelocatedError(RuntimeError)
                                 connect(read_only): compare store_meta['store_dir'] with self.store_dir.resolve():
                                   - equal, or store_meta absent on a brand-new store  -> proceed
                                   - different and read_only=False -> recreate every parquet view against the current
                                     store_dir, update the record, log one WARNING naming both paths, proceed
                                   - different and read_only=True  -> raise StoreRelocatedError naming both paths and
                                     stating that a read-write `argus init-store` repairs it
argus/commands/store_cmds.py  modify  `init-store` prints the recorded store_dir and, when it repaired a relocated
                                      store, says so explicitly
tests/test_store.py      modify  add the three §5 store tests
```

## 3. Exclusions
No provider code, no ingest code, no adjustment logic, no CLI beyond the
`init-store` message, no other table's DDL (`bar_flags` is WO-0004's), **no
changes to `argus/data/validate.py` or `tests/test_validate.py` at all**
(AMD-0018 §2G), no data migration, no changes under `docs/` by the
Implementer.

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

_(The two `test_validate.py` rows moved to WO-0004 §5 with the scope — AMD-0018 §2G.)_

## 6. Acceptance criteria
- **AC1** — A relocated store opened read-only raises `StoreRelocatedError`; opened read-write it repairs itself and reads the new directory (tests 1–3).
- **AC2** — `test_relocated_store_does_not_read_old_path` passes: after repair, data present only in the old directory is invisible (the silent-wrong-data case).
- **AC3** — _Moved to WO-0004 AC2/§5 with the `validate.py` scope (AMD-0018 §2G)._
- **AC4** — Non-vacuity, mandatory (CI-6): removing the relocation comparison makes tests 1–3 fail. File the mutation run and its failure output. _(The `validate_day` mutation moved to WO-0004 AC4.)_
- **AC5** — `argus init-store` on the host prints the recorded `store_dir`; copying the store and re-running reports the repair explicitly (operator check: both outputs filed, paths as filesystem paths only).
- **AC6** — `SCHEMA_VERSION` is 4 (AMD-0018 §2G), `init-store` remains idempotent, and an existing store upgrades without data loss (operator check on a copy of the host store: row counts per table before and after).

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

The downstream half of that story — the rule that could not fire being
counted as a pass — is WO-0004's now (AMD-0018 §2G). Do not reimplement it
here, and do not touch `validate.py`: if the merged WO-0004 appears not to
carry it, report that rather than fixing it in this branch.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
