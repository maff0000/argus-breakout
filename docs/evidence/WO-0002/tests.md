# WO-0002 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism
- **Audited head:** `19ad58f96e100f90f57ebfc3b2fdb87e46516c39`. Every command below ran **on the execution host `dell-debian`** in `/srv/argus-breakout-wt/WO-0002`
  (output header records host, cwd and HEAD). Implementers, Auditors and the Delivery Controller reached that path by `ssh` only.
  **No mount** was used for any dispatch; no mounted path appears in any prompt (§7.1(1),(2),(6)). §7.1(3) write-visibility check: n/a.
- The Delivery Controller reviewed and committed every Implementer diff (Implementers never commit).

## History (disclosed)
1. Implementer dispatch 1 delivered the WO §2 scope (`e5682b9` after a delta that replaced the obsolete `init-store` stub test). First audit:
   GREEN at `e5682b9` with `scope_fidelity: no` (test_cli.py) and an untested `end_date` boundary. The Delivery Controller declined to self-certify
   under AMD-0010 and returned to the Architect; AMD-0011 followed (ratified test_cli.py, confirmed inclusive `end_date`, added AC7).
2. `main` (`92cb752`) was merged into the branch by hand (one conflict in the WO header, resolved by taking main's Amendments line and re-applying Base SHA).
3. A fresh Implementer added `test_members_on_boundaries` (test only; `argus/` unchanged — commit `0958745`).
4. The first audit's evidence files were removed from the branch and the whole branch was re-audited by a fresh Auditor at `19ad58f96e100f90f57ebfc3b2fdb87e46516c39`. This audit is the one relied on.

## Mechanical results at the audited head (host-run, verbatim)
```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0002 head=19ad58f96e100f90f57ebfc3b2fdb87e46516c39 branch=wo/0002-schema-and-store
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
......................................                                   [100%]
38 passed in 4.89s
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
12:15AM INF scanned ~725250 bytes (725.25 KB) in 483ms
12:15AM INF no leaks found
rc=0
$ git status --porcelain (after)
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
