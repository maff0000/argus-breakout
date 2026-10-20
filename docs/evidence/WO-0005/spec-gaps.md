# WO-0005 — Spec gaps and residuals (for the Architect)

1. **AC1 is unattainable as worded** (83.2% vs 98%; all 127 failures are delisted/renamed historical members yfinance cannot serve). See `operator-checks.md`. Needs a ruling on the denominator or a second source.
2. **Rename series.** yfinance serves BK/FI/MMC history only under BNY/FISV/MRSH; for EQR/PSKY it returned rows (aliased). The price series for a renamed company is therefore split across tickers or aliased, which matters for features that look back across a rename (AMD-0014 §2A). A bars-layer alias rule is a design item for P0-D.
3. **Two downloads per chunk** (`daily_bars` and `actions` each call `yf.download`): matches §2, wasteful.
4. **Unpinned:** the 0.95 resume threshold value; `>=` vs `>` at the boundary is an equivalent mutant.
5. **ruff format drift** (7 files, 2 added here) — gate is `ruff check`.
6. **AMD-0014 §2E confirmation:** the implementation did not count skips before `2c5a8a2`; fixed with tests (see `audit.md`).
