# WO-0006 — Audit record (two independent passes, both GREEN)

Fresh Forge Auditor dispatches (never forks), ssh-only, mutations on `mktemp` copies. Pass 1 at `9d6e192`: GREEN, no findings. The live operator check then showed the real FMP payload (no `time` field; a thin calendar), so the fixtures were replaced with recorded rows and a coverage line was added (`9a841b0`); pass 2 re-audited the **whole branch**: **GREEN, no findings** (below).

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0006
base_sha: 46086e6
commit_sha: 9d6e192172b844b500451844445f68b5b7aebb01
scope_fidelity: yes (10 changed paths, all in §2 Scope or DC-authored docs/ clerical; no §3 exclusion touched)
offline_tests_pass: yes (168 passed; no .env; all FMP traffic respx-mocked)
non_vacuity_established: yes (9 of 10 mutations killed; the one miss was a faulty mutation, re-run correctly and killed)
gitleaks_clean: yes (78 commits scanned)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no at audit time (operator check; the FMP allowance was spent that day) -- see operator-checks.md
AC2_verified: yes   AC3_verified: yes for the test (operator ingest_log check in operator-checks.md)   AC4_verified: yes
findings: none
confidence: high
```

## Mutation table (Auditor, copies outside the worktree; baseline 16 passed in tests/test_events.py)
| Mutation | Result |
|---|---|
| no filter on non-members | 3 failed |
| `time_of_day` forced to None | 1 failed |
| weekday-only trading-day counting | 1 failed |
| `confirmed` forced False | 2 failed |
| unavailable half not recorded | 3 failed |
| an extra FMP call | 3 failed |
| upcoming count includes past dates | 1 failed |
| `approx` forced False | 1 failed |
| delete events before the upsert | 1 failed (first attempt was a no-op on a nonexistent method; redone and killed) |

Before the audit the DC found one survivor in the Implementer's own mutation run (the `| (date <= today)` term of `confirmed`); the test `test_past_dated_row_is_confirmed_even_without_actual_eps` was added and fails when the term is removed.

## Out-of-scope observations (Auditor)
`ruff format --check` would reformat 11 files (pre-existing; CI runs `ruff check` only); `confirmed` = actual EPS present OR date <= today (design choice consistent with WO §1; ratifiable); the trading calendar is the union of `bars_raw` dates (sparse bars understate counts with `approx=False`); the `approx` column is beyond the §2 signature but required by WO §4; fixtures were authored from field names, not a recorded payload; both-halves-unavailable exits 0 with status `partial` and names the halves.

## Pass 2 verdict block (as returned; `9a841b0`)
```
AUDIT_VERDICT: GREEN
work_order: WO-0006
base_sha: 46086e6
commit_sha: 9a841b07ebe42491d921e309a2b0aed14d2dcef9
scope_fidelity: yes
offline_tests_pass: yes (173 passed, no .env, all respx-mocked)
non_vacuity_established: yes (11 of 11 real mutants killed; one, M12, survived -- see below)
gitleaks_clean: yes (79 commits scanned)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no (39 of 518 active symbols = 7.5% on the real plan; external data fact, ruling 7; CI-8 honoured by the CLI line "N of M active")
AC2_verified: yes   AC3_verified: yes   AC4_verified: yes
findings: none
confidence: high
```
Mutants killed by name: hard-coded `n_with_time` (0 and 2), hard-coded CLI coverage line ("the coverage line cannot lie"), no member filter on earnings and on dividends, dropped `time` mapping, `confirmed` ignoring past dates, weekday-only trading days, a third FMP call, swallowed unavailable flag.
**Survivor M12:** `bisect_right` -> `bisect_left` for the last-earnings-on-or-before lookup; no test puts an earnings date exactly equal to `on`, so `days_since_earnings == 0` on the report day is unchecked. Not required by WO §5 / AC2, not a finding; recorded in `spec-gaps.md` as a one-line test to add.
Other observations: `ruff format --check` would reformat 11 pre-existing files (CI runs `ruff check` only); WO §8 still says the FMP earnings calendar has a `time` field, which the recorded payload does not (clerical, for the Architect).
