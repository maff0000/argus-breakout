# WO-0011 — Operator checks

Run by the Delivery Controller on dell-debian against head `647e1aa930c385f754593ef38b03668514eca53c`. Scratch stores only (copies under mktemp); the version-1 store used for AC6 is a copy of the WO-0002-era scratch store.

```
host=dell-debian head=647e1aa930c385f754593ef38b03668514eca53c
--- AC1/AC5: fresh store, init-store twice
$ uv run argus init-store
  sector_daily
  splits
  symbols
[(19,)]
[('dividends',), ('splits',)]
$ SHOW TABLES (names)
[('bars',), ('bars_raw',), ('briefs',), ('composites',), ('dividends',), ('etf_bars',), ('events',), ('evidence_packs',), ('features',), ('ingest_log',), ('iv_daily',), ('market_daily',), ('membership',), ('ranks',), ('reconcile_log',), ('schema_version',), ('sector_daily',), ('splits',), ('symbols',)]
[(2, datetime.datetime(2026, 10, 20, 7, 42, 30, 458026))]
$ uv run argus init-store  (second run)
  sector_daily
  splits
  symbols
[(2,)]
--- AC6: copy of the existing scratch store (version-1, has adjustments)
[('adjustments',)]
[(1, datetime.datetime(2026, 10, 19, 23, 39, 38, 154637))]
[(0,)]
$ uv run argus init-store  (on the copy)
  sector_daily
  splits
  symbols
rc=0
[('adjustments',), ('dividends',), ('splits',)]
[(1,), (2,)]
[(0,)]
  symbols
[(1,), (2,)]
```
