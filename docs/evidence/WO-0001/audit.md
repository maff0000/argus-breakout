# WO-0001 — Audit record

Fresh Forge Auditor dispatch, ssh-only, audit worktree `/srv/argus-breakout-wt/WO-0001-audit` at the audited SHA.
This audit is of the **final** head. (An earlier audit of the tree-identical pre-rebase commit `be43d78` was also
GREEN with the same single procedural finding; it was superseded by the rebase onto `02ddd97` and is not relied on.)

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0001
base_sha: 02ddd97de53c34fb2914cab17ca7cf3e832d659f
commit_sha: be5a224bf98cb5ffb25e4d462663d72f3c45c6f9
scope_fidelity: yes for all implementer-owned paths (see finding 1 on DC-authored docs/ paths)
offline_tests_pass: yes (9 passed; run under `unshare -n`, no network, no .env)
non_vacuity_established: yes (5 mutations on a `git archive` copy under mktemp, each failed the intended tests)
gitleaks_clean: yes (20 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes (only hits: ib_host default "127.0.0.1" per PID 8.2, the permitted dell-debian, and public astral-sh GitHub URLs in host-setup.md)
AC1_verified: yes
AC2_verified: yes
AC3_verified: yes
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes
AC7_verified: yes
findings:
 1. (minor, non-blocking) Exclusion check: the diff touches paths under docs/ that are not in WO §2 and fall under the §3 exclusion "no changes under docs/ (the Delivery Controller adds evidence)". The paths are docs/evidence/DELIVERY-LOG.md, docs/evidence/WO-0001/host-setup.md, and docs/work-orders/WO-0001-repo-skeleton.md (the status and base-SHA fields). They come from the DC commits 27909a4 and be5a224, and host-setup.md is the evidence WO §7 requires. The Architect should confirm that DC edits to the WO header fields are acceptable.
out_of_scope_observations:
 - The worktree already had .venv, .pytest_cache and .ruff_cache. All are gitignored, and `git status --short` was empty after the run. I recreated .venv for the audit (rm -rf, then uv venv).
 - WO §7 evidence files (tests.md, operator-checks.md and the rest) are not in the diff. They are DC deliverables for later.
confidence: high
```

## Method and results (as reported)
- Preflight: `cat-file -t` → commit; `rev-parse HEAD` → the audited SHA.
- Scope: `git diff --stat 02ddd97… be5a224…` = 22 files, +1936/−5; implementer paths (pyproject.toml, uv.lock, ci.yml, `argus/`, `tests/`) all in §2; DC paths = the three `docs/` files in finding 1.
- Sources read against PID §8.1–8.3 and AMD-0007: `pyproject.toml` matches (hatchling backend, wheel packages entry, deps, extras, ruff config, pytest marker/addopts); `settings.py` matches §8.2 field for field; `ConfigError` carries only missing names; `logging.py` JSON to stdout, UTC `ts`, redaction; `cli.py` has `--version`, five sub-apps, marker comment, init-store stub exit 2; CI guards removed.
- Offline run: no `.env`; fresh venv CPython 3.12.15; `uv sync --all-extras --frozen` ok (AC1); `uv run ruff check .` clean (AC2); `unshare -n uv run --frozen python -m pytest -q` → 9 passed (AC3); `argus --version` → 0.1.0 (AC4); `uv lock --check` → 61 packages, and a clean `git archive` copy synced `--frozen` (AC5); `gitleaks detect` 20 commits, no leaks (AC6); both AC7 greps empty.
- Hygiene grep of added lines (excluding `uv.lock`): only the three hits listed in the verdict block.
- Non-vacuity (mutations on a `git archive` copy; baseline 9 passed): config default `cfg` → `test_defaults_without_env` + `test_config_dir_default_and_override` fail; `require()` first-missing-only → `test_require_lists_all_missing` fails; `polygon_api_key` plain `str` → `test_secret_not_in_repr` + `test_configured_secret_redacted` fail; redaction regex removed → `test_json_and_redaction` fails; init-store exits 0 → `test_init_store_stub_exits_2` fails. `test_version` asserts `0.1.0` and exit 0 (not mutated).
- Presentation target FUNCTIONAL_ONLY; no browser gate.

## Delivery Controller spot-checks of the Auditor's findings (against the artefact)
- Finding 1: `git log --format='%h %an' 02ddd97..HEAD` (see `operator-checks.md`) shows the three branch commits, all by the
  Delivery Controller identity; the docs/ paths are the Status/Base SHA fields, one log line per state change and the
  `host-setup.md` required by WO §7. Confirmed as bookkeeping/evidence; ruling on the Work Order §3 wording is the Architect's.
- Mutation (config default `cfg`) re-run by the Delivery Controller on a clean checkout of the audited SHA: 2 failed, 7 passed;
  restored → 9 passed (see `operator-checks.md`). Confirmed.
- `hatchling`: the Auditor read `pyproject.toml` against AMD-0007 (which names it) and raised no finding.
