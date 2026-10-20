# WO-0003 — Specification gaps and rulings

1. **Renamed tickers fall through AMD-0013 §2C route (c).** Additions are derived only for `Date added > H`; a current member added before H but listed under a different ticker in hanshof@H gets no row (5 live: BNY, FISV, MRSH, SKYD, VMRK), and the predecessor ticker is recorded as a bounded removal. `members_on(today)` is 498 vs 503. Auditor finding 1; the code follows the spec literally. **Needs an Architect decision** (accept as residual; or a rename-aware rule, e.g. give such members a bounded start at H+1 — which would raise the bounded count to ~38, still under the ceiling of 40 — or report a "current members without a membership row" count).
2. `tickers.normalize(..., "hanshof")` uses "." but the real hanshof file uses "-" (worked around by normalising as "yfinance"); carried from the first audit.
3. Implementer-noted: `RateLimiter` burst behaviour; `cli.py` never calls `configure_logging`; `test_budget_enforced` takes ~15 s.
4. Unpinned optimisation: stop calling `profile` after the first 402 (Auditor M5) — harmless.
5. `MAX_BOUNDED_ROWS` stop is applied after membership is written (Auditor O2).
6. AMD-0013 §2C(b) detector is fixture-only; the live page currently has no changes table.
