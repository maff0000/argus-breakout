# WO-0007 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Audited and final code head `dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c` (Implementer commit `6232d8c` merged with `main` at `9ac355d`). Every command ran on the execution host `dell-debian` in `/srv/argus-breakout-wt/WO-0007` by `ssh` only; no mount. The Implementer's diff was reviewed and committed by the Delivery Controller. The AMD-0018 §2A/§2F obligations are not in the WO text; they were supplied to the Implementer as Delivery Controller notes and re-supplied to the Auditor.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0007 head=dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c branch=wo/0007-adjust-and-materialise
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 84%]
........................................                                 [100%]
256 passed in 270.48s (0:04:30)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
2:06AM INF scanned ~1769469 bytes (1.77 MB) in 519ms
2:06AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
```

Commit identity over `4321d92..HEAD`: `Rogue (Delivery Controller) <noreply@anthropic.com>` and the GitHub merge of PR #9 (upstream, `main`).
