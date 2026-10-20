# WO-0005 — Operator checks (live, host-run, final code `70ce2d7`)

Run on dell-debian against the final code (the audited `85c01e1` tree plus one test). Store seeded from the WO-0003 branch's real `universe refresh` (755 `symbols` = 518 active current members/ETFs + 237 historical-only, `active=false`); yfinance needs no key.
**Method note (disclosed).** The seed store was *copied* to the working directory; DuckDB's Parquet views bake in an absolute path, so after a copy `init_schema()` must be re-run or reads see the source directory's (empty) views. My first re-run on the un-reinitialised copy therefore skipped nothing (reading the wrong, empty directory) — that run is not evidence and is discarded; the resume check below was repeated after `init_schema()`. This is a container-readiness observation (spec-gaps).

## AC1a — met (current cohort 518 / 518 = 100.0% ≥ 99%)
`argus ingest bootstrap --start 2015-01-01` on the fresh store (wall 258 s):
```
symbols=628 rows=1743171 skipped=0 failed=127
current: written=518 skipped=0 failed=0 (100.0%)
historical: written=110 skipped=0 unavailable=127 (46.4%)
rc=0
```
Exception list for the current cohort: **none** (no current member or ETF failed). The exit code is 0 — before AMD-0015 §2B the same data gave exit 1.

## AC1b — reported, no threshold (limitation of the free source, accepted residual R5)
Historical-only requested: **237** = written **110** + unavailable **127** (**46.4%** covered). Full unavailable list: `delisted-coverage.md`.

## AC2 — met, exceptions listed
Every active symbol (current members and ETFs) has ≥ 2,400 `bars_raw[source='yfinance']` rows for 2015-01-01…2024-12-31 **except 47, every one of which first traded after 2015-01-10** (IPO, spin-off, listing, or ETF inception); none was listed from the start but short. Output of the check:
```
symbols total 755 active 518 historical-only 237
bars_raw yfinance symbols/rows (628, 1743171)
AC2: active symbols with <2400 rows 2015-2024: 47 | of which first bar after 2015-01-10 (or none): 47 | listed-from-start but short: []
exceptions (symbol,rows,first bar): [('KHC', 2390, '2015-07-06'), ('PYPL', 2390, '2015-07-06'), ('LITE', 2377, '2015-07-23'), ('P', 2325, '2015-10-06'), ('XLRE', 2323, '2015-10-08'), ('HPE', 2316, '2015-10-19'), ('XYZ', 2293, '2015-11-19'), ('TWLO', 2145, '2016-06-23'), ('FTV', 2138, '2016-07-05'), ('DELL', 2107, '2016-08-17'), ('VST', 2073, '2016-10-05'), ('HWM', 2054, '2016-11-01'), ('INVH', 1992, '2017-02-01'), ('CVNA', 1932, '2017-04-28'), ('IR', 1922, '2017-05-12'), ('VICI', 1761, '2018-01-02'), ('XLC', 1645, '2018-06-19'), ('BE', 1620, '2018-07-25'), ('VRT', 1614, '2018-08-02'), ('MRNA', 1526, '2018-12-07'), ('FOXA', 1463, '2019-03-12'), ('FOX', 1462, '2019-03-13'), ('DOW', 1457, '2019-03-20'), ('UBER', 1421, '2019-05-10'), ('CRWD', 1399, '2019-06-12'), ('DDOG', 1330, '2019-09-19'), ('CARR', 1205, '2020-03-19'), ('OTIS', 1205, '2020-03-19'), ('PLTR', 1070, '2020-09-30'), ('DASH', 1021, '2020-12-09'), ('ABNB', 1020, '2020-12-10'), ('EXE', 979, '2021-02-10'), ('COIN', 936, '2021-04-14'), ('APP', 935, '2021-04-15'), ('HOOD', 862, '2021-07-29'), ('CEG', 742, '2022-01-19'), ('GEHC', 513, '2022-12-15'), ('KVUE', 418, '2023-05-04'), ('VLTO', 313, '2023-10-04'), ('RDDT', 197, '2024-03-21'), ('SOLV', 194, '2024-03-26'), ('GEV', 193, '2024-03-27'), ('SNDK', 0, '2025-02-13'), ('Q', 0, '2025-10-27'), ('FDXF', 0, '2026-05-27'), ('HONA', 0, '2026-06-15'), ('VYLR', 0, '2026-10-01')]
AC3 splits yfinance 207 dividends yfinance 20843
same-date pairs [('DXC', datetime.date(2015, 11, 30), 1.7412, 9.083045), ('DHR', datetime.date(2016, 7, 5), 1.319, 24.56), ('XRX', datetime.date(2017, 1, 3), 1.518, 2.98)]
```

## AC3 — met
`splits` source=yfinance **207**, `dividends` source=yfinance **20,843**; same-date split + dividend retained: **3** (DXC 2015-11-30, DHR 2016-07-05, XRX 2017-01-03) — see the last lines above.

## AC4 — resumability (live)
Re-run on the same store after `init_schema()` (wall 60 s, rc 0):
```
symbols=74 rows=100448 skipped=554 failed=127
current: written=45 skipped=473 failed=0 (100.0%)
historical: written=29 skipped=81 unavailable=127 (46.4%)
```
554 symbols skipped (473 current + 81 historical); the 45 current + 29 historical re-written are symbols listed after the range start, which cannot reach the 95% resume floor (audit observation 1).
