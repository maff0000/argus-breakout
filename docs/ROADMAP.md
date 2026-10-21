# Roadmap — where Argus-Breakout should go, not what is approved

> **This file carries no authority.** It is a reminder, not an instrument.
> Nothing here approves, schedules or authorises work, and **no Implementer
> or Delivery Controller may act on it.** Only `PID.md`, a Phase PID, an
> Amendment or an approved Work Order authorises anything
> (`docs/governance/DELIVERY-CHAIN.md` §1). Items move out of this file by
> becoming one of those.
>
> Maintained by the Architect on the Product Owner's direction. Last
> updated 2026-10-21 (AMD-0024 §2F).

## What the product is, so the backlog is read correctly

A **stock screener** that identifies individual equities worth trading,
seen through a **sector-rotation lens**. Rotation reveals where money is
flowing and **preferences** candidates; it never determines membership of a
list (`PID.md` §2, AMD-0023 §2A, AMD-0024). Everything below is judged by
whether it makes the nightly list better, not by whether it is interesting.

---

## 0. Priority order and the research protocol (AMD-0028)

**Binding, and recorded so it is not relitigated.** Everything below is
read against this order:

1. **Finish Phase 0** — trustworthy data. Eight Amendments in three days
   corrected silent data defects, each of which would have produced a
   confident wrong backtest.
2. **PID-ARGUS-0002** — the §5 feature layer and composites.
3. **The IC gate.** The factor-IC and lead-time studies gate everything
   downstream: until a feature set carries information out of sample, net
   of costs, **no threshold tuning, no playbook weighting, no sizing work
   and no exit work is authorised.** A negative result closes the phase
   honestly and is worth more than a tuned system nobody can trust.
4. **Breadth before refinement.** Information ratio scales roughly as
   IC × √breadth, and 10 concurrent positions is ~100–200 trades a year —
   dominated by idiosyncratic variance for years whatever the exits do. The
   lever is §A4, and the data already arrives nightly.
5. **Sizing and portfolio volatility targeting.**
6. **Exits, last**, in this order: vol-scaled stop → staged trailing →
   partial exits → *measure the remaining prize* → only then a learned
   **trim** policy.

**Protocol for any study in phases 0004/0005** (DESIGN §9, AMD-0028 §2B):
pre-register the hypothesis and the success bar in the Work Order before
running; purged and embargoed walk-forward CV, because holding-horizon
labels overlap; **count the trials and deflate for them** — the best of
twenty backtests is not a discovery; model costs rather than assuming them
away; compare against the dumbest adequate baseline; and carry coverage
beside every figure (CI-8, R5's 46.4%).

**Non-negotiables for any automated exit** (AMD-0028 §2D): the stop is
**monotonic** — it never widens, or position sizing is fiction; the trail
multiplier is bounded and the bound is not a model output; a hard
per-position maximum loss no model may override; a portfolio drawdown halt
and a kill switch that does not need the agent to be healthy; and every
automated exit records the rule and inputs that fired it, because an exit
nobody can explain cannot be told from a lucky one.

### 0.1 On adaptive / AI-driven exits — sequenced, not rejected
The strongest argument for automation is **not** the model. It is that
**mechanising the decision removes the behavioural gap** — panic selling,
chasing, and the disposition effect of cutting winners early while holding
losers — which runs to whole percentage points a year and dwarfs anything
a stop formula adds. That benefit arrives with a plain vol-scaled staged
trail, needs no inference at all, and lands the moment there is an edge to
execute.

Two further findings worth keeping:
- **Trim decisions are counterfactually evaluable; entries are not.** A
  retail-scale position does not move the market, so every historical trade
  can be re-priced under *every* trim schedule on the **same path**, with
  no simulation feedback loop — and a trim fraction gives a graded outcome
  where a binary exit gives one bit. **If inference is spent anywhere, spend
  it on trims first.**
- **Live validation is impossible at this breadth.** Unpaired, 100–200
  trades a year cannot distinguish two exit rules; the standard error on a
  year's mean is about the size of the mean. Paired comparison in
  simulation can, which is why §2B's protocol is the only route.
- **Measure the prize before building.** Run the playbooks over history with
  a plain Chandelier exit and count the return left on the table by stops
  hit on trades that then ran another 2R. One day's work; it tells you
  whether the prize is 20bp or 2% before any model is written.

---

## A. Data gaps worth closing

### A1. Short interest and short float — the real gap
The weakness list (`DESIGN.md` §7) is **purely technical**. Short float is
the most informative non-price field on the short side: it is crowding and
squeeze risk in one number, and nothing in the current design approximates
it.

- **Decision point:** PID-ARGUS-0004 (calibration), where it can be tested
  against outcomes *before* paying for it — does adding short float
  measurably improve the weakness list?
- **Source if adopted:** Finviz Elite API (§F), or any vendor with an
  official API and a documented history.
- **Caveat:** short interest is reported **twice monthly with a settlement
  lag**. Any backtest must use the figure *as it was known on the date*,
  not the revised one, or it reads the future.

### A2. Float and shares outstanding
"Breakout on 3× volume" is a different event on a 20M float than on 2B
shares. Cheap to obtain, directly improves the `rvol` and
`dist_days25` readings.

### A3. Fundamentals as a guardrail — deliberately limited
A coarse quality screen (profitable, not a melting ice cube) would remove
some low-quality breakouts. **Kept narrow on purpose:** fundamentals are
where overfitting lives, and the brief is a technical screener. A guardrail
that *excludes*, not a factor that *scores*, and only if factor-IC shows it
helps.

### A4. Universe beyond the S&P 500 — we already own the data
Worth stating plainly so no vendor is bought for it: **Polygon's
grouped-daily call already returns every US ticker every night, and the
pipeline filters to S&P 500 members and discards the rest.** Widening to
mid- and small-caps is a **filter and storage decision**, not a data
acquisition problem.

What it would cost is not the data but the scaffolding: point-in-time
membership for a wider universe (the S&P 500 has `hanshof`; the Russell
2000 does not, free), liquidity floors that actually bite, and far more
survivorship exposure (R5 is already at 46.4% coverage for delisted S&P
members). Do this only with the coverage reporting of CI-8 in place.

---

## B. Rule for any new source (candidate for a standing ruling)

**No scraped source enters the nightly path.** A scraper makes unversioned
HTML the data contract: terms-of-service exposure, and breakage that looks
like a quiet night rather than an error. Several Finviz MCP servers are
Apify scrapers, one already deprecated (§F).

Any new vendor enters the way Polygon did: an **official API**, a key in
`.env` and nowhere else (CI-7), its own **pacer** inside the client so
callers cannot bypass it, its own **`source` tag** in the store so rows are
never silently mixed across vendors (AMD-0019 §2A), and a **measured**
statement of what its fields mean rather than an assumed one (the
WO-0013 `dividend-basis.md` standard, AMD-0021 §2A).

---

## C. Already-known follow-ups held outside Phase 0

- `n_symbol_days_flag_excluded` must report truthfully or be absent before
  any feature is computed — never a constant `0` (AMD-0021 §2F).
- The Work Order building the aggregates must **call**
  `equal_weight_aggregate`, not reimplement it.
- IBKR history pacing is budget-bound at 46 of 50 requests per 10 minutes
  (AMD-0020 §2D): growing the reconciliation sample or the ETF list is an
  architectural decision, not a parameter change.
- **`adj_close` is suspect on variable/special-dividend ex-dates** until
  WO-0015 reports (AMD-0025 §2D). The named dates (PGR, FCX, WRB, CME,
  DVN, FANG, COP, EXE, F, HP, HST) are known-suspect inputs, and any
  feature study crossing them must say so — the limitation travels with
  the number, CI-8-style.
- **Rename classification from stored data: tried, measured, abandoned.**
  WO-0015 returned 500 candidates because index maintenance is pairwise —
  S&P replaces one name with another on a date, so every addition has an
  adjacent leaver, and VMRK paired with 32 of them. The distinguishing fact
  is corporate identity and no free source carries it. **Do not attempt
  this again from membership and price alone** (AMD-0027 §1c, R8). If it
  ever matters enough, the input is a corporate-actions feed or S&P's own
  announcements, not a cleverer signal.
- **Former members' history is not bootstrapped**, so 10 symbols' post-exit
  tails cannot be told from a reassignment (WO-0014 spec-gap 1). An
  ingestion decision, belonging with the R5 survivorship work.
- Recording a store-relocation repair in `store_meta` as a provenance
  event, rather than only a WARNING line (R7) — belongs to
  PID-ARGUS-0006, where relocation becomes routine.

---

## D. The final piece — AI review and ranking of the nightly list

The Product Owner's intent: the evening list is reviewed by a language
model that **ranks** the candidates, with access to the trading rules as a
skill and to stock news, to form a view.

**What exists to build on.** `DESIGN.md` §8 already has the evidence pack,
the prompt discipline ("numbers only from the pack; cite the metric for
every claim"), model routing, and **grading tables** that attach realised
relative return at 5/10/20 sessions to every call. The grading machinery is
the part that makes this safe.

**The rules as a skill.** `config/playbooks.yaml` is already the
machine-readable statement of the rules. The skill is that file plus the
active thresholds, serialised into the prompt, with §8's citation rule
extended: **cite the metric *and* the rule** being applied. A view that
cannot name the rule it rests on is not a review, it is prose.

**News.** Barchart or Yahoo were both named. Two hard constraints:
- **Point-in-time timestamps are mandatory** — a story enters date D's pack
  only if published at or before D's close. Without this, a backtest reads
  tomorrow's news today and the results are fiction that looks like skill.
  This is the single largest look-ahead risk in the whole system.
- §B applies: official API or nothing. Barchart has a commercial API;
  Yahoo has no official one (`yfinance` is unofficial, and is already
  accepted here **only** as a one-off historical bootstrap, never on the
  nightly path).

**The ranking question, and the answer the project already has.** Letting a
model reorder a trade list puts something non-reproducible in the decision
path. PID-ARGUS-0005 already sets the precedent for exactly this — an ML
ranker is *"deployed only if it beats the rules baseline out of sample"* —
and the same test applies here:

> The **rules** produce the ranked list. The AI produces a **review**: an
> explicit agree / disagree / caution per name, with reasons citing a
> metric and a rule, and its own ordering recorded as a **separate**
> ranking alongside the rules ranking. Both are graded by §8's existing
> tables. The AI's ordering becomes primary **only if it beats the rules
> baseline out of sample** — and until then it is advisory and visible,
> never silently authoritative.

This is also the honest answer to "is the local model actually adding
anything?", which is otherwise unanswerable.

---

## E. `argus-execution-agent` — a successor project, not a phase here

Risk-sizes a reviewed candidate and places the trade in the IBKR **paper**
account.

**It is a separate project** with its own repository, PID and safety
design. `PID.md` §7's first non-goal is unchanged and absolute:
**Argus-Breakout submits no order, to any account, ever.** The boundary is
that Argus-Breakout emits a reviewed, ranked list with levels and stops,
and sizing and order placement live wholly outside it. No Work Order in
this project may anticipate it.

**What this project hands over:** per-candidate levels, the ATR stop, the
nearest support and resistance with touch counts (AMD-0023 §2D), the
rotation tag, `days_to_earnings`, `adv20_usd`, and the sizing parameters
already in `DESIGN.md` §7 (1% risk, 1.5·ATR long / 2·ATR short stops, 10%
position cap, max 10 open, max 3 per sector, gross ≤ 120%, net ±60%).

**What its design will have to solve — the interesting part, and the
dangerous one:**
- **Write access is a different security posture entirely.** Everything
  here is read-only by construction: `readonly=True`, an order-API grep as
  an acceptance criterion, a paper-port allowlist, and a paper-account
  assertion on connect (AMD-0021 §2E). An execution agent deliberately
  gives up the first two of those. The remaining barriers — paper port,
  paper-account assertion, a separate `IB_CLIENT_ID_WRITE` — become
  load-bearing rather than belt-and-braces.
- **Idempotency.** A retried order is a doubled position. Every submission
  needs a client-side idempotency key and a reconciliation pass that can
  tell "my order" from "an order".
- **Bounded authority.** Maximum order value, maximum orders per session, a
  daily loss limit that halts, and a kill switch that does not depend on
  the agent being healthy to work.
- **An unambiguous audit trail**: which list, which review, which rule,
  which size, which fill — for every order, before any thought of leaving
  paper.
- **The transition to live is not a configuration change.** It is a
  separate decision with its own evidence, and nothing in either project
  should make it feel like flipping a flag.

---

## F. Finviz — researched 2026-10-21, not adopted

**Finviz is a cross-section; Argus is a time series.** Finviz answers "what
is true right now" across ~8,000 tickers with a far wider filter set than
ours, and does it better than we will. It does **not** appear to offer
point-in-time or historical screening — which is the one thing the stated
problem requires, because knowing *how early* a signal fires means
replaying history. A screener that only shows today cannot be calibrated.

Found: an **official Elite API** (Screener, Portfolio, News, Groups,
Insider, Managers, Funds, Calendars; 10 requests / 5 seconds, rolling
window, `429` + `Retry-After`), Elite at **$39.50/month or $299.50/year**.
**No official MCP server and none in the Claude connector registry**;
community servers exist (`tradermonty/finviz-mcp-server` in Python,
a .NET one, several Apify scrapers) and the main one needs Elite for full
function while **not documenting whether it uses the official API or
scrapes**.

**Decision (Product Owner, 2026-10-21): use it manually alongside the
Product Owner's own charting for reviewing the nightly list; keep it out of
the build for now.** Phase 0 was one Work Order from closing, and adding a
vendor would reopen a data layer that five Amendments had just finished
making trustworthy.

**What it would be worth returning for:** §A1 (short float) and §A2
(float), at the §A1 decision point, via the official API under §B. **What
it is not worth returning for:** technical indicators — total overlap with
§5, and taking a vendor's SMA or RSI would reintroduce exactly the
cross-source provenance problem AMD-0019 removed, where 51 symbol-days had
silently switched vendor on their most volatile day.
