# WO-0014 — Operator checks

Run by the Delivery Controller on `dell-debian` at the audited head `6236748`, on a **copy** of the post-WO-0013 scratch store (`bars` 1,590,784 rows, schema 5). `init-store` (read-write connect, repairs the copied store's views) then `argus adjust materialise`, the latter under `unshare -rn` (no network namespace): **network calls = 0, structurally**. No `.env`, no provider code. No host, port or key appears below.

## AC6 — `bars_raw` byte-identical, no provider call
Checksum (sha256 of sorted parquet checksums) before **2d97299e07ceab09**, after **2d97299e07ceab09**. Re-run of materialise: `rows=0` (no-op). **AC6 met.**

## AC1 — same-company tails retained
`bars` 1,590,784 → **1,700,331** (+109,547); `etf_bars` unchanged at 43,426. Bars excluded as post-exit tails: **118,027 → 8,480**, i.e. **109,547 recovered** (the +109,547 above). AAL, AAP, ALK, M and WHR now run to 2026-10-19 (2,966 bars each); K's series ends 2025-12-10 (286 bars; the data stop there). 22 symbols remain excluded, each with its gap in trading days (list under AC2). `n_readjusted` 65. **AC1 met.**

## AC2 — boundary warnings: counters, names, gaps, reasons
`n_bars_before_first_membership` = 285,663 (counted, never warned). `n_bars_after_final_end_without_continuity` = 8,480 across **22 symbols, each warned and named with its gap** (WO-0013: 121 symbols). The last bar on or before each symbol's final membership end is **absent from `bars_raw` for all 22** (the store holds no pre-exit history for former members that were never bootstrapped), so the gap runs from the end date to the first stored bar after it. That makes the reason checkable from the first-bar-after date:

| Reading | Symbols (final_end → first bar after; gap in trading days) |
|---|---|
| **Reassigned or a different entity** — first bar years after the exit, or a later listing | APC (2019-08-08 → 2026-02-12; 1636) · BBBY (2017-07-25 → 2025-08-29; 2035) · CAM (2016-04-01 → 2025-10-06; 2391) · CSRA (2018-04-03 → 2026-08-12; 2100) · FB (2022-06-08 → 2025-06-26; 763) · NFX (2019-02-14 → 2026-07-07; 1855) · SPLS (2017-09-12 → 2026-01-16; 2097) · STI (2019-12-06 → 2022-05-02; 603) · TE (2016-06-30 → 2020-01-10; 887) · LB (2021-08-02 → 2024-06-28; 730) · INFO (2022-03-01 → 2024-10-10; 656) · SBNY (2023-03-14 → 2024-08-15; 357) |
| **Not discriminable** — the only stored bars are Polygon-era (first bar after = 2024-10-21, the first Polygon day) and nothing lies between the exit and that date, so a same-company exit and a reassignment look identical | CA (1497) · CMA (83) · FL (1308) · HBI (712) · JWN (1090) · LEG (712) · PDCO (1659) · SEE (211) · SRCL (1479) · TGNA (1858) |

For the second group the tail is excluded and warned, as the rule says; whether it is the same company cannot be told from `bars_raw`. These are non-members, so the exclusion costs no feature input today (`spec-gaps.md` 1). **AC2 met, with the second group disclosed as a limit of the stored history.**

## AC3 — no non-`ok` day publishes
Join of `bars` dates against the latest Polygon `ingest_log` status per day: `ok` 301,573 rows, **no other status present**; rows on a date with a non-`ok` verdict that also have a Polygon raw row: **0**. Days with no Polygon verdict (yfinance-bootstrap history) still publish, as WO-0007 intended. **AC3 met.**

## AC4 — `dividend_disagreement`
**228 → 40 warnings, 42 → 11 symbols** (CME, COP, DVN, EXE, F, FANG, FCX, HP, HST, PGR, WRB). Every remaining one is a **genuine amount difference between vendors**, none a basis artefact: normalised and stored amounts agree in each (no split intervenes), and they show the pattern of one vendor reporting a single combined amount where the other reports the regular amount alone — FCX 0.075 vs 0.15 on every quarter; PGR 0.10 vs 4.60 (2025-01-10) and 13.60 (2026-01-02); WRB 0.08 vs 0.33/0.58/1.09; DVN, FANG, COP variable dividends; CME annual variable 1.30 vs 7.45. Full list: the 40 lines of the materialise report (`ingest_log.detail`). The cause of the pattern (a Polygon row per (symbol, date) keeping only one of several same-date records) is a hypothesis, not established here; see `spec-gaps.md` 2. **AC4 met as worded.**

## AC5 — `n_symbol_days_flag_excluded`
`materialise` reports `None`; the CLI prints `0 quarantined days not published, flagged symbol-days excluded: not computed`. Test `test_flag_excluded_count_is_never_a_silent_zero` asserts both `None` and the printed text. **AC5 met.**

## Other figures
Warnings by kind: `source_disagreement` 3,136 (a WO-0007 kind, unchanged in meaning; it grew from 2,832 because 109,547 more post-exit bars now overlap two sources), `bars_after_final_end_without_continuity` 22, `no_bars` 22, `dividend_disagreement` 40.
