# AMD-0028 — Research protocol: nothing is built on an unvalidated signal, and the IC study is a gate

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `PID.md` §6 (PID-ARGUS-0004 deliverables and gating), §12 (quality); `docs/architecture/DESIGN.md` §9; `docs/ROADMAP.md` (adds §0, reorders exit work) |
| **Related ADR** | ADR-0005 |
| **Raised by** | Product Owner, 2026-10-21: *"don't let me lead. do what a world class hedge fund would do"* — on a proposal for an ML-driven adaptive stop-loss and trim policy |
| **Affects Work Orders** | None now. Binding on every PID-ARGUS-0004 and PID-ARGUS-0005 Work Order when authored |

## 1. Problem

### (a) Exit work is a second-order refinement of an edge that does not yet exist
Argus-Breakout has **no validated signal.** Not one feature in DESIGN §5
has been shown to carry information. The §7 playbook thresholds are
hand-specified by the Architect. The §6.5 rotation triggers are explicitly
*"initial values … PID-ARGUS-0004 calibrates them"*. Nothing in this system
has yet been shown to predict anything.

Optimising the exit of an unvalidated entry is unfalsifiable work: there is
no established edge for a better exit to preserve, so any improvement
measured is a measurement of noise. **The order is not negotiable:** does
the signal predict → does it survive costs → does it survive out of sample
→ sizing → exits. Exits are last because they are the least-leveraged, not
because they are uninteresting.

### (b) The binding constraint is breadth, and the Product Owner's own premise points the other way
The proposal's premise was that *few trades* favours expensive per-trade
cleverness. For compute, true. For **evidence**, it is backwards.

By the fundamental law of active management, information ratio scales
roughly as **IC × √breadth**. Ten concurrent positions on a swing horizon
is perhaps 100–200 trades a year, so realised results are dominated by
idiosyncratic variance for years regardless of how good the exits are. The
institutional response to low breadth is **to raise breadth**, not to
refine the exit of a thin bet stream.

And the lever is already paid for: **Polygon's grouped-daily call returns
every US ticker nightly and the pipeline discards all but the S&P 500**
(ROADMAP §A4). Universe expansion is a filter, a liquidity floor and
point-in-time membership — not a vendor purchase. It is a materially higher
return on engineering than adaptive exits, and it is available now.

### (c) Most of the available exit gain is two trivial changes
Practitioner consensus, and consistent with what this project can
measure: nearly all of the benefit attributed to clever exits is captured
by **volatility-scaling the stop** and **not trailing too early**. Both are
a few lines. A learned policy's marginal gain over a vol-scaled, staged
trail is small and hard to demonstrate — which is why reinforcement
learning for trade exits remains an active research area rather than a
settled one.

### (d) What the Product Owner is right about, and it changes the objective
Two points stand and were under-weighted by the Architect:

1. **Mechanised execution is a larger edge than exit optimisation.**
   Individual investors reliably underperform the assets they hold, and
   the dominant mechanisms — panic selling, chasing, and the disposition
   effect of selling winners early while holding losers — run to whole
   percentage points a year. That dwarfs any plausible gain from a stop
   formula. **A mediocre rule executed without fail beats an excellent rule
   applied inconsistently.** The edge is in the consistency, not the
   cleverness.
2. **Trim decisions are counterfactually evaluable**, and entries are not.
   A retail-scale position does not move the market, so for every
   historical trade the P&L under *every* trim schedule can be computed on
   **the same path**, with no simulation feedback loop. A trim fraction
   also yields a graded outcome where a binary exit yields one bit. That
   makes trimming a far better-posed learning problem than entry selection,
   and it is where any inference effort should go first.

### (e) And a machine has no fear, which is the price of (d)
Removing emotion removes the panic that occasionally saves a human. A
machine will hold into a catastrophe with perfect discipline if the rule
does not cover the case. **The fear must be engineered back in as explicit
limits that no model may override.**

## 2. Change

### A. The IC study is a gate, not a deliverable
`PID.md` §6, PID-ARGUS-0004: the **factor IC study and the lead-time study
are a gate on everything downstream.** Until a feature set is shown to
carry information out of sample, net of costs, **no threshold tuning, no
playbook weighting, no sizing work and no exit work may be authorised.** A
negative result is a **complete and acceptable outcome** of that phase —
"nothing here predicts, and here is the evidence" closes it honestly, and
is worth more than a tuned system nobody can trust.

### B. The research protocol, binding on PID-ARGUS-0004 and 0005
`DESIGN.md` §9 gains, and every Work Order in those phases inherits:

1. **Pre-registration.** The hypothesis, the feature set, the horizon and
   **the bar that counts as success** are written into the Work Order
   **before** the study runs. A result reinterpreted after the fact is not
   evidence. This project's own instrument for that is an acceptance
   criterion, so the discipline is free.
2. **Purged, embargoed walk-forward cross-validation.** Labels over a
   holding horizon overlap, so ordinary k-fold leaks. Purge the training
   set of observations whose label window intersects the test window, and
   embargo a gap after it.
3. **Count the trials.** The number of configurations tried is itself a
   parameter: the best of twenty backtests is not a discovery. Report the
   trial count and deflate the result for it; an undeflated Sharpe from a
   search is not reportable.
4. **Costs modelled, never assumed away.** Commission, spread at the
   traded size, and slippage. A result that does not survive costs did not
   happen.
5. **Compare against the dumbest adequate baseline.** Equal-weight
   buy-and-hold for selection; a plain Chandelier exit for exits; a fixed
   fraction for sizing. A model that cannot beat the trivial version is not
   a model.
6. **Coverage travels with every figure** (CI-8). The 46.4% delisted-member
   coverage of R5 is an input to every historical result and must be stated
   beside it, weighted, not merely mentioned.

### C. Priority order — recorded so it is not relitigated
1. Finish Phase 0: trustworthy data. **Eight Amendments in three days
   corrected silent data defects** — 46% delisted coverage, a validation
   rule that could not fire, a flag deleting rows, a dividend key
   collapsing a 13.50 special, a basis mismatch inflating adjustments.
   Every one of those would have produced a confident wrong backtest.
2. PID-ARGUS-0002: features and composites.
3. **The IC gate (§2A).** Stop here if it fails.
4. **Breadth** (§1b): universe expansion, on data already arriving.
5. Sizing and portfolio volatility targeting.
6. **Exits, last** — and in this order: vol-scaled stop, staged trailing,
   partial exits, *then* measure what prize remains, *then* consider a
   learned **trim** policy.

### D. Non-negotiables for any automated exit, whatever governs it
Recorded now for `argus-execution-agent` (ROADMAP §E):
- **The stop is monotonic.** It ratchets toward the position and never
  away. A widening stop makes the position-sizing guarantee fiction.
- **The trail multiplier is bounded**, and the bound is not a model output.
- **A hard per-position maximum loss no model may override.**
- **A portfolio drawdown level that halts trading**, and a kill switch that
  does not require the agent to be healthy to work (§1e).
- **Every automated exit records the rule and the inputs that fired it.**
  An exit nobody can explain cannot be told from a lucky one, and cannot be
  improved.

## 3. What this does to the Product Owner's proposal
It is **not rejected; it is sequenced, and its target is changed.** The
version that survives: a learned **trim** policy (not a stop policy),
evaluated counterfactually on historical paths, against a vol-scaled staged
trail, under §2B, after the IC gate, with §2D's bounds as hard
constraints — and with the honest prize measured first, so the effort is
sized to what is actually on the table.

The strongest part of the proposal is not the model at all. It is §1d(1):
**mechanising the decision removes the behavioural gap, and that gap is
larger than anything a formula will add.** That benefit arrives with a
plain vol-scaled staged trail, needs no inference, and is available as soon
as there is an edge to execute.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0028)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
