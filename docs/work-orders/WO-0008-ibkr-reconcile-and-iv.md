# WO-0008 — IBKR provider: reconciliation and implied volatility

| Field | Value |
|---|---|
| **Status** | Closed |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.6, §8.7 (`ibkr reconcile`, `ibkr iv`) ; `DESIGN.md` §3.1, §3.3 (reconciliation), §3.2 (`iv_daily`, `reconcile_log`) ; ADR-0006 |
| **Applicable Amendments** | AMD-0002, AMD-0012, AMD-0019 (delta, pre-dispatch — §2 paper-port enforcement and flag-first sampling) |
| **Base SHA** | main at Closure of WO-0007 |
| **Branch** | `wo/0008-ibkr-reconcile-and-iv` |
| **Depends on** | WO-0007 |
| **Parallel group** | P0-E |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0008/` |

## 1. Objective
A read-only IBKR client against the **paper** gateway that (a) reconciles
a rotating sample of 20 members' materialised bars against IBKR daily
bars and records breaches, and (b) stores 30-day implied and historical
volatility for the benchmark and sector ETFs into `iv_daily`. Tested
against an in-process fake; live tests opt-in.

## 2. Scope (exhaustive)
```
argus/data/providers/ibkr.py         create  class IBClient(Protocol):   # the seam the fake implements
                                               connect() / disconnect()
                                               daily_bars(symbol: str, end: date, duration_days: int, what: Literal['TRADES','ADJUSTED_LAST']) -> pl.DataFrame
                                               daily_series(symbol: str, end: date, duration_days: int, what: Literal['OPTION_IMPLIED_VOLATILITY','HISTORICAL_VOLATILITY']) -> pl.DataFrame[date, value]
                                             class IBAsyncClient(IBClient): implementation over ib_async (lazy import; ProviderError if missing:
                                               "install extras: argus[ibkr]"); connect(host, port, client_id) with readonly=True;
                                               Stock(symbol_provider_form, 'SMART', 'USD'); reqHistoricalData(..., barSizeSetting='1 day', useRTH=True,
                                               formatDate=2); pacing: ≤ 50 historical requests per 10 minutes (RateLimiter)
                                             source="ibkr"; basis: TRADES="split", ADJUSTED_LAST="split_div"
argus/data/reconcile.py              create  choose_sample(members: list[str], on: date, n: int = 20,
                                                 priority: list[str] | None = None) -> list[str]
                                               (deterministic rotation: sorted members, offset = (ordinal(on) * n) % len.
                                                AMD-0019 §3: symbols in `priority` — members carrying an unresolved
                                                `jump_unexplained` flag from the previous session — are placed FIRST and the
                                                rotation fills the remainder; the offset advances as if the full sample had
                                                been drawn, so the rotation still covers the universe over time. This makes a
                                                flag adjudicable by a third source within a day out of a request budget
                                                already being spent)
                                             reconcile_day(store, client, on: date, sample: list[str], lookback_days: int = 5) -> ReconcileReport(
                                               n_symbols, n_fields, n_breaches, breach_rate, rows: pl.DataFrame)
                                               (compare bars.close vs TRADES close, tolerance 0.1%; bars.volume vs volume, tolerance 10%; write every
                                                comparison to reconcile_log with breach flag; never modifies bars)
                                             fetch_iv(store, client, on: date, symbols: list[str]) -> int
                                               (iv30 from OPTION_IMPLIED_VOLATILITY, hv30 from HISTORICAL_VOLATILITY, last 5 days; upsert iv_daily, source='ibkr')
argus/commands/ibkr_cmds.py          create  `ibkr reconcile --date D [--sample 20]`, `ibkr iv --date D` (registers onto argus.commands.ibkr.app;
                                             both require settings.ib_port; exit 2 with ConfigError message when missing)
                                             PAPER-PORT ENFORCEMENT (AMD-0019 §3): settings.ib_port must be a paper port —
                                             7497 (TWS paper) or 4002 (IB Gateway paper), as a module-level allowlist
                                             constant. A live port (7496, 4001) or any other value raises ConfigError naming
                                             the value and exits 2 WITHOUT opening a socket
argus/cli.py                         modify  add exactly one import line for argus.commands.ibkr_cmds in the append-only block (AMD-0002)
tests/fakes/fake_ib.py               create  FakeIBClient(IBClient) seeded from parquet fixtures; records calls
tests/fixtures/ibkr/trades_sample.parquet       create  5 symbols × 10 days, two deliberate breaches (one close, one volume)
tests/fixtures/ibkr/iv_sample.parquet           create  3 ETFs × 5 days
tests/test_reconcile.py              create  see §5
tests/test_ibkr_live.py              create  @pytest.mark.live smoke: connect, one daily_bars call, disconnect (skipped by default)
```

## 3. Exclusions
Any order, watchlist, account or position call. Any write to IBKR. Any
non-paper port default. No changes to bars/adjust logic. No `docs/`.

## 4. Design constraints
ADR-0006 and PID §8.9. `readonly=True` on connect is mandatory. The host,
port and client id come only from settings; there is no default port. The
client must disconnect in a `finally`. IBKR returns symbols in its own
form; convert with `tickers`. `reconcile_day` compares on the intersection
of dates; a symbol with no IBKR data is recorded as `field='missing'`,
`breach=True`. Nothing in this Work Order mutates `bars`, `bars_raw`, `splits` or
`dividends` (AMD-0012).

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_reconcile.py::test_sample_rotates_deterministically` | same date → same sample; consecutive dates → disjoint samples until wrap | set logic |
| `test_reconcile.py::test_breaches_detected_and_logged` | fixture's two planted breaches are the only breaches; both in `reconcile_log` | exact counts |
| `test_reconcile.py::test_tolerances_boundary` | 0.09% close diff passes, 0.11% fails; 9% volume passes, 11% fails | boundaries |
| `test_reconcile.py::test_missing_symbol_is_breach` | — | flag |
| `test_reconcile.py::test_iv_upsert` | 15 rows upserted; re-run idempotent | counts |
| `test_reconcile.py::test_cli_requires_port` | no `IB_PORT` → exit 2 and message names `ib_port` | CliRunner |
| `test_ibkr_live.py::test_connect_smoke` (live) | real paper gateway reachable | skipped offline |

## 6. Acceptance criteria
- **AC1** — On the host with the paper gateway running, `argus ibkr reconcile --date <last trading day>` completes with `breach_rate < 0.01` (operator check: ReconcileReport output filed).
- **AC2** — `argus ibkr iv --date <last trading day>` writes iv30/hv30 for SPY, RSP and all 11 sector ETFs (operator check: 13 rows for that date).
- **AC3** — `grep -rn "placeOrder\|reqIds\|cancelOrder\|modifyOrder\|whatIfOrder" argus/` returns nothing (Auditor check).
- **AC4** — Connection is read-only (Auditor: `readonly=True` present in connect call; no write API used).
- **AC5** — Tests in §5 pass offline; live smoke passes on host (operator check).
- **AC6** — A live port in the environment exits 2 **without opening a socket** (test: a monkeypatched `connect` asserted never called, for 7496 and 4001; and 7497/4002 accepted). The Work Order already excludes every order, account and position call — this is the cheapest guard against speaking to the wrong gateway at all (AMD-0019 §3).
- **AC7** — `choose_sample` places unresolved `jump_unexplained` symbols first and still covers the universe over time (test: a priority list is sampled first; consecutive dates with no priority remain disjoint until wrap).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1, AC2, AC5 outputs — with host/port redacted).

## 8. Implementer notes
`ib_async` is the maintained successor of `ib_insync`. Use the synchronous
convenience API (`ib.connect`, `ib.reqHistoricalData`) inside a plain
function; no asyncio in callers. `formatDate=2` yields UTC epoch seconds;
convert to the exchange date. Volume from IBKR is in shares for daily
bars (not lots) when `useRTH=True`; verify against the fixture and note
any scale factor in a comment rather than guessing.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
