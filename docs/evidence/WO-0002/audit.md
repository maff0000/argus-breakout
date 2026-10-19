# WO-0002 — Audit record (re-audit of the whole branch)

Fresh Forge Auditor dispatch, ssh-only, detached audit worktree at the audited SHA. (An earlier audit at `e5682b9` was superseded by AMD-0011 and is not relied on; see tests.md.)

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0002
base_sha: 75b230dacb555dbe2f3f4347d640262348bf2b4a
commit_sha: 19ad58f96e100f90f57ebfc3b2fdb87e46516c39
scope_fidelity: yes (every changed path is in WO §2, or is a docs/ path authored by the Delivery Controller or Architect, which is procedural. tests/test_cli.py is now listed in §2 via AMD-0011.)
offline_tests_pass: yes (38 passed, plain run and under `unshare -n` with no network; no .env present; ruff check clean)
non_vacuity_established: yes
gitleaks_clean: yes (37 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes (only Rogue (Delivery Controller) and Claude (Architect) noreply identities)
AC1_verified: yes
AC2_verified: yes
AC3_verified: yes
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes
AC7_verified: yes
findings: none
out_of_scope_observations:
 1. SQL is built by concatenation in two places, neither carrying external values: upsert splices identifiers (checked against information_schema.columns / schema.DDL and quoted via _quote_ident; values go through the registered `incoming` relation); init_schema splices the store-derived parquet glob into the view DDL with single quotes doubled. Every other execute uses `?` placeholders.
 2. `features` carries only (date, symbol); DESIGN §3.2 leaves its columns open (spec-gaps.md).
 3. JSON columns (ratio_z, reasons, grade) are TEXT as WO §8 directs.
 4. Empty placeholder parquet files are written on init as WO §8 directs.
 5. argus/cli.py ends with a trailing blank line after the stub removal; ruff passes (cosmetic).
confidence: high
```

## Method and results (as reported)
- Preflight: `cat-file -t` → commit; `rev-parse HEAD` = audited SHA. `git diff --stat 75b230d 19ad58f` = 23 files (+1045/−15); `argus/` and `tests/` changes all in §2; `docs/` changes are DC/Architect clerical, evidence and governance files.
- Fresh venv, `uv sync --all-extras`: 38 passed; ruff clean; `unshare -n` run: 38 passed; gitleaks 37 commits, no leaks; identity check `75b230d..19ad58f`: only the two noreply identities.
- Public-hygiene greps over the whole diff (IPv4, URLs, 4–5 digit ports, gateway/model names, IBKR account patterns, `192.168`): empty. ADR-0008 greps of `argus/`: empty; paths only via `argus_store_dir`; `tempfile` in the target dir.
- AC4 grep of `argus/data/`: all f-strings are `ValueError` messages; every `execute` is parameterised or uses constants.
- CLI on a temp store: `store ready: 18 tables`, identical second run, mode 750, `SHOW TABLES` 18 rows, one `schema_version` row.
- Non-vacuity on a `git archive` copy: baseline 8 passed in test_store.py; `end_date >= ?`→`>`: `test_members_on_boundaries` fails (1 failed, 7 passed); `start_date <= ?`→`<`: same test fails; restored: 8 passed; extra mutation dedupe `keep="last"`→`"first"`: `test_bars_raw_roundtrip_and_dedupe` fails.
- Schema/PID conformance: 18 DDL entries vs DESIGN §3.2 and `Store` signatures vs PID §8.5 match; `members_on` uses the exact AMD-0011 predicate; §8.6 provider-base names and §8.4 `CANONICAL` regex present.
