# Argus-Breakout — Delivery Chain and Governance

This document is the authority for *how* work enters this repository. It
sits on top of the Forge delivery-control framework
(`https://github.com/maff0000/forge`) and does not replace any of Forge's
doctrine; where Forge says "PL", read "Delivery Controller". Every agent
prompt in `docs/governance/prompts/` restates the rules below verbatim, so
no agent is ever expected to remember them from a prior conversation.

## 1. The mandatory chain

```
Architecture decision
      ↓
PID / Amendment                     (Architect; committed to git)
      ↓
Git-tracked Work Order              (Architect approves; committed to git)
      ↓
Delivery Controller ("Rogue")       (bounded execution; owns git on the project)
      ↓
Implementer                         (Forge Engineer; works only inside the Work Order)
      ↓
Independent Audit                   (Forge Auditor; fresh dispatch, never a fork)
      ↓
Pull Request                        (evidence trail attached)
      ↓
Architect Acceptance                (fixed-format record on the PR + in git)
      ↓
Merge                               (Delivery Controller, only after acceptance)
      ↓
Closure                             (Work Order status → Closed; evidence filed)
```

No step may be skipped, reordered, or satisfied by a chat message.

## 2. Hard invariants

```
NO PID            → NO WORK ORDER.
NO WORK ORDER     → NO IMPLEMENTATION.
NO INDEPENDENT AUDIT + ARCHITECT ACCEPTANCE → NO MERGE.
NO GIT RECORD     → NOT DURABLE PROJECT AUTHORITY.
```

A fifth, derived from Forge: **the Implementer never commits.** The
Delivery Controller reviews every diff and commits it.

## 3. Roles

| Role | Who | Owns | Must not |
|---|---|---|---|
| **Human Product Owner** | Matt | Product intent, final product acceptance, account/credential custody | — |
| **Architect** | Claude, acting as Project Architect in the Human's Claude session | Architecture, ADRs, PIDs, Amendments, Work Order authoring and approval, sequencing, acceptance of every PR | Implement; commit application code; merge |
| **Delivery Controller ("Rogue")** | AI agent booted from `/srv/forge`, pointed at `PROJECT_ROOT=/srv/argus-breakout` | Bounded execution of *approved* Work Orders: worktree creation, Implementer dispatch, review and commit of diffs, test runs, Auditor dispatch, PR lifecycle, evidence filing, merge after acceptance | Write or alter PIDs/Amendments/Work Orders (except the clerical fields in §6.4); widen scope; merge without acceptance; dispatch without an approved Work Order |
| **Implementer** | Forge Engineer subagent dispatched by the Delivery Controller | Implementation strictly inside one Work Order, in its assigned worktree | Commit; invent architecture; touch files outside the Work Order's scope; "fix" unrelated issues; spawn agents |
| **Auditor** | Forge Auditor subagent, fresh dispatch | Independent challenge of the integrated commit against the PID + Work Order | Edit; inherit the Implementer's context; be given hints about the diff |

## 4. Documents and where they live

| Document | Path | Authored by | Status field |
|---|---|---|---|
| Master PID | `PID.md` (repo root — required by Forge's `ops/pl-startup-gate`) | Architect | — |
| Phase PIDs | `docs/pids/PID-ARGUS-NNNN-<slug>.md` | Architect | Draft / Approved / Superseded / Closed |
| Architecture Decision Records | `docs/architecture/adr/ADR-NNNN-<slug>.md` | Architect | Proposed / Accepted / Superseded |
| Design | `docs/architecture/DESIGN.md` | Architect | versioned in-file |
| Amendments | `docs/amendments/AMD-NNNN-<slug>.md` | Architect | Draft / Approved / Applied |
| Work Orders | `docs/work-orders/WO-NNNN-<slug>.md` | Architect (authors + approves); DC updates clerical fields only | see §6 |
| Evidence | `docs/evidence/WO-NNNN/` (audit verdict, auditor prompt verbatim, test output, acceptance record) | Delivery Controller files; Architect writes `acceptance.md` | — |
| Delivery log | `docs/evidence/DELIVERY-LOG.md` (append-only, one line per state change) | Delivery Controller | — |

Templates: `WORK-ORDER-TEMPLATE.md`, `AMENDMENT-TEMPLATE.md`,
`ACCEPTANCE-RECORD-TEMPLATE.md` in this directory. Forge's
`docs/PID-TEMPLATE.md` is the PID shape.

## 5. PIDs and Amendments

- A PID is written to leave little or no room for interpretation: exact
  module paths, function signatures where they matter, schemas, formulas
  with lookbacks, test names, acceptance criteria phrased so an Auditor can
  check them without asking what was meant.
- A PID is organised so the Delivery Controller can run **long continuous
  deliveries**: Work Orders are pre-sequenced with explicit dependencies
  and parallel groups, so Rogue proceeds from one to the next without
  returning to the Architect unless a *significant* issue cannot be
  overcome (see §8).
- Any change to an approved PID is an **Amendment**, never an in-place
  edit. An Amendment names the PID and sections it changes, the reason,
  and which open or future Work Orders it affects. Approved Amendments are
  applied to the PID text by the Architect in the same commit, with the
  Amendment ID cited in the changed section.

## 6. Work Orders

### 6.1 Required fields (a Work Order missing any of these is not approved)
1. `WO id`, title, **Status**
2. **Parent PID** (id + path) and the PID sections it implements
3. **Applicable Amendments** (ids, or "none")
4. **Base SHA** — the exact `main` commit the work starts from
5. **Scope** — files/modules to create or change, behaviour to deliver
6. **Exclusions** — what must not be touched or built, stated explicitly
7. **Dependencies** — Work Orders that must be Closed first; parallel group
8. **Required tests** — names, what they prove, and the rule that they run
   offline with no secrets
9. **Acceptance criteria** — numbered, observable, each mapped to a test or
   an operator check
10. **Evidence required** — what the Delivery Controller must file
11. **Approval** — Architect signature line (name, date, commit)

### 6.2 Status lifecycle
```
Draft → Approved → In Progress → Implemented → Audited (GREEN|RED)
      → PR Open → Accepted → Merged → Closed
                 ↘ Returned to Architect (any stage, with reason)
```
Only the Architect moves a Work Order to `Approved`. Only the Architect
moves it to `Accepted`. The Delivery Controller moves it through every
other state and records each transition in `DELIVERY-LOG.md`.

### 6.3 Base SHA discipline
The Work Order's Base SHA is the commit the branch is cut from. If `main`
has advanced past the Base SHA before work starts, the Delivery Controller
**may** rebase the Work Order onto the new `main` HEAD and record the new
SHA — **only if** `git diff --stat <old-base> <new-base> -- <every path in
the Work Order's scope>` is empty. If any in-scope path changed, the Work
Order is **Returned to Architect**.

### 6.4 Clerical fields the Delivery Controller may update
Status, Base SHA (under §6.3 only), branch name, PR number, evidence paths,
timestamps. Nothing else. Scope, exclusions, tests and acceptance criteria
are Architect-only.

## 7. Branching, PRs, acceptance, merge

- `main` is protected. Nothing is committed to `main` except by merge of an
  accepted PR.
- One branch per Work Order: `wo/NNNN-<slug>`, cut from the Base SHA.
- The Delivery Controller commits Implementer diffs to that branch after
  review (Forge: the Engineer never commits). Commit messages cite the
  Work Order id.
- Mechanical tests run on the integrated branch before audit. RED here
  goes back to the Implementer, not to the Auditor.
- The Auditor is dispatched **fresh** against the integrated commit SHA.
  Its dispatch prompt is filed **verbatim** in
  `docs/evidence/WO-NNNN/auditor-prompt.md` and its verdict in
  `docs/evidence/WO-NNNN/audit.md`, committed to the branch.
- The PR body links the Work Order, the Base SHA, the audited SHA, and the
  evidence directory.
- **Architect Acceptance** is two artefacts, both required:
  1. A PR comment (or review) by the Architect in exactly this form:
     `ARCHITECT ACCEPTANCE: WO-NNNN @ <audited-sha> — ACCEPTED` (or
     `— REJECTED: <reason>`).
  2. `docs/evidence/WO-NNNN/acceptance.md` (template in this directory),
     committed to the PR branch by the Architect, or by the Delivery
     Controller quoting the comment URL if the Architect cannot push.
- Merge is a **merge commit** (no squash, no rebase of pushed commits), by
  the Delivery Controller, only after both acceptance artefacts exist and
  the audited SHA is the branch head. Any commit after the audited SHA
  invalidates the audit and acceptance.
- After merge: Work Order → `Closed`, `DELIVERY-LOG.md` appended, branch
  deleted.

## 8. Stop conditions — return to the Architect

The Delivery Controller stops and returns the Work Order with a written
reason (filed as `docs/evidence/WO-NNNN/returned.md`, committed to the
branch) when:
- implementation exposes an **architectural ambiguity** or a contradiction
  between the Work Order, its PID, and the code;
- the Work Order cannot be completed without touching an excluded path;
- §6.3's rebase check fails;
- the Auditor returns RED twice on the same Work Order;
- a required external dependency (API, credential, host service) is
  unavailable and the Work Order's tests cannot be made to pass offline;
- anything would require a secret, hostname, or account identifier to be
  committed to this public repository.

Do not improvise past any of these. A paused delivery is cheap; an
improvised architecture is not.

## 9. Corrections and follow-up work

A defect found after merge, a missed criterion, or a refinement is a **new
Work Order** under the same PID (or an Amendment if the PID itself was
wrong). It goes through the full chain. Hotfixes do not exist.

## 10. Public repository rules

This repository is public until project completion. Never commit: `.env`
or any credential; API keys; IBKR account identifiers or usernames;
internal hostnames, IP addresses or ports; model-gateway URLs or alias
names; anything describing the Human's home network. Configuration is
supplied by environment variables documented as placeholders in
`.env.example`. The committed pre-commit hook runs `gitleaks` and blocks
commits when the scanner is missing; `--no-verify` is forbidden.

## 11. Durable truth

If it is not in this repository (or on its GitHub PRs), it did not happen.
Chat between the Human, the Architect and the Delivery Controller is a
control surface for pointing at the next Work Order; it carries no
authority of its own.
