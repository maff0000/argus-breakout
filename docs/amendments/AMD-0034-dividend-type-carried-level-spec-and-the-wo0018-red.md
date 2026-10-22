# AMD-0034 — `dividend_type` is carried with a cross-source veto; the level and dividend features get the spec they lacked; WO-0018's RED is upheld

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0031` §1(a) (overstatement corrected), §2A (type joins the discriminating set, with a veto); `docs/architecture/DESIGN.md` §3.2, §3.3, §5; `docs/governance/ACCEPTED-RESIDUALS.md`; `docs/work-orders/WO-0018-feature-layer.md` (delta); `docs/pids/PID-ARGUS-0002-screening-engine.md` §6 (renumber); adds `docs/work-orders/WO-0019-events-point-in-time-completion.md` |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-22: DVN's two records carry `dividend_type` **SC** and **CD** while TEL's are both **CD** — *"that contradicts AMD-0031's 'no payload field can separate them'"*; plus WO-0018's first-audit **PRODUCT_RED** and two specification gaps |
| **Affects Work Orders** | WO-0017 (accepted @ `6c7077d`, no change), WO-0018 (delta), WO-0019 (new) |

## 1. Problem

### (a) I generalised from one case again
AMD-0031 §1(a) says *"no function of those fields separates them, because
the fact that distinguishes them … exists in the issuer's announcement and
not in Polygon's record. A fourth field would not help; there is no fourth
field."*

**There is a fourth field, and it works.** The payloads:

| | amount | declaration | frequency | **dividend_type** | verdict |
|---|---|---|---|---|---|
| TEL 2024-11-22 | 0.65, 0.65 | identical | 4, 4 | **CD, CD** | duplicate |
| DVN 2024-09-13 | 0.22, 0.22 | identical | 4, 4 | **SC, CD** | genuine |
| PGR 2026-01-02 | 0.10, 13.50 | differ | 4, 1 | CD, CD | genuine |

Each of the three is separable by *something*: PGR by amount and frequency,
DVN by **type**, TEL by nothing. I had checked PGR's types (both CD),
concluded the field was useless, and wrote that conclusion as a general
claim about all cases. **The claim is true of TEL and false of DVN** — and
TEL is the only one of the three that genuinely needs cross-source.

The Delivery Controller's phrasing was better than mine: *"Two cases do not
make a rule."* Right — which is why §2A below uses the field as a fast path
that cross-source can **veto**, rather than as the authority.

### (b) SKYD is a third mechanism: one dividend counted under both tickers of a rename
The SKYD payload shows something neither TEL nor DVN does. Polygon carries
**one** record (0.05, under `PSKY`). yfinance stores **the same dividend
under both tickers** of the renamed company — `PSKY` and `SKYD` — so its
total for that ex-date is 0.10.

So the duplicate is **cross-ticker on one source**, not within-ticker. It
resolved correctly here only because `PSKY/SKYD` is in
`config/ticker_renames.yaml`, so `resolve_symbol` lands both rows in one
canonical group and the dedupe sees them. **An unmapped rename would
double-count every dividend of that company on the yfinance side** — and
AMD-0027 §1(c) established that undeclared renames cannot be detected from
stored data. This compounds R8 and is recorded as **R11**.

### (c) Two features were specified without the numbers needed to build them
`dist_res_atr`, `dist_sup_atr`, `res_touches`, `sup_touches` — AMD-0023
§2D gave the fractal window (5 bars either side) and the clustering
tolerance (0.5 ATR) and **omitted the lookback and any invalidation rule**.
`next_div_pct` and `div_yield_ttm` were put in the events group when the
amounts live in `dividends`, which `events` does not carry. Both are my
gaps, correctly reported as undelivered rather than guessed at.

### (d) The events point-in-time change is live but incomplete
Two consequences the Delivery Controller reported honestly:
- **Readers do not filter superseded rows.** `next_earnings` and
  `days_to_earnings` can now return a stale row after a date moves, because
  there are two rows where there used to be one.
- **`confirmed`, `time_of_day` and `source` are no longer updated** on an
  existing row, because the spec says extend `last_seen` only. So a date
  that later becomes *confirmed*, or gains a before/after-market marker,
  never records it — and `time_of_day` decides whether an earnings gap
  lands on day D or D+1, which is the whole basis of a PEAD study.

My spec made the row immutable when what it needed was **versioning**.

### (e) WO-0018's RED is correct
The Auditor recomputed all 186 golden literals in plain Python (0
disagreements), matched ~24,000 values over a larger panel, found 0
look-ahead mismatches across 87 features, and confirmed Wilder smoothing,
the NULL discipline and all four AC9 mutations. Then it rated **RED** on:
- **F2 (CI-6):** 12 of 33 constant and lag mutants **survive** — nine
  features whose constants nothing pins: the `slope*` lags, `clenow90`'s
  window, `dist20_atr`'s sign, `atr_pct`'s denominator,
  `dist_days25`'s threshold, `trend_template`'s 0.75, the `rs_rank`
  weights, the Keltner multiplier.
- **F4:** `macd_hist` emits an artificial **exact 0.0** on its first valid
  bar, which enters the percentile population for every new listing that
  day.

Both findings are **upheld**. F2 is the exact failure WO-0018 §5 was
written to prevent — a test that cannot detect a changed constant does not
pin it, and CI-6 is a critical invariant. F4 is the NULL-is-not-zero trap
§8 named, with seventy chances to occur and one taken. The implementation
is evidently strong; **the test suite under-pins nine constants**, and
that is what RED means here.

## 2. Change

### A. `dividend_type` is carried, and discriminates — subject to a cross-source veto
`DESIGN.md` §3.2 adds `dividend_type TEXT NULL` to `dividends` (from the
payload; NULL where a source does not supply it).

`DESIGN.md` §3.3's resolution rule becomes:
> Records differing in `cash_amount`, `declaration_date`, `frequency`
> **or `dividend_type`** are **distinct dividends** and are summed
> (AMD-0034 §2A). Records identical in **all four** are **ambiguous** and
> resolve against the other source's basis-normalised total as before,
> defaulting to collapse.
>
> **Cross-source veto.** Where a group is held distinct by
> `dividend_type` **alone** — identical in amount, declaration date and
> frequency — and a second source's normalised total equals the **single**
> amount rather than the sum, the second source **wins**: collapse, and
> warn naming both the type values and the totals. Two observations do not
> establish that a vendor's type taxonomy is reliable, so the field is a
> fast path and cross-source remains the authority.

The gain is real: DVN resolves **deterministically, with no second source
needed**, which matters because the no-second-source default collapses and
would have understated it.

### B. The level features get their missing numbers
`DESIGN.md` §5's Levels group:
> - **Lookback: 252 trading days.** A fractal pivot older than that is
>   stale and is dropped.
> - **Fractal pivot:** a bar whose high (low) is the extreme of the **5
>   bars either side** (AMD-0023 §2D).
> - **Clustering:** pivots within **0.5 × ATR14** of each other are one
>   level; its price is the mean of its members and `res_touches` /
>   `sup_touches` is the count of distinct pivots in it.
> - **Invalidation:** a level the close has since passed through by more
>   than **0.5 × ATR14** is **dropped**. A level price has cut clean
>   through is not resistance any more, and keeping it is how a level list
>   becomes noise.
> - `dist_res_atr` = (nearest surviving level **above** close − close)/ATR14;
>   `dist_sup_atr` = (close − nearest surviving level **below**)/ATR14.
>   **NULL** where none survives in the lookback — never 0 (AMD-0021 §2F).

### C. The dividend features read `dividends`, and must not see an unannounced dividend
`DESIGN.md` §5's Events group:
> - `next_div_pct` = the **resolved total** (per §3.3) of the earliest
>   `dividends` ex-date **after** the bar date, divided by close — counting
>   **only rows whose `declaration_date <= the bar date`** (AMD-0034 §2C).
>   A dividend is public information from its declaration, not before:
>   using an undeclared one is look-ahead of exactly the kind AMD-0024 §2D
>   forbids for news. **This is the second reason `declaration_date` is
>   carried**, and the stronger one.
> - `div_yield_ttm` = the sum of resolved totals with an ex-date in the
>   trailing 252 trading days, divided by close. NULL where the symbol has
>   no dividend history.
>
> Both read `dividends` and therefore depend on §3.3's resolution — so they
> are built **after WO-0017 merges**, in **WO-0020**, not in WO-0018.

### D. Feature coverage is per feature, not per date
`DESIGN.md` §5:
> Feature coverage is reported **per (date, feature)** — the ranked
> non-NULL population against `n_members` — and **not** collapsed to a
> per-date flag (AMD-0034 §2D). A date where `ret252` is 20% NULL from
> warm-up while `rsi14` is 99% covered is not uniformly poor, and a flag
> that is always on carries no information. `market_daily.coverage_flag`
> remains a per-date **breadth** measure (§6.1) and is a different thing.

### E. WO-0018 delta — the fix the Auditor's RED earns
1. **F2:** a boundary or golden test for each of the nine features, pinning
   the constant: the `slope*` lags, `clenow90`'s window, `dist20_atr`'s
   sign, `atr_pct`'s denominator, `dist_days25`'s threshold,
   `trend_template`'s 0.75, the `rs_rank` weights, the Keltner multiplier.
   **AC9 gains: all 33 constant and lag mutants must fail a test**, with
   the surviving count reported and required to be **0**.
2. **F4:** `macd_hist` is **NULL** until the signal line has 9 values. No
   artificial zero reaches a percentile.
3. **§2B's level specification** is now buildable: deliver
   `dist_res_atr`, `dist_sup_atr`, `res_touches`, `sup_touches`, with a
   test that a level cut through by more than 0.5 ATR is dropped.
4. `next_div_pct` and `div_yield_ttm` are **removed from WO-0018 §2** and
   moved to WO-0020 (§2C).

**WO-0018 is permanently outside the Delegated Acceptance Mandate** — its
first audit was not GREEN (AMD-0010) — so its merge needs explicit
two-artefact acceptance whatever the re-audit says.

### F. WO-0019 — the events point-in-time completion
`docs/work-orders/WO-0019-events-point-in-time-completion.md`: the key
becomes **`(symbol, date, type, first_seen)`**, a change to `confirmed`,
`time_of_day` or `source` **closes the current row and opens a new one**
(slowly-changing-dimension, type 2), and every reader goes through one
helper — `events_live_as_of(store, as_of)` — which returns, per
`(symbol, type)`, the row current on that date. No reader touches `events`
directly.

PID-ARGUS-0002's planned Work Orders renumber to **WO-0020 … WO-0023**.

### G. Ratified
- **WO-0018 F1 scope** (`argus/commands/features.py`, `tests/test_adjust.py`,
  `tests/test_schema.py`): ratified. `features.py` is the Typer app holder my
  §2 omitted — the same clerical gap as `diagnose.py` at WO-0015 — and the
  test edits are version literals under ruling 9. **On the merge conflict
  with WO-0017 over those literals: whoever merges second sets the literal
  to its own version**, which is the only resolution that leaves the suite
  green; keep both sides' other lines (ruling 3).
- **Event features 100% NULL** is **correct** point-in-time behaviour: the
  migration stamped existing rows today, so nothing was visible earlier.
  They will stay NULL-dominated for weeks, and **PR-0001's registered set
  includes them** — so the IC study will report them as uninformative for
  want of history, which is a result and not a reason to drop them
  (PR-0001's final clause).
- **rs_rank ~15% NULL**: 594 symbols have bars against 503 current members;
  the 91 extras are historical members still trading, whose features
  compute and correctly do not rank. Right behaviour.
- **AC6's figures**: 88 s full history over 1,565,316 rows, 24 s single
  date, **peak 7.9 GB**. The wall times are fine. The memory is a finding
  rather than a pass: `dell-debian` is a shared development host also
  running the Product Owner's model stack, and a nightly step peaking near
  8 GB can collide with it. **Recorded as a constraint on WO-0023** (the
  nightly step): peak RSS must be measured and reported, and if it exceeds
  4 GB the step processes symbols in chunks. Not WO-0018's problem — it has
  no nightly step by design.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0034)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
