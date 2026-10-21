# WO-0013 — Operator checks

Run by the Delivery Controller on `dell-debian` at the audited head `df4b52d`, on a **copy** of the WO-0007 scratch store (`bars_raw` 2,055,196 rows, schema 4). `migrate-store` and `adjust materialise` ran under `unshare -rn` (no network namespace): **network calls = 0, structurally**. No `.env`, no provider client. No host, port or key appears below.

## AC7 — migration on a copy, idempotent, `bars_raw` byte-identical
```
bars_raw checksum (sha256 of sorted parquet checksums) before: 2d97299e07ceab09
migrate-store #1: store relocated: repaired views; migrated to schema 5
  bar_flags 128->128  bars 1590779->1590779  bars_raw 2055196->2055196  dividends 26291->26291
  etf_bars 43426->43426  ingest_log 1136->1136  membership 751->751  splits 253->253  symbols 755->755
  store_meta 1->1  (empty tables unchanged)   schema_version 3->4 (rows of the version table)
bars_raw checksum after #1: 2d97299e07ceab09
migrate-store #2: every table before == after; schema_version 4->4
bars_raw checksum after #2: 2d97299e07ceab09
```
SCHEMA_VERSION is 5. **AC7 met.**

## AC2 — `dividends.basis`
`polygon / as_paid: 5,448` · `yfinance / split_adjusted: 20,843` · **nulls: 0**. The basis each source stores is established in `dividend-basis.md`. **AC2 met.**

## AC1 — re-materialisation publishes the previously withheld flagged symbol-days, no provider call
`argus adjust materialise` (28 s, no network): `symbols=652 rows=197166 readjusted=73 warnings=3203`; `0 quarantined days not published, 0 flagged symbol-days excluded`. Re-run: `rows=0 readjusted=0` (no-op).
- `bars` 1,590,779 → **1,590,784** (+5 rows); `etf_bars` 43,426 → 43,426. `adj_version` 2 on 181,304 rows (73 symbols re-adjusted, CI-5).
- Flagged symbol-days (128 `jump_unexplained` rows, all Polygon): **56 now published** (was 51, all via yfinance substitution). **All 41 flags on a member on that day are published and carry their flag.** The other 87: 25 symbols that never entered the published universe, 47 on days after the symbol's final membership end (AMD-0018 §2F, no continuity), and 15 published (before first membership or with continuity).
- No cross-source substitution remains: every previously substituted day now carries Polygon's row.
**AC1 met.**

## AC3 — `adj_close` change on a symbol with a split and dividends on both sides
APH (2:1 splits 2024-06-12 and 2026-09-03; Polygon `as_paid` dividends before both):
| date | close | adj_close before | adj_close after | adj/close before → after |
|---|---|---|---|---|
| 2024-01-02 | 24.2075 | 23.1479 | 23.7019 | 0.9562 → 0.9791 |
| 2024-06-28 | 33.6850 | 32.5756 | 33.1006 | 0.9671 → 0.9827 |
| 2025-12-31 | 67.5700 | 66.9968 | 67.2309 | 0.9915 → 0.9950 |
The dividend adjustment shrinks by roughly the later-split factor, as AMD-0019 §1(b) predicts (the 2024-01-02 adjustment falls from 4.4% to 2.1%). **AC3 met.**

## AC4 — DOUBLE, and WO-0007 AC2 re-measured
`typeof(open, close, adj_close, volume)` = DOUBLE for `bars`; `etf_bars` close/adj_close DOUBLE.
- 20-symbol sample (seeded, symbols with a published bar on a Polygon day, close on the symbol's last such day): **20 of 20 identical** (WO-0007: 17 of 20 as originally worded).
- Population: Polygon rows 312,025 → **263,961 identical, 0 different** (WO-0007: 48 different at 5.1e-8), **48,064 not published** (WO-0007: 48,069): 5,891 for symbols never in the published universe and 42,173 after a symbol's final membership end (AMD-0018 §2F). The float32 differences came from the yfinance substitution that no longer exists. **AC4 met.**

## AC5 — warning channel
- `n_bars_before_first_membership` = 285,663 (counted, never warned); `n_bars_after_final_end_without_continuity` = 118,027 bars across **121 symbols, each warned and named** (list below) — against WO-0007's 3,403 `bars_outside_membership` warnings.
- Total warnings in the report are 3,203, of which 2,832 are `source_disagreement` (a WO-0007 kind, unchanged by this WO; e.g. BDX around a restatement), 228 `dividend_disagreement` (42 symbols; **new noise**: the two sources are now on different bases, so the comparison needs the split factor — see `spec-gaps.md`), 22 `no_bars`, and the 121 boundary warnings.
- The 121: AAL AAP AIV ALK AMG AMTM AN APC ATI AVB AYI BBBY BBT BBWI BHF BIO BLDR BWA CA CAG CAM CE CMA CNX COTY CPB CPRI CSRA CTRA CTVA CZR DAY DXC EA EMN ENPH EPAM ETSY FB FCPT FL FLR FLS FMC FTI GME GNW GT HBI HOG HOLX HP HRB INFO IPG IPGP JEF JWN K KMX KSS LB LEG LKQ LNC LUMN LW M MAC MAT MHK MKTX MOH MTCH MUR NAVI NBR NFX NKTR NOV NWL OGN OI PARA PAYC PBI PDCO PENN POOL PRGO PVH QRVO R RHI RRC SBNY SEDG SEE SLG SPLS STI TAP TDC TE TFX TGNA THC TRIP TTD UA UAA UNM VFC VNO VNT WBD WHR WU XRAY XRX ZION.
**AC5 met for the membership-boundary channel; total warnings remain high for reasons recorded in `spec-gaps.md`.**

## AC6, AC8
`logging.md` filed; AC8 mutation runs are in `audit.md` (Auditor) and the Implementer's report (a: 3 tests failed, b: 1 failed, plus float32 and quarantine mutants).
