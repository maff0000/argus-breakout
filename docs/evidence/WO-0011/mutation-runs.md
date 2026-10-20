# WO-0011 — AC4 mutation runs

Run by the Delivery Controller on a `git archive` copy of `647e1aa930c385f754593ef38b03668514eca53c` under mktemp (own venv). Each mutation reverts one PRIMARY KEY from `(symbol, date, source)` to `(symbol, date)`; the file is restored after each run.

```
baseline:
5 passed in 3.59s
=== mutation: splits PRIMARY KEY (symbol, date, source) -> (symbol, date)
 1 file changed, 1 insertion(+), 1 deletion(-)
E               _duckdb.BinderException: Binder Error: The specified columns as conflict target are not referenced by a UNIQUE/PRIMARY KEY CONSTRAINT or INDEX
FAILED tests/test_schema.py::test_actions_tables_keyed_by_source - _duckdb.Bi...
1 failed, 4 passed in 1.44s
=== mutation: dividends PRIMARY KEY (symbol, date, source) -> (symbol, date)
 1 file changed, 1 insertion(+), 1 deletion(-)
E               _duckdb.BinderException: Binder Error: The specified columns as conflict target are not referenced by a UNIQUE/PRIMARY KEY CONSTRAINT or INDEX
FAILED tests/test_schema.py::test_actions_tables_keyed_by_source - _duckdb.Bi...
1 failed, 4 passed in 1.66s
restored:
5 passed in 1.66s
```
Reading: both mutations make `test_actions_tables_keyed_by_source` fail; the failure is a BinderException on the upsert's `ON CONFLICT (symbol, date, source)` target rather than a row-count assertion (disclosed by the Implementer; the Auditor's MUT5 additionally shows a row-level ConstraintException when the conflict target survives).
