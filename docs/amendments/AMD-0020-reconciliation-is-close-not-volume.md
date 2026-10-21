# AMD-0020 — Reconciliation compares closes; volume is recorded, not breached; pacing is now a design constraint

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.1, §3.3, §10; `docs/work-orders/WO-0009-nightly-orchestration.md` §2, §4, §6 (delta); ratifies WO-0008's AC1 spec defect |
| **Related ADR** | ADR-0006 |
| **Raised by** | Delivery Controller, 2026-10-21: WO-0008's live reconciliation gave 200 comparisons, 101 breaches, `breach_rate` 0.505 — **close 1 of 100** (max 2.09%, SKYD), **volume 100 of 100** (median ours/theirs 2.03×, p5–p95 1.35–2.78×) |
| **Affects Work Orders** | WO-0008 (accepted and merging; AC1 ratified as a spec defect), WO-0009 (delta — §2, §4, §6) |

## 1. Problem

### (a) The volume comparison compares two different quantities
Our volume is Polygon's consolidated daily figure; IBKR's is its own
`TRADES` daily volume from `reqHistoricalData`. The measurement says they
are not the same quantity and never will be:

- median ours/theirs **2.03×**, p5–p95 **1.35–2.78×**;
- **systematic across all 20 symbols**, not scattered;
- shares, not lots (SO 2026-10-13: 6,567,653 vs 3,879,970 — 1.69×);
- and Polygon and yfinance agree with each other **to 0.03%** on the same
  days, so the dispersion is not ours.

A 10% tolerance against that cannot be met by any correct
implementation. This is not a bar the delivery failed to clear; it is a
comparison I should not have specified. The Delivery Controller declined
to widen the tolerance because widening changes behaviour, which is
exactly right under ruling 7's second hard guard, and sent it up instead.

### (b) `breach_rate < 0.01` has no granularity at n=100
One hundred close comparisons and a strict `< 0.01` permits **zero**
breaches. A criterion that cannot express "one symbol needs a look"
is a binary gate wearing a rate's clothing. The same wording sits in
WO-0009 **AC6 as a phase-closure criterion**, so left alone it would have
blocked Phase 0 for the same reason.

### (c) The cause is a question of fact and is being assumed
Two mechanisms fit: `useRTH=True` scoping the bar to regular hours, or
IBKR excluding off-exchange/TRF prints. The 1.35–2.78× spread favours the
second, because off-exchange participation varies widely by stock while
regular-hours share does not. **Favours is not establishes.** WO-0008 §8
told the Implementer to measure any scale factor rather than guess it;
the same discipline applies to me.

## 2. Change

### A. The reconciliation gate is per-field, and close is the gate
`DESIGN.md` §3.3's reconciliation rule becomes:
> - Reconciliation: 20 members per night against IBKR daily bars, the
>   sample placing unresolved `jump_unexplained` flags first (AMD-0019
>   §3). **Every comparison is logged; the gate is per-field, never an
>   aggregate rate** (AMD-0020 §2A).
>   **Close** is the reconciliation: it passes when `max |pct_diff| ≤
>   0.5%` **and** at most one comparison exceeds `0.1%`, with every
>   exceedance named in the report. **Volume is recorded, not breached**:
>   `reconcile_log.breach` is false for volume rows and the ratio
>   `ours/theirs` is carried in `pct_diff` as stored. The volume gate is
>   on **drift**, not level — alert when the sample median ratio moves
>   more than 25% from the trailing 20-session median. A stable ≈2× is
>   information about two vendors; a jump to 5× means one of them broke.

`DESIGN.md` §3.1's IBKR row gains: *"daily `TRADES` volume is **not**
comparable with consolidated volume (measured ≈2× at WO-0008); closes
are. See §3.3."*

### B. The cause is measured, then recorded
Before WO-0009 closes, re-request the same 20 symbols for the same five
sessions with **`useRTH=False`** and record the ratio. If it closes toward
1, the difference is regular-hours scoping; if it stays near 2×, it is
off-exchange print exclusion. Either way the finding is written into
`DESIGN.md` §3.1 as a stated vendor fact, with the comparison that
establishes it, in `docs/evidence/WO-0009/ibkr-volume-basis.md`. Twenty
requests to settle a question that would otherwise be re-argued at every
future reconciliation.

### C. SKYD is a contract-identity check, not noise
The single close breach sits on one of the five renamed tickers
(AMD-0014), which is precisely where CI-2 lives, and a 2.09% close
difference on a renamed symbol has the shape of a **wrong contract
matched by symbol string**. Confirm IBKR's `conId`, `primaryExchange` and
long name against our SKYD and account for 2026-10-13 specifically. If it
is a different contract, that is a finding against the ticker mapping and
not a tolerance question. Filed in
`docs/evidence/WO-0009/skyd-contract.md`.

### D. IBKR request pacing is a design constraint, not an implementation detail
The measured nightly budget is **20 reconcile + 13×2 IV = 46 history
requests**. Two ceilings, and my own documents disagreed on which:
DESIGN §3.1 said ≈60 per 10 minutes (IBKR's documented limit for
historical data), WO-0008 §2 specified a conservative **50**, and 50 is
what the pacer implements. So the headroom is **four against the
implemented pacer** and about fourteen against the vendor limit — not the
bare four my acceptance comment stated. `qualifyContracts` is a contract
lookup and paces separately, so it does not consume the budget.

DESIGN §3.1's IBKR row is corrected to state both figures, because a
budget quoted against the wrong ceiling is how a safety margin gets spent
by accident.

`DESIGN.md` §10 gains:
> - IBKR history requests are pacing-bound: the nightly budget is 46,
>   against an implemented pacer ceiling of 50 per 10 minutes and a vendor
>   limit of ≈60 (AMD-0020 §2D). The reconciliation sample size and
>   the ETF list are therefore **coupled to the pacer**: increasing either
>   makes the nightly run sleep, and is an architectural decision rather
>   than a parameter change. WO-0009 must either stay inside the budget or
>   sleep deliberately and report the wall time it cost.

This is the most useful line in the WO-0008 report: a limit that is
invisible until something is added, found before anything was.

### E. Ratifications
Ratified with no action: WO-0008 spec-gaps **3** (a flag is resolved once
`reconcile_log` holds a `close` row for that symbol and date — correct,
and it stops a flag being re-sampled forever), **5** (clerical
`tests/fakes/__init__.py`), **7** (the weak disconnect test — tightened in
the §3 delta).

**Spec-gap 4 is an improvement on my text, not a gap.** A sliding-window
pacer is the right primitive for a per-10-minutes limit; the token bucket
the Work Order named permits ~55 in a window and was my error. The
substitution stands and §2D's budget assumes it.

**AC1 is ratified as a specification defect** against WO-0008, which is
accepted and merging. Its `spec-defects.md` records the measured figures;
nothing about WO-0008's code changes.

## 3. WO-0009 delta
1. **§2 `argus/data/reconcile.py` enters scope** — field treatment per
   §2A: close breaches as now, volume rows recorded with `breach = False`,
   and `ReconcileReport` carrying per-field pass/fail plus the volume
   median ratio. WO-0009 is the only Work Order that may touch this file
   (it owns the nightly gate and depends on WO-0008); WO-0013 does not
   touch it, so the two stay concurrent.
2. **§2 `argus/pipeline.py`** — the `ibkr_reconcile` step reads the
   **per-field** verdict, never `breach_rate`. It also reads the per-day
   `ingest_log` verdicts rather than any exit code (ratified WO-0004
   spec-gap 5: a quarantined day exits 0 by design).
3. **§4** — §2D's pacing budget is a stated constraint; the step reports
   the pacer's sleep time.
4. **§6 AC6 is replaced**: *"Across the three nights, every night's close
   comparison passes §2A's per-field gate — `max |pct_diff| ≤ 0.5%` and at
   most one comparison over 0.1%, each exceedance named — and the volume
   median ratio is reported per night with its drift against the trailing
   median. An aggregate `breach_rate` is not a criterion."*
5. **§6 new AC9** — `ibkr-volume-basis.md` (§2B) and `skyd-contract.md`
   (§2C) filed, each with the comparison that establishes its conclusion.
6. **§6 new AC10** — the nightly run on the host completes with
   `IB_PORT` set to a paper port, and a non-paper port makes the
   `ibkr_reconcile` step report a configuration error and the pipeline
   continue (the step is `required=False`), rather than failing the night.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0020)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
