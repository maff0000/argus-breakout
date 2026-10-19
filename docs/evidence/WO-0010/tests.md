# WO-0010 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- **Final audited head:** `57b0817447c220e31c90c11ae25f529e82ef59e7` — every command below ran **on the execution host `dell-debian`**, in
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


## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0010 head=57b0817447c220e31c90c11ae25f529e82ef59e7 branch=wo/0010-secret-drop-hardening
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
4 passed in 0.05s
$ ruff (project config from WO-0001 pyproject, run from this worktree root)
All checks passed!
$ gitleaks detect --source . --redact
11:27PM INF scanned ~569849 bytes (569.85 KB) in 403ms
11:27PM INF no leaks found
rc=0
$ gitleaks protect --staged --redact (nothing staged)
11:27PM INF scanned ~0 bytes (0) in 288ms
11:27PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```
