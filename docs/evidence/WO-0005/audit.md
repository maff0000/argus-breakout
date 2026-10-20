# WO-0005 — Audit record (four independent passes)

All passes: fresh Forge Auditor dispatches (never forks), ssh-only, detached audit worktree at the audited SHA, mutations on `mktemp` copies. The earlier record is `audit-pass1-abdb1a2.md`.

| Pass | Audited SHA | Scope | Verdict |
|---|---|---|---|
| 1 | `abdb1a2` | AMD-0012: `splits`/`dividends`, integer 98% rule, resume rule | GREEN, no findings |
| 2 | `2c5a8a2` | AMD-0014 §2E: skipped symbols count as successes | GREEN, no findings |
| 3 | `85c01e1` | AMD-0015 §2B: current / historical cohorts, exit rule on the current cohort | GREEN, **one finding** (test gap) |
| 4 | `70ce2d7` | whole branch after the fix | **GREEN, no findings** |

## Pass 3 finding (fixed in `70ce2d7`)
> Test gap on skipped-symbol classification. `cur = current_cohort(store, result.skipped)` in argus/commands/ingest_bootstrap.py is not covered by any test that can fail. Mutation M5 (`cur = set(result.skipped)`, every skip treated as current) leaves all 40 tests green… Under M5 skipped historical symbols would be counted as current successes… which could mask a current-cohort shortfall. The shipped code is correct… Per CI-6, proof of this behaviour is missing.

Fix: `test_cli_rerun_classifies_skipped_symbols_by_cohort` (real store, CLI re-run that skips a current AND an inactive-historical symbol with an unavailable historical symbol present; asserts `current: written=0 skipped=1 failed=0 (100.0%)`, `historical: written=0 skipped=1 unavailable=1 (50.0%)`, `historical unavailable: HIST1`, exit 0).
The Implementer showed M5 now fails 1 test (baseline 41 passed); the pass-4 Auditor reproduced it.

## Pass 4 verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0005
base_sha: 5e95343
commit_sha: 70ce2d765a4c2c671f5be6402961eda7f7b7f75e
scope_fidelity: yes (all 15 changed paths inside WO-0005 §2, or DC-authored docs/evidence and clerical WO fields)
offline_tests_pass: yes (83 passed plain; 83 passed under `unshare -rn`; no .env present; ruff check clean)
non_vacuity_established: yes (M5 and all 7 requested mutants fail)
gitleaks_clean: yes (71 commits scanned, no leaks found)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes (5e95343..70ce2d7: one identity, Rogue (Delivery Controller) <noreply@anthropic.com>)
AC1a_verified: yes   AC1b_verified: yes   AC2_verified: yes (operator check)   AC3_verified: yes   AC4_verified: yes
findings: none
confidence: high
```

### Mutants (pass 4, mktemp copies of 70ce2d7; baseline 83 passed)
| Mutant | Result |
|---|---|
| M5 every skip classified as current in the command | KILLED — `test_cli_rerun_classifies_skipped_symbols_by_cohort` only |
| historical failures counted against the exit rule | KILLED (4) |
| current cohort ignored in the exit rule | KILLED (9) |
| everything classified as current — in the command / in the run / in `current_cohort` | KILLED (1 / 7 / 7) |
| `active` filter dropped from `current_cohort` | KILLED (4) |
| skips not counted as successes | KILLED (5) |
| `>=` -> `>` in `meets_threshold` | KILLED (5) |
| resume threshold removed / `COVERAGE_THRESHOLD = 0.0` | KILLED (1 / 1) |
| `r["n"] >= need` -> `r["n"] > need` in `_covered` | survived — equivalent on the fixture (need = 55.1, not an integer); observation |

### Exit-code behaviour through the real CLI (pass 3, driver outside the worktree)
| Scenario | Exit |
|---|---|
| current 100/100, historical 100% unavailable | 0 |
| current 97/100, historical perfect | 1 |
| current 98/100 (boundary) | 0 |
| empty current cohort | 0 (`n/a`) |
| unknown `--symbols` (data returned) | 0, filed as historical |
| re-run, everything skipped | 0 |
| `BOTH` active+member no data, ETF ok, `ONLYM` membership-only no data | 1; `current failed: BOTH`, `historical unavailable: ONLYM` |

### Observations (none blocking)
1. The resume threshold is relative to the whole requested range, so a symbol listed after the range start (IPO, or a delisted symbol that ended early) can never reach 95% and is re-downloaded on every run. Idempotent; costs only a repeat download; never a wrong number or exit. A per-symbol floor would be a spec change. (Live: 45 current + 29 historical symbols re-written on a resume re-run.)
2. A typo in `--symbols` exits 0 (filed as historical) — by design under AMD-0015 §2B.
3. `ruff format --check` lists files the branch did not touch; the gate is `ruff check`.
