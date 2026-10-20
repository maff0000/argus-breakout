# Acceptance — WO-0011 (Delegated, AMD-0013 §3)

```
WORK ORDER:        WO-0011 — Corporate-actions schema correction: splits and dividends
PARENT PID:        PID-ARGUS-0001 (Foundations)
AMENDMENTS:        AMD-0012, AMD-0013 (with AMD-0011 ruling 6)
BASE SHA:          19d9ca0ee0a441a1f74cd9030e18f2f94fecf517
AUDITED SHA:       647e1aa930c385f754593ef38b03668514eca53c
PR:                #4  https://github.com/maff0000/argus-breakout/pull/4
AUDIT VERDICT:     GREEN, no findings  (docs/evidence/WO-0011/audit.md)
ACCEPTANCE:        ACCEPTED
AUTHORITY:         AMD-0013 §3 (pre-committed acceptance for WO-0011) with the AMD-0010 §2B conditions
DATE (UTC):        2026-10-20
VERIFIED BY:       Rogue (Delivery Controller)
```

## AMD-0013 §3 conditions, each checked against the artefact
1. **GREEN whole-branch audit** — fresh Auditor at the audited SHA, whole branch against base `19d9ca0`: `AUDIT_VERDICT: GREEN`, `findings: none`.
2. **Every AC verified with filed output** — AC1/AC5/AC6 in `operator-checks.md`; AC2/AC3 by tests (`tests.md`, 42 passed); **AC4's two mutation runs** in `mutation-runs.md` (each PK reverted to `(symbol, date)` fails `test_actions_tables_keyed_by_source`) and independently by the Auditor (five key mutations, two nullability mutations).
3. **Diff touches only §2 files plus evidence/clerical** — `schema.py`, `store.py`, `test_schema.py`, `test_store.py`; plus the single ruling-6 assertion edit in `tests/test_cli.py` (18 → 19), disclosed in `spec-gaps.md` and confirmed by the Auditor; plus `docs/evidence/**` and the WO header fields. Nothing under §3 exclusions.
4. **Other AMD-0010 §2B conditions** — `non_vacuity_established: yes`; `offline_tests_pass: yes` (42, also under `unshare -n`); ruff and gitleaks clean; CI `secrets` and `test` pass, `mergeable_state: clean` at the pre-acceptance head; `commit_identity_clean: yes`; ssh-only access mechanism recorded in `tests.md`; no Amendment triggered.

## Notes
- Auditor observation 2: the v1→v2 upgrade path of the version-row guard is untested (operator check shows it working); a test is recommended in a later Work Order (recorded in `spec-gaps.md`).
- Architect retrospective review applies at the P0-C group boundary.
