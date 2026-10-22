# AMD-0031 — The payload cannot decide this: cross-source agreement resolves it, and the default understates

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0029` §2B (dedupe rule), §2C (integer-multiple rule, consequentially); `docs/architecture/DESIGN.md` §3.3; `docs/work-orders/WO-0017-dividend-duplicate-guard.md` §2, §5, §6 (delta, pre-merge) |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-22: **DVN 2024-09-13** has two *genuine* Polygon records — a fixed and a variable dividend, both **0.22**, same declaration date **2024-08-06**, same frequency **4** — which my three-field dedupe collapses to 0.22 against yfinance's 0.44 |
| **Affects Work Orders** | WO-0017 (delta, pre-merge). WO-0009 unaffected except for the §3 sequencing note |

## 1. Problem

### (a) Three attempts, each trading one error for its opposite
| | Rule | What it broke |
|---|---|---|
| AMD-0012 | `dividends` keyed `(symbol, date, source)` | discarded a genuine second dividend (PGR 13.50) |
| AMD-0027 | key on `vendor_id`, sum the records | summed a duplicated record (TEL 1.30 for 0.65) |
| AMD-0029 | dedupe on amount + declaration date + frequency | **collapses a genuine pair (DVN 0.22 + 0.22)** |

Each fix was correct about the case in front of it and wrong about the
next one. The reason is not carelessness in choosing fields. It is that
**the payload does not contain the fact we need.**

**TEL's duplicate and DVN's genuine pair have the identical signature**:
same amount, same declaration date, same frequency, differing ids. No
function of those three fields separates them, because the fact that
distinguishes them — *these are two different declared dividends* — exists
in the issuer's announcement and not in Polygon's record. A fourth field
would not help; there is no fourth field.

So the honest conclusion is architectural, not a better key: **stop trying
to decide this from one source.** The Delivery Controller's observation is
the only available discriminator and it is a good one:

- **TEL**: yfinance 0.65 equals **one record** → duplicate.
- **DVN**: yfinance 0.44 equals **the sum** → genuine.

### (b) The three fields still do real work
They are not replaced. DVN's *other* two-record quarters survive today
**only because their frequencies differ**, and PGR's pair separates on both
fields. The signature resolves most cases; cross-source resolves the
residue it cannot.

## 2. Change

### A. An identical-signature group is *ambiguous*, and the second source resolves it
`DESIGN.md` §3.3's dedupe rule is replaced:
> - Records of one `(symbol, date, source)` that differ in `cash_amount`,
>   `declaration_date` **or** `frequency` are **distinct dividends** and are
>   summed (AMD-0029 §2B).
> - Records identical in all three and differing only in `vendor_id` are
>   **ambiguous**, not duplicates: a duplicated record and a genuine pair
>   are indistinguishable from one source (AMD-0031 §1a — TEL and DVN share
>   the signature). They are resolved against the **other source's
>   basis-normalised total** for that `(symbol, date)`:
>   - within one cent of the **single** amount → **duplicate**, collapse;
>   - within one cent of the **sum** → **genuine**, keep both;
>   - **neither, or no second source** → **collapse**, warn, and **count
>     it** (§2B).
> - Every ambiguous group's resolution and the evidence for it is recorded
>   in `MaterialiseReport.warnings`, so a later reader can see which
>   interpretation was taken and why. This needs **no vendor call**: both
>   sources' rows are already in `dividends`.

### B. The default understates, deliberately, and its use is counted
**Collapse is the default when the second source cannot decide**, because
the two errors are not symmetric. `adj_close` for a past date is the
present close divided back through the dividend factors, so an
**overstated** dividend makes historical `adj_close` smaller and therefore
**inflates measured historical returns**. A dividend payer then looks like
a stronger momentum name than it was, gets selected more often, and the
realised forward return does not match. That is the unstated-optimism
direction this project keeps refusing (R5, CI-8). An understated dividend
errs the other way and is the safer error.

**The count of groups resolved by the default must be reported** with every
materialise run, not merely logged. A tie-breaker is acceptable while it
is rare and visible; if it ever becomes load-bearing — tens of groups
rather than one or two — it needs revisiting rather than trusting. Same
discipline as CI-8: the figure travels with the result.

### C. §2C's integer-multiple rule is unchanged but will fire less
With §2A resolving DVN as genuine, its 2× disagreement disappears, so
AC3's thirteen warnings become **twelve — the FCX doublings**, which are
genuine vendor omission (R9) and correctly left on precedence.

### D. `dividends` still stores every record
Unchanged and worth restating: **no row is ever deleted.** Deduplication is
an *adjustment-time* decision over stored rows, so a later ruling can
reinterpret the same data without a re-ingest. The three attempts in §1a
cost one re-ingest between them precisely because the storage was right;
the decision layer is where this belongs.

## 3. WO-0017 delta, and sequencing
**WO-0017 §2** gains §2A's resolution in `argus/data/adjust.py`, and §2B's
counter in `MaterialiseReport`. **§5** gains:
- `test_ambiguous_group_resolved_genuine_by_second_source` — DVN's shape:
  two identical-signature records, other source equals the sum → both
  count, total 0.44.
- `test_ambiguous_group_resolved_duplicate_by_second_source` — TEL's shape:
  other source equals one record → collapse to 0.65.
- `test_ambiguous_group_defaults_to_collapse_and_counts_it` — no second
  source → collapse, warn, and the counter increments.

**AC1** gains DVN 2024-09-13 to the attribution set. **AC2** gains the
count of default-resolved groups. **AC6** gains a fourth mutation:
resolving an ambiguous group as genuine **by default** must fail
`test_ambiguous_group_defaults_to_collapse_and_counts_it`.

**This is a pre-merge delta to an open Work Order** (AMD-0016 §2A), not a
RED: the stop was correct, the finding is mine, and the Delivery
Controller's recommended rule is adopted essentially as proposed. **Its
pre-committed acceptance in AMD-0029 §3 stands**, with DVN added to the
attribution condition.

**Sequencing against WO-0009.** The production store is at
`SCHEMA_VERSION` 6 and WO-0017 takes it to 7. **Do not migrate the
production store during WO-0009's three unattended nights.** Those nights
prove *orchestration* — the units fire, the steps run in order, the logs
arrive, the reports are written — and nothing about them depends on
`adj_close`, so a schema-6 store is valid evidence for them. Migrating
mid-sequence would perturb a night for no gain. **Migrate after WO-0009
closes.**

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0031)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
