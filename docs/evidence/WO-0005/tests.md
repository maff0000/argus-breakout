# WO-0005 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final code head **`70ce2d765a4c2c671f5be6402961eda7f7b7f75e`** (evidence commit follows). Every command ran on dell-debian in `/srv/argus-breakout-wt/WO-0005`; all dispatches by `ssh dell-debian`, no mount; dispatch prompts name the host and absolute paths only (AMD-0015 §2C).

## Delivery history on this branch
First implementation audited GREEN; `abdb1a2` (AMD-0012) GREEN; `2c5a8a2` (AMD-0014 §2E) GREEN; main @ 5e95343 merged cleanly apart from the WO header fields (clerical); `85c01e1` (AMD-0015 §2B cohort split) GREEN with one finding; `70ce2d7` (test fix) GREEN, no findings.
Implementer side effects disclosed: a brief `git stash`/`pop` (pass 2 work) and, during the finding fix, a mutation copy that symlinked the worktree `.venv` repointed the editable install briefly; it was repaired with `uv sync --all-extras` and tests/ruff re-run (the live bootstrap had finished before that happened).

## Mechanical results at the final code head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0005 head=70ce2d765a4c2c671f5be6402961eda7f7b7f75e branch=wo/0005-bootstrap-history
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 14.81s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
1:23PM INF scanned ~1457998 bytes (1.46 MB) in 540ms
1:23PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
The non-DC identities in the range are upstream (Architect commits and the GitHub merge of PR #4, inside the range via main); all branch commits are the Delivery Controller identity (`commit_identity_clean: yes`, Auditor-confirmed over 5e95343..70ce2d7).
