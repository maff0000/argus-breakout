# WO-0019 — Events point-in-time completion: versioned rows and a single reader

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.5 ; `DESIGN.md` §3.2, §3.3 |
| **Applicable Amendments** | AMD-0024, AMD-0033, AMD-0034 |
| **Base SHA** | main at Closure of WO-0009 |
| **Branch** | `wo/0019-events-point-in-time-completion` |
| **Depends on** | WO-0009 (which lands the `first_seen`/`last_seen` columns) |
| **Parallel group** | P0-G — **may run concurrently with WO-0018** (shares no file) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **Evidence** | `docs/evidence/WO-0019/` |

## 1. Objective
WO-0009 made `events` point-in-time for a **moved date**. Two gaps remain,
both reported by the Delivery Controller and both mine (AMD-0034 §1d):

1. **Readers return superseded rows.** There are now two rows where there
   used to be one, and `next_earnings` / `days_to_earnings` do not filter,
   so after a date moves they can return the stale one.
2. **`confirmed`, `time_of_day` and `source` are frozen.** "Extend
   `last_seen` only" made the row immutable when what it needed was
   **versioning**. A date that later becomes *confirmed*, or gains a
   before/after-market marker, never records it — and `time_of_day`
   decides whether an earnings gap lands on day D or D+1, which is the
   entire basis of a PEAD study.

## 2. Scope (exhaustive)
```
argus/data/schema.py      modify  events: key becomes (symbol, date, type, first_seen);
                                    bump SCHEMA_VERSION to 10 (7 events, 8 WO-0017, 9 WO-0018)
argus/events/earnings.py  modify  SLOWLY-CHANGING DIMENSION, TYPE 2 (AMD-0034 §2F):
                                    - a row whose tracked attributes (confirmed, time_of_day, source) are
                                      UNCHANGED has its last_seen extended, as now
                                    - a row whose tracked attributes CHANGED is closed — last_seen frozen at
                                      the previous refresh date — and a NEW row is inserted with
                                      first_seen = last_seen = this refresh date and the new values
                                    - a row the calendar no longer carries is LEFT ALONE, last_seen frozen
                                    - date, type and first_seen are NEVER rewritten on an existing row
argus/data/store.py       modify  add events_live_as_of(as_of: date) -> pl.DataFrame: per (symbol, type), the
                                    row current on `as_of` — first_seen <= as_of <= last_seen, and where more
                                    than one qualifies the one with the greatest first_seen. THE ONLY
                                    sanctioned way to read `events`
argus/features/events_feat.py  modify  read via events_live_as_of(bar_date); no direct `events` access
argus/data/adjust.py      modify  ONLY if it reads `events` — route through the helper. Otherwise untouched
tests/test_events.py      modify  add the §5 tests
tests/test_store.py       modify  add the events_live_as_of tests
tests/test_schema.py      modify  count/version assertions only (ruling 9)
tests/test_cli.py         modify  count/version assertions only (ruling 9)
```

## 3. Exclusions
No new event source, no news, no calendar provider change, no PEAD or
event-feature logic beyond routing the existing readers through the helper.
No `pipeline.py`, `reconcile.py`, `providers/*` or `ops/`. No `docs/` by the
Implementer.

**Do not backfill history that was never captured.** Rows the migration
stamped with today's date stay stamped; the point-in-time record begins
when it begins, and inventing earlier windows would fabricate exactly the
evidence this mechanism exists to provide.

## 4. Design constraints
PID §8.5, §8.9 and ADR-0008. `events` is small, so the key change is cheap;
the migration must be idempotent and lose no row.

**One reader, no exceptions.** The defect being fixed is that a second way
to read the table existed. After this Work Order, `events_live_as_of` is
the only sanctioned access and an Auditor grep for direct `events` reads
outside `store.py` must come back empty.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_events.py::test_changed_confirmed_opens_a_new_version` | `confirmed` false→true closes the old row with a frozen `last_seen` and inserts a new one | asserts two rows and both windows |
| `test_events.py::test_changed_time_of_day_opens_a_new_version` | same for `time_of_day` — the field a PEAD study depends on | asserts two rows |
| `test_events.py::test_unchanged_row_extends_last_seen_only` | two refreshes on an identical calendar give **one** row with a widened window | asserts one row — fails if versioning is over-eager |
| `test_events.py::test_dropped_row_is_left_alone` | a row the calendar no longer carries keeps its `last_seen` frozen and is not deleted | asserts presence and the frozen date |
| `test_store.py::test_live_as_of_returns_the_row_current_then` | with three versions, `as_of` inside each window returns that version — **not** the latest | asserts per-window identity; this is the reader defect, pinned |
| `test_store.py::test_live_as_of_picks_greatest_first_seen_on_overlap` | overlapping windows resolve to the most recently opened row | asserts the tie-break |
| `test_store.py::test_live_as_of_excludes_superseded_rows` | after a date move, `as_of` later than the move returns **only** the new date | fails on an unfiltered read — the reported defect |

## 6. Acceptance criteria
- **AC1** — A live calendar refresh on the host that changes `confirmed` or `time_of_day` produces two versioned rows with adjacent windows (operator check: the rows, `first_seen`/`last_seen` shown).
- **AC2** — `events_live_as_of` for a past date returns the row that was current then; for today it returns the current one. Both filed for one symbol with a real version history, or — if none has yet accrued — the synthetic case filed and the absence stated plainly.
- **AC3** — An Auditor grep finds **no direct read of `events`** outside `argus/data/store.py`.
- **AC4** — `SCHEMA_VERSION` is 10; the migration is idempotent and loses no row (counts before and after).
- **AC5** — Every other table is byte-identical before and after (checksum, CI-9).
- **AC6** — Non-vacuity, mandatory (CI-6): three mutation runs — (a) extending `last_seen` on a changed attribute instead of versioning fails `test_changed_confirmed_opens_a_new_version`; (b) versioning on every refresh fails `test_unchanged_row_extends_last_seen_only`; (c) returning the latest row regardless of `as_of` fails `test_live_as_of_returns_the_row_current_then`.

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC5), and the AC6 mutation runs.

## 8. Implementer notes
The two mutations in AC6(a) and AC6(b) are opposite errors and the tests
are paired against both: version on every refresh and the table grows
without bound while every window is one day wide; version on none and the
original defect returns. The correct behaviour is "version **when a tracked
attribute changes**, extend otherwise", and nothing else.

`time_of_day` deserves the care: before-market and after-market earnings
put the price reaction on different days, so a study that reads the
corrected value rather than the one known at the time measures a gap it
could not have traded.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
