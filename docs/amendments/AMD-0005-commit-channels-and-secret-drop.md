# AMD-0005 — Commit channels to `main`; secret-drop hardening as WO-0010

| Field | Value |
|---|---|
| **Status** | Applied |
| **Amends** | `docs/governance/DELIVERY-CHAIN.md` §7 (first bullet), §9; `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md` ("What you must never do") |
| **Related ADR** | ADR-0001 |
| **Raised by** | Architect, prompted by the Delivery Controller's Base-SHA question and its report of a credential file dropped inside the repository working tree (2026-10-19) |
| **Affects Work Orders** | WO-0001 (Base SHA determination, §11 added); WO-0010 (new, Approved) |

## 1. Problem

**(a) Commit-channel contradiction.** §7's first bullet reads "Nothing is
committed to `main` except by merge of an accepted PR." The Architect has
nonetheless pushed nine governance commits (the baseline, PIDs, ADRs,
Amendments, Work Orders) directly to `main`. One of the two had to be
wrong, and it is the rule as written: the chain begins
*Architecture decision → PID/Amendment → Work Order*, so the artefacts that
confer authority necessarily precede any Work Order. Requiring a Work Order
to commit the first PID is an infinite regress, and an Auditor has nothing
to audit in a PID — it audits implementation *against* one. The rule was
written for application code and silently over-reached. Leaving it
unamended would make every governance commit a standing violation and
teach future sessions that the invariants are negotiable.

**(b) Secret drop inside the working tree.** A credential file
(`polygon.txt`) was placed in the repository root rather than `/tmp`. It
was never staged and has been shredded, and `gitleaks` would likely have
caught a key on commit — but the only thing standing between an untracked
secret in the working tree and a public commit was that nobody ran
`git add -A`. `.gitignore` covers `.env` and nothing else of that shape.

## 2. Change

**`docs/governance/DELIVERY-CHAIN.md` §7**, first bullet — current text:
> - `main` is protected. Nothing is committed to `main` except by merge of
>   an accepted PR.

Replacement:
> - `main` is protected and has exactly **two** commit channels:
>   1. **Governance (Architect, direct).** PIDs, Amendments, ADRs, Work
>      Orders, `docs/governance/**` (including the agent prompts and
>      templates) and `docs/architecture/**` are committed to `main` by the
>      **Architect** directly. These artefacts confer the authority the
>      Work Order chain runs on, so they cannot themselves require a Work
>      Order (`NO PID → NO WORK ORDER` would otherwise be a regress), and
>      an Auditor audits implementation *against* them rather than auditing
>      them. The Architect commits nothing else by this channel — never
>      application code, tests, CI, packaging or repository plumbing.
>   2. **Everything else (Delivery Controller, by accepted PR).** All
>      application code, tests, configuration files, CI, repository
>      plumbing and evidence reaches `main` only by merge of a PR that
>      carries an independent audit and Architect Acceptance.
>   A commit that mixes the two channels is a governance defect: split it.

**§9** gains a closing sentence:
> This applies to repository plumbing and safety fixes as much as to
> application defects: the Architect writes the Work Order, the chain
> delivers it. The Architect does not fix code directly, however small the
> change (AMD-0005).

**Delivery Controller prompt, "What you must never do"** gains:
> - Commit anything to `main` directly, or merge a PR that mixes governance
>   artefacts with code — the two commit channels in DELIVERY-CHAIN §7 are
>   separate (AMD-0005).

## 3. Consequences
- The nine existing governance commits are regularised by this amendment
  rather than retrospectively excused; they fall squarely in channel 1.
- The secret-drop hardening is **WO-0010**, not an Architect edit, which is
  this amendment's own rule applied to itself. Until WO-0010 merges, the
  interim control is operational: credential files are dropped in `/tmp`
  only, never inside the working tree.

## 4. Application
Applied in the commit introducing this file; changed sections tagged
`(AMD-0005)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
