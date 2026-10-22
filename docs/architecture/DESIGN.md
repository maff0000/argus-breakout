# Argus-Breakout — Design

**Version:** 1.0 (2026-10-19) · **Owner:** Architect · Changes only by Amendment.
Decisions are recorded in `adr/`. This document is the technical reference
Work Orders cite by section number.

## 1. Purpose

A nightly, locally-run system that (1) detects sector rotation in the S&P
500 early, using breadth, relative strength and volume rather than price
alone; (2) ranks constituents against the equal-weight index and their own
sector and industry group; (3) produces a short written brief from a local
model with long/research and short/avoid candidates; (4) records
everything so signals and briefs can be graded.

Fixed decisions: ADR-0001 (governance), ADR-0002 (storage/runtime),
ADR-0003 (data sources), ADR-0004 (model gateway), ADR-0005
(industry-group detection), ADR-0006 (IBKR paper, read-mostly).

## 2. Architecture and layout

```
            Polygon grouped-daily      IBKR paper gateway        FMP Basic
                    │                        │                      │
                    ▼                        ▼                      ▼
     ┌──────────────────────────────────────────────────────────────────┐
     │ argus.data   ingest → validate → adjust → reconcile              │
     │ Parquet partitions + DuckDB catalog (store/)                    │
     └────────────────────────────┬─────────────────────────────────────┘
                                  ▼
   ┌──────────────┐  ┌───────────────────────┐  ┌─────────────────────┐
   │ argus.features│  │ argus.market          │  │ argus.events        │
   │ per-stock     │  │ composites, breadth,  │  │ earnings, ex-div,   │
   │ indicators    │  │ RRG, rotation score,  │  │ days-to-event       │
   │ (wide table)  │  │ regime                │  │                     │
   └──────┬───────┘  └──────────┬────────────┘  └──────────┬──────────┘
          └─────────────────────┼───────────────────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ argus.rank  percentiles,     │
                 │ playbooks, lists, sizing     │
                 └──────────────┬───────────────┘
                                ▼
   ┌──────────────────────────┐      ┌─────────────────────────────┐
   │ argus.brief  evidence    │─────▶│ OpenAI-compatible gateway   │
   │ pack, prompt, grading    │◀─────│ (LLM_BASE_URL)              │
   └──────────────┬───────────┘      └─────────────────────────────┘
                  ▼
   ┌──────────────────────────┐      ┌─────────────────────────────┐
   │ argus.report  HTML + MD, │─────▶│ IBKR paper watchlist (0004) │
   │ alerts                   │      └─────────────────────────────┘
   └──────────────────────────┘
   ┌──────────────────────────┐
   │ argus.mcp  read-only MCP │  ← local model / ad hoc queries
   │ server over DuckDB       │
   └──────────────────────────┘
```

### Repository layout (fixed)
```
/srv/argus-breakout/
├── PID.md                      master PID (Forge startup gate requires it here)
├── pyproject.toml              package `argus`, console script `argus`
├── .env.example                every variable, placeholder values only
├── .gitignore  .gitleaks.toml
├── ops/
│   ├── bootstrap               verifies gitleaks, sets core.hooksPath
│   └── systemd/                argus-nightly.service / .timer (installed by operator)
├── scripts/hooks/pre-commit    gitleaks gate
├── config/                     = ARGUS_CONFIG_DIR (AMD-0004); never read by a package-relative path
│   ├── universe.yaml           benchmark + sector ETFs, ratio pairs, GICS maps
│   ├── features.yaml           lookbacks and parameters (single source of truth)
│   └── playbooks.yaml          factor weights per regime, list definitions (0004)
├── argus/
│   ├── __init__.py  settings.py  logging.py  cli.py
│   ├── data/        providers/{polygon,fmp,ibkr,bootstrap}.py store.py schema.py
│   │                adjust.py validate.py reconcile.py universe.py tickers.py
│   ├── features/    trend.py momentum.py rs.py vol.py flow.py structure.py risk.py
│   ├── market/      composites.py breadth.py rrg.py internals.py ratios.py rotation.py regime.py
│   ├── events/      earnings.py dividends.py
│   ├── rank/        percentiles.py playbooks.py lists.py sizing.py
│   ├── brief/       evidence.py prompt.py llm.py grade.py
│   ├── report/      markdown.py html.py ibkr_watchlist.py
│   ├── backtest/    engine.py ic.py leadtime.py
│   ├── ml/          (PID-ARGUS-0005)
│   └── mcp/         server.py
├── store/           parquet/  argus.duckdb        (host only; git-ignored)
├── out/             evidence/ briefs/ reports/    (host only; git-ignored)
├── tests/           fixtures/ …
└── docs/            governance/ pids/ architecture/ amendments/ work-orders/ evidence/
```

## 3. Data layer

### 3.1 Sources and roles (ADR-0003)
| Source | Role | Cadence | Limits |
|---|---|---|---|
| Polygon `GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true` | primary nightly OHLCV, all US tickers | 1 call per trading day; ≈500 calls for the 2-year backfill | 5 calls/min; 2 years; EOD delayed |
| Bootstrap (yfinance or Stooq) | one-off 10+ year adjusted bars for universe + ETFs | once | unofficial; validated before use |
| IBKR paper gateway (`ib_async`) | reconciliation sample (20 symbols/night, rotating, flagged-first), corporate-action truth, IV30 for ETFs/index | nightly | vendor limit ≈60 historical requests / 10 min; **the pacer implements a conservative 50** and the nightly budget is 46 (AMD-0020 §2D). Daily `TRADES` volume is **not** comparable with consolidated volume — measured ≈2× at WO-0008 — while closes are; see §3.3 |
| FMP Basic | `profile` (GICS sector + industry group, fallback only), `earnings-calendar`, `dividends-calendar`, `splits-calendar` | daily calendars | 250 calls/day; the constituent endpoints are **402 on this plan** — AMD-0013 |
| Public constituents table + `hanshof` CSV | current members with `GICS Sector`, `GICS Sub-Industry`, `Date added`; membership history to 2025-08-23, with a documented derivation for the gap | weekly | no key; see AMD-0013 §2C for the gap routing and the `membership.source` precision values |
| `hanshof/sp500_constituents` CSV (MIT) | cross-check of membership 1996→ | monthly | — |

### 3.2 Schema (DuckDB catalog; large tables are Parquet-backed)
```
symbols        (symbol TEXT PK, name TEXT, gics_sector TEXT, gics_industry_group TEXT,
                exchange TEXT, first_date DATE, last_date DATE, active BOOLEAN)
membership     (symbol TEXT, start_date DATE, end_date DATE NULL, source TEXT)
                -- point-in-time S&P 500. BOTH BOUNDS INCLUSIVE (AMD-0011): a symbol is a member
                -- on start_date and on end_date. end_date NULL = still a member. A removal
                -- effective on date D is stored as end_date = the last trading day before D.
bars_raw       (symbol TEXT, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
                volume DOUBLE, source TEXT, basis TEXT {'unadjusted','split','split_div'},
                ingested_at TIMESTAMP)                                         -- as received, with its adjustment basis
splits         (symbol TEXT, date DATE, ratio DOUBLE NOT NULL, source TEXT)
                -- PK (symbol, date, source). date = execution/effective date. ratio = to/from (2.0 for a 2:1).
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, basis TEXT NOT NULL,
                                source TEXT, vendor_id TEXT NOT NULL,
                declaration_date DATE NULL, frequency INT NULL)
                -- PK (symbol, date, source, vendor_id)  (AMD-0027 §2A). date = ex-dividend date.
                -- declaration_date and frequency come from the payload (AMD-0029 §2A) and are what
                -- separate a genuine second dividend from a DUPLICATED record: PGR's 2026-01-02 pair
                -- differ on both (declared 2025-12-08 freq 4; 2025-12-05 freq 1) while a duplicate
                -- repeats them. NULL where a source does not supply them. frequency also separates a
                -- regular payment from a special, which the event features want in their own right.
                -- vendor_id: the SOURCE'S OWN per-record identifier. Polygon supplies `id` on every
                -- /v3/reference/dividends record (verified, WO-0015). A source with no record
                -- identifier — yfinance, which delivers one summed figure per ex-date — uses 'sum'.
                -- NOT dividend_type and NOT frequency: both of PGR's 2026-01-02 records are
                -- dividend_type "CD", so type does not separate a quarterly from a special.
                -- A source may legitimately report several dividends on one ex-date; the narrower
                -- key silently kept one (measured: PGR 0.10 + 13.50 special, stored 0.10 alone).
                -- basis {'as_paid','split_adjusted'} (AMD-0019 §2B): whether cash_amount sits on the
                -- share count of the ex-date or is already restated onto the current basis. Recorded
                -- per source from a measured check, never assumed. A dividend must be on the same
                -- basis as the price it divides.
                -- Two tables, not one nullable-measure table: a split and a dividend on the same
                -- (symbol, date) must both survive, from each source independently (AMD-0012).
bars           (symbol TEXT, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
                volume DOUBLE, adj_close DOUBLE, adj_version INT)
                -- OHLCV split-adjusted; adj_close additionally dividend-adjusted; adj_version increments
                -- whenever a new split forces historical re-adjustment for that symbol
etf_bars       (same shape as bars; symbols from config/universe.yaml)
iv_daily       (symbol TEXT, date DATE, iv30 DOUBLE, hv30 DOUBLE, source TEXT)
composites     (date DATE, group_id TEXT, level TEXT {'index','sector','industry_group'},
                eq_close DOUBLE, eq_ret DOUBLE, n_members INT, pct_above_20 DOUBLE,
                pct_above_50 DOUBLE, pct_above_200 DOUBLE, nh20 INT, nl20 INT, nh252 INT,
                nl252 INT, adv INT, dec INT, dollar_vol DOUBLE)
features       (date DATE, symbol TEXT, <one column per §5 feature>, <one *_pct column per feature>)
market_daily   (date DATE, regime TEXT, pct_above_20 DOUBLE, pct_above_50 DOUBLE, pct_above_200 DOUBLE,
                ad_line DOUBLE, nhnl20 INT, nhnl252 INT, mcclellan DOUBLE, mcclellan_sum DOUBLE,
                pct_rsi_gt50 DOUBLE, rsp_spy DOUBLE, rsp_spy_slope20 DOUBLE, dispersion21 DOUBLE,
                avg_corr21 DOUBLE, ratio_z JSON)
sector_daily   (date DATE, group_id TEXT, level TEXT, rs_ratio DOUBLE, rs_mom DOUBLE, d_rs_mom5 DOUBLE,
                quadrant TEXT, heading_deg DOUBLE, rank_rs21 INT, rank_delta10 INT,
                dist_days25 INT, updown_vol20 DOUBLE, vol_share DOUBLE, vol_share_z DOUBLE,
                divergence BOOLEAN, rotation_score DOUBLE, flag TEXT NULL)
events         (symbol TEXT, date DATE, type TEXT {'earnings','exdiv'}, time_of_day TEXT NULL,
                source TEXT, confirmed BOOLEAN)
ranks          (date DATE, symbol TEXT, playbook TEXT, composite DOUBLE, verdict TEXT, reasons JSON)
evidence_packs (date DATE PK, tokens INT, json TEXT)
briefs         (date DATE, model TEXT, prompt_tokens INT, completion_tokens INT, text TEXT, grade JSON NULL)
reconcile_log  (date DATE, symbol TEXT, field TEXT, ours DOUBLE, theirs DOUBLE, pct_diff DOUBLE, breach BOOLEAN)
bar_flags      (symbol TEXT, date DATE, source TEXT, flag TEXT, detail TEXT)
                -- PK (symbol, date, source, flag). Per-symbol-day data-quality findings (AMD-0018).
                -- flag: 'jump_unexplained' | 'jump_split_reconciled'. The set is extensible
                -- without an Amendment and is enumerated in argus/data/validate.py.
ingest_log     (date DATE, source TEXT, rows INT, status TEXT, detail TEXT, finished_at TIMESTAMP)
                -- status: 'ok' | 'quarantined' | 'holiday' | 'failed' (AMD-0018 §2A). 'rejected' is retired.
schema_version (version INT, applied_at TIMESTAMP)
store_meta     (key TEXT PRIMARY KEY, value TEXT)
                -- key 'store_dir' records the absolute directory the parquet views were built
                -- against, so a relocated store is detected rather than silently misread (AMD-0017)
```

### 3.3 Rules
- The Parquet-backed views bake an absolute glob at `init_schema()` time.
  `store_meta['store_dir']` records the directory they were built against
  and `Store.connect()` verifies it (AMD-0017): read-write recreates the
  views against the current directory and logs the change; read-only raises
  `StoreRelocatedError` naming both paths. A missing record means first
  use, not relocation. Reading a store whose views point elsewhere is
  prohibited — the dangerous mode returns **wrong** rows, not no rows.
- Every validation rule that depends on prior state must distinguish
  **applied-and-passed** from **could-not-be-applied** (AMD-0017, CI-6).
  For the 25%-jump rule: on a date with any earlier row in `bars_raw`,
  `prior_close` missing for more than 5% of that day's members
  **quarantines** the day (AMD-0018 §2A) with reason `jump rule inapplicable: prior_close missing for N of
  M members`. `jump_rule_applied = False` is legitimate only on a genuine
  first-ever ingest date, where it is recorded rather than counted as a
  pass. Any later rule with a prior-state dependency inherits this.
- Store bars as received (`bars_raw`, tagged with the source's adjustment
  `basis`) and corporate actions (`splits`, `dividends`) separately; `bars` is
  materialised from them by `argus/data/adjust.py`. Free sources deliver
  split-adjusted history, so the canonical basis of `bars` OHLCV is
  **split-adjusted**, with `adj_close` additionally dividend-adjusted
  (factor Π(1 − dividend/prev_close) applied backwards).
  **A dividend must be on the same basis as the price it divides**
  (AMD-0019 §2B): before use in that factor an `as_paid` amount is divided
  by the cumulative split ratio applied to that symbol between the ex-date
  and the adjustment reference date — the same cumulative factor that
  split-adjusts the prices — while a `split_adjusted` amount is used as
  stored. Mixing the two overstates the adjustment by the split ratio: a
  4:1 split makes every earlier dividend count four times over, and
  `adj_close` carries that error into every return-type feature in §5.
    Each source's basis is established by **measurement**, recorded in
  `dividends.basis`; a source whose basis cannot be established is a stop,
  never a default.
    A symbol's dividend for an ex-date is the **sum of that source's
  records** for it, taken after source precedence and after basis
  normalisation (AMD-0027 §2A, §2B) — one row per vendor record, one total
  per ex-date.
  **Deduplicate before summing** (AMD-0029 §2B): records of one
  `(symbol, date, source)` sharing `cash_amount`, `declaration_date` **and**
  `frequency` are **one** dividend, however many `vendor_id`s they carry.
  Keying on the vendor record id stopped a genuine second dividend being
  discarded and removed an accidental guard against a duplicated one; this
  restores that guard deliberately, on fields rather than by collapsing.
  Where a source supplies neither field, fall back to `cash_amount`
  equality and **warn that the dedupe was weakened**.
  **Vendor completeness** (AMD-0027 §2D): where two sources' normalised,
  summed totals for one `(symbol, date)` differ by more than **one cent and
  2% relative**, the adjustment takes the **larger**, records which source
  supplied it, and warns with both figures. The justification is
    asymmetry — a vendor omitting a component is observed (Polygon carries
  one of FCX's two 0.075 components), a vendor inventing one is not. The
  comparison must be on **basis-normalised** amounts, or a split ratio
  reads as a completeness gap.
  **The larger-total rule does NOT apply where one total is an integer
  multiple of the other within one cent** (2×, 3×, …) — that is the
  **duplicate** signature, not the omission one, and "take the larger" is
  then exactly backwards (AMD-0029 §2C). Measured: TEL 2024-11-22 (1.30
  against 0.65) and SKYD 2026-09-15 (0.05 against 0.10). Such a pair is
  warned, left on source precedence, and named for attribution.
  Price columns and `adj_close` are stored **DOUBLE** (AMD-0019 §2C);
  float32 puts a 6e-8 relative floor under every published close and every
  return derived from one. When a new split
  arrives, the symbol's history is re-adjusted and `adj_version`
  increments; nothing is overwritten silently. §5 features use
  split-adjusted OHLCV; return-type features (`ret*`, `mom12_1`, `rs_*`)
  use `adj_close`.
- GICS classification: sector and sub-industry from the public S&P 500
  constituent table, mapped to the 25 GICS industry groups by the static
  `config/gics.yaml`; FMP `profile` is the fallback for symbols the table
  lacks. A member without an industry group fails validation.
- Canonical ticker form: `BRK.B`. Provider forms (`BRK-B`, `BRK B`,
  `BRK/B`) are mapped in `argus/data/tickers.py` at every boundary.
- **`bars_raw` records what the provider returned, always** (AMD-0018 §2A,
  CI-9). No validation verdict may prevent a fetched row from being stored.
  Validation records a judgement *about* a day; it is not a gate on
  persisting it. The quality seam is `bars_raw` → `bars`
  (`argus/data/adjust.py`).
- Publication admits a day **only** where `ingest_log.status = 'ok'`
  (AMD-0021 §2C) — never "any status other than `'quarantined'`". A day
  holding `bars_raw` rows with no completed verdict is unjudged data, and
  the remedy is `ingest revalidate`, not publication. A blocklist admits
  every status invented after it was written, and AMD-0019 §2E invented
  one. A judging failure **always** writes an `ingest_log` row, in
  `revalidate_range` as well as `ingest_polygon_day`: a path that fails
  without recording lets a day keep a stale verdict indefinitely.
  A day-level verdict is a vendor-fault finding. It
  **never withholds a symbol-day for carrying a `bar_flags` row**
  (AMD-0019 §2A; AMD-0018 §2A's exclusion clause is withdrawn). A flag is
  an advisory that travels with the row: consumers join `bar_flags` on
  `(symbol, date, source)` and decide for themselves. A `jump_unexplained`
  flag on a member is the most interesting row of the night, not a row to
  delete — and on the measured sample 51 of 51 such flags were real price
  moves corroborated by an independent source to 1e-5.
- **Never substitute across sources** to fill a flagged or withheld
  symbol-day (AMD-0019 §2A). Source precedence (Polygon over yfinance)
  decides which source supplies a symbol's series; a flag does not re-open
  that choice. Switching source on the day of a large move mixes two
  adjustment bases at the worst possible moment and is not reproducible.
- **Aggregates exclude, series do not** (AMD-0019 §2A). `composites`,
  `market_daily` and `sector_daily` exclude flagged symbol-days from their
  equal-weight means — one bad print distorts a 500-member average — and
  report the count excluded per date (CI-8, §6.1). A symbol's **own**
  series keeps the row: a hole severs the price history and breaks every
  252-day momentum and relative-strength feature crossing it, which is the
  damage CI-2 exists to prevent.
- `ingest_log.status` ∈ `{'ok','quarantined','holiday','failed'}`
  (AMD-0018 §2A). `'ok'` — stored, no day-level fault; any symbol flags
  counted in `detail`. `'quarantined'` — **stored in `bars_raw`** but
  carrying a day-level fault, so not published to `bars`. `'failed'` —
  nothing was fetched. `'rejected'` is retired: it conflated "judged
  faulty" with "not stored". `backfill_polygon` resumes past
  `('ok','holiday','quarantined')`; re-judging is `ingest revalidate`'s
  job, which reads `bars_raw` and calls no provider (AMD-0018 §2D, §2E).
- Nightly validation (`argus/data/validate.py`). A day is **quarantined**
  (stored in `bars_raw`, not published to `bars`) if < 95% of members on
  that date have a bar; if volume is zero for > 2% of them; if the jump
  rule is inapplicable per AMD-0017 §2B; or if **≥ 20% of members on that
  date are flagged `jump_unexplained`**. A `|close/prior_close − 1| > 0.25`
  move is otherwise **a flag on that symbol-day, not a verdict on the
  day** (AMD-0018 §2C): `jump_split_reconciled` where `splits` holds a row
  for that `(symbol, date)` consistent with the move, `jump_unexplained`
  otherwise. Flags go to `bar_flags` and are counted in
  `ingest_log.detail`. The rule is **recorded** for every symbol in the
  fetched frame and **decided** over `members_on(d)` only: a symbol that
  is not a member on `d` — a former member whose ticker has since been
  reassigned, or a configured ETF — can never contribute to a day-level
  verdict (AMD-0018 §2B). Record widely, decide narrowly. The
  classification check applies to **current members only**
  (AMD-0016 §2C): a historical-only member without an industry group never
  quarantines a day — `validate_day` returns `n_unclassified_members` and
  the day is stored. Rejecting on historical classification was
  miscalibrated; it rejected every day before hanshof's last snapshot.
  Every verdict is logged to `ingest_log` and surfaced in the report.
  The 20% breadth figure separates a vendor-side failure, which is
  near-total, from real market action, where individual members moving
  more than 25% on the heaviest sessions number in the tens, not the
  hundreds. It is a named constant beside `_COVERAGE_MIN_PCT`, changeable
  only by Amendment, and a test must fail without it (CI-6).
- A symbol's `bars` tail is bounded **only where the ticker was reassigned
  to a different entity** (AMD-0021 §2B, narrowing AMD-0018 §2F). The
  discriminator is a **trading gap**, not rename continuity: where
  `bars_raw` is continuous across the final `membership.end_date` — no gap
  exceeding **20 trading days** — the post-exit bars are the same
  company's and are **retained**, because a company that merely leaves the
  index keeps trading and may re-enter. Where the gap exceeds 20 trading
  days the tail is excluded and the symbol warned with its gap length:
  that is the reassignment hazard, where joining the two runs would splice
  a different company's prices onto a member's history.
  `config/ticker_renames.yaml` continuity still suppresses the warning.
  Rename continuity alone was the wrong test — it dropped 118,027 bars for
  AAL, AAP, ALK, K, M and WHR, companies still trading that had simply
  left the index, and that loss made the §3.3 survivorship gap worse
  rather than better. **Leading history before the first `start_date` is
  retained unconditionally** (AMD-0019 §2D). `MaterialiseReport` therefore
  reports two separate figures — `n_bars_before_first_membership`
  (counted, never warned) and
  `n_bars_after_final_end_without_continuity` (warned per symbol, the §2F
  hazard). A single combined counter fired 3,403 times at WO-0007 and was
  a warning channel nobody would read. Untreated, a reverse split at the new company appears as a
  discontinuity in the old member's history and corrupts every 252-day
  momentum and relative-strength feature crossing it — the damage CI-2
  guards against for renames.
- Reconciliation: 20 members per night against IBKR daily bars, the sample
  placing unresolved `jump_unexplained` flags first (AMD-0019 §3). Every
  comparison is written to `reconcile_log`. **The gate is per-field, never
  an aggregate rate** (AMD-0020 §2A).
  **Close is the reconciliation**: it passes when `max |pct_diff| ≤ 0.5%`
  **and** at most one comparison exceeds `0.1%`, with every exceedance
  named in the report. At n=100 a `breach_rate < 0.01` gate permits zero
  breaches and cannot express "one symbol needs a look"; that was a
  criterion of mine, not a bar.
  **Volume is recorded, not breached**: `reconcile_log.breach` is false for
  volume rows. Our consolidated volume and IBKR's `TRADES` volume are not
  the same quantity — median ours/theirs 2.03×, p5–p95 1.35–2.78×,
  systematic across all 20 symbols, while Polygon and yfinance agree with
  each other to 0.03%. The volume gate is therefore on **drift**, not
  level: alert when the sample median ratio moves more than 25% from the
  trailing 20-session median. A stable ≈2× is a fact about two vendors; a
  jump to 5× means one of them broke.
- Corporate actions are stored **per source** and never overwritten across
  sources: PK `(symbol, date, source)` on both `splits` and `dividends`
  (AMD-0012). WO-0007 resolves duplicates by the same precedence as bars —
  Polygon over yfinance — and records in `MaterialiseReport.warnings` any
  `(symbol, date)` where the sources disagree on a split ratio by more than
  0.1% or on a dividend by more than one cent. **Dividend amounts are
  normalised to one basis with the same `split_cum` before being compared**
  (AMD-0021 §2D): Polygon stores `as_paid` and yfinance `split_adjusted`
  (measured, WO-0013), so comparing raw amounts reports the split ratio as
  a vendor disagreement — 228 warnings over 42 symbols, every one generated
  by the correction itself. A split dated **on** the ex-date is divided
  out: the divisor takes the last bar **before** the ex-date, because the
  dividend was declared before the split.
- **Every symbol in the current constituents table has exactly one open
  membership interval** (`end_date IS NULL`) (AMD-0014). If it is in the
  index today it is a current member; no derivation may leave it without a
  row. `members_on(today)` must equal the current table's symbol count. A
  shortfall is a failure, never a reported statistic.
- A **ticker rename is one continuous membership under a changed symbol**,
  never a removal plus an addition (AMD-0014). Pairs are read from
  `config/ticker_renames.yaml`; the old interval closes the trading day
  before the effective date (or at hanshof's last snapshot H when the date
  is unknown) and the new interval opens immediately after, so no date
  falls between them.
- Membership intervals are **closed on both ends** (AMD-0011):
  `members_on(d)` is `start_date <= d AND (end_date IS NULL OR d <= end_date)`.
  Re-added symbols get a second interval; intervals for one symbol never
  overlap.
- Composites are equal-weight, rebalanced daily, over members per
  `membership` as of each date.
- Bars coverage for **delisted** historical members is incomplete
  (AMD-0015 §2B): the free source serves no data for a material share of
  them, so point-in-time membership alone does not eliminate survivorship
  bias. Every consumer of `composites` must carry coverage with the figure
  it reports — see §6.1.

## 4. Universe and baselines
- **Stocks:** S&P 500 members as of each date (currently ≈503 tickers).
    Ticker renames are mapped in `config/ticker_renames.yaml` so a company's
  membership stays continuous across a symbol change (AMD-0014).
  `symbols` covers **every** symbol that ever appears in `membership`, not
  only current members; a historical-only symbol takes its classification
  from the rename target's group where mapped, else FMP `profile`, else
  NULL and counted (AMD-0016 §2C).
  **Bars lookup follows the rename chain forward** to the current symbol
  via `Store.resolve_symbol(symbol, as_of)`, because the free sources serve
  a renamed company's whole history under its new ticker. Membership keeps
  the historically correct ticker; only the lookup is redirected, and the
  redirection is recorded. An unmapped chain counts as `without bars` in
  §6.1's coverage rather than dropping out silently (AMD-0016 §2D).
- **Baselines:** `EQ_SPX` (computed equal-weight composite), `SPY`, `RSP`;
  11 sector composites `EQ_S_<GICS_SECTOR>` and 25 industry-group
  composites `EQ_IG_<GICS_INDUSTRY_GROUP>`; sector SPDRs (XLK XLF XLV XLY
  XLP XLE XLI XLB XLU XLRE XLC) as cross-checks.
- **Ratio pairs** (config/universe.yaml): SMH/SPY, XLE/SPY, XLK/XLP,
  XLY/XLP, SPHB/SPLV, IWF/IWD, RSP/SPY, HYG/IEF, CPER/GLD.
- **Overlay:** an operator-supplied watchlist (config) is scored with the
  same features but excluded from composites; flagged `overlay=true`.

## 5. Stock-level features
Computed on adjusted daily bars; lookbacks live in `config/features.yaml`.
Every feature also gets a cross-sectional percentile (0–100) across the
universe and within sector (`<feature>_pct`, `<feature>_pct_sector`).

| Factor | Feature | Definition |
|---|---|---|
| Trend | `sma20 sma50 sma150 sma200` | simple MAs of close |
| | `slope20_5`, `slope50_10` | sma_n / sma_n[−k] − 1 |
| | `ma_stack` | 1 if close>sma50>sma200; −1 if close<sma50<sma200; else 0 |
| | `trend_template` | close>sma150>sma200 ∧ sma200>sma200[−20] ∧ close≥0.75·hi252 ∧ close≥1.3·lo252 |
| | `adx14` | Wilder ADX |
| | `clenow90` | annualised exp-regression slope of ln(close) over 90d × R² |
| Momentum | `ret5 ret21 ret63 ret126 ret252` | close/close[−n] − 1 |
| | `mom12_1` | close[−21]/close[−252] − 1 |
| | `macd_hist` | (EMA12−EMA26) − EMA9(EMA12−EMA26) |
| Relative strength | `rs_spx`, `rs_sector`, `rs_ig` | close / EQ_SPX; / sector composite; / industry-group composite |
| | `rs_spx_nh63` | 1 if rs_spx at 63-day high |
| | `rs_rank` | percentile 1–99 of 0.4·ret63 + 0.2·ret126 + 0.2·ret189 + 0.2·ret252 |
| | `rs_rank_sector`, `rs_rank_ig` | same, within sector / industry group |
| | `beta60` | OLS beta of daily returns vs SPY, 60d |
| Volatility | `atr14`, `atr_pct` | Wilder ATR; atr14/close |
| | `dist20_atr` | (close − sma20)/atr14 |
| | `hv20 hv60 hv_rank252` | annualised std of log returns; percentile of hv20 over 252d |
| | `bb_width`, `bb_width_pct252` | (upper−lower)/mid for BB(20,2); 252d percentile |
| | `squeeze` | 1 if BB(20,2) inside Keltner(20, 1.5·ATR) |
| Flow | `rvol` | volume / sma50(volume) |
| | `updown_vol20` | Σvol(up days) / Σvol(down days), 20d |
| | `dist_days25` | count of days with close ≤ prev·0.998 ∧ vol > prev vol, 25d |
| | `obv_slope20`, `cmf20` | OBV 20d regression slope / close; Chaikin Money Flow |
| Mean reversion | `rsi14`, `rsi2` | Wilder RSI |
| | `z20` | (close − sma20)/std20 |
| | `consec_down`, `consec_up` | run lengths |
| Structure | `pct_from_hi252`, `pct_from_lo252` | close/hi252 − 1; close/lo252 − 1 |
| | `donchian20_hi`, `donchian55_hi` | 1 if close ≥ max(high, n) |
| | `base_len`, `base_depth` | days since hi63; close/hi63 − 1 |
| | `gap_pct`, `nr7` | open/prev close − 1; 1 if today's range is lowest of 7 |
| Risk | `dd126`, `ulcer63`, `sharpe63` | max drawdown; Ulcer index; rolling Sharpe (rf=0) |
| Events | `days_to_earnings`, `days_since_earnings`, `pead_gap` | from `events`; gap % on earnings day |
| Liquidity | `adv20_usd` | 20d mean of close·volume |
| Candle geometry (AMD-0023) | `body_pct` | abs(close − open) / (high − low); NULL where high = low |
| | `upper_wick_pct`, `lower_wick_pct` | (high − max(open,close))/(high − low); (min(open,close) − low)/(high − low) |
| | `marubozu` | sign(close − open) where `body_pct` ≥ 0.90, else 0 |
| | `doji` | 1 where `body_pct` ≤ 0.10, else 0 |
| | `range_atr` | (high − low) / atr14 — today's candle in the stock's own volatility |
| Levels (AMD-0023) | `pivot_d r1_d s1_d r2_d s2_d` | from the prior session's H/L/C: P=(H+L+C)/3, R1=2P−L, S1=2P−H, R2=P+(H−L), S2=P−(H−L). `_w`/`_m` variants from the prior week/month |
| | `dist_pivot_atr`, `dist_r1_atr`, `dist_s1_atr` | (close − level) / atr14 |
| | `swing_hi`, `swing_lo` | fractal pivot: a bar whose high (low) is the extreme of the 5 bars either side |
| | `dist_res_atr`, `dist_sup_atr` | distance to the nearest clustered swing level above/below, in ATR; levels within 0.5·ATR are one level |
| | `res_touches`, `sup_touches` | touch count of that level — a level tested four times is not the same object as one tested once |

**Level and candle distances are in ATR, never per cent** (AMD-0023 §2D):
"2% from resistance" means something different for a 12%-volatility
utility and a 70%-volatility biotech, and ATR units are what make the
figure comparable across the universe, which the percentile system above
depends on.

**Candle features are confirmation terms, never triggers** (AMD-0023 §2D).
A single daily candle pattern is weak evidence alone; its value is a
marubozu **on a breakout day**, or a doji or long lower wick **at a tested
support level**. PID-ARGUS-0004's factor-IC study decides whether each one
carries information; one that does not stays a displayed field and leaves
the scoring.

## 6. Market and sector layer — the rotation detector

### 6.1 Breadth (members of EQ_SPX)
`composites` and every breadth field carry `n_members`,
`n_members_with_bars`, `n_members_classified` **and** `n_members_flagged`
per date (AMD-0019 §2A), and the equal-weight composite is computed
over members with bars, excluding flagged symbol-days. A breadth percentage is reported alongside its
coverage ratio, never bare. Where coverage on a date is below 95%, that
date's breadth figures are flagged in `market_daily.coverage_flag` and
excluded from PID-ARGUS-0004's lead-time study unless explicitly included.
A sector or industry-group composite is computed over **classified**
members only and reports its classification coverage with it (AMD-0016
§2C). Every coverage figure here **reports a measured value or is NULL — never
a constant** (AMD-0021 §2F): a field that always reads `0` says "nothing
was excluded" when it means "not computed", and is indistinguishable from
a measurement at the point of reading. `n_symbol_days_flag_excluded` in
particular reports the real count or `NULL`, and the Work Order that
builds the aggregates calls `equal_weight_aggregate` rather than
reimplementing it. This is how the survivorship and classification gaps of
§3.3 stay measurable per date instead of becoming unstated optimism in
every backtest (AMD-0015 §2B, CI-8).

`pct_above_20/50/200`; advance–decline line; `nh20−nl20`; `nh252−nl252`;
McClellan oscillator = EMA19(r) − EMA39(r) with r = (adv−dec)/(adv+dec),
and its summation; `% with rsi14 > 50`; `RSP/SPY` and its 20d slope.

### 6.2 Relative Rotation (per composite vs EQ_SPX; computed at industry-group and sector level — ADR-0005)
```
rs        = 100 · EQ_group / EQ_SPX
rs_ratio  = 100 + (rs − SMA(rs, 50)) / STD(rs, 50)
roc       = rs_ratio / rs_ratio[−10] − 1
rs_mom    = 100 + (roc − SMA(roc, 50)) / STD(roc, 50)
quadrant  = Leading (ratio>100 ∧ mom>100) | Weakening (ratio>100 ∧ mom≤100)
          | Lagging (ratio≤100 ∧ mom≤100) | Improving (ratio≤100 ∧ mom>100)
heading   = atan2(rs_mom − rs_mom[−5], rs_ratio − rs_ratio[−5])  (degrees)
d_rs_mom5 = rs_mom − rs_mom[−5]
```
Early signal: `d_rs_mom5 < 0` on 3 consecutive sessions while Leading
(exit side); `> 0` on 3 consecutive sessions while Lagging (entry side).

### 6.3 Group internals
- `pct_above_20/50` of members; `nh20`; **divergence** = composite within 2%
  of its 63d high ∧ `pct_above_20` fell > 15 points over 10 sessions.
- `dist_days25` and `updown_vol20` on the composite.
- `rank_rs21`: rank of groups (within level) by 21d return vs EQ_SPX;
  `rank_delta10` = rank[−10] − rank (positive = climbing).
- `vol_share` = group dollar volume / total; `vol_share_z` vs 60d.

### 6.4 Cross-market
- Ratio z-scores: `z = (ROC10 − mean252(ROC10)) / std252(ROC10)` per pair;
  flag |z| > 1.5.
- `dispersion21` = std of 21d returns across sector composites;
  `avg_corr21` = mean pairwise correlation of sector daily returns, 21d.
  Rotation regime when dispersion percentile(252) > 70 ∧ avg_corr
  percentile(252) < 40.

### 6.5 Rotation score and triggers
```
rotation_score = z252(d_rs_mom5) + z252(Δpct_above_20 over 10d) − z252(Δdist_days25 over 10d)
               + z252(rank_delta10) + z252(vol_share_z)
EXIT_WARNING : quadrant ∈ {Leading, Weakening} ∧ rotation_score ≤ −1.5 ∧ divergence
ENTRY_WATCH  : quadrant ∈ {Lagging, Improving} ∧ rotation_score ≥ +1.5 ∧ vol_share_z > 0.5
```
Thresholds are initial values in `config/features.yaml`; PID-ARGUS-0004
calibrates them.

### 6.6 Regime label
```
bull_broad  : EQ_SPX > sma200(EQ_SPX) ∧ pct_above_50 > 55
bull_narrow : SPY > sma200(SPY) ∧ pct_above_50 < 45 ∧ rsp_spy_slope20 < 0
correction  : SPY < sma50(SPY) ∧ 25 ≤ pct_above_50 ≤ 55
bear        : SPY < sma200(SPY) ∧ pct_above_200 < 40
else        : neutral
```
Evaluated top to bottom; first match wins.

## 7. Ranking, lists and sizing (PID-ARGUS-0004)
Playbooks in `config/playbooks.yaml` applied to percentile features, with
sector-neutral variants:

| Playbook | Core factors | Active regimes |
|---|---|---|
| Leaders | rs_rank, trend_template, clenow90, updown_vol20, −dist20_atr (penalty > 2 ATR) | bull_broad, bull_narrow (ENTRY_WATCH/Leading groups) |
| Pullback buys | ma_stack=1, dist20_atr ∈ [−2,−0.5], rsi14 ∈ [38,55], updown_vol20 ≥ 0.9 | bull_*, correction |
| Breakout watch | squeeze, bb_width_pct252 < 20, pct_from_hi252 > −5%, rvol falling | all |
| Bounce | ma_stack ≥ 0, rsi2 < 10, z20 < −2, close > sma200 | correction |
| **Weakness — short / trim / avoid** | ma_stack=−1, rs_rank < 30, dist_days25 ≥ 4, Donchian-20 low break; `marubozu = −1` on the break as confirmation | **Always runs, every regime** (AMD-0023 §2C). The regime sets the actionability column only: `shortable` in bull_narrow/correction/bear, `trim/avoid only` in bull_broad/neutral |

Hard filters: `adv20_usd ≥ 20,000,000`; `days_to_earnings` shown and
highlighted if ≤ 10.

**Rotation tags; it never removes** (AMD-0023 §2A). The earlier filter —
*"members of EXIT_WARNING groups excluded from long lists"* — is
**deleted**. Rotation is information about a **group**; it is not a verdict
on a **company**, and using it as a gate was the fourth instance in this
project of a judgement being used to delete data (AMD-0018 §2A,
AMD-0019 §2A, AMD-0021 §2C). Instead:

- Every candidate carries its group's `quadrant`, `rotation_score` and
  `ENTRY_WATCH`/`EXIT_WARNING` state as **displayed fields**.
- Rotation may **tilt the ordering** and may not determine membership:
  `rank_final = rank_raw + clamp(0.5 · z(rotation_score), −10, +10)`
  percentile points, with **both `rank_raw` and `rank_final` shown** so the
  size and direction of the effect is visible rather than baked in. The
  tilt is bounded by construction, so no rotation state can push a name off
  a list.
- A high `rs_sector` or `rs_ig` percentile inside an `EXIT_WARNING` group is
  **highlighted, not penalised twice**. Rotation is computed on a group
  **average** while dispersion inside a group is wide, so the name holding
  up while its sector is sold is frequently the position institutions keep
  — the most interesting observation in that group, not a disqualified one.

### 7.1 Report layout — rotation leads as context (AMD-0023 §2B)
The report opens with rotation, then lists candidates independently of it.

1. **Headline — rotation and regime.** The regime label, what changed since
   yesterday, and two explicit lists:
   - **Rotating IN** — groups in `ENTRY_WATCH`, or `Improving` with
     `d_rs_mom5 > 0` three sessions running, each followed by **its member
     tickers that appear on any candidate list**.
   - **Rotating OUT** — groups in `EXIT_WARNING`, or `Leading`/`Weakening`
     with `d_rs_mom5 < 0` three sessions running, same treatment.

   A turning group with no candidates is **still listed, with an empty
   ticker set**: that a group is moving and holds nothing worth buying is
   itself a finding, and suppressing the row would hide it.
2. **Long candidates** — ranked per playbook, each row tagged with its
   group's quadrant and rotation state, **not filtered by either**.
3. **Weakness — short / trim / avoid** — always present (§2C above).
4. **Plain ticker lines** — one comma-separated line per bucket for
   copy-paste into the operator's own charting tool. A convenience inside
   the report, **not** an integration with any third-party platform; no
   such integration is in scope.

Every ticker shown carries its nearest support and resistance levels (§5
Levels) beside the ATR stop, so the operator can judge whether the stop
sits somewhere sensible rather than taking `1.5 · ATR` on faith.

**Paper-account sizing (config):** equity 100,000 GBP; risk per trade 1%;
stop 1.5·ATR14 (long) / 2·ATR14 (short); position cap 10% of equity; max
10 open; max 3 per sector; gross ≤ 120%, net within ±60%.

## 8. Commentary layer (PID-ARGUS-0003; ADR-0004)
- **Evidence pack** (≤ 12K tokens, JSON, rounded): date, regime, breadth
  (≤12 fields), ratios with |z|>1.0, 11 sector rows + flagged industry
  groups, exit_warnings, entry_watch, candidates (long ≤15, short_avoid
  ≤10, each with levels, stop, days_to_earnings, 3 reasons), overlay
  watchlist verdicts, and ≤5 of yesterday's claims with then/now metrics.
- **Prompt:** static system prompt (role, rules, output schema) first, pack
  second, task last. Rules: numbers only from the pack; cite the metric for
  every claim; "short" means exit/avoid/inverse unless the account allows
  margin (paper does); output is a research list, not orders; ≤ 600 words;
  end with "what confirms / what kills this view in the next 5 sessions".
- **Routing:** nightly brief `LLM_MODEL_BRIEF` (temperature 0.3, max_tokens
  1500, timeout 180 s, one retry); weekly review `LLM_MODEL_REVIEW`;
  classification for grading `LLM_MODEL_FAST`; embeddings `LLM_MODEL_EMBED`.
  ≤ 2 concurrent requests.
- **Grading:** sector and symbol calls parsed per brief; realised relative
  return attached at 5/10/20 sessions; rolling hit-rate in the report.

## 9. Backtesting and evaluation (PID-ARGUS-0004/0005)

**Research protocol — binding on every Work Order in these phases
(AMD-0028 §2B).** Six rules, and a study that breaks one is not evidence:

1. **Pre-register.** The hypothesis, feature set, horizon and **the bar
   that counts as success** go into the Work Order **before** the study
   runs. A result reinterpreted afterwards is not evidence; an acceptance
   criterion is this project's instrument for that, so the discipline costs
   nothing.
2. **Purged, embargoed walk-forward CV.** Holding-horizon labels overlap,
   so ordinary k-fold leaks: purge training observations whose label window
   intersects the test window, and embargo a gap after it.
3. **Count the trials and deflate for them.** The number of configurations
   tried is itself a parameter — the best of twenty backtests is not a
   discovery. An undeflated Sharpe out of a search is not reportable.
4. **Model costs.** Commission, spread at the traded size, slippage. A
   result that does not survive costs did not happen.
5. **Beat the dumbest adequate baseline.** Equal-weight buy-and-hold for
   selection; a plain Chandelier exit for exits; a fixed fraction for
   sizing. A model that cannot beat the trivial version is not a model.
6. **Coverage travels with every figure** (CI-8): R5's 46.4%
   delisted-member coverage is an input to every historical result and is
   stated beside it, weighted rather than merely mentioned.

**The IC study is a gate** (AMD-0028 §2A), not a deliverable: nothing
downstream — thresholds, weights, sizing, exits — is authorised until a
feature set carries information out of sample, net of costs.

1. Lead-time study on sector ETFs (1998→) and composites: for every ≥10%
   relative drawdown, sessions between each §6 signal and the peak; keep
   signals with median lead ≥ 5 sessions and false-positive rate < 60%.
2. Factor IC: daily rank-correlation of each feature with forward 10/20-day
   relative return; drop |IC| < 0.01 or unstable sign.
3. Playbook walk-forward (train 3y / test 1y, roll), point-in-time
   membership, 5 bps/side, ATR stops, §7 sizing.
4. Optional ML ranker (LightGBM) with purged k-fold + 20-day embargo;
   trained on CPU; deployed only if out-of-sample IC beats the rules.

## 10. Operations and security
- IBKR history requests are pacing-bound: the nightly budget is 46,
  against an implemented pacer ceiling of 50 per 10 minutes and a vendor
  limit of ≈60 (AMD-0020 §2D). The reconciliation sample size and the ETF
  list are therefore **coupled to the pacer**: increasing either makes the
  nightly run sleep, and is an architectural decision rather than a
  parameter change. WO-0009 stays inside the budget or sleeps deliberately
  and reports the wall time it cost.
- `IB_PORT` must be a paper port (AMD-0019 §3). A non-paper port makes the
  reconcile step report a configuration error; since the step is
  `required=False`, the night continues rather than failing.
- **Gateway topology** (AMD-0021 §2E, corrected AMD-0026 §2A): the
  **paper** gateway runs on `dell-debian`; any live gateway runs on another
  host and is never reachable from this application's configuration. The
  absence of a live **IBKR gateway process** on the nightly host is
  verified at install (WO-0009 AC10a), not assumed — and the check
  identifies the **listening process**, never merely a bound port. IBKR's
  live port numbers are conventions, and on this host another service
  legitimately occupies one; a non-IBKR service on an IBKR-numbered port is
  a pass and is none of this project's business. All three barriers below
  hold as delivered, with nothing to remove first. A gateway listening on
  a live port on `dell-debian` is a misconfiguration to be removed, not
  something to be defended against by port number alone.
- **The paper account is asserted on connect, not inferred from the
  port.** After `connect(readonly=True)` the managed account identifier
  delivered in the handshake must carry IBKR's paper prefix (`DU`/`DF`);
  otherwise the client disconnects immediately and raises. **Only a
  boolean leaves the check** — the identifier is never logged, stored,
  filed in evidence or placed in an exception message (CI-7). This reads
  handshake data already received and is **not** an account, order or
  position request, which WO-0008 §3 continues to exclude. With the live
  gateway on another host, `ib_host`'s loopback default (R3) is the first
  of three independent barriers, the port allowlist the second and this
  assertion the third.

**Schedule (UK time; systemd timers; service user `argus`):**
```
23:30 ingest      Polygon grouped-daily for T; FMP calendars; validate
23:45 reconcile   IBKR sample + IV30
00:00 features    features, composites, market/sector layer, ranks
00:15 brief       evidence pack → gateway → briefs/
00:20 report      HTML + Markdown; optional watchlist update
```
- Secrets only in `.env` (0600, owner `argus`): `POLYGON_API_KEY`,
  `FMP_API_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_*`, `IB_HOST`,
  `IB_PORT`, `IB_CLIENT_ID`, `IB_CLIENT_ID_WRITE`. Never in git.
- IB Gateway: paper login only; read-only API for the ingestion client id;
  watchlist writes from `IB_CLIENT_ID_WRITE` only (PID-ARGUS-0004).
- Least privilege: `argus` owns `/srv/argus-breakout/{store,out}`; DuckDB
  0640; MCP server binds localhost, read-only connection, allow-listed
  tools, 10 s query timeout, 10k row cap.
- Validation: symbols `^[A-Z][A-Z0-9.\-]{0,9}$`; ISO dates; all SQL
  parameterised.
- Logging: structured JSON, secrets redacted, request ids; MCP access log
  retained 90 days. No PII stored.
- Backups: nightly `store/` snapshot to a second disk. A restored or
  relocated snapshot must be opened read-write once (`argus init-store`,
  idempotent) so the Parquet views are rebuilt against their new path —
  `Store.connect()` enforces this (AMD-0017).

**Portability (ADR-0008, AMD-0004).** The application is built
container-ready and packaged in PID-ARGUS-0006: no absolute paths in
`argus/`, writes confined to `ARGUS_STORE_DIR` and `ARGUS_OUT_DIR`,
configuration (including `ARGUS_CONFIG_DIR`) and every network endpoint
from environment variables, the CLI as the only entrypoint, structured logs
to stdout, no root at runtime. The `uv.lock` of ADR-0007 is the input to
the future image build (`uv sync --frozen --no-dev`); the development
toolchain under `/srv/argus-breakout-tools` is never part of the delivered
artefact. Everything host-coupled (systemd units, `ops/nightly.sh`, backup
rsync) lives under `ops/` with no application logic, so a container
scheduler replaces it without touching `argus/`.

## 11. Phase map
See `PID.md` §6. Phase PIDs in `docs/pids/` carry the Work Order
decomposition and acceptance criteria for each phase.
