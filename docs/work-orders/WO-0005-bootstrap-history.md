# WO-0005 — Bootstrap history provider (yfinance)

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.6, §8.7 (`ingest bootstrap`) ; `DESIGN.md` §3.1, §3.3 ; ADR-0003 |
| **Applicable Amendments** | AMD-0002, AMD-0012, AMD-0014, AMD-0015 |
| **Base SHA** | main at Closure of WO-0002 |
| **Branch** | `wo/0005-bootstrap-history` |
| **Depends on** | WO-0002 |
| **Parallel group** | P0-C (with WO-0003, WO-0004) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0005/` |

## 1. Objective
A one-off, resumable bootstrap that loads ≥ 10 years of daily bars for
every symbol in `symbols` (members, historical members in `membership`,
and ETFs) into `bars_raw` with `source='yfinance'`, `basis='split'`, and
their split and dividend actions into `splits` and `dividends` (AMD-0012), so that later phases can
backtest to 2015 or earlier.

## 2. Scope (exhaustive)
```
argus/data/providers/bootstrap.py    create  class YFinanceProvider(pause_s: float = 0.5):
                                               daily_bars(symbols, start, end) -> pl.DataFrame  (yfinance download with auto_adjust=False,
                                                 actions=True, threads=False, chunks of ≤ 50 symbols; returns canonical columns plus adj_close)
                                               actions(symbols, start, end) -> pl.DataFrame[symbol, date, split_ratio|None, cash_dividend|None]
                                               source="yfinance"; basis="split"
                                             yfinance is imported lazily inside methods; absence raises ProviderError("install extras: argus[bootstrap]")
argus/data/ingest_bootstrap.py       create  bootstrap_history(store, provider, start, end, symbols: list[str] | None) -> BootstrapResult(
                                               n_symbols, n_rows, failed: list[str], skipped: list[str],
                                               current_written: int, current_failed: list[str],
                                               historical_written: int, historical_unavailable: list[str])   # AMD-0015 §2B
                                               (the cohorts are: CURRENT = current members + configured ETFs; HISTORICAL = symbols appearing
                                                only in historical membership. The exit rule applies to the CURRENT cohort only; historical
                                                unavailability never sets a non-zero exit)
                                               (skips symbols already having ≥ 95% of expected rows in bars_raw[source='yfinance'] for the range;
                                                writes per chunk; records ingest_log(source='yfinance') per chunk; writes non-null split rows to
                                                `splits` and non-null dividend rows to `dividends`, each keyed ["symbol","date","source"] — AMD-0012)
                                             `ingest bootstrap` exits 0 when >= 98% of requested symbols were written and 1 otherwise,
                                             reporting the failed list either way (AMD-0012). The threshold counts written AND
                                             skipped symbols as successes; only symbols in `failed` count against it (AMD-0014 §2E) —
                                             a skip means already complete, so counting skips as failures would make a fully
                                             complete re-run exit 1
argus/commands/ingest_bootstrap.py   create  `ingest bootstrap --start D [--end D] [--symbols S1,S2]` (registers onto argus.commands.ingest.app)
argus/cli.py                         modify  add exactly one import line for argus.commands.ingest_bootstrap in the append-only block (AMD-0002)
tests/fixtures/bootstrap/yf_download_sample.parquet   create  3 symbols × 60 days, yfinance-shaped multiindex flattened as the provider receives it
tests/fixtures/bootstrap/yf_actions_sample.parquet    create  includes one split and three dividends
tests/test_bootstrap_provider.py     create  see §5 (yfinance mocked at the module boundary — no network)
tests/test_ingest_bootstrap.py       create  see §5
```

## 3. Exclusions
No Polygon code, no adjustment/materialisation (WO-0007), no reconciliation
against IBKR (WO-0008), no universe code, no schema changes, no `docs/`.

## 4. Design constraints
PID §8.6, §8.9. The provider must tolerate yfinance returning NaN rows,
missing symbols and renamed columns without crashing the whole run: a
failing symbol is recorded in `failed` and the run continues. Store
`adj_close` from yfinance's `Adj Close` as a column of `bars_raw`? **No** —
`bars_raw` has no such column; instead write the dividend series into
the `dividends` table (AMD-0012) and let WO-0007 compute `adj_close`. Ticker conversion via
`argus.data.tickers.to_provider(sym, "yfinance")` and
`normalize(..., "yfinance")` (delivered by WO-0002). Chunked download with a pause to stay polite;
no retries beyond one per chunk.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_bootstrap_provider.py::test_canonical_columns_from_fixture` | fixture → canonical bar columns, symbols normalised (`BRK-B`→`BRK.B`) | column set + symbol value |
| `test_bootstrap_provider.py::test_nan_rows_dropped_and_counted` | NaN rows removed; count reported | counts |
| `test_bootstrap_provider.py::test_actions_split_and_dividends` | one split ratio and three dividends extracted with correct dates | values |
| `test_bootstrap_provider.py::test_missing_dependency_message` | with yfinance import patched to fail → `ProviderError` naming the extra | raises |
| `test_ingest_bootstrap.py::test_resumable_skips_complete_symbols` | second run skips symbols already ≥95% covered | provider called with fewer symbols |
| `test_ingest_bootstrap.py::test_failed_symbol_does_not_abort_run` | provider raising on one chunk → others written, symbol in `failed` | counts + list |

## 6. Acceptance criteria
- **AC1a** — Of symbols that are **current** members or configured ETFs, **≥ 99%** have bars written for the requested range (operator check: count, percentage, and an exception list with a reason per symbol). Below 99% is a delivery defect (AMD-0015 §2B).
- **AC1b** — Of symbols appearing **only** in historical `membership`, coverage is **reported with no threshold**: count written, count unavailable, percentage, and the full unavailable list filed in `docs/evidence/WO-0005/delisted-coverage.md`. A shortfall here is a recorded limitation of the free source, not a failure — provided it is recorded (AMD-0015 §2B).
- **AC2** — Every current member and ETF has ≥ 2,400 rows for 2015-01-01…2024-12-31 (operator check: query, exceptions listed with reason, e.g. IPO after 2015).
- **AC3** — `splits` and `dividends` each contain rows with `source='yfinance'`, and a symbol with a same-date split and dividend retains both (operator check: counts per table) (AMD-0012).
- **AC4** — Resumability and fault isolation (tests in §5).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC3 outputs).

## 8. Implementer notes
yfinance's `download` returns a column MultiIndex when more than one
symbol is requested; flatten to long format `(symbol, date, open, high,
low, close, adj_close, volume)`. `actions=True` adds `Dividends` and
`Stock Splits` columns (split value is the ratio, 0 when none). Dates are
exchange dates; cast to `pl.Date`. This provider is a bootstrap path; do
not make it clever.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
