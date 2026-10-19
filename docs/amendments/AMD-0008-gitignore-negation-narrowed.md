# AMD-0008 — Narrow the governance-doc negation; ignore `*.txt` at all depths

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/work-orders/WO-0010-secret-drop-hardening.md` §2, §6, §8 (supersedes the `.gitignore` negation text introduced by AMD-0007) |
| **Related ADR** | — |
| **Raised by** | Delivery Controller, 2026-10-19, reporting that AMD-0007's `!/docs/**` plus `!/*.md` re-included credential-shaped files under `docs/`, and that only gitleaks content scanning would then cover them |
| **Affects Work Orders** | WO-0010 (Implemented, audit in flight; folded into the single AMD-0007 delta dispatch — see §3) |

## 1. Problem
AMD-0007 required `!/docs/**` so no future governance document could be
silently ignored. The Delivery Controller correctly reported that this
re-includes anything under `docs/` that matched only a credential pattern:
`docs/x/.env`, `docs/secret.key`, `docs/id.pem`, `docs/credentials.json`
and so on. It also reported `docs/x/polygon.txt` as exposed — that one is a
separate defect in AMD-0005/WO-0010's own `/*.txt` rule, which is
root-scoped and never covered nested paths at all.

My AMD-0007 text traded one silent-ignore hazard for a different staging
exposure. The negation was wider than its purpose: every governance
document is Markdown, so the negation never needed to cover other
extensions.

## 2. Change — verified against real `git check-ignore`, not asserted

**WO-0010 §2**, `.gitignore`: replace the root-scoped `/*.txt` with
`*.txt` (all depths), and replace AMD-0007's negations with
extension-scoped ones:

```gitignore
*.txt                      # the shape of a dropped key file, at any depth
!/docs/**/*.md             # governance documents must never be silently ignored
!/*.md
```

Behaviour proven in a scratch repository with `git check-ignore`:

| Path | Result | Why it matters |
|---|---|---|
| `.env`, `.env.local`, `secret.key`, `id.pem` | ignored | baseline unchanged |
| `polygon.txt`, `docs/x/polygon.txt`, `deep/a/b/fmp.txt` | ignored | `*.txt` now covers every depth |
| `docs/x/.env`, `docs/secret.key`, `docs/id.pem`, `docs/credentials.json` | ignored | the five AMD-0007 exposures are closed |
| `sub/secret.md` | ignored | non-root Markdown outside `docs/` still caught |
| `docs/amendments/AMD-0011-secret-rotation.md`, `docs/work-orders/WO-0099-token-test.md`, `docs/runbook/OPERATIONS.md`, `docs/README.md` | **not** ignored | AC8 intact |
| `README.md`, `PID.md`, `.env.example` | **not** ignored | tracked files unaffected |

**WO-0010 §6** — **AC9** (new):
> - **AC9** — The exposure matrix above holds exactly (AMD-0008). Operator
>   check: run `git check-ignore -q <path>` for every row and file the path,
>   expected result and exit status. A single row behaving the other way is
>   a failure, not a note.

**WO-0010 §8** gains:
> **Accepted residual (AMD-0008).** Root-level Markdown whose *filename*
> looks credential-shaped — `secret.md`, `token.md`, `api-key.md` — remains
> stageable, because `!/*.md` must keep `README.md` and `PID.md` tracked.
> This is accepted deliberately: a filename pattern was never going to
> protect prose, a secret pasted into `notes.md` or `README.md` is the same
> risk, and gitleaks **content** scanning is the control for all of them.
> Blocking `secret.md` while allowing `notes.md` would be theatre. Do not
> add filename rules for Markdown.

## 3. Consequences and sequencing
- This **supersedes** AMD-0007's negation lines; it does not add a second
  dispatch. The Delivery Controller folds AMD-0007 and AMD-0008 into the
  **single** delta dispatch on `wo/0010-secret-drop-hardening`, then
  re-runs the mechanicals and re-audits the branch whole before the PR.
- The `/*.txt` → `*.txt` widening means a legitimate `.txt` anywhere in the
  repository now needs `git add -f` and a reviewer's attention. There is no
  such file today (the lockfile is `uv.lock`), and that is the intended
  trade.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0008)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
