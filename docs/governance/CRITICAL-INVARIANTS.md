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
| CI-2 | A ticker rename is one continuous membership — no date falls between the old and new intervals. **Scope (AMD-0025 §2C): verified only for pairs declared in `config/ticker_renames.yaml`.** An undeclared rename is not checked and presents as an index exit plus a separate addition. **Detection from stored data was attempted at WO-0015 and is NOT POSSIBLE** (AMD-0027 §1c): index maintenance is pairwise, so every addition has an adjacent leaver, and 500 candidates resulted. The map stays **operator-maintained from index announcements**. An undeclared rename is an **R8/R5 coverage gap** — the old ticker becomes a member without bars in historical composites, which CI-8 already reports — **not** a severed price series, because both free sources serve a renamed company's whole history under the new ticker, so the successor's own features are unaffected (AMD-0027 §1c corrects AMD-0025 §1b). This invariant's harm statement applies to a **declared** rename bounded wrongly | AMD-0014 §2C, AMD-0025 §2C, AMD-0027 §1c | A hole severs the company's price series, so every 252-day momentum and relative-strength feature across the rename computes on broken data. |
| CI-3 | Membership intervals are closed on both ends; `members_on` is `start_date <= d AND (end_date IS NULL OR d <= end_date)` | AMD-0011 | A one-day error changes which symbols enter every historical composite. |
| CI-4 | `splits` and `dividends` are separate tables with `NOT NULL` measures. `splits` is keyed `(symbol, date, source)`; **`dividends` is keyed `(symbol, date, source, vendor_id)`** (AMD-0027 §2A). A source may legitimately report several dividends on one ex-date — **measured at WO-0015: PGR 2026-01-02 carries a 0.10 quarterly and a 13.50 special, and the narrower key stored only the 0.10.** `dividend_type` does not discriminate (both records are "CD"); the vendor's own record `id` does. The adjustment sums an ex-date's records. Until WO-0016 lands, `adj_close` on the thirteen measured ex-dates is **suspect, not trusted** | AMD-0012, AMD-0025 §2B, AMD-0027 §2A | A nulled split leaves an unadjusted 2:1 discontinuity in the price series, and the validator then misreads its own symptom. |
| CI-5 | Bars are stored with their adjustment basis, and `bars` is materialised from `bars_raw` + actions, never overwritten in place without a new `adj_version`; **and a store whose recorded `store_dir` does not match the directory it is opened from must not be read** | DESIGN §3.2, §3.3; AMD-0017 §2A | Backtests must be reproducible; a silent re-adjustment changes history, and a relocated store's views return wrong rows rather than none. |
| CI-6 | Non-vacuity: any test relied on as proof of a behaviour must be shown capable of failing | Forge `EVIDENCE-DOCTRINE.md`; AMD-0011 AC7, AMD-0012 AC4 | A check that cannot fail is not a weak pass, it is not a pass. |
| CI-7 | No secret, IP address, port, account identifier, gateway URL or model alias reaches the repository | `PID.md` §9, AMD-0001, AMD-0009, AMD-0015 §2C | Public repository; a published credential cannot be unpublished. |
| CI-8 | Coverage travels with every aggregate: `n_members` and `n_members_with_bars`/`n_members_classified` per date, breadth never reported bare | AMD-0015 §2B, DESIGN §6.1 | This is the only thing keeping the known survivorship and classification gaps from becoming unstated optimism in every backtest. |
| CI-9 | `bars_raw` is never filtered by a validation verdict: every row a provider returns is stored, and quality judgements are recorded separately in `ingest_log` and `bar_flags` | AMD-0018 §2A; DESIGN §3.3 | Gating the raw layer deletes the evidence a rejection has to be diagnosed from, makes a rule change cost a full re-fetch, and makes a validator's input depend on its own verdicts — which is how one real price move rejected 268 days. |

Anything **not** on this list, where an acceptance criterion proves
unachievable because of an external data fact, is handled by standing
ruling 7: measure it, record it, proceed, and file it as a specification
defect for ratification.
