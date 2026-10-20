# WO-0003 — Operator checks (final head `4c10c60`)

Run by the Delivery Controller on the execution host against the final head, live network. The FMP key is used but never printed. Both FMP endpoints
for membership return 402 on this plan, so the "real key" run and the forced-402 run take the same route (disclosed in earlier passes; AMD-0013).
The run script is the same as pass 1 plus AC9 / AC2-second-half / rename-row prints.

```
host=dell-debian head=4c10c6036f0d408a8eb411701364bf4818617e97
===== RUN real (force402=False)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
n_symbols: 518 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 2 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1}
AC1 sql missing-group count: 0 | ETFs: 15 | non-ETF: 503
AC4 invalid tickers in symbols: 0
===== RUN force402 (force402=True)
gap_route: wikipedia-derived
rows_by_source: {'hanshof': 685, 'rename-bounded': 10, 'wikipedia-derived-bounded': 28, 'wikipedia-derived-exact': 28}
AC9 current_members_without_row: 0 | AC2b members_on(today)= 503 current_table= 503 equal: True
renames in membership: [('BK', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('BNY', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('EQR', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('FI', datetime.date(2023, 6, 8), datetime.date(2025, 8, 23), 'rename-bounded'), ('FISV', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('MMC', datetime.date(2015, 1, 1), datetime.date(2025, 8, 23), 'rename-bounded'), ('MRSH', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('PSKY', datetime.date(2025, 8, 12), datetime.date(2025, 8, 23), 'rename-bounded'), ('SKYD', datetime.date(2025, 8, 25), None, 'rename-bounded'), ('VMRK', datetime.date(2025, 8, 25), None, 'rename-bounded')]
n_symbols: 518 n_members_today: 503 n_missing_group: 0 membership_rows: 751
FMP calls: 2 {'sp500-constituent:402': 1, 'historical-sp500-constituent:402': 1}
AC1 sql missing-group count: 0 | ETFs: 15 | non-ETF: 503
AC4 invalid tickers in symbols: 0
===== AC2 (run A store): members_on vs hanshof snapshot
2016-06-30: members_on=479 hanshof(2016-06-27)=479 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2020-03-31: members_on=499 hanshof(2020-03-03)=499 symmetric_diff=0 only_members_on=[] only_hanshof=[]
2024-12-31: members_on=503 hanshof(2024-12-31)=503 symmetric_diff=0 only_members_on=[] only_hanshof=[]
H (hanshof last snapshot): 2025-08-23
===== Run A vs B: same route and counts? True True
bounded rows A: 28 (ceiling 40)
```

## Reading
- **AC9:** `current_members_without_row = 0` (both runs). **AC2 second half:** `members_on(today)` = **503** = current table **503**. **AC2 first half:** differences vs hanshof 0 / 0 / 0 on the three dates.
- **AC7:** gap route `wikipedia-derived`; rows by source hanshof=685, rename-bounded=10, wikipedia-derived-bounded=**28** (ceiling 40; was 33 before the five mapped renames left the removal set), wikipedia-derived-exact=28.
- **AC6:** 2 FMP calls per refresh (limit 60), both 402; refresh completes. **AC1/AC4:** 0 symbols without an industry group (503 + 15 ETFs), 0 invalid tickers.
- **Rename pairs:** all five have `effective: null`, so both rows are `rename-bounded`: old closes 2025-08-23 (H), new opens 2025-08-25 (next trading day; H is a Saturday). Pairs: BK→BNY, FI→FISV, MMC→MRSH, PSKY→SKYD, EQR→VMRK.
  Pairing evidence (not a source of truth; the map is): current-table names, `Date added` ≈ the old ticker's hanshof start (EQR 2001-12-03; PSKY/PARA 1994), and yfinance serving the old ticker's history under the new ticker with equal closes
  (EQR/VMRK 2026-08-17 close 63.66 = 63.66; PSKY/SKYD 2026-10-16 6.91 = 6.91). The effective dates are not evidenced by any free source, hence null.
- Earlier-pass evidence for the unchanged AMD-0013 behaviour (forced 402, FMP call counts) is in `audit-pass1-22a3ad1.md` and the pass-1 operator record in git history.
