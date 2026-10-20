# WO-0011 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
- **Final audited head:** `647e1aa930c385f754593ef38b03668514eca53c` — every command ran **on the execution host `dell-debian`** in `/srv/argus-breakout-wt/WO-0011`.
  Implementer, Auditor and Delivery Controller reached that path by `ssh` only. **No mount** was used for any dispatch on this branch (§7.1(1),(2),(6)); §7.1(3)/(4) are therefore n/a.
- Implementer reported 41 passed + 1 failed (`tests/test_cli.py` asserting 18 tables, outside §2); the Delivery Controller applied the ruling-6 one-assertion edit (see `spec-gaps.md`) and committed; results below are at the final head.

## Mechanical results at the final head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0011 head=647e1aa930c385f754593ef38b03668514eca53c branch=wo/0011-actions-schema-correction
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
..........................................                               [100%]
42 passed in 6.12s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
8:41AM INF scanned ~1203189 bytes (1.20 MB) in 475ms
8:41AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
