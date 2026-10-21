# Work Orders — index

The only artefacts an Implementer may act on. Authored and approved by the
Architect; clerical fields updated by the Delivery Controller
(`docs/governance/DELIVERY-CHAIN.md` §6). Status here is a convenience
mirror; the Work Order file is authoritative.

## PID-ARGUS-0001 — Foundations

| WO | Title | Depends on | Group | Status |
|---|---|---|---|---|
| [WO-0001](WO-0001-repo-skeleton.md) | Repository skeleton, settings, logging, CLI, tooling, CI | — | P0-A | Approved |
| [WO-0002](WO-0002-schema-and-store.md) | DuckDB schema, Store and ticker normalisation | WO-0001 | P0-B | Approved |
| [WO-0003](WO-0003-universe-and-membership.md) | Universe and point-in-time membership (FMP client) | WO-0002 | P0-C | Approved |
| [WO-0004](WO-0004-polygon-provider.md) | Polygon provider, ingest CLI, validation (+ AMD-0018 delta: `bars_raw` never gated, jump rule repaired, `bar_flags`, `revalidate`) | WO-0002 | P0-C | Approved — delta pending |
| [WO-0005](WO-0005-bootstrap-history.md) | Bootstrap history provider (yfinance) | WO-0002 | P0-C | Approved |
| [WO-0006](WO-0006-fmp-calendars-events.md) | FMP calendars → events | WO-0003 | P0-D | Approved |
| [WO-0007](WO-0007-adjust-and-materialise.md) | Adjustment and materialisation of `bars` | WO-0004, WO-0005 | P0-D | Approved |
| [WO-0008](WO-0008-ibkr-reconcile-and-iv.md) | IBKR reconciliation and implied volatility (+ AMD-0019 delta: paper-port guard, flag-first sampling) | WO-0007 | P0-E | **Accepted @ `6d531f5`** — merging on CI green; AC1 ratified as a spec defect (AMD-0020) |
| [WO-0009](WO-0009-nightly-orchestration.md) | Nightly orchestration, systemd, runbook, phase acceptance (+ AMD-0020 delta: per-field reconciliation gate, pacing budget, AC6 replaced) | WO-0003, 0006, 0007, 0008 | P0-F | Approved |

## PID-ARGUS-0000 — repository security (corrective)

| WO | Title | Depends on | Group | Status |
|---|---|---|---|---|
| [WO-0010](WO-0010-secret-drop-hardening.md) | Secret-drop hardening: ignore credential-shaped files, document the drop procedure | — | P0-A (independent of WO-0001) | Merged |
| [WO-0011](WO-0011-actions-schema-correction.md) | Corporate-actions schema correction: `splits` and `dividends` (AMD-0012 defect fix) | — | P0-B2 | Merged (`02e4a2e`) |
| [WO-0012](WO-0012-store-identity-and-vacuous-validation.md) | Store relocation safety (AMD-0017 §2A; the `validate.py` half moved to WO-0004 by AMD-0018 §2G) | WO-0004 (`SCHEMA_VERSION` 4 after WO-0004's 3) | P0-D2 — may run with WO-0007 | Approved |
| [WO-0013](WO-0013-materialisation-basis-corrections.md) | Materialisation basis corrections: flags carried not subtracted, dividend basis measured, prices DOUBLE (AMD-0019) | WO-0007 (merged — this corrects it) | P0-E2 — may run with WO-0008 | Merged — accepted @ `df4b52d` |
| [WO-0014](WO-0014-boundary-and-warning-corrections.md) | Boundary and warning corrections: same-company tails retained, publication allowlist, basis-normalised comparisons (AMD-0021) | WO-0013 (merged — this corrects it) | P0-F2 — may run with WO-0009 | **Accepted @ `6236748`** — merging |
| [WO-0015](WO-0015-dividend-and-rename-diagnostics.md) | **Diagnostics only, changes nothing**: same-date dividend collapse; undeclared ticker renames (AMD-0025) | WO-0014 | P0-F3 — may run with WO-0009 | Approved |

Execution order for the Delivery Controller: **WO-0001 + WO-0010
concurrently** (P0-A) → **WO-0002** (P0-B, merged `bdce04d`) →
**WO-0003 + WO-0004 + WO-0005** concurrently (P0-C, all audited GREEN,
deltas pending) → **WO-0011** (P0-B2, must merge before the WO-0004/0005
deltas) → D (two concurrent) → E → F. Current order of work is set by
**AMD-0019 §3**: WO-0001…WO-0007, WO-0010, WO-0011 and WO-0012 are merged.
WO-0008 (accepted @ `6d531f5`) and WO-0013 (accepted @ `df4b52d`) are
merging. **WO-0009 and WO-0014 then run concurrently** (P0-F / P0-F2 —
WO-0009 owns `reconcile.py` and `providers/ibkr.py`, WO-0014 owns
`adjust.py`; they share no file). WO-0009 carries phase closure and needs
explicit two-artefact acceptance (AMD-0010); WO-0014 does not block it.
`n_symbol_days_flag_excluded` must report truthfully or be absent before
PID-ARGUS-0002 computes a feature (AMD-0021 §2F).
WO-0003, WO-0005, WO-0006 and WO-0011 are merged.
Base SHAs for dependent Work Orders are by-reference (`main at Closure of
…`) and are resolved by the Delivery Controller when their dependencies
close (DELIVERY-CHAIN §6.3). WO-0001's Base SHA was rebased by Architect
determination — see its §11.

## Approval record
WO-0001 … WO-0009 were approved by the Architect in the commit that
introduced this index; WO-0010 in the commit that added it (AMD-0005);
WO-0011 in the commit that added it (AMD-0013). Each
Work Order's §9 `Commit:` line refers to its approving commit — see
`git log -- docs/work-orders/`.
