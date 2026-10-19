# WO-0002 — Audit record

Fresh Forge Auditor dispatch, ssh-only, detached audit worktree at the audited SHA. First audit of this Work Order.

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0002
base_sha: 75b230dacb555dbe2f3f4347d640262348bf2b4a
commit_sha: e5682b9d57e09a4575cf25e57564fb94eecf244b
scope_fidelity: no (tests/test_cli.py is modified but not listed in WO §2; see finding 1. All other paths are in scope, and the docs/ changes are procedural Delivery Controller clerical edits.)
offline_tests_pass: yes (37 passed; ruff check clean; no .env present; the tests contain no network or provider code; host not firewalled)
non_vacuity_established: yes (4 of 5 perturbations were caught; the members_on end-date boundary is not covered, see observation 1)
gitleaks_clean: yes (34 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1_verified: yes
AC2_verified: yes
AC3_verified: yes
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes
findings:
 1. Scope: tests/test_cli.py is changed (+7/-3) but is not in WO-0002 §2. The edit is mechanically required: WO §2 removes the init-store stub, so test_init_store_stub_exits_2 could not pass. The replacement test_init_store_creates_store asserts exit 0, "store ready: 18 tables" and that the db file exists. Strictly an Architect scope ruling, not a behavioural defect.
out_of_scope_observations:
 1. test_members_on does not exercise the closed-interval end-date boundary. Perturbing `end_date >= ?` to `end_date > ?` in members_on left every WO-0002 test passing. The PID does not state whether the end date is inclusive; the code treats it as inclusive.
 2. Empty placeholder parquet files (bars_raw/year=1900/empty.parquet, bars/ and etf_bars/ symbol=_EMPTY_/) are written on init, as WO §8 directs; they add no rows to the views.
 3. DDL matches DESIGN §3.2 for names, types, keys and the 18 tables; JSON columns are TEXT per WO §8.
 4. `.format` appears in schema.py only to build the static view DDL from constants. store.py splices only quoted identifiers validated against the schema and the store-derived glob with quotes doubled; all external values use `?` or a registered relation.
confidence: high
```

## Method and results (as reported)
- Preflight: `cat-file -t` → commit; `rev-parse HEAD` = audited SHA. `git diff --stat 75b230d e5682b9` = 17 files (+817/−10): WO §2 files, DELIVERY-LOG.md and the WO Status/Base SHA fields (procedural), and tests/test_cli.py (finding 1). ACCEPTED-RESIDUALS read; none of R1–R4 applies.
- Fresh venv, `uv sync --all-extras`: `37 passed`; `ruff check .` clean; `gitleaks detect` 34 commits, no leaks; `git status` clean after.
- Identity check `75b230d..e5682b9`: only the Rogue (Delivery Controller) noreply identity.
- ADR-0008 greps of `argus/` empty; hygiene grep of added lines: only decorator `@` false positives; AC4 grep of `argus/data/`: only the `.format` uses in observation 4.
- AC1/AC2 operator check with a `mktemp` store: 18 tables, identical second run, store dir mode 0750, parquet dirs present.
- Non-vacuity on copies under `mktemp -d`: dedupe removed → `test_bars_raw_roundtrip_and_dedupe` fails; `end_date >= ?` → `> ?` → **no WO-0002 test fails**; limiter `sleep` removed → `test_blocks_after_quota` fails; `schema_version` NOT EXISTS guard removed → `test_init_idempotent` fails; ibkr separator changed → `test_generic_share_class_rule` fails (note `test_roundtrip_all_sources` reaches the ibkr "BRK B" case through the `KNOWN_SHARE_CLASSES` table, so it alone would not catch that mutation). The 4 `test_repo_hygiene.py` failures seen in the copies are artefacts of the copy lacking repo files.
- Presentation target FUNCTIONAL_ONLY; no browser gate.
