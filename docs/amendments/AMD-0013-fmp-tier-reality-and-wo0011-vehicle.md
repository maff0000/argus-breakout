# AMD-0013 — FMP tier reality: membership without paid constituent endpoints; WO-0011 as the schema vehicle

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/adr/ADR-0003-data-sources.md`; `docs/architecture/DESIGN.md` §3.1; `docs/work-orders/WO-0003-universe-and-membership.md` §2, §4, §5, §6; `AMD-0012` §3 step 1 (superseded); adds `docs/work-orders/WO-0011-actions-schema-correction.md` |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, 2026-10-20: FMP returns **402** on `sp500-constituent`, `historical-sp500-constituent` and `stock-list` for the account's plan, while `profile`, `earnings-calendar`, `dividends-calendar` and `splits-calendar` return **200**; and WO-0002 is already merged (`bdce04d`), so AMD-0012 §3's "fold into the pending delta" has no vehicle |
| **Affects Work Orders** | WO-0003 (open, audited GREEN at `b732626`, delta at `61598ed`), WO-0004 and WO-0005 (open, audited GREEN, deltas pending), WO-0006 (not started), WO-0011 (new) |

## 1. Problem

### (a) The FMP assumption was mine, and it was unverified
ADR-0003 assigned "Constituents (point-in-time), GICS profiles, earnings &
ex-dividend calendars" to **FMP Basic (free)**. The Delivery Controller has
now established by live probe that the two constituent endpoints and
`stock-list` are **402 on this plan**. Three facts about how this happened,
recorded because the pattern matters more than the fix:

1. While choosing providers I read FMP's own documentation page for the
   historical-constituents endpoint and noted that it **"doesn't state a
   plan requirement."** I recorded the uncertainty and then designed as if
   the endpoint were available. Recording a doubt is not resolving it.
2. The cost of the error was deferred to the live operator check — the
   first point where anything actually called the endpoint — which is four
   Work Orders downstream of the decision.
3. The Delivery Controller probed **by status code only and never printed
   the key**, which is exactly right, and reported rather than coding
   around it.

### (b) `adjustments` → `splits`/`dividends` has no vehicle
AMD-0012 §3 step 1 told the Delivery Controller to fold the DDL change into
"the delta already pending under AMD-0011". When I wrote that, PR #3 was
open awaiting its boundary-test delta. It has since merged correctly under
AMD-0011 §3 (`bdce04d`) and the branch is gone. **My instruction referred
to a vehicle that no longer existed.** The Delivery Controller declined to
reopen a closed Work Order on its own authority — correct, and exactly what
DELIVERY-CHAIN §9 requires.

## 2. Change

### A. The schema vehicle is a new Work Order, not a reopened one
DELIVERY-CHAIN §9 already answers this: *"A defect found after merge … is a
**new Work Order** under the same PID … Hotfixes do not exist."* So:

- **AMD-0012 §3 step 1 is superseded.** The `splits`/`dividends` DDL,
  `store.py` readers and schema tests are delivered by **WO-0011**
  (`docs/work-orders/WO-0011-actions-schema-correction.md`, Approved), on
  its own branch off `main`.
- The Delivery Controller's proposal — a fresh branch off `main` for the
  WO-0002 follow-up — was right in substance. It needed a **Work Order
  number**, because an unnumbered follow-up branch would be implementation
  without a Work Order, which the first hard invariant forbids.
- WO-0011 **blocks** the WO-0004 and WO-0005 deltas, which need those
  tables on `main`. AMD-0012 §3 steps 2 and 3 otherwise stand.

### B. FMP: stay on the free tier; membership no longer depends on it
**Decision: do not upgrade the FMP plan for this.** Reasons, in order of
weight:

1. The free tier already serves everything we still need from FMP:
   `profile` (the GICS fallback) and the three calendars that WO-0006
   depends on. All four return 200.
2. **I cannot tell you which tier unlocks `historical-sp500-constituent`.**
   FMP's pricing page does not state it per endpoint, and that exact
   silence is what produced this defect. Paying to find out is the same
   mistake with money attached.
3. The membership data is obtainable free, and WO-0003 already fetches the
   page that carries most of it.

FMP's role in ADR-0003 and DESIGN §3.1 is narrowed to: **`profile` (GICS
fallback) and the earnings / dividends / splits calendars.** Constituents
and membership history are no longer sourced from FMP.

If a later phase wants fundamentals (revenue growth overlays in
PID-ARGUS-0004), FMP Starter earns its cost there on its own merits and can
be evaluated then — against a specific, testable endpoint list rather than
on spec.

### C. Membership without FMP — specified so it does not depend on which free source exists
Confirmed available: the public S&P 500 constituents table carries
`Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry` and **`Date
added`**. Confirmed limitation: the `hanshof` CSV ends **2025-08-23**, so
roughly fourteen months of index changes are missing.

I have **not** been able to confirm from here whether a changes/additions
table exists on that page today, or whether `hanshof` has since updated.
**The Implementer must therefore probe, in this order, and record what it
actually found — not assume.** WO-0003 §2 becomes:

```
build_membership(hanshof, current_table, fmp_changes_or_None, start=date(2015,1,1))
  1. hanshof snapshots → intervals, up to hanshof's last snapshot date H.   source='hanshof'
  2. Gap H→today, by the first source that is actually available:
     a. FMP historical changes, IF the endpoint returns 200              source='fmp'
     b. a changes/additions table on the constituents page, IF present   source='wikipedia-changes'
     c. derivation from the current table (always available):            see below
  3. Record which route was used, in the report AND in membership.source.
```

**Route (c), the derivation, and its honest limits:**
- **Additions are exact.** Any symbol in the current table whose `Date
  added` > H joined in the gap on that date.
  `start_date = Date added`, `source='wikipedia-derived-exact'`.
- **Removals are identifiable but not precisely dateable.** A symbol in
  hanshof's snapshot at H that is absent from the current table left the
  index somewhere in `(H, today]`. Set `end_date = H` (conservative: it
  stops counting as a member at the last date we actually know it was one),
  `source='wikipedia-derived-bounded'`, and record the bound.

`membership.source` therefore carries the **precision** of each row, so
every downstream consumer and audit can see which rows are inferred. A
bounded row understates membership for up to the gap length; that is
visible in the data rather than hidden in a provider's silence.

**WO-0003 §4** gains: `FMPClient.historical_sp500_changes()` and
`current_sp500()` must treat **402/403 as "unavailable", not as failure** —
raise a typed `ProviderUnavailable(ProviderError)` which `refresh()`
catches to fall through to the next route, logging the status code and
**never** the key. A 402 must not abort `universe refresh`.

**WO-0003 §6** acceptance criteria become:
- **AC1** — unchanged in substance, but satisfied from the constituents
  table and `profile` fallback with **no dependency on a paid endpoint**:
  every current member and configured ETF present in `symbols` with a
  non-empty industry group.
- **AC2** — unchanged: `members_on` for 2016-06-30, 2020-03-31 and
  2024-12-31 within ±3 of the hanshof CSV. All three predate H, so the gap
  does not touch them.
- **AC6** — becomes: total FMP calls for one `universe refresh` ≤ 60 **and**
  the run completes successfully when every FMP endpoint returns 402
  (operator check: run once with the real key, once with a key forced to
  402, and file both).
- **AC7** (new) — the membership report states the route used for the gap
  and the count of rows per `source` value. The count of
  `wikipedia-derived-bounded` rows is **reported** and must not exceed 40;
  above that indicates a malfunction rather than ordinary index turnover,
  and is a stop.
- **AC8** (new) — a 402 on any FMP endpoint does not abort `universe
  refresh` (test: `respx` returning 402 → refresh completes, route recorded
  as the next available one).

### D. Dependency note for WO-0004's live checks
WO-0004's AC1 operator check needs a populated `symbols` table, which is
WO-0003's output. Killing the scaffolded live run that stubbed the 402
endpoints was right: a scaffold is fine for unblocking a probe, never for
producing an acceptance figure. Re-run WO-0004's operator checks after
WO-0003 merges, against real `symbols`.

## 3. Order of work
1. **WO-0011** — schema correction. Merge first; the WO-0004 and WO-0005
   deltas need `splits` and `dividends` on `main`.
2. **WO-0003 delta** on its existing branch — the §2C routing, the
   `ProviderUnavailable` handling, and AC6/AC7/AC8 — then re-audit the
   branch whole and merge.
3. **WO-0004 and WO-0005 deltas** (AMD-0012 §3 step 2) — write targets —
   then re-audit each whole and merge. WO-0004's operator checks run after
   step 2 has merged.
4. **P0-D** (WO-0006, WO-0007) proceeds as sequenced.

**Pre-committed acceptance.** WO-0011 and the WO-0003 delta are both
mechanical consequences of this amendment and fully specified above, so
acceptance is granted in advance for each, conditional on: a GREEN
whole-branch re-audit; every acceptance criterion verified with filed
output, including WO-0011 AC4's two mutation runs and WO-0003's AC6 forced-402
run; the diff touching only the files named in §2 for that Work Order plus
evidence and clerical paths; and every other AMD-0010 §2B condition
holding. Any one false → stop and report. The AMD-0012 §3
pre-authorisations for the WO-0004 and WO-0005 deltas stand unchanged.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0013)`.

## 5. Approval
```
Approved by: Claude (Architect), on the Product Owner's standing instruction
             to deliver unguided; the FMP spend decision in §2B is a
             recommendation the Product Owner may overrule
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
