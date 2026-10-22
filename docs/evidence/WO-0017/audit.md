# Independent Audit — WO-0017 (audit 1)

Auditor: a fresh Agent (not a fork), offline, on a `git archive` copy of the audited SHA.
The Auditor's final report follows; its prompt is `auditor-prompt.md`.

```
AUDIT_VERDICT: GREEN
work_order: WO-0017
base_sha: 2a59157515c5420c98270dd289e345b4f7fd9f00
commit_sha: 3551139956e3f5ad4fde2b88c956de78560b07ab
scope_fidelity: yes (two accepted extensions outside WO §2: argus/data/ingest_polygon.py, tests/test_store.py)
offline_tests_pass: yes (338 passed, 1 deselected, 313s, on a git-archive copy of the audited SHA, env -i, no .env, no network)
non_vacuity_established: yes (mutations a/b/c on a copy under mktemp)
gitleaks_clean: yes (126 commits, no leaks)
access_mechanism: ssh
write_visibility_verified: n/a (local to execution host)
public_hygiene_clean: yes
commit_identity_clean: yes (only "Rogue (Delivery Controller) <noreply@anthropic.com>")
AC1_verified: no (operator check)
AC2_verified: no (operator check; dividend_dedupe_counts exists and is tested; PGR lands in genuine)
AC3_verified: no (operator check; every multiple pair emits a dividend_integer_multiple warning)
AC4_verified: no (operator check; PGR 0.10 + 13.50 = 13.60 in the unit test)
AC5_verified: yes for code and tests (SCHEMA_VERSION 7; migration idempotent, no row loss, bars_raw checksum equal, re-run populates the new columns); the live checksum is an operator check
AC6_verified: yes (a and c as written, b with the disclosed deviation)
findings: none
confidence: high
```

## Scope
- 11 files in the diff, all inside WO §2 except two accepted extensions.
- `tests/test_cli.py` is not in the diff: its schema-version change landed in `tests/test_adjust.py::test_cli_migrate_store`, the same clerical change in a file already in scope.
- `argus/data/ingest_polygon.py`: accepted extension. Necessary because the select list would otherwise drop the two new columns and a re-ingest could not populate them; adds two column names and a docstring note.
- `tests/test_store.py`: accepted extension. Adds the two new names to the column-set assertion; no assertion weakened.
- No §3 exclusion touched (`renames.py`, `ibkr.py`, `reconcile.py`, `pipeline.py`, `docs/`).

## Judgement points
1. **Dedupe key** is `(round(cash_amount, 6), declaration_date, frequency)` inside one (symbol, date, source). Records are sorted by `vendor_id` first, so the result does not depend on storage order (20 random shuffles of a 4-record case gave one outcome). Float noise handled (0.1+0.2 and 0.3 collapse). Constructed cases: three identical records collapse to one; same amount and declaration date but different frequency stay two; two equal specials declared on different dates plus a true duplicate of one give 2 records and 1.00; PGR 0.10 + 13.50 gives 13.60 and still matches yfinance at 13.60.
2. **NULL fallback** applies per source, only to a source with more than one record, keys on amount alone and always emits `dividend_dedupe_weakened`. It can merge two genuine equal specials only while the fields are NULL, as the WO specifies; once populated they stay separate.
3. **`integer_multiple`** returns k >= 2 only when `|hi - k*lo| <= 0.01`; equal totals give None; 0.30 vs 0.70 gives None and 0.30 vs 0.90 gives 3; it is called on the normalised totals (Polygon as-paid 2.0 vs yfinance 1.0 with a 2:1 split after the ex-date is equal after normalisation, no warning; as-paid 3.0 vs 0.75 is a 2x multiple only after normalising). A multiple's gap is at least 50% of the larger total, so it can never fall inside the AMD-0027 2D 2% band; the two rules cannot overlap.
4. **Three changed existing tests** were each forced by the new rules and none weakens coverage: `test_same_amount_twice_does_not_collapse` (records now carry different declaration dates; still asserts two records and a 1.00 factor), `test_larger_normalised_total_wins_and_warns` (0.15 became 0.20 because 0.075 vs 0.15 is now a multiple; FCX's doubling is pinned in `test_non_multiple_omission_still_takes_larger`), `test_attribute_pairs_collapse_omission_neither_and_basis_trap` (gained the two fields and assertions on the new columns; original verdict assertions unchanged).
5. **Migration** is gated on all four columns, so a re-run is a no-op; it keeps existing `vendor_id` values (a schema-6 store with real ids keeps them); the new test checks rows 3 to 3, NULL backfill, version 7, idempotent second run, `bars_raw` checksum equal (CI-9), re-ingest over the same keys populating the columns, yfinance staying NULL.
6. **FCX** confirmed: Polygon 0.075 against yfinance 0.15 now emits `dividend_integer_multiple ... multiple=2x left on source precedence (polygon)`; the amount stays 0.075 with `total_source` polygon. The same happens for TEL (1.30, polygon) and SKYD (0.05, polygon).

## Mutation runs (copy under mktemp, restored and re-passed afterwards)
- (a) dedupe removed: `test_duplicate_record_is_deduplicated` fails, as do `test_null_fields_weaken_dedupe_and_warn`, `test_dedupe_is_per_source`, `test_dividend_dedupe_counts_separates_collapsed_from_preserved`.
- (b) key reduced to the amount alone: only `test_equal_specials_with_different_declarations_both_count` fails (and `test_same_amount_twice_does_not_collapse`).
- (c) integer-multiple exclusion dropped: `test_integer_multiple_does_not_trigger_larger_wins` fails, as does `test_non_multiple_omission_still_takes_larger`.

The Implementer's disclosure on (b) holds: `test_genuine_pair_survives_dedupe` cannot fail under an amount-only key because PGR's amounts differ (0.10 vs 13.50), so it passes in mutation (b). That is a gap in the Work Order's AC6(b) wording, not in the code (see `spec-gaps.md`). AC6(b) is satisfied by `test_equal_specials_with_different_declarations_both_count`.

## Offline, portability and architecture
No absolute system paths or `uv`/`systemd` words in `argus/`; no `.env` in the audit copy; configuration untouched; the new SQL is parameterised or column-only.

## Observations (not findings)
- FCX's twelve exact doublings (R9) now show as `dividend_integer_multiple` and stay on Polygon at 0.075; this is the WO-specified behaviour. AC3 lists them.
- `integer_multiple(0.005, 0.01)` returns 2 as a bare function; unreachable from `resolve_dividends` because the one-cent gate comes first.
- Legacy rows with NULL fields dedupe on amount alone until `ingest polygon-actions` is re-run (the warned, specified fallback), so that ingest is run before the live AC2 counts.

# Independent Audit — WO-0017 delta (audit 2, AMD-0031)

Auditor: a fresh Agent (not a fork), on a `git archive` copy of b9defa2, reading the Delivery Controller's gate output.
Its prompt is `auditor-prompt-delta.md`.

```
AUDIT_VERDICT: GREEN
work_order: WO-0017 (AMD-0031 delta audit, 28321fa..b9defa2)
base_sha: 28321fa
commit_sha: b9defa2d944c555da5f9ef84c65a9cc135fd4ca2
scope_fidelity: minor (argus/commands/adjust_cmds.py is not in WO section 2)
offline_tests_pass: yes (344 passed, 1 deselected; all 76 tests/test_adjust.py re-run on a copy)
non_vacuity_established: yes (AC6 a, c, d as written; b fails except its first-named test)
gitleaks_clean: yes (134 commits)
commit_identity_clean: yes
AC1/AC4: operator checks     AC2/AC3: yes for the code     AC5: yes for code and tests     AC6: yes
findings: 1 minor, procedural, non-blocking (adjust_cmds.py +4 lines, the CLI echo of the new counter; ratify)
confidence: high for code, tests and mutations; medium for the CLI echo (read, not run)
```

Resolution verified exactly as AMD-0031 section 2A: records differing in amount, declaration_date or frequency are
distinct and summed; identical-signature groups resolve against the other source's basis-normalised total (within one
cent of the single amount -> collapse; of the sum -> keep all; neither or no second source -> collapse, warn, count).
Edge decisions probed, none violating AMD-0031, each erring toward understating: matches-both -> default; three identical
records; several ambiguous groups in one source (sequential); second source itself ambiguous -> treated as none;
PGR 0.10 + 13.50 sums to 13.60 (and 0.10 duplicated beside 13.70 keeps the pair); DVN 2 x 0.22 vs 0.44 -> 0.44;
TEL 2 x 0.65 vs 0.65 -> 0.65. `n_ambiguous_groups_resolved_by_default` is a MaterialiseReport field, in the ingest_log
detail and the CLI output. The migration is gated on the dividend columns, not the version (a store at version 7 still
gets them; version rows 7 and 8 kept; re-run a no-op; bars_raw checksum identical).
