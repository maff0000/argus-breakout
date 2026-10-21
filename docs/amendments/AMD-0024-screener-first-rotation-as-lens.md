# AMD-0024 — The purpose statement is corrected: a screener with a rotation lens, not a rotation detector

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `PID.md` §2 (Purpose), §3 (Target Outcome), §6 (phase map — PID-ARGUS-0002 renamed and §5 assigned), §7 (Non-Goals — news deferred, execution boundary stated); adds `docs/ROADMAP.md` |
| **Related ADR** | ADR-0005 |
| **Raised by** | Product Owner, 2026-10-21: *"regarding argus-breakout as a rotation tool is slightly wrong… It is a stock screener first looking for opportunities with a stock rotation emphasis… while its primary function is to identify equities to trade"* — and, on being told this was a reframing, that his framing had been consistent throughout |
| **Affects Work Orders** | None. No Work Order's scope changes; PID-ARGUS-0002 and later are unauthored |

## 1. Problem

### (a) The Architect inverted the brief, and the Product Owner did not change it
The opening brief read: *"create a stock scanner… a daily list of
companies from the S&P 500 **unweighted** (for breadth and sector
rotation)"*. The equal weighting was chosen **so that** rotation would be
visible; the list was the product and rotation the lens. The repository is
named `argus-breakout`.

PID §2 then stated the purpose as *"(1) detects sector rotation early…
(2) ranks constituents…"*, and §6 titled the phase **"Rotation
Detector"**. That ordering is an Architect drift, not a change of
requirement. The Product Owner's framing has been consistent since the
first message; this document corrects mine to match it.

### (b) Two concrete consequences, both traceable to the inversion
- **The `EXIT_WARNING` exclusion filter** (removed by AMD-0023). If
  rotation is the product, "drop stocks whose sector is rotating out"
  looks sensible. If the list is the product and rotation is a lens, it is
  obviously wrong — which is how the Product Owner saw it immediately.
  AMD-0023 fixed the rule; this fixes the belief that produced it.
- **§5's stock-level features are assigned to no phase at all.** PID-0002
  delivers composites, breadth, RRG, internals, ratios, rotation score,
  regime and the report. PID-0004 delivers playbooks and ranked lists.
  Nothing delivers the ~60 features in DESIGN §5 that the playbooks score.
  That is exactly the omission the inversion predicts: plan the rotation
  layer, forget the layer underneath it. Under the brief, a first report
  containing a regime and a sector table and **no stocks** is not the
  product.

## 2. Change

### A. PID §2 — Purpose, reordered
> Argus-Breakout is a nightly, locally-run **equity screener** over the
> S&P 500. Its primary function is to **identify individual equities worth
> trading** — long and short — and present them as a ranked list for the
> Product Owner to review. It does that through a **sector-rotation
> lens**: an equal-weight universe, breadth, relative strength and volume
> behaviour reveal where money is flowing, which **preferences** candidates
> and frames the list, but never determines membership of it (AMD-0023
> §2A). So it (1) computes stock-level trend, momentum, relative-strength,
> volatility, flow, structure and level features against an equal-weight
> index and each stock's own sector; (2) ranks them into playbook lists with
> levels and stops; (3) detects sector rotation early from breadth and
> relative-strength momentum rather than price alone, and attaches that
> context to every candidate; (4) produces a short written brief from a
> local language model; and (5) records every signal and brief so they can
> be graded against what happened next.
>
> The problem it solves has two halves: finding tradeable setups nightly
> without reading 500 charts, and not learning about a rotation only after
> the leading sector has fallen 10–15% and the new leaders have run.

### B. PID §3 — Target Outcome, reordered
The report's **layout** is unchanged — rotation still leads as headline
context (AMD-0023 §7.1), because that is where the Product Owner wants it.
What changes is which part is the deliverable: *"ranked long and
short/trim/avoid candidate lists with levels, sizing and earnings flags,
each tagged with its group's rotation state"* is the product; the regime
and sector table are the frame around it.

### C. PID §6 — PID-ARGUS-0002 renamed, and §5 given a home
> | PID-ARGUS-0002 | **Screening Engine and Rotation Layer** | **the DESIGN §5 stock-feature layer and its cross-sectional percentiles**, equal-weight composites, breadth, RRG mechanics, sector internals, ratio z-scores, rotation score, regime label, **uncalibrated playbook candidate lists**, Markdown/HTML report per §7.1 |

PID-ARGUS-0004 keeps **calibration** and what depends on it: the lead-time
study, factor IC, threshold tuning, final playbook weights, paper-account
sizing, the IBKR watchlist push and the paper trade log. Phase 0002 thus
produces a usable — if uncalibrated — list one phase earlier than the old
plan, which is what the brief asked for.

### D. PID §7 — news is deferred, not excluded
*"News, transcripts or sentiment ingestion"* becomes:
> - News, transcripts and sentiment ingestion **in phases 0001–0004**.
>   Deferred, not excluded: the Product Owner has placed an AI review of
>   the nightly list, informed by news, as the final piece of the product
>   (`docs/ROADMAP.md` §D). Any such phase must carry a **point-in-time
>   timestamp rule** — a story may enter date D's evidence only if its
>   publication timestamp is at or before D's close — because news without
>   accurate timestamps is the most efficient way to put look-ahead bias
>   into a backtest and have it look like skill.

### E. The execution boundary is stated, and this PID's prohibition stands
§7's first non-goal is **unchanged and absolute**: Argus-Breakout submits
no order, to any account, ever. The Product Owner's
**`argus-execution-agent`** is a **separate project** with its own
repository, PID and safety design (`docs/ROADMAP.md` §E). The boundary:
Argus-Breakout emits a reviewed, ranked list with levels and stops; sizing
and order placement live wholly outside it. Recording the successor does
not widen this project's scope by one line, and no Work Order here may
anticipate it.

### F. `docs/ROADMAP.md` is created, and carries no authority
A single place for "where we should go, not now". It is **not a governance
instrument**: nothing in it approves, schedules or authorises work, and no
Implementer or Delivery Controller may act on it. Only a PID, an Amendment
or an approved Work Order does that (DELIVERY-CHAIN §1). The file says so
in its own first lines, so it cannot be mistaken for scope.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0024)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
