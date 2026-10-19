# AMD-0006 — Worktree access path and evidence provenance across hosts

| Field | Value |
|---|---|
| **Status** | Approved (application in progress — see §4) |
| **Amends** | `docs/governance/DELIVERY-CHAIN.md` (new §7.1); `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md` (dispatch procedure, evidence); `docs/governance/prompts/AUDITOR-PROMPT.md` (evidence block) |
| **Related ADR** | ADR-0001; Forge `.claude/skills/forge/SKILL.md` "known sharp edge #1"; Forge `docs/EVIDENCE-DOCTRINE.md` (Provenance) |
| **Raised by** | Delivery Controller, 2026-10-19, disclosing that Implementers run commands on `dell-debian` over ssh while editing files through an sshfs mount at `/mnt/argus-wt` on the controller's machine — "my addition and not in the prompts" |
| **Affects Work Orders** | WO-0001, WO-0010 (both In Progress at the time of this amendment; the §7.1 checks apply before their diffs are committed or their test results treated as evidence) |

## 1. Problem
The Delivery Controller correctly disclosed an access mechanism that no
document describes. It is the Delivery Controller's own operational choice
and is not forbidden, but it sits underneath two load-bearing guarantees
and currently weakens both.

**(a) Isolation.** Every dispatch prompt names one absolute worktree path
and forbids the shared `PROJECT_ROOT`. If the Implementer actually writes
through a *different* path than the one named, the stated boundary is not
the enforced boundary, and the Implementer cannot verify its own location
against its instructions. Worse, `/mnt/argus-wt` is a **singular** name: if
two concurrent Implementers write through one mount point, that is exactly
Forge's known sharp edge #1 — concurrent dispatches colliding in a shared
path — which has already failed silently once in Forge's history.

**(b) Provenance.** Commands execute on `dell-debian`; edits arrive over
sshfs from another machine. sshfs caching, non-atomic writes and
disconnection mean the bytes `pytest` reads on the execution host are not
guaranteed to be the bytes the editor wrote. A test result whose
construction path is unverified is arithmetic, not evidence (Forge
`docs/EVIDENCE-DOCTRINE.md`, Provenance): "a measurement is only as
authoritative as the thing it measured."

No application code existed when this was raised, so exposure to date is
low. The rule is required before it matters, not after.

## 2. Change — new `DELIVERY-CHAIN.md` §7.1

> ### 7.1 Worktree access and cross-host provenance (AMD-0006)
>
> The Delivery Controller chooses how it and its subagents reach the
> worktree files. Whatever it chooses:
>
> 1. **Exclusive path per dispatch.** Each concurrent dispatch gets a
>    worktree that no other dispatch can reach by any path. A shared mount
>    point serving two dispatches is prohibited; use a distinct mount or a
>    distinct per-Work-Order subdirectory.
> 2. **The prompt names the path actually used.** The absolute worktree
>    path in a dispatch prompt must be the path that dispatch reads and
>    writes. Never name a remote path and hand over a mounted one, or the
>    stated boundary is not the enforced boundary.
> 3. **Verify write visibility before trusting any result** produced on a
>    different host from where edits are written. Write a sentinel file
>    through the edit path, read it back through the execution path, and
>    confirm byte-identical content; repeat in reverse. Record the check.
> 4. **Reconcile before committing.** Compute `git status --porcelain` and
>    `git diff --stat` **on the execution host** and confirm they match what
>    the edit path shows. A mismatch is a stop condition, not something to
>    resolve by re-copying.
> 5. **Record the access mechanism in the evidence.**
>    `docs/evidence/WO-NNNN/tests.md` states where each command ran, where
>    the files were written, and the §7.1(3) check result — the construction
>    path of every number it reports.
> 6. **Prefer no mount.** Where a dispatch can run on the host that holds
>    the files, do that instead; a network mount is a fallback, and its use
>    is disclosed, not assumed.

**Delivery Controller prompt** — the dispatch procedure gains step 3a
(exclusive path, prompt/path identity, sentinel check) and the evidence
list gains the access-mechanism line. **Auditor prompt** — the evidence
block gains `access_mechanism` and `write_visibility_verified`.

## 3. Consequences
- WO-0001 and WO-0010 are mid-flight: the §7.1 checks must be performed and
  recorded **before** either diff is committed and before any test, lint or
  scan result from those branches is treated as evidence. If the two
  Implementers shared one mount point, the Delivery Controller must
  establish that neither wrote outside its own worktree — by inspecting
  both diffs against their Work Orders' §2 scopes — and record that
  finding; if it cannot be established, both dispatches are discarded and
  re-run on exclusive paths. No partial credit: an isolation guarantee that
  cannot be shown to have held did not hold.
- Future phases may run the Delivery Controller on `dell-debian` itself,
  which removes the mount entirely. That is the preferred end state and is
  the obvious container-era answer too (ADR-0008).

## 4. Application
The §7.1 text and the prompt edits are applied by the Architect in the
commit introducing this file. The mid-flight obligations in §3 are the
Delivery Controller's to execute and record on the two open branches.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
