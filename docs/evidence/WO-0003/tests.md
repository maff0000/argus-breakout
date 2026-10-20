# WO-0003 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- Audited head `22a3ad1721117690e2b3a3c9c2d6eff274b973c5`; PR head is `465b8f3…` = the audited tree plus a clerical merge of main (`02e4a2e`). Every command ran **on the execution host `dell-debian`** in `/srv/argus-breakout-wt/WO-0003`; Implementer, Auditor and Delivery Controller reached it by `ssh` only. **No mount** was used for any dispatch on this branch (§7.1(1),(2),(6)); §7.1(3)/(4) n/a.
- History: first implementation audited GREEN at `b732626` with one weak-test finding, fixed by test-only delta `61598ed`; then the AMD-0013 delta (`22a3ad1`) and a whole-branch re-audit (this evidence). Earlier evidence is superseded.

## Mechanical results at the PR head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0003 head=465b8f3559ef47ae82dd659d998470183c1edda1 branch=wo/0003-universe-and-membership
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 44.91s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
9:02AM INF scanned ~1259951 bytes (1.26 MB) in 459ms
9:02AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
