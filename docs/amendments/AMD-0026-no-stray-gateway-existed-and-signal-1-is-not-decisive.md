# AMD-0026 — Retraction: no stray live gateway existed; and WO-0015's signal (1) is not decisive

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0021` §1(e), §2E (retracted in part); `AMD-0022` metadata, §1(b), §2C (retracted in part); `docs/architecture/DESIGN.md` §10; `docs/work-orders/WO-0009-nightly-orchestration.md` AC10a; `docs/work-orders/WO-0015-dividend-and-rename-diagnostics.md` §2, AC3, AC6 |
| **Related ADR** | ADR-0004, ADR-0006 |
| **Raised by** | Delivery Controller, 2026-10-21: *"There is no live IBKR gateway on dell-debian: 4001 is a LiteLLM container and ib-gateway is paper-only on 4002."* And the WO-0015 Implementer, disclosing that AC6 mutation (b) only fails when signal (1)'s materiality is also weakened |
| **Affects Work Orders** | WO-0009 (AC10a reworded), WO-0015 (§2, AC3, AC6 corrected mid-flight) |

## 1. Problem

### (a) I identified a service by its port number and wrote it down as fact — twice
The Delivery Controller reported *"the host has a second gateway on the
live port (4001, loopback)"*. **4001 is IB Gateway's live port by
convention, and it is also just a port.** What is actually listening on
`dell-debian`'s 4001 is a **LiteLLM container** — the Product Owner's local
model gateway, and the path ADR-0004's commentary layer depends on. There
was **never** a stray IBKR live gateway on that host.

I took a port number as an identified service and recorded the inference
as established fact in **two Amendments**: AMD-0021 §2E ("a gateway
listening on a live port on `dell-debian` is a misconfiguration to be
removed"), and AMD-0022 §1(b)/§2C ("two of them only hold once the stray
live-port gateway on `dell-debian` is gone"), plus WO-0009's AC10a, which
states as history that the Product Owner "has removed the stray live-port
gateway and archived its container."

**Had that instruction been carried out, it would have destroyed the
Product Owner's local LLM gateway** — the service the whole PID-ARGUS-0003
commentary layer runs on. The Product Owner twice instructed removal on
the strength of my documents, and I twice repeated the claim without
asking what was actually bound to the port.

**And the principle was already written down, by me, in the same
paragraph.** AMD-0021 §2E says: *"The paper account is **asserted** on
connect, not **inferred** from the port."* I wrote that sentence about the
application and then did the exact opposite in my own diagnosis. This is
the same error as ADR-0003's FMP tier, AMD-0018's threshold, AMD-0019
§1(c)'s float32 and AMD-0021's own §1(a) — a plausible mechanism recorded
as a cause without a check. It is the fifth instance, and the first with
real blast radius.

**What stopped it was the stop-and-report clause**, not my care: the
Delivery Controller was told to identify the container first and to halt
on an ambiguous match, and it did exactly that instead of acting on an
authorised instruction. That clause earned its place.

### (b) WO-0015's signal (1) cannot be decisive, and my AC6 mutation was unfalsifiable
WO-0015 §2 calls signal (1) — *a current member whose membership start is
materially later than its first stored bar* — "the decisive one". **It is
nearly universally true and therefore decides nothing.** Companies list
years before they join the S&P 500, and the bootstrap pulls 10+ years for
every symbol in `membership`, so **essentially every index addition** has
bars predating its membership interval. Signal (1) alone flags the whole
universe.

No threshold repairs it, because a genuine addition and a rename have the
**same shape** under signal (1). What distinguishes a rename is the
**pairing**: another member's interval ending adjacent to this one's start
(signal 2), with price continuity across the boundary (signal 3).

The Implementer disclosed that AC6 mutation (b) only fails if signal (1)'s
materiality is also weakened. They are right, and the reason is my
fixture: AC6(b) points at `test_genuine_new_listing_is_not_a_candidate`,
whose IPO has its first bar and membership start on the **same date** — so
the IPO fails signal (1) too, and "accept signal (1) alone" still excludes
it correctly. **The mutation cannot fail against the fixture I
specified.** That is a vacuous non-vacuity requirement, which is a
particular embarrassment given CI-6.

Disclosing it rather than quietly weakening the materiality threshold to
make the mutation pass is exactly the conduct the chain is built for.

## 2. Change

### A. The stray-gateway claim is retracted
- **AMD-0021 §1(e) and §2E:** the sentence *"A gateway listening on a live
  port on `dell-debian` is a misconfiguration to be removed"* is
  **withdrawn as to fact.** `dell-debian` runs `ib-gateway` **paper-only on
  4002**; **4001 is a LiteLLM container and must not be touched.**
- **AMD-0022 §1(b), §2C and metadata:** the claims that a stray live-port
  gateway existed and that two barriers depended on its removal are
  **withdrawn.** All three barriers — loopback default (R3), the paper-port
  allowlist, the paper-account assertion — hold **as delivered**, with
  nothing to remove first.
- **Nothing is to be removed or archived on `dell-debian`.** Any earlier
  instruction to remove or archive a gateway container there is
  **cancelled**, including the archive-the-configuration-not-the-credentials
  procedure, which addressed a container that does not exist. The
  credential-hygiene *principle* (AMD-0022 §2D) stands on its own merits
  for any future archive.
- The remaining **real** action is unchanged and small: `IB_PORT` in
  `.env` must be **4002**. Note what the guard caught: the configured port
  was not an allowlisted paper port, so the application would have spoken
  IBKR protocol at a **model gateway**. The allowlist refused before a
  socket opened.

### B. AC10a identifies a service, not a port
`WO-0009` **AC10a** is reworded:
> **Precondition, checked at install:** no **IB Gateway or TWS process**
> on the host is serving a live-trading port. The check must identify the
> **listening process or container**, not merely that a port is bound
> (AMD-0026 §2A): IBKR's live ports are conventions, and on this host
> another service already occupies one. Recorded as pass/fail with **no
> port, host or container values filed** (CI-7). A fail is a **stop**. A
> non-IBKR service on an IBKR-numbered port is a **pass** — it is not a
> gateway and is none of this project's business.

`DESIGN.md` §10's topology bullet takes the same correction.

### C. WO-0015: signal (2) is necessary; signal (1) corroborates
`WO-0015` §2 is corrected:
> **Signal (2) is necessary**: a rename candidate requires **another
> symbol's membership interval ending within `--gap-days` of this one's
> start.** Signals (1) and (3) **corroborate** and rank; neither is
> sufficient alone (AMD-0026 §2C). Signal (1) — bars predating the
> membership interval — is true of **nearly every index addition**, because
> companies list years before they join, so treating it as decisive would
> flag the whole universe. A genuine addition and a rename are
> indistinguishable under signal (1); only the pairing separates them.

**AC3** gains: the report states the count of current members for which
signal (1) alone is true, **to demonstrate on real data why it is not
decisive** — the Architect's error, measured rather than asserted.

**AC6(b)** is replaced:
> (b) Treating **signal (1) as sufficient** — i.e. dropping the signal (2)
> requirement — makes `test_long_prior_history_addition_is_not_a_candidate`
> fail. That test's fixture is a **genuine index addition with ten years of
> prior bars and no adjacent interval ending**, which is the real
> false-positive class. The previous AC6(b) pointed at an IPO fixture whose
> first bar and membership start share a date, so it failed signal (1) too
> and the mutation could not fail: a vacuous non-vacuity requirement
> (AMD-0026 §1b). `test_genuine_new_listing_is_not_a_candidate` is retained
> as a separate case, not as the mutation target.

AC6 is **not** met under the old wording, and that is an Architect defect,
not a delivery one. **This is not a RED against WO-0015:** the Delivery
Controller applies §2C and the new AC6(b) as a mid-flight correction to an
open Work Order and re-audits, per AMD-0016 §2A.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0026)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
