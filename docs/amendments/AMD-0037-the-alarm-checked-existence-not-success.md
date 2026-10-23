# AMD-0037 — The alarm checked that a report existed, not that the night succeeded; 403 is pending, not failed; and every open item ruled

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0032` §2C (AC14's predicate); `AMD-0036` §2A (the pending trigger was the wrong signal); `docs/architecture/DESIGN.md` §3.1, §3.3, §10; `docs/governance/DELIVERY-CHAIN.md` §9 (adds standing ruling 11); `docs/work-orders/WO-0009-nightly-orchestration.md` §2, AC14, AC16; `docs/work-orders/WO-0024-pending-days-and-the-market-calendar.md` §2, §5, §6 |
| **Related ADR** | ADR-0003, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-23: the 23:30 firing failed on **HTTP 403**, and **`nightly-status` printed OK and exited 0** the next morning |
| **Affects Work Orders** | WO-0009 (AC14 corrected, AC16 extended), WO-0024 (403 handling added) |

## 1. Problem

### (a) The alarm I built yesterday to catch a failed night did not catch a failed night
WO-0009 §2, my wording:

> `nightly-status`: **exits 0 when a report JSON exists** in
> `ARGUS_OUT_DIR/nightly` for the last completed trading day.

**Exists.** Not *succeeded*. So the failed run wrote its report with
`ok=False`, the 09:30 check found a file with the right name, and the alarm
reported **OK**.

This is the same error as every other one this week — **checking the
presence of a thing instead of its content**: a rule that could not fire
counted as a pass (AMD-0017), a coverage field hard-coded to 0 read as a
measurement (AMD-0021), a blocklist admitted a status invented after it
(AMD-0021), an empty vendor response read as a holiday (AMD-0036). I wrote
AC14 *as the fix for exactly this class* and then specified it the same way.
**First opportunity, false assurance.**

### (b) The failure was 403, and my `pending` design keyed on the wrong signal
AMD-0036 triggers `pending` on `resultsCount == 0`. The vendor does not do
that: it returned **HTTP 403** at 18:30 New York time and **HTTP 200 with
12,618 rows** later. A 403 is not an empty response, so **AMD-0036's
`pending` never fires for the failure it was written hours after.**

Whether 403 means *plan entitlement* or *not yet published* is **not
established** and I am not guessing — the prober settles it. Either way the
handling is the same: on a **recent** date, a 403 from grouped-daily is
`pending`, retried, never `failed`.

The silent-holiday defect AMD-0036 fixes is still real, and its urgency is
**lower than I claimed**: it needs a 200-with-empty response, which happens
on a **genuine exchange holiday** — the next being weeks away. Tonight will
fail loudly, as last night did.

### (c) I escalated 7.9 GB without knowing the host's size
Measured: the nightly peaks at **0.45 GB** on a **62 GB** host. My AMD-0035
reasoning about the OOM killer taking the model server was argued from a
figure belonging to a *different* workload — WO-0018's feature run, which
is not in the nightly — on a host whose RAM I never asked for. The cap
stays because it is nearly free and because the feature step will join the
nightly at WO-0023, but the alarm I raised was disproportionate to the
measurement I had.

## 2. Change

### A. AC14 checks that the night SUCCEEDED
`WO-0009` §2 and **AC14**:
> `nightly-status` exits **0** only when, for the last trading day per the
> market calendar, **both** hold: a report JSON exists **and** its
> `ok` is **true**, **and** the day's `ingest_log` status is `ok` or
> `quarantined`. Anything else — missing, `ok=False`, `pending`, `failed`
> — exits **1** and prints which condition failed.
>
> **Non-vacuity (AC14, extended):** a report with `ok=False` present for
> the last trading day **must** make it exit 1. That mutation is mandatory,
> because the original wording passed it.

### B. 403 on a recent date is `pending`
`WO-0024` §2 — `argus/data/providers/polygon.py`:
> `grouped_daily` raises `DataNotYetAvailable` on **HTTP 403** for a date
> within the last 5 calendar days; `ingest_polygon_day` records that as
> **`pending`** (AMD-0037 §2B). A 403 on an older date remains an error:
> there it means entitlement, not timing.
>
> So `pending` has **two** triggers — a 403 on a recent date, and a
> 200-with-empty on a day the calendar says is trading. AMD-0036 §2A named
> only the second and the vendor uses the first.

`DESIGN.md` §3.1's Polygon row records the observed behaviour: **403 before
publication, 200 with ~12,600 rows after**, with the measured time to be
written in from WO-0024 AC4.

### C. The immediate fix is a retime, not code
Once the prober reports, **move the timer to after the measured
availability** and file the figure. That is a unit-file change inside
WO-0009 AC3c's existing wording, **no new scope and no new Work Order**,
and it makes the nightly work tomorrow. WO-0024's retry timer then removes
the need for the hour to be right at all — but the retime is available
today and costs nothing.

### D. Standing ruling 11 — a migration is gated on what it adds
`DELIVERY-CHAIN` §9:
> 11. **A migration is gated on the presence of what it adds, never on the
>     `SCHEMA_VERSION` literal (AMD-0037 §2D).** The version is a marker
>     for humans and must never be a control: migrations merging out of
>     order would otherwise skip silently, which is the trap caught at
>     `111c12a`. Every migration is idempotent and checks for its own
>     column or table. Where branches disagree on the literal, **keep
>     `main`'s and let the gates do the work** — the Delivery Controller
>     needs no ruling for this.

This confirms the Delivery Controller's own proposal, which was right.

### E. Every unit that runs `argus` carries the cap, plus `MemorySwapMax=0`
`WO-0009` **AC16** extends:
> The cap applies to **every** systemd unit that executes `argus` code —
> the nightly, the status check, and the retry unit when WO-0024 adds it.
> Uniform by default so a later unit cannot be forgotten.
>
> Add **`MemorySwapMax=0`**. Without it a process over the limit swaps
> instead of being killed, which on a shared host means disk thrashing that
> slows everything — including the model stack — rather than a clean,
> attributable death. Swapping defeats the entire purpose of the cap.
>
> `MemoryMax=4G` / `MemoryHigh=3G` **confirmed** against the measured
> 0.45 GB peak on a 62 GB host.

### F. The Work Order governs. An Implementer never needs an amendment
Ruling on the Delivery Controller's third open item:
> **The Work Order is the Implementer's only authority** and is
> self-contained by construction (`DELIVERY-CHAIN` §1). Where an
> Implementer cannot read an amendment, nothing is lost — if the Work
> Order's text does not settle the question, **the Work Order is
> underspecified and that is a stop**, reported to the Architect. An
> Implementer asking which amendment wording governs is a signal that I
> wrote the Work Order badly, not that it needs wider access.

### G. WO-0024 bases from `main` after WO-0009 merges
The Delivery Controller's recommendation is **adopted**, and §1(b) is why:
WO-0024's urgency rested on tonight silently losing a day, and tonight will
fail loudly instead. So finish WO-0009 — AC14's correction, AC16, the
measured AC3c, the retime — merge it, and start WO-0024 from `main`.
**Do not stack branches**; a stacked WO-0024 would merge a half-tested
pipeline change through two levels of review.

### H. The cap and the chunking must land together
Recorded for WO-0023: WO-0018's feature run measured **7.9 GB** before
chunking, and `MemoryMax=4G` would kill it. **The features step may not
join the nightly until WO-0018's chunked implementation is merged**, or the
cap turns a working pipeline into a nightly cgroup kill.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0037)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-23
Commit:      the commit introducing this file
```
