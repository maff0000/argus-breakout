# WO-0002 — AC7 mutation runs (AMD-0011)

Run by the Delivery Controller on dell-debian on a `git archive` copy of the committed head under `mktemp -d` (the worktree is never perturbed).
Both mutations make `test_members_on_boundaries` fail; unmutated and restored runs pass. The Auditor independently reproduced both (audit.md).

```
host=dell-debian head=0958745fea94120816f5f6d76d747981835f0558
--- baseline (unmutated)
.                                                                        [100%]
1 passed in 1.06s
--- mutation 1: end_date >= ?  ->  end_date > ?
1
267:            "WHERE start_date <= ? AND (end_date IS NULL OR end_date > ?) ORDER BY symbol",
            schema_overrides={"end_date": pl.Date},
        )
        store.upsert("membership", m, ["symbol", "start_date"])
        # closed interval [s, e] is inclusive at both ends
        assert "AAA" in store.members_on(s)
>       assert "AAA" in store.members_on(e)
E       AssertionError: assert 'AAA' in []
E        +  where [] = members_on(datetime.date(2021, 9, 20))
E        +    where members_on = <argus.data.store.Store object at 0x7f989ff7a660>.members_on

tests/test_store.py:130: AssertionError
=========================== short test summary info ============================
FAILED tests/test_store.py::test_members_on_boundaries - AssertionError: asse...
1 failed in 0.95s
--- mutation 2: start_date <= ?  ->  start_date < ?
1
267:            "WHERE start_date < ? AND (end_date IS NULL OR end_date >= ?) ORDER BY symbol",
            },
            schema_overrides={"end_date": pl.Date},
        )
        store.upsert("membership", m, ["symbol", "start_date"])
        # closed interval [s, e] is inclusive at both ends
>       assert "AAA" in store.members_on(s)
E       AssertionError: assert 'AAA' in []
E        +  where [] = members_on(datetime.date(2021, 3, 10))
E        +    where members_on = <argus.data.store.Store object at 0x7f424108d040>.members_on

tests/test_store.py:129: AssertionError
=========================== short test summary info ============================
FAILED tests/test_store.py::test_members_on_boundaries - AssertionError: asse...
1 failed in 0.98s
--- restored
.                                                                        [100%]
1 passed in 0.97s
```
