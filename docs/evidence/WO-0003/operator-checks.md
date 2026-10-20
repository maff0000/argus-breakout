# WO-0003 — Operator checks

Run by the Delivery Controller on dell-debian. FMP key taken from the git-ignored `.env` via a filtered read; never printed. Scratch stores only.

## A. AC1/AC2/AC4/AC6/AC7/AC8 at head `22a3ad1721117690e2b3a3c9c2d6eff274b973c5` (code identical to the audited tree)
Run `real` = real FMP key, live network. Run `force402` = same code with every FMP request answered HTTP 402 by a transport shim (Wikipedia and hanshof live). **Disclosure:** on this plan the real key already returns 402 for `sp500-constituent` and `historical-sp500-constituent`, so the two runs exercise the same path and agree exactly; `profile` was never needed because every member mapped from the constituents table.
```
22a3ad1721117690e2b3a3c9c2d6eff274b973c5
2026-10-20 08:52:49 [warning  ] fmp_unavailable                path=sp500-constituent status=402
2026-10-20 08:52:49 [warning  ] fmp_current_unavailable        error='fmp sp500-constituent unavailable on this plan (status 402)'
2026-10-20 08:52:54 [warning  ] fmp_unavailable                path=historical-sp500-constituent status=402
2026-10-20 08:52:54 [warning  ] fmp_changes_unavailable        error='fmp historical-sp500-constituent unavailable on this plan (status 402)'
===== RUN real (force402=False)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'wikipedia-derived-bounded': 33, 'wikipedia-derived-exact': 28}
n_symbols: 518 n_members_today: 498 n_missing_group: 0 membership_rows: 746
FMP calls: 2 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1}
AC1 sql missing-group count: 0 | ETFs: 15 | non-ETF: 503
AC4 invalid tickers in symbols: 0
2026-10-20 08:52:56 [warning  ] fmp_unavailable                path=sp500-constituent status=402
2026-10-20 08:52:56 [warning  ] fmp_current_unavailable        error='fmp sp500-constituent unavailable on this plan (status 402)'
2026-10-20 08:53:01 [warning  ] fmp_unavailable                path=historical-sp500-constituent status=402
2026-10-20 08:53:01 [warning  ] fmp_changes_unavailable        error='fmp historical-sp500-constituent unavailable on this plan (status 402)'
===== RUN force402 (force402=True)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'wikipedia-derived-bounded': 33, 'wikipedia-derived-exact': 28}
n_symbols: 518 n_members_today: 498 n_missing_group: 0 membership_rows: 746
FMP calls: 2 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1}
AC1 sql missing-group count: 0 | ETFs: 15 | non-ETF: 503
AC4 invalid tickers in symbols: 0
===== AC2 (run A store): members_on vs hanshof snapshot
2016-06-30: members_on=479 hanshof(2016-06-27)=479 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2020-03-31: members_on=499 hanshof(2020-03-03)=499 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2024-12-31: members_on=503 hanshof(2024-12-31)=503 symmetric_diff=0 only_members_on=[] only_hanshof=[]
H (hanshof last snapshot): 2025-08-23
===== Run A vs B: same route and counts? True True
bounded rows A: 33 (ceiling 40)
wall=19.94s
```
Reading: AC1 — 0 symbols without an industry group (503 non-ETF + 15 ETFs). AC2 — `members_on` equals the hanshof snapshot (symmetric difference 0) on 2016-06-30, 2020-03-31, 2024-12-31. AC4 — 0 invalid tickers. AC6 — 2 FMP calls per refresh (<= 60); both the real-key run and the forced-402 run complete successfully. AC7 — gap route `wikipedia-derived`; rows by source hanshof=685, wikipedia-derived-exact=28, wikipedia-derived-bounded=33 (ceiling 40). AC8 — covered by tests and by both runs.

**Unreported by the spec — current members with no membership row (Auditor finding 1):** `members_on(2026-10-20)` = 498 against 503 current non-ETF symbols. The missing five are BNY, FISV, MRSH, SKYD, VMRK (Date added 1995/2001/1987/1994/2001; absent from hanshof@H under these tickers; FISV has a hanshof interval ending 2023-06-07). Likely ticker renames; their predecessors count among the 33 bounded removals.

## B. Real-code seed for the WO-0004/WO-0005 live checks (no scaffold)
Head `465b8f3` (= audited code + clerical merge of main):
```
WO-0003 head 465b8f3559ef47ae82dd659d998470183c1edda1
$ argus universe refresh
symbols: 518
members on 2026-10-20: 498
missing industry group: 0
membership rows: 746
sources: wikipedia, hanshof, wikipedia:derived
membership gap route: wikipedia-derived
rows by source: hanshof=685, wikipedia-derived-bounded=33, wikipedia-derived-exact=28
rc=0
SEED_DONE
```
