# AMD-0025 — Two hypotheses to establish before features: same-date dividend collapse, and renames CI-2 cannot see

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/governance/CRITICAL-INVARIANTS.md` (CI-2 scope note, CI-4 scope note); `docs/ROADMAP.md` §C; adds `docs/work-orders/WO-0015-dividend-and-rename-diagnostics.md` |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-21, WO-0014 `spec-gaps.md` 2 (PGR 0.10 vs 13.60, FCX 0.075 vs 0.15 every quarter) — **labelled a hypothesis, not a cause**; and the Architect, from WO-0014's AC2 table, on `FB` appearing as a reassignment |
| **Affects Work Orders** | WO-0015 (new, diagnostic). Neither item blocks WO-0009 |

## 1. Problem

### (a) `dividends`' primary key may assert something false
The measured figures: Polygon holds **0.10** for PGR's 2026-01-02 ex-date
where yfinance holds **13.60** — roughly 5% of price on a single
adjustment — and **0.075 against 0.15 for FCX every quarter**, plus WRB,
CME, DVN, FANG and COP in the same shape. Polygon takes precedence, so
`adj_close` carries the smaller amount, and every return-type feature
crossing those dates inherits it.

The suspected mechanism: `dividends` is keyed `(symbol, date, source)`
(CI-4, AMD-0012), which **asserts one dividend per symbol per ex-date per
source.** A regular and a special dividend sharing an ex-date makes that
false, and an upsert on that key silently keeps one of them.

If that is the mechanism, **it is my schema defect, not an implementation
fault.** AMD-0012 split the old `adjustments` table in two precisely to
stop a same-date split and dividend from overwriting one another — and
left a narrower version of the same collapse inside the key.

**The mechanism is not established.** The Delivery Controller said so
explicitly rather than asserting a cause, which is the correct call and
the standard this project has had to learn three times: ADR-0003's FMP
tier assumption cost four Work Orders, and AMD-0018, AMD-0019 §1(c) and
AMD-0021 §2A were each a plausible mechanism written down as fact. **No
fix is designed from a hypothesis.**

### (b) CI-2 cannot see a rename nobody declared
`config/ticker_renames.yaml` holds five pairs — BK/BNY, FI/FISV, MMC/MRSH,
PSKY/SKYD, EQR/VMRK — all recent. It holds **no historical rename**, so
`FB`, `INFO`, `LB`, `TE`, `CAM`, `CSRA` and others appear in WO-0014's
"reassigned or a different entity" bucket.

**CI-2 verifies continuity for the pairs the yaml declares.** An *unmapped*
rename is therefore invisible to it: CI-1 catches a current member with no
membership row, and nothing catches a current member whose history is
**severed** at a rename. The invariant is sound; its reach is not.

The consequence if `FB`/`META` is unmapped: META's membership opens in
2022 while its bars run back to 2012 — because both free sources serve a
renamed company's whole history under the new ticker (AMD-0016 §2D) — so
Meta's pre-2022 history sits detached from the historical composite and
from its own 252-day features, for a company that was around 2% of the
index. That is the damage CI-2 exists to prevent, arriving through the
door CI-2 does not watch.

## 2. Change

### A. Both are diagnostics first. Nothing is fixed in this Amendment
**WO-0015** establishes the two mechanisms by measurement and **changes no
behaviour**: no schema change, no ingestion change, no membership change,
no `adj_close` recomputation. It files findings. The fix — if the findings
warrant one — is a separate Work Order designed from facts.

This is deliberate. Four of this week's amendments corrected a mechanism I
had assumed, and the cheapest of those corrections cost a re-audit. A
diagnostic Work Order is the inexpensive way to stop paying that.

### B. CI-4 gains a scope note
> **Scope note (AMD-0025 §1a):** the key `(symbol, date, source)` asserts
> **one dividend per symbol per ex-date per source**. If a source reports a
> regular and a special dividend on one ex-date, that assertion is false
> and the key collapses them. WO-0015 establishes whether it does. Until
> then, `adj_close` on an ex-date carrying a variable or special dividend
> is **suspect, not trusted**.

### C. CI-2 gains a scope note
> **Scope note (AMD-0025 §1b):** this invariant is verified **only for the
> pairs declared in `config/ticker_renames.yaml`.** An undeclared rename is
> not checked by it and will present as an index exit plus a separate
> addition — severing the company's price series exactly as this invariant
> forbids. Detection of undeclared renames is WO-0015; the map stays
> operator-reviewed, because asserting that two tickers are one company is
> a judgement, not an inference (the yaml's own rationale).

### D. `adj_close` is suspect on affected dates until WO-0015 reports
Recorded for PID-ARGUS-0002, which computes the return-type features:
until WO-0015 reports, the ex-dates named in WO-0014's AC4 list (PGR, FCX,
WRB, CME, DVN, FANG, COP, EXE, F, HP, HST) are **known-suspect inputs**,
and any feature study crossing them says so. This is a CI-8-shaped
obligation: the limitation travels with the number.

## 3. Why neither blocks WO-0009
WO-0009 installs and runs the nightly pipeline. Neither item changes what
it orchestrates, and both concern inputs to a feature layer that does not
exist yet. WO-0015 may run **concurrently with WO-0009** — it shares no
file, writes no code, and is read-only against a copy of the store.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0025)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
