# Critical invariants

The short list of properties that **always stop delivery** when they cannot
be met. Standing ruling 7 (DELIVERY-CHAIN §9) lets the Delivery Controller
proceed past an unachievable acceptance criterion by measuring and
recording the shortfall — **except** where it touches one of these. These
are correctness properties whose silent violation produces confidently
wrong numbers rather than a visible gap.

Adding or removing an entry is an Amendment.

| # | Invariant | Where defined | Why it is critical |
|---|---|---|---|
| CI-1 | Every symbol in the fetched current constituents table has exactly one open membership interval; `current_members_without_row` must be 0 | AMD-0014 §2B, AMD-0015 §2A | `members_on(today)` is the universe every nightly scan iterates. A missing row is a company invisible to the product with no error surfaced. |
| CI-2 | A ticker rename is one continuous membership — no date falls between the old and new intervals | AMD-0014 §2C | A hole severs the company's price series, so every 252-day momentum and relative-strength feature across the rename computes on broken data. |
| CI-3 | Membership intervals are closed on both ends; `members_on` is `start_date <= d AND (end_date IS NULL OR d <= end_date)` | AMD-0011 | A one-day error changes which symbols enter every historical composite. |
| CI-4 | `splits` and `dividends` are separate tables with `NOT NULL` measures, keyed `(symbol, date, source)` | AMD-0012 | A nulled split leaves an unadjusted 2:1 discontinuity in the price series, and the validator then misreads its own symptom. |
| CI-5 | Bars are stored with their adjustment basis, and `bars` is materialised from `bars_raw` + actions, never overwritten in place without a new `adj_version` | DESIGN §3.2, §3.3 | Backtests must be reproducible; a silent re-adjustment changes history. |
| CI-6 | Non-vacuity: any test relied on as proof of a behaviour must be shown capable of failing | Forge `EVIDENCE-DOCTRINE.md`; AMD-0011 AC7, AMD-0012 AC4 | A check that cannot fail is not a weak pass, it is not a pass. |
| CI-7 | No secret, IP address, port, account identifier, gateway URL or model alias reaches the repository | `PID.md` §9, AMD-0001, AMD-0009, AMD-0015 §2C | Public repository; a published credential cannot be unpublished. |
| CI-8 | Coverage travels with every aggregate: `n_members` and `n_members_with_bars`/`n_members_classified` per date, breadth never reported bare | AMD-0015 §2B, DESIGN §6.1 | This is the only thing keeping the known survivorship and classification gaps from becoming unstated optimism in every backtest. |

Anything **not** on this list, where an acceptance criterion proves
unachievable because of an external data fact, is handled by standing
ruling 7: measure it, record it, proceed, and file it as a specification
defect for ratification.
