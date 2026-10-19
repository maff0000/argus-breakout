# ADR-0001 — Governance: Forge + Architect-led Work Orders

**Status:** Accepted · **Date:** 2026-10-19

## Context
The Product Owner mandates the chain *Architecture decision → PID/Amendment →
Git-tracked Work Order → Delivery Controller → Implementer → Independent
Audit → PR → Architect Acceptance → Merge → Closure*, with the invariants NO
PID → NO WO; NO WO → NO IMPLEMENTATION; NO AUDIT + ACCEPTANCE → NO MERGE; NO
GIT RECORD → NOT AUTHORITY. Forge provides the PL/Engineer/Auditor loop, the
PID template, the startup gate and the evidence doctrine, but has no
Architect role, no Work Order or Amendment artefacts, and no acceptance
step distinct from the PL.

## Decision
Keep Forge unchanged and add a project-level control envelope in this
repository: `docs/governance/DELIVERY-CHAIN.md` (binding), templates for
Work Orders, Amendments and Acceptance records, and three baked prompts
(Delivery Controller, Implementer, Auditor) that restate every rule. Forge's
PL is the Delivery Controller. Architect Acceptance is a fixed-form PR
comment plus `docs/evidence/WO-NNNN/acceptance.md`.

## Consequences
- Rogue runs from `/srv/forge` with `PROJECT_ROOT=/srv/argus-breakout` and
  must use Forge's hub-model manual-worktree procedure.
- All authority artefacts are files in git; chat carries none.
- Overhead per change is one Work Order; hotfixes do not exist.
