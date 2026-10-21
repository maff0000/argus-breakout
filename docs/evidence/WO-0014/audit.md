# WO-0014 — Audit record

Fresh Auditor dispatch, ssh-only, offline, against audited SHA `6236748aef5f026ac3f1da401970d606a3fd7b54`, base `e16b0c5`.

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0014
base_sha: e16b0c5
commit_sha: 6236748aef5f026ac3f1da401970d606a3fd7b54
scope_fidelity: yes (5 paths: adjust_cmds.py, adjust.py, ingest_polygon.py, tests/test_adjust.py, tests/test_ingest_polygon.py; all in WO §2; no §3 exclusion touched; no schema or SCHEMA_VERSION change; no docs/; no providers/ibkr.py)
offline_tests_pass: yes (301 passed, 1 deselected; also under `unshare -rn` with no network: 301 passed); ruff clean
non_vacuity_established: yes (AC7 a/b/c and 7 further mutations each fail the intended test)
gitleaks_clean: yes (101 commits)   public_hygiene_clean: yes   commit_identity_clean: yes
AC1-AC4, AC6_verified: n/a (operator checks; code paths verified)   AC5_verified: yes   AC7_verified: yes
findings: none
out_of_scope_observations:
 1. test_dividend_disagreement_normalises_basis does not pin the ex-date handling inside the comparison helper: changing split_cum_at to the bar AT the ex-date instead of the last bar before it still passed, because its split falls after the ex-date. test_split_on_ex_date_is_divided_out covers the applied factor and production is consistent. Minor test gap.
 2. The 20-trading-day discriminator is faithful to the WO wording and §8: it counts calendar-union market days (distinct bars_raw dates across all symbols) that this symbol lacks between its last bar at or before final_end and its first bar after. Holiday runs are not gaps. 20 retains, 21 excludes. Hazards the WO accepts: (a) a thin store errs toward retaining; (b) a same-company data hole of more than 20 market days across end_date reads as a reassignment and the tail is excluded with a named warning; (c) a reassigned ticker with a gap of 20 days or fewer is retained by design; (d) `present` uses all of the symbol's raw rows, whatever the source or basis.
 3. A day with no ingest_log verdict still publishes (WO-0007); covered by test_only_ok_days_are_published and test_day_without_verdict_is_published.
 4. The argument passed to _bound_by_membership includes unsupported-basis rows; harmless.
confidence: high
```
Changed existing tests, each judged faithful and none weakened: `_reassigned` helper and two membership tests moved to a 2026-03-02 successor with a calendar symbol; `test_outside_warning_needs_more_than_ten_days` replaced by the gap-threshold test; `test_failed_verdict_does_not_withhold` replaced by `test_unjudged_day_is_not_published`; `== 0` assertions changed to `is None`.

## Mutations (on a `git archive` copy under mktemp; baseline `tests/test_adjust.py` 50 passed)
(a) gap threshold removed (tail always excluded) → `test_same_company_tail_is_retained` failed; (b) blocklist (`status == 'quarantined'`) restored → `test_unjudged_day_is_not_published` and `test_only_ok_days_are_published` failed; (c) raw `cash_amount` comparison → `test_dividend_disagreement_normalises_basis` failed. Further: divisor `cums[i-1]`→`cums[i]` (`test_split_on_ex_date_is_divided_out`); `gap <=`→`gap <` and a calendar-day gap (`test_gap_threshold_boundary`); reporting `0` for `None` (`test_flag_excluded_count_is_never_a_silent_zero`); silent revalidate failure (`test_revalidate_failure_writes_a_log_row`); withholding all bars_raw dates (`test_only_ok_days_are_published`).
