# AMD-0014 — Current-membership invariant; ticker renames are continuity, not additions

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.3, §4; `docs/pids/PID-ARGUS-0001-foundations.md` §8.8; `docs/work-orders/WO-0003-universe-and-membership.md` §2, §4, §5, §6; `docs/work-orders/WO-0005-bootstrap-history.md` §2 (exit rule clarification) |
| **Related ADR** | ADR-0003; AMD-0013 §2C |
| **Raised by** | Delivery Controller, 2026-10-20: the WO-0003 re-audit is GREEN at `22a3ad1` with one low finding — five current index members (BNY, FISV, MRSH, SKYD, VMRK) have **no membership row**, so `members_on(today)` returns 498 against 503 current symbols, and their former tickers are counted among the 33 bounded removals |
| **Affects Work Orders** | WO-0003 (PR #5 open, not merged), WO-0005 (open, audited GREEN — §2D clarification only, no re-audit) |

## 1. Problem

AMD-0013's route (c) derives additions only where `Date added > H`
(H = hanshof's last snapshot, 2025-08-23). A **ticker rename** defeats that
by construction, and does so twice over:

- the **new** ticker sits in the current table with the company's original
  `Date added` (≤ H), so no interval is created for it — the company
  disappears from the index entirely; and
- the **old** ticker is in hanshof@H but absent from the current table, so
  it is recorded as a bounded *removal* — a company that never left.

The code is correct against the specification I wrote. The specification
was wrong: it modelled index membership as a property of a *ticker* while
the free sources describe a *company* whose ticker can change.

**Why this is not acceptable as a residual.** `members_on(today)` is the
universe every nightly scan iterates. Five names silently never screened is
not a precision question about the past, it is five companies invisible to
the product today, with no error surfaced — the exact failure mode the
rotation detector cannot survive.

## 2. Change

### A. The recommended option 2 is **rejected**, and why
The Delivery Controller proposed giving the five members "a bounded start at
the day after the last hanshof date". That models a rename as an
**addition**, which is factually false and has consequences beyond the count:

1. `members_on(d)` for `d ∈ (H, rename_date)` would exclude a company that
   demonstrably *was* a member throughout.
2. The old ticker stays a spurious removal at H, so the company **vanishes
   from the index for the gap and reappears under a new name** — a
   discontinuity injected into every equal-weight composite spanning the
   rename.
3. Worst, for later phases: the company becomes two entities with a hole
   between them, severing its price series. Every 252-day momentum,
   relative-strength and trend feature computed across the rename would be
   computed on a broken series. That is a silent wrong number, not a gap.

A rename is **one continuous membership under a changed symbol**. Nothing
about the company's index participation changed.

### B. Hard invariant — current membership must be complete
`DESIGN.md` §3.3 gains:
> - **Every symbol in the current constituents table has exactly one open
>   membership interval** (`end_date IS NULL`) (AMD-0014). If it is in the
>   index today, it is a current member — no derivation may leave it
>   without a row. `members_on(today)` must equal the current table's
>   symbol count. A shortfall is a failure, never a reported statistic.

### C. Renames are mapped, not inferred
`config/ticker_renames.yaml` (new, operator-maintained, read from
`settings.argus_config_dir` per ADR-0008):
```yaml
# old ticker -> current ticker, with the effective date where known.
# Operator-maintained: a reviewed static map is more trustworthy than
# inferring identity from `Date added` collisions, and is auditable.
renames:
  - old: <OLD>
    new: <NEW>
    effective: YYYY-MM-DD   # or null when unknown
```
Seed it with the five pairs the Delivery Controller has already identified,
with `effective` filled where it can be evidenced and `null` otherwise.

`build_membership` handling (WO-0003 §2):
- For a mapped pair with a known `effective` date: close the **old**
  ticker's interval at the last trading day before `effective`, and open
  the **new** ticker's interval at `effective`. Both rows
  `source='rename-mapped'`.
- For a mapped pair with `effective: null`: the rename happened in
  `(H, today]`. Close the old interval at H and open the new interval at
  the next trading day after H. Both rows `source='rename-bounded'`, with
  the bound recorded. This is still a bound, but it is a bound on **one
  continuous membership**, not an invented addition: the company is a
  member on every date, under one symbol or the other, with no hole.
- A mapped old ticker is **removed from the bounded-removal set**: it did
  not leave the index.

**Why a curated map rather than an algorithm.** Pairing by `Date added`
collision is available and I am rejecting it: with ~500 symbols it will
usually be unique and will occasionally mis-pair two companies added the
same day, producing a confidently wrong identity in the foundation of every
historical composite. Roughly five renames per fourteen months is minutes
of human curation against a heuristic that fails silently. The map is also
needed permanently — renames keep happening — so the nightly run needs a
place to record them regardless.

### D. Reporting, as an enforced criterion
The Delivery Controller's option 3 is adopted and strengthened from a
reported number into a gate. WO-0003 §6:
- **AC9** (new) — `UniverseReport` states `current_members_without_row`,
  and that count must be **0**. Non-zero is an acceptance failure
  (AMD-0014 §2B). The report also states the count per `source` value,
  including `rename-mapped` and `rename-bounded`.
- **AC2** gains: `members_on(today)` equals the current constituents
  table's symbol count exactly (operator check: both numbers filed).
- **AC7**'s bounded ceiling of 40 is unchanged and now excludes mapped
  renames, which are no longer removals.

WO-0003 §5 gains:
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_universe.py::test_rename_preserves_continuity` | a mapped pair with a known `effective` yields a closed old interval ending the trading day before it and an open new interval starting on it, with **no date in `[Date added, today]` where neither is a member** | asserts membership on the day before, the day of and the day after `effective`, and that the old ticker is absent from the bounded-removal set |
| `test_universe.py::test_rename_unknown_effective_is_bounded_not_added` | a mapped pair with `effective: null` is continuous across H: the old interval ends at H, the new begins the next trading day, and `members_on` returns exactly one of them on every date | asserts both dates and that the union covers the gap with no hole |
| `test_universe.py::test_no_current_member_without_row` | every symbol in the current table has an open interval (AC9) | fails if any current symbol is missing a row |

### E. Also ruled now — the P0-C retrospective item
**Skipped symbols count as successes toward WO-0005's 98% exit rule.** A
skipped symbol is one already ≥95% complete for the range; it is a success
the run did not need to repeat. Counting skips as failures would make a
fully-complete re-run exit 1, which is absurd. WO-0005 §2 gains: *"the 98%
threshold counts written **and** skipped symbols as successes; only symbols
in `failed` count against it (AMD-0014 §2E)."* This is a clarification of a
criterion I wrote ambiguously, needs no code change if the implementation
already behaves this way, and the Delivery Controller should confirm which
it does in the WO-0005 evidence rather than assume.

## 3. Sequencing and acceptance
The WO-0003 delta goes on its existing branch: `config/ticker_renames.yaml`,
the §2C handling, and AC2/AC9 plus the three §5 tests. Then re-run the
mechanicals and the two live runs, re-audit the branch whole, and merge.

**Pre-committed acceptance for this delta**, conditional on: a GREEN
whole-branch re-audit; AC9 reporting `current_members_without_row = 0`;
AC2's two numbers equal; the three §5 tests present and shown capable of
failing (mutate the rename handling to the rejected option-2 behaviour and
confirm `test_rename_preserves_continuity` fails); the diff touching only
`config/ticker_renames.yaml`, `argus/data/universe.py`,
`tests/test_universe.py` plus evidence and clerical paths; and every other
AMD-0010 §2B condition holding. Any one false → stop and report.

WO-0004 and WO-0005 merge after WO-0003 under their existing
pre-authorisations (AMD-0012 §3), with WO-0005's evidence confirming §2E.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0014)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
