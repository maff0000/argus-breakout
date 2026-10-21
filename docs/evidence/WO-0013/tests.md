# WO-0013 — tests and access mechanism (DELIVERY-CHAIN §7.1, AMD-0006)

## Access mechanism (disclosed)
Every command ran on the execution host `dell-debian`, in `/srv/argus-breakout-wt/WO-0013`, reached by `ssh` only; no mount is in use. Implementer and Auditor worked offline. The operator checks ran on a copy of a scratch store under `unshare -rn` (no network).

## Mechanical results at the audited head `df4b52d` (host-run; run on the identical tree before the commit)
```
269 passed in 288.73s (0:04:48)
$ uv run ruff check .                  -> All checks passed!
$ AC7a / AC7b greps (argus/)           -> rc=1 (no matches)
$ gitleaks detect --source . --redact  -> no leaks found (rc=0)
$ git log --format='%an <%ae> | %cn <%ce>' c582c61..HEAD | sort -u
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>
```
Auditor, over `df0a126..df4b52d`: Delivery Controller identity only. Baseline at `df0a126` was 256 passed; +13 tests net (one WO-0007 test replaced under AMD-0019 §2A: `test_quarantine_does_not_withhold_yfinance_row` → `test_quarantine_is_not_filled_from_yfinance`).

## Non-vacuity (AC8)
(a) restoring the flag exclusion → `test_flagged_symbol_day_is_published` and `test_no_cross_source_substitution` (+ `test_seam_rerun_is_a_no_op` in the Implementer's run) fail; (b) dropping the split division → `test_as_paid_dividend_is_divided_by_cumulative_split` fails; extra: Float32 cast → `test_prices_are_float64` fails; judge failure recorded as `failed` → `test_judge_failure_records_quarantined` fails. Independently re-run by the Auditor (`audit.md`).
