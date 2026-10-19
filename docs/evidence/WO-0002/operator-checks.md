# WO-0002 — Operator checks

Run by the Delivery Controller on dell-debian against the audited head, using a `mktemp` store directory (deleted after).
No credential, host or port value is involved.

```
host=dell-debian head=e5682b9d57e09a4575cf25e57564fb94eecf244b
$ argus init-store   (AC1; ARGUS_STORE_DIR=<mktemp>/store)
store ready: 18 tables
  adjustments
  bars
  bars_raw
  briefs
  composites
  etf_bars
  events
  evidence_packs
  features
  ingest_log
  iv_daily
  market_daily
  membership
  ranks
  reconcile_log
  schema_version
  sector_daily
  symbols
rc=0
$ stat -c "%a" <store>
750
$ SHOW TABLES  (AC1)
adjustments
bars
bars_raw
briefs
composites
etf_bars
events
evidence_packs
features
ingest_log
iv_daily
market_daily
membership
ranks
reconcile_log
schema_version
sector_daily
symbols
count 18
$ argus init-store (second run; AC2) then schema_version rows
store ready: 18 tables
schema_version rows 1
$ find <store>/parquet -type d  (AC3 layout before any write)
parquet
parquet/bars
parquet/bars_raw
parquet/bars_raw/year=1900
parquet/bars/symbol=_EMPTY_
parquet/etf_bars
parquet/etf_bars/symbol=_EMPTY_
--- AC3: write sample fixture, list year partition
columns ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'source', 'basis', 'ingested_at'] rows 90
```

AC1: `init-store` created the store and `SHOW TABLES` lists exactly 18 names. AC2: second run unchanged, one `schema_version` row.
AC3 (parquet partition under `store/parquet/bars_raw/year=YYYY/` after a write) is proven by
`tests/test_store.py::test_bars_raw_roundtrip_and_dedupe`, which asserts the `year=2024` directory exists (Auditor re-ran it).
