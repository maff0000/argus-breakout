# WO-0017 operator checks (live data, scratch copy of the production store)

Store: a copy of the production store taken after the WO-0009 first-install load (schema 6), migrated with the
WO-0017 code, `ingest polygon-actions --since 2024-01-01` re-run so the new columns are populated
(09:39Z to 11:29Z, rc=0; declaration_date on 5,492 and frequency on 5,499 of 5,499 Polygon rows),
then re-migrated to schema 8 and `adjust materialise` re-run with the AMD-0031 code (b9defa2).

## History
The first live run, on the first-implementation code (3551139), FAILED AC2: DVN 2024-09-13 (a genuine pair of two
0.22 records) was collapsed, turning a Polygon figure that agreed with yfinance into one that disagreed 2x. The work
was stopped and reported; AMD-0031 replaced the rule. The figures below are from the AMD-0031 code.

## Results
- **AC1** attribution.md: TEL duplicate, SKYD duplicate (yfinance side), DVN genuine.
- **AC2** (canonical-symbol grouping, as materialise sees it): groups collapsed 2 (TEL 2024-11-22, SKYD 2026-09-15 yfinance side);
  genuine multi-record preserved 29, **including PGR 2026-01-02 and DVN 2024-09-13**; resolved by the section 2B default **0**;
  weakened 1 (SKYD yfinance, NULL fields). `n_ambiguous_groups_resolved_by_default` = 0.
- **AC3** 12 integer-multiple pairs, all FCX (0.075 vs 0.15), left on source precedence; DVN no longer among them.
- **AC4** adj_close before/after in the raw output below: TEL moves to match one 0.65 dividend; SKYD matches PSKY's series;
  PGR unchanged (214.5528... / 211.8139..., ratio 0.93892, the -5.931% established by WO-0016).
- **AC5** bars_raw checksum identical (1,917,529 rows, 17672670937475303361139567), SCHEMA_VERSION 6 -> 8, no table lost a row.

## Raw output
```
AC5 bars_raw before [(1917529, '17672670937475303361139567')]
AC5 bars_raw after  [(1917529, '17672670937475303361139567')]
AC5 schema_version [(7,)] -> [(8,)]
AC5 rows dividends 24652 -> 24652
AC5 rows splits 228 -> 228
AC5 rows membership 751 -> 751
AC5 rows bars 1565316 -> 1565316
AC5 rows bars_raw 1917529 -> 1917529
AC5 rows symbols 755 -> 755
populated declaration_date/frequency: [('polygon', 5499, 5492, 5499), ('yfinance', 19153, 0, 0)]
AC2 raw table (as stored symbol): {'duplicate_groups_collapsed': 1, 'genuine_multi_record': 29, 'resolved_by_default': 0, 'weakened': 0}
AC2 canonical symbol grouping   : {'duplicate_groups_collapsed': 2, 'genuine_multi_record': 29, 'resolved_by_default': 0, 'weakened': 1}
AC2 prefix pattern of vendor_id in every multi-record polygon group (canonical symbol):
   CME 2026-03-10 [(6.15, '2026-02-12', 1, 'E'), (1.3, '2026-02-12', 4, 'E')]
   COP 2024-02-15 [(0.2, '2024-02-08', 0, 'E'), (0.58, '2024-02-08', 4, 'E')]
   COP 2024-08-12 [(0.58, '2024-08-01', 4, 'E'), (0.2, '2024-08-01', 4, 'E')]
   DVN 2024-03-14 [(0.22, '2024-02-27', 4, 'E'), (0.22, '2024-02-27', 0, 'P')]
   DVN 2024-06-14 [(0.22, '2024-05-01', 4, 'E'), (0.13, '2024-05-01', 0, 'E')]
   DVN 2024-09-13 [(0.22, '2024-08-06', 4, 'E'), (0.22, '2024-08-06', 4, 'P')]
   EXE 2024-05-15 [(0.575, '2024-04-30', 4, 'E'), (0.14, '2024-04-30', 0, 'E')]
   EXE 2025-08-14 [(0.575, '2025-07-25', 4, 'E'), (0.89, '2025-07-29', 4, 'E')]
   F 2024-02-15 [(0.15, '2024-02-06', 4, 'E'), (0.18, '2024-02-06', 0, 'E')]
   F 2025-02-18 [(0.15, '2025-02-05', 4, 'E'), (0.15, '2025-02-06', 0, 'E')]
   FANG 2024-03-04 [(0.9, '2024-02-15', 4, 'E'), (2.18, '2024-02-15', 0, 'E')]
   FANG 2024-05-14 [(1.07, '2024-04-30', 4, 'E'), (0.9, '2024-04-30', 4, 'E')]
   FANG 2024-08-15 [(1.44, '2024-08-05', 4, 'E'), (0.9, '2024-08-05', 4, 'E')]
   HP 2024-02-12 [(0.25, '2023-12-06', 4, 'E'), (0.17, '2023-12-06', 4, 'E')]
   HP 2024-05-16 [(0.25, '2024-02-28', 4, 'E'), (0.17, '2024-02-28', 4, 'E')]
   HP 2024-08-16 [(0.17, '2024-06-05', 4, 'E'), (0.25, '2024-06-05', 4, 'E')]
   HST 2024-12-31 [(0.1, '2024-12-11', 1, 'E'), (0.2, '2024-12-11', 4, 'E')]
   HST 2025-12-31 [(0.15, '2025-12-11', 1, 'E'), (0.2, '2025-12-11', 4, 'E')]
   HST 2026-06-30 [(0.2, '2026-05-06', 4, 'E'), (0.72, '2026-05-06', 0, 'E')]
   PGR 2024-01-18 [(0.1, '2023-12-01', 4, 'E'), (0.75, '2023-12-01', 1, 'E')]
   PGR 2025-01-10 [(4.5, '2024-12-06', 1, 'E'), (0.1, '2024-12-09', 4, 'E')]
   PGR 2026-01-02 [(13.5, '2025-12-05', 1, 'E'), (0.1, '2025-12-08', 4, 'E')]
   PXD 2024-03-01 [(1.31, '2024-02-22', 4, 'E'), (1.25, '2024-02-22', 4, 'E')]
   TEL 2024-11-22 [(0.65, '2024-03-13', 4, 'E'), (0.65, '2024-03-13', 4, 'E')]
   WRB 2024-06-24 [(0.12, '2024-06-12', 4, 'E'), (0.5, '2024-06-12', 0, 'E')]
   WRB 2024-09-23 [(0.25, '2024-09-11', 0, 'E'), (0.08, '2024-09-11', 4, 'E')]
   WRB 2024-12-16 [(0.5, '2024-12-06', 0, 'E'), (0.08, '2024-12-06', 4, 'E')]
   WRB 2025-06-23 [(0.09, '2025-06-11', 4, 'E'), (0.5, '2025-06-11', 0, 'E')]
   WRB 2025-12-15 [(1.0, '2025-12-05', 0, 'E'), (0.09, '2025-12-05', 4, 'E')]
   WRB 2026-06-23 [(0.1, '2026-06-03', 4, 'E'), (0.5, '2026-06-03', 2, 'E')]
materialise rerun n_rows 0 n_warnings 3186 [('source_disagreement', 3126), ('bars_after_final_end_without_continuity', 22), ('no_bars', 22), ('dividend_integer_multiple', 12), ('dividend_ambiguous_group', 3), ('dividend_dedupe_weakened', 1)]
n_ambiguous_groups_resolved_by_default 0
  A dividend_ambiguous_group DVN 2024-09-13 source=polygon records=2 amount=0.2200 ids=Eb19fea597c46e0d6b0411fb962cec49a96020fd42743cb04ea9dcadcfac23adf,Pe3c430b21d4818e8b6db8c079a0b6bd4b9e3b7843eca5b937be3158674c5cf23 resolution=genuine (matches_sum) yfinance=0.4400 if_one=0.2200 if_all=0.4400
  A dividend_ambiguous_group SKYD 2026-09-15 source=yfinance records=2 amount=0.0500 ids=sum,sum resolution=duplicate (matches_one) polygon=0.0500 if_one=0.0500 if_all=0.1000
  A dividend_ambiguous_group TEL 2024-11-22 source=polygon records=2 amount=0.6500 ids=E0db7c55e9207d0d053fbf9370917fe59c0c4dfee0d5af8de4026cfa31983cb74,E89b4ac9e4c8a74626d9ea08f59bf9b3e20c7fc900cf32ef2dadaf5e321ca942d resolution=duplicate (matches_one) yfinance=0.6500 if_one=0.6500 if_all=1.3000
AC3 integer_multiple warnings: 12
  M dividend_integer_multiple FCX 2024-01-11 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2024-04-12 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2024-07-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2024-10-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2025-01-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2025-04-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2025-07-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2025-10-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2026-01-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2026-04-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2026-07-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
  M dividend_integer_multiple FCX 2026-10-15 polygon=0.0750 yfinance=0.1500 multiple=2x left on source precedence (polygon), attribute from the raw payload (normalised; stored 0.0750/0.1500)
dividend_ambiguous_group: 3  weakened: 1
dividend_disagreement w/ total_source: 0
AC4 TEL 2024-11-22
  before [(datetime.date(2024, 11, 18), 148.36, 143.27079330625955), (datetime.date(2024, 11, 19), 146.95, 141.90916066564327), (datetime.date(2024, 11, 20), 147.82, 142.74931697581073), (datetime.date(2024, 11, 21), 150.52, 145.35669862805463), (datetime.date(2024, 11, 22), 152.26, 148.3179931182656)]
  after  [(datetime.date(2024, 11, 18), 148.36, 143.894878654397), (datetime.date(2024, 11, 19), 146.95, 142.5273147631682), (datetime.date(2024, 11, 20), 147.82, 143.37113078116042), (datetime.date(2024, 11, 21), 150.52, 145.98987014734317), (datetime.date(2024, 11, 22), 152.26, 148.3179931182656)]
AC4 SKYD 2026-09-15
  before [(datetime.date(2026, 9, 11), 10.600000381469727, 10.502484277577656), (datetime.date(2026, 9, 14), 10.869999885559082, 10.769999885559082), (datetime.date(2026, 9, 15), 11.010000228881836, 11.010000228881836), (datetime.date(2026, 9, 16), 11.140000343322754, 11.140000343322754)]
  after  [(datetime.date(2026, 9, 11), 10.600000381469727, 10.551242329523692), (datetime.date(2026, 9, 14), 10.869999885559082, 10.819999885559083), (datetime.date(2026, 9, 15), 11.010000228881836, 11.010000228881836), (datetime.date(2026, 9, 16), 11.140000343322754, 11.140000343322754)]
AC4 PSKY 2026-09-15
  before [(datetime.date(2026, 9, 11), 10.6, 10.551241950321987), (datetime.date(2026, 9, 14), 10.87, 10.819999999999999), (datetime.date(2026, 9, 15), 11.01, 11.01), (datetime.date(2026, 9, 16), 11.135, 11.135)]
  after  [(datetime.date(2026, 9, 11), 10.6, 10.551241950321987), (datetime.date(2026, 9, 14), 10.87, 10.819999999999999), (datetime.date(2026, 9, 15), 11.01, 11.01), (datetime.date(2026, 9, 16), 11.135, 11.135)]
AC4 PGR 2026-01-02
  before [(datetime.date(2025, 12, 29), 228.51, 214.55283685996164), (datetime.date(2025, 12, 30), 229.97, 215.92366151453058), (datetime.date(2025, 12, 31), 227.72, 213.8110892729004), (datetime.date(2026, 1, 2), 212.12, 211.81397467106123)]
  after  [(datetime.date(2025, 12, 29), 228.51, 214.55283685996164), (datetime.date(2025, 12, 30), 229.97, 215.92366151453058), (datetime.date(2025, 12, 31), 227.72, 213.8110892729004), (datetime.date(2026, 1, 2), 212.12, 211.81397467106123)]
AC4 PGR before [(datetime.date(2025, 12, 31), 227.72, 213.8110892729004), (datetime.date(2026, 1, 2), 212.12, 211.81397467106123)] adj ratio 0.9389209962800826
AC4 PGR after [(datetime.date(2025, 12, 31), 227.72, 213.8110892729004), (datetime.date(2026, 1, 2), 212.12, 211.81397467106123)] adj ratio 0.9389209962800826
AC4 PGR warnings: []
AC4 TEL/SKYD/PSKY warnings: ['dividend_dedupe_weakened SKYD 2026-09-15 source=yfinance records=2 declaration_date or frequency is NULL: grouped on cash_amount alone', 'dividend_ambiguous_group SKYD 2026-09-15 source=yfinance records=2 amount=0.0500 ids=sum,sum resolution=duplicate (matches_one) polygon=0.0500 if_one=0.0500 if_all=0.1000', 'dividend_ambiguous_group TEL 2024-11-22 source=polygon records=2 amount=0.6500 ids=E0db7c55e9207d0d053fbf9370917fe59c0c4dfee0d5af8de4026cfa31983cb74,E89b4ac9e4c8a74626d9ea08f59bf9b3e20c7fc900cf32ef2dadaf5e321ca942d resolution=duplicate (mat']
```
