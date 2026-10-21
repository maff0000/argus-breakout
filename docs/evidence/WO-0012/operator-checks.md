# WO-0012 — Operator checks (AC5, AC6)

Run by the Delivery Controller on dell-debian against head `48eb7a5df5df89e4a6831eac201e48620ef56508`, on **copies** of the live WO-0004 store (the live store is untouched). Paths are filesystem paths only; no host, port or key value appears.

```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0012 head=48eb7a5df5df89e4a6831eac201e48620ef56508
--- AC6: upgrade a copy of the live store (schema v3 -> v4); row counts before/after
BEFORE
{'bar_flags': 128, 'bars': 0, 'bars_raw': 312025, 'briefs': 0, 'composites': 0, 'dividends': 5448, 'etf_bars': 0, 'events': 0, 'evidence_packs': 0, 'features': 0, 'ingest_log': 1134, 'iv_daily': 0, 'market_daily': 0, 'membership': 751, 'ranks': 0, 'reconcile_log': 0, 'schema_version': 2, 'sector_daily': 0, 'splits': 46, 'symbols': 755}
$ argus init-store (ARGUS_STORE_DIR=copy a)
store ready: 21 tables
store_dir: /tmp/argus-live/s12a
  store_meta
AFTER
{'bar_flags': 128, 'bars': 0, 'bars_raw': 312025, 'briefs': 0, 'composites': 0, 'dividends': 5448, 'etf_bars': 0, 'events': 0, 'evidence_packs': 0, 'features': 0, 'ingest_log': 1134, 'iv_daily': 0, 'market_daily': 0, 'membership': 751, 'ranks': 0, 'reconcile_log': 0, 'schema_version': 3, 'sector_daily': 0, 'splits': 46, 'store_meta': 1, 'symbols': 755}
$ argus init-store again (idempotent)
store ready: 21 tables
store_dir: /tmp/argus-live/s12a
--- AC5: copy the upgraded store and run init-store on the copy
$ read-only open of the copy
StoreRelocatedError store relocated: recorded '/tmp/argus-live/s12a', now '/tmp/argus-live/s12b'; a read-write `argus init-store` repairs it
$ argus init-store (copy b)
store relocated: recorded '/tmp/argus-live/s12a', now '/tmp/argus-live/s12b'; views recreated
store relocated: repaired views (was /tmp/argus-live/s12a)
store ready: 21 tables
store_dir: /tmp/argus-live/s12b
COPY B COUNTS
{'bar_flags': 128, 'bars': 0, 'bars_raw': 312025, 'briefs': 0, 'composites': 0, 'dividends': 5448, 'etf_bars': 0, 'events': 0, 'evidence_packs': 0, 'features': 0, 'ingest_log': 1134, 'iv_daily': 0, 'market_daily': 0, 'membership': 751, 'ranks': 0, 'reconcile_log': 0, 'schema_version': 3, 'sector_daily': 0, 'splits': 46, 'store_meta': 1, 'symbols': 755}
```

Reading: AC6 — every table's row count is identical before and after the v3→v4 upgrade (`schema_version` gains one row, `store_meta` appears with 1 row); a second `init-store` is a no-op. AC5 — `init-store` prints the recorded `store_dir`; the copy opened read-only raises `StoreRelocatedError` naming both paths; read-write `init-store` on the copy repairs, says so explicitly, and every row count is preserved.
