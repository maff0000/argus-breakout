# Argus-Breakout — Project Initiation Document (Master)

**PID id:** PID-ARGUS-0000 · **Status:** Approved · **Version:** 1.0 (2026-10-19)
**Architect:** Claude (Project Architect) · **Product Owner:** Matt
**Governance:** `docs/governance/DELIVERY-CHAIN.md` (binding) on top of Forge
(`https://github.com/maff0000/forge`).

This master PID follows Forge's `docs/PID-TEMPLATE.md`. It defines the whole
project and delegates each delivery phase to a **Phase PID** in
`docs/pids/`. Work Orders are authored against Phase PIDs, never against
this document directly, except Work Orders that change governance or
repository plumbing (which cite this PID).

## 1. Identity

```text
PROJECT_ROOT:

/srv/argus-breakout

GitHub repository:

maff0000/argus-breakout

Remote:

https://github.com/maff0000/argus-breakout.git
```

Verified against `git remote -v` on the clone this PID was authored in
(2026-10-19, repository empty before this commit). Delivery host: `dell-debian` (hostname only — Product Owner decision
2026-10-19, AMD-0001). `PROJECT_ROOT=/srv/argus-breakout` on that host. No
IP address, port, user credential or network detail of the host is
recorded anywhere in this repository.

## 2. Purpose

Argus-Breakout is a nightly, locally-run **equity screener** over the
S&P 500. Its primary function is to **identify individual equities worth
trading** — long and short — and present them as a ranked list for the
Product Owner to review. It does that through a **sector-rotation lens**:
an equal-weight universe, breadth, relative strength and volume behaviour
reveal where money is flowing, which **preferences** candidates and frames
the list, but never determines membership of it (AMD-0023 §2A, AMD-0024).

So it (1) computes stock-level trend, momentum, relative-strength,
volatility, flow, structure and level features against an equal-weight
index baseline and each stock's own sector; (2) ranks them into playbook
lists with levels and stops; (3) detects sector rotation early from
breadth and relative-strength momentum rather than price alone, and
attaches that context to every candidate; (4) produces a short written
brief from a local language model; and (5) records every signal and brief
so they can be graded against what happened next.

The problem it solves has two halves: finding tradeable setups nightly
without reading 500 charts, and not learning about a rotation only after
the leading sector has fallen 10–15% and the new leaders have already run.

The equal weighting is chosen **so that** rotation is visible — the lens
serves the list, not the reverse (AMD-0024 §1).

## 3. Target Outcome

Each trading day, before the UK morning, a report exists on the delivery
host whose **deliverable** is **ranked long and short/trim/avoid candidate
lists** — with levels, stops, support and resistance, sizing for the paper
account, earnings flags, and each name tagged with its group's rotation
state (AMD-0024 §2B). Framing that list, and leading the report as
headline context per `DESIGN.md` §7.1: the market regime, an 11-sector
rotation table with `EXIT_WARNING` / `ENTRY_WATCH` flags, and explicit
**Rotating IN / Rotating OUT** groups each followed by their member
tickers. Plus a ≤600-word brief whose every claim cites a metric in that
night's evidence pack. Signals and briefs are graded automatically at 5,
10 and 20 sessions. The Product Owner can see, in hindsight, the date each
rotation signal fired relative to the sector's price peak.

## 4. Users

The Product Owner, trading an IBKR **paper** account (£100k starting
equity) for the life of this project. Secondary readers: the Architect,
the Delivery Controller and auditors, via the evidence trail.

## 5. Presentation Target

`FUNCTIONAL_ONLY` for PID-ARGUS-0001 through 0004. Outputs are files
(Markdown, HTML written to disk, JSON) and a CLI. No served web surface
exists in these phases, so Forge's browser-verification gate does not
apply; Auditors inspect the produced files directly. Any phase that adds a
served UI must declare `PRODUCT_USABLE` or higher in its own Phase PID.

## 6. Scope (whole project)

Delivered in phases, each a Phase PID with its own Work Orders:

| Phase PID | Title | Delivers |
|---|---|---|
| PID-ARGUS-0001 | Foundations | repo/tooling, DuckDB+Parquet store, universe & point-in-time membership, Polygon nightly ingest + 2y backfill, 10y bootstrap, FMP events/profiles, IBKR reconciliation & IV, nightly orchestration |
| PID-ARGUS-0002 | **Screening Engine and Rotation Layer** | **the DESIGN §5 stock-feature layer with its cross-sectional percentiles**, equal-weight composites, breadth, RRG mechanics, sector internals, ratio z-scores, rotation score, regime label, **uncalibrated playbook candidate lists**, Markdown/HTML report per DESIGN §7.1 (AMD-0024 §2C — §5 previously belonged to no phase) |
| PID-ARGUS-0003 | Brief & Query Surface | evidence pack, gateway client, nightly brief, grading tables, read-only MCP server over the store |
| PID-ARGUS-0004 | Calibration & Lists | **the factor-IC and lead-time studies are a GATE (AMD-0028 §2A): until a feature set is shown to carry information out of sample, net of costs, no threshold tuning, no playbook weighting, no sizing and no exit work is authorised. A negative result closes the phase honestly.** Then: threshold tuning, **final** playbook weights, paper-account sizing, IBKR watchlist push, paper trade log. Phase 0002 already produces a usable **uncalibrated** list, one phase earlier than the original plan (AMD-0024 §2C) |
| PID-ARGUS-0005 | ML Ranking (optional) | gradient-boosted ranker with purged CV; deployed only if it beats the rules baseline out of sample |
| PID-ARGUS-0006 | Containerisation | multi-stage Dockerfile (`uv sync --frozen --no-dev`), compose with `store/`+`out/` volumes and env-file, container scheduler, production deployment notes |

PID-ARGUS-0001 is Approved; **PID-ARGUS-0002 is authored as Draft**
(AMD-0033 §2A). A Phase PID is authored by the Architect **when the
evidence that should inform it is in hand**, which is normally at the
preceding phase's closure but need not be. A Work Order from a later phase
may be dispatched **concurrently** with the preceding phase's remaining
Work Orders provided all four hold, recorded in the Work Order: (1) it
shares **no source file** with any open Work Order; (2) it depends on no
table, column or interface an open Work Order is still changing; (3) the
evidence that would have informed it is cited, by figure; (4) the Product
Owner has approved the overlap. A PID authored before closure is marked
**Draft** and finalised at closure with the closure evidence appended.
**Phase closure criteria are unaffected** — overlap buys parallelism, never
a shortcut through a gate, and PID-ARGUS-0004's IC gate (AMD-0028 §2A)
binds regardless of when the work was dispatched. PID-ARGUS-0006 is planned, not yet authored: the application
is built **container-ready** from WO-0001 under ADR-0008 and packaged in
that phase (AMD-0004).

## 7. Non-Goals

- Live-account trading or order submission of any kind. The system writes
  nothing to IBKR except, in PID-ARGUS-0004, a named watchlist on the paper
  account via the local gateway path. **This is unchanged and absolute**
  (AMD-0024 §2E): Argus-Breakout submits no order, to any account, ever.
  The Product Owner's **`argus-execution-agent`** — which risk-sizes a
  reviewed candidate and places the trade in the IBKR paper account — is a
  **separate project** with its own repository, PID and safety design
  (`docs/ROADMAP.md` §E). The boundary: Argus-Breakout emits a reviewed,
  ranked list with levels and stops; sizing and order placement live wholly
  outside it, and **no Work Order here may anticipate it**.
- News, transcripts or sentiment ingestion **in phases 0001–0004**.
  Deferred, not excluded (AMD-0024 §2D): the Product Owner has placed an
  AI review of the nightly list, informed by news, as the final piece of
  the product (`docs/ROADMAP.md` §D). Any such phase must carry a
  **point-in-time timestamp rule** — a story may enter date D's evidence
  only if its publication timestamp is at or before D's close — because
  news without accurate timestamps is the most efficient way to put
  look-ahead bias into a backtest and have it look like skill.
- Intraday data or real-time streaming.
- A served web dashboard (would be a new Phase PID with a new presentation
  target).
- Containerisation **in this phase**. Docker packaging is deferred to
  PID-ARGUS-0006, not excluded; ADR-0008's portability constraints are
  binding on every Work Order in the meantime (AMD-0004).
- Any Forge framework changes; Argus does not import or embed Forge.

## 8. Architecture

Authoritative detail: `docs/architecture/DESIGN.md` and the ADRs in
`docs/architecture/adr/`. Summary of the fixed decisions an Implementer
works within:

- **Language/runtime:** Python 3.12, provided by a project-local `uv`-managed
  CPython under `/srv/argus-breakout-tools/` with no system installs
  (ADR-0007); `polars` for feature computation,
  `duckdb` + Parquet for storage, `httpx` for HTTP, `pydantic-settings` for
  configuration, `typer` for the CLI, `pytest` + `ruff` for quality.
  (ADR-0002)
- **Package:** `argus/` with sub-packages `data/`, `features/`, `market/`,
  `events/`, `rank/`, `brief/`, `report/`, `backtest/`, `ml/`, `mcp/`; CLI
  entry point `argus`. Layout fixed in DESIGN.md §2.
- **Data sources:** Polygon grouped-daily (nightly), one-off bootstrap for
  10+ years, IBKR paper gateway for reconciliation and implied volatility,
  FMP Basic for constituents/profiles/earnings. (ADR-0003)
- **Model access:** an OpenAI-compatible local gateway reached only via
  `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL_*` environment variables; ≈30K
  token window assumed; the scanner never names models or hosts in source.
  (ADR-0004)
- **Rotation detection** at GICS industry-group level, reported at sector
  level. (ADR-0005)
- **IBKR write path:** local gateway only; no third-party connector writes.
  (ADR-0006)
- **Portability (AMD-0004):** built container-ready — no absolute paths in
  `argus/`, writes only under `ARGUS_STORE_DIR`/`ARGUS_OUT_DIR`, every
  network endpoint configurable, the CLI is the only entrypoint, logs to
  stdout, no root at runtime. Docker packaging is PID-ARGUS-0006. (ADR-0008)
- **Configuration:** environment variables only, read through
  `argus/settings.py`; required variables fail loudly at startup.
- **Time:** UTC canonical in storage and logs; trading dates are exchange
  dates (America/New_York) stored as ISO dates.

What may not change without an Amendment: the storage engine, the package
layout, the data-source roles, the schema in DESIGN.md §3.2, any formula in
DESIGN.md §5–6, ADR-0008's portability constraints, the security rules in
§9 below.

## 9. Public Repository Security

This repository is public until project completion so the Architect can
inspect progress. Therefore, binding on every role:

- Never commit `.env`, API keys, tokens, IBKR account identifiers or
  usernames, IP addresses, ports, model-gateway URLs or model alias names,
  or any description of the Product Owner's network. The single exception
  is the bare hostname of the delivery host, `dell-debian`, accepted as
  disclosable by the Product Owner (AMD-0001); no other hostname may
  appear.
- `.env.example` documents every variable with a placeholder value.
- The committed pre-commit hook (`scripts/hooks/pre-commit`, activated by
  `./ops/bootstrap` via `core.hooksPath`) runs `gitleaks` and blocks the
  commit if the scanner is absent. `--no-verify` is forbidden.
- CI runs `gitleaks detect` on every push and PR.
- Test fixtures are synthetic or scrubbed; no fixture contains a real key,
  account id or host.
- **Commit metadata is published content (AMD-0009).** Every commit carries
  a project identity, never a personal one: the Architect as
  `Claude (Architect) <noreply@anthropic.com>`, the Delivery Controller as
  `Rogue (Delivery Controller) <noreply@anthropic.com>`. Set this
  repo-locally for **`author.*` and `committer.*`, not only `user.*`** — a
  host's global configuration may define `author`/`committer` sections that
  silently override `user.*`. Verify before every push:
  `git log --format='%an <%ae> | %cn <%ce>' <range> | sort -u` must list
  only those two identities. A personal name or address reaching a public
  commit cannot be undone by a later commit.
- Logs are structured JSON with secrets redacted; no request URL containing
  an API key is logged.

## 10. Persistence and Durable Truth

- Application state: `store/parquet/` (append-only by partition) and
  `store/argus.duckdb` on the delivery host, owned by a dedicated service
  user, mode 0640, backed up nightly to a second disk. Not in git.
- Outputs: `out/evidence/`, `out/briefs/`, `out/reports/` on the host. Not
  in git.
- Project authority: this repository and its GitHub PRs. PIDs, Amendments,
  Work Orders, ADRs and the delivery evidence trail live in `docs/`. No
  Redis, message bus or scheduler state is durable; systemd timers are the
  only scheduler.

## 11. Git and GitHub

Per `docs/governance/DELIVERY-CHAIN.md` §7, restated: `main` is protected;
one branch per Work Order (`wo/NNNN-<slug>`) cut from the Work Order's Base
SHA; the Delivery Controller alone commits (Implementers never do); every
PR carries its audit evidence; merge is a merge commit by the Delivery
Controller only after Architect Acceptance (PR comment in fixed form +
`docs/evidence/WO-NNNN/acceptance.md`). No force-push, no squash, no amending commits cited by SHA. No rebase,
merge or cherry-pick may be scripted to continue through a conflict: a
conflict stops the operation for inspection, to be resolved by hand or
aborted. After any history operation on a Work Order branch, re-verify the
Base SHA in-scope diff and the commit identities before proceeding
(AMD-0009).

## 12. Quality and Testing

- `uv run python -m pytest -q` (AMD-0003; see ADR-0007 for the toolchain)
  must pass **offline with no `.env` and no network** on every Work Order
  branch. Live checks are `@pytest.mark.live`, skipped
  by default, run by the Delivery Controller as operator checks with the
  host's `.env` and recorded in evidence.
- `uv run ruff check .` clean; `gitleaks detect` clean.
- Every Work Order names its tests and what each proves; tests relied on as
  proof must be shown capable of failing (Forge Engineer rule 14).
- Acceptance criteria are observable and numbered; file-based outputs are
  inspected as artefacts, not inferred from code.

## 13. Acceptance Definition

**The nightly soak is operations, not a gate** (AMD-0032 §2D). The first
week of real nightly runs is reviewed **retrospectively** by the Architect,
at the same boundary as mandate-merged Work Orders; a defect found there
becomes a **new Work Order** under DELIVERY-CHAIN §9 and does not reopen
the phase. Closure is gated on WO-0009 AC3a–AC3d and AC14, not on elapsed
calendar time.

This master PID closes when PID-ARGUS-0001 through 0004 are Closed and the
Product Owner confirms, in a PR comment on the final Work Order, that the
Target Outcome in §3 is met on the delivery host for ten consecutive
trading days. PID-ARGUS-0005 is optional and does not gate closure. Containerisation
(PID-ARGUS-0006) does not gate closure either, but ADR-0008's portability
constraints are part of every phase's acceptance (AMD-0004).

## 14. Development Inputs

- `docs/architecture/DESIGN.md` (v1.0) and ADR-0001 … ADR-0006
- `docs/governance/DELIVERY-CHAIN.md` and the prompts in
  `docs/governance/prompts/`
- Forge: `.claude/skills/forge/SKILL.md`, `.claude/agents/forge-engineer.md`,
  `.claude/agents/forge-auditor.md`, `docs/EVIDENCE-DOCTRINE.md`
- Phase PIDs in `docs/pids/` as they are approved
