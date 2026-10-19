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
| [WO-0004](WO-0004-polygon-provider.md) | Polygon provider, ingest CLI, validation | WO-0002 | P0-C | Approved |
| [WO-0005](WO-0005-bootstrap-history.md) | Bootstrap history provider (yfinance) | WO-0002 | P0-C | Approved |
| [WO-0006](WO-0006-fmp-calendars-events.md) | FMP calendars → events | WO-0003 | P0-D | Approved |
| [WO-0007](WO-0007-adjust-and-materialise.md) | Adjustment and materialisation of `bars` | WO-0004, WO-0005 | P0-D | Approved |
| [WO-0008](WO-0008-ibkr-reconcile-and-iv.md) | IBKR reconciliation and implied volatility | WO-0007 | P0-E | Approved |
| [WO-0009](WO-0009-nightly-orchestration.md) | Nightly orchestration, systemd, runbook, phase acceptance | WO-0003, 0006, 0007, 0008 | P0-F | Approved |

## PID-ARGUS-0000 — repository security (corrective)

| WO | Title | Depends on | Group | Status |
|---|---|---|---|---|
| [WO-0010](WO-0010-secret-drop-hardening.md) | Secret-drop hardening: ignore credential-shaped files, document the drop procedure | — | P0-A (independent of WO-0001) | Approved |

Execution order for the Delivery Controller: **WO-0001 + WO-0010
concurrently** (group P0-A, independent — WO-0010 touches no path in
WO-0001's scope) → B → C (three concurrent) → D (two concurrent) → E → F.
Base SHAs for dependent Work Orders are by-reference (`main at Closure of
…`) and are resolved by the Delivery Controller when their dependencies
close (DELIVERY-CHAIN §6.3). WO-0001's Base SHA was rebased by Architect
determination — see its §11.

## Approval record
WO-0001 … WO-0009 were approved by the Architect in the commit that
introduced this index; WO-0010 in the commit that added it (AMD-0005). Each
Work Order's §9 `Commit:` line refers to its approving commit — see
`git log -- docs/work-orders/`.
