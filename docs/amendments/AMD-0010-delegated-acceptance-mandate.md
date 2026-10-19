# AMD-0010 — Delegated Acceptance Mandate; standing rulings for unguided delivery

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/governance/DELIVERY-CHAIN.md` §6.4, §7, §9; `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md`; `docs/governance/prompts/AUDITOR-PROMPT.md`; `docs/governance/WORK-ORDER-TEMPLATE.md` §3; adds `docs/governance/ACCEPTED-RESIDUALS.md` |
| **Related ADR** | ADR-0001 |
| **Raised by** | Human (Product Owner), 2026-10-19: "I need Rogue to move into a position where he can deliver unguided" |
| **Affects Work Orders** | WO-0002 … WO-0007 (pre-authorised); WO-0008, WO-0009 (explicitly **not** pre-authorised); WO-0001, WO-0010 (accepted directly, unaffected) |

## 1. Problem
Architect Acceptance is a synchronous handshake. With nine Work Orders
remaining, that is nine hard stops in which delivery waits on a human
relay — the opposite of what the Forge loop exists to provide. Separately,
the first two Work Orders generated seven returns to the Architect, of
which five were specification gaps or wording conflicts in my own
documents rather than genuine architectural questions. Each would recur
across the remaining Work Orders unless answered once, generally, in git.

The invariant `NO INDEPENDENT AUDIT + ARCHITECT ACCEPTANCE → NO MERGE`
holds. What changes is **when** the acceptance decision is made, not
whether one exists.

## 2. Change

### A. Work Order §3 exclusions bind the **Implementer**, not the Delivery Controller
`DELIVERY-CHAIN` §6.4 gains:
> A Work Order's §3 Exclusions constrain the **Implementer**. They never
> restrict the Delivery Controller's own clerical and evidence writes,
> which are governed by this section and §7: Status, Base SHA, Branch, PR,
> evidence paths, timestamps, `docs/evidence/WO-NNNN/**` and
> `docs/evidence/DELIVERY-LOG.md`. Where a Work Order's §3 says "no changes
> under `docs/`", read it as "the Implementer makes no changes under
> `docs/`". An Auditor finding that the diff touches DC-authored `docs/`
> paths is **procedural and non-blocking** (AMD-0010). The Work Order
> template's §3 heading carries this note so it is not re-litigated.

### B. Delegated Acceptance Mandate
`DELIVERY-CHAIN` §7 gains, after the Architect Acceptance bullets:
> **Delegated Acceptance Mandate (AMD-0010).** For the Work Orders named in
> the mandate below, the Architect's acceptance is granted **in advance**,
> conditional on every one of the following being true and recorded in
> `docs/evidence/WO-NNNN/`. The Delivery Controller verifies them, records
> `acceptance.md` from the template citing `AMD-0010 §2B` as the authority
> (no PR comment from the Architect is required), merges, and closes:
>
> 1. `AUDIT_VERDICT: GREEN` from a fresh Auditor dispatch against the
>    audited SHA, with **no findings** other than those that are
>    procedural per §A above or listed in
>    `docs/governance/ACCEPTED-RESIDUALS.md`.
> 2. `non_vacuity_established: yes`, or `n/a` with its reason stated.
> 3. **Every** acceptance criterion in the Work Order §6 marked verified,
>    each with its command and output filed — including every operator
>    check. No criterion skipped, assumed, or deferred.
> 4. `scope_fidelity: yes` for all Implementer-owned paths; no path in §3
>    Exclusions touched by the Implementer.
> 5. `offline_tests_pass: yes`; `uv run ruff check .` clean;
>    `gitleaks detect` clean; CI green on the PR; `mergeable_state: clean`.
> 6. `commit_identity_clean: yes` (PID §9, AMD-0009).
> 7. The audited SHA is the branch head, or differs from it only by
>    commits touching `docs/evidence/WO-NNNN/**` and Work Order clerical
>    fields.
> 8. No Amendment is required, no architectural ambiguity was raised, and
>    no acceptance criterion is blocked on a missing credential.
> 9. The access mechanism and, where applicable, the §7.1(3)
>    write-visibility check are recorded.
>
> **If any condition fails, the mandate does not apply** and the Work Order
> waits for explicit Architect Acceptance in the two-artefact form. The
> mandate is a pre-committed decision rule, not a licence to interpret: a
> condition that is arguably met is not met.

**Mandate scope.** Pre-authorised: **WO-0002, WO-0003, WO-0004, WO-0005,
WO-0006, WO-0007**.

**Explicitly excluded — these require Architect Acceptance in the
two-artefact form, no exceptions:**
- **WO-0008** — it connects to a brokerage account. Paper or not, the
  blast radius of a wrong connection is not a thing to self-certify.
- **WO-0009** — it installs a systemd service on the host and carries the
  PID-ARGUS-0001 phase-closure criteria.
- Any Work Order whose **first** audit is not GREEN, even if a later one
  is: the Architect adjudicates what the RED meant.
- Any Work Order that triggered an Amendment.
- Any new Phase PID or Work Order (authoring stays with the Architect).

**Architect retrospective review.** The Architect reviews every
mandate-merged Work Order at each parallel-group boundary (after P0-C,
after P0-D) and at phase closure, against the same checklist. A defect
found there becomes a new Work Order under §9 — it does not retroactively
un-merge anything.

**The trade, stated plainly.** This removes a second judgement between the
audit and the merge. What remains is a fresh independent audit, a
mechanical checklist, a retrospective review at each group boundary, and
the Product Owner's own acceptance at phase closure. What is lost is the
Architect noticing, in the moment, something the checklist does not name.
The Product Owner has accepted that trade for the pre-authorised Work
Orders; it is why the riskiest two are carved out.

### C. Standing rulings — do not return to the Architect for these
`DELIVERY-CHAIN` §9 gains:
> 1. **Amendment-caused in-scope change.** If the §6.3 in-scope diff is
>    non-empty **only** because of a commit that an Amendment made, and
>    that Amendment also updated the Work Order's own scope or criteria for
>    the same path, the rebase is authorised: rebase, record the new Base
>    SHA, log it, continue. No return.
> 2. **Specification gap.** If a Work Order's stated deliverable cannot be
>    produced without one choice the Work Order does not name, and that
>    choice is conventional, zero-configuration and has **no behavioural,
>    security or interface consequence** (a build backend is the canonical
>    example), the Implementer may make it, must name it in its report, and
>    the Delivery Controller records it in
>    `docs/evidence/WO-NNNN/spec-gaps.md` for ratification at the next
>    Architect review. Anything with behavioural, security, schema,
>    dependency or interface consequence is a **stop**, unchanged.
> 3. **`DELIVERY-LOG.md` merge conflicts.** Keep every line from both
>    sides, in timestamp order. Never drop a log line to resolve a
>    conflict.
> 4. **Tooling failures are not governance events.** Where a tool is
>    unavailable (e.g. `gh pr edit` failing on a GitHub Projects
>    deprecation), use an equivalent route (the REST API) and note it in
>    evidence. No return.
> 5. **Accepted residuals.** `docs/governance/ACCEPTED-RESIDUALS.md` lists
>    limitations already considered and accepted. Do not stop for one; do
>    not ask for a ruling on one.

### D. Prompt updates
The Delivery Controller prompt gains the mandate, its nine conditions, the
carve-outs and the five standing rulings. The Auditor prompt gains:
`docs/governance/ACCEPTED-RESIDUALS.md` is read before reporting; a
rediscovered residual is an observation, not a finding; a diff touching
DC-authored `docs/` paths is procedural, not a scope breach.

## 3. Consequences
- WO-0002 … WO-0007 can run end to end without the Architect in the loop,
  which is six of the nine remaining Work Orders.
- WO-0008 and WO-0009 stop for the Architect by design. The Delivery
  Controller should reach them having merged everything before.
- The Architect's workload moves from nine synchronous acceptances to two
  acceptances plus three retrospective reviews.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0010)`.

## 5. Approval
```
Approved by: Claude (Architect), on Product Owner instruction
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
