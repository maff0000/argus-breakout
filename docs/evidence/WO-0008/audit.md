# WO-0008 — Audit record

Fresh Auditor dispatch, ssh-only, offline (no gateway contact, no `.env`), against audited SHA `6d531f5919f42ae052ed6f2d1290685254264208`, base `df0a126`.

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0008
base_sha: df0a126
commit_sha: 6d531f5919f42ae052ed6f2d1290685254264208
scope_fidelity: yes (10 changed paths, all in WO §2 plus tests/fakes/__init__.py; nothing in §3 touched; cli.py diff is exactly one import line)
offline_tests_pass: yes (279 passed, 1 deselected = the `live` smoke; ruff check clean)
non_vacuity_established: yes (9 mutations on a copy under mktemp, each failed the suite)
gitleaks_clean: yes (89 commits scanned, no leaks found)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no (operator check on the live gateway; not run by the Auditor)
AC2_verified: no (operator check, 13 rows live; not run by the Auditor)
AC3_verified: yes
AC4_verified: yes
AC5_verified: no (offline half passes; live smoke is an operator check)
AC6_verified: yes
AC7_verified: yes
findings: none
out_of_scope_observations:
 1. Port numbers 7497/4002 (allowlist) and 7496/4001 (test values) appear in the repo; required by the WO, well-known IBKR defaults, not internal network facts.
 2. test_cli_disconnects_on_provider_error is weak (accepts exit code 1 or 2; asserts disconnect only for 1). The disconnect-in-finally behaviour is correct in the code; no AC relies on the test.
 3. ib_host defaults to 127.0.0.1 (accepted residual R3).
confidence: high
```

## Method (as reported)
- Preflight, diff stat, identity check over `df0a126..6d531f5`; read the WO, ACCEPTED-RESIDUALS, CRITICAL-INVARIANTS, PID §9 and every changed file.
- `unshare -rn uv run python -m pytest -q` → 279 passed, 1 deselected (network-isolated); `ruff check` clean.
- Greps over `argus/` empty: AC3 pattern; absolute-path literals; `uv|systemd|systemctl|apt-get`. The only IB calls: `connect(..., readonly=True)`, `disconnect`, `qualifyContracts`, `reqHistoricalData`.
- Non-vacuity on a `git archive` copy (baseline 23 passed in `tests/test_reconcile.py`): close tolerance 0.001→0.002; volume tolerance 0.10→0.12; `missing` not a breach; priority ignored; offset perturbed by priority; `readonly=False`; 7496 added to allowlist; paper-port check removed; iv upsert key reduced to `["symbol"]` — each failed the intended test(s).
