# WO-0011 — Specification gaps and rulings

1. **`tests/test_cli.py` not in WO §2.** `test_init_store_creates_store` asserted `"store ready: 18 tables"`; §2 explicitly changes the count to 19. The Implementer reported it as out of scope and did not edit it; the Delivery Controller changed that single assertion (18 → 19) under DELIVERY-CHAIN §9 standing ruling 6 (AMD-0011): confined to one assertion, coverage not reduced, test named. The Auditor confirmed the three conditions hold. Recommend adding `tests/test_cli.py` to the §2 table of any future Work Order that changes the table count.
2. **`init_schema()` version-row guard.** WO §4 requires recording version 2 "without destroying the version-1 row"; the old guard (`WHERE NOT EXISTS (SELECT 1 FROM schema_version)`) would never have recorded it on a version-1 store. Changed to `... WHERE version = ?`. In `store.py`, which is in §2. No test pins the upgrade path (Auditor observation 2); recommend a v1→v2 test in a later Work Order.
3. **AC4 failure mode** is a BinderException (see `mutation-runs.md`, `audit.md` observation 4). Accepted as meeting AC4.
4. **Cosmetic:** the `init_schema` docstring still says "once".
