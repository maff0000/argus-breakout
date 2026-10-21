# WO-0004 — Spec gaps and residuals (for the Architect)

1. **Scope ratification (Auditor finding 1).** `tests/test_schema.py` and `tests/test_cli.py` are not in WO §2 (which is "exhaustive"). Their edits (19→20 tables, `bar_flags` in DESIGN_TABLES, SCHEMA_VERSION 2→3, "20 tables") are the mechanical consequence of the §2 `bar_flags` DDL and version bump. Ratify, please.
2. **Same-date split+dividend** is not demonstrable on Polygon data (0 pairs; 0 `jump_split_reconciled` flags either); proven by unit tests and WO-0005's yfinance pairs (ratified, AMD-0016 §2E).
3. **Grouped-daily for "today"** is not published when the range ends today; AC ranges end at the last trading day (used here).
4. **Unpinned guards:** `ratio <> 1` filter and the `.unique` dedupe in the actions path.
5. **CLI exit codes:** quarantined days exit 0, `failed` exits 1 (the WO is silent); the nightly pipeline (WO-0009) must read the per-day verdicts, not the exit code, to surface quarantines.
6. **`_judge` failure after `bars_raw` write** logs the day `failed` although the rows are stored (idempotent re-fetch; status slightly misleading).
7. **Breadth rule is untested against a real market-wide shock day.** In 499 live days no day exceeded 0.42% member flags, so the 20% threshold is exercised by unit tests only (boundary pinned exactly). The threshold remains a named constant, as AMD-0018 §2C intends.
8. **Price series across renames and ticker reassignment** (STI, AIV, NKTR flags are non-member rows from reassigned or delisted tickers): bars bounded by listing life and rename-aware lookup are WO-0007 (AMD-0018 §2F).
9. **`ruff format --check`** would reformat 17 files (CI runs `ruff check` only; not a gate).
