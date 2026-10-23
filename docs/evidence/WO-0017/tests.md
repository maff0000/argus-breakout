host=dell-debian cwd=/srv/argus-breakout-wt/WO-0017 head=2a59157515c5420c98270dd289e345b4f7fd9f00 branch=wo/0017-dividend-duplicate-guard
$ ls .env  (must not exist)
ls: cannot access '.env': No such file or directory
$ git status --porcelain
 M argus/data/adjust.py
 M argus/data/ingest_polygon.py
 M argus/data/providers/bootstrap.py
 M argus/data/providers/polygon.py
 M argus/data/schema.py
 M argus/data/store.py
 M argus/diagnostics/dividends.py
 M tests/test_adjust.py
 M tests/test_polygon_client.py
 M tests/test_schema.py
 M tests/test_store.py
(end)
$ rm -rf .venv && uv venv --python 3.12 .venv && uv sync --frozen --all-extras
Activate with: source .venv/bin/activate
 + yfinance==1.7.0
$ env -u ARGUS_STORE_DIR uv run python -m pytest -q
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 85%]
..................................................                       [100%]
338 passed, 1 deselected in 316.38s (0:05:16)
$ uv run ruff check .
All checks passed!
$ AC7a
grep rc=1 (1 = no matches)
$ AC7b
grep rc=1 (1 = no matches)
$ stray store dir check
ls: cannot access 'store': No such file or directory
$ gitleaks detect --source . --redact
[90m7:31AM[0m [32mINF[0m [1mscanned ~2463586 bytes (2.46 MB) in 662ms[0m
[90m7:31AM[0m [32mINF[0m [1mno leaks found[0m
rc=0
$ git status --porcelain (after)
 M argus/data/adjust.py
 M argus/data/ingest_polygon.py
 M argus/data/providers/bootstrap.py
 M argus/data/providers/polygon.py
 M argus/data/schema.py
 M argus/data/store.py
 M argus/diagnostics/dividends.py
 M tests/test_adjust.py
 M tests/test_polygon_client.py
 M tests/test_schema.py
 M tests/test_store.py
(end)
$ identity check c582c61..HEAD
Claude (Architect) <noreply@anthropic.com> | Claude (Architect) <noreply@anthropic.com>
maff0000 <131767449+maff0000@users.noreply.github.com> | GitHub <noreply@github.com>
Rogue (Delivery Controller) <noreply@anthropic.com> | Rogue (Delivery Controller) <noreply@anthropic.com>

## AMD-0031 delta (b9defa2)
- Gate (mech2, head b9defa2): 344 passed, 1 deselected; ruff clean; gitleaks clean; AC7a/AC7b greps clean; identity clean.
- New tests: `test_ambiguous_group_resolved_genuine_by_second_source` (DVN, 0.44),
  `test_ambiguous_group_resolved_duplicate_by_second_source` (TEL, 0.65),
  `test_ambiguous_group_defaults_to_collapse_and_counts_it`, `test_ambiguous_group_edge_cases`,
  `test_differing_frequency_or_declaration_still_sums`, `test_store_already_at_version_7_still_receives_the_dividend_columns`.
- AC6 mutations (Implementer and Auditor, copies under mktemp, tests/test_adjust.py, 76 tests):
  (a) resolution removed: 6 failed, incl. test_duplicate_record_is_deduplicated and test_ambiguous_group_resolved_duplicate_by_second_source;
  (b) amount-only key: 3 failed (test_equal_specials_with_different_declarations_both_count, test_differing_frequency_or_declaration_still_sums, test_same_amount_twice_does_not_collapse); test_genuine_pair_survives_dedupe does not fail (spec-gaps 1);
  (c) integer-multiple exclusion dropped: 2 failed (test_integer_multiple_does_not_trigger_larger_wins, test_non_multiple_omission_still_takes_larger);
  (d) ambiguous resolves as genuine by default: 5 failed incl. the named test_ambiguous_group_defaults_to_collapse_and_counts_it.
