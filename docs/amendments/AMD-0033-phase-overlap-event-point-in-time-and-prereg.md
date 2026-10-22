# AMD-0033 — Phases may overlap where they share no file; event history becomes point-in-time tonight; the IC study is pre-registered before any feature exists

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `PID.md` §6 (phase authoring), §7 (news non-goal, consequentially); `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/work-orders/WO-0009-nightly-orchestration.md` §2, §6; adds `docs/pids/PID-ARGUS-0002-screening-engine.md`, `docs/work-orders/WO-0018-feature-layer.md`, `docs/research/PRE-REGISTRATION.md` |
| **Related ADR** | ADR-0005 |
| **Raised by** | Product Owner, 2026-10-22: *"what can we actually do now? … in terms of engineering"*, approving both the phase overlap and the event point-in-time capture |
| **Affects Work Orders** | WO-0009 (§2 scope addition, **urgent — before tonight's run**), WO-0018 (new) |

## 1. Problem

### (a) Serial phases make the Architect the bottleneck at every boundary
`PID.md` §6 says later Phase PIDs are *"authored by the Architect when the
preceding phase closes, informed by its evidence."* Written to stop a phase
being designed in ignorance of the last one's findings — a good reason. But
applied literally it means **nothing in Phase 0002 can start until Phase 0
closes and I have written a PID**, so the project stops twice: once for the
closure, once for me.

And the evidence that matters is **already in hand**: coverage measured at
46.4% (R5), the dividend basis and resolution rules, the schema, the
survivorship and classification gaps, ten amendments' worth of data-layer
defects. Phase 0002 can be designed informed by that today.

The §5 feature layer shares **no file** with Phase 0's remaining work:
WO-0017 touches `adjust.py`, WO-0009 touches `pipeline.py`,
`reconcile.py`, `providers/ibkr.py`, `nightly_cmds.py` and `ops/`, and the
feature layer creates `argus/features/`. WO-0017 will shift some feature
*values* when it merges; it cannot affect whether the computation is
correct.

### (b) Event history is being lost from tonight, and it is not recoverable
`events` is filled from FMP's **forward calendar**, and a row is
overwritten when a company moves its reporting date. So the table holds
only the latest view, and any later study reads **corrected** dates as
though they had been known at the time — look-ahead bias that does not fail
loudly, it just makes results look better than they were.

**The nightly starts accumulating event history tonight.** There is no way
to reconstruct afterwards what the calendar said last Tuesday, so every run
without this costs a night permanently. AMD-0024 §2D already made the
point-in-time rule binding on any future news or events phase; this makes
it true of the data from the first night rather than from whenever someone
implements it.

### (c) Pre-registration is worth most before anything has been seen
AMD-0028 §2B.1 requires a study's hypothesis and success bar to be written
**before it runs**, in its Work Order. The IC study belongs to
PID-ARGUS-0004, whose Work Orders do not exist — so there is nowhere to put
it, and by the time there is, features will exist and someone will have
looked at them.

**The strongest possible version of that commitment can be made today**,
with 1.9M bars in the store and not one feature computed.

## 2. Change

### A. Phases may overlap where they share no file
`PID.md` §6:
> A Phase PID is authored by the Architect **when the evidence that should
> inform it is in hand**, which is normally at the preceding phase's
> closure but need not be (AMD-0033 §2A). A Work Order from a later phase
> may be dispatched **concurrently** with the preceding phase's remaining
> Work Orders provided **all** of the following hold, and the Architect
> records them in the Work Order:
> 1. it shares **no source file** with any open Work Order;
> 2. it depends on no table, column or interface that an open Work Order is
>    still changing;
> 3. the evidence that would have informed it is cited, by figure;
> 4. the Product Owner has approved the overlap.
>
> A Phase PID authored before closure is marked **Draft** and is finalised
> at closure with the closure evidence appended. **Phase closure criteria
> are unaffected** — overlap buys parallelism, never a shortcut through a
> gate, and the PID-ARGUS-0004 IC gate (AMD-0028 §2A) binds regardless of
> when the work was dispatched.

`PID-ARGUS-0002` is authored **Draft** under this, and **WO-0018** is its
first Work Order, dispatchable now.

### B. `events` records what the calendar said, and when — from tonight
`DESIGN.md` §3.2:
```
events         (symbol TEXT, date DATE, type TEXT {'earnings','exdiv'}, time_of_day TEXT NULL,
                source TEXT, confirmed BOOLEAN,
                first_seen DATE NOT NULL, last_seen DATE NOT NULL)
                -- first_seen/last_seen are the calendar-snapshot window in which this row was
                -- present (AMD-0033 §2B). A refresh that still sees the row extends last_seen;
                -- a row the calendar no longer carries keeps its last_seen frozen. A MOVED date
                -- is a different `date` and therefore a new row, so the key needs no change.
                -- Point-in-time: what the calendar said on day X is the row where
                -- first_seen <= X <= last_seen. Without this the table holds only the latest
                -- view and any study reads corrected dates as though known at the time.
```
`DESIGN.md` §3.3 gains:
> - Event rows are **never overwritten in place** for a changed date: a
>   moved earnings date creates a new row and leaves the old one with its
>   `last_seen` frozen (AMD-0033 §2B). A study for date X uses only rows
>   with `first_seen <= X <= last_seen` — the mandatory point-in-time rule
>   of AMD-0024 §2D, now enforceable from the data rather than promised.

**`WO-0009` §2 gains** (and this is the part that must land **before
tonight's run**):
```
argus/data/schema.py        modify  events: add `first_seen DATE NOT NULL`, `last_seen DATE NOT NULL`;
                                      key unchanged (symbol, date, type); bump SCHEMA_VERSION to 8
                                      (WO-0017 takes 7; the version is a monotonic marker, so a gap
                                      if these merge out of order is harmless)
argus/events/earnings.py    modify  on insert set first_seen = last_seen = the refresh date; on a row the
                                      calendar still carries, extend last_seen only — never rewrite date,
                                      time_of_day or first_seen. A row absent from the calendar is LEFT
                                      ALONE, its last_seen frozen. The migration sets both columns to the
                                      existing rows' ingest date where known, else the migration date, and
                                      says which it used
```
**New AC15** — a calendar refresh that moves an event's date leaves the old
row intact with a frozen `last_seen` and inserts a new row; two refreshes
on the same unchanged calendar extend `last_seen` without duplicating.
**Non-vacuity: overwriting in place must fail the first test.**

### C. The IC study is pre-registered now
`docs/research/PRE-REGISTRATION.md` is created as a **dated, append-only**
record. Entry **PR-0001** states the IC study's hypothesis, feature set,
horizons, population, method and **the bar that counts as success**, and
records that it was written when **no feature had been computed**. A later
Work Order **cites** PR-0001 rather than restating it, and any departure
from it is an Amendment, not an edit.

An entry is never revised after the fact. If a hypothesis changes, a new
entry supersedes the old one and both stay, with the reason — otherwise
pre-registration is just a draft of the conclusion.

## 3. What this does not buy
Overlap buys **parallelism only**. Phase 0 closure still needs WO-0009
AC3a–AC3d, AC14 and AC15; the IC gate still blocks everything downstream of
PID-ARGUS-0002; and the §5 feature values will shift when WO-0017 merges,
which changes nothing about whether the computation is right. WO-0018's
acceptance explicitly does **not** depend on the values being final.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0033)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
