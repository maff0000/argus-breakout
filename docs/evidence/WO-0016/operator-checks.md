# WO-0016 operator checks (AC2-AC5)
Run on a scratch copy of the WO-0014 re-materialised store, migrated to schema 6 with argus migrate-store, then argus ingest polygon-actions --since 2024-01-01 (WO section 8 option 2: re-ingest, not a legacy backfill; 555 paged Polygon requests, about 110 minutes at the 5 per minute limit), then adjust materialise. Key never printed.

## Migration and re-ingest
- migrate-store: counts printed per table, none changed; 5448 Polygon dividend rows held the placeholder vendor_id legacy.
- polygon-actions: 46 splits and 5482 dividend rows upserted; legacy_superseded=5448; after: polygon 5482 rows, 0 legacy; yfinance 20843 rows (vendor_id sum). Net +34 dividend records that the old key had silently dropped.

## AC2 — collapse pairs: all records persist, summed total within one cent of yfinance (before -> after, polygon records and sum)
CME 2026-03-10 1/1.30 -> 2/7.45 (yf 7.45); COP 2024-08-12 1/0.20 -> 2/0.78 (0.78); DVN 2024-06-14 1/0.13 -> 2/0.35 (0.35); EXE 2024-05-15 1/0.14 -> 2/0.715 (0.715); FANG 2024-05-14 1/0.90 -> 2/1.97 (1.97); FANG 2024-08-15 1/0.90 -> 2/2.34 (2.34); HP 2024-02-12 1/0.17 -> 2/0.42 (0.42); HP 2024-05-16 1/0.17 -> 2/0.42 (0.42); PGR 2025-01-10 1/0.10 -> 2/4.60 (4.60); PGR 2026-01-02 1/0.10 -> 2/13.60 (13.60); WRB 2024-09-23 1/0.08 -> 2/0.33 (0.33); WRB 2024-12-16 1/0.08 -> 2/0.58 (0.58); WRB 2025-12-15 1/0.09 -> 2/1.09 (1.09). 13 of 13 within one cent.

## AC3 — omission list (rule 2D, larger normalised total wins, total_source recorded, warning filed)
Re-materialise gives 14 dividend_disagreement warnings, all with total_source:
- FCX, 12 ex-dates 2024-01-11 to 2026-10-15: polygon 0.0750, yfinance 0.1500; total_source=yfinance (the Polygon completeness gap established by WO-0015).
- SKYD 2026-09-15: polygon 0.0500, yfinance 0.1000; total_source=yfinance. NOT attributed raw (not one of the 13); a symbol that was redirected from PSKY. Flag for the Architect.
- TEL 2024-11-22: polygon 1.3000, yfinance 0.6500; total_source=polygon (the larger). Here the rule picked Polygon because it is larger; the reason the two disagree 2:1 is not established. Flag for the Architect.

## AC4 — adj_close before and after (pre-ex dates move down because more dividend is removed)
PGR 2024-10-28 243.4703 -> 224.7974 (-7.669%); 2025-06-02 287.9681 -> 270.8889 (-5.931%, matching the 5.93% WO-0015 measured); 2026-10-19 unchanged (219.11).
CME -1.935% (both pre-ex dates), EXE -0.602%, WRB -2.523% / -1.713%, FCX -1.214% / -0.804%, SKYD -0.462%, TEL -0.434% on 2024-10-28.
Pairs whose collapse predates the first Polygon bar (COP, DVN, EXE, FANG, HP, WRB) show on bootstrap-era dates: COP -0.717%/-0.535%, DVN -1.494%/-1.032%, EXE -1.232%/-0.602%, FANG -1.753%/-0.736%, HP -1.795%/-0.494%, WRB -3.093%/-3.093% (2024-01-02 / 2024-06-03). All latest-date adj_close values are unchanged, as they must be (nothing after them).

## AC5
- SCHEMA_VERSION 6. bars_raw: 2,055,196 rows, checksum 18944650581957857753416230 before and after (identical, CI-9). Rows: splits 253 -> 253, membership 751 -> 751, bars 1700331 -> 1700331, symbols 755 -> 755, dividends 26291 -> 26325 (+34). Migration idempotent (tested; a second materialise wrote 0 rows).
