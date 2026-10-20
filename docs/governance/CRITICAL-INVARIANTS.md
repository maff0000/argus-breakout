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
| CI-5 | Bars are stored with their adjustment basis, and `bars` is materialised from `bars_raw` + actions, never overwritten in place without a new `adj_version`; **and a store whose recorded `store_dir` does not match the directory it is opened from must not be read** | DESIGN §3.2, §3.3; AMD-0017 §2A | Backtests must be reproducible; a silent re-adjustment changes history, and a relocated store's views return wrong rows rather than none. |
| CI-6 | Non-vacuity: any test relied on as proof of a behaviour must be shown capable of failing | Forge `EVIDENCE-DOCTRINE.md`; AMD-0011 AC7, AMD-0012 AC4 | A check that cannot fail is not a weak pass, it is not a pass. |
| CI-7 | No secret, IP address, port, account identifier, gateway URL or model alias reaches the repository | `PID.md` §9, AMD-0001, AMD-0009, AMD-0015 §2C | Public repository; a published credential cannot be unpublished. |
| CI-8 | Coverage travels with every aggregate: `n_members` and `n_members_with_bars`/`n_members_classified` per date, breadth never reported bare | AMD-0015 §2B, DESIGN §6.1 | This is the only thing keeping the known survivorship and classification gaps from becoming unstated optimism in every backtest. |
| CI-9 | `bars_raw` is never filtered by a validation verdict: every row a provider returns is stored, and quality judgements are recorded separately in `ingest_log` and `bar_flags` | AMD-0018 §2A; DESIGN §3.3 | Gating the raw layer deletes the evidence a rejection has to be diagnosed from, makes a rule change cost a full re-fetch, and makes a validator's input depend on its own verdicts — which is how one real price move rejected 268 days. |

Anything **not** on this list, where an acceptance criterion proves
unachievable because of an external data fact, is handled by standing
ruling 7: measure it, record it, proceed, and file it as a specification
defect for ratification.
