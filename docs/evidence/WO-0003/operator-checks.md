# WO-0003 — Operator checks (final head `6896fe7`; earlier live run at `8530a79`)

Run by the Delivery Controller on the execution host, live network, real FMP key used but never printed. Status codes only.

## Run at the final head `6896fe7`, 2026-10-20 (after the pass-6 GREEN)
FMP returned **429 on the profile calls** during this run (the day's FMP allowance had been spent by earlier verification runs on the same key; a status-code probe afterwards
returned 429 for every endpoint). The consequences are disclosed in `spec-defects.md`: the call count (96 attempts: 28 × 200, 66 × 429 retried three times each, 2 × 402) exceeds AC6's ≤ 60,
`n_unclassified` is 229 instead of 224, and the closing "today" CLI run exited 1 on 429 at the FMP changes endpoint. Everything not dependent on FMP profile availability is unchanged from the earlier run.
```
host=dell-debian head=6896fe7b3ca156bf64d633aa11eca4cbad796073
##### OPCHK (real key, then forced 402, then AC2 vs hanshof)
===== RUN real (force402=False)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
AMD-0016: symbols rows: 755 | historical-only (active=false): 237 | n_unclassified: 229 | every membership symbol has a symbols row: True
n_symbols: 755 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 96 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1, 'profile:200': 28, 'profile:429': 66}
AC1 (current+ETF, active) missing-group count: 0 | ETFs: 15 | non-ETF active: 503
AC4 invalid tickers in symbols: 0
===== RUN force402 (force402=True)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
AMD-0016: symbols rows: 755 | historical-only (active=false): 237 | n_unclassified: 232 | every membership symbol has a symbols row: True
n_symbols: 755 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 3 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1, 'profile:402': 1}
AC1 (current+ETF, active) missing-group count: 0 | ETFs: 15 | non-ETF active: 503
AC4 invalid tickers in symbols: 0
===== AC2 (run A store): members_on vs hanshof snapshot
2016-06-30: members_on=479 hanshof(2016-06-27)=479 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2020-03-31: members_on=499 hanshof(2020-03-03)=499 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2024-12-31: members_on=503 hanshof(2024-12-31)=503 symmetric_diff=0 only_members_on=[] only_hanshof=[]
H (hanshof last snapshot): 2025-08-23
===== Run A vs B: same route and counts? True True
bounded rows A: 28 (ceiling 40)
##### AC10 via the CLI
before: symbols=755 membership=751 ingest_log=53
universe refresh refused: --date 2026-09-20 is more than 7 days before 2026-10-20: the current constituents table has no historical snapshot, so a back-dated refresh cannot be correct
universe refresh --date 2026-09-20 (30 days ago): exit=2
after:  symbols=755 membership=751 ingest_log=53
--date 2026-10-12 (8 days ago): exit=2
after:  symbols=755 membership=751 ingest_log=53
--- today (real key)
universe refresh failed: fmp historical-sp500-constituent failed after 3 attempts (status 429)
universe refresh (today): exit=1
after:  symbols=755 membership=751 ingest_log=60
```

## Run at `8530a79` (pre-delta; the FMP allowance was available)
Same script. Real key: 52 FMP calls (2 × 402 + 50 profile, all 200); forced 402: 3 calls; AC10 on the CLI: `--date` 30 days back exit 2, 8 days back exit 2, store counts unchanged;
today and the last trading day (2026-10-19) exit 0. `n_unclassified` 224 (real key), 232 (forced 402).
```
host=dell-debian head=8530a79ccac6384c70825ca3b20fdf82c67e91c5
##### OPCHK (real key, then forced 402, then AC2 vs hanshof)
===== RUN real (force402=False)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
AMD-0016: symbols rows: 755 | historical-only (active=false): 237 | n_unclassified: 224 | every membership symbol has a symbols row: True
n_symbols: 755 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 52 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1, 'profile:200': 50}
AC1 (current+ETF, active) missing-group count: 0 | ETFs: 15 | non-ETF active: 503
AC4 invalid tickers in symbols: 0
===== RUN force402 (force402=True)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
AMD-0016: symbols rows: 755 | historical-only (active=false): 237 | n_unclassified: 232 | every membership symbol has a symbols row: True
n_symbols: 755 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 3 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1, 'profile:402': 1}
AC1 (current+ETF, active) missing-group count: 0 | ETFs: 15 | non-ETF active: 503
AC4 invalid tickers in symbols: 0
===== AC2 (run A store): members_on vs hanshof snapshot
2016-06-30: members_on=479 hanshof(2016-06-27)=479 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2020-03-31: members_on=499 hanshof(2020-03-03)=499 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2024-12-31: members_on=503 hanshof(2024-12-31)=503 symmetric_diff=0 only_members_on=[] only_hanshof=[]
H (hanshof last snapshot): 2025-08-23
===== Run A vs B: same route and counts? True True
bounded rows A: 28 (ceiling 40)
##### AC10 via the CLI
before: symbols=755 membership=751 ingest_log=53
universe refresh refused: --date 2026-09-20 is more than 7 days before 2026-10-20: the current constituents table has no historical snapshot, so a back-dated refresh cannot be correct
universe refresh --date 2026-09-20 (30 days ago): exit=2
after:  symbols=755 membership=751 ingest_log=53
--date 2026-10-12 (8 days ago): exit=2
after:  symbols=755 membership=751 ingest_log=53
--- today (real key)
symbols: 755
members on 2026-10-20: 503
current table symbols: 503
current members without row: 0
missing industry group: 0
unclassified historical symbols: 224
universe refresh (today): exit=0
after:  symbols=755 membership=751 ingest_log=106
symbols: 755
members on 2026-10-19: 503
current table symbols: 503
current members without row: 0
missing industry group: 0
unclassified historical symbols: 224
membership rows: 751
sources: wikipedia, hanshof, wikipedia:derived, fmp:profile
universe refresh --date 2026-10-19 (last trading day): exit=0
```
