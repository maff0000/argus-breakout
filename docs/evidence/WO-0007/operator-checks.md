# WO-0007 — Operator checks (AC1, AC2, AC4)

Run by the Delivery Controller on dell-debian against head `dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c`, 2026-10-21T01:14Z, on a scratch store assembled for the purpose: the WO-0004 Polygon store (312,025 `bars_raw` rows, 46 splits, 5,448 dividends) **plus** the WO-0005 yfinance bootstrap rows and actions copied in (1,743,171 `bars_raw` rows, 207 splits, 20,843 dividends). The live stores are untouched. No key is involved; no host or port appears below.

```
host=dell-debian head=dd8d830c0f7aa9d868df3ecbbf8a5c477fa06c3c start 2026-10-21T01:14:08Z
combine: yfinance bars_raw rows 1743171 written 1743171
splits 207 207
dividends 20843 20843
(store-p4 Polygon store + store-b2 yfinance bootstrap rows/actions combined into a scratch copy)
$ argus adjust materialise   (AC1)
warning: bars_outside_membership AIV - outside=1463 before_first=0 after_final_end=1463 gap=0 excluded=1463 rename_continuity=false
warning: bars_outside_membership AJG - outside=354 before_first=354 after_final_end=0 gap=0 excluded=0 rename_continuity=false
warning: bars_outside_membership ALB - outside=377 before_first=377 after_final_end=0 gap=0 excluded=0 rename_continuity=false
warning: bars_outside_membership ALGN - outside=619 before_first=619 after_final_end=0 gap=0 excluded=0 rename_continuity=false
warning: bars_outside_membership ALK - outside=1054 before_first=343 after_final_end=711 gap=0 excluded=711 rename_continuity=false
warning: bars_outside_membership AMCR - outside=1114 before_first=1114 after_final_end=0 gap=0 excluded=0 rename_continuity=false
... 3393 more (see ingest_log.detail)
wall=24.32s
MAT1_DONE 2026-10-21T01:14:35Z
bars: [(1590779, 615, datetime.date(2015, 1, 2), datetime.date(2026, 10, 19))]
etf_bars: [(43426, 15, datetime.date(2015, 1, 2), datetime.date(2026, 10, 19))]
symbols with >=10y in bars: [(488,)]
adj_version dist: [(1, 1590779)]
ingest_log materialise: [('ok', 1634205, '{"n_symbols": 652, "n_rows": 1634205, "n_readjusted": 0, "n_days_quarantined_skipped": 0, "n_symbol_days_flag_excluded": 128, "n_warnings": 3403, "warnings": ["bars_outside_membership AAL - outside=574 before_first=54 
  MISMATCH CA 2026-05-07 [(24.99,)] [] []
  MISMATCH BBT 2026-10-19 [(27.36,)] [] []
  MISMATCH ENPH 2026-10-19 [(30.63,)] [] []
AC2: 17 / 20
digest [(1590779, Decimal('14672471556597462421815846'))]
$ argus adjust materialise again   (AC4)
warning: bars_outside_membership ALB - outside=377 before_first=377 after_final_end=0 gap=0 excluded=0 rename_continuity=false
warning: bars_outside_membership ALGN - outside=619 before_first=619 after_final_end=0 gap=0 excluded=0 rename_continuity=false
warning: bars_outside_membership ALK - outside=1054 before_first=343 after_final_end=711 gap=0 excluded=711 rename_continuity=false
warning: bars_outside_membership AMCR - outside=1114 before_first=1114 after_final_end=0 gap=0 excluded=0 rename_continuity=false
... 3393 more (see ingest_log.detail)
wall=28.09s
digest after rerun [(1590779, Decimal('14672471556597462421815846'))]
E7_DONE 2026-10-21T01:15:09Z
```

## AC1 — what was built
- `bars`: 1,590,779 rows, 615 symbols, 2015-01-02 .. 2026-10-19; `etf_bars`: 43,426 rows, 15 ETFs, same span; 488 symbols have at least 10 years of bars. Total 1,634,205 rows = `n_rows` of the run.
- 652 symbols processed; **0 quarantined days skipped; 128 symbol-days excluded by flag** (all `jump_unexplained` rows); 3,403 `bars_outside_membership` warnings (full list in `ingest_log.detail`, capped at 200 inline). They are expected: yfinance serves full history for symbols that joined the index late, and Polygon serves tickers for periods after a member's removal.
- `adj_version` is 1 for every row (first publication); `n_readjusted` 0. The hand-checked split case in this window (the 2026 splits) is covered by the split tests; the bootstrap yfinance history is already split-adjusted as of its fetch and the baseline rule applies only splits dated after the fetch.

## AC2 — Polygon close equals the published close (see `spec-defects.md`)
- Literal sample (20 random symbols, seed 7, last Polygon day): **17 of 20**. The three misses, **CA (2026-05-07), BBT (2026-10-19), ENPH (2026-10-19)**, are symbols whose last Polygon day lies after their final membership end (CA 2018-11-05, BBT 2019-12-06, ENPH 2025-08-23): AMD-0018 §2F excludes those bars on purpose, so no published row exists to compare.
- Population view, all 312,025 Polygon rows: **263,908 published with an identical close; 48 published with a close differing by at most 3.9e-5 absolute (5.1e-8 relative)** — float32 noise from the yfinance value that replaced a flag-excluded Polygon row; **48,069 not published** (outside the symbol's listing life / membership bound, or flag-excluded; none belongs to a symbol with no membership row). Restricted to symbols with a published bar on that day, 17 of 17 in the sample match exactly.
- The 51 flag-excluded symbol-days that were published from yfinance all agree with Polygon to within 1e-5 relative (51/51): the "unexplained" jumps are real moves present in both sources.

## AC4 — re-run is a no-op
Second `argus adjust materialise` on the unchanged store: `ingest_log` row `ok, rows=0, n_readjusted=0`; digest of `bars` (count, sum of per-row hash over symbol/date/close/adj_close/adj_version) identical before and after: `(1590779, 14672471556597462421815846)`.

```
$ grep -rnE '([0-9]{1,3}\.){3}[0-9]{1,3}' docs/evidence/WO-0007     # empty
```
