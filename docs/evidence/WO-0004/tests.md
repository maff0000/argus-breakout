# WO-0004 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- **Audited and final code head:** `46ad537e5b0a95253957b7db7b0dbfd980b443d3`. Every command below ran on the execution host `dell-debian`, in `/srv/argus-breakout-wt/WO-0004`, reached by `ssh` only. No mount was used for any dispatch on this branch; no mounted path is named in any prompt filed here.
- **Process notes:** the Implementer's diff was reviewed and committed by the Delivery Controller (one `I001` import-order fix in `argus/cli.py` by the DC). `main` (`9a7a505`, AMD-0018) was merged into the branch before the delta; conflicts in `argus/cli.py` (all import lines kept), `DELIVERY-LOG.md` and the WO header were resolved by hand.
- **Commit identity** over `9a7a505..HEAD`: only `Rogue (Delivery Controller) <noreply@anthropic.com>`.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0004 head=46ad537e5b0a95253957b7db7b0dbfd980b443d3 branch=wo/0004-polygon-provider
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 97%]
......                                                                   [100%]
222 passed in 244.93s (0:04:04)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
1:31AM INF scanned ~1674197 bytes (1.67 MB) in 632ms
1:31AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```
