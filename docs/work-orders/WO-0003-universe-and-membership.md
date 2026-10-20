# WO-0003 — Universe and point-in-time membership (FMP client)

| Field | Value |
|---|---|
| **Status** | PR Open |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.7 (`universe refresh`), §8.8 ; `DESIGN.md` §3.1, §3.3 (GICS rule), §4 ; ADR-0003, ADR-0005 |
| **Applicable Amendments** | AMD-0002, AMD-0004, AMD-0013, AMD-0014, AMD-0015, AMD-0016 |
| **Base SHA** | 5e95343 (main with AMD-0016) |
| **Branch** | `wo/0003-universe-and-membership` |
| **Depends on** | WO-0002 |
| **Parallel group** | P0-C (with WO-0004, WO-0005) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0003/` |

## 1. Objective
`argus universe refresh` populates `symbols` (with GICS sector and
industry group for every current member and every configured ETF) and
`membership` (point-in-time S&P 500 intervals from 2015-01-01 to today),
from the public constituent table, the hanshof CSV, and FMP's historical
constituent endpoint, with every ticker in canonical form via
`argus.data.tickers` (WO-0002).

## 2. Scope (exhaustive)
```
argus/data/providers/fmp.py          create  class FMPClient(api_key: SecretStr, budget: int, store: Store):
                                               get(path, params) -> dict|list  (httpx; base https://financialmodelingprep.com/stable/;
                                               apikey param added here only; RateLimiter 4/sec; tenacity retry 3x on 5xx/429;
                                               per-day call counter persisted in ingest_log(source='fmp-budget'); raises
                                               ProviderError("fmp daily budget exhausted") at budget)
                                               historical_sp500_changes() -> pl.DataFrame[date, symbol, action{'added','removed'}, reason]
                                               current_sp500() -> pl.DataFrame[symbol, name, sector, sub_industry]
                                               profile(symbol) -> dict  (fallback only)
argus/data/universe.py               create  fetch_wikipedia_constituents(http) -> pl.DataFrame[symbol,name,gics_sector,gics_sub_industry]
                                               (parses the "List of S&P 500 companies" table; validates ≥490 rows and 11 sectors)
                                             load_hanshof_csv(path_or_url) -> pl.DataFrame[date, symbols:list]
                                             build_membership(hanshof, current_table, fmp_changes_or_None, start=date(2015,1,1))
                                               -> pl.DataFrame[symbol,start_date,end_date,source]   (AMD-0013 §2C routing:
                                               hanshof to its last snapshot H; then the gap H->today by the first AVAILABLE route —
                                               (a) FMP historical changes if 200, (b) a changes table on the constituents page if present,
                                               (c) derivation: additions = current rows with `Date added` > H (exact, source
                                               'wikipedia-derived-exact'); removals = in hanshof@H but absent from current (end_date = H,
                                               source 'wikipedia-derived-bounded', bound recorded). Report which route was used.)
                                               (hanshof is primary; the gap after hanshof's last date is filled per AMD-0013 §2C; intervals merged;
                                               membership.source carries the PRECISION of each row. RENAMES, AMD-0014: for each pair in
                                               config/ticker_renames.yaml with a known `effective`, close the OLD interval on the last trading
                                               day before it and open the NEW interval on it (source 'rename-mapped'); with `effective: null`,
                                               close the old at H and open the new on the next trading day (source 'rename-bounded', bound
                                               recorded). A mapped old ticker is REMOVED from the bounded-removal set — it did not leave the
                                               index. No date may fall between a pair's two intervals.)
                                             map_industry_group(sub_industry, gics_yaml) -> str  (raise on unknown)
                                             (AMD-0016 §2C: `symbols` is populated for EVERY symbol appearing in `membership`, not only
                                               current members. A historical-only symbol takes its classification from the rename target's
                                               group where mapped, else FMP `profile`, else NULL and counted in n_unclassified.)
                                             refresh(store, settings, http) -> UniverseReport(dataclass: n_symbols, n_members_today,
                                               n_missing_group, membership_rows, sources_used)
config/universe.yaml                 create  per PID §8.8 (benchmarks, sector_etfs, ratio_pairs, overlay_watchlist: [])
config/ticker_renames.yaml           create  AMD-0014: `renames: [{old, new, effective|null}]`, seeded with the pairs found in the
                                             live run (BNY, FISV, MRSH, SKYD, VMRK and their former tickers), `effective` filled where
                                             evidenced and null otherwise
config/gics.yaml                     create  per PID §8.8: 11 sectors, 25 industry groups→sector, 163 sub-industries→group
argus/commands/universe_cmds.py      create  `universe refresh [--date]` → universe.refresh(...); prints the UniverseReport; exit 1 if
                                             n_missing_group>0; exit 1 if current_members_without_row>0 (AC9, unconditional — AMD-0015 §2A);
                                             exit 2 if --date is more than 7 calendar days in the past, with a message that the current
                                             constituents table has no historical snapshot so a back-dated refresh cannot be correct (AC10)
                                             (registers onto argus.commands.universe.app)
argus/cli.py                         modify  add exactly one import line for argus.commands.universe_cmds in the append-only block (AMD-0002)
tests/fixtures/universe/wikipedia_sp500.html      create  scrubbed static copy (≥490 rows)
tests/fixtures/universe/hanshof_sample.csv        create  10 dates spanning 2015–2026 with realistic add/remove churn
tests/fixtures/fmp/historical_sp500.json          create  ≥ 20 change records, scrubbed
tests/fixtures/fmp/sp500_constituent.json         create
tests/test_universe.py               create  see §5
tests/test_fmp_client.py             create  see §5 (respx)
```

## 3. Exclusions
No bars ingestion, no earnings/dividend calendars (WO-0006), no Polygon or
yfinance code, no changes to `store.py`/`schema.py` beyond none, no
`docs/` changes.

## 4. Design constraints
PID §8.8, §8.9; ADR-0005; ADR-0008. `config/universe.yaml` and
`config/gics.yaml` are loaded from `settings.argus_config_dir`, never a
path relative to the package (AMD-0004). Industry group is mandatory: a symbol with
no mapping goes through the FMP `profile` fallback; if still unmapped it
is counted in `n_missing_group` and the command exits 1 — never a silent
default. The current-membership invariant (AMD-0014 §2B) is computed against the
**fetched current constituents table**, always, **independent of `--date`**
(AMD-0015 §2A): it asserts that every symbol in the table just fetched has
exactly one row with `end_date IS NULL`. It is a statement about rows
existing, not about membership on a date, so it holds for every invocation.
`FMPClient.historical_sp500_changes()` and `current_sp500()` must treat
**402/403 as unavailable, not as failure** (AMD-0013): raise a typed
`ProviderUnavailable(ProviderError)` that `refresh()` catches to fall
through to the next route, logging the status code and never the key. A 402
must not abort `universe refresh`. The FMP api key is only ever a query
parameter added inside `FMPClient.get`; it must not appear in logs (the logging redactor covers
`apikey=`; also strip it from any exception message). Wikipedia fetch is
one HTTP GET with a fixed URL constant and a 20 s timeout; parsing uses
the standard library (`html.parser`) or `polars`/`pyarrow` only — no new
dependency. ETFs from `config/universe.yaml` are inserted into `symbols`
with `gics_sector='ETF'`, `gics_industry_group='ETF'`, `active=true`.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_universe.py::test_wikipedia_parse_counts` | fixture yields ≥490 rows, 11 sectors, no empty sub_industry | count assertions |
| `test_universe.py::test_gics_yaml_integrity` | 11 sectors, 25 groups each mapping to a listed sector, 163 sub-industries each mapping to a listed group | counts + referential checks |
| `test_universe.py::test_membership_intervals` | from the hanshof sample, a symbol removed on date D has `end_date = D - 1 trading day`; re-added symbols get a second interval | exact dates |
| `test_universe.py::test_fmp_fills_gap_after_hanshof` | with FMP returning 200, a change dated after hanshof's last date appears as an interval with `source='fmp'` | presence + source |
| `test_universe.py::test_gap_derivation_when_fmp_402` | with FMP returning 402: additions after H appear with `source='wikipedia-derived-exact'` and the exact `Date added`; a symbol in hanshof@H absent from the current table gets `end_date = H` and `source='wikipedia-derived-bounded'`; the report names route (c) (AMD-0013) | exact dates + source values + route |
| `test_universe.py::test_402_does_not_abort_refresh` | a 402 from any FMP endpoint leaves `refresh()` completing (AC8) | no raise; report populated |
| `test_universe.py::test_rename_preserves_continuity` | a mapped pair with a known `effective` yields a closed old interval ending the trading day before it and an open new interval starting on it, with no date in `[Date added, today]` where neither is a member; the old ticker is absent from the bounded-removal set (AMD-0014) | asserts membership the day before, the day of and the day after `effective`, plus set membership |
| `test_universe.py::test_rename_unknown_effective_is_bounded_not_added` | a pair with `effective: null` is continuous across H — old closes at H, new opens the next trading day, exactly one is a member on every date (AMD-0014) | asserts both dates and that the union covers the gap with no hole |
| `test_universe.py::test_no_current_member_without_row` | every symbol in the current table has an open interval (AC9) | fails if any current symbol lacks a row |
| `test_universe.py::test_missing_group_exits_nonzero` | a fixture row with unknown sub-industry and failing profile fallback → exit code 1 | CliRunner exit code |
| `test_fmp_client.py::test_budget_enforced` | 201st call in a day raises `ProviderError` (budget=200) | counter persisted via Store |
| `test_fmp_client.py::test_key_not_in_logs_or_errors` | a 500 response's raised error and log lines contain no `apikey` value | string assertions on captured output |

## 6. Acceptance criteria
- **AC1** — `argus universe refresh` on the host populates `symbols` with every current member and all configured ETFs, each with a non-empty industry group (operator check: `SELECT count(*) FROM symbols WHERE gics_industry_group IS NULL OR gics_industry_group=''` = 0).
- **AC2** — `members_on('2016-06-30')`, `('2020-03-31')`, `('2024-12-31')` each match the hanshof CSV for that date within ±3 symbols (operator check with output; differences listed). **And `members_on(today)` equals the current constituents table's symbol count exactly** (AMD-0014; operator check: both numbers filed).
- **AC3** — `config/gics.yaml` passes test_gics_yaml_integrity.
- **AC4** — Every symbol written passes `tickers.is_valid` (Auditor: query `symbols` for non-matching rows = 0).
- **AC5** — FMP daily budget enforced; key never logged (tests).
- **AC6** — Total FMP calls for one `universe refresh` ≤ 60 **and** the run completes successfully when every FMP endpoint returns 402 (AMD-0013). Operator check: run once with the real key and once with a key forced to 402; file both.
- **AC7** — The membership report states the gap route used and the row count per `source` value. The `wikipedia-derived-bounded` count is reported and must not exceed 40; above that is a malfunction, not ordinary turnover, and is a stop (AMD-0013).
- **AC8** — A 402 on any FMP endpoint does not abort `universe refresh` (test: `respx` returns 402 → refresh completes and records the next available route).
- **AC9** — `UniverseReport` states `current_members_without_row` and that count is **0** (AMD-0014), **under every invocation including a back-dated one** (AMD-0015 §2A); non-zero exits non-zero and is an acceptance failure, not a statistic. The report also states the row count per `source`, including `rename-mapped` and `rename-bounded`.
- **AC10** — `universe refresh --date <30 days ago>` exits **2** and writes nothing (operator check: exit status plus an unchanged store row count before/after); `--date` of today or the last trading day succeeds (AMD-0015 §2A).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC2, AC6 outputs).

## 8. Implementer notes
Author `config/gics.yaml` from the public GICS structure (MSCI/S&P
publish the names). Membership intervals use exchange trading days; a
removal on date D means the symbol is **not** a member on D. hanshof dates
are membership snapshots: derive intervals by diffing consecutive
snapshots. Keep `refresh()` free of CLI concerns so WO-0009 can call it.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
