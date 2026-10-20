# WO-0003 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final head **`4c10c6036f0d408a8eb411701364bf4818617e97`**. Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0003`; Implementer, Auditors and
Delivery Controller reached it by `ssh` only. No mount was used for this branch at any delivery step after WO-0010; no mounted path is named in any prompt filed here.

## Delivery history on this branch
b732626, 61598ed (original, audited GREEN in the first pass of AMD-0013), 22a3ad1 (AMD-0013 delta), 465b8f3 (main @ 02e4a2e merged), f838f75 (main @ d0ea305, AMD-0014 merged),
dcfe0b0 (AMD-0014 delta), 4c10c60 (invariant fix after the pass-2 finding). Merges were resolved on the WO header fields only. Implementer diffs were reviewed and committed by the Delivery Controller.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0003 head=4c10c6036f0d408a8eb411701364bf4818617e97 branch=wo/0003-universe-and-membership
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed in 49.23s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
12:12PM INF scanned ~1327582 bytes (1.33 MB) in 498ms
12:12PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
Identity: the listed authors are the Architect and the GitHub merge of PR #4 (upstream, inside the range via main) and the Delivery Controller identity for all branch commits (`commit_identity_clean: yes`, Auditor-confirmed over `d0ea305..4c10c60`).
