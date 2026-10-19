# AMD-0011 — `membership.end_date` is inclusive; consequential test updates; WO-0002 delta

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/pids/PID-ARGUS-0001-foundations.md` §8.5; `docs/work-orders/WO-0002-schema-and-store.md` §2, §4, §5, §6; `docs/governance/DELIVERY-CHAIN.md` §9 (standing rulings) |
| **Related ADR** | ADR-0002 |
| **Raised by** | Delivery Controller, 2026-10-20, declining to self-certify WO-0002 under AMD-0010: `scope_fidelity: no` (an out-of-scope test edit) and an unspecified behavioural choice (`end_date` inclusivity) with the Auditor demonstrating the boundary untested |
| **Affects Work Orders** | WO-0002 (PR #3 open, audited GREEN at `e5682b9`; delta required — §3); WO-0003 (§5 wording confirmed, no change) |

## 1. Problem

**(a) Consequential test edit.** WO-0002 §2 instructs the Implementer to
*remove WO-0001's `init-store` stub* and implement the command. A test
asserting the stub's exit code 2 cannot survive that removal, yet §2 did
not list `tests/test_cli.py` as `modify`. The Implementer had to edit it or
leave the suite failing; the Auditor correctly reported
`scope_fidelity: no`. The defect is in my scope table, and the class will
recur every time a Work Order changes behaviour a predecessor's test pins.

**(b) `membership.end_date` inclusivity unspecified where it was
implemented.** `DESIGN.md` §3.2 defines the column but not whether a symbol
is a member *on* `end_date`. The Implementer chose inclusive. That is a
behavioural choice, not a conventional specification gap, so the Delivery
Controller was right to stop rather than record it under AMD-0010 standing
ruling 2.

**The answer already existed in an approved document, which is why this is
a clarification and not a new decision.** WO-0003 §5 requires
`test_membership_intervals` to assert that *"a symbol removed on date D has
`end_date = D − 1 trading day`"*. If removal on D makes the previous
trading day the last day of membership, then `end_date` **is** the last day
of membership, and the symbol **is** a member on `end_date`. Inclusive. The
Implementer's choice is hereby confirmed, not merely permitted.

**(c) The boundary is untested — the material finding.** The Auditor showed
that changing `>=` to `>` in `members_on` fails no test. The existing
`test_members_on` asserts dates near boundaries (`2023-01-01` against an
`end_date` of `2022-12-31`) but never `d == end_date` or `d == start_date`,
so the inclusivity the whole point-in-time model rests on is unverified.
Membership determines which symbols enter every historical composite, so a
one-day error here silently corrupts every breadth and rotation figure in
PID-ARGUS-0002. This must not merge untested.

## 2. Change

### A. `end_date` semantics, stated explicitly
**`DESIGN.md` §3.2**, the `membership` line, becomes:
```
membership     (symbol TEXT, start_date DATE, end_date DATE NULL, source TEXT)
                -- point-in-time S&P 500. BOTH BOUNDS INCLUSIVE (AMD-0011): a symbol is a member
                -- on start_date and on end_date. end_date NULL = still a member. A removal
                -- effective on date D is stored as end_date = the last trading day before D.
```
**`DESIGN.md` §3.3** gains a rule:
> - Membership intervals are **closed on both ends** (AMD-0011):
>   `members_on(d)` is `start_date <= d AND (end_date IS NULL OR d <= end_date)`.
>   Re-added symbols get a second interval; intervals for one symbol never
>   overlap.

**Phase PID §8.5**, the `members_on` signature, gains:
`# closed interval both ends; end_date NULL = current (AMD-0011)`.

### B. Standing ruling — consequential test updates
`DELIVERY-CHAIN` §9 standing rulings gain **6**:
> 6. **Consequential test update.** An Implementer may modify an existing
>    test that asserts behaviour this Work Order's §2 **explicitly
>    changes**, without that counting as a scope breach, provided all three
>    hold: the edit is confined to that test's assertions (no new
>    behaviour, no other test touched); coverage is not reduced — the
>    replacement asserts the **new** behaviour at least as strongly as the
>    old asserted the old; and the Implementer names the test and the
>    reason in its report. The Delivery Controller records it in
>    `docs/evidence/WO-NNNN/spec-gaps.md`, and an Auditor's
>    `scope_fidelity: no` raised solely on such an edit is **procedural and
>    non-blocking**. Touching a test whose behaviour the Work Order does
>    **not** change remains a stop.

### C. WO-0002 scope corrections
**§2** gains:
```
tests/test_cli.py                    modify  replace test_init_store_stub_exits_2 with a test of the
                                             implemented command (WO-0001's stub is removed by this WO) — AMD-0011
```
**§4** gains:
> `membership` intervals are **closed on both ends** (AMD-0011):
> `members_on(d)` must be
> `start_date <= d AND (end_date IS NULL OR end_date >= d)`, with NULL
> `end_date` meaning current membership.

**§5** gains:
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_store.py::test_members_on_boundaries` | both interval bounds are inclusive and NULL is open-ended | asserts `d == start_date`, `d == end_date`, `d == start_date − 1 day` and `d == end_date + 1 day` for a closed interval, and `d == start_date` plus a far-future date for a NULL interval |

**§6** gains:
> - **AC7** — Interval boundaries are inclusive **and demonstrably tested**
>   (AMD-0011). Non-vacuity is mandatory: with `test_members_on_boundaries`
>   in place, changing `end_date >= ?` to `end_date > ?` **and** separately
>   `start_date <= ?` to `start_date < ?` must each make it fail. File both
>   mutation runs and their failure output.

### D. Specification gaps ratified (no action)
From `docs/evidence/WO-0002/spec-gaps.md`:
1. **`# noqa: F401, E402` on the `argus/cli.py` import line** — ratified.
   AMD-0002's append-only import block sits after the sub-app
   registrations, so `E402` is structural and `F401` is inherent to a
   registration-only import. Conventional and zero-consequence.
2. **`features` table carrying only `(date, symbol)`** — ratified and
   correct. `DESIGN.md` §3.2 defines it as `(date, symbol, <one column per
   §5 feature>)`; the feature columns arrive with PID-ARGUS-0002. A minimal
   table now is the right outcome, not an omission.
3. **Empty placeholder parquet files** — ratified; WO-0002 §8 explicitly
   required them so the DuckDB views resolve over empty directories.

## 3. Sequencing, and acceptance of the delta without a second handshake

PR #3 is **not** accepted at `e5682b9`: the boundary test gap in §1(c) is a
genuine non-vacuity failure on the central property of the point-in-time
model, and it should not merge untested.

Dispatch a fresh Implementer for a delta on `wo/0002-schema-and-store`
covering **only**: the §5 `test_members_on_boundaries` test, and — if and
only if the implementation does not already match §2C — the `members_on`
predicate. The implementation at `e5682b9` already reads
`start_date <= ? AND (end_date IS NULL OR end_date >= ?)`, which is
correct, so the expected delta is **the test and nothing else**. Then
re-run the mechanicals and re-audit the branch whole.

**Pre-committed acceptance for this delta (AMD-0011 §3).** WO-0002 has
triggered an Amendment, so AMD-0010's mandate excludes it. In its place the
Architect grants acceptance **in advance, for this delta only**, conditional
on all of the following:
1. The re-audit at the new head returns `AUDIT_VERDICT: GREEN` with no
   findings other than procedural ones or accepted residuals.
2. `test_members_on_boundaries` exists and asserts all six cases in §2C.
3. **Both** mutations in AC7 were run and **each** made that test fail,
   with the failure output filed.
4. The delta diff touches only `tests/test_store.py` (plus evidence and
   clerical paths). Any other production-code change voids this
   pre-authorisation.
5. All of AMD-0010 §2B conditions 2, 3, 5, 6, 7 and 9 hold.

All five true → file `acceptance.md` citing `AMD-0011 §3`, merge, close
WO-0002, and start WO-0003, WO-0004 and WO-0005 concurrently. Any one false
→ stop and report.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0011)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
