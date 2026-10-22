# AMD-0030 — Reconciliation is a monitor, not a gate; the corroboration clause is withdrawn and the yfinance work is cancelled

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0029` §2E (withdrawn); `AMD-0020` §2A (close gate → monitor); `docs/architecture/DESIGN.md` §3.3; `docs/work-orders/WO-0009-nightly-orchestration.md` AC6 |
| **Related ADR** | ADR-0003, ADR-0006 |
| **Raised by** | Delivery Controller, 2026-10-22: *"the nightly only stores Polygon bars. No second vendor's close exists for the night to corroborate an exceedance."* |
| **Affects Work Orders** | WO-0009 (AC6 replaced; one in-flight Implementer task **cancelled**) |

## 1. Problem

### (a) I wrote a criterion requiring data the nightly does not hold
AMD-0029 §2E permits one close exceedance per night **where a second
independent source corroborates our value**. The nightly stores Polygon
bars only. There is no second vendor's close for that night, so the
criterion cannot be satisfied on the night it applies to. Seventeen hours
old and unsatisfiable.

### (b) The fix in flight would break a constraint I wrote two days ago
An on-demand yfinance check for the exceedance symbol-date would put an
**unofficial source on the nightly path** — against `DESIGN.md` §3.1,
which scopes the bootstrap source to *"once"*, and against `ROADMAP.md` §D,
where I wrote that yfinance is *"accepted here **only** as a one-off
historical bootstrap, **never on the nightly path**"*. The Delivery
Controller's design was careful — conditional, fail-closed, audited — and
it was being built to satisfy a **criterion**, not to make the pipeline
work.

### (c) The real error: I made a monitor into a gate
`argus/pipeline.py` already has `ibkr_reconcile` as **`required=False`** —
the night continues whatever reconciliation finds. So nothing at runtime
ever failed on it. **Only my AC6 gated**, as a phase-closure criterion.

And AMD-0020 already got this right for volume: *"the volume gate is on
**drift**, not level"* — a monitor that trends rather than a gate that
stops. I moved volume and **left close behind as a pass/fail**, then spent
two amendments patching the gate I should not have written. Reconciliation
compares us against a third party on a 20-symbol sample; it is a
data-quality **instrument**. The thing that must stop the pipeline when
bars are wrong is `validate.py`, and it does.

## 2. Change

### A. AC6 — reconciliation reports and is adjudicated; it does not gate
`WO-0009` **AC6** is replaced:
> Across the three nights, **every** close comparison and its `pct_diff`
> is written to `reconcile_log` and the per-field summary is filed. **Each
> exceedance over 0.5% is reported and adjudicated in the evidence** with
> a stated verdict, by the template the Delivery Controller already used
> for SKYD: a second source's close where the store already holds one, the
> IBKR contract identity (`conId`, `primaryExchange`, long name), and a
> conclusion. The volume median ratio is reported per night with its drift
> against the trailing median (AMD-0020 §2A).
>
> **The night does not fail on reconciliation**, and no count of
> exceedances fails this criterion. What fails it is an exceedance left
> **unreported or unadjudicated**. Reconciliation is a monitor: its value
> is the trend, and a *sustained* pattern of disagreement is the alarm, not
> a single instance.

### B. AMD-0029 §2E is withdrawn
The corroboration clause — one exceedance permitted where a second vendor
confirms within 0.1% — is **withdrawn**, replaced by §2A's reporting and
adjudication. The Delivery Controller's **narrow reading of it was
correct**: the 0.5% bound held, only a single corroborated exceedance was
relaxed, and two still failed. That reading was right and is now moot,
because the clause it read is gone.

### C. The yfinance corroboration work is cancelled
**Stop the second Implementer.** No vendor call is added to the nightly for
this. **yfinance remains bootstrap-only** (DESIGN §3.1, ROADMAP §D) with no
exception, and the nightly's source set is unchanged.

Where corroboration is genuinely wanted it is **already free, with a
one-day lag**: the store holds yfinance history for every symbol, and the
following night's bars give the surrounding context. An exceedance
adjudicated tomorrow costs nothing and adds no dependency. Waiting is the
cheaper instrument than fetching.

### D. DESIGN §3.3
The reconciliation rule's gate wording is replaced by §2A's: every
comparison logged, exceedances reported and adjudicated, volume on drift,
and the night never failed by it.

## 3. Ratified, with one note
**AC10a's execution was exemplary** and worth recording as the pattern:
run as root, the conventional live port numbers passed **on stdin** rather
than as arguments — keeping them out of the process list and the shell
history — and **only the verdict kept**. That is CI-7 handled better than
the criterion asked for.

Also ratified: WO-0016 merged at `2a59157` with its acceptance record
filed; the `/root` `.env` copy shredded; the install running from a
separate checkout of `c671aa5` with the store created at its production
path and the production checkout untouched, exactly as AMD-0029 §2D
requires.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0030)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
