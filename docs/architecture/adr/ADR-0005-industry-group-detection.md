# ADR-0005 — Detect rotation at GICS industry-group level, report at sector level

**Status:** Accepted · **Date:** 2026-10-19

## Context
Sector-level composites blur the moves that matter most (semiconductors vs
software inside Information Technology; banks vs payments inside
Financials). The September 2026 semiconductor break is the motivating case.

## Decision
Equal-weight composites are built for both the 11 GICS sectors and the 25
GICS industry groups. RRG mechanics, breadth, distribution counts and the
rotation score are computed at industry-group level; the report rolls them
up to sector level and lists the industry groups driving each sector's
flag. Ratio z-scores stay at the ETF/sector level listed in
`config/universe.yaml`.

## Consequences
- 35 composites nightly instead of 11; trivial cost.
- Membership data must carry `gics_industry_group` (FMP profile provides
  it; missing values are a validation failure, not a silent default).
