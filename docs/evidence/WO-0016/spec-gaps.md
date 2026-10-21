# WO-0016 spec gaps for the Architect
1. Scope extensions to ratify: argus/data/store.py (the migration lives there, not in store_cmds.py), argus/data/ingest_bootstrap.py, and fixture/column edits in tests/test_diagnostics.py, test_ingest_polygon.py, test_store.py and beyond-count edits in test_schema.py. Audited as necessary and minimal.
2. Two unattributed 2D hits for review: SKYD 2026-09-15 (0.05 vs 0.10, yfinance taken) and TEL 2024-11-22 (1.30 vs 0.65, Polygon taken). Neither was among the thirteen, so neither was fetched raw.
3. FCX has 12 omission ex-dates; the rule resolves them, but the underlying Polygon gap (a second 0.075 component) remains upstream.
4. The change to test_dividend_disagreement_normalises_basis (DIFF 0.50 vs 0.52 now takes the larger total) is the intended consequence of AMD-0027 2D; noted for the record.
5. Chosen migration option: section 8 option 1 as a placeholder plus option 2 (real re-ingest) executed here. A production store created after this WO bootstraps at schema 6 directly and never holds a legacy row.
