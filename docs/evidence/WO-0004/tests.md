# WO-0004 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final head **`b5948ae575d48c776d2d9b23f1589cebb71c8f5c`** (evidence commit follows). Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0004`; all dispatches by `ssh` only, no mount.

## Delivery history on this branch
Original implementation audited GREEN earlier at `8cfe386` (superseded); `db714d9` (AMD-0012 delta) audited GREEN; main @ d0ea305 merged cleanly (`b5948ae`).
The live backfill ran against the `.venv` of this worktree for ~104 minutes; mechanicals were re-run only after it finished.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0004 head=b5948ae575d48c776d2d9b23f1589cebb71c8f5c branch=wo/0004-polygon-provider
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 11.73s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
12:36PM INF scanned ~1370343 bytes (1.37 MB) in 491ms
12:36PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
The non-DC identities in the range are upstream (Architect commits and the GitHub merge of PR #4, inside the range via main); all branch commits are the Delivery Controller identity.
