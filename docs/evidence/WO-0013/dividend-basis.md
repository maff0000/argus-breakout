# WO-0013 — Dividend basis, measured (AMD-0019 §2B)

**Conclusion: Polygon stores `as_paid` amounts; yfinance stores `split_adjusted` amounts.** Measured by the Delivery Controller on stored data (WO-0007 scratch store), no network call.

## Method
`dividends` holds both sources for 2024-01-02 onwards (Polygon 5,448 rows; yfinance 20,843 rows from 2015). For every (symbol, ex-date) stored by **both** sources, compute the ratio Polygon/yfinance and compare it with the cumulative ratio of splits dated **after** that ex-date (yfinance splits table). If a source were split-adjusted and the other as-paid, the ratio equals the cumulative later-split ratio.

## Result
| Population | n | Ratio equals cumulative later-split ratio (±3%) |
|---|---|---|
| Pairs with a later split | 199 | **198** |
| Pairs with no later split | 4,915 | Polygon = yfinance in **4,876** |
| All pairs | 5,114 | consistent in 5,074 |

The 40 misfits are not basis differences: they are pairs where the vendors disagree on the amount itself (variable or special dividends — for example F 2025-02-18 0.15 vs 0.30, FCX 0.075 vs 0.15, COP 2024-08-12 0.20 vs 0.78); none has a later split.

## Worked comparisons against the declared amount
- **AAPL** (4:1 split 2020-08-31): yfinance holds 0.1925 on 2020-02-07 and 0.205 on 2020-05-08, 2020-08-07, 2020-11-06. The declared amounts were $0.77 and $0.82; 0.77/4 = 0.1925 and 0.82/4 = 0.205 → **yfinance = split_adjusted**.
- **APH** (2:1 splits 2024-06-12 and 2026-09-03): Polygon holds 0.22 on 2024-03-18 (the declared quarterly dividend of $0.22) and yfinance 0.055 (= 0.22/4) → **Polygon = as_paid, yfinance = split_adjusted**.
- **AMCR** (1-for-5 reverse split, ratio 0.2): Polygon 0.125 vs yfinance 0.625 on the same ex-dates → the same relation in the other direction.

## Consequences
- Mapping encoded once, `DIVIDEND_BASIS_BY_SOURCE` in `argus/data/store.py`, used by the write path and the migration; an unknown source raises.
- Before the correction, Polygon dividends dated before a later split were used undivided, so a 2:1 later split overstated the dividend factor 2× (AMD-0019 §1(b)). The yfinance dividends, the bulk of history, were already on the price basis. The counts are reproducible with a self-join of `dividends` on (symbol, date) across the two sources against the stored `splits`.
