# AMD-0012 — Split `adjustments` into `splits` and `dividends`; ratify the bootstrap exit threshold

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/pids/PID-ARGUS-0001-foundations.md` §8.5; `docs/work-orders/WO-0002-schema-and-store.md` §2, §5, §6; WO-0004 §2, §6; WO-0005 §2, §6; WO-0007 §2, §4, §5; supersedes AMD-0011 §3 condition 4 |
| **Related ADR** | ADR-0002, ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-20, recording as an observation that `adjustments` is keyed `(symbol, date)` so Polygon and yfinance rows for the same day can overwrite each other |
| **Affects Work Orders** | WO-0002 (delta pending — DDL folded in), WO-0004 (Implementer in flight), WO-0005 (committed at `8ecc4a9`, audit in flight), WO-0007 (not started — simplified) |

## 1. Problem

The Delivery Controller filed this as an observation for the Architect. It
is not an observation; it is a **silent data-loss defect in my schema**, and
it must be fixed before WO-0007 runs. There are two collision paths, and
the Delivery Controller reported only the first.

`adjustments (symbol, date, split_ratio NULL, cash_dividend NULL, source)`
keyed `(symbol, date)`:

**Path 1 — cross-source (reported).** Polygon and yfinance both write
corporate actions. Two rows for the same `(symbol, date)` collide and the
second `upsert` overwrites the first, losing one source's value and its
provenance.

**Path 2 — within one source, and materially worse (not reported).** WO-0004
writes **both** splits and dividends into this one table from two separate
endpoint calls: `splits()` yields rows carrying `split_ratio` with
`cash_dividend` NULL, `dividends()` yields the reverse. For a symbol with a
split **and** a dividend on the same date, the second `upsert` writes
`split_ratio = NULL` over the first's value. WO-0005's `actions()` has the
same shape and the same exposure.

**Why this is not a tolerable residual.** WO-0007's `apply_splits` reads
that column. A nulled split means the price series is never adjusted across
it — a 2:1 or 10:1 discontinuity left in the data, silently. Every §5
feature, every equal-weight composite and every rotation signal in
PID-ARGUS-0002 is computed from those prices, and `validate.py`'s own
25%-jump rule would then *reject* the real split day for having no split
record. One nulled cell corrupts a symbol's entire history and the
validator misreads the symptom.

**Root cause is mine:** a table with two optional measures keyed by
`(symbol, date)` makes this collision inevitable. Keying on
`(symbol, date, source)` fixes path 1 only — path 2 is within a single
source, so it survives. Column-wise `COALESCE` on upsert would work but
makes correctness depend on every writer remembering to do it, in a generic
`upsert()` helper shared by every table.

Decisive argument for the chosen fix: **WO-0007's own signatures already
want them separate** — `apply_splits(bars, splits, …)` and
`dividend_adjusted_close(bars, dividends, …)`. The single table was always
the awkward fit, forcing WO-0007 to filter on NULLs.

## 2. Change — two tables, no nullable measures

**`DESIGN.md` §3.2** replaces the `adjustments` line with:
```
splits         (symbol TEXT, date DATE, ratio DOUBLE NOT NULL, source TEXT)
                -- PK (symbol, date, source). date = execution/effective date. ratio = to/from (2.0 for a 2:1).
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, source TEXT)
                -- PK (symbol, date, source). date = ex-dividend date.
                -- Two tables, not one nullable-measure table: a split and a dividend on the same
                -- (symbol, date) must both survive, from each source independently (AMD-0012).
```

**`DESIGN.md` §3.3** gains:
> - Corporate actions are stored **per source** and never overwritten
>   across sources: PK `(symbol, date, source)` on both `splits` and
>   `dividends` (AMD-0012). WO-0007 resolves duplicates by the same
>   precedence as bars — Polygon over yfinance — and records in
>   `MaterialiseReport.warnings` any `(symbol, date)` where the sources
>   disagree on a split ratio by more than 0.1% or on a dividend by more
>   than one cent.

The §3.3 validation rule "no split in `adjustments`" reads "no split in
`splits`".

**Phase PID §8.5**: `read_adjustments(symbols)` becomes
`read_splits(symbols, start, end)` and `read_dividends(symbols, start, end)`.

**WO-0002 §2**: the schema DDL covers `splits` and `dividends` in place of
`adjustments`, with PK `(symbol, date, source)` on each and both measures
`NOT NULL`. §5 gains `test_schema.py::test_actions_tables_keyed_by_source`
— a split row and a dividend row for the same `(symbol, date)` coexist, and
two sources' rows for the same `(symbol, date)` both persist. §6 AC1's table
count becomes **19**.

**WO-0004 §2**: `ingest_polygon_actions` writes `splits()` to `splits` and
`dividends()` to `dividends`, each `upsert` keyed
`["symbol","date","source"]`. §6 AC3 counts rows in both tables and
requires that a symbol with a same-date split and dividend retains both.

**WO-0005 §2**: `actions()` keeps its single return frame (it is one
yfinance call) but `bootstrap_history` writes the non-null split rows to
`splits` and the non-null dividend rows to `dividends`, keyed
`["symbol","date","source"]`. §6 AC3 updated likewise.

**WO-0007 §2/§4**: `apply_splits` and `dividend_adjusted_close` read the two
tables directly — the NULL-filtering they would have needed is gone. §4
gains the source-precedence and disagreement-warning rule from §3.3 above.
§5 gains `test_adjust.py::test_source_precedence_on_actions` — Polygon and
yfinance rows for the same split: Polygon's ratio is used and a disagreement
beyond tolerance is warned.

## 3. Sequencing — no interrupted dispatches

Do **not** interrupt a running Implementer or Auditor. Let WO-0005's audit
and WO-0004's implementation complete against their current scope, then:

1. **WO-0002** — fold this DDL change into the delta already pending under
   AMD-0011. **This supersedes AMD-0011 §3 condition 4** ("the delta diff
   touches only `tests/test_store.py`"): the delta may now also touch
   `argus/data/schema.py`, `argus/data/store.py` and `tests/test_schema.py`.
   AMD-0011 §3's other four conditions stand, and acceptance remains
   pre-committed on them plus a GREEN re-audit covering AC1 (19 tables) and
   the new §5 test.
2. **WO-0004 and WO-0005** — one delta dispatch each for the two write
   targets, then re-audit each branch whole. **Neither merges before its
   delta lands**, so each merges once, audited at its final state.
3. **WO-0007** — unchanged in sequence; it starts from the corrected schema.

**Pre-committed acceptance for the WO-0004 and WO-0005 deltas.** Both are
mechanical consequences of this amendment, fully specified above, so the
Architect grants acceptance in advance for each, conditional on: a GREEN
re-audit of the whole branch; AC3 verified including the same-date
split-and-dividend case; every other AMD-0010 §2B condition holding; and the
delta touching only the files named in §2 for that Work Order plus evidence
and clerical paths. Any one false → stop and report. Note this does not
make either Work Order mandate-eligible for anything beyond its delta.

## 4. Also ruled now, so they need not wait on the audit

**Bootstrap exit threshold — ratified.** WO-0005's CLI exits 1 when more
than 2% of symbols fail. AC1 states "≥ 98% of symbols", so exiting non-zero
below that is the faithful reading of a criterion I wrote, not an invented
policy. WO-0005 §2 gains the explicit sentence: *"`ingest bootstrap` exits 0
when ≥ 98% of requested symbols were written and 1 otherwise, reporting the
failed list either way (AMD-0012)."*

**Resume heuristic — correctly deferred.** The Delivery Controller is right
to wait for the Auditor's view rather than ask me to pre-empt it. The
standard that applies is WO-0005 §5
`test_ingest_bootstrap.py::test_resumable_skips_complete_symbols` plus
non-vacuity: if the skip rule cannot be shown capable of both skipping a
complete symbol and *not* skipping an incomplete one, that is a finding
regardless of how reasonable the heuristic looks. Route it on the audit.

## 5. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0012)`.

## 6. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
