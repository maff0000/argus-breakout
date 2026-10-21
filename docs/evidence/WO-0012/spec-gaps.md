# WO-0012 — Spec gaps and residuals (for the Architect)

1. **Scope ratification.** `tests/test_schema.py` and `tests/test_cli.py` (table count 20→21, `store_meta` in DESIGN_TABLES, version 3→4) are not in WO §2 and follow mechanically from the mandated DDL and `SCHEMA_VERSION = 4`. Same pattern as WO-0004 (finding filed there). Suggest the standing rule: a WO that adds a table or bumps the version may update the count/version assertions in `test_schema.py` and `test_cli.py`.
2. **Undetectable first relocation.** A pre-schema-4 store (no `store_meta`) copied before `init-store` runs once cannot be detected as relocated; CI-5's relocation clause is enforced from the first post-upgrade `init-store` or read-write `connect()`. The live store should be `init-store`d on its home path before any copy.
3. **Read-write `connect()` repairs silently** (one WARNING log line). A process that opens a copy read-write will rebuild its views without the operator running `init-store`. That follows the WO text; flagging it in case the Architect wants repair confined to `init-store`.
4. **No automated test for the CLI "repaired" message.**
