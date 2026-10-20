# ADR-0003 — Data sources and their roles

**Status:** Accepted · **Date:** 2026-10-19

## Decision
| Role | Source | Why |
|---|---|---|
| Nightly OHLCV for the whole US market | Polygon grouped-daily endpoint (free tier) | one call per trading day; adjusted; 2 years history |
| 10+ year bootstrap of adjusted daily bars | yfinance or Stooq (one-off) | free; validated against IBKR before use; never a production path |
| Reconciliation sample, corporate-action truth, implied volatility | IBKR paper gateway via `ib_async` | matches the trading venue; consolidated volume; free with the account |
| GICS profile fallback, earnings / dividends / splits calendars | FMP Basic (free) | these four endpoints return 200 on the free tier |
| Constituents (current) and point-in-time membership | the public S&P 500 constituents table (`Symbol`, `GICS Sector`, `GICS Sub-Industry`, `Date added`) + the public `hanshof/sp500_constituents` CSV, with a documented derivation for the gap after hanshof's last snapshot | **AMD-0013**: FMP returns 402 on `sp500-constituent`, `historical-sp500-constituent` and `stock-list` for this account's plan, and FMP does not state which tier unlocks them. Membership no longer depends on a paid endpoint. |

Raw prices and adjustment factors are stored separately; adjusted bars are
materialised. Ticker normalisation to a canonical form (`BRK.B`) happens at
every provider boundary.

## Consequences
- Three vendors → nightly validation and reconciliation are mandatory
  pipeline steps, not optional.
- FMP Starter may be adopted later for fundamentals; that is an Amendment,
  and must be evaluated against a specific testable endpoint list rather
  than on spec (AMD-0013 §2B).
- **Lesson recorded (AMD-0013 §1a):** this ADR assigned constituents to FMP
  Basic on documentation that did not state a plan requirement. The doubt
  was noted and not resolved, and the cost surfaced four Work Orders later
  at the first live call. Where a provider's documentation is silent on
  entitlement, probe the endpoint before the ADR, not at the operator check.
