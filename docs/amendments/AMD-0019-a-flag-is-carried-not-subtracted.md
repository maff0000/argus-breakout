# AMD-0019 — A flag is carried, not subtracted; dividends must be on the price basis; P0-D review rulings

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0018` §2A (withdraws the flag-exclusion clause); `docs/architecture/DESIGN.md` §3.2, §3.3, §6.1; `docs/governance/DELIVERY-CHAIN.md` §9 (adds standing ruling 9); `docs/governance/ACCEPTED-RESIDUALS.md` (adds R6, R7); `docs/work-orders/WO-0008-ibkr-reconcile-and-iv.md` §2, §4, §6 (delta, pre-dispatch); adds `docs/work-orders/WO-0013-materialisation-basis-corrections.md` |
| **Related ADR** | ADR-0003, ADR-0006, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-21, at the P0-D stop: WO-0007's `spec-gaps.md` F2/F1/#3/#4/#5 and `spec-defects.md` AC2; WO-0004 and WO-0012 `spec-gaps.md` #1 |
| **Affects Work Orders** | WO-0013 (new), WO-0008 (delta, pre-dispatch), WO-0004 and WO-0007 (closed — corrections routed to WO-0013 per DELIVERY-CHAIN §9) |

## 1. Problem

Ten of twelve Phase 0 Work Orders are merged and the P0-D review surfaces
four things worth a decision, one ratification, and a set of items that
need only to be recorded. The first is mine and it is the important one.

### (a) I made the same error a third time, in the Amendment that fixed the first two
AMD-0018 §2A says the `bars_raw` → `bars` seam "publishes only days whose
`ingest_log.status = 'ok'` **and excludes flagged symbol-days per
`bar_flags`**." The first clause is right: a day-level quarantine is a
vendor-fault verdict and withholding the day is the point of it. The second
clause is the same mistake I had just spent that Amendment correcting — **a
judgement acting as a filter.** I gated `bars_raw` on a verdict (AMD-0018
§2A fixed it), I let a rule's verdict feed its own input (§2A fixed that
too), and then in the same document I let a *symbol-level advisory* delete
data.

A flag does not say the row is wrong. It says the row is unusual. For a
breakout scanner, a member that just moved 25% is the single most
interesting symbol of the night — and the specification was withholding
exactly that row from `bars`. The Delivery Controller's F2 is the question
that found it, and the measurement settles it:

> 51 of the 128 flagged symbol-days were published via an independent
> yfinance row, and **all 51 agree with Polygon to within 1e-5 relative** —
> the jumps were real earnings-type moves.

Fifty-one for fifty-one. On the measured sample the flag's precision as a
*data-fault* detector is zero. Every one was a real price move, and the
specification's response to a real price move was to drop it.

The substitution that revealed this is itself a defect, for a different
reason: a symbol's series switched source on the most volatile day in its
history, silently, 51 times. Those two sources carry different adjustment
bases and different vendor conventions; the day of a 25% move is the worst
possible day to switch between them. It is safe *in this instance* only
because the agreement was measured. It is not safe as a rule.

### (b) Dividend amounts are not on the same basis as the prices — arithmetic, not opinion
`bars` OHLCV is split-adjusted. The dividend factor is
`Π(1 − dividend / prev_close)`. If a source stores a dividend **as paid**
and a split came later, that amount is on the pre-split share count while
`prev_close` is on the post-split basis, so the factor is overstated by the
cumulative split ratio.

This is not second-order. A symbol with a 4:1 split mid-history has every
pre-split dividend counted **four times** too large; one with 7:1 and then
4:1 inside a ten-year bootstrap window, 28 times. At a ~0.6%/year yield
that is roughly 1.8%/year of spurious adjustment accumulating in
`adj_close` — and DESIGN §5 puts `adj_close` under every return-type
feature (`ret*`, `mom12_1`, `rs_*`), which are the features the rotation
detector ranks on.

I did not specify this. DESIGN §3.3 gave the formula without saying that
the dividend must be on the same basis as the price it divides. `bars_raw`
carries a `basis` column for exactly this reason; `dividends` does not, and
should.

**Whether each source stores as-paid or already-adjusted amounts is a
question of fact, not of recall.** Polygon's and yfinance's conventions are
to be *measured*, not assumed — the last time I designed around an
unverified vendor assumption it cost four Work Orders (ADR-0003, AMD-0013).

### (c) `float32` prices break the schema I specified
> **RETRACTED — see AMD-0021 §2A.** This diagnosis was wrong. There was
> never any float32: the views already cast to `DOUBLE` and the polars
> frames were `Float64`. The 5.1e-8 differences came from **yfinance rows
> published under the flag fallback**, which §2A of this Amendment
> removes. §2C (prices stored `DOUBLE`) stands as belt and braces on
> behaviour already correct. Do not act on the paragraph below as a
> statement of cause.

DESIGN §3.2 declares every price column `DOUBLE`. The materialised store
holds `float32`, which is why published closes differ from Polygon's by up
to 5e-8 relative. That is a conformance break, not an acceptance-criterion
wording problem: the fix is the column type, after which AC2's "exactly"
holds as written. Widening 1.59 M rows costs tens of megabytes before
compression and removes a floor on every derived return.

### (d) A warning channel that fires 3,403 times is not a warning channel
`bars_outside_membership` counts both the benign case — history before a
symbol joined the index, which features **need** — and the AMD-0018 §2F
hazard, a delisted member's reassigned ticker. The Delivery Controller's
proposal to separate them is correct and I am adopting it verbatim.

## 2. Change

### A. A flag is carried, not subtracted — AMD-0018 §2A's exclusion clause is withdrawn
`DESIGN.md` §3.3's publication rule becomes:
> - Publication from `bars_raw` to `bars` withholds a **day** whose
>   `ingest_log.status` is `'quarantined'` — a day-level verdict is a
>   vendor-fault finding. It **never withholds a symbol-day for carrying a
>   `bar_flags` row** (AMD-0019 §2A; AMD-0018 §2A's exclusion clause is
>   withdrawn). A flag is an advisory that travels with the row: consumers
>   join `bar_flags` on `(symbol, date, source)` and decide for themselves.
>   A `jump_unexplained` flag on a member is the most interesting row of
>   the night, not a row to delete.
> - **Never substitute across sources to fill a flagged or withheld
>   symbol-day.** Source precedence (Polygon over yfinance) resolves which
>   source supplies a symbol's series; a flag does not re-open that choice.
>   Switching source on the day of a large move mixes two adjustment bases
>   at the worst moment and is not reproducible.
> - **Aggregates, not series, exclude.** `composites`, `market_daily` and
>   `sector_daily` exclude flagged symbol-days from their equal-weight
>   means — one bad print distorts a 500-member average — and report the
>   count excluded per date alongside `n_members` and
>   `n_members_with_bars` (CI-8). A symbol's **own** series keeps the row:
>   a hole severs the price history and breaks every 252-day momentum and
>   relative-strength feature crossing it, which is the damage CI-2 exists
>   to prevent.

`DESIGN.md` §6.1 gains `n_members_flagged` to the per-date coverage
figures that travel with every aggregate.

**Making the flag actionable, at no new cost.** WO-0008's reconciliation
already spends 20 IBKR requests a night on a rotating sample. Those
requests are retargeted so that **symbols with an unresolved
`jump_unexplained` flag from the previous session are sampled first**, with
the deterministic rotation filling the remainder. A third source then
adjudicates the previous night's flags within one day, which is what turns
a flag from a label into a finding.

### B. A dividend amount carries its basis (`dividends.basis`)
`DESIGN.md` §3.2:
```
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, basis TEXT NOT NULL, source TEXT)
                -- PK (symbol, date, source). date = ex-dividend date.
                -- basis {'as_paid','split_adjusted'} (AMD-0019 §2B): whether cash_amount is on the
                -- share count of the ex-date or already restated onto the current basis. Recorded
                -- per source from a measured check, never assumed.
```
`DESIGN.md` §3.3's adjustment rule gains:
> - **A dividend must be on the same basis as the price it divides**
>   (AMD-0019 §2B). Before use in `Π(1 − dividend/prev_close)`, an
>   `as_paid` amount is divided by the cumulative split ratio applied to
>   that symbol between the ex-date and the adjustment reference date —
>   the same cumulative factor that split-adjusts the prices. A
>   `split_adjusted` amount is used as stored. Mixing the two overstates
>   the adjustment by the split ratio: a 4:1 split makes every earlier
>   dividend count four times over, and `adj_close` carries that error
>   into every return-type feature in DESIGN §5.
> - Each source's basis is established by **measurement** and recorded in
>   `docs/evidence/WO-0013/dividend-basis.md`: for a symbol with a split
>   inside the window and dividends on both sides, compare the stored
>   amounts against the amount the company declared. A source whose basis
>   cannot be established is a **stop**, not a default.

### C. Prices are `DOUBLE`, as DESIGN §3.2 always said
Every price and `adj_close` column in `bars` and `etf_bars` is stored
`DOUBLE` (float64). `float32` is a conformance break against §3.2, not an
accepted precision trade: it puts a 6e-8 relative floor under every
published close and under every return derived from one.

### D. The membership-boundary warning channel is split
`MaterialiseReport` reports two separate figures in place of
`bars_outside_membership`:
- `n_bars_before_first_membership` — **counted, not warned.** Pre-entry
  history is required by the features and is not an anomaly.
- `n_bars_after_final_end_without_continuity` — **warned, per symbol.**
  This is the AMD-0018 §2F hazard: a delisted member's ticker reassigned to
  an unrelated company. `config/ticker_renames.yaml` continuity suppresses
  it.

Leading history is explicitly **retained**. AMD-0018 §2F bounds the tail
only; a symbol's bars before its first `start_date` are kept, and any
reading of "bounded by listing life" that drops them is wrong.

### E. A judging failure after the raw write is a quarantine, not a failure
When `_judge` raises after `bars_raw` has been written, the day's rows are
stored and unpublished — which is precisely what `'quarantined'` means.
Status `'failed'` is reserved for *nothing fetched*, so using it here both
misdescribes the day and makes the backfill re-fetch rows it already has.
Record `'quarantined'` with the exception in `detail`.

### F. Standing ruling 9 — count-and-version assertions follow the DDL
`DELIVERY-CHAIN` §9 gains:
> 9. **Count and version assertions (AMD-0019 §2F).** A Work Order whose
>    §2 adds or removes a table, or changes `SCHEMA_VERSION`, may update
>    the assertions that *count* those things — the table-count,
>    `DESIGN_TABLES` membership and schema-version assertions in
>    `tests/test_schema.py` and `tests/test_cli.py` — without that counting
>    as a scope breach, under ruling 6's three conditions. These
>    assertions are arithmetic on the mandated change, not independent
>    behaviour: a Work Order that adds a table and may not say so in the
>    count test cannot leave the suite green. The Delivery Controller
>    records the edit in `spec-gaps.md` and does **not** ask for a ruling.
>    Any other change to those files remains a stop.

WO-0004's and WO-0012's edits are **ratified** under it, retrospectively.

### G. WO-0007 AC2 — ratified under standing ruling 7, by analogy, correctly
The Delivery Controller's handling is right and its reasoning is the right
shape: cause established with counts (263,908 of 312,025 identical, 48
within float32 noise, 48,069 deliberately unpublished), shortfall named
beside the aggregate, three hard guards checked individually. The three
misses are an acceptance criterion written **before** AMD-0018 §2F, not an
implementation shortcoming.

Ruling 7 is worded for an *external data fact*, and this is a conflict
between my own criterion and my own later Amendment. The analogy holds —
the remedy is reporting, not behaviour — and ruling 7 is hereby read to
cover it: **an acceptance criterion contradicted by a later binding
Amendment is handled exactly as an unachievable one**, with the same three
guards. Proceeding there was correct and needed no ruling.

For the record, AC2's corrected wording is: *"For 20 random symbols with a
published bar on a Polygon day, the published close equals the Polygon
close; report the count of Polygon rows not published and the reason."*
WO-0007 stays **closed** with its `spec-defects.md` — a closed Work Order's
criteria are not rewritten after the fact (§9). §2A and §2C shrink the
unpublished population from 48,069 and remove the float32 term; WO-0013's
AC re-measures it.

### H. Two loggers in `store.py` — a question, not a ruling
The WO-0007 merge resolved a `store.py` conflict by keeping **both** a
structlog logger (`log`) and a stdlib one (`_stdlog`). PID §8.3 requires
structured JSON to stdout **through the redaction processor**, which is how
credentials stay out of the logs (CI-7). A stdlib logger beside it may
bypass both.

Before WO-0013 closes: state what `_stdlog` emits, whether it passes
through the redaction processor, and whether anything requires it. If
nothing does, remove it. If something does, it goes through redaction or it
does not log. This is not a finding against WO-0007 — it is the kind of
thing a conflict resolution hides, and it is to the Delivery Controller's
credit that the merge note recorded it at all.

### I. Residuals
`ACCEPTED-RESIDUALS.md` gains:

| # | Residual | Scope | Why accepted |
|---|---|---|---|
| R6 | A pre-schema-4 store copied **before** `init-store` has ever run on it cannot be detected as relocated; CI-5's relocation clause is enforced from the first post-upgrade `init-store` or read-write `connect()`. | `store_meta` | There is no record to compare against before one exists. The operational control is sufficient and cheap: `init-store` the live store on its home path before any copy. Recorded so it is not rediscovered as a defect. |
| R7 | A read-write `connect()` repairs a relocated store's views itself, announcing it in one WARNING line rather than requiring the operator to run `init-store`. | `argus/data/store.py` | This is the behaviour ADR-0008's container entrypoint depends on: a volume-mounted store arrives at a path that need not match where it was built, and self-repair is what makes that work. The verdict is still loud, and the dangerous mode — reading the old path — is what CI-5 prohibits. Recording the repair in `store_meta` as a provenance event would be better; that belongs to PID-ARGUS-0006, where relocation becomes routine. |

### J. Ratified with no action
WO-0004 §2 (no same-date split/dividend pair on Polygon — already ratified
AMD-0016 §2E), §3 (today's grouped-daily unpublished), §4 (unpinned
`ratio <> 1` and dedupe guards), §5 (**binding on WO-0009: the nightly
pipeline reads the per-day verdicts, never the exit code** — a quarantined
day exits 0 by design), §7, §9 (`ruff format` would touch 17 files: the
Phase 0 gate stays `ruff check`; a single formatting pass plus
`ruff format --check` in CI goes to WO-0009, which already owns CI and
ops, rather than churning 17 files mid-flight). WO-0007 §6 (helpers inside
§2 files — ruling 8), §7 (per-row split baseline: the synthetic test
discriminates it, so CI-6 is satisfied; the fixture need not).
WO-0012 §4 (no automated test for the `init-store` "repaired" message —
AC5's operator check covers it at this phase).

**§7's breadth measurement is worth keeping.** Across 499 live days no day
exceeded **0.42%** of members flagged, against a 20% threshold: 48× of
headroom, measured. That is the separation AMD-0018 §2C argued for, now
observed rather than asserted — and it is also why the threshold stays a
named constant rather than being tuned toward the data.

### K. WO-0008: approval authorises dispatch; acceptance is a later gate
WO-0008's **Status is Approved**, and an approved Work Order is the
Implementer's authority to build (`NO WORK ORDER → NO IMPLEMENTATION`;
there is no converse). AMD-0010 removes WO-0008 and WO-0009 from the
**Delegated Acceptance Mandate**, which is a *merge* gate — it sits
between Independent Audit and Merge in the chain. It is not a dispatch
gate, and nothing requires the Architect's acceptance before an Implementer
starts.

So **the Delivery Controller may dispatch WO-0008 now.** What waits for
explicit two-artefact acceptance is the merge, after a GREEN audit. The
one thing that genuinely needs the Product Owner's word first is the live
connection itself — it is his brokerage account — and that is being asked
of him directly, not of the chain.

Two deltas to WO-0008, both pre-dispatch, in §3 below.

## 3. Work Orders

### WO-0013 — new, Approved
`docs/work-orders/WO-0013-materialisation-basis-corrections.md` carries
§2A's publication change, §2B, §2C, §2D and §2E, and answers §2H.
WO-0004 and WO-0007 are closed, so these are post-merge corrections and a
**new Work Order is the only vehicle** (DELIVERY-CHAIN §9).

**It does not block Phase 0.** §2B's error accumulates in `adj_close` over
multi-year windows and the nightly pipeline's own operation does not depend
on it, so WO-0013 may run concurrently with WO-0008 — different files
entirely. It **must** close before PID-ARGUS-0002 computes a single
feature, because every return-type feature there reads `adj_close`.

**No re-fetch.** Every correction re-materialises from `bars_raw` and the
actions tables, which are already stored and untouched. This is AMD-0018
§2D paying for itself one day after it was written.

### WO-0008 — delta, pre-dispatch
1. **Paper-port enforcement (§2, §4).** `settings.ib_port` must be a paper
   port — **7497** (TWS paper) or **4002** (IB Gateway paper). A live
   port (7496, 4001) or any other value raises `ConfigError` naming the
   value and exits 2; the allowlist is a module constant. `readonly=True`
   stays mandatory and AC3's grep stays. Belt and braces: the Work Order
   already excludes every order, account and position call, but the
   cheapest guard against the wrong gateway is refusing to speak to it.
   New **AC6**: a live port in the environment exits 2 without opening a
   socket (test with a monkeypatched connect asserting it is never called).
2. **Flag-first sampling (§2).** `choose_sample(members, on, n=20)` gains
   `priority: list[str]` — symbols with an unresolved `jump_unexplained`
   flag from the previous session are placed first, the deterministic
   rotation fills the remainder, and the rotation offset advances as if the
   full sample had been drawn so it still covers the universe over time.
   §2A's reason: it makes a flag adjudicable by a third source within a
   day, out of a request budget already being spent.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0019)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
