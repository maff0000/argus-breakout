# AMD-0009 — Commit identity on a public repository; no scripted rebase through a conflict

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `PID.md` §9, §11; `docs/governance/DELIVERY-CHAIN.md` §7; `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md`; `docs/governance/prompts/AUDITOR-PROMPT.md` |
| **Related ADR** | ADR-0001; AMD-0005 (commit channels) |
| **Raised by** | Delivery Controller, 2026-10-19: commits on the Work Order branches carried a personal name and address plus a third-party committer identity, inherited from the host's global git configuration, because `author.*`/`committer.*` sections there override `user.*`. Also disclosed: an automated rebase script continued through a merge conflict and committed on top of it |
| **Affects Work Orders** | WO-0001, WO-0010 (identity already corrected by the Delivery Controller before any push; this amendment makes the requirement durable and checkable) |

## 1. Problem

**(a) Identity leak.** `PID.md` §9 forbids committing personal details to
this public repository but says nothing about commit metadata, which is
published with every commit and cannot be corrected after a push without
rewriting history. The host's global git configuration set `author.*` and
`committer.*`, which take precedence over `user.name`/`user.email`, so
setting `user.*` repo-locally — the obvious move, and the one the Delivery
Controller made first — changed nothing. The commits were caught and the
identity corrected before any push, with trees unchanged.

**(b) Scripted rebase through a conflict.** An automated rebase continued
past a merge conflict and committed on top of it. It was aborted and redone
by hand, and no bad state reached either branch. A conflict is information;
a script that proceeds through one destroys it silently.

## 2. Change

**`PID.md` §9** gains:
> - **Commit metadata is published content.** Every commit in this
>   repository carries a project identity, never a personal one: the
>   Architect commits as `Claude (Architect) <noreply@anthropic.com>`, the
>   Delivery Controller as
>   `Rogue (Delivery Controller) <noreply@anthropic.com>`. Set this
>   **repo-locally for `author.*` and `committer.*`, not only `user.*`** —
>   a host's global configuration may define `author`/`committer` sections
>   that silently override `user.*` (AMD-0009). Verify before every push:
>   `git log --format='%an <%ae> | %cn <%ce>' <range> | sort -u` must list
>   only those two identities. A personal name or address reaching a public
>   commit cannot be undone by a later commit.

**`PID.md` §11** and **DELIVERY-CHAIN §7** gain:
> No rebase, merge or cherry-pick may be scripted to continue through a
> conflict. A conflict stops the operation for inspection; resolve it by
> hand, or abort and re-approach. After any history operation on a Work
> Order branch, re-verify the Base SHA in-scope diff and the commit
> identities before proceeding (AMD-0009).

**Delivery Controller prompt** — startup gains:
> 6. **Commit identity (AMD-0009).** Confirm
>    `git -C /srv/argus-breakout config --local author.name`,
>    `author.email`, `committer.name`, `committer.email` are the Delivery
>    Controller identity, and that `git log --format='%an <%ae> | %cn <%ce>'`
>    over any unpushed range lists nothing else. Setting `user.*` alone is
>    not sufficient. Never push a branch carrying a personal identity.

and "What you must never do" gains:
> - Script a rebase, merge or cherry-pick to continue through a conflict,
>   or push a commit whose author or committer is a personal identity
>   (AMD-0009).

**Auditor prompt** — the public-hygiene step gains:
> Also confirm commit identity: `git log --format='%an <%ae> | %cn <%ce>'
> <BASE SHA>..<AUDITED SHA> | sort -u` lists only the project identities in
> `PID.md` §9. Record as `commit_identity_clean` in the verdict block.

and the verdict block gains `commit_identity_clean: yes | no`.

## 3. Consequences
- One extra startup check and one extra audit line.
- The two open branches already comply; the amendment makes it durable
  rather than a thing one session happened to notice.
- Nothing in this amendment records the leaked identity itself — recording
  it here would be the leak.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0009)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
