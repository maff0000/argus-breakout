# WO-0007 — Audit record

Fresh Auditor, whole branch, audited SHA `dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c` (a merge of `main` at WO-0012, which already holds the store-identity code), base `4321d92`. The WO's own diff is `git diff 9ac355d dd8d830` (10 files).

## Verdict block (as returned, fields verbatim)
```
AUDIT_VERDICT: GREEN  (two non-blocking findings F1, F2)
work_order: WO-0007
base_sha: 4321d92eeea6546a8095ecda3f22e5065837cae4
commit_sha: dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c
scope_fidelity: yes (helpers not named in §2 sit inside the §2 files)
offline_tests_pass: yes (256 passed in 259s, under `unshare -rn`, no network, no .env)
non_vacuity_established: yes (15 of 15 mutants killed by an intended test)
gitleaks_clean: yes (86 commits)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no, operator check (test level: test_etf_routed_to_etf_bars, test_cli_materialise)
AC2_verified: yes at test level (operator 20-symbol check to follow)
AC3_verified: yes
AC4_verified: yes at test level (parquet sha256 before/after, n_rows=0, n_readjusted=0)
confidence: high
```

## Findings
1. **F1 (low, non-blocking): dividend prior-close tolerance.** WO §4 says the factor uses the prior trading day's close and, if that close is missing, skips the dividend and warns. `dividend_adjusted_close` takes the last bar before the ex-date if it is at most 5 calendar days old and skips only beyond that. Probe (`python -I`): bars on 03-02, 03-04, 03-05, ex-date 03-04 amount 1.0, real prior day 03-03 absent → `[99.0, 100.0, 100.0]`, warnings empty: the dividend was applied against the 03-02 close silently. The numeric error is one stale close in the yield denominator. `test_missing_prior_close_skips_dividend_with_warning` covers a null close and a gap above 5 days, not 2–5. Architect: ratify the 5-day tolerance or ask for warn-on-stale.
2. **F2 (ruling request, non-blocking): a withheld Polygon row can still be published from a yfinance row for the same day.** Deliberate and tested (`test_quarantine_does_not_withhold_yfinance_row`). In the quarantine case the day-level fault is a judgement on the Polygon fetch and yfinance is an independent source; in the flag case `bar_flags` is keyed per source, so the code follows the schema, while AMD-0018 §2A's prose says "excludes flagged symbol-days". The Architect should ratify or amend the §2A wording. (Live evidence in `operator-checks.md`: all 51 flagged symbol-days that were published from yfinance agree with Polygon to within 1e-5 relative.)

## Observations (from the Auditor)
- Per-row split baseline (`date < D` and `date(ingested_at) < D`, fallback per-(symbol, source) latest bar date) is a faithful per-row evaluation of WO §8 and strictly more correct for a source fetched either side of D; proven by `test_split_baseline_is_per_row_fetch_time` (mutant `per_source_baseline` is killed only by it). The `split_case` fixture is consistent with §8 but does not discriminate per-row from per-source. A row fetched on the split date itself is treated as already adjusted.
- `adj_version` increments whenever an already-published row changes or vanishes (dividend-only change, newly quarantined day); appended bars alone do not bump it. Broader than the WO text, better for CI-5.
- CI-9: no write path to `bars_raw`; `ingest_log`/`bar_flags` read through `Store` methods with bound parameters and `_check_symbols`; no f-string SQL added.
- A latest verdict of `failed` or `holiday` also withholds that day's Polygon rows (conservative).
- SCHEMA_VERSION 3→4 relative to base comes only through the merged WO-0012.

## Mutations (each killed by the named test; `tests/test_adjust.py`)
splits not applied → `test_split_applied_only_to_prior_history`; baseline ignored → `test_split_baseline_is_per_row_fetch_time`; per-source baseline → same test; ratio inverted → `test_split_applied_only_to_prior_history`; dividend ignored → `test_dividend_adj_close_hand_values`; source preference reversed → `test_prefers_polygon_on_overlap`; actions precedence reversed → `test_source_precedence_on_actions`; listing-life bound removed and outside-membership warning removed → `test_reassigned_ticker_is_not_concatenated`; rename continuity removed → `test_rename_chain_stays_continuous`; quarantine filter removed → `test_quarantined_day_not_published`; flag filter removed → `test_flagged_symbol_day_excluded_rest_remains`; excluding set widened → `test_split_reconciled_flag_does_not_exclude`; `adj_version` not incremented → `test_split_not_double_applied`; 5-day gap guard removed → `test_missing_prior_close_skips_dividend_with_warning`. The Implementer separately filed 14 + 7 mutations.
