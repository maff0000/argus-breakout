# AMD-0017 — Store relocation safety; a rule that cannot fire is not a pass; WO-0003 is already cleared

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.2, §3.3, §10; `docs/architecture/adr/ADR-0008-container-ready-now-containerised-later.md` (consequences); `docs/governance/ACCEPTED-RESIDUALS.md` (R5 measured figure); `docs/governance/CRITICAL-INVARIANTS.md` (CI-5 scope); adds `docs/work-orders/WO-0012-store-identity-and-vacuous-validation.md` |
| **Related ADR** | ADR-0002, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-20: a copied store kept its DuckDB Parquet view globs pointing at the original absolute path, so the views read the seed directory's empty contents, `prior_close` came back empty, and WO-0004's jump rule "could not be applied" — reported as an observation for the container-readiness work |
| **Affects Work Orders** | WO-0012 (new), WO-0004 (unchanged — its running backfill is unaffected), WO-0003 (no change; see §2D) |

## 1. Problem

### (a) A relocated store reads the wrong data, silently
`argus/data/schema.py` defines `bars_raw`, `bars` and `etf_bars` as
`CREATE OR REPLACE VIEW … FROM read_parquet('<absolute glob>')`, with the
glob baked in at `init_schema()` time from the then-current `store_dir`.
Move or copy the store and the views still point at the original path.
Two failure modes, **both silent**:

1. the old path no longer holds data → every view returns zero rows; or
2. the old path still holds **stale but populated** data → every view
   returns **wrong** rows.

The Delivery Controller hit mode 1 and reported it as a portability
observation. Mode 2 is the more dangerous one and the same defect.

### (b) A rule that cannot fire was being counted as a pass
The downstream symptom is the part that matters. With the views empty,
`prior_close` was empty, so `validate_day`'s 25%-jump rule **had nothing to
compare** — and nothing in the result distinguished *"the jump rule applied
and passed"* from *"the jump rule could not be applied."* That is exactly
CI-6: a check that cannot fail is not a weak pass, it is not a pass. In this
instance the day was rejected anyway on coverage, so the outcome was
conservative by luck. Under mode 2 above — stale-but-populated — the jump
rule would have compared against the wrong prior closes and passed.

This is a genuine defect found by running the thing, not a theoretical one,
and it was surfaced by a careful observation rather than by any check I had
written. The lesson for my own specifications: when I write a rule that
depends on prior state, I must also say what happens when that state is
absent. I did not, in DESIGN §3.3.

## 2. Change

### A. Store identity is recorded and verified
`DESIGN.md` §3.2 gains a table:
```
store_meta     (key TEXT PRIMARY KEY, value TEXT)
                -- key 'store_dir' records the absolute directory the parquet views were built
                -- against, so a relocated store is detected rather than silently misread (AMD-0017).
```
`DESIGN.md` §3.3 gains:
> - The Parquet-backed views bake an absolute glob at `init_schema()` time.
>   `store_meta['store_dir']` records the directory they were built
>   against, and `Store.connect()` verifies it (AMD-0017): read-write
>   recreates the views against the current directory and logs the change;
>   read-only raises `StoreRelocatedError` naming both paths. A missing
>   record means first use, not relocation. Reading a store whose views
>   point elsewhere is prohibited — mode 2 of the defect returns wrong rows,
>   not no rows.

**CI-5** is widened to cover it: *"…and a store whose recorded
`store_dir` does not match the directory it is opened from must not be
read."*

### B. A rule that cannot be applied is recorded as such, never as a pass
`DESIGN.md` §3.3's validation rules gain:
> - Every validation rule that depends on prior state must distinguish
>   **applied-and-passed** from **could-not-be-applied** (AMD-0017, CI-6).
>   For the 25%-jump rule: on a date that has any earlier row in
>   `bars_raw`, `prior_close` missing for more than 5% of that day's
>   members **rejects** the day with reason
>   `jump rule inapplicable: prior_close missing for N of M members`.
>   `jump_rule_applied = False` is legitimate only on a genuine first-ever
>   ingest date, where it is recorded rather than counted as a pass.

This generalises beyond the jump rule: any later rule with a prior-state
dependency inherits the same obligation.

### C. ADR-0008 consequence — recorded for PID-ARGUS-0006
ADR-0008's consequences gain:
> - **A relocated or volume-mounted store needs its views recreated**
>   (AMD-0017). Found in practice when a copied store silently read its
>   source directory. This is precisely the class of host-coupling ADR-0008
>   exists to surface before packaging: in a container the store arrives as
>   a mount at a path that need not match where it was built, so
>   PID-ARGUS-0006's entrypoint must run a read-write `argus init-store`
>   (idempotent) before the pipeline, and the §2A check makes the failure
>   loud if it does not.

### D. WO-0003 (PR #5) is already cleared — this is a context question, not a decision
The Delivery Controller reports WO-0003 "held at the F1 stop … waiting for
your decision." **It was cleared before that report**, and the ruling is in
git:

- **AMD-0016 §2A** (`main` @ `5e95343`) supersedes every "the diff touches
  only …" file list, including the AMD-0014 §3 clause that stopped it.
  `argus/commands/universe_cmds.py` is in WO-0003 §2, so the delta is in
  scope and always was.
- The PR carries an explicit clearing comment.
- WO-0003 must still apply **AMD-0016 §2C** (`symbols` covering every
  symbol in `membership`) before merging; that is work, not a decision.

The Delivery Controller's session was compacted between the ruling and the
report, which is why it is asking again. **That is what the durable-truth
rule is for:** chat is the control surface, git is the authority, so a
compaction loses nothing — the ruling is in `main`, in the amendment, and
on the PR. The correct response to a lost thread is to re-read
`docs/amendments/README.md` and the PR comments, not to wait. No new ruling
exists here because none is needed.

### E. R5 updated with the measured figure
WO-0005's live run gives **current cohort 518/518 = 100%** (AC1a's gate is
99%) and **historical cohort 110/237 = 46.4%**. R5 is amended to carry
46.4% rather than the earlier 79.8%, which was computed on a different
denominator. Stated plainly because it is worse than it first appeared:
**over half of delisted historical members have no bars at all**, so
composites for periods with material turnover lean substantially toward
survivors. CI-8's per-date coverage reporting is therefore not
bookkeeping — it is the only thing standing between that gap and an
unstated optimism in every PID-ARGUS-0004 backtest. The lead-time study
must weight coverage explicitly, not merely record it.

## 3. Sequencing
**WO-0012** (new, Approved) carries §2A and §2B. It is sequenced **after
WO-0004** because both touch `argus/data/validate.py` — a file-conflict
avoidance, not a logical dependency — so **WO-0004's running backfill is
not wasted and must not be restarted for this.** WO-0012 may then run
concurrently with WO-0006 and WO-0007 in P0-D2.

**Pre-committed acceptance** for WO-0012, conditional on: a GREEN
whole-branch audit; AC1–AC3 verified; **AC4's two mutation runs filed and
each failing the intended test**; AC5 and AC6 operator outputs filed with
filesystem paths only; the diff within WO-0012 §2 (AMD-0016 §2A); and every
other AMD-0010 §2B condition. Any one false → stop and report.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0017)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
