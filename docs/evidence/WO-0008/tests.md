# WO-0008 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Every command ran on the execution host `dell-debian`, in `/srv/argus-breakout-wt/WO-0008`, reached by `ssh` only. No mount is in use; no mounted path is named in any prompt filed here. Implementer and Auditor worked offline; only the Delivery Controller's operator checks (see `operator-checks.md`) touched the gateway, after a GREEN audit and the Product Owner's confirmation.

## Mechanical results at the audited head `6d531f5` (host-run)
```
279 passed, 1 deselected in 279.38s (0:04:39)      # the deselected test is the opt-in live smoke
$ uv run ruff check .          -> All checks passed!
$ AC7a / AC7b greps (argus/)   -> rc=1 (no matches)
$ gitleaks detect --source . --redact -> no leaks found (rc=0)
$ git log --format='%an <%ae> | %cn <%ce>' c582c61..HEAD | sort -u
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
The Architect and upstream-merge identities are inside the range via main; `commit_identity_clean: yes` (Auditor, over `df0a126..6d531f5`: Delivery Controller only).

## Implementer's non-vacuity runs (13 mutants, all killed) and the Auditor's (9, all killed)
See `audit.md`. The Implementer's list: priority ignored (3 tests failed); close tolerance 0.001→0.0015 (2); volume tolerance 0.10→0.12 (2); 7496 in allowlist (3); paper-port check removed (5); `readonly=False` (3); missing symbol not a breach (2); `reconcile_log` not written (2); hv30 dropped (1); rotation offset fixed (1); volume compared at the close tolerance (4); `disconnect` not called (3); resolved-flag check removed (1).
