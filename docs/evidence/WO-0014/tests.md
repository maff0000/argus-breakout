# WO-0014 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Every command ran on `dell-debian` in `/srv/argus-breakout-wt/WO-0014`, by `ssh` only; no mount. Implementer and Auditor worked offline. The operator checks ran on a copy of a scratch store under `unshare -rn` (no network).

## Mechanical results at the audited head `6236748` (host-run)
```
301 passed, 1 deselected in 310.46s (0:05:10)      # baseline at e16b0c5: 292 passed
$ uv run ruff check .                  -> All checks passed!
$ AC7a / AC7b greps (argus/)           -> rc=1 (no matches)
$ gitleaks detect --source . --redact  -> no leaks found (rc=0)
identity: only "Rogue (Delivery Controller) <noreply@anthropic.com>" in e16b0c5..6236748 (Auditor)
```
Non-vacuity (AC7): the three mandated mutations and seven further ones, run independently by the Auditor — see `audit.md`; the Implementer's runs gave the same outcomes (a: 3 tests failed, b: 2, c: 1).
