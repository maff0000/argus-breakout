# WO-0001 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- **Final audited head:** `be5a224bf98cb5ffb25e4d462663d72f3c45c6f9` — every command below ran **on the execution host `dell-debian`**, in
  `/srv/argus-breakout-wt/WO-0001` (the output header records host, cwd and HEAD). The Implementer, Auditor and
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
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0001 head=be5a224bf98cb5ffb25e4d462663d72f3c45c6f9 branch=wo/0001-repo-skeleton
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(rc=0)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ .venv/bin/python --version
Python 3.12.15
$ uv run python -m pytest -q
.........                                                                [100%]
9 passed in 0.36s
$ uv run ruff check .
All checks passed!
$ .venv/bin/argus --version
0.1.0
$ .venv/bin/argus init-store; echo rc=$?
store not implemented (WO-0002)
rc=2
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ gitleaks detect --source . --redact
11:26PM INF scanned ~907613 bytes (907.61 KB) in 402ms
11:26PM INF no leaks found
rc=0
$ gitleaks protect --staged --redact (nothing staged)
11:26PM INF scanned ~0 bytes (0) in 285ms
11:26PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```
