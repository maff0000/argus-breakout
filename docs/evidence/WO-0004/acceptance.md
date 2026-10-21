# WO-0004 — Acceptance (delegated, AMD-0010 §2B; pre-committed by AMD-0018 §3)

| # | Condition | Result | Evidence |
|---|---|---|---|
| 1 | AMD-0010 §2B conditions 1–9 | **true** | independent audit GREEN on the whole branch with one non-blocking scope observation (`audit.md`); diff within §2 plus two mechanically necessary test edits flagged for ratification (`spec-gaps.md` 1); 222 tests, ruff, ADR-0008 greps, gitleaks clean (`tests.md`); commit identity clean over `9a7a505..HEAD`; no IP in any evidence file |
| 2 | AC2 re-run shows no day quarantined on the ≥20% breadth rule, or each has a stated non-market cause | **true** | 0 quarantined days of 520 (499 ok, 21 holiday); max member-flag share on any day 0.42% (`operator-checks.md`) |
| 3 | `jump_unexplained` flags exist and are listed | **true** | 128 rows, 99 dates, 81 symbols; the 41 member rows are listed in `operator-checks.md`; zero flags would have been a stop |
| 4 | STI, AIV, NKTR appear in no day-level verdict | **true** | no day carries a verdict other than ok/holiday; the three symbols have 22 flag rows, none on a date they were members (no membership/CI-1 question arises) |
| 5 | AC4 non-vacuity mutation runs filed | **true** | `audit.md`: nine mutants all killed by the intended tests, plus the Implementer's two |

Also: AC7 revalidate over 500 days, no provider call, `bars_raw` digest unchanged; AC3 46 splits + 5,448 dividends with the five 2026 splits present. Critical invariants: CI-9 held (500 dates, 312,025 rows stored, none withheld), CI-6 non-vacuity shown by mutation, CI-7 hygiene greps clean. Residuals for the Architect: `spec-gaps.md`.
