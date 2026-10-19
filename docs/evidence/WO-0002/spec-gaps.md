# WO-0002 — Specification gaps (AMD-0010 §2C ruling 2; for ratification at the next Architect review)

1. **Obsolete stub test (`tests/test_cli.py`).** WO §2 removes the `init-store` stub from `argus/cli.py`, but `tests/test_cli.py::test_init_store_stub_exits_2`
   (WO-0001) asserts the stub's exit code 2 and is not in §2. The Implementer was dispatched a delta to replace it with
   `test_init_store_creates_store` (exit 0, `store ready: 18 tables`, db file exists, store under `tmp_path`). Conventional, no interface
   consequence beyond the one the Work Order itself mandates. **The Auditor recorded it as `scope_fidelity: no` (finding 1), so it is not
   treated as procedural.**
2. **`# noqa: F401, E402` on the new `argus/cli.py` import line** (WO text says `F401` only). Ruff fails without `E402` because the line follows code.
3. **`members_on` end-date semantics — behavioural choice, NOT conventional; raised, not ruled.** PID/DESIGN do not state whether `membership.end_date`
   is inclusive. The Implementer chose inclusive (`start_date <= d AND (end_date IS NULL OR end_date >= d)`). The test does not cover the boundary
   (Auditor observation 1). Architect to rule and, if exclusive, to say so in the Work Order or an Amendment.
4. **`features` table** carries only `(date, symbol)` because DESIGN §3.2 leaves its columns open; later Work Orders add columns.
5. **Empty placeholder parquet files** written on init so the views resolve when empty (WO §8); views hold the resolved absolute store path and are
   recreated on every `init-store`.
