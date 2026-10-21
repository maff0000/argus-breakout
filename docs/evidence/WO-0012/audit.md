# WO-0012 — Audit record

Fresh Auditor, whole branch, audited SHA `48eb7a5df5df89e4a6831eac201e48620ef56508`, base `4321d92`.

## Verdict block (as returned, summarised fields verbatim)
```
AUDIT_VERDICT: GREEN
work_order: WO-0012
base_sha: 4321d92eeea6546a8095ecda3f22e5065837cae4
commit_sha: 48eb7a5df5df89e4a6831eac201e48620ef56508
scope_fidelity: yes (tests/test_schema.py and tests/test_cli.py are outside §2: a necessary consequence, see O1)
offline_tests_pass: yes (226 passed, no .env)
non_vacuity_established: yes (mutations A, B, C)
gitleaks_clean: yes (84 commits)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: yes   AC2_verified: yes   AC3_verified: n/a (moved to WO-0004, AMD-0018 2G; validate.py and test_validate.py diff empty)
AC4_verified: yes   AC5_verified: yes   AC6_verified: yes
findings: none
confidence: high
```

## Non-vacuity (AC4), on `git archive` copies, `argus` imported from the copy (control: 13 passed)
- **A — remove the relocation comparison** (`if True: return`): `test_relocated_store_read_only_raises`, `test_relocated_store_read_write_repairs`, `test_relocated_store_does_not_read_old_path` all fail (3 failed, 10 passed). AC4 literal.
- **B — restore the original defect** (`CREATE OR REPLACE VIEW` → `CREATE VIEW IF NOT EXISTS`): repair and does-not-read-old-path fail (2 failed).
- **C — repair updates `store_meta` but skips view recreation:** tests 2 and 3 fail (`assert 1 == 4`; `['OLD','ONLYOLD'] == ['OLD']`), the silent-wrong-data case.
- Tests 2 and 3 repair through a plain read-write `connect()`, not `init_schema`. (The Implementer's first version repaired via `init_schema`, which left test 3 alive under mutation A; the Delivery Controller changed both tests before commit so AC4 holds literally.)

## Observations (from the Auditor)
- **O1** `tests/test_schema.py` (`store_meta` in DESIGN_TABLES, 20→21, version 3→4) and `tests/test_cli.py` ("21 tables") are outside §2; mechanical consequence of the mandated DDL and version; Architect to ratify.
- **O2** A pre-schema-4 store copied before `init-store` runs once is undetectable (spec §4's own design; pinned by `test_fresh_and_legacy_store_are_not_relocations`).
- **O3** Repair runs in `connect()` for any read-write connect, transactionally, with one WARNING. Matches §2.
- **O5** The CLI "repaired" line has no automated test (exercised by the operator check).
- Error message holds filesystem paths and the remedy only; `connect()` makes one local SELECT, no network or secret.
