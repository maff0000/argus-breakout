# WO-0013 — Audit record

Fresh Auditor dispatch, ssh-only, offline, against audited SHA `df4b52d1e7365261b0aefb7a47b38374f7dbe379`, base `df0a126`.

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0013
base_sha: df0a126
commit_sha: df4b52d1e7365261b0aefb7a47b38374f7dbe379
scope_fidelity: yes (9 changed paths, all inside WO section 2 or the disclosed extensions: tests/test_ingest_polygon.py, tests/test_store.py, tests/test_schema.py, and migrate-store in store_cmds.py; tests/test_cli.py and adjust_cmds.py unchanged; no docs/ paths; no section 3 path touched)
offline_tests_pass: yes (269 passed in 292s; no .env; no provider call by any code path)
non_vacuity_established: yes (4 mutations on a copy, all failed the intended tests)
gitleaks_clean: yes (90 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: no (code and tests yes; live operator check pending)
AC2_verified: no (code yes; dividend-basis.md DC-filed)
AC3_verified: no (operator check pending; arithmetic proven by test: 49.5 vs 49.0)
AC4_verified: yes for DOUBLE (bars, etf_bars and on-disk parquet; bit-exact round trip of 187.12345678901234); 20-symbol re-run is a DC item
AC5_verified: yes for code and tests; live warned list is a DC item
AC6_verified: yes in code; logging.md DC-filed
AC7_verified: yes (SCHEMA_VERSION 5; bars_raw SHA-256 identical before/after; second run changes nothing; unmeasured source refuses and changes nothing)
AC8_verified: yes (independently re-run)
findings: none
out_of_scope_observations:
 1. equal_weight_aggregate is standalone; no composite/market_daily code exists to call it, so "aggregates exclude" is proven at function level only. A later WO must wire it in.
 2. n_symbol_days_flag_excluded is kept as a constant 0 for the CLI summary shape; adjust_cmds.py unchanged.
 3. AC1-AC3, AC5, AC7 operator checks, dividend-basis.md and logging.md are DC deliverables (WO section 7), procedural; the Architect should see them before acceptance.
 4. "Unknown or null basis raises" holds on every path: adjustment (_require_dividend_basis: null, empty, wrong-case, unknown, missing column), write (stamp_dividend_basis: unmeasured source or disagreeing basis), migration (raises before dropping anything).
 5. CI-9 holds (bars_raw read only in materialise, never written or verdict-filtered; migration only counts its rows); no cross-source substitution; split_cum computed in the same loop as _div; as_paid division uses the first bar on or after the ex-date (test covers a split before the ex-date); _judge failure after the raw write records 'quarantined' with bars.height rows, fetch failure 'failed' with 0; no float32 in argus/ except the migration's detection; ADR-0008 greps empty; residuals R1-R7 not applicable.
confidence: high (code, tests, mutations); medium on AC1-3, AC5 live figures (not auditable offline)
```

## Method and mutations (as reported)
Preflight, diff stat, full source review of `git diff df0a126 df4b52d -- argus/`; `uv sync` (60 packages); `pytest -q` → 269 passed; gitleaks 90 commits clean; identity check; ADR-0008 greps. Mutations on an rsync copy with the worktree's venv and `PYTHONPATH=<copy>` (baseline 8 passed on the targeted subset):
- (a) restore the flag exclusion by anti-joining flags after `select_source` → `test_flagged_symbol_day_is_published` and `test_no_cross_source_substitution` failed (2 failed, 6 passed);
- (b) replace `amount = amount / cums[i]` with `pass` → `test_as_paid_dividend_is_divided_by_cumulative_split` failed;
- (c) final cast to Float32 → `test_prices_are_float64` failed (round trip returned 187.12345886…);
- (d) judge-failure result → `0, "failed"` → `test_judge_failure_records_quarantined` failed.
