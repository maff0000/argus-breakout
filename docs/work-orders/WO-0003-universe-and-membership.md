# WO-0003 — Universe and point-in-time membership (FMP client)

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.7 (`universe refresh`), §8.8 ; `DESIGN.md` §3.1, §3.3 (GICS rule), §4 ; ADR-0003, ADR-0005 |
| **Applicable Amendments** | none |
| **Base SHA** | main at Closure of WO-0002 |
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
                                             build_membership(hanshof, fmp_changes, start=date(2015,1,1)) -> pl.DataFrame[symbol,start_date,end_date,source]
                                               (hanshof is primary; FMP changes fill gaps after hanshof's last date; intervals merged)
                                             map_industry_group(sub_industry, gics_yaml) -> str  (raise on unknown)
                                             refresh(store, settings, http) -> UniverseReport(dataclass: n_symbols, n_members_today,
                                               n_missing_group, membership_rows, sources_used)
config/universe.yaml                 create  per PID §8.8 (benchmarks, sector_etfs, ratio_pairs, overlay_watchlist: [])
config/gics.yaml                     create  per PID §8.8: 11 sectors, 25 industry groups→sector, 163 sub-industries→group
argus/cli.py                         modify  `universe refresh [--date]` → universe.refresh(...); prints the UniverseReport; exit 1 if n_missing_group>0
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
PID §8.4, §8.8, §8.9; ADR-0005. Industry group is mandatory: a symbol with
no mapping goes through the FMP `profile` fallback; if still unmapped it
is counted in `n_missing_group` and the command exits 1 — never a silent
default. The FMP api key is only ever a query parameter added inside
`FMPClient.get`; it must not appear in logs (the logging redactor covers
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
| `test_universe.py::test_fmp_fills_gap_after_hanshof` | a change dated after hanshof's last date appears as an interval from FMP with `source='fmp'` | presence + source |
| `test_universe.py::test_missing_group_exits_nonzero` | a fixture row with unknown sub-industry and failing profile fallback → exit code 1 | CliRunner exit code |
| `test_fmp_client.py::test_budget_enforced` | 201st call in a day raises `ProviderError` (budget=200) | counter persisted via Store |
| `test_fmp_client.py::test_key_not_in_logs_or_errors` | a 500 response's raised error and log lines contain no `apikey` value | string assertions on captured output |

## 6. Acceptance criteria
- **AC1** — `argus universe refresh` on the host populates `symbols` with every current member and all configured ETFs, each with a non-empty industry group (operator check: `SELECT count(*) FROM symbols WHERE gics_industry_group IS NULL OR gics_industry_group=''` = 0).
- **AC2** — `members_on('2016-06-30')`, `('2020-03-31')`, `('2024-12-31')` each match the hanshof CSV for that date within ±3 symbols (operator check with output; differences listed).
- **AC3** — `config/gics.yaml` passes test_gics_yaml_integrity.
- **AC4** — Every symbol written passes `tickers.is_valid` (Auditor: query `symbols` for non-matching rows = 0).
- **AC5** — FMP daily budget enforced; key never logged (tests).
- **AC6** — Total FMP calls used by one `universe refresh` ≤ 60 (operator check: `ingest_log` counter).

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
