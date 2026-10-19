# ADR-0003 — Data sources and their roles

**Status:** Accepted · **Date:** 2026-10-19

## Decision
| Role | Source | Why |
|---|---|---|
| Nightly OHLCV for the whole US market | Polygon grouped-daily endpoint (free tier) | one call per trading day; adjusted; 2 years history |
| 10+ year bootstrap of adjusted daily bars | yfinance or Stooq (one-off) | free; validated against IBKR before use; never a production path |
| Reconciliation sample, corporate-action truth, implied volatility | IBKR paper gateway via `ib_async` | matches the trading venue; consolidated volume; free with the account |
| Constituents (point-in-time), GICS profiles, earnings & ex-dividend calendars | FMP Basic (free) cross-checked with the public `hanshof/sp500_constituents` CSV | 250 calls/day suffices; one key |

Raw prices and adjustment factors are stored separately; adjusted bars are
materialised. Ticker normalisation to a canonical form (`BRK.B`) happens at
every provider boundary.

## Consequences
- Three vendors → nightly validation and reconciliation are mandatory
  pipeline steps, not optional.
- FMP Starter may be adopted later for fundamentals; that is an Amendment.
