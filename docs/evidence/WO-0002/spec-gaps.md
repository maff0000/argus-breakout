# WO-0002 — Specification gaps and rulings

Ratified by the Architect in AMD-0011 (§1, §2D):
1. **Obsolete stub test (`tests/test_cli.py`).** Replaced by `test_init_store_creates_store`; now listed in WO-0002 §2 and covered by standing ruling 6.
2. **`# noqa: F401, E402` on the `argus/cli.py` import line** — ratified (structural).
3. **`features` carries only `(date, symbol)`** — ratified (columns arrive with PID-ARGUS-0002).
4. **Empty placeholder parquet files** — ratified (WO §8).
5. **`membership.end_date` inclusive** — confirmed by AMD-0011 (DESIGN §3.2/§3.3); boundary test and AC7 added; both mutations filed in `mutation-runs.md`.

Not ruled, noted: the views hold the resolved absolute store path and are recreated on every `init-store`; a moved store needs `init-store` re-run.
