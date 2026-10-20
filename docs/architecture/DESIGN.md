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
| IBKR paper gateway (`ib_async`) | reconciliation sample (20 symbols/night, rotating), corporate-action truth, IV30 for ETFs/index | nightly | ≈60 historical requests / 10 min |
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
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, source TEXT)
                -- PK (symbol, date, source). date = ex-dividend date.
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
ingest_log     (date DATE, source TEXT, rows INT, status TEXT, detail TEXT, finished_at TIMESTAMP)
schema_version (version INT, applied_at TIMESTAMP)
```

### 3.3 Rules
- Store bars as received (`bars_raw`, tagged with the source's adjustment
  `basis`) and corporate actions (`splits`, `dividends`) separately; `bars` is
  materialised from them by `argus/data/adjust.py`. Free sources deliver
  split-adjusted history, so the canonical basis of `bars` OHLCV is
  **split-adjusted**, with `adj_close` additionally dividend-adjusted
  (factor Π(1 − dividend/prev_close) applied backwards). When a new split
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
- Nightly validation (`argus/data/validate.py`): a day is **rejected** (not
  published to `bars`) if < 95% of active members have a bar; if any close
  moves > 25% vs prior close with no split in `splits`; if volume is
  zero for > 2% of members; if any member lacks `gics_industry_group`.
  Rejection is logged to `ingest_log` and surfaced in the report.
- Reconciliation: 20 rotating members per night vs IBKR `ADJUSTED_LAST`
  daily bars; tolerance 0.1% on close, 10% on volume; breaches written to
  `reconcile_log` and surfaced.
- Corporate actions are stored **per source** and never overwritten across
  sources: PK `(symbol, date, source)` on both `splits` and `dividends`
  (AMD-0012). WO-0007 resolves duplicates by the same precedence as bars —
  Polygon over yfinance — and records in `MaterialiseReport.warnings` any
  `(symbol, date)` where the sources disagree on a split ratio by more than
  0.1% or on a dividend by more than one cent.
- Membership intervals are **closed on both ends** (AMD-0011):
  `members_on(d)` is `start_date <= d AND (end_date IS NULL OR d <= end_date)`.
  Re-added symbols get a second interval; intervals for one symbol never
  overlap.
- Composites are equal-weight, rebalanced daily, over members per
  `membership` as of each date (no survivorship bias).

## 4. Universe and baselines
- **Stocks:** S&P 500 members as of each date (currently ≈503 tickers).
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

## 6. Market and sector layer — the rotation detector

### 6.1 Breadth (members of EQ_SPX)
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
| Breakdown / short-avoid | ma_stack=−1, rs_rank < 30, dist_days25 ≥ 4, Donchian-20 low break | EXIT_WARNING groups; shorts only in bull_narrow/correction/bear |

Hard filters: `adv20_usd ≥ 20,000,000`; `days_to_earnings` shown and
highlighted if ≤ 10; members of EXIT_WARNING groups excluded from long lists.

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
- Backups: nightly `store/` snapshot to a second disk.

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
