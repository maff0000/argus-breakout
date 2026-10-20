# WO-0011 — Audit record

Fresh Forge Auditor, ssh-only, detached audit worktree at the audited SHA `647e1aa930c385f754593ef38b03668514eca53c` (whole branch against base `19d9ca0`).

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0011
base_sha: 19d9ca0ee0a441a1f74cd9030e18f2f94fecf517
commit_sha: 647e1aa930c385f754593ef38b03668514eca53c
scope_fidelity: yes (tests/test_cli.py changed by one assertion, "18 tables" -> "19 tables"; judged covered by standing ruling 6, procedural and non-blocking)
offline_tests_pass: yes (42 passed, no .env present; also 42 passed under `unshare -n`)
non_vacuity_established: yes (AC4 and AC3 mutations all fail)
gitleaks_clean: yes (52 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: yes
AC2_verified: yes
AC3_verified: yes
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes
findings: none
confidence: high
```

## Out-of-scope observations (as returned)
1. Ruling 6 conditions hold for `tests/test_cli.py` (confined to one assertion; as strong as before; 19 is the count §2 changes; the Implementer named the test). Delivery Controller records it in `spec-gaps.md` (done).
2. The `init_schema()` guard change (NOT EXISTS on this version, not on emptiness) is correct and required by WO §4. No test covers the v1→v2 upgrade path: reverting the guard to the old emptiness check leaves all 42 tests passing; the operator check shows the guard working. Observation only; a v1→v2 test would be worth adding later.
3. The `init_schema` docstring ("record schema_version once") is slightly stale. Cosmetic.
4. AC4's failure mode is a DuckDB BinderException (the upsert's `ON CONFLICT (symbol,date,source)` target no longer matches a key), not a row-count assertion. A mutant that survives the conflict target but still collapses sources (PRIMARY KEY (symbol,date) plus UNIQUE (symbol,date,source)) fails with a ConstraintException on duplicate key, so row-level behaviour is covered too.

## Non-vacuity table (as returned; mutations on `git archive` copies outside the worktree)
| Mutation | Result |
|---|---|
| MUT1 `splits` PK -> (symbol,date) | FAILED, BinderException (conflict target not a key) |
| MUT2 `dividends` PK -> (symbol,date) | FAILED, same |
| MUT3 PKs -> (symbol,date,ratio) / (symbol,date,cash_amount) (source omitted) | FAILED, same |
| MUT4 both PKs removed | FAILED, same |
| MUT5 PK (symbol,date) plus UNIQUE (symbol,date,source) | FAILED, ConstraintException duplicate key (AAA, 2024-06-10) |
| `ratio` made nullable | `test_actions_measures_not_null` FAILED (DID NOT RAISE) |
| `cash_amount` made nullable | `test_actions_measures_not_null` FAILED (DID NOT RAISE) |
| `SCHEMA_VERSION` = 1 | 1 failed, 4 passed |
| init_schema guard reverted to emptiness check | 42 passed (upgrade path untested; observation 2) |

## Method (as reported)
Identity of commit confirmed; `git diff --stat 19d9ca0..647e1aa` = 7 files (schema.py, store.py, test_schema.py, test_store.py in §2; test_cli.py one assertion; DELIVERY-LOG.md and the WO header fields clerical); no §3 exclusion touched; identity check clean; 42 passed with and without network; gitleaks clean; hygiene and ADR-0008 greps empty; DDL, `SCHEMA_VERSION`, readers (parameterised, `_check_symbols`) match the WO; AC1/AC5/AC6 operator checks reproduced independently (AC6 on a store built with base-SHA code, one `adjustments` row retained, versions [(1),(2)]).
