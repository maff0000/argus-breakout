# PID-ARGUS-0002 — Screening Engine and Rotation Layer

**Status:** **Draft** (authored before PID-ARGUS-0001 closure under
AMD-0033 §2A; finalised at closure with the closure evidence appended)
· **Owner:** Architect · Changes only by Amendment.

## 1. Purpose
Turn the Phase 0 data foundation into **the product**: a nightly ranked
list of individual equities worth trading, framed by a sector-rotation
headline (`PID.md` §2 as corrected by AMD-0024).

Phase 0 built a store nothing reads. This phase is what makes the scanner
scan.

## 2. Delivers
Per `PID.md` §6 as amended (AMD-0024 §2C):
- the **DESIGN §5 stock-feature layer** with its cross-sectional and
  within-sector percentiles;
- equal-weight composites (index, 11 sectors, 25 industry groups) with
  coverage carried per date (CI-8);
- breadth (§6.1), RRG mechanics (§6.2), group internals (§6.3),
  cross-market ratios (§6.4), the rotation score and its triggers (§6.5),
  and the regime label (§6.6);
- **uncalibrated** playbook candidate lists (§7) — long and
  weakness/trim/avoid, every row tagged with its group's rotation state and
  never filtered by it (AMD-0023 §2A);
- the Markdown and HTML report in the §7.1 layout: rotation headline with
  **Rotating IN / Rotating OUT** and their member tickers, then the
  candidate lists, then plain comma-separated ticker lines.

## 3. Explicitly not in this phase
- **Calibration of any threshold.** Every number in §6.5 and §7 stays at
  its specified initial value. Tuning is PID-ARGUS-0004, **behind the IC
  gate** (AMD-0028 §2A).
- **Any claim that the lists are predictive.** They are a rules-based
  screen until the IC study says otherwise, and the report says so.
- The brief and the LLM layer (PID-ARGUS-0003), news (AMD-0024 §2D),
  sizing and the watchlist push (PID-ARGUS-0004), ML (0005),
  containerisation (0006).

## 4. Evidence this phase was designed from
Cited as AMD-0033 §2A(3) requires, by figure:
- **Coverage: 46.4%** of delisted historical members have bars (R5,
  AMD-0017 §2E). Every composite before the Polygon window leans toward
  survivors, so §6.1's per-date coverage is **not bookkeeping** — it is the
  only thing keeping that gap out of the numbers.
- **`bars`: 1,917,529 rows**, ~615 symbols, ten years, schema 6/7.
- **Dividend basis measured** (WO-0013): Polygon `as_paid`, yfinance
  `split_adjusted`; 34 collapsed records recovered (WO-0016); ambiguous
  same-signature groups resolved cross-source, defaulting to collapse
  (AMD-0031).
- **`adj_close` is suspect on the 13 measured ex-dates** until WO-0017
  merges (AMD-0025 §2D) — so feature **values** are provisional while the
  computation is not.
- **Flags are carried, not subtracted** (AMD-0019 §2A): 128 flagged
  symbol-days are published and tagged; aggregates exclude them and report
  the count, series never do.
- **Classification**: sector and industry-group composites compute over
  **classified** members only and report classification coverage with them
  (AMD-0016 §2C).

## 5. Binding constraints inherited
Every ADR and the full amendment set apply. The ones this phase will meet
first:
- **ADR-0008 portability** — no absolute paths, everything from settings.
- **CI-8** — coverage travels with every aggregate; a figure **reports or
  is NULL, never a constant** (AMD-0021 §2F). `n_symbol_days_flag_excluded`
  must report truthfully or be absent **before any feature is computed**,
  and the Work Order that builds the aggregates **calls**
  `equal_weight_aggregate` rather than reimplementing it.
- **CI-6** — non-vacuity: for ~70 numerical features, a test that
  re-implements the production formula proves nothing. See WO-0018 §5.
- **AMD-0023** — rotation tags and never filters; the weakness list always
  runs; candle features are confirmation terms, never triggers; level
  distances in ATR, never per cent.
- **AMD-0028 §2B** — the research protocol, and **PR-0001** is already
  registered: no feature may be added to the IC study after the fact.

## 6. Work Orders
| WO | Title | Depends on | Group |
|---|---|---|---|
| [WO-0018](../work-orders/WO-0018-feature-layer.md) | DESIGN §5 feature layer and percentiles | — (Phase 0 store) | P2-A — **concurrent with Phase 0** |
| WO-0019 | Composites, breadth, coverage | WO-0018 | P2-B |
| WO-0020 | RRG, internals, ratios, rotation score, regime | WO-0019 | P2-C |
| WO-0021 | Playbooks and uncalibrated candidate lists | WO-0018, WO-0020 | P2-D |
| WO-0022 | Report: §7.1 layout, Markdown and HTML; nightly step | WO-0021 | P2-E |

WO-0019 onward are authored when WO-0018 closes. Only **WO-0018** carries
the AMD-0033 §2A overlap conditions and may run during Phase 0.

## 7. Acceptance
- Every Work Order above closed under the delivery chain.
- `argus nightly` produces the §7.1 report for a trading day, on the host,
  with candidate lists that are **non-empty** and whose every row carries
  its rotation tag, its levels and its stop.
- Breadth, composites and every aggregate carry per-date coverage
  (CI-8), and no coverage field is a constant.
- The report states plainly that the lists are **uncalibrated and not yet
  shown to be predictive**, with a pointer to PR-0001 and the IC gate.
- The Product Owner can review a night's list and reach each ticker in his
  own charting from the plain ticker lines.

## 8. Approval
```
Authored by:  Claude (Architect)
Date (UTC):   2026-10-22
Status:       Draft (AMD-0033 §2A) — finalise at PID-ARGUS-0001 closure
Commit:       the commit introducing this file
```
