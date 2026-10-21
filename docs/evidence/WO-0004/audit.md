# WO-0004 — Audit record

Pass 1 (at `16a65bf`, before AMD-0018): GREEN; its live operator run exposed the jump-rule feedback loop, which the Architect ruled in AMD-0018. Its evidence is superseded and replaced by this file.

**Pass 2 — fresh Auditor, whole branch, audited SHA `46ad537e5b0a95253957b7db7b0dbfd980b443d3`, base `9a7a505`. Verdict GREEN, one non-blocking finding.**

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0004
base_sha: 9a7a505
commit_sha: 46ad537e5b0a95253957b7db7b0dbfd980b443d3
scope_fidelity: yes (22 changed paths in WO §2 or DC evidence/clerical; tests/test_schema.py and tests/test_cli.py not listed in §2 — finding 1)
offline_tests_pass: yes (222 passed; 56-test subset also under `unshare -rn`, no network, no .env)
non_vacuity_established: yes (every mutant failed an intended test)
gitleaks_clean: yes (82 commits)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: n/a-for-auditor (operator check)
AC2_verified: yes at code and test level (live numbers are operator checks)
AC3_verified: yes at code and test level
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes at code and test level
AC7_verified: yes
findings:
 1. (scope observation, not a defect) tests/test_schema.py and tests/test_cli.py are not in WO §2. Edits: table count 19→20, bar_flags added to DESIGN_TABLES, SCHEMA_VERSION 2→3, "20 tables" in the CLI test. They are the mechanical consequence of the §2 mandate (bar_flags DDL, SCHEMA_VERSION 3); the suite fails without them. §2 is "exhaustive", so the Architect should ratify them explicitly.
confidence: high
```

## Method and results (as reported)
- **CI-9 / bars_raw before validation:** `store.write_bars_raw` runs before `_judge`/`validate_day`; only a provider error or an empty (holiday) response skips it. Mutant M5 (write only if verdict is `ok`): six tests failed (`test_quarantined_day_is_still_stored`, `test_missing_group_member_quarantined_but_stored`, `test_current_member_without_group_quarantines_amid_historical`, `test_breadth_of_jumps_quarantines_but_stores`, `test_prior_close_comes_from_a_quarantined_day`, `test_backfill_resumable`). `validate_day` is pure (`test_does_not_mutate_inputs`). (A first mutant, a post-hoc DELETE, was invalid: `bars_raw` is a view.)
- **Non-vacuity (AC4), on `git archive` copies under `mktemp`, baseline 37 passed in `tests/test_validate.py` + `tests/test_ingest_polygon.py`:** M1 decide over whole frame → `test_non_member_jump_never_reaches_the_verdict`; M6 record flags for members only → same test; M2 prior_close from ok days only → `test_prior_close_comes_from_a_quarantined_day`; breadth threshold 1 symbol and fraction 0.0001 → `test_one_member_jump_does_not_quarantine_the_day`; inapplicable-rule check removed → `test_missing_prior_close_quarantines_non_initial_day`; `>=`→`>` at the 20% boundary → `test_breadth_of_jumps_quarantines_the_day` (boundary exact, `Fraction`); `_JUMP_MAX` 0.9 → four validate tests. All killed.
- **Judgement calls accepted:** prior_close = each symbol's latest stored close in a 14-day window read from `bars_raw` regardless of verdict (§2A, pinned); 5% denominator `members_on(d)` (WO §2); CLI exits 0 on quarantine and 1 only on `failed`; `revalidate_range` writes no failed row to `ingest_log`; day flags written atomically (delete then insert in one transaction).
- **revalidate (AC7):** never builds a `PolygonClient`, never calls `require("polygon_api_key")`, issues only SELECTs against `bars_raw`; `test_revalidate_makes_no_provider_call` and `test_cli_revalidate_needs_no_key_and_no_network` (respx call count 0, bars_raw digest and rows identical).
- **Hygiene:** both ADR-0008 greps empty; `ruff check .` clean; gitleaks 82 commits, no leaks; the only URL in the diff is the public `api.polygon.io`.
- **Out-of-scope observations:** `ruff format --check .` would reformat 17 files (CI runs `ruff check` only); if `_judge` raises after `bars_raw` is written the day is logged `failed` although rows are stored (re-fetch is an idempotent upsert; the status is slightly misleading); ticker-reassignment bound (AMD-0018 §2F) is WO-0007's.

## Delivery Controller note
Finding 1 is recorded in `spec-gaps.md` for ratification. The live operator numbers the Auditor said it could not verify are in `operator-checks.md` and checked against AMD-0018 §3 in `acceptance.md`.
