# WO-0016 — Dividend record identity: attribute all thirteen pairs, then fix both mechanisms

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5, §8.6 ; `DESIGN.md` §3.2, §3.3 |
| **Applicable Amendments** | AMD-0012, AMD-0019, AMD-0021, AMD-0025, AMD-0027 |
| **Base SHA** | main at Closure of WO-0015 |
| **Branch** | `wo/0016-dividend-record-identity` |
| **Depends on** | WO-0015 (merged — its measurement is this Work Order's premise) |
| **Parallel group** | P0-F4 — **may run concurrently with WO-0009**; shares no file with it |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0016/` |

## 1. Objective
Fix the two mechanisms WO-0015 established — **and attribute the remaining
twelve pairs before applying either fix**, so the right one is applied to
each.

1. **Measure first.** Fetch the raw Polygon payload for the twelve
   unattributed `(symbol, ex_date)` pairs and attribute each to *collapse*
   (several records, one kept) or *omission* (one record, smaller than the
   other source's total).
2. **Collapse** → `dividends` keyed on the vendor record identity, and the
   adjustment sums an ex-date's records (AMD-0027 §2A, §2B).
3. **Omission** → the stated precedence rule on normalised totals
   (AMD-0027 §2D).
4. **Neither** → **stop and report.** Do not invent a third mechanism.

## 2. Scope (exhaustive)
```
argus/data/schema.py           modify  dividends: add `vendor_id TEXT NOT NULL`; PK becomes
                                         (symbol, date, source, vendor_id); bump SCHEMA_VERSION to 6
argus/data/providers/polygon.py modify  dividends(): carry the record's `id` through as vendor_id
                                         (verified present on every record, WO-0015 evidence). Do NOT use
                                         dividend_type or frequency as identity — both PGR 2026-01-02 records
                                         are dividend_type "CD" (AMD-0027 §2A)
argus/data/providers/bootstrap.py modify  yfinance dividends: vendor_id = the literal 'sum' (one summed figure
                                         per ex-date; no per-record identifier exists)
argus/data/ingest_polygon.py   modify  ingest_polygon_actions: upsert dividends on the four-column key, so every
                                         record for an ex-date persists
argus/data/adjust.py           modify  (a) the dividend for an ex-date is the SUM of the chosen source's records
                                           for it, after precedence and after basis normalisation
                                       (b) AMD-0027 §2D: where two sources' normalised summed totals differ by
                                           more than one cent AND 2% relative, take the LARGER, record
                                           `total_source`, and warn with both figures
argus/commands/store_cmds.py   modify  the migration backfills vendor_id for existing rows ('sum' for yfinance;
                                         for Polygon rows, re-derivation requires a refetch — see §8) idempotently,
                                         printing before/after counts per table
argus/diagnostics/dividends.py modify  add `attribute_pairs(store, client, pairs) -> pl.DataFrame` for AC1; this is
                                         the WO-0015 command extended to a list, still read-only
tests/test_adjust.py           modify  add the §5 tests
tests/test_polygon_client.py   modify  add the vendor_id test
tests/test_schema.py           modify  count/version assertions only (DELIVERY-CHAIN §9 ruling 9)
tests/test_cli.py              modify  count/version assertions only (ruling 9)
```

## 3. Exclusions
No rename work of any kind — that line is closed (AMD-0027 §2E) and
`argus/diagnostics/renames.py` is **not** to be touched. No
`providers/ibkr.py` or `reconcile.py` (WO-0009's). No validation-rule
change. No feature computation. No `docs/` by the Implementer.

**Do not change source precedence generally.** §2D is a narrowly scoped
rule about the *total for one ex-date*, not a reordering of Polygon over
yfinance anywhere else.

## 4. Design constraints
PID §8.5, §8.6, §8.9 and ADR-0008's portability constraints.

The twelve attribution fetches are **twelve Polygon calls**, inside the
5-per-minute limit via the existing pacer; the key is never printed.
Everything after attribution re-materialises from stored data: **no
`bars_raw` row may change** (CI-9, checksum).

`vendor_id` is `NOT NULL`, so the migration must give every existing row a
value. See §8 on the Polygon rows.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_polygon_client.py::test_vendor_id_carried_from_payload` | a two-record fixture for one ex-date yields two rows with the payload's two `id` values | asserts both ids — the PGR case |
| `test_adjust.py::test_two_records_one_ex_date_both_persist_and_sum` | 0.10 and 13.50 on one ex-date both stored, and the factor uses 13.60 | asserts the stored count **and** the factor |
| `test_adjust.py::test_same_amount_twice_does_not_collapse` | two records with the **same** `cash_amount` and different ids both persist | fails any key that includes the amount instead of the id |
| `test_adjust.py::test_larger_normalised_total_wins_and_warns` | Polygon 0.075 against yfinance 0.15 normalised → the 0.15 total is used, `total_source` recorded, a warning carries both | asserts the chosen total, the record and the warning |
| `test_adjust.py::test_basis_difference_is_not_an_omission` | the same economic dividend stored `as_paid` and `split_adjusted` across a 2:1 split does **not** trigger §2D | fails if the comparison skips normalisation — this is the trap in §2D |
| `test_adjust.py::test_sub_threshold_difference_changes_nothing` | a half-cent / 1% difference leaves precedence untouched and warns nothing | the threshold, both sides |
| `test_schema.py` / migration | `SCHEMA_VERSION` 6; the migration is idempotent and loses no rows | counts before/after |

## 6. Acceptance criteria
- **AC1** — `docs/evidence/WO-0016/attribution.md` attributes **all thirteen** pairs — the twelve plus PGR 2026-01-02 from WO-0015 — each with its raw payload summary (record count, amounts, `id` values) and a verdict of **collapse**, **omission**, or **neither**. **No pair may be left unattributed, and "neither" is a stop, not a residual.**
- **AC2** — Every pair attributed to collapse has all its records in `dividends` after re-ingest, and the summed factor matches the other source's total to within one cent (operator check: per-pair before/after).
- **AC3** — Every pair attributed to omission takes the larger normalised total with `total_source` recorded and a warning filed (operator check: the list).
- **AC4** — `adj_close` before and after, per affected symbol, on three dates each — including PGR, where the pre-2026 history should move by about the 5.93% WO-0015 measured (operator check: the figures, and the direction explained).
- **AC5** — `bars_raw` is **byte-identical** before and after (checksum, CI-9); `SCHEMA_VERSION` is 6; the migration is idempotent and loses no rows.
- **AC6** — Non-vacuity, mandatory (CI-6): file three mutation runs — (a) keying on `dividend_type` instead of `vendor_id` fails `test_vendor_id_carried_from_payload` **and** `test_two_records_one_ex_date_both_persist_and_sum` (this is the design error the measurement prevented); (b) including `cash_amount` in the key fails `test_same_amount_twice_does_not_collapse`; (c) comparing raw rather than normalised amounts fails `test_basis_difference_is_not_an_omission`.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC2–AC5), `attribution.md` (AC1), and the AC6
mutation runs.

## 8. Implementer notes
Both mechanisms are the Architect's to own: the key was specified in
AMD-0012 and narrowed again in AMD-0025's scope note, and the precedence
rule is new in AMD-0027 §2D.

**On the migration and `vendor_id` for existing Polygon rows.** A stored
Polygon row has no `id` recorded, and the id cannot be reconstructed
locally. Two honest options — **choose the second unless it proves
impractical, and say which you chose and why**:
1. Backfill the existing Polygon rows with `vendor_id = 'legacy'`, leaving
   them collapsed until the next `ingest polygon-actions` refresh replaces
   them.
2. **Re-run `ingest polygon-actions --since <store start>`** after the
   migration, so every Polygon row carries its real id and the collapse is
   undone for the whole store rather than only for future ex-dates. This is
   the complete fix and costs a bounded number of paginated calls.

Option 1 leaves a store that *looks* fixed while the historical collapse
persists — the failure mode this project keeps meeting. Prefer option 2.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
