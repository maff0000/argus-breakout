# WO-0017 — spec gaps and deviations for the Architect

1. **AC6(b) cannot fail as written.** The Work Order says that deduplicating on `cash_amount` alone must fail both `test_genuine_pair_survives_dedupe` and `test_equal_specials_with_different_declarations_both_count`. PGR's real pair is 0.10 (frequency 4) against 13.50 (frequency 1): the amounts differ, so an amount-only key keeps both and the first test still passes. Measured by the Implementer and re-measured by the Auditor on a copy under mktemp: under the amount-only mutation only `test_equal_specials_with_different_declarations_both_count` (and `test_same_amount_twice_does_not_collapse`) fail. This is a defect in the WO's expectation, not in the code or the tests, and no test was weakened or contrived to force a failure (Ruling 7: measured, reported, merged under the pre-committed acceptance). `test_genuine_pair_survives_dedupe` still guards the opposite over-dedupe failure that collapses by date alone.
2. **Two files outside WO §2**, both accepted by the Auditor as necessary and minimal: `argus/data/ingest_polygon.py` (the select list must carry `declaration_date` and `frequency` or a re-ingest cannot populate them) and `tests/test_store.py` (column-set assertion). `tests/test_cli.py` was not needed (its version assertion sits in `tests/test_adjust.py::test_cli_migrate_store`). Same class as AMD-0029 §2G: an incomplete §2 list.
3. **Three existing tests changed behaviour, beyond Ruling 9 count edits**, each forced by the new rules and judged by the Auditor to weaken nothing: `test_same_amount_twice_does_not_collapse`, `test_larger_normalised_total_wins_and_warns` (0.15 became 0.20), `test_attribute_pairs_collapse_omission_neither_and_basis_trap`.
4. **`attribute_pairs` still returns collapse / omission / neither**, not the WO's duplicate / genuine / omission labels. The WO §2 asked only for the two extra columns, so the verdicts in `attribution.md` are read from the verbatim payloads.
5. **FCX's twelve exact doublings (0.075 vs 0.15)** now fall into the integer-multiple case and stay on Polygon's lower figure, as the WO's own test table specifies. R9 is therefore no longer resolved to the larger total for those twelve dates; AC3 lists them. If the Architect considers FCX's doubling an omission rather than a duplicate, the integer-multiple rule cannot tell them apart from raw data alone.
6. **SKYD is a cross-ticker duplicate inside yfinance** (one dividend stored under both PSKY and SKYD), not a Polygon duplicate; see `attribution.md`.

## Added at the AMD-0031 delta
1. **AC6(b), first-named test (unchanged from the first audit).** `test_genuine_pair_survives_dedupe`
   cannot fail under an amount-only key because PGR's amounts (0.10, 13.50) differ; the capable tests are
   `test_equal_specials_with_different_declarations_both_count`, `test_differing_frequency_or_declaration_still_sums`
   and `test_same_amount_twice_does_not_collapse`. Reword AC6(b).
2. **AC5 and WO text stale on the schema version.** AC5 still says SCHEMA_VERSION is 7; section 2 and the code say 8
   (AMD-0033 reassignment). The code is right.
3. **Accepted extension outside section 2.** `argus/commands/adjust_cmds.py` (+4 lines) echoes
   `n_ambiguous_groups_resolved_by_default`; section 2(c) requires it to be REPORTED. Listed for ratification.
4. **Sequential resolution of several ambiguous groups in one source (Auditor observation).** Two genuine
   pairs on one ex-date, with the other source at their sum, would each see "neither" and collapse, and be counted as
   defaults. It understates, which is AMD-0031's direction; none exist in the store (default count 0).
5. **dividend_type separates TEL from DVN in the two payloads examined** (see attribution.md). AMD-0031's premise
   that no payload field can is contradicted by this sample; the cross-source rule is nonetheless correct on both.
