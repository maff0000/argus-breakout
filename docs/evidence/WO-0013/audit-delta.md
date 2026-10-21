# WO-0013 — Delta audit (post-acceptance integration fix)

WO-0013 was audited GREEN at `df4b52d` and accepted by the Architect at that SHA. Merging `main` (WO-0008 had landed) into the branch (`0d72f01`, DELIVERY-LOG conflict only) made the integrated suite fail two `tests/test_store.py` relocation tests with `ValueError: I/O operation on closed file`: `configure_logging()` binds the `sys.stdout` of the test that ran it (WO-0008's CLI tests use `CliRunner`), and WO-0013 had correctly moved the relocation warning onto structlog (AMD-0019 §2H). Both tests pass in isolation, so neither branch was red on its own.

Fix (fresh Implementer, test-only): one autouse fixture in `tests/conftest.py` resetting structlog's defaults after each test. Committed as `affa97579600f2a291ad94f9bff3fd20cea748f4`.

## Delta audit verdict (fresh Auditor, base `0d72f01`)
```
AUDIT_VERDICT: GREEN
commit_sha: affa97579600f2a291ad94f9bff3fd20cea748f4
scope_fidelity: yes (only tests/conftest.py, +8 lines; argus/ untouched)
offline_tests_pass: yes (292 passed, 1 deselected); ruff clean
non_vacuity_established: yes (fixture disabled on a copy: the same two tests fail again; same two failures reproduced at 0d72f01)
gitleaks_clean: yes (97 commits)   commit_identity_clean: yes   public_hygiene_clean: yes
findings: none
out_of_scope_observations:
 1. `ruff format --check .` would reformat 21 files, both at this SHA and at 0d72f01 (predates the delta; the Phase 0 gate is `ruff check`).
 2. Five test files already carry per-file autouse structlog resets; the conftest fixture generalises that pattern.
```
Check 5 (can the fixture mask a real logging bug?): no session- or module-scoped logging setup exists in tests; each test that needs logging calls `configure_logging` itself, and the reset runs after each test, so a test keeps its configuration for its own duration; `test_logging.py` (redaction) configures inside the test and is unaffected.

## Requested
`ARCHITECT ACCEPTANCE: WO-0013 @ affa975 — ACCEPTED` on PR #12 (the acceptance at `df4b52d` covered the code; this commit adds one test-only fixture).
