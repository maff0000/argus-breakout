# WO-0010 — Audit record

Fresh Forge Auditor dispatch, ssh-only, audit worktree `/srv/argus-breakout-wt/WO-0010-audit` at the audited SHA.
This audit is of the **whole branch at its final head**, after the AMD-0007 delta dispatch (AC8). (An earlier audit of the
pre-delta, pre-rebase commit `040ddaa` was also GREEN; it is superseded and not relied on.)

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN (functionally; one scope finding for Architect ruling, see finding 1)
work_order: WO-0010
base_sha: 02ddd97de53c34fb2914cab17ca7cf3e832d659f
commit_sha: 57b0817447c220e31c90c11ae25f529e82ef59e7
scope_fidelity: no (docs/evidence/DELIVERY-LOG.md and docs/work-orders/WO-0010-secret-drop-hardening.md changed; WO §3 excludes anything under docs/)
offline_tests_pass: yes (4/4, no .env present, no network used)
non_vacuity_established: yes (3 perturbations on copies in mktemp dirs, each made the relevant test fail; AC5 fires on the argus-bare-key-file RuleID with non-key content)
gitleaks_clean: yes
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
AC1_verified: yes
AC2_verified: yes
AC3_verified: yes
AC4_verified: yes
AC5_verified: yes
AC6_verified: yes
AC7_verified: yes
AC8_verified: yes
findings:
1. Scope: the diff touches two paths under docs/. Exclusions say "anything under docs/ other than nothing (evidence is filed by the Delivery Controller)". `docs/evidence/DELIVERY-LOG.md` gained 2 log lines. `docs/work-orders/WO-0010-...md` had its Status changed to "In Progress" and its Base SHA row rewritten. Neither is in §2 Scope. Both look like Delivery Controller bookkeeping (the WO notes the rebase under §6.3), and neither changes behaviour. The Architect should rule whether they are acceptable.
2. Observation, not a defect: tests/test_repo_hygiene.py does not cover AC8 (governance docs not ignored). WO §5 does not require it, and I verified AC8 by hand.
out_of_scope_observations:
- The repo has no pyproject.toml or argus/ package yet, so checks 4, 6 and 7 are vacuously satisfied. `uv sync` was not applicable. I ran pytest through `uv run --no-project --with pytest`.
- The `argus-bare-key-file` rule is path-based. It fired for polygon.txt with content `hello` and with the fake AWS key. It did not fire for requirements.txt. As WO §8 says, an empty file is not covered, and I did not test that case.
confidence: high
```

## Method and results (as reported)
- Preflight: `cat-file -t` → commit; `rev-parse HEAD` → the audited SHA. `git diff --stat 02ddd97 57b0817` = 6 files, +145/−2: `.gitignore`, `.gitleaks.toml`, `README.md`, `docs/evidence/DELIVERY-LOG.md`, the WO file, `tests/test_repo_hygiene.py`. No `.env` present.
- AC1 `check-ignore -q polygon.txt` rc 0 (`.gitignore:41:/*.txt`). AC2 `-q .env.example` rc 1 and `git ls-files` lists it.
- AC8 (rc): `docs/amendments/AMD-0099-secret-test.md` 1; `docs/work-orders/WO-0099-token-test.md` 1; `.env` 0 (`.gitignore:2`); `polygon.txt` 0.
- AC3: scratch `polygon.txt` with `AKIAIOSFODNN7EXAMPLE`, `git add -A`, `git status --porcelain` empty; deleted.
- AC4: `gitleaks detect --source . --redact` 20 commits, no leaks; `protect --staged --redact` no leaks, rc 0.
- AC5: `git add -f polygon.txt` + `gitleaks protect --staged --redact -v`: leaks found 1, rc 1, `RuleID: argus-bare-key-file`, `File: polygon.txt`; same with content `hello` (rule fires on path); control `requirements.txt` with `hello` → no leaks.
- AC6: README paragraph in "Setup (once per clone)". AC7: `python3 tests/test_repo_hygiene.py` 4 PASS; `python3 -m pytest -q` and `uv run --no-project --with pytest python -m pytest -q` 4 passed.
- Non-vacuity (copies under mktemp): removing `*.pem` and `*token*` → `test_credential_patterns_ignored` FAIL; renaming the rule id → `test_gitleaks_rule_present` FAIL; bare `*` .gitignore → `test_env_example_still_tracked` + `test_env_ignored` FAIL.
- Hygiene grep of added lines (IPv4, URLs, ports, trinity/litellm/bagman): none. ADR-0008 greps trivially clean (no `argus/`).

## Delivery Controller spot-checks of the Auditor's findings (against the artefact)
- AC8 and AC5 re-run directly by the Delivery Controller on the branch worktree (exit statuses 1 1 0 0; AC5 rc 1 naming
  `argus-bare-key-file`) — see `operator-checks.md`. Confirmed.
- Finding 2 / WO §8 empty-file bound: a force-staged zero-byte `polygon.txt` in a scratch clone gives `gitleaks protect` rc 0
  (not flagged), as WO §8 states; the `.gitignore` rule is the load-bearing control. Confirmed.
- Finding 1: the two docs/ paths are clerical (Status, Base SHA, log lines) under DELIVERY-CHAIN §6.4; ruling is the Architect's.

## Delivery Controller note for the Architect (not an Auditor finding)
The delta Implementer reported that `!/docs/**` + `!/*.md` also un-ignore credential-shaped files under `docs/` and at the repo
root that match no other rule (for example `docs/x/.env`, `docs/id.pem`, root `secret.md`); root `.env`, root `polygon.txt` and
`sub/secret.md` stay ignored. The Work Order text was implemented as written; this is raised for adjudication, not pre-empted.
