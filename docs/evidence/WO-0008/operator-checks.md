# WO-0008 — Operator checks (live, read-only, paper gateway)

Run by the Delivery Controller on the execution host against the audited head `6d531f5`, **after** a GREEN audit and with the Product Owner's explicit confirmation of the paper-gateway connection (2026-10-21). Host and port values are not recorded here.

## Gateway selection (AC6 in practice)
- The `IB_PORT` configured in the project's `.env` is **not** one of the allowlisted paper ports. The paper-port guard (AMD-0019 §3) would therefore refuse it, which is the behaviour the guard exists to provide. The `.env` was **not modified**.
- The checks were run with the process environment overriding `IB_PORT` to the allowlisted paper-gateway port (the only allowlisted port with a listening gateway on the host). The CLI accepted it; no live-gateway port was used. Only historical-data requests were issued (the code issues nothing else, AC3/AC4).
- Scratch store: a copy of the WO-0007 scratch store (`bars` through 2026-10-19); only `reconcile_log` and `iv_daily` are written by these commands.

## AC5 — live smoke
`pytest -m live tests/test_ibkr_live.py` → **1 passed** (connect, one `daily_bars` call for SPY, disconnect).

## AC2 — `argus ibkr iv --date 2026-10-19`
`symbols=13 rows=65` — **13 rows for 2026-10-19** (SPY, RSP and the 11 sector ETFs) and 13 rows for each of the four prior sessions (65 in all). iv30/hv30 are decimals (SPY 0.1346 / 0.1067, i.e. 13.5% / 10.7%): the IBKR series are stored as returned, **IV scale is decimal**. **AC2 met.**

## AC1 — `argus ibkr reconcile --date 2026-10-19` (20-member rotating sample, 5-day window)
```
symbols=20  fields=200  breaches=101  breach_rate=0.5050
by field:   close  false=99  true=1     volume  false=0  true=100
missing symbols: 0       dates compared: 2026-10-13 .. 2026-10-19 (5 sessions)
close: max |pct_diff| 2.09%  (the single breach: SKYD 2026-10-13 ours 9.27 vs 9.08)
volume: ours/theirs  p5 1.35  p25 1.67  median 2.03  p75 2.33  p95 2.78
```
- **Date handling verified:** `formatDate=2` epoch → exchange date lines up with our trading dates (5 sessions, no off-by-one).
- **Close agrees:** 99 of 100 close comparisons within 0.1%.
- **Volume does not:** every one of the 100 volume comparisons breaches the 10% tolerance; our (consolidated, Polygon) volume is a median **2.03×** IBKR's TRADES daily volume. IBKR volume is in shares (e.g. SO 2026-10-13: ours 6,567,653 vs IBKR 3,879,970), not lots; the gap is a coverage difference between the two vendors, not a scale factor. Polygon and yfinance agree with each other to 0.03% on the same days. **AC1 literally not met (`breach_rate < 0.01`)** — see `spec-defects.md`.

## Hygiene
`grep -rnE '([0-9]{1,3}\.){3}[0-9]{1,3}' docs/` → only loopback.
