# WO-0010 — Audit record

Fresh Forge Auditor dispatch, ssh-only, audit worktree `/srv/argus-breakout-wt/WO-0010-audit` at the audited SHA.
This audit is of the **whole branch at its final head**, after the single combined AMD-0007 + AMD-0008 delta dispatch
(`*.txt` at all depths, extension-scoped negations, AC8 and AC9). Earlier audits, made against superseded scope, were
withdrawn: PR #2 was returned to draft, the superseded evidence was removed from the branch before this audit so the
Auditor could not see an earlier verdict, and none of it is relied on. The audit base is `4d1f2f1` (the `main` commit
merged into the branch), so the diff shows only this Work Order's own changes.

## Verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0010
base_sha: 4d1f2f1a38392fd70f0095f979349c0c9fc4866a
commit_sha: 7a0cf85556be311f050de0aa36449ee06e60c2d1
scope_fidelity: no (finding 1 only: docs/evidence/DELIVERY-LOG.md and docs/work-orders/WO-0010-secret-drop-hardening.md changed. Both are Delivery Controller clerical files; the four §2 scope paths are fully covered.)
offline_tests_pass: yes (4/4 via `python3 -m pytest -q tests/test_repo_hygiene.py` and via `python3 tests/test_repo_hygiene.py`. `uv sync` is impossible because the branch has no pyproject.toml or uv.lock yet, as WO §4 anticipates. I ran no `uv run pytest` and no `argus` package tests. No .env was present and the tests use no network.)
non_vacuity_established: yes (perturbed copies: removing `*.txt` gave 1 FAIL, removing `*token*` gave 1 FAIL, removing `*.pem` gave 1 FAIL, appending `*` gave FAIL test_env_example_still_tracked, renaming the gitleaks rule id gave FAIL test_gitleaks_rule_present. AC5 is also a live perturbation.)
gitleaks_clean: yes (8.30.1: `detect --source . --redact` found no leaks across 27 commits, exit 0, on the worktree and on a clone at the audited SHA)
access_mechanism: ssh (every command ran as `ssh <ssh-target> '...'`; destructive and perturbation tests ran in `mktemp -d` clones of the worktree checked out at 7a0cf85, deleted afterwards; the worktree `git status --short` is empty)
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes (the only URL in the added diff lines is the public PR URL, https://github.com/maff0000/argus-breakout/pull/2. No IPs, ports, internal hostnames or aliases.)
commit_identity_clean: yes (`git log --format='%an <%ae> | %cn <%ce>' 4d1f2f1..7a0cf85 | sort -u` returned only `Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>`. That is the PID §9 / AMD-0009 identity.)
AC1_verified: yes (`git check-ignore -q polygon.txt` exit 0)
AC2_verified: yes (`git check-ignore -q .env.example` exit 1, and `git ls-files .env.example` lists it)
AC3_verified: yes (with `polygon.txt` containing AKIAIOSFODNN7EXAMPLE, `git add -A` then `git status --porcelain` printed nothing)
AC4_verified: yes (`gitleaks detect --source . --redact` exit 0; `gitleaks protect --staged --redact` with nothing staged exit 0)
AC5_verified: yes (force-staged `polygon.txt` with fake key content: `protect --staged --redact` exit 1 with 2 leaks. Content `hello` alone: exit 1, `RuleID: argus-bare-key-file`, `File: polygon.txt`. A force-staged `requirements.txt` gave no leak.)
AC6_verified: yes (README.md "Setup (once per clone)" now says credential values are handed over in `/tmp` only, e.g. `/tmp/<provider>.txt`, moved into `.env` without being printed, shredded, and never placed in the working tree)
AC7_verified: yes (see offline_tests_pass; the `python tests/test_repo_hygiene.py` invocation also works and exits 0)
AC8_verified: yes (`docs/amendments/AMD-0099-secret-test.md` exit 1; `docs/work-orders/WO-0099-token-test.md` exit 1; `.env` exit 0; `polygon.txt` exit 0)
AC9_verified: yes (all 12 must-be-ignored paths exit 0: .env, .env.local, secret.key, id.pem, polygon.txt, docs/x/polygon.txt, deep/a/b/fmp.txt, docs/x/.env, docs/secret.key, docs/id.pem, docs/credentials.json, sub/secret.md. All 7 must-not-be-ignored paths exit 1: docs/amendments/AMD-0011-secret-rotation.md, docs/work-orders/WO-0099-token-test.md, docs/runbook/OPERATIONS.md, docs/README.md, README.md, PID.md, .env.example.)
findings:
1. Minor and non-blocking, for the Architect to rule on. Scope: the diff touches `docs/evidence/DELIVERY-LOG.md` (7 appended log lines) and `docs/work-orders/WO-0010-secret-drop-hardening.md` (Status, Base SHA and PR fields). WO §3 excludes "anything under docs/ other than nothing", but WO §7 and §10 assign evidence and log writing to the Delivery Controller. The edits are status and log bookkeeping only, with no policy text changed. No `ops/`, `scripts/hooks`, `.github/workflows` or `PID.md` changes, and no `argus/` code.
2. Informational, a bounded claim rather than a defect. A force-staged zero-byte `polygon.txt` is NOT flagged by the gitleaks rule (`protect --staged` gave "no leaks found", exit 0). WO §8 and AMD-0007 accept this, and `.gitignore` is the load-bearing control. AC5 correctly uses non-empty content.
3. Informational: `docs/evidence/WO-0010/` (evidence the WO lists) is absent from the branch. The latest commit message says the superseded evidence was removed and "regenerated after re-audit". It is the DC's to file, not a defect in the code.
out_of_scope_observations:
- Item 7 (ADR-0008 portability) is vacuous: there is no `argus/` directory, so `grep -rnE "['\"]/(srv|etc|usr|opt|home|var)/" argus/` found nothing because there was nothing to search.
- Item 6 (architecture conformance): the WO touches no application code (no settings module use, SQL or UTC), so those checks do not apply.
- `uv venv` works, but `uv sync` fails with "No pyproject.toml" until WO-0001 lands.
- The worktree contains an untracked, ignored `.pytest_cache`, left over from earlier runs.
confidence: high
```
(Verdict transcribed as returned; the only edit is the ssh login target in `access_mechanism`, replaced by `<ssh-target>` per PID §9.)

## Delivery Controller spot-checks of the Auditor's findings (against the artefact)
- AC9 matrix re-run row for row by the Delivery Controller on the branch worktree: 19 rows, 0 mismatches (`operator-checks.md`); AC8 four commands match. Confirmed.
- AC5 re-run directly: force-staged dummy `polygon.txt` → `gitleaks protect --staged` rc 1, `RuleID: argus-bare-key-file`. Confirmed.
- Finding 2 (zero-byte file): force-staged empty `polygon.txt` in a scratch clone → rc 0, not flagged, as WO §8 states. Confirmed.
- Finding 3: `docs/evidence/WO-0010/` was emptied deliberately before the audit and is refilled by this commit.
- Finding 1: the two docs/ paths are clerical (Status, Base SHA, PR, log lines) under DELIVERY-CHAIN §6.4; the ruling is the Architect's.
- Identity: `git log --format='%an <%ae> | %cn <%ce>' c582c61..HEAD | sort -u` on the final head lists only the two project identities (`tests.md`).

## Accepted residual (AMD-0008, recorded)
Root-level Markdown with a credential-shaped *filename* (`secret.md`, `token.md`, `api-key.md`) remains stageable because `!/*.md` must
keep `README.md` and `PID.md` tracked; gitleaks content scanning is the control (WO §8). Not an Auditor finding.
