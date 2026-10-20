# AMD-0015 — The invariant is unconditional; delisted-history coverage and survivorship bias; evidence hygiene

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/work-orders/WO-0003-universe-and-membership.md` §2, §4, §6; `docs/work-orders/WO-0005-bootstrap-history.md` §2, §6; `docs/architecture/DESIGN.md` §3.3, §6.1; `docs/governance/ACCEPTED-RESIDUALS.md`; `docs/governance/prompts/DELIVERY-CONTROLLER-PROMPT.md` |
| **Related ADR** | ADR-0003; AMD-0014 |
| **Raised by** | Delivery Controller, 2026-10-20: (a) WO-0003's invariant was enforced only when `as_of >= today`, so a back-dated run reported `current members without row: 18` and exited 0; (b) WO-0005's live bootstrap reaches 79.8%, not AC1's 98%, because yfinance has no data for 127 of 628 delisted or renamed tickers; (c) an internal IP address was filed in WO-0011's Auditor-prompt evidence, already on `main` |
| **Affects Work Orders** | WO-0003 (delta in progress), WO-0005 (open, audited GREEN, merge held), WO-0011 (merged — evidence correction only) |

## 2A. The invariant is unconditional, and back-dated refresh is unsound

The Delivery Controller is right that enforcing the invariant only for
`as_of >= today` reports a shortfall as a statistic, which AMD-0014 §2B
forbids. Its proposed fix — "computed relative to `as_of`" — is **not
correct**, and the reason matters:

The constituents table is only ever available **as of now**. There is no
historical snapshot of it. So "current members without a row, relative to a
past `as_of`" is a question about two different points in time: today's
constituent list against a past membership state. Many of today's members
were not members then, so the count is meaningless rather than merely
wrong.

**Ruling, two parts:**

1. **The invariant is computed against the fetched current table, always,
   independent of `--date`.** It asserts that every symbol in the table
   just fetched has exactly one row with `end_date IS NULL`. That is a
   statement about rows existing, not about membership on a date, so it
   holds for every run. `current_members_without_row != 0` exits non-zero
   under every invocation (AC9, unchanged).
2. **`universe refresh --date` rejects a date more than 7 calendar days in
   the past**, exit 2, with the message that the current constituents table
   has no historical snapshot so a back-dated refresh cannot be correct.
   Historical membership comes from hanshof plus the gap derivation, which
   is already as-of-independent — it builds the whole interval table in one
   pass — so nothing legitimate needs a back-dated refresh. The 7-day
   window exists only so WO-0009's nightly run can pass the most recent
   trading date.

Defining semantics for an operation that cannot be performed correctly is
worse than refusing it.

WO-0003 §6 gains **AC10** — a `universe refresh --date <30 days ago>` exits
2 and writes nothing (operator check: exit status and an unchanged store
row count), and a `--date` of today or the last trading day succeeds.

## 2B. Delisted history: AC1 was unreachable, and the shortfall has a product consequence

WO-0005 AC1 required "≥ 98% of symbols in `symbols` ∪ historical
`membership`". yfinance has nothing for 127 of 628 tickers — delisted
symbols are frequently purged from that source. **The criterion was
unreachable from the source I specified; that is my error, not a delivery
failure.**

But the shortfall is **not** harmless, and must not be waved through as a
threshold adjustment. Missing delisted members is precisely the
**survivorship bias** that ADR-0003 and DESIGN §3.3's point-in-time
membership exist to avoid. A composite built from members whose bars
survive is a composite of survivors: breadth and relative-strength figures
for older periods will read better than reality, and PID-ARGUS-0004's
lead-time study would inherit that optimism silently.

**Ruling — split the criterion, then make the residual measurable
downstream:**

WO-0005 §6 replaces AC1 with:
- **AC1a** — of the symbols that are **current** members or configured
  ETFs, **≥ 99%** have bars written for the requested range. These are
  live tickers; anything below 99% is a delivery defect. Operator check:
  count, percentage, and the exception list with a reason per symbol.
- **AC1b** — of the symbols that appear **only** in historical
  `membership` (delisted or renamed away), coverage is **reported with no
  threshold**: the count written, the count unavailable, the percentage,
  and the full unavailable list filed in
  `docs/evidence/WO-0005/delisted-coverage.md`. A shortfall here is a
  recorded limitation of the free source, not a failure — provided it is
  recorded.

WO-0005 §2 gains: `BootstrapResult` separates `current_written`,
`current_failed`, `historical_written`, `historical_unavailable`, and the
exit rule of AMD-0012/AMD-0014 §2E applies to the **current** cohort only
(written + skipped vs failed). Historical unavailability never sets a
non-zero exit.

**DESIGN §3.3** gains:
> - Bars coverage for delisted historical members is incomplete (AMD-0015):
>   the free source serves no data for a material share of them. Every
>   consumer of `composites` must therefore carry coverage with the figure
>   it reports — see §6.1.

**DESIGN §6.1** gains:
> `composites` and every breadth field carry `n_members` **and**
> `n_members_with_bars` for each date, and the equal-weight composite is
> computed over members with bars. A breadth percentage is reported
> alongside its coverage ratio, never bare. Where coverage on a date is
> below 95%, that date's breadth figures are flagged in
> `market_daily.coverage_flag` and excluded from PID-ARGUS-0004's lead-time
> study unless explicitly included. This is how the survivorship bias of
> §3.3 stays visible instead of becoming an unstated optimism in every
> backtest.

New accepted residual **R5** records the limitation, its cause, and the
mitigation above. It is accepted because no free source covers delisted
history well — this is what paid point-in-time datasets exist for — and
because the mitigation makes the bias measurable per date rather than
hidden.

## 2C. Evidence hygiene: scrub forward, and stop composing the leak

An internal IP address was filed in WO-0011's Auditor-prompt evidence and
is on `main`. It is not a credential and it is a private-range address, but
PID §9 forbids it.

**Ruling:**
1. **Scrub the working tree, do not rewrite history.** Replace the address
   with `<delivery-host>` in a commit on the WO-0003 branch, with a message
   naming it as an AMD-0015 §2C evidence correction, and add a one-line
   note in `docs/evidence/WO-0011/` recording that the pre-correction
   commit retains the value. Rewriting `main` is forbidden
   (DELIVERY-CHAIN §7) and would not un-publish anything in any case: a
   public repository's history is already mirrored by anyone who cloned it.
   Claiming a force-push had removed it would be the real failure here.
2. **Fix the cause, not just the instance.** The Auditor prompt is filed
   **verbatim** by design, so redaction at filing time would corrupt the
   record. The address must therefore never be composed into the prompt in
   the first place. The Delivery Controller prompt gains: *dispatch prompts
   name hosts as `dell-debian` and paths as absolute paths — never an IP
   address or port. Then the verbatim filing is clean by construction.*
3. Carrying the fix on the WO-0003 branch is ratified as a clerical
   evidence write (DELIVERY-CHAIN §6.4), notwithstanding that it touches
   another Work Order's evidence directory.

## 3. Sequencing and acceptance
The WO-0003 delta absorbs §2A (unconditional invariant, AC10) and §2C's
scrub. WO-0005 needs no code change for §2B beyond the `BootstrapResult`
split and the evidence file; its audit at `2c5a8a2` is GREEN and the
AMD-0014 §2E fix is confirmed, so re-audit only the delta.

**Pre-committed acceptance** for both, conditional on: a GREEN whole-branch
re-audit; AC9 reporting 0 and AC10's two runs filed for WO-0003; AC1a ≥ 99%
with the exception list, and AC1b's `delisted-coverage.md` filed, for
WO-0005; no IP address anywhere in the diff or in any evidence file
(`grep -rnE '([0-9]{1,3}\.){3}[0-9]{1,3}' docs/` empty apart from the
§2C note); and every other AMD-0010 §2B condition holding. Any one false →
stop and report.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0015)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-20
Commit:      the commit introducing this file
```
