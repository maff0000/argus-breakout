# WO-0012 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Audited and final code head `48eb7a5df5df89e4a6831eac201e48620ef56508`. Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0012`, by `ssh` only; no mount. The Implementer's diff was reviewed and committed by the Delivery Controller, who also changed tests 2 and 3 to repair via a plain read-write `connect()` (see `audit.md`) before the commit.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0012 head=48eb7a5df5df89e4a6831eac201e48620ef56508 branch=wo/0012-store-identity-and-vacuous-validation
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 31%]
........................................................................ [ 63%]
........................................................................ [ 95%]
..........                                                               [100%]
226 passed in 249.83s (0:04:09)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
1:46AM INF scanned ~1698337 bytes (1.70 MB) in 546ms
1:46AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```

Commit identity over `4321d92..HEAD`: only `Rogue (Delivery Controller) <noreply@anthropic.com>`.
