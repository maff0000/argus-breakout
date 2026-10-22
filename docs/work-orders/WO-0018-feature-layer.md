# WO-0018 — DESIGN §5 feature layer and cross-sectional percentiles

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0002-screening-engine.md` (Draft) ; `DESIGN.md` §5 ; `PID.md` §8 |
| **Applicable Amendments** | AMD-0019, AMD-0021, AMD-0023, AMD-0028, AMD-0033 |
| **Base SHA** | main at the commit introducing this file |
| **Branch** | `wo/0018-feature-layer` |
| **Depends on** | the Phase 0 store (`bars`, `etf_bars`, `membership`, `symbols`, `events`, `bar_flags`) |
| **Parallel group** | **P2-A — runs CONCURRENTLY with Phase 0** under AMD-0033 §2A |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0018/` |

## 0. Overlap conditions (AMD-0033 §2A), recorded as required
1. **Shares no source file with any open Work Order.** WO-0017 touches
   `adjust.py`; WO-0009 touches `pipeline.py`, `reconcile.py`,
   `providers/ibkr.py`, `nightly_cmds.py`, `events/earnings.py`, `ops/`.
   This creates `argus/features/` and touches neither set. **The nightly
   pipeline step for features is NOT in this Work Order** — that is
   WO-0022, after Phase 0 closes, and adding it here would collide with
   WO-0009.
2. **Depends on no table, column or interface an open Work Order is
   changing.** It reads `bars`, `etf_bars`, `membership`, `symbols`,
   `events`, `bar_flags` — none of whose shapes WO-0017 or WO-0009 alters.
   WO-0017 changes dividend **values** inside `bars.adj_close`; WO-0009 adds
   two columns to `events` which this Work Order reads but does not require.
3. **Evidence cited:** PID-ARGUS-0002 §4.
4. **Product Owner approved the overlap**, 2026-10-22.

**Acceptance does not depend on the feature values being final.** WO-0017
will shift `adj_close` on thirteen ex-dates and therefore some feature
values; that changes nothing about whether the computation is correct, and
no acceptance criterion below asserts a particular market value.

## 1. Objective
Compute every DESIGN §5 feature for every symbol and trading date, with
each feature's cross-sectional percentile across the universe and within
its sector, into the `features` table.

This is the layer the whole product sits on: the playbooks score
percentiles, and nothing downstream can be better than this.

## 2. Scope (exhaustive)
```
argus/features/__init__.py      create  compute_features(store, start, end, symbols=None) -> FeatureReport(
                                          n_dates, n_symbols, n_rows,
                                          null_counts: dict[str, int],          # per feature, over the run
                                          pct_population: pl.DataFrame[date, feature, n_non_null, n_members],
                                          seconds: float)
                                        Writes `features`; idempotent per (date, symbol)
argus/features/trend.py         create  sma20 sma50 sma150 sma200, slope20_5, slope50_10, ma_stack,
                                          trend_template, adx14 (Wilder), clenow90
argus/features/momentum.py      create  ret5 ret21 ret63 ret126 ret252, mom12_1, macd_hist
argus/features/relative.py      create  rs_spx, rs_sector, rs_ig, rs_spx_nh63, rs_rank,
                                          rs_rank_sector, rs_rank_ig, beta60
argus/features/volatility.py    create  atr14 (Wilder), atr_pct, dist20_atr, hv20 hv60 hv_rank252,
                                          bb_width, bb_width_pct252, squeeze
argus/features/flow.py          create  rvol, updown_vol20, dist_days25, obv_slope20, cmf20, adv20_usd
argus/features/reversion.py     create  rsi14, rsi2 (Wilder), z20, consec_down, consec_up
argus/features/structure.py     create  pct_from_hi252, pct_from_lo252, donchian20_hi, donchian55_hi,
                                          base_len, base_depth, gap_pct, nr7
argus/features/candles.py       create  body_pct, upper_wick_pct, lower_wick_pct, marubozu, doji, range_atr
                                          (AMD-0023 §2D — CONFIRMATION terms, computed here, never a trigger)
argus/features/levels.py        create  pivot_d r1_d s1_d r2_d s2_d and the _w/_m variants, dist_pivot_atr,
                                          dist_r1_atr, dist_s1_atr, swing_hi, swing_lo, dist_res_atr,
                                          dist_sup_atr, res_touches, sup_touches
                                          (distances in ATR, NEVER per cent — AMD-0023 §2D)
                                          SWING LEVELS, fully specified by AMD-0034 §2B (the numbers WO-0018's
                                          first pass correctly refused to guess):
                                            lookback 252 trading days; a pivot older than that is dropped
                                            fractal pivot = a bar whose high (low) is the extreme of the 5 bars
                                              either side
                                            clustering: pivots within 0.5 x ATR14 are ONE level, priced at the mean
                                              of its members; res_touches/sup_touches = count of distinct pivots in it
                                            INVALIDATION: a level the close has since passed through by more than
                                              0.5 x ATR14 is DROPPED — a level price cut clean through is not
                                              resistance any more
                                            dist_res_atr = (nearest surviving level ABOVE close - close)/ATR14
                                            dist_sup_atr = (close - nearest surviving level BELOW)/ATR14
                                            NULL where none survives in the lookback — never 0 (AMD-0021 §2F)
argus/features/risk.py          create  dd126, ulcer63, sharpe63
argus/features/events_feat.py   create  days_to_earnings, days_since_earnings, pead_gap,
                                          days_to_exdiv, days_since_exdiv
                                          (next_div_pct and div_yield_ttm are REMOVED from this Work Order by
                                           AMD-0034 §2C and §2E.4: they read resolved totals from `dividends`,
                                           not `events`, so they depend on WO-0017 merging. They are WO-0020's)
                                           `events` rows are read point-in-time where first_seen/last_seen exist,
                                           and without them where WO-0009 has not yet merged)
argus/features/percentiles.py   create  add_percentiles(df, features) -> df with <f>_pct and <f>_pct_sector
                                          Rank over MEMBERS ON THAT DATE with a published bar, EXCLUDING
                                          flagged symbol-days (bar_flags, AMD-0019 §2A); ties averaged;
                                          scaled 0-100; computed over NON-NULL values only and the
                                          population size recorded per (date, feature)
argus/commands/features_cmds.py create  `features compute --start D [--end D] [--symbols S1,S2]`;
                                          registers onto a new argus.commands.features app; one import line
                                          added to argus/cli.py's append-only block (AMD-0002)
argus/data/schema.py            modify  `features` DDL per DESIGN §3.2 — one column per §5 feature plus one
                                          *_pct and one *_pct_sector each; bump SCHEMA_VERSION to 9
                                          (7 is WO-0009's events migration, 8 is WO-0017's — a migration must
                                          never find the store already at its own target version, or it skips
                                          silently)
tests/fixtures/features/*.parquet  create  the §5 golden fixtures (see §5)
tests/test_features_*.py        create  one module per factor group; see §5
tests/test_percentiles.py       create  see §5
```

## 3. Exclusions
**No nightly pipeline step** (WO-0022) — adding one would collide with
WO-0009's `pipeline.py`. No composites, breadth, RRG, regime or rotation
(WO-0019, WO-0020). No playbooks or lists (WO-0021). No report. No
calibration or threshold tuning of any kind — **every constant stays at
its DESIGN §5 value** and tuning is PID-ARGUS-0004 behind the IC gate
(AMD-0028 §2A). No `adjust.py`, `pipeline.py`, `reconcile.py`,
`providers/*`, `events/earnings.py` or `ops/`. No `docs/` by the
Implementer.

**And explicitly: do not look at the relationship between any feature and
forward returns.** PR-0001 is registered; an unregistered peek inflates
every later result (AMD-0028 §2B.3). This Work Order computes features and
proves the computation. It does not evaluate them.

## 4. Design constraints
PID §8 and ADR-0008. `polars` throughout, **vectorised** — no per-symbol
Python loop over 615 symbols × 2,500 dates. Wilder's smoothing for ADX,
ATR and RSI (not a simple mean). UTC canonical; trading dates are exchange
dates.

**A feature with insufficient history is `NULL`, never `0`**
(AMD-0021 §2F, CI-8). `ret252` on a symbol with 200 bars is NULL;
`z20` where the 20-day standard deviation is zero is NULL, not an infinity
or a zero. **`null_counts` per feature is reported with every run** — a
feature that is 90% NULL is a finding, and a zero substituted for a missing
measurement is indistinguishable from a real zero at the point of reading,
which is the defect AMD-0021 §2F exists to prevent.

**Percentiles are computed over non-NULL values only**, with the
population size recorded per date and feature. A percentile over 40 of 500
members is not comparable with one over 495 and must not be presented as
though it were (CI-8).

## 5. Required tests — and why re-implementation is not a test
For ~70 numerical features, **a test that recomputes the production
formula proves only that the code equals itself** (CI-6). So the proof
comes in three independent forms, and every factor group needs at least one
of the first two:

**(a) Property tests — behaviour that must hold regardless of implementation**
| Test | Property |
|---|---|
| `test_features_trend.py::test_sma_of_constant_series_is_the_constant` | `sma20/50/150/200` of a flat series equal that value |
| `test_features_trend.py::test_clenow_of_perfect_exponential` | an exact exponential gives the known annualised slope and **R² = 1** |
| `test_features_reversion.py::test_rsi_of_monotonic_series` | strictly rising → `rsi14 = 100`; strictly falling → `0` |
| `test_features_volatility.py::test_atr_of_constant_true_range` | constant true range → `atr14` equals it |
| `test_features_volatility.py::test_bb_width_of_constant_series_is_zero` | flat series → `bb_width = 0`, and `z20` is **NULL** not 0 |
| `test_features_momentum.py::test_mom12_1_ignores_the_last_21_days` | perturbing the **last 20 bars** leaves `mom12_1` unchanged — an independent check of the 1-month skip that no formula restatement gives |
| `test_features_momentum.py::test_ret5_on_doubling_series` | a series doubling daily → `ret5 = 2**5 - 1` |
| `test_features_structure.py::test_donchian_on_new_high` | a new 20-day high sets `donchian20_hi = 1` and a bar one tick lower sets 0 |
| `test_features_levels.py::test_level_distances_are_in_atr_not_pct` | doubling the series' volatility while holding the percentage gap constant **halves** `dist_res_atr` (AMD-0023 §2D) |
| `test_features_candles.py::test_marubozu_and_doji_boundaries` | `body_pct` 0.90 → marubozu, 0.89 → not; 0.10 → doji, 0.11 → not |

**(b) Clause-wise falsification for every composite boolean**
`test_features_trend.py::test_trend_template_each_clause_falsified` —
`trend_template` has four clauses; construct a fixture satisfying all four,
then **four variants each breaking exactly one**, and assert each is
`False`. Same shape for `ma_stack` (1 / −1 / 0) and `squeeze`.

**(c) Golden fixtures with independently-derived values**
`tests/fixtures/features/golden_30d.parquet` — 3 symbols × 30 bars, with
the expected values for `sma20`, `rsi14`, `atr14`, `macd_hist` and `z20`
**derived by hand or by an independent reference and committed as a
literal table in the test**, not computed by importing the production
function. The derivation is recorded in `docs/evidence/WO-0018/golden.md`
so an Auditor can check the arithmetic rather than the code.

**(d) Percentiles and NULL discipline**
| Test | Proves |
|---|---|
| `test_percentiles.py::test_ranks_over_members_with_bars_only` | a non-member and a symbol without a bar are absent from the ranking |
| `test_percentiles.py::test_flagged_symbol_day_excluded_from_ranking` | a `bar_flags` row removes that symbol-day from the percentile population and the count reflects it (AMD-0019 §2A) |
| `test_percentiles.py::test_ties_are_averaged` | five equal values all get the same percentile, the mean of their ranks |
| `test_percentiles.py::test_nulls_excluded_and_population_recorded` | NULL features do not rank, and `pct_population.n_non_null` matches |
| `test_percentiles.py::test_sector_percentile_uses_classified_members_only` | an unclassified member is absent from `_pct_sector` and counted (AMD-0016 §2C) |
| `test_features_*.py::test_insufficient_history_is_null_not_zero` | a symbol with 50 bars has `ret252` and `sma200` **NULL**; asserts `is_null`, not `== 0` |

## 6. Acceptance criteria
- **AC1** — `argus features compute` over the full store writes `features` for every (date, symbol) with a published bar; row count reported against `bars`, and any shortfall explained per symbol (operator check).
- **AC2** — **`null_counts` per feature is filed**, with the five most-NULL features named and each explained (short history, insufficient lookback, missing `events` row). A feature NULL for more than 50% of rows is reported as a finding with its cause, not left in the table unremarked.
- **AC3** — `pct_population` is filed: per date, the number of non-NULL values ranked against `n_members`. Dates where the ranked population is below 95% of members are **listed** (CI-8, DESIGN §6.1).
- **AC4** — Every §5 feature in DESIGN appears as a column, with its `_pct` and `_pct_sector`. **A diff of the §5 table against the delivered column list is filed**, and it is empty in both directions — nothing missing, nothing invented.
- **AC5** — All §5 tests pass offline with no network and no `.env`. The golden-fixture derivation is filed in `golden.md` and is checkable by arithmetic.
- **AC6** — **Wall time measured and reported**, not bounded in advance: full-history recompute and single-date incremental, both on the host, with the row counts. If the full run exceeds 30 minutes, say so and name the slowest factor group — a figure the Architect can act on rather than a target to be gamed.
- **AC7** — Idempotency: a second run over the same range changes no row (operator check: checksum of `features` before and after).
- **AC8** — `bars`, `bars_raw`, `etf_bars`, `membership`, `splits`, `dividends` and `events` are **byte-identical** before and after (checksum, CI-9). This Work Order reads them and writes only `features`.
- **AC9** — Non-vacuity, mandatory (CI-6): file four mutation runs, each failing the intended test — (a) replacing Wilder smoothing with a simple mean fails the RSI and ATR property tests; (b) dropping the 1-month skip from `mom12_1` fails `test_mom12_1_ignores_the_last_21_days`; (c) substituting `0` for a NULL on insufficient history fails `test_insufficient_history_is_null_not_zero`; (d) ranking flagged symbol-days fails `test_flagged_symbol_day_excluded_from_ranking`.
- **AC10** — (AMD-0034 §2E.1, the first-audit RED's F2) **Every constant and lag mutant must fail a test.** Run the full constant/lag mutation set and report the **surviving count, which must be 0**. The nine features the first audit found unpinned each need a boundary or golden test fixing their constant: the `slope*` lags, `clenow90`'s window, `dist20_atr`'s sign, `atr_pct`'s denominator, `dist_days25`'s threshold, `trend_template`'s 0.75, the `rs_rank` weights, the Keltner multiplier. A test that cannot detect a changed constant does not pin it, which is the whole of CI-6 and the reason §5 exists.
- **AC11** — (AMD-0034 §2E.2, F4) `macd_hist` is **NULL** until the signal line has 9 values; no artificial `0.0` reaches a percentile population (test: the first valid bar asserts `is_null`, not `== 0`).
- **AC12** — (AMD-0034 §2B) The four swing-level features are delivered, with a test that **a level the close has cut through by more than 0.5 ATR is dropped**, and `dist_res_atr`/`dist_sup_atr` are NULL where no level survives the lookback.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC3, AC6–AC8), `golden.md` (AC5), the §5 column
diff (AC4), and the AC9 mutation runs.

## 8. Implementer notes
This is the largest Work Order in the project and the one everything
downstream reads, so the risk is not any single formula — it is **seventy
formulas each plausibly slightly wrong**, in a way no amount of
re-implementing the spec in a test would catch. §5(a)–(c) exist for exactly
that: a property holds or it does not, independently of how the feature is
written.

Two traps worth naming. **Wilder's smoothing is not a simple moving
average** — ADX, ATR and RSI all use it, and a simple mean gives
plausible-looking numbers that are wrong everywhere. And **NULL is not
zero**: with 252-day lookbacks over ten years, early dates and recent
listings are legitimately NULL in bulk, and a zero there poisons every
percentile that date computes. The project has already been bitten by a
coverage field hard-coded to zero (AMD-0021 §2F); this is the same failure
with seventy chances to occur.

Report a feature you cannot compute faithfully from DESIGN §5 rather than
approximating it. An approximation that looks reasonable is worse than a
gap, because the gap gets fixed.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
