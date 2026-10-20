# WO-0004 — Audit record

Whole-branch re-audit by a fresh Forge Auditor (never a fork), ssh-only, detached audit worktree at the audited SHA, mutations on `mktemp` copies. An earlier audit of the pre-AMD-0012 head (`8cfe386`) is superseded and not relied on.

| Audited SHA | Scope | Verdict |
|---|---|---|
| `db714d9` | whole branch after AMD-0012 delta (`ingest_polygon_actions` writes `splits` and `dividends`, keyed `["symbol","date","source"]`; `splits_today` reads `splits`; CLI echo text) | **GREEN, no findings**, `commit_identity_clean: yes` |

The branch head is now `b5948ae` = `db714d9` + a clean merge of main `d0ea305` (AMD-0014, which does not touch WO-0004 code); code identical to the audited tree.

Result summary: 73 tests pass offline (also with network disabled); ruff and gitleaks clean; scope inside WO §2; portability greps empty. Mutations on copies were killed by the intended tests — including writing splits to the wrong table,
collapsing the same-date split+dividend case to one row, dropping the `source` key column, and the key never appearing in logs. **Unpinned (observations, not findings):** the `ratio <> 1` filter and the `.unique` dedupe in the actions path are not pinned by any test.

*Note on provenance:* the Auditor's full return was consumed in the Delivery Controller session; this file records the verdict and the mutation outcome as reported. The verbatim dispatch prompt is `auditor-prompt.md`.
