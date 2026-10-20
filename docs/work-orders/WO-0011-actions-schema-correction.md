# WO-0011 — Corporate-actions schema correction: `splits` and `dividends`

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5 ; `DESIGN.md` §3.2, §3.3 |
| **Applicable Amendments** | AMD-0012, AMD-0013 |
| **Base SHA** | main at approval of this Work Order (the commit introducing this file) |
| **Branch** | `wo/0011-actions-schema-correction` |
| **Depends on** | none (WO-0002 is merged at `bdce04d`) |
| **Parallel group** | P0-B2 — **blocks the WO-0004 and WO-0005 deltas**, which need these tables on `main` |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0011/` |

## 1. Objective
Replace the merged `adjustments` table with `splits` and `dividends`, each
keyed `(symbol, date, source)` with a `NOT NULL` measure, so a split and a
dividend on the same `(symbol, date)` both survive — from each source
independently. This is the AMD-0012 defect fix, delivered as a new Work
Order because WO-0002 is closed and DELIVERY-CHAIN §9 forbids reopening one
(AMD-0013 §2A).

## 2. Scope (exhaustive)
```
argus/data/schema.py     modify  remove the `adjustments` DDL; add:
                                   splits    (symbol TEXT, date DATE, ratio DOUBLE NOT NULL, source TEXT,
                                              PRIMARY KEY (symbol, date, source))
                                   dividends (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, source TEXT,
                                              PRIMARY KEY (symbol, date, source))
                                 bump SCHEMA_VERSION to 2
argus/data/store.py      modify  replace any adjustments accessor with
                                   read_splits(symbols: list[str] | None, start: date, end: date) -> pl.DataFrame
                                   read_dividends(symbols: list[str] | None, start: date, end: date) -> pl.DataFrame
                                 (same parameterised-SQL and symbol-validation rules as read_bars)
tests/test_schema.py     modify  update the table-name list to 19; add test_actions_tables_keyed_by_source (§5)
tests/test_store.py      modify  add test_read_splits_and_dividends (§5)
```
Migration: `init_schema()` is create-if-not-exists and the store on the
host holds no production rows in `adjustments` yet, so no data migration is
required. If `adjustments` exists, `init_schema()` leaves it in place and
untouched; **do not** write a dropper — an unused empty table is harmless
and dropping tables is not in this Work Order's scope.

## 3. Exclusions
No provider code (`argus/data/providers/**`), no ingest code, no adjustment
or materialisation logic, no CLI changes, no changes to `bars`, `bars_raw`,
`etf_bars` or any other table's DDL, no data migration or table drops, no
changes under `docs/` by the Implementer.

## 4. Design constraints
DESIGN §3.2/§3.3 as amended by AMD-0012, and PID §8.9 including the
ADR-0008 portability constraints. Both measures are `NOT NULL`: a row
exists only where there is a value. `SCHEMA_VERSION = 2`, recorded by
`init_schema()` in `schema_version` without destroying the version-1 row.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_schema.py::test_all_design_tables_present` | 19 tables/views exist, `splits` and `dividends` among them, `adjustments` not required | hard-coded list of 19 names |
| `test_schema.py::test_actions_tables_keyed_by_source` | a split row **and** a dividend row for the same `(symbol, date)` coexist; two sources' rows for the same `(symbol, date)` both persist; four upserts → four rows | row counts after four upserts, two per table |
| `test_schema.py::test_actions_measures_not_null` | inserting a NULL `ratio` or NULL `cash_amount` is rejected | expects an exception |
| `test_store.py::test_read_splits_and_dividends` | both readers filter by symbol and date range and return the canonical columns | row counts + column set |
| `test_schema.py::test_schema_version_is_2` | `init_schema()` records version 2 and remains idempotent | value + row count |

## 6. Acceptance criteria
- **AC1** — `argus init-store` on a fresh store creates 19 tables/views including `splits` and `dividends` (test + operator check listing `SHOW TABLES`).
- **AC2** — The same-date split-and-dividend case and the two-source case both persist (test_actions_tables_keyed_by_source).
- **AC3** — `NOT NULL` is enforced on both measures (test_actions_measures_not_null).
- **AC4** — Non-vacuity, mandatory: changing either PRIMARY KEY back to `(symbol, date)` makes `test_actions_tables_keyed_by_source` fail. File both mutation runs and their failure output.
- **AC5** — `argus init-store` run twice changes nothing and `schema_version` shows version 2 once (test + operator check).
- **AC6** — Re-running against a store that already contains an `adjustments` table succeeds without error and without dropping it (operator check on a copy of the host store).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC5, AC6 outputs), and the AC4 mutation runs.

## 8. Implementer notes
This is a schema correction, not a redesign: do not alter any other
table, do not add indexes, do not write a migration. The consuming code in
WO-0004, WO-0005 and WO-0007 is changed by their own Work Orders, so
nothing outside §2 should need to compile differently.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
