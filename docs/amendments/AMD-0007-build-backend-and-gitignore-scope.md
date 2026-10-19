# AMD-0007 — Build backend named; `.gitignore` must not swallow governance docs

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/work-orders/WO-0001-repo-skeleton.md` §2, §4; `docs/work-orders/WO-0010-secret-drop-hardening.md` §2, §6, §8 |
| **Related ADR** | ADR-0002, ADR-0007; AMD-0005, AMD-0006 |
| **Raised by** | Delivery Controller, 2026-10-19, in its post-implementation status: (a) WO-0001's Implementer added `hatchling` as the build backend, which the Work Order does not name; (b) WO-0010's `*secret*`/`*token*` patterns would silently ignore future governance documents whose filenames contain those words; (c) a path-only gitleaks rule cannot flag an empty key file |
| **Affects Work Orders** | WO-0001 (Implemented, audit in flight — §2/§4 clarified, no new work); WO-0010 (Implemented, audit in flight — new scope line and AC8 require a delta dispatch, see §3) |

## 1. Problem

**(a) Build backend unnamed (my gap, not the Implementer's).** WO-0001 §2
specifies "`pyproject.toml` create PEP 621 … `[project.scripts] argus=…`"
but names no PEP 517 build backend. An installable package with a console
script requires one, so the Implementer had to choose or stop. It chose
`hatchling` and the Delivery Controller flagged it rather than letting it
pass — the correct handling on both sides. The defect is in the Work
Order's specification, which should have named it.

**(b) `.gitignore` patterns would swallow governance documents.** WO-0010
§2 requires ignoring `*secret*` and `*token*`. Files already tracked are
unaffected, but a **new** document named, say,
`docs/amendments/AMD-0011-secret-rotation.md` would be silently ignored.
Governance documents reach `main` by direct Architect commit (AMD-0005
channel 1), so the failure mode is the Architect pushing a commit that
silently omits the very document conferring authority — with no PR review
to catch it. That is a worse outcome than the near-miss WO-0010 exists to
prevent.

**(c) Path-only gitleaks rule cannot see an empty file.** Correct, and
disclosed. `gitleaks` scans diff **content**; a zero-byte file offers none.
This bounds what WO-0010's rule can prove.

## 2. Change

**WO-0001 §2**, the `pyproject.toml` line, gains:
> `[build-system] requires = ["hatchling"]`, `build-backend = "hatchling.build"`
> — the backend is **hatchling** (AMD-0007): minimal, zero-config, PEP 517/621
> native, and what `uv init --package` generates, so it matches ADR-0007's
> toolchain. `[tool.hatch.build.targets.wheel] packages = ["argus"]`.

**WO-0001 §4** gains:
> The build backend is `hatchling` and is the only build-time dependency
> permitted beyond PID §8.1's list (AMD-0007).

**WO-0010 §2**, the `.gitignore` line, gains:
> After the credential patterns, re-include governance documents so no
> future document can be silently ignored (AMD-0007):
> ```
> !/docs/**
> !/*.md
> ```
> These negations must appear **after** the credential patterns and must
> not re-include `.env`. Verify with `git check-ignore -v` on each case in
> AC8.

**WO-0010 §6** gains:
> - **AC8** — Governance documents are never ignored, in either direction
>   (AMD-0007). `git check-ignore -q docs/amendments/AMD-0099-secret-test.md`
>   **fails** (not ignored); `git check-ignore -q docs/work-orders/WO-0099-token-test.md`
>   **fails**; `git check-ignore -q .env` **succeeds**;
>   `git check-ignore -q polygon.txt` **succeeds**. Operator check: all four
>   commands with exit statuses filed, using temporary non-existent paths
>   (`check-ignore` does not require the file to exist).

**WO-0010 §8** gains:
> `gitleaks` scans diff content, so the path-only rule cannot fire on a
> zero-byte key file (AMD-0007). This is accepted and bounds the rule's
> claim: **`.gitignore` is the load-bearing control** — it stops
> `git add -A` from staging the file at all — and the gitleaks rule is
> defence in depth for the force-added case, where a real key has content.
> AC5 therefore uses a fake key **with content** and remains the
> non-vacuity check for AC4. Do not weaken AC5 to chase the empty-file
> case, and do not claim the rule covers it.

## 3. Consequences and sequencing

- **WO-0001:** no new work. §2/§4 now authorise what was delivered. The
  running audit may report `hatchling` as outside §2 on the pre-amendment
  text; the Architect adjudicates that finding against this amendment
  rather than the Delivery Controller pre-empting it.
- **WO-0010:** the AC8 negations are **new work on the same Work Order**.
  Sequence: let the running audit complete against the pre-amendment
  scope; then dispatch a **fresh Implementer** for this delta on the same
  branch (`wo/0010-secret-drop-hardening`), re-run the mechanical tests,
  and **re-audit the branch as a whole** before opening the PR. One Work
  Order, two Implementer dispatches, one final audited SHA. Do not open
  the PR on the pre-amendment audit.
- Neither change affects any other Work Order's scope.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0007)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
