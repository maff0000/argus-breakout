# WO-0010 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- **Final audited head:** `7a0cf85556be311f050de0aa36449ee06e60c2d1` — every command below ran **on the execution host `dell-debian`**, in
  `/srv/argus-breakout-wt/WO-0010` (the output header records host, cwd and HEAD). The Implementer, Auditor and
  Delivery Controller reach that path by `ssh` only. There is **no mount** in use for any dispatch on this
  branch at its final head, and no mounted path is named in any prompt filed here (§7.1(1),(2),(6)).
- **History (disclosed):** the first Implementer dispatch for this Work Order wrote its files through an sshfs mount
  (`/mnt/argus-wt`, one mount exporting the shared parent directory; the prompt named the host path, the edit
  path was the mount path) and ran commands on the host over ssh. That contravened what AMD-0006 later
  required. Before any result from that implementation was treated as evidence the Delivery Controller ran the
  §7.1(3) sentinel check (SHA-256, both directions, mount↔host: MATCH in both directions) and the §7.1(4)
  reconciliation (host `git status --porcelain` and `git diff --stat` empty; SHA-256 of every file in the
  worktree, excluding `.git`/`.venv`/caches, identical on host and mount: 63 files WO-0001, 45 files WO-0010);
  mount-side `git` cannot run (a worktree's `.git` points at a host path), so the file-hash comparison stood in for
  it. One stale sshfs directory-cache entry for a deleted sentinel was observed and cleared. Isolation finding:
  each branch's committed paths against its base lay inside its own §2 scope plus Delivery Controller
  clerical/evidence files; neither branch contained the other's files; the shared parent held no stray files;
  `/srv/argus-breakout` was clean. The Architect ruled this acceptable provisionally (corroboration by the Auditors'
  `scope_fidelity`, below). The branch was subsequently rebased (unpushed) onto `02ddd97` and its commits re-authored
  to a noreply identity with **identical trees** (verified by tree hash before/after each rewrite); all results
  below were re-run on the final head.

- **WO-0010 additional history:** after the first PR was opened, AMD-0008 superseded the AMD-0007 negation lines; PR #2 was returned to draft, `main` (4d1f2f1) was merged into the branch (conflict resolved by hand), a single combined delta dispatch implemented AMD-0007 + AMD-0008 (AC8, AC9), and the superseded evidence was removed from the branch before this audit. Everything below is at the final head.

## Commit identity check (AMD-0009)
Run on `dell-debian`; repo-local `author.*`/`committer.*` confirmed as the Delivery Controller identity first.
```
$ git log --format='%an <%ae> | %cn <%ce>' c582c61152dd68807aad59aa58a347e78b755cb2..HEAD | sort -u
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
The Architect lines are upstream governance commits inside the range (main merged at `4d1f2f1`). `commit_identity_clean: yes`
(also reported by the Auditor over the audit base).


## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0010 head=7a0cf85556be311f050de0aa36449ee06e60c2d1 branch=wo/0010-secret-drop-hardening
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(rc=0)
$ python3 tests/test_repo_hygiene.py
PASS test_credential_patterns_ignored
PASS test_env_example_still_tracked
PASS test_env_ignored
PASS test_gitleaks_rule_present
rc=0
$ uvx pytest -q -p no:cacheprovider tests/test_repo_hygiene.py
....                                                                     [100%]
4 passed in 0.04s
$ ruff (project config from WO-0001 pyproject, run from this worktree root)
All checks passed!
$ gitleaks detect --source . --redact
11:36PM INF scanned ~615146 bytes (615.15 KB) in 453ms
11:36PM INF no leaks found
rc=0
$ gitleaks protect --staged --redact (nothing staged)
11:36PM INF scanned ~0 bytes (0) in 350ms
11:36PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```
