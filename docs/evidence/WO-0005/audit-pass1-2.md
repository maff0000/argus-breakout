# WO-0005 — Audit record

Fresh Forge Auditor dispatches (never forks), ssh-only, detached audit worktree at the audited SHA, mutations on `mktemp` copies.

| Pass | Audited SHA | Scope | Verdict |
|---|---|---|---|
| 1 | `abdb1a2` | AMD-0012 delta: `splits`/`dividends`, integer 98% rule, resume rule | GREEN, no findings (resume rule shown non-vacuous in both directions; 0.95 value unpinned and `>=` vs `>` equivalent — observations) |
| 2 | `2c5a8a2` | whole branch after AMD-0014 §2E: skipped symbols count as successes | **GREEN, no findings** |

Pass-1 observation put to the Architect and **ruled in AMD-0014 §2E**: the exit denominator excluded skipped symbols (a run of 10 written / 600 skipped / 5 failed evaluated 10/15 and exited 1). Fixed in `2c5a8a2`.

## Pass 2 verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0005
base_sha: d0ea305
commit_sha: 2c5a8a2bbd14b6db16d13a26beb7ba53e1b9b144
scope_fidelity: yes (9 paths changed: 5 source/test paths + 2 fixtures + cli.py one-line import, all within §2; other paths are DELIVERY-LOG and the WO clerical fields)
offline_tests_pass: yes (74 passed normally; 74 passed again under `unshare -rn`; no .env present)
non_vacuity_established: yes
gitleaks_clean: yes (61 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: yes for the code path only (CLI exit rule and bulk load are covered by tests; the host-run operator check is the DC's)
AC2_verified: no — operator check (2,400 rows per symbol on the live host); not a code defect
AC3_verified: yes for the code path (both tables written with source='yfinance'; same-date split and dividend both retained)
AC4_verified: yes
findings: none
confidence: high
```
Out-of-scope observations: (1) `ruff format --check` lists 7 files, 2 added by this branch (`providers/bootstrap.py`, `tests/test_ingest_bootstrap.py`) and 5 pre-existing (the gate is `ruff check`, clean);
(2) `YFinanceProvider.daily_bars` and `.actions` each call `yf.download` for the same chunk, so every chunk downloads twice (matches the §2 interface; an efficiency point).

## Exit-code behaviour (real CLI, `bootstrap_history` mocked) — AMD-0014 §2E
| (written, skipped, failed) | exit |
|---|---|
| (10, 600, 5) | 0 |
| (0, 98, 2) | 0 |
| (0, 97, 3) | 1 |
| (0, 50, 0) fully skipped re-run | 0 |
| (0, 0, 0) | 0 |
| (98, 0, 2) | 0 |
| (97, 0, 3) | 1 |
| (5, 0, 0) | 0 |
| (0, 0, 1) | 1 |

**Which the implementation does (AMD-0014 §2E asked for confirmation):** before `2c5a8a2` it did **not** count skips — it evaluated `written / (written + failed)`; after, `(written + skipped) / (written + skipped + failed)` in integer arithmetic.

## Non-vacuity (copies under mktemp)
- Revert the §2E fix: 3 failed (`[10-600-5-0]`, `[0-98-2-0]`, `[50-48-2-0]`); the other cases are negative controls.
- Disable the skip logic: `test_resumable_skips_complete_symbols`, `test_resume_skips_symbol_with_complete_data` fail.
- Over-skip (ignore the 95% threshold): `test_resume_does_not_skip_symbol_with_incomplete_data` fails.
- Stop writing `splits`: `test_loads_bars_actions_and_log`, `test_same_date_split_and_dividend_retain_both` fail.
- Collapse dividends to one row per symbol: `test_loads_bars_actions_and_log` fails.
