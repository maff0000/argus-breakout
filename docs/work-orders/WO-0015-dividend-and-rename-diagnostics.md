# WO-0015 — Diagnostics: same-date dividend collapse, and undeclared ticker renames

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5, §8.6 ; `DESIGN.md` §3.2, §3.3 |
| **Applicable Amendments** | AMD-0012, AMD-0014, AMD-0016, AMD-0025 |
| **Base SHA** | main at Closure of WO-0014 |
| **Branch** | `wo/0015-dividend-and-rename-diagnostics` |
| **Depends on** | WO-0014 (merged) |
| **Parallel group** | P0-F3 — **may run concurrently with WO-0009**; shares no file with it |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0015/` |

## 1. Objective
**Establish two mechanisms by measurement. Change nothing.**

This Work Order writes **no production code**. It adds two read-only
diagnostic commands and files what they find. The fix for either finding,
if one is warranted, is a separate Work Order designed from the facts this
one produces (AMD-0025 §2A).

## 2. Scope (exhaustive)
```
argus/commands/diagnose_cmds.py   create  `diagnose dividends --symbol S --date D [--raw]` and
                                            `diagnose renames [--gap-days N]`, registered onto a new
                                            `argus.commands.diagnose.app`; one import line added to
                                            argus/cli.py's append-only block (AMD-0002)
argus/diagnostics/dividends.py    create  same_date_dividend_report(store, client | None) -> pl.DataFrame
                                            [symbol, date, source, n_rows_stored, stored_amount, note]
                                          With --raw and a Polygon client: fetch the RAW /v3/reference/dividends
                                          payload for ONE symbol and date, record how many records the API
                                          returns for that (symbol, ex_date), their cash_amount values and any
                                          dividend_type / frequency fields VERBATIM, and whether the stored
                                          row equals one of them, their sum, or neither. This is the
                                          measurement that decides AMD-0025 §1a. It is READ-ONLY: it must not
                                          write to `dividends`, `bars` or any table
argus/diagnostics/renames.py      create  undeclared_rename_candidates(store) -> pl.DataFrame
                                            [old_symbol, old_end_date, new_symbol, new_start_date, gap_trading_days,
                                             new_symbol_first_bar, bars_before_new_start, price_ratio_at_boundary, confidence]
                                          Signals, all from stored data, none decisive alone:
                                            (1) a current member whose membership start is materially later than its
                                                FIRST STORED BAR — the decisive one: both free sources serve a renamed
                                                company's whole history under the NEW ticker (AMD-0016 §2D), so bars
                                                predating the membership interval indicate the interval begins at a
                                                rename, not at the company's listing
                                            (2) another symbol's interval ending within `--gap-days` (default 10) of it
                                            (3) the two symbols' closes at the boundary within 10% of each other
                                          Output is RANKED CANDIDATES FOR OPERATOR REVIEW. It must not edit
                                          `config/ticker_renames.yaml`, must not write `membership`, and must not
                                          merge any interval (AMD-0025 §2C)
tests/test_diagnostics.py         create  see §5
```

## 3. Exclusions
**No fix of either problem.** No schema change, no `SCHEMA_VERSION` bump,
no change to `dividends`, `splits`, `membership`, `bars_raw`, `bars`,
`adjust.py`, `validate.py`, any provider client, or
`config/ticker_renames.yaml`. No `adj_close` recomputation. No
`providers/ibkr.py` or `reconcile.py` (WO-0009's). No `docs/` by the
Implementer. **If the diagnosis suggests an obvious fix, do not apply it —
report it.**

## 4. Design constraints
PID §8.5, §8.6, §8.9 and ADR-0008's portability constraints.

`diagnose renames` is **wholly offline** and read-only. `diagnose
dividends` is offline **except** with `--raw`, which makes exactly one
Polygon call per invocation and requires `POLYGON_API_KEY`; without
`--raw` it reports only stored data. Both open the store **read-only**, so
a relocated store raises rather than being repaired (CI-5).

Record the raw API payload's field names and values **verbatim** in the
evidence. The purpose is to establish a vendor fact, and a paraphrase is
not a measurement (the WO-0013 `dividend-basis.md` standard).

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_diagnostics.py::test_same_date_report_lists_suspect_dates` | a seeded store with a Polygon amount far below yfinance's on one ex-date appears in the report with both values | asserts the row and both amounts |
| `test_diagnostics.py::test_raw_payload_record_count_is_reported` | with a respx-mocked payload holding **two** records for one `(symbol, ex_date)`, the report states `n_records_returned = 2`, lists both amounts, and flags that the stored row equals neither their sum nor one of them | asserts the count and the classification — this is the measurement AMD-0025 §1a turns on |
| `test_diagnostics.py::test_diagnostics_never_write` | after both commands run against a seeded store, every table's row count and a `bars_raw` checksum are unchanged | asserts equality — CI-9 and §3 |
| `test_diagnostics.py::test_rename_candidate_detected_from_bars_before_membership` | a symbol with bars from 2012 whose membership opens in 2022, with another symbol's interval ending two days before and closes within 10%, is returned as a high-confidence candidate | asserts the row and its confidence |
| `test_diagnostics.py::test_genuine_new_listing_is_not_a_candidate` | an IPO — first bar and membership start on the same date, no other interval ending nearby — is **not** returned | asserts absence; fails if signal (1) alone is treated as sufficient |
| `test_diagnostics.py::test_renames_does_not_edit_config_or_membership` | `config/ticker_renames.yaml` is byte-identical and `membership` row counts unchanged after the command | asserts both |

## 6. Acceptance criteria
- **AC1** — `docs/evidence/WO-0015/dividend-mechanism.md` states, **with the verbatim raw Polygon payload for at least PGR 2026-01-02 and FCX on one quarterly ex-date**, how many records the API returns per `(symbol, ex_date)`, their amounts and type fields, and whether the stored amount equals one record, their sum, or neither. It ends with a plain statement: the collapse hypothesis is **confirmed** or **refuted**, and on what evidence.
- **AC2** — The same report lists every `(symbol, ex_date)` in the store where Polygon and yfinance disagree by more than 2× after basis normalisation, with both amounts and the resulting `adj_close` error as a percentage of price on that date. The population is stated, not a sample.
- **AC3** — `docs/evidence/WO-0015/rename-candidates.md` ranks undeclared rename candidates with all three signals per row, and states for each whether it is a probable rename, a probable reassignment, or not discriminable. **FB/META is present and explicitly adjudicated.**
- **AC4** — The same report states whether any **current** member's membership interval begins materially after its first stored bar — the CI-2 severance case — and names every one.
- **AC5** — Nothing was written: every table's row count and a `bars_raw` checksum are identical before and after both commands, `config/ticker_renames.yaml` is byte-identical, and `git status` on the host clone is clean (operator check, all figures filed).
- **AC6** — Non-vacuity, mandatory (CI-6): file two mutation runs — (a) treating a multi-record payload as a single record makes `test_raw_payload_record_count_is_reported` fail; (b) accepting signal (1) alone as sufficient makes `test_genuine_new_listing_is_not_a_candidate` fail.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC5), `dividend-mechanism.md` (AC1, AC2),
`rename-candidates.md` (AC3, AC4), and the AC6 mutation runs.

## 8. Implementer notes
Both findings are the Architect's defects, not the previous Implementers':
`dividends`' key was specified in AMD-0012, and CI-2's reach was specified
in AMD-0014. Your job is to establish what is true, **not to repair it** —
and a diagnostic that quietly fixes what it finds destroys the measurement
it exists to produce.

Report a refutation with the same care as a confirmation. "The hypothesis
is wrong and here is the payload that shows it" is a complete and valuable
result, and it is the outcome that saves the most work.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
