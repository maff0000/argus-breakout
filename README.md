# Argus-Breakout

A nightly, locally-run S&P 500 scanner that detects sector rotation early
(breadth, relative strength, volume), ranks constituents against an
equal-weight baseline and their sector, and writes a short research brief
with a local model. Paper-trading only. See `PID.md` for the project
definition and `docs/architecture/DESIGN.md` for the design.

## Governance

This repository is delivered under the Forge framework
(`https://github.com/maff0000/forge`) with an Architect-led Work Order
process. **Read `docs/governance/DELIVERY-CHAIN.md` before doing anything.**

```
Architecture decision → PID/Amendment → Git-tracked Work Order
→ Delivery Controller → Implementer → Independent Audit → PR
→ Architect Acceptance → Merge → Closure
```

```
NO PID → NO WORK ORDER.   NO WORK ORDER → NO IMPLEMENTATION.
NO INDEPENDENT AUDIT + ARCHITECT ACCEPTANCE → NO MERGE.
NO GIT RECORD → NOT DURABLE PROJECT AUTHORITY.
```

| Where | What |
|---|---|
| `PID.md` | Master Project Initiation Document |
| `docs/pids/` | Phase PIDs |
| `docs/architecture/` | Design and ADRs |
| `docs/amendments/` | Amendments to approved PIDs |
| `docs/work-orders/` | Work Orders (the only thing an Implementer may act on) |
| `docs/evidence/` | Audit verdicts, prompts, acceptance records, delivery log |
| `docs/governance/prompts/` | Baked prompts for the Delivery Controller, Implementer and Auditor |

## Setup (once per clone)

```sh
./ops/bootstrap        # verifies gitleaks and activates the committed pre-commit hook
cp .env.example .env   # fill in locally; .env is never committed
```

Credential values are handed over in `/tmp` only (for example
`/tmp/<provider>.txt`), moved into `.env` without being printed, and then
shredded. Never place a credential file inside the repository working tree.

Future direction — explicitly **not** approved scope — is in
`docs/ROADMAP.md` (AMD-0024 §2F).

This repository is public until project completion. No secrets,
hostnames, ports, account identifiers or gateway details are ever
committed; see `PID.md` §9.
