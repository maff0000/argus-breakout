# AMD-0038 — AC10 was unsatisfiable by construction; the price basis is enumerated; a test that cannot fail is the finding

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0034` §2E.1 (AC10 replaced); `docs/architecture/DESIGN.md` §3.3, §5; `docs/governance/DELIVERY-CHAIN.md` §9 (adds standing ruling 12); `docs/governance/ACCEPTED-RESIDUALS.md`; `docs/work-orders/WO-0018-feature-layer.md` AC10, §5 |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-23: WO-0018's **second PRODUCT_RED** on AC10 — the first audit generated 33 mutants and 12 survived; the second generated **335** and **21 different ones** survived |
| **Affects Work Orders** | WO-0018 (AC10 replaced, second fix delta authorised) |

## 1. Problem

### (a) I wrote a criterion whose population is chosen by whoever evaluates it
AMD-0034 §2E.1: *"**Every constant and lag mutant must fail a test.** Run
the full constant/lag mutation set and report the **surviving count, which
must be 0**."*

There is no such thing as "the full constant/lag mutation set." The mutant
space over 87 features is combinatorially large, every Auditor generates
its own, and a larger set finds more survivors. First audit: 33 mutants,
12 survivors. Second: 335 mutants, 21 **different** survivors. A third
would find more again.

**So AC10 cannot be satisfied, by construction**, and the Delivery
Controller is right that each re-audit can find new survivors indefinitely.
This is the standard failure of "kill all mutants" as a target: the
criterion has no defined denominator, so it is not a criterion. It is an
instruction to keep going until someone stops.

The Delivery Controller's recommendation — fix a **defined** set the
Implementer also runs — is right, and §2A goes one step further: **bound it
by the specification, not by a tool.**

### (b) Two of the findings are not mutation score at all
**F5** — *"A required test cannot fail on the mutation it names."*
**F6** — *"the 'non-finite becomes NULL' rule has no test that could
fail."*

Those are **vacuous tests**, and CI-6 makes them findings regardless of any
mutation count. They stay findings under any criterion and are not
negotiable.

### (c) F7 is my specification gap, not a test gap
DESIGN §3.3 says *"§5 features use split-adjusted OHLCV; return-type
features (`ret*`, `mom12_1`, `rs_*`) use `adj_close`."* It names **three
families** and leaves the rest to inference — so for seven features the
basis is genuinely undetermined, and the Auditor is right that a test can
then only pin what the code happens to do.

**And the stakes are higher than a tidiness issue.** A dividend payer's
`adj_close` sits systematically **below** its `close` through history. Put
`sma200` on `adj_close` and the average is of prices the stock never
traded at, *and it sits lower* — so "close above its 200-day" fires more
readily for high-yield names. That is a **systematic selection bias toward
dividend payers** in a momentum screen, arriving silently through an
unstated default.

## 2. Change

### A. AC10 is bounded by DESIGN, not by a mutation tool
`WO-0018` **AC10** is replaced:
> **Every numeric constant, window length, lag, comparison operand and
> price basis that DESIGN §5 states has a test that fails when it is
> changed.** The target list is **enumerated from §5** — finite, derived
> from the specification, and filed as
> `docs/evidence/WO-0018/pinned-constants.md`: one row per specified value,
> naming the feature, the value, and the test that pins it. A row with no
> test is the finding.
>
> The mutation run **verifies that table** against a **committed mutant
> set** at `tests/mutants/features.yaml`, version-controlled so every
> re-audit runs the same set and the score is comparable between audits.
> **Survivors in that set must be 0.** An Auditor that constructs
> additional mutants reports survivors as **findings against the table** —
> either a specified value the table missed, which is a real gap, or an
> unspecified value, which is **§2B's question and not a test defect**.
>
> The set is seeded with the **union of both audits' survivors** — the
> first audit's 12 and this audit's 21 — so nothing already found is lost.

**Why bounded by the specification:** the purpose was never to kill mutants.
It is that *the tests pin the behaviour the design states*. DESIGN §5 is a
finite list of specified values, so that is the denominator — auditable,
completable, and immune to the next tool generating a bigger set.

### B. The price basis, enumerated — every §5 feature named
`DESIGN.md` §3.3's basis sentence is replaced and §5 carries the table:
> **The principle (AMD-0038 §2B):** a feature that measures a **return** —
> or is derived from returns — uses **`adj_close`**. A feature that measures
> a **price level, a range, or a position within price history** uses the
> **split-adjusted OHLCV** (`close`, `high`, `low`). Dividend adjustment
> changes the *level* of historical prices, so a moving average of
> `adj_close` is an average of prices that never traded — and it sits
> systematically lower for dividend payers, biasing every "above its
> average" test toward them.
>
> **`adj_close`:** `ret5 ret21 ret63 ret126 ret252`, `mom12_1`,
> `rs_spx`, `rs_sector`, `rs_ig`, `rs_spx_nh63`, `rs_rank`,
> `rs_rank_sector`, `rs_rank_ig`, `beta60`, `hv20`, `hv60`,
> `hv_rank252`, `clenow90`, `sharpe63`, `dd126`, `ulcer63`.
>
> **Split-adjusted OHLCV:** `sma20 sma50 sma150 sma200`, `slope20_5`,
> `slope50_10`, `ma_stack`, `trend_template`, `adx14`, `macd_hist`,
> `atr14`, `atr_pct`, `dist20_atr`, `bb_width`, `bb_width_pct252`,
> `squeeze`, `rsi14`, `rsi2`, `z20`, `consec_down`, `consec_up`,
> `pct_from_hi252`, `pct_from_lo252`, `donchian20_hi`, `donchian55_hi`,
> `base_len`, `base_depth`, `gap_pct`, `nr7`, every candle feature, every
> level feature, `rvol`, `updown_vol20`, `dist_days25`, `obv_slope20`,
> `cmf20`, `adv20_usd`.
>
> `clenow90` is on `adj_close`: an annualised log-price regression slope is
> a return measure. `slope20_5` and `slope50_10` are on OHLCV because they
> are ratios of moving averages of `close`, and must match the averages
> they are computed from.
>
> **Every feature's basis is pinned by a test** (AC10) using a fixture
> where `close` and `adj_close` **differ** — the Auditor found this
> unpinnable precisely because the fixtures made them equal.

### C. Standing ruling 12 — a criterion needs a defined denominator
`DELIVERY-CHAIN` §9:
> 12. **A criterion must name the population it is measured over
>     (AMD-0038 §2A).** "No surviving mutants", "no defects", "all cases
>     covered" are not criteria unless the set is **defined, enumerable
>     and committed** — otherwise whoever evaluates it chooses the
>     denominator and the criterion cannot be satisfied. Where the target
>     is a property of the implementation, bound it by the
>     **specification**, which is finite, and verify with a
>     **version-controlled** set so successive audits are comparable. A
>     Delivery Controller may **refuse** an unbounded criterion and say so;
>     that is not obstruction.

### D. The second fix delta is authorised
Covers **F1–F6** and **F7 under §2B**:
1. **F1** — pin the `_hi252` and `pct_from_*252` windows, `hv60`'s window
   and the `sma200` guard lag.
2. **F2** — `ma_stack` and `trend_template` clause **operands** pinned, not
   only their constants: `close>sma50` must fail when mutated to
   `close>sma20`.
3. **F3** — fixtures give the sector and industry-group composites
   **different** values, so `rs_sector` and `rs_ig` cannot be swapped
   undetected. **A fixture that makes two code paths indistinguishable is a
   fixture defect**, and this one hid a real swap.
4. **F4** — the equal-weight **mean** is pinned against a median.
5. **F5** — the unclassified-member gate is tested with **two or more**
   unclassified symbols, and the test must fail on the mutation it names
   (CI-6).
6. **F6** — a test for the non-finite→NULL rule that **can** fail:
   construct an input producing `inf`/`NaN` and assert NULL.
7. **F7** — every feature's basis pinned per §2B, on a fixture where
   `close ≠ adj_close`.

Plus `pinned-constants.md` and `tests/mutants/features.yaml`.

**WO-0018 remains outside the Delegated Acceptance Mandate** and needs
explicit two-artefact acceptance.

### E. Recorded, not fixed
**R12** — atomicity is per 60-date chunk; a failed run stays coherent and
re-runnable, verified by injected failures, but **a hard kill can leave a
hidden spill directory**. Accepted: the run is re-runnable and the
directory is inert. A later Work Order may add cleanup-on-start.

The level-cluster invalidation edge — a cluster containing a pivot formed
after a break is dropped whole — **follows AMD-0034 §2B's order as
written** and is confirmed, not a defect.

## 3. On the Auditor's work
335 mutants, 6,080 independent level comparisons with zero mismatches,
`macd_hist` recomputed in pure Python over 80 bars, batch-invariance proven
at four sizes, spill cleanup verified under **injected** failures, and the
float32/float64 split confirmed. That is substantially more than AC10 asked
for, and **both REDs were correct**. The criterion was the problem, not the
scrutiny.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0038)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-23
Commit:      the commit introducing this file
```
