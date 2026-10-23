# AMD-0036 — A trading day whose data is not published yet is not a holiday; and a criterion that depends on an external fact must cite its measurement

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `WO-0004` §4 (the no-calendar decision, reversed); `AMD-0032` §2B (a holiday is not always a holiday); `docs/architecture/DESIGN.md` §3.1, §3.3, §10; `docs/governance/DELIVERY-CHAIN.md` §9 (adds standing ruling 10); `docs/work-orders/WO-0009-nightly-orchestration.md` AC3c; adds `docs/work-orders/WO-0024-pending-days-and-the-market-calendar.md` |
| **Related ADR** | ADR-0003 |
| **Raised by** | Product Owner, 2026-10-23: the 23:30 firing failed, after a wait that produced nothing |
| **Affects Work Orders** | WO-0024 (new, **urgent**), WO-0009 (AC3c replaced) |

## 1. Problem

### (a) I had the measurement, ratified it, and then wrote a criterion that contradicted it
**WO-0004 `spec-gaps.md` item 3**, which I ratified in AMD-0020 §2E:

> **Grouped-daily for "today"** is not published when the range ends today;
> AC ranges end at the last trading day (used here).

Then **AMD-0032 §2A** made AC3c: *"One firing at 23:30 BST completes with
the day's Polygon grouped-daily **present** … it is the only evidence that
the chosen hour is late enough for the vendor."*

I had the fact **in writing, from a live run, and had formally ratified
it** — and then wrote an acceptance criterion requiring the opposite,
calling it *"the one thing no compression replaces."* It was the one thing
we already had data about. The Product Owner waited overnight for a result
that the evidence in this repository predicted.

### (b) The worse defect: a pending day reports success and the bars are lost
**WO-0004 §4, my decision:**

> Trading-day calendar: use `pandas_market_calendars`? **No** — no new
> dependency: treat weekdays as candidate days and let an empty
> grouped-daily response (`resultsCount == 0`) mark a holiday, logged
> `status='holiday'`.

So **"this is a holiday" and "this day's data is not published yet" are the
same observation** to this system. And **AMD-0032 §2B**, which I wrote
yesterday, blessed it:

> A `nightly` run targeting a non-trading date completes `ok=True` … A
> holiday is **not** a failed required step.

Put those together. A real trading day whose data is not ready yet:
1. returns `resultsCount == 0`;
2. is logged `status='holiday'`;
3. makes the night report **`ok=True`**;
4. is **skipped by the resume logic**, which skips `('ok','holiday','quarantined')`;
5. **never fires the staleness alarm**, because a report *was* written.

**The system can silently lose a trading day and report success.** Last
night it failed visibly, which was luck. The silent path is the live one,
and yesterday's amendment made it explicit.

### (c) The methodology failure underneath both
This is the sixth time this week a decision rested on an unverified or
unused fact — ADR-0003's FMP tier, AMD-0018's threshold, AMD-0019 §1(c)'s
float32, AMD-0021 §1(a)'s port, AMD-0031's "no fourth field", and now this.
The others I caught by measuring. **This one I caught by wasting the
Product Owner's night**, which is the expensive way.

The difference is that the previous five were facts I had not checked.
**This was a fact I had checked, recorded, and ratified** — and then did
not consult when writing the criterion that depended on it. No amount of
"measure first" discipline helps if the measurement is not read back.

## 2. Change

### A. `pending` — a status for a trading day that is not ready
`DESIGN.md` §3.3:
> `ingest_log.status` ∈ `{'ok','pending','quarantined','holiday','failed'}`
> (AMD-0036 §2A). **`'pending'` — the market calendar says this is a
> trading day and the vendor has not published it yet.** It is **not** a
> holiday, it is **not** `ok`, and the resume logic **does not skip it**:
> `backfill_polygon` and the nightly resume past
> `('ok','holiday','quarantined')` only. A `pending` day is unfinished
> work, and the staleness alarm (WO-0009 AC14) treats the last trading day
> as incomplete until it is `ok` or `quarantined`.
>
> `'holiday'` now means **the calendar says this is not a trading day** —
> never merely "the response was empty".

### B. The calendar comes from Polygon, so the no-dependency decision stands
WO-0004 §4's reasoning — no new dependency — was right; its
**implementation was wrong**, because it substituted an inference for the
fact. Polygon serves the fact directly, with the key we already have:

`DESIGN.md` §3.1 gains:
> | Polygon `GET /v1/marketstatus/upcoming` | exchange holidays and early
> closes, authoritative, same vendor as the bars | weekly refresh, cached
> in `market_calendar` | no new dependency (AMD-0036 §2B) |

A `market_calendar` table caches it. Where the calendar is unavailable the
day is **`pending`, never `holiday`** — the safe direction, because a
pending day is retried and a wrongly-marked holiday is lost.

### C. The nightly retries instead of relying on a well-chosen hour
`DESIGN.md` §10:
> The nightly runs at its scheduled time and, where the target day is
> **`pending`**, a retry timer re-attempts every 30 minutes until the day
> is `ok`/`quarantined` or a **06:00 UK cutoff** (AMD-0036 §2C). Picking an
> hour late enough for the vendor is guesswork that breaks whenever the
> vendor's timing moves; retrying until the data exists does not need the
> hour to be right.

### D. AC3c is replaced — and it is no longer a reason to wait
`WO-0009` **AC3c** becomes:
> **AC3c — the vendor's publication time is measured, not waited for.**
> Poll `GET /v1/marketstatus/now` and the grouped-daily endpoint for the
> current trading day **at intervals through one session**, and file the
> time the data first appears. Then set the schedule and the retry window
> from **that figure**. No overnight wait is required to establish it, and
> **the previous wording — requiring the data to be present at a guessed
> hour — was contradicted by WO-0004 spec-gap 3 before it was written**
> (AMD-0036 §1a).

### E. Standing ruling 10 — the rule that stops the class
`DELIVERY-CHAIN` §9:
> 10. **A criterion that depends on an external fact cites its measurement
>     (AMD-0036 §2E).** Where an acceptance criterion turns on something
>     outside this system's control — a vendor's publication time, a tier's
>     entitlements, a field's presence, a market's calendar — the Work
>     Order **names the evidence establishing that fact**, by file and
>     figure, or the criterion is **not valid** and the Delivery Controller
>     says so rather than attempting it.
>
>     Searching `docs/evidence/**/spec-gaps.md` and `spec-defects.md` for
>     the fact is part of writing the criterion. **The Architect has twice
>     now written a criterion contradicted by evidence already filed and
>     ratified**; this makes the omission visible before anyone waits on
>     it, and a Delivery Controller challenging a criterion on this ground
>     is doing its job, not obstructing.

## 3. WO-0024 — urgent
`docs/work-orders/WO-0024-pending-days-and-the-market-calendar.md` carries
§2A–§2C. **It precedes WO-0009's remaining criteria**, because until it
lands the nightly can lose a trading day and report success — and the
nightly is installed and firing.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0036)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-23
Commit:      the commit introducing this file
```
