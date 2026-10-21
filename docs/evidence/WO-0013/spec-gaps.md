# WO-0013 — Spec gaps and residuals

## Scope extensions (disclosed; ruling 9 does not cover all)
1. `tests/test_store.py:174` — one column set gained `"basis"` (the mandated column broke an existing assertion; test file outside §2). Applied by the Delivery Controller.
2. `tests/test_schema.py` — beyond the count/version assertions ruling 9 allows, a positional `INSERT INTO dividends VALUES (...)` gained the basis value, because the table now has five columns.
3. `tests/test_ingest_polygon.py` — outside the §2 list, but §5 requires `test_judge_failure_records_quarantined` there.
Request: the Architect confirms (or widens ruling 9 to "tests that fail purely because a mandated column or table was added").

## Findings for the Architect
4. **`dividend_disagreement` is now noise.** `resolve_dividends` compares the two sources' raw `cash_amount`; Polygon is `as_paid`, yfinance `split_adjusted`, so any dividend before a later split disagrees by the split ratio (228 warnings, 42 symbols on the scratch store). The comparison should normalise both to one basis with the same `split_cum` first. Small follow-up (adjust.py, warning-only; no published value changes).
5. **`failed` days with stored rows are now published.** Only `quarantined` withholds. Historic `failed` rows that hold `bars_raw` data (from before AMD-0019 §2E) become publishable. This is the intended reading (`failed` = nothing fetched) but is a behaviour change on existing logs.
6. **`equal_weight_aggregate` is a standalone function** (no composite/market_daily code exists yet); "aggregates exclude, series do not" is proven at function level. The WO that builds the aggregates must call it. `n_symbol_days_flag_excluded` is kept as a constant 0 only so `adjust_cmds.py` (outside §2) still runs; a later WO should remove the field and the CLI line.
7. **The float32 diagnosis (AMD-0019 §1(c)) was a misdiagnosis.** No float32 existed in the code or the stored columns (views already cast to DOUBLE; polars frames were Float64). The 48 rows differing at 5.1e-8 were rows published from **yfinance** (whose prices are float32-valued) under the flag fallback that this WO removes. Result: 0 differing rows now. The DOUBLE enforcement and the widening migration are belt and braces.
8. **`_judge` failure in `revalidate_range` is unchanged:** the WO names only the post-write path in `ingest_polygon_day`. A revalidation failure still returns in the results with no log row.
9. **AMD-0018 §2F drops same-company tails.** Of the 121 boundary warnings, symbols such as AAL, AAP, ALK, K, M, WHR are the same company still trading after leaving the index; their post-exit bars (118,027 in all) are dropped because no rename continuity exists. Correct for reassigned tickers, lossy for companies that simply left the index. Not in scope here; the Architect may want a decision before features need post-exit history.
10. Split on the ex-date itself: the divisor uses the first bar on or after the ex-date, so a split dated exactly on an ex-date is not divided out. Differs from the prior-bar choice only in that edge.
