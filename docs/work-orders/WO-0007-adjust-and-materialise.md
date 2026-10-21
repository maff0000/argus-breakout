# WO-0007 — Adjustment and materialisation of `bars`

| Field | Value |
|---|---|
| **Status** | In Progress |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.7 (`adjust materialise`) ; `DESIGN.md` §3.2 (`bars`, `etf_bars`), §3.3 (adjustment rule) |
| **Applicable Amendments** | AMD-0002, AMD-0012, AMD-0014, AMD-0016, AMD-0018 |
| **Base SHA** | 4321d92eeea6546a8095ecda3f22e5065837cae4 |
| **Branch** | `wo/0007-adjust-and-materialise` |
| **Depends on** | WO-0004, WO-0005 |
| **Parallel group** | P0-D (with WO-0006) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0007/` |

## 1. Objective
Combine `bars_raw` from both sources into one canonical, split-adjusted
`bars` table (and `etf_bars` for ETFs) with a dividend-adjusted
`adj_close`, choosing Polygon where both sources have a day, applying new
splits to history with an incremented `adj_version`, and never silently
overwriting.

## 2. Scope (exhaustive)
```
argus/data/adjust.py                 create  select_source(raw: pl.DataFrame) -> pl.DataFrame
                                               (per (symbol,date): prefer source='polygon', else 'yfinance'; both are basis='split')
                                             apply_splits(bars: pl.DataFrame, splits: pl.DataFrame, as_of_version: int) -> pl.DataFrame
                                               (for each split dated D with ratio r: multiply open/high/low/close by 1/r and volume by r
                                                for all rows with date < D, **only for splits newer than the bars' recorded adj_version baseline**;
                                                yfinance/Polygon history is already split-adjusted as of ingestion, so a split is applied only when
                                                its date is later than the latest ingested bar of the source that supplied the historical rows)
                                             dividend_adjusted_close(bars: pl.DataFrame, dividends: pl.DataFrame) -> pl.Series
                                               (adj_close = close × Π_{ex-dates > date} (1 − dividend/close[ex-date − 1 trading day]))
                                             materialise(store, symbols: list[str] | None) -> MaterialiseReport(n_symbols, n_rows, n_readjusted, warnings)
                                               (reads bars_raw + `splits` + `dividends`, builds bars/etf_bars per symbol, writes via store.write_bars /
                                                write_etf_bars; adj_version = previous + 1 only when apply_splits changed rows; records ingest_log(source='materialise'))
argus/data/store.py                  modify  add write_etf_bars(df) / read_etf_bars(...) mirroring bars; add read_splits(...) and
                                             read_dividends(...) (AMD-0012); add resolve_symbol(symbol, as_of) -> str following the
                                             config/ticker_renames.yaml chain FORWARD to the symbol under which bars for that date are
                                             stored, recording the redirection (AMD-0016 §2D)
argus/commands/adjust_cmds.py        create  `adjust materialise [--symbols S1,S2]` (registers onto argus.commands.adjust.app)
argus/cli.py                         modify  add exactly one import line for argus.commands.adjust_cmds in the append-only block (AMD-0002)
tests/fixtures/adjust/raw_two_sources.parquet   create  one symbol with Polygon and yfinance overlap (identical closes within 0.01) and a disagreeing day
tests/fixtures/adjust/split_case.parquet        create  pre-split history + a split record dated after the last yfinance bar
tests/fixtures/adjust/dividend_case.parquet     create  known dividends with hand-computed expected adj_close values (documented in the test)
tests/test_adjust.py                 create  see §5
```

## 3. Exclusions
No provider changes, no new providers, no IBKR, no features, no schema
changes beyond none (tables already exist), no `docs/`.

## 4. Design constraints
DESIGN §3.3 adjustment rule is binding. Corporate actions come from `splits` and `dividends`, keyed
`(symbol, date, source)` (AMD-0012): resolve duplicates with the same
precedence as bars — Polygon over yfinance — and warn on any
`(symbol, date)` where sources disagree on a ratio by more than 0.1% or on a
dividend by more than one cent. Precision: compare sources at 4 decimal
places; when Polygon and yfinance disagree by > 0.5% on close for
the same day, keep Polygon and append a warning `(symbol, date, pct_diff)`
to `MaterialiseReport.warnings` and to `ingest_log.detail`. Volume is
never averaged. `adj_close` uses the prior trading day's close in the
dividend factor; if that close is missing, skip the dividend and warn.
Materialisation writes per-symbol partitions atomically.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_adjust.py::test_prefers_polygon_on_overlap` | overlapping day keeps the Polygon row | source value |
| `test_adjust.py::test_disagreement_warns_but_keeps_polygon` | > 0.5% disagreement produces a warning entry and Polygon row | warning present |
| `test_adjust.py::test_split_applied_only_to_prior_history` | 2-for-1 dated after last bar halves earlier prices, doubles volume, leaves later rows unchanged | exact values |
| `test_adjust.py::test_split_not_double_applied` | running materialise twice does not re-apply; adj_version increments once | version + values |
| `test_adjust.py::test_dividend_adj_close_hand_values` | adj_close equals the hand-computed fixture values to 1e-6 | numeric |
| `test_adjust.py::test_missing_prior_close_skips_dividend_with_warning` | — | warning + unchanged value |
| `test_adjust.py::test_source_precedence_on_actions` | Polygon and yfinance rows for the same split: Polygon's ratio is used, and a disagreement beyond tolerance is warned (AMD-0012) | value + warning presence |
| `test_adjust.py::test_etf_routed_to_etf_bars` | symbols with gics_sector='ETF' land in etf_bars, not bars | counts |

## 6. Acceptance criteria
- **AC1** — On the host, `argus adjust materialise` builds `bars` for every member/historical member and `etf_bars` for every ETF with ≥ 10 years where source data exists (operator check: counts per table, min/max date per symbol summary).
- **AC2** — For 20 random symbols the materialised close on the last Polygon day equals the Polygon raw close exactly (operator check: query, 20/20).
- **AC3** — Split handling and dividend adjustment proven by tests (§5).
- **AC4** — Re-running materialise is a no-op on unchanged inputs: zero rows changed, no version increments (operator check: row hash before/after).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC2, AC4 outputs).

## 8. Implementer notes
The subtle case is the baseline: both free sources deliver history that is
already split-adjusted *as of the day it was fetched*. A split that
occurred before the fetch is therefore already in the data; only splits
after the latest ingested bar of the supplying source need applying. Track
this per (symbol, source) using the max `ingested_at`/`date` in
`bars_raw`. Write the reasoning as comments; the Auditor will check the
fixture `split_case` against it.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
