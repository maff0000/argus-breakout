# AMD-0001 — Name the delivery host in the PIDs

| Field | Value |
|---|---|
| **Status** | Applied |
| **Amends** | `PID.md` §1, §9; `docs/pids/PID-ARGUS-0001-foundations.md` §1 |
| **Related ADR** | none |
| **Raised by** | Human (Product Owner), 2026-10-19 |
| **Affects Work Orders** | none open (all nine are Approved, none In Progress); no scope change to any |

## 1. Problem
`PID.md` §9 forbids internal hostnames in this public repository, so the
PIDs referred only to "the delivery host". The Product Owner requires the
Delivery Controller to be told, in the PIDs, that the host is
`dell-debian` with project root `/srv/argus-breakout`, so that no session
has to infer it from chat.

## 2. Change

**`PID.md` §1 — current text:**
> The delivery host is referred to only as "the delivery host"; its name is
> not recorded here (public repository).

**Replacement:**
> Delivery host: `dell-debian` (hostname only — Product Owner decision
> 2026-10-19, AMD-0001). `PROJECT_ROOT=/srv/argus-breakout` on that host.
> No IP address, port, user credential or network detail of the host is
> recorded anywhere in this repository.

**`PID.md` §9 — current text:**
> - Never commit `.env`, API keys, tokens, IBKR account identifiers or
>   usernames, internal hostnames, IP addresses, ports, model-gateway URLs or
>   model alias names, or any description of the Product Owner's network.

**Replacement:**
> - Never commit `.env`, API keys, tokens, IBKR account identifiers or
>   usernames, IP addresses, ports, model-gateway URLs or model alias
>   names, or any description of the Product Owner's network. The single
>   exception is the bare hostname of the delivery host, `dell-debian`,
>   accepted as disclosable by the Product Owner (AMD-0001); no other
>   hostname may appear.

**`docs/pids/PID-ARGUS-0001-foundations.md` §1 — current text:**
> As `PID.md` §1. `PROJECT_ROOT=/srv/argus-breakout`, `maff0000/argus-breakout`.

**Replacement:**
> As `PID.md` §1. Delivery host `dell-debian`;
> `PROJECT_ROOT=/srv/argus-breakout`; `maff0000/argus-breakout` (AMD-0001).

## 3. Consequences
- No Work Order is re-based or re-scoped.
- `docs/governance/DELIVERY-CHAIN.md` §10 and the three prompts gain the
  same one-hostname exception (editorial, same commit).
- The Auditor's public-hygiene check treats `dell-debian` as permitted and
  every other hostname as a finding.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections are tagged `(AMD-0001)`.

## 5. Approval
```
Approved by: Claude (Architect), on Product Owner instruction
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
