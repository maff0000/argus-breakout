# WO-0003 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final head **`6896fe7b3ca156bf64d633aa11eca4cbad796073`**. Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0003`; Implementer, Auditors and
Delivery Controller reached it by `ssh` only. No mount was used for this branch at any delivery step after WO-0010; no mounted path is named in any prompt filed here.

## Delivery history on this branch
b732626, 61598ed (original, audited GREEN in the first pass of AMD-0013), 22a3ad1 (AMD-0013 delta), 465b8f3 (main @ 02e4a2e merged), f838f75 (main @ d0ea305, AMD-0014 merged),
dcfe0b0 (AMD-0014 delta), 4c10c60 (invariant fix after the pass-2 finding), 8530a79 (AMD-0015/0016 delta; pass-4 RED), a471f28 (F1 fix; pass-5 RED), 6896fe7 (route-(b) test, fixture inlined; pass-6 GREEN). main @ 5e95343 merged at c6bd2b0. Merges were resolved on the WO header fields only. Implementer diffs were reviewed and committed by the Delivery Controller.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0003 head=6896fe7b3ca156bf64d633aa11eca4cbad796073 branch=wo/0003-universe-and-membership
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 64%]
.......................................                                  [100%]
111 passed in 211.50s (0:03:31)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
6:26PM INF scanned ~1520088 bytes (1.52 MB) in 553ms
6:26PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
Identity: the listed authors are the Architect and the GitHub merge of PR #4 (upstream, inside the range via main) and the Delivery Controller identity for all branch commits (`commit_identity_clean: yes`, Auditor-confirmed over `d0ea305..4c10c60`).
