# AMD-0032 — Three nights decomposed: a soak is not an acceptance criterion, and the alarm that was missing

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/work-orders/WO-0009-nightly-orchestration.md` §2, §6 (AC3 replaced by AC3a–AC3d; new AC14); `docs/architecture/DESIGN.md` §10; `PID.md` §13 |
| **Related ADR** | ADR-0008 |
| **Raised by** | Product Owner, 2026-10-22: *"Is there a way to complete this without waiting?"* |
| **Affects Work Orders** | WO-0009 (§2, §6) |

## 1. Problem

### (a) "Three consecutive nights" is a convention I never decomposed
AC3 asks for *"three consecutive unattended nightly runs"*. Asked what each
night proves, most of it does not need calendar time:

| What the nights are meant to prove | Needs real days? |
|---|---|
| the systemd timer fires unattended — no TTY, service-user permissions, `EnvironmentFile`, stdout to the journal | **No.** Retime the timer to fire in two minutes, three times. |
| day-over-day state: resumability, the `ingest_log` skip, `adj_version`, incremental materialise | **No.** `nightly --date D` is date-parameterised; run three consecutive *trading* dates in sequence. |
| Polygon's grouped-daily is actually published by 23:30 BST | **Yes — one firing.** Already scheduled for tonight. |
| a non-trading date behaves | **No.** Run `--date <a Saturday>` now. |
| environmental drift across days — log growth, disk, credential expiry, timer drift | **Yes**, and this is the only genuine loss. |

So one real firing is needed, not three, and the rest is testable in an
evening.

### (b) AC3 is ambiguous about the case it would actually have hit
The timer's next fire is **Thursday**. Three consecutive nights is
therefore **Thursday, Friday, Saturday** — and Saturday is **not a trading
day.** Night three would have exercised the holiday path, not a third
repetition, and **nothing specifies whether a non-trading-day run counts as
`ok=True`.** `ingest_polygon_day` is `required=True`; a non-trading date
yields `resultsCount == 0`, which WO-0004 logs as `status='holiday'`
rather than a failure, and `materialise` then no-ops at `rows=0`. That
*should* pass. "Should" is how a criterion gets discovered by accident
instead of specified.

### (c) The control that would actually protect the nightly does not exist
**If the nightly stops firing, nothing tells anyone.** Three nights
happening proves nothing about night four. A staleness alarm protects every
night, forever, and it is a few lines.

That is the real trade here: AC3 is a weak control bought with two days of
waiting, and a freshness check is a strong one bought with an hour of work.
A soak test is an **operations activity**, not an acceptance criterion — you
do not hold a release for three days of nothing happening, you release
behind a monitor and watch.

## 2. Change

### A. AC3 is replaced by four criteria, each naming what it proves
`WO-0009` §6:
> - **AC3a — the timer fires unattended.** With the timer temporarily
>   retimed, **three** firings complete without a terminal: no TTY, running
>   as the service user, `EnvironmentFile` loaded, stdout in the journal as
>   JSON (AC12). The timer is restored to 23:30 afterwards and
>   `systemctl list-timers` re-filed. Minutes, not days.
> - **AC3b — day-over-day state.** Three **consecutive trading dates** run
>   in sequence via `nightly --date D`, each a separate unattended
>   invocation, proving resumability, the `ingest_log` skip, `adj_version`
>   and incremental materialise. The second and third runs must **skip**
>   what the previous already stored (counts filed).
> - **AC3c — the configured hour works.** **One** firing at 23:30 BST
>   completes with the day's Polygon grouped-daily **present**, filed with
>   the row count. This is the one thing no compression replaces: it is the
>   only evidence that the chosen hour is late enough for the vendor.
> - **AC3d — a non-trading date behaves** (§2B): a run targeting a
>   non-trading date is `ok=True`, with the ingest step `holiday` and
>   materialise a no-op, filed.

### B. A non-trading date is a pass, specified rather than discovered
`DESIGN.md` §10 and WO-0009 §2:
> A `nightly` run targeting a **non-trading date** completes `ok=True`:
> `ingest_polygon_day` records `status='holiday'` on an empty
> grouped-daily response (WO-0004), `ingest_polygon_actions` and
> `materialise` no-op, and the optional steps behave as on any night. A
> holiday is **not** a failed required step. The weekend is the common
> case and must not raise an alarm.

### C. New AC14 — the staleness alarm, which is what replaces the waiting
`WO-0009` §2 gains:
```
argus/commands/nightly_cmds.py  modify  `nightly-status [--max-age-days N]`: exits 0 when a report JSON exists
                                          in ARGUS_OUT_DIR/nightly for the last completed TRADING day, 1 otherwise,
                                          printing the newest report's date and age. No network, no secrets
ops/argus-status.{service,timer}  create  fires mid-morning UK; no application logic (ADR-0008 constraint 5)
```
> **AC14** — `nightly-status` exits 0 after a good night and **1** when the
> newest report predates the last completed trading day (operator check:
> both outcomes, the second produced by moving the newest report aside and
> restoring it). The timer is installed and listed. **Non-vacuity: a
> deliberately stale `out/nightly/` must make it exit 1.**

This is strictly stronger than the criterion it replaces: three nights is
evidence about three nights, and this is a control over every night after.

### D. The soak continues as operations, and does not gate closure
`PID.md` §13: the first week of real nightly runs is reviewed
**retrospectively** by the Architect, at the same boundary as the
mandate-merged Work Orders. A defect found there becomes **a new Work
Order** under DELIVERY-CHAIN §9 — it does not reopen the phase. That is the
same bargain AMD-0010 already struck for merges, applied to operations.

## 3. What this gives up, stated plainly
**Multi-day environmental drift** — a log filling a disk, a credential
expiring, timer skew — is no longer proven before closure. Accepted for
three reasons: the nightly runs every night from now on, so the soak
happens either way and only *closure* is unblocked; the failure mode is a
missed report rather than lost data or money, since `bars_raw` is
append-only, resumable and never gated (CI-9); and **AC14 now detects
exactly that class of failure**, which AC3 never did.

Phase closure moves from roughly Sunday to tonight, once AC3c's firing is
filed.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0032)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
