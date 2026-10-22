# Pre-registration — hypotheses recorded before the data was looked at

**Append-only.** An entry is **never revised after the fact.** If a
hypothesis changes, a new entry supersedes the old one and **both stay**,
with the reason — otherwise pre-registration is a draft of the conclusion.

Required by AMD-0028 §2B.1: a study's hypothesis, population, method and
**success bar** are written before it runs. A Work Order **cites** an entry
rather than restating it, and any departure from one is an Amendment.

---

## PR-0001 — Does anything in DESIGN §5 predict forward relative return?

| Field | Value |
|---|---|
| **Registered** | 2026-10-22 |
| **Registered by** | Claude (Architect) |
| **State of the data at registration** | 1,917,529 `bars` rows over ~615 symbols, ten years of history, schema 6/7. **No feature in DESIGN §5 has been computed. No feature-return relationship has been examined by anyone.** `argus/features/` does not exist. |
| **Study belongs to** | PID-ARGUS-0004 (the IC gate, AMD-0028 §2A) |
| **Supersedes** | — |

### Hypothesis
At least one of DESIGN §5's factor groups carries information about a
stock's **forward return relative to the equal-weight S&P 500 composite**,
out of sample and net of costs, at a swing-trading horizon.

Stated as the gate decides it, not as a hope: **the null is that none of
them do**, and the null is a complete and acceptable result that closes
PID-ARGUS-0004 honestly.

### Features
The §5 set as specified on this date — the ten factor groups and their
cross-sectional percentiles. **No feature may be added to the study after
registration** without a superseding entry. Features added to §5 later for
other reasons (display, context) are **not** in this study.

### Population
Members of the S&P 500 per point-in-time `membership`, on dates where
`composites` carries `coverage_flag` clear — coverage ≥ 95% (DESIGN §6.1,
CI-8). Dates below that threshold are **excluded and counted**, not
silently included.

### Horizons
5, 10 and 21 trading days. Forward return measured on `adj_close`,
**relative to EQ_SPX over the same window.**

### Method
As AMD-0028 §2B, with no deviation permitted without an Amendment:
purged and embargoed walk-forward cross-validation, with the embargo at
least the horizon length; trials counted and the result deflated for them;
costs modelled (commission, spread at the traded size, slippage); compared
against the stated baselines below; and coverage reported beside every
figure.

### Baselines it must beat
1. **Equal-weight buy-and-hold** of the point-in-time universe.
2. **A single trivial factor** — 21-day relative return — as the cheapest
   plausible competitor. A feature set that cannot beat one-line momentum
   has not earned its complexity.

### Success bar, stated before the data was seen
A factor group **passes** when, at one or more horizons:
- the **deflated** out-of-sample rank information coefficient is **≥ 0.03**
  with a t-statistic **≥ 2.0** across folds, and
- the sign is **stable** — the same direction in at least **4 of 5** folds,
  and
- the top-minus-bottom quintile spread **survives modelled costs**, and
- it beats **both** baselines above on the same folds and the same costs.

**Anything less is a fail**, including a result that is individually
significant but unstable in sign, and including a result that beats
buy-and-hold but not the one-line momentum baseline.

### What will be reported either way
The full table of every factor group at every horizon — passes and fails —
with the trial count, the deflation applied, the coverage per fold, and the
excluded-date count. **No group may be dropped from the report for
performing badly.** A study that reports only what worked is not evidence,
and the fails are the more useful half for the next hypothesis.
