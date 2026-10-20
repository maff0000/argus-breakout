# WO-0003 — Audit record (three independent passes)

All passes: fresh Forge Auditor dispatches (never forks), ssh-only on the execution host, in a detached audit worktree at the audited SHA,
mutations on `mktemp` copies. The earlier pass-1 record is kept as `audit-pass1-22a3ad1.md`.

| Pass | Audited SHA | Scope | Verdict |
|---|---|---|---|
| 1 | `22a3ad1` | AMD-0013 delta (routes a/b/c, ProviderUnavailable) | GREEN, one low finding (rename gap) → Architect ruled it AMD-0014 |
| 2 | `dcfe0b0` | whole branch incl. the AMD-0014 delta | GREEN, **one finding** (invariant enforced only when `as_of >= today`) |
| 3 | `4c10c60` | whole branch after the fix | **GREEN, no findings** |

## Pass 2 finding (fixed in `4c10c60`)
> LOW-MEDIUM. The invariant is enforced only when `as_of >= today (UTC)` (universe.py `enforced = as_of >= _today_utc()`). A back-dated
> `argus universe refresh --date 2025-12-31` completed rc=0, persisted the store and printed `current members without row: 18`: a shortfall
> reported as a statistic, which AMD-0014 §2B forbids. The CLI block commented "covers a back-dated --date" was dead code; a test locked the behaviour in.

Fix: `find_orphans(membership, current, renames, as_of)` — an orphan is a current-table symbol with `Date added <= as_of` (or unknown) and no membership interval
containing `as_of`; a symbol added after `as_of` is not one; the NEW ticker of a mapped rename not yet happened at `as_of` is not one *only while its OLD ticker is a member*.
Enforced on every run, before any write; the CLI exits 1 and names the symbols. A pending rename (known `effective` after `as_of`) keeps the old ticker a member.

## Pass 3 verdict block (as returned)
```
AUDIT_VERDICT: GREEN
work_order: WO-0003
base_sha: d0ea305
commit_sha: 4c10c6036f0d408a8eb411701364bf4818617e97
scope_fidelity: yes (all 21 changed paths are in WO §2 or AMD-0014 §3, or are DC evidence/clerical paths under docs/)
offline_tests_pass: yes (93 passed, run twice: normally, and inside `unshare -rn`; no .env present, FMP_API_KEY unset in the second run)
non_vacuity_established: yes (5 mutants run, all caught)
gitleaks_clean: yes (62 commits scanned, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes
AC1..AC9_verified: yes (AC2's +/-3 historical comparison against the real hanshof CSV is operator-only; filed in operator-checks.md)
findings: none
confidence: high
```

### Mutants (pass 3, `pytest tests/test_universe.py` on a copy of universe.py)
| Mutant | Result |
|---|---|
| (i) rename as addition (old not closed, new opens H+1) — the rejected option 2 | 10 failed incl. `test_rename_preserves_continuity`, `test_rename_unknown_effective_is_bounded_not_added`, `test_no_current_member_without_row` |
| (ii) new ticker's row dropped | 19 failed incl. both rename tests and `test_no_current_member_without_row` |
| (iii) gating reintroduced (`as_of >= today` only) | 1 failed — `test_missing_rename_map_fails_loudly` (the pass-2 regression) |
| (iv) pending-rename exclusion removed | 1 failed — `test_known_effective_after_as_of_keeps_old_ticker_a_member` |
| (v) orphan exemption widened to any mapped new ticker | 1 failed — `test_orphans_unmapped_hanshof_internal_rename_is_named` |

### Probes (pass 3, real CLI, offline fixtures, shipped map)
| as_of | exit | members | current table | without row |
|---|---|---|---|---|
| 2026-10-20 | 0 | 503 | 503 | 0 |
| 2027-01-01 | 0 | 503 | 503 | 0 |
| 2025-12-31 | 0 | 485 | 503 | 0 (18 later additions neither flagged nor members) |
| 2025-09-01 | 0 | 476 | 503 | 0 |
| 2025-08-23 (=H) | 0 | 503 | 503 | 0 |

With the map removed: exit 1, nothing persisted, "5 current index members have no membership row on <date>: BNY, FISV, MRSH, SKYD, VMRK" (more names before H on the sparse fixture).
A genuinely missing member (AAPL stripped) exits 1 naming AAPL on both dates.

### Per-test judgement of tests changed across the deltas (pass 3)
- `_mock_sources` serves a COMPLETE history: justified (a partial route-(a)/(b) history now correctly fails a today-dated run); no assertion loosened.
- Route-(b) test: strengthened (complete changes table, default as_of); still asserts IBKR/WBA rows and zero bounded.
- FMP-fallback test moved to `--date 2026-10-20`: justified (FMP-only current table has no `Date added`); the one narrowing — back-dated FMP-only behaviour fails closed and is untested.
- 33→28: derived (`len(last − cur − mapped_old) == 28`, all five mapped olds asserted), not a magic number. `_pin_today`: determinism only.
- `test_missing_rename_map_fails_loudly`: strengthened (back-dated half asserts exit 1 + names the five).

### Observations (none blocking)
1. The orphan exemption hides a missing member only if the rename map is wrong (OLD also a current constituent, future `effective`, back-dated run); a today-dated run still trips the equal-count check. Not exploitable with null `effective`.
2. A back-dated run with the FMP-only current table fails closed with false orphans (`date_added` None) and the hint text mentions a missing rename.
3. A back-dated run before an unmapped rename inside hanshof (PARA→PSKY→SKYD) names SKYD: correct under the rule; sparse fixture also names APO/LII/WDAY before H.
4. The post-write `members_on` equality check (universe.py ~894) is unreachable in practice (the pre-write check raises first).
