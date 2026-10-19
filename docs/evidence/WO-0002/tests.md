# WO-0002 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism
- **Audited head:** `e5682b9d57e09a4575cf25e57564fb94eecf244b`. Every command below ran **on the execution host `dell-debian`** in
  `/srv/argus-breakout-wt/WO-0002` (output header records host, cwd and HEAD). The Implementer, Auditor and Delivery
  Controller reached that path by `ssh` only. **No mount** was used for any dispatch; no mounted path appears in any
  prompt (§7.1(1),(2),(6)). The §7.1(3) write-visibility check is therefore not applicable (no second view of the path).
- The Implementer's diff was reviewed by the Delivery Controller and committed by it (the Implementer never commits).
  One delta dispatch to the same Implementer replaced the obsolete `init-store` stub test (see `spec-gaps.md`).

## Mechanical results at the audited head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0002 head=e5682b9d57e09a4575cf25e57564fb94eecf244b branch=wo/0002-schema-and-store
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
.....................................                                    [100%]
37 passed in 4.66s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
11:57PM INF scanned ~696239 bytes (696.24 KB) in 437ms
11:57PM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
