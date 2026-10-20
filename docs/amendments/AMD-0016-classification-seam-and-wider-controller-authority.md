# AMD-0016 — The classification seam; rename-aware bars lookup; wider Delivery Controller authority

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.3, §4, §6.1; `docs/work-orders/WO-0003-universe-and-membership.md` §2, §6; WO-0004 §2, §4, §6; WO-0005 §6; WO-0007 §2, §4; `docs/governance/DELIVERY-CHAIN.md` §9; `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md`; AMD-0011 §3, AMD-0012 §3, AMD-0013 §3, AMD-0014 §3, AMD-0015 §3 (pre-authorisation scope clauses, all superseded by §2A); adds `docs/governance/CRITICAL-INVARIANTS.md` |
| **Related ADR** | ADR-0003, ADR-0005 |
| **Raised by** | Architect, on the Product Owner's observation that too much still routes through him. Three of the last four Delivery Controller stops were caused by my own documents, not by genuine architectural questions |
| **Affects Work Orders** | WO-0003 (#5), WO-0004 (#7), WO-0005 (#6) — all three unblocked here; WO-0007 (gains the rename rule for P0-D) |

## 1. Problem — diagnosis before patch

Four consecutive stops, classified by cause:

| Stop | Cause | Mine? |
|---|---|---|
| WO-0003 §3 file-list excludes `universe_cmds.py`, which WO-0003 §2 requires | My pre-authorisation listed files **more narrowly than my own Work Order scope** | Yes |
| WO-0005 AC1 unreachable (127 delisted tickers absent from yfinance) | My acceptance criterion specified a figure the source cannot produce | Yes |
| WO-0004 rejects 210 days: historical members have no industry group | A **seam** between WO-0003's `symbols` population and WO-0004's validation rule, invisible until the live run | Yes |
| Rename price-series question | A genuine architectural question for P0-D | No |

Two structural faults, both mine:

1. **Double-gating.** Every delta pre-authorisation restated a file list
   alongside the condition "the diff stays within the Work Order's §2
   Scope". The file list can only ever be narrower than §2, so it generates
   false stops on legitimate work and adds nothing — §2 conformance is
   already independently verified by the Auditor's `scope_fidelity`.
2. **No authority to proceed past my own bad criterion.** Standing ruling 2
   covers conventional zero-consequence *choices*. It does not cover an
   acceptance criterion that is simply unachievable because of an external
   data fact. So every one of those returns here, even when the honest
   response — measure it, record it, carry on — is already the established
   pattern in AMD-0015 §2B.

## 2. Change

### A. Delta pre-authorisations are bounded by §2 Scope, not by a file list
Every "the delta diff touches only …" clause in AMD-0011 §3, AMD-0012 §3,
AMD-0013 §3, AMD-0014 §3 and AMD-0015 §3 is **superseded**. The binding
condition is AMD-0010 §2B condition 4: the diff stays within the Work
Order's **§2 Scope** and touches no §3-excluded path, as verified by the
Auditor's `scope_fidelity` plus evidence and clerical paths. Future
amendments state scope bounds by reference to §2 and **must not restate a
file list**.

**WO-0003 (#5) is cleared on this basis**: `argus/commands/universe_cmds.py`
is in WO-0003 §2, so the delta is within scope. The Delivery Controller was
right not to waive the condition itself; the condition was wrong.

### B. Standing ruling 7 — unachievable or inconsistent acceptance criterion
`DELIVERY-CHAIN` §9 standing rulings gain:

> 7. **Unachievable or inconsistent acceptance criterion (AMD-0016).** Where
>    an acceptance criterion cannot be met **because of an external data
>    fact rather than an implementation shortcoming**, and the honest
>    response is to measure and record rather than to change behaviour, the
>    Delivery Controller may proceed. It must: establish the cause with
>    evidence (what the source does and does not provide, with counts);
>    apply the coverage-reporting pattern — report the shortfall as a named
>    figure beside the aggregate it affects, never bare; record it in
>    `docs/evidence/WO-NNNN/spec-defects.md` with the criterion quoted and
>    the achievable figure stated; and continue to merge under the Work
>    Order's pre-committed acceptance.
>
>    **Three hard guards. Any one of them means stop:**
>    - the criterion touches an entry in
>      `docs/governance/CRITICAL-INVARIANTS.md`;
>    - the fix would change **behaviour** rather than reporting;
>    - the shortfall would weaken a non-vacuity requirement, or make a
>      check incapable of failing.
>
>    This authority is to proceed past *my* bad criterion, not to lower a
>    bar. A criterion that is merely *hard* to meet is not unachievable.

### C. The classification seam — ruled
**Root cause, mine.** DESIGN §3.3's validation rule rejects a day if "any
member lacks `gics_industry_group`". I wrote that to catch an unclassified
*current* member — a real defect. Applied to a historical date, where
`members_on(d)` includes delisted tickers that `symbols` never held, it
rejects every day before hanshof's last snapshot. The rule was
miscalibrated, not the provider.

1. **`symbols` covers every symbol that ever appears in `membership`**, not
   only current members (WO-0003 §2). Classification for a historical-only
   symbol is obtained, in order: the rename target's group for a mapped
   rename (same company, so the group is correct); else FMP `profile`,
   which the free tier serves; else left NULL and **counted**.
2. **The validation classification check applies to current members only**
   (DESIGN §3.3, WO-0004 §2/§4). A historical-only member without a group
   never rejects a day. Instead `validate_day` returns
   `n_unclassified_members` and the day is stored.
3. **Coverage travels with the aggregate**, consistent with AMD-0015 §2B:
   `composites` carries `n_members_classified` beside `n_members` and
   `n_members_with_bars`; a sector or industry-group composite is computed
   over classified members only, and its coverage ratio is reported with
   it (DESIGN §6.1, CI-8).
4. **The 95% bars-coverage gate stands** — that is a data-completeness
   check and it was not the thing failing.

### D. Rename-aware bars lookup — ruled now for P0-D
The Delivery Controller reports that yfinance serves BK, FI and MMC history
only under their **new** tickers. So a historical member's bars live under
the current symbol while `membership` names the old one — a composite on a
2020 date would look up `BK`, find nothing, and lose coverage.

**Rule (DESIGN §4, WO-0007 §2/§4):** resolving bars for a member follows
the rename chain **forward** to the current symbol via
`config/ticker_renames.yaml`. `Store` gains
`resolve_symbol(symbol, as_of) -> str` returning the symbol under which
bars for that date are stored. Membership keeps the historically correct
ticker (CI-2 is about membership continuity, not storage); only the bars
lookup is redirected, and the redirection is recorded so a reader can see
it happened. Where a rename chain is unmapped, the member counts as
`without bars` in CI-8's coverage rather than silently dropping out.

### E. The three open PRs — rulings
1. **WO-0003 (#5), GREEN at `4c10c60`:** cleared by §2A. Merge under its
   existing pre-committed acceptance. The `universe_cmds.py` change is in
   §2 and always was.
2. **WO-0005 (#6), GREEN at `2c5a8a2`:** AC1 was already replaced by
   AMD-0015 §2B with AC1a/AC1b, which the branch pre-dates. Apply the
   `BootstrapResult` cohort split and file `delisted-coverage.md`, then
   merge: no current member or ETF failed, which is AC1a satisfied, and the
   127 delisted absences are AC1b's reported figure. Under §2B this needed
   no ruling from me — it is the archetype of standing ruling 7.
3. **WO-0004 (#7), GREEN at `db714d9`:** apply §2C, re-run the backfill, and
   merge. AC3's absent same-date split-and-dividend pair in Polygon's window
   is **ratified as covered** by the unit tests plus WO-0005's three
   yfinance pairs — the criterion is that the system retains both rows, and
   that is proven. The operator checks running before WO-0003 merged is
   ratified: disclosed, and the ordering existed to guarantee real
   `symbols`, which §2C now changes anyway.

## 3. Expected effect
Of the four stops above, §2A removes the first class outright, §2B removes
the second, and §2C plus §2D removes the third and the fourth by settling
the seam and the rename rule for every downstream Work Order. What should
still stop: WO-0008 and WO-0009 (Route B by design), a first-audit RED, a
critical-invariant breach, and a genuine architectural question. If a stop
arrives that is none of those, the fault is in my documents again and the
remedy is another structural amendment, not another adjudication.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0016)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
