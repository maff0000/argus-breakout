# WO-0005 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final head **`2c5a8a2bbd14b6db16d13a26beb7ba53e1b9b144`** (evidence commit follows). Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0005`; all dispatches by `ssh` only, no mount.

## Delivery history on this branch
First implementation audited GREEN earlier; `abdb1a2` (AMD-0012: splits/dividends tables, integer 98% rule) audited GREEN; main @ d0ea305 merged (clerical); `2c5a8a2` (AMD-0014 §2E: skips count as successes) audited GREEN.
The Implementer briefly ran `git stash` / `git stash pop` in the worktree to compare formatting; it restored cleanly (disclosed).

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0005 head=2c5a8a2bbd14b6db16d13a26beb7ba53e1b9b144 branch=wo/0005-bootstrap-history
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 10.47s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
12:15PM INF scanned ~1351497 bytes (1.35 MB) in 468ms
12:15PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
The two non-DC identities in the range are upstream (Architect commits and the GitHub merge of PR #4, inside the range via main); all branch commits are the Delivery Controller identity.
