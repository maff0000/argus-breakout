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
The Work Order's Base SHA is the commit the branch is cut from.

- A Work Order with no dependencies carries a literal 40-hex Base SHA at
  approval.
- A Work Order with dependencies carries a **by-reference** Base SHA at
  approval: `main at Closure of <WO-list>`. When every listed Work Order is
  Closed, the Delivery Controller resolves it to the 40-hex SHA of `main`
  at that moment, records it in the Work Order (clerical, §6.4), and cuts
  the branch there. The reference is exact: there is one such commit.

If `main` has advanced past a recorded Base SHA before work starts, the
Delivery Controller **may** rebase the Work Order onto the new `main` HEAD
and record the new SHA — **only if** `git diff --stat <old-base> <new-base>
-- <every path in the Work Order's scope>` is empty. If any in-scope path
changed, the Work Order is **Returned to Architect**.

### 6.4 Clerical fields the Delivery Controller may update
Status, Base SHA (under §6.3 only), branch name, PR number, evidence paths,
timestamps. Nothing else. Scope, exclusions, tests and acceptance criteria
are Architect-only.

A Work Order's §3 Exclusions constrain the **Implementer**. They never
restrict the Delivery Controller's own clerical and evidence writes, which
are governed by this section and §7: Status, Base SHA, Branch, PR, evidence
paths, timestamps, `docs/evidence/WO-NNNN/**` and
`docs/evidence/DELIVERY-LOG.md`. Where a Work Order's §3 says "no changes
under `docs/`", read it as "the Implementer makes no changes under
`docs/`". An Auditor finding that the diff touches DC-authored `docs/`
paths is **procedural and non-blocking** (AMD-0010).

## 7. Branching, PRs, acceptance, merge

- `main` is protected and has exactly **two** commit channels (AMD-0005):
  1. **Governance (Architect, direct).** PIDs, Amendments, ADRs, Work
     Orders, `docs/governance/**` (including the agent prompts and
     templates) and `docs/architecture/**` are committed to `main` by the
     **Architect** directly. These artefacts confer the authority the Work
     Order chain runs on, so they cannot themselves require a Work Order
     (`NO PID → NO WORK ORDER` would otherwise be a regress), and an
     Auditor audits implementation *against* them rather than auditing
     them. The Architect commits nothing else by this channel — never
     application code, tests, CI, packaging or repository plumbing.
  2. **Everything else (Delivery Controller, by accepted PR).** All
     application code, tests, configuration files, CI, repository plumbing
     and evidence reaches `main` only by merge of a PR carrying an
     independent audit and Architect Acceptance.
  A commit that mixes the two channels is a governance defect: split it.
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
- **Delegated Acceptance Mandate (AMD-0010).** For **WO-0002 … WO-0007**
  the Architect's acceptance is granted **in advance**, conditional on all
  nine conditions in `docs/amendments/AMD-0010-delegated-acceptance-mandate.md`
  §2B being true and recorded: GREEN audit with no non-procedural,
  non-residual findings; non-vacuity established; every acceptance
  criterion verified with filed command output including operator checks;
  scope fidelity; offline tests, ruff, gitleaks and CI all clean;
  commit identity clean; audited SHA is the branch head bar evidence and
  clerical commits; no Amendment, ambiguity or credential gap; access
  mechanism recorded. The Delivery Controller then files `acceptance.md`
  citing `AMD-0010 §2B` as the authority, merges and closes — no PR comment
  from the Architect is required. **If any condition fails the mandate does
  not apply**, and the Work Order waits for explicit two-artefact
  acceptance. A condition that is arguably met is not met.
  **Never pre-authorised:** WO-0008 (brokerage connection), WO-0009 (host
  service install and phase closure), any Work Order whose first audit was
  not GREEN, and any Work Order that triggered an Amendment.
- No rebase, merge or cherry-pick may be scripted to continue through a
  conflict; a conflict stops the operation for inspection. After any
  history operation on a Work Order branch, re-verify the Base SHA in-scope
  diff and the commit identities (`PID.md` §9) before proceeding (AMD-0009).
- Merge is a **merge commit** (no squash, no rebase of pushed commits), by
  the Delivery Controller, only after both acceptance artefacts exist and
  the audited SHA is the branch head. Any commit after the audited SHA
  invalidates the audit and acceptance.
- After merge: Work Order → `Closed`, `DELIVERY-LOG.md` appended, branch
  deleted.

### 7.1 Worktree access and cross-host provenance (AMD-0006)

The Delivery Controller chooses how it and its subagents reach the worktree
files. Whatever it chooses:

1. **Exclusive path per dispatch.** Each concurrent dispatch gets a
   worktree that no other dispatch can reach by any path. A shared mount
   point serving two dispatches is prohibited; use a distinct mount or a
   distinct per-Work-Order subdirectory.
2. **The prompt names the path actually used.** The absolute worktree path
   in a dispatch prompt must be the path that dispatch reads and writes.
   Never name a remote path and hand over a mounted one, or the stated
   boundary is not the enforced boundary.
3. **Verify write visibility before trusting any result** produced on a
   different host from where edits are written. Write a sentinel file
   through the edit path, read it back through the execution path, and
   confirm byte-identical content; repeat in reverse. Record the check.
4. **Reconcile before committing.** Compute `git status --porcelain` and
   `git diff --stat` **on the execution host** and confirm they match what
   the edit path shows. A mismatch is a stop condition, not something to
   resolve by re-copying.
5. **Record the access mechanism in the evidence.**
   `docs/evidence/WO-NNNN/tests.md` states where each command ran, where the
   files were written, and the §7.1(3) check result — the construction path
   of every number it reports.
6. **Prefer no mount.** Where a dispatch can run on the host that holds the
   files, do that instead; a network mount is a fallback, and its use is
   disclosed, not assumed.

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
wrong). It goes through the full chain. Hotfixes do not exist. This applies to repository plumbing and safety fixes as much as to
application defects: the Architect writes the Work Order, the chain
delivers it. The Architect does not fix code directly, however small the
change (AMD-0005).

### Standing rulings — do not return to the Architect for these (AMD-0010)

1. **Amendment-caused in-scope change.** If the §6.3 in-scope diff is
   non-empty **only** because of a commit an Amendment made, and that
   Amendment also updated the Work Order's own scope or criteria for the
   same path, the rebase is authorised: rebase, record the new Base SHA,
   log it, continue.
2. **Specification gap.** If a Work Order's stated deliverable cannot be
   produced without one choice the Work Order does not name, and that
   choice is conventional, zero-configuration and has **no behavioural,
   security or interface consequence** (a build backend is the canonical
   example), the Implementer may make it, must name it in its report, and
   the Delivery Controller records it in
   `docs/evidence/WO-NNNN/spec-gaps.md` for ratification at the next
   Architect review. Anything with behavioural, security, schema,
   dependency or interface consequence is a **stop**, unchanged.
3. **`DELIVERY-LOG.md` merge conflicts.** Keep every line from both sides,
   in timestamp order. Never drop a log line to resolve a conflict.
4. **Tooling failures are not governance events.** Where a tool is
   unavailable, use an equivalent route and note it in evidence.
5. **Accepted residuals.** `docs/governance/ACCEPTED-RESIDUALS.md` lists
   limitations already considered and accepted. Do not stop for one; do not
   ask for a ruling on one.
6. **Consequential test update (AMD-0011).** An Implementer may modify an
   existing test that asserts behaviour this Work Order's §2 **explicitly
   changes**, without that counting as a scope breach, provided all three
   hold: the edit is confined to that test's assertions (no new behaviour,
   no other test touched); coverage is not reduced — the replacement asserts
   the **new** behaviour at least as strongly as the old asserted the old;
   and the Implementer names the test and the reason in its report. The
   Delivery Controller records it in `docs/evidence/WO-NNNN/spec-gaps.md`,
   and an Auditor's `scope_fidelity: no` raised solely on such an edit is
   **procedural and non-blocking**. Touching a test whose behaviour the
   Work Order does **not** change remains a stop.
7. **Unachievable or inconsistent acceptance criterion (AMD-0016).** Where
   an acceptance criterion cannot be met **because of an external data fact
   rather than an implementation shortcoming**, and the honest response is
   to measure and record rather than change behaviour, the Delivery
   Controller may proceed. It must establish the cause with evidence (what
   the source does and does not provide, with counts); report the shortfall
   as a named figure beside the aggregate it affects, never bare; record it
   in `docs/evidence/WO-NNNN/spec-defects.md` with the criterion quoted and
   the achievable figure stated; and merge under the Work Order's
   pre-committed acceptance. **Three hard guards — any one means stop:**
   the criterion touches an entry in
   `docs/governance/CRITICAL-INVARIANTS.md`; the fix would change
   **behaviour** rather than reporting; or the shortfall would weaken a
   non-vacuity requirement or make a check incapable of failing. This is
   authority to proceed past a bad criterion of the Architect's, not to
   lower a bar — a criterion that is merely *hard* to meet is not
   unachievable.
8. **Pre-authorisation scope is §2, never a file list (AMD-0016 §2A).** A
   delta's bound is the Work Order's §2 Scope as verified by the Auditor's
   `scope_fidelity`, plus evidence and clerical paths. Any "the diff
   touches only …" file list in an earlier amendment is superseded.
10. **A criterion that depends on an external fact cites its measurement
    (AMD-0036 §2E).** Where an acceptance criterion turns on something
    outside this system's control — a vendor's publication time, a tier's
    entitlements, a field's presence, a market's calendar — the Work Order
    **names the evidence establishing that fact**, by file and figure, or
    the criterion is **not valid** and the Delivery Controller says so
    rather than attempting it. Searching
    `docs/evidence/**/spec-gaps.md` and `spec-defects.md` for the fact is
    part of writing the criterion. **The Architect has now twice written a
    criterion contradicted by evidence already filed and ratified**; this
    makes the omission visible before anyone waits on it, and a Delivery
    Controller challenging a criterion on this ground is doing its job.
9. **Count and version assertions (AMD-0019 §2F, widened AMD-0021 §2G).**
   A Work Order whose §2 adds or removes a table or column, or changes
   `SCHEMA_VERSION`, may update any test that fails **purely because a
   mandated column or table was added** — including a positional literal
   that must gain the new column's value, and the test module belonging to
   a source module named in §2 — as well as the assertions that *count*
   those things — the table-count, `DESIGN_TABLES`
   membership and schema-version assertions in `tests/test_schema.py` and
   `tests/test_cli.py` — without that counting as a scope breach, under
   ruling 6's three conditions. These assertions are arithmetic on the
   mandated change, not independent behaviour: a Work Order that adds a
   table and may not say so in the count test cannot leave the suite
   green. The Delivery Controller records the edit in `spec-gaps.md` and
   does **not** ask for a ruling. Any other change to those two files
   remains a stop.

## 10. Public repository rules

This repository is public until project completion. Never commit: `.env`
or any credential; API keys; IBKR account identifiers or usernames; IP
addresses or ports; hostnames other than the delivery host `dell-debian`
(the one permitted hostname, AMD-0001); model-gateway URLs or alias names;
anything describing the Human's home network. Configuration is
supplied by environment variables documented as placeholders in
`.env.example`. The committed pre-commit hook runs `gitleaks` and blocks
commits when the scanner is missing; `--no-verify` is forbidden.

## 11. Durable truth

If it is not in this repository (or on its GitHub PRs), it did not happen.
Chat between the Human, the Architect and the Delivery Controller is a
control surface for pointing at the next Work Order; it carries no
authority of its own.
