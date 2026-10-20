# WO-0005 — Spec gaps and residuals (for the Architect)

1. **Resume floor** is relative to the requested range, so late-listed symbols are re-downloaded every run (see `spec-defects.md` #2). A per-symbol floor based on the first available bar would be a spec change.
2. **Rename series.** yfinance serves BK/FI/MMC history only under BNY/FISV/MRSH (those three are in `delisted-coverage.md`). The rename-aware bars lookup (AMD-0016 §2D) lives in WO-0007.
3. **Two downloads per chunk** (`daily_bars` and `actions` each call `yf.download`): matches §2, wasteful.
4. **Store relocation.** The Parquet views in the DuckDB file carry the absolute glob of the directory they were created in; a copied/relocated store reads the old directory until `init_schema()` is re-run. Matters for ADR-0008 (container readiness) — worth a note on `init-store`/Store.
5. **`--symbols` typo** exits 0 (filed as historical) by design; a stricter mode would be a behaviour change.
6. **Pre-existing:** `ruff format --check` drift in files this branch did not touch; the gate is `ruff check`.
