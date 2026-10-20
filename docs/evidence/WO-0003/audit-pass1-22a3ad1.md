# WO-0003 — Audit record

Fresh Forge Auditor, ssh-only, detached audit worktree at `22a3ad1721117690e2b3a3c9c2d6eff274b973c5`. Whole-branch re-audit after the AMD-0013 delta (`22a3ad1`). The branch head at PR time is `465b8f3` = `22a3ad1` plus a clerical merge of main (`02e4a2e`, WO-0011) — no WO-0003 code differs from the audited tree (tests at the merged head: 82 passed = 78 + 4 from WO-0011).

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0003
base_sha: 02e4a2e3065570a46f55349b524e60131d7de8a3 (as supplied; NOT an ancestor of the audited commit; effective base 19d9ca0 = merge-base = the WO's recorded Base SHA; see O1)
commit_sha: 22a3ad1721117690e2b3a3c9c2d6eff274b973c5
scope_fidelity: yes (15 paths vs 19d9ca0: the WO §2 files, fixtures and tests, the new wikipedia_changes_table.html fixture, DELIVERY-LOG.md and the WO header fields; no §3 exclusion touched)
offline_tests_pass: yes (78 passed under unshare -rn; no .env; ruff clean)
non_vacuity_established: yes (12 mutations; two survivors explained as equivalent)
gitleaks_clean: yes (57 commits)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no (code and test only; live check is the DC's)
AC2_verified: no (not independently; live check is the DC's)
AC3_verified: yes
AC4_verified: yes (code)
AC5_verified: yes
AC6_verified: yes in code and test; live runs are the DC's
AC7_verified: yes
AC8_verified: yes
findings:
 1. (Low, non-blocking, spec-conformant) In route (c), a current member whose `Date added` <= H but who is absent from hanshof@H gets no membership row, silently omitted and uncounted. Probe: 5 symbols (BNY 1995-03-31, FISV 2001-04-02, MRSH 1987-08-31, SKYD 1994-09-30, VMRK 2001-12-03) look like renames/successor tickers; their predecessors are in hanshof@H and are bounded out. members_on(today) is short of the current table by these symbols and the bounded count is inflated by the old tickers. WO §2 route (c) says additions are only `Date added > H`, so the code matches the spec literally. Recommendation: accept as residual, or report a count of "current members with no membership row"; a rename-aware rule is a spec change. (argus/data/universe.py build_membership, route-(c) branch.)
confidence: high on code, tests and mutations; medium overall (live checks and real page shape outside the Auditor's remit)
```

## Judgement items (as returned)
1. 402/403: `_UNAVAILABLE_STATUSES=(402,403)` raises `ProviderUnavailable` for all three endpoints, no retry, one call; message carries only path and status; `test_402_403_raise_provider_unavailable_without_key` (6 cases) asserts no key in traceback or stdout.
2. refresh(): catches only `ProviderUnavailable` for the changes endpoint, so a 500 still aborts (`test_other_fmp_errors_still_abort_refresh`).
3. Derivation: exact additions H < date_added <= as_of; bounded removals end_date = H; hanshof rows untouched.
4. Route-(b) detector needs a non-`constituents` table with Date/Added/Removed headers, rows beginning with a date and >= 5 cells; tested positive and negative; layout dependence cannot be verified against the live page (fixture-only).
5. Worst-case FMP calls 1+1+50 = 52 <= 60.

## Mutations (as returned; `git archive` copies under mktemp, offline)
| # | Mutation | Result |
|---|---|---|
| M1 | drop 403 from the unavailable set | killed |
| M2 | catch ProviderError instead of ProviderUnavailable for changes | killed (`test_other_fmp_errors_still_abort_refresh`) |
| M3 | bounded end_date = as_of | killed |
| M4 | exact filter `>= H` | survived — equivalent (a member with date_added == H is already open from hanshof@H) |
| M5 | remove stop-after-first-profile-402 optimisation | survived — unpinned, harmless (worst case still 52 <= 60) |
| M6 | put the query (key) in the unavailable message | killed |
| M7 | profile cap 50 -> 80 | killed |
| M8 | skip route (b) | killed |
| M9 | ignore as_of for exact additions | killed |
| M10 | bounded limit 40 -> 400 | killed |
| M11 | re-route current-constituents ProviderUnavailable branch | survived — equivalent while Wikipedia is present |
| M12 | bounded end = previous trading day of H | killed |

## Observations (as returned)
- O1: the supplied BASE `02e4a2e` was not an ancestor of the audited commit (branch lacked main's WO-0011 commits); the DC has since merged main (`465b8f3`, clerical) so the PR does not revert WO-0011.
- O2: the `MAX_BOUNDED_ROWS` stop lives in the CLI wrapper; `refresh()` has already written membership when the stop fires (exit 1 + ingest_log `failed`) — not transactional.
- O3: when Wikipedia succeeded, a non-402 FMP error on `sp500-constituent` is logged and swallowed (secondary source).
- O4: stdlib `httpx` logger would log URLs including `apikey` at INFO if a handler were attached; none is configured; worth remembering for WO-0009.
- O5: FUNCTIONAL_ONLY — no browser gate. O6: no ACCEPTED-RESIDUALS entry applies.
