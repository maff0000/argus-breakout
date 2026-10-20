# AMD-0018 — `bars_raw` is never gated by a quality judgement; the 25%-jump rule repaired on three counts

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/governance/CRITICAL-INVARIANTS.md` (adds CI-9); `docs/work-orders/WO-0004-polygon-provider.md` §2, §3, §4, §5, §6 (delta on an open Work Order); `docs/work-orders/WO-0012-store-identity-and-vacuous-validation.md` (narrowed) |
| **Related ADR** | ADR-0003, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-20: the 521-day live backfill on `16a65bf` rejected **268 of 520** weekdays, every one for `N close(s) moved >25% without a split`, in long consecutive runs named by the same few tickers (BE 49 days, STI 45, SMCI 26, NKTR 24, OGN 21, NWL 18, FMC 18, CHTR 17, AIV 17, CNC 16) |
| **Affects Work Orders** | WO-0004 (delta, pre-merge), WO-0012 (narrowed), WO-0007 (two obligations recorded) |

## 1. Problem

The Delivery Controller's diagnosis is correct as far as it goes and the
measurement is the right kind: consecutive runs named by the same tickers
is the signature of a feedback loop, not of bad vendor data. But there are
**three** defects here, not one, and the third is architectural. All three
are mine, and two of them are in prose I wrote.

### D1 — The jump rule is evaluated over the wrong population
`validate_day` computes every other rule over `member_bars` — the day's
bars filtered to `members_on(d)`. The jump rule alone is computed over
`bars`, the whole fetched frame:

```python
member_bars = bars.filter(pl.col("symbol").is_in(list(member_set)))   # coverage, zero-volume
...
jumps = bars.select("symbol", ...)                                     # the jump rule
```

`bars` is grouped-daily filtered to `symbols` ∪ ETFs — and **AMD-0016 §2C
widened `symbols` to every symbol appearing in `membership`**, all 628 of
them, to fix the classification seam. So my own amendment widened this
rule's population from ~500 current members to every company that has ever
been in the index, plus the configured ETFs, on every date.

That is why **STI** is in the list with 45 rejected days. SunTrust left the
index in December 2019 when it merged into Truist; it cannot have 2024–2026
bars. The ticker was reassigned — Nasdaq now lists **STI** as Solidion
Technology, which has run reverse splits. So those bars are a different
company's, and the jump rule was rejecting the entire market's day on the
strength of them. `AIV` and `NKTR` are the same shape of problem. The rule
was not wrong to notice; it was looking at symbols it had no business
judging, and it took the wrong action.

This is a genuine hazard with a life beyond this rule, and it is the
*second* consequence of AMD-0016 §2C I have had to chase. Recorded in §2F.

### D2 — The rule's input depends on its own verdicts
`_prior_close` reads the last **stored** close. A rejected day stores
nothing. So one genuine >25% move leaves the next day comparing against the
same stale pre-move close, which rejects it, which stores nothing, which
rejects the next — until the window closes. The validator's input is
downstream of the validator's output. BE at 49 consecutive days is that
loop, not 49 bad days.

### D3 — A single-symbol anomaly was given a market-wide verdict
The threshold assumed a 25% daily move is impossible. For an individual
equity it is routine: BE, SMCI, CNC, FMC, NWL and CHTR all genuinely moved
that far in the window, on earnings and guidance. Across ~500 members and
520 days there are ~260,000 symbol-days; a dozen or more genuine 25% moves
is the expected count, not an anomaly. Polygon grouped-daily is requested
with `adjusted=true`, so splits are already out of the series — which makes
the remaining large moves *more* likely to be real, not less.

AC2 requires rejections "confined to days with a genuine data-quality
failure." A real price move is not one. The Delivery Controller was right to
stop rather than widen the threshold until the symptom went away.

### The root: a quality judgement was placed at the raw-storage boundary
`bars_raw` means *as received from the provider*. WO-0004 §4 says
"rejected days are kept out of `bars_raw` entirely" — and my own
DESIGN §3.3 says a rejected day is "**not published to `bars`**". My two
documents disagree, and the Work Order's version is the one that was built.
Gating the raw layer is the error that makes D2 structurally possible and
costs real money besides:

- it **destroys the evidence** needed to diagnose a rejection;
- it makes **re-validation impossible without re-fetching** — a changed
  rule costs another 100-minute backfill against a 5-call/minute limit;
- it creates D2's loop, because the only record of yesterday is a record
  that yesterday was judged acceptable.

The seam belongs where §3.3 always said it was: between `bars_raw` and
`bars`. Fixing the threshold alone would leave all of that in place.

## 2. Change

### A. `bars_raw` is never filtered by a quality judgement
`DESIGN.md` §3.3 gains:
> - **`bars_raw` records what the provider returned, always.** No
>   validation verdict may prevent a fetched row from being stored.
>   Validation records a judgement *about* a day; it is not a gate on
>   persisting it. The quality seam is `bars_raw` → `bars`
>   (`argus/data/adjust.py`), which publishes only days whose
>   `ingest_log.status = 'ok'` and excludes flagged symbol-days per
>   `bar_flags`.
> - `ingest_log.status` ∈ `{'ok','quarantined','holiday','failed'}`.
>   `'ok'` — stored, no day-level fault; any symbol flags are counted in
>   `detail`. `'quarantined'` — **stored in `bars_raw`** but carrying a
>   day-level fault, so not published to `bars`. `'failed'` — nothing was
>   fetched. `'rejected'` is retired; it conflated "judged faulty" with
>   "not stored".

This disposes of D2 structurally rather than by patch: the previous
trading day's closes are present whatever verdict that day received, so no
verdict can propagate to the next day. Option A of the Delivery
Controller's three is thereby satisfied without an in-memory carry or a
separate quarantine table — the carry *was* the workaround for gating the
raw layer.

### B. The jump rule's population (D1)
`DESIGN.md` §3.3's validation rule gains:
> The 25%-jump rule is **recorded** for every symbol in the fetched frame
> and **decided** over `members_on(d)` only. A symbol that is not a member
> on `d` — a former member whose ticker has since been reassigned, or a
> configured ETF — can never contribute to a day-level verdict (AMD-0018
> §2B). Record widely, decide narrowly.

### C. A symbol-level anomaly gets a symbol-level action (D3)
`DESIGN.md` §3.2 gains:
```
bar_flags      (symbol TEXT, date DATE, source TEXT, flag TEXT, detail TEXT)
                -- PK (symbol, date, source, flag). Per-symbol-day data-quality findings.
                -- flag: 'jump_unexplained' | 'jump_split_reconciled'  (extensible without
                -- an Amendment; the set is enumerated in argus/data/validate.py)
```
`DESIGN.md` §3.3's nightly-validation rule is replaced by:
> - Nightly validation (`argus/data/validate.py`). A day is
>   **quarantined** (stored in `bars_raw`, not published to `bars`) if
>   < 95% of members on that date have a bar; if volume is zero for > 2%
>   of them; if the jump rule is inapplicable per AMD-0017 §2B; or if
>   **≥ 20% of members on that date are flagged `jump_unexplained`**.
>   A `|close/prior_close − 1| > 0.25` move is otherwise **a flag on that
>   symbol-day, not a verdict on the day**: `jump_split_reconciled` when
>   `splits` holds a row for that `(symbol, date)` consistent with the
>   move, `jump_unexplained` otherwise. Flags are written to `bar_flags`
>   and counted in `ingest_log.detail`. The classification check applies
>   to current members only (AMD-0016 §2C).

**The 20% figure, and why it is that.** The day-level rule exists to catch
a *vendor-side* failure — prices served in the wrong scale, a wrong or
duplicated file — and those are near-total: essentially every symbol
moves. Real market action is not: on the heaviest single sessions in this
window, individual S&P 500 members moving more than 25% number in the tens,
not the hundreds. 20% of members is ~100 symbols — above anything the market
produces and far below what corruption produces. The separation is wide, so
the exact value inside it is not load-bearing; it is a named constant in
`validate.py` beside `_COVERAGE_MIN_PCT`, changeable only by Amendment, with
this reasoning in a comment. A test must fail without it (CI-6).

### D. Re-validation must not require re-fetching
`argus ingest revalidate --start A --end B` re-runs `validate_day` over
bars already in `bars_raw` and rewrites `ingest_log` and `bar_flags` for
those dates. It makes **no** provider call and **never** writes, alters or
deletes a row of `bars_raw`. Without it §2A's benefit is theoretical: the
next change to a rule would again cost a 100-minute backfill. With it, the
268 days about to be re-fetched are the **last** data this project loses to
a validation change.

### E. Resumability under the new semantics
`backfill_polygon` skips dates whose `ingest_log.status` is in
`('ok','holiday','quarantined')` — a quarantined day is already stored, and
re-fetching it cannot change the verdict. Only `'failed'` and absent dates
are fetched. Re-judging is `revalidate`'s job, not the backfill's.

### F. Ticker reassignment is a materialisation hazard — routed to WO-0007
A delisted member's ticker may be reassigned to an unrelated company (D1's
STI). `bars_raw` legitimately holds both companies' rows under one symbol,
because the provider served them that way and §2A stores what was served.
`bars` must not **concatenate** them into one price history: a reverse
split at the new company would otherwise appear as a discontinuity in the
old member's series and corrupt every 252-day momentum and
relative-strength feature that crosses it — the same class of damage CI-2
guards against for renames.

`DESIGN.md` §3.3 gains:
> - A symbol's `bars` are bounded by that symbol's own listing life. Where
>   a delisted member's ticker has been reassigned, WO-0007 must not join
>   the two companies' rows into one series; bars after the member's final
>   `membership.end_date` are excluded unless `config/ticker_renames.yaml`
>   maps the symbol forward as continuity (AMD-0014, AMD-0016).
>   `MaterialiseReport.warnings` records every symbol where bars exist
>   outside its membership intervals by more than 10 trading days.

This is recorded, not built, in this Amendment. It belongs to WO-0007,
where materialisation happens. It is the right seam and the wrong moment.

### G. WO-0012 is narrowed; the file overlap is removed
WO-0012's `argus/data/validate.py` scope — AMD-0017 §2B's
applied-and-passed versus could-not-be-applied distinction — **moves into
the WO-0004 delta.** One Work Order rewrites that function; two do not.
WO-0012 retains §2A only: store identity and relocation safety. Its
AMD-0017 §2B obligation is unchanged in substance and **still binds**, now
discharged inside WO-0004.

WO-0012 keeps its `main at Closure of WO-0004` Base SHA, but the reason
changes from file-conflict avoidance to a real dependency: **`bar_flags`
takes `SCHEMA_VERSION = 3` in the WO-0004 delta, and `store_meta` takes
`SCHEMA_VERSION = 4` in WO-0012.** Assigned here so two Work Orders cannot
claim the same version.

### H. CI-9
`CRITICAL-INVARIANTS.md` gains:
> | CI-9 | `bars_raw` is never filtered by a validation verdict: every row a provider returns is stored, and quality judgements are recorded separately in `ingest_log` and `bar_flags` | AMD-0018 §2A; DESIGN §3.3 | Gating the raw layer deletes the evidence a rejection has to be diagnosed from, makes a rule change cost a full re-fetch, and makes a validator's input depend on its own verdicts — which is how one real price move rejected 268 days. |

## 3. Sequencing and acceptance

**WO-0004 delta, then WO-0012; WO-0007 may start as soon as WO-0004
merges.** The re-fetch of the 268 discarded days (~100 minutes) and the
actions refresh (~110 minutes) are unavoidable: that data was not kept.
They are the last such cost, by §2D.

**WO-0004's acceptance is pre-committed here**, in the two-artefact form
required by AMD-0010 (a Work Order that triggers an Amendment leaves the
standing mandate). The Architect has looked again — that is what this
document is — and the conditions below are mechanical, so there is nothing
left for a second look to add:

1. Every AMD-0010 §2B condition 1–9.
2. AC2's re-run shows **no day quarantined on the ≥20% breadth rule**, or
   every such day carries a stated non-market cause. A breadth quarantine
   whose cause looks like real market action is a **stop** — it means the
   threshold is wrong, which is a decision, not a defect.
3. `jump_unexplained` flags exist and are listed; a nightly run with zero
   flags across 520 days means the rule is not firing and is a stop.
4. **STI, AIV and NKTR appear in no day-level verdict** after §2B. If any
   of them still does, report it — it is then a membership defect and a
   CI-1 question, not a validation one.
5. AC4's non-vacuity mutation runs filed, each failing the intended test.

Any one false → stop and report. **WO-0012's pre-committed acceptance in
AMD-0017 §3 stands unchanged**, less its `validate.py` conditions.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0018)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
