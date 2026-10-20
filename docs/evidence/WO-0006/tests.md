# WO-0006 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Final code head **`9a841b07ebe42491d921e309a2b0aed14d2dcef9`** (branched from main `46086e6`). Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0006`;
Implementer, Auditor and Delivery Controller reached it by `ssh` only. No mount was used; no mounted path is named in any prompt filed here.

## Delivery history
Implementer dispatch 1 (diff reviewed by the DC); one delta (a test pinning the `date <= today` override on `confirmed`, which had survived mutation) before commit; code commits `9d6e192` (first audited GREEN) and `9a841b0` (delta after the live check showed the real FMP payload: recorded fixtures, time-of-day coverage line; whole branch re-audited GREEN). main @ 46086e6 is the base; no later main merge was needed except the clerical log lines.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0006 head=9a841b07ebe42491d921e309a2b0aed14d2dcef9 branch=wo/0006-fmp-calendars-events
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 41%]
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 226.98s (0:03:46)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
8:27PM INF scanned ~1581377 bytes (1.58 MB) in 482ms
8:27PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
Identity: the Architect and GitHub-merge lines are upstream commits inside the range via main; every WO-0006 commit is the Delivery Controller identity (`commit_identity_clean: yes`).
