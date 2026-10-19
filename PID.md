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
(2026-10-19, repository empty before this commit). The delivery host is
referred to only as "the delivery host"; its name is not recorded here
(public repository).

## 2. Purpose

Argus-Breakout is a nightly, locally-run equity scanner over the S&P 500.
It (1) detects sector rotation early from breadth, relative-strength and
volume behaviour rather than price alone; (2) ranks constituents against
an equal-weight index baseline and their own sector; (3) produces a short
written brief from a local language model with long/research and
short/avoid candidates; and (4) records every signal and brief so they can
be graded against what happened next.

The problem it solves: rotation is noticed only after the leading sector
has fallen 10–15% and the new leaders have already run.

## 3. Target Outcome

Each trading day, before the UK morning, a report exists on the delivery
host containing: the market regime; an 11-sector rotation table with
`EXIT_WARNING` / `ENTRY_WATCH` flags; ranked long and short/avoid
candidate lists with levels, sizing for the paper account and earnings
flags; and a ≤600-word brief whose every claim cites a metric in that
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
| PID-ARGUS-0002 | Rotation Detector | equal-weight composites, breadth, RRG mechanics, sector internals, ratio z-scores, rotation score, regime label, Markdown/HTML report |
| PID-ARGUS-0003 | Brief & Query Surface | evidence pack, gateway client, nightly brief, grading tables, read-only MCP server over the store |
| PID-ARGUS-0004 | Calibration & Lists | lead-time study, factor IC, threshold tuning, playbooks, ranked lists, paper-account sizing, IBKR watchlist push, paper trade log |
| PID-ARGUS-0005 | ML Ranking (optional) | gradient-boosted ranker with purged CV; deployed only if it beats the rules baseline out of sample |

Only PID-ARGUS-0001 is Approved at v1.0 of this document. Later Phase PIDs
are authored by the Architect when the preceding phase closes, informed by
its evidence.

## 7. Non-Goals

- Live-account trading or order submission of any kind. The system writes
  nothing to IBKR except, in PID-ARGUS-0004, a named watchlist on the paper
  account via the local gateway path.
- News, transcripts or sentiment ingestion.
- Intraday data or real-time streaming.
- A served web dashboard (would be a new Phase PID with a new presentation
  target).
- Any Forge framework changes; Argus does not import or embed Forge.

## 8. Architecture

Authoritative detail: `docs/architecture/DESIGN.md` and the ADRs in
`docs/architecture/adr/`. Summary of the fixed decisions an Implementer
works within:

- **Language/runtime:** Python 3.12; `polars` for feature computation,
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
- **Configuration:** environment variables only, read through
  `argus/settings.py`; required variables fail loudly at startup.
- **Time:** UTC canonical in storage and logs; trading dates are exchange
  dates (America/New_York) stored as ISO dates.

What may not change without an Amendment: the storage engine, the package
layout, the data-source roles, the schema in DESIGN.md §3.2, any formula in
DESIGN.md §5–6, the security rules in §9 below.

## 9. Public Repository Security

This repository is public until project completion so the Architect can
inspect progress. Therefore, binding on every role:

- Never commit `.env`, API keys, tokens, IBKR account identifiers or
  usernames, internal hostnames, IP addresses, ports, model-gateway URLs or
  model alias names, or any description of the Product Owner's network.
- `.env.example` documents every variable with a placeholder value.
- The committed pre-commit hook (`scripts/hooks/pre-commit`, activated by
  `./ops/bootstrap` via `core.hooksPath`) runs `gitleaks` and blocks the
  commit if the scanner is absent. `--no-verify` is forbidden.
- CI runs `gitleaks detect` on every push and PR.
- Test fixtures are synthetic or scrubbed; no fixture contains a real key,
  account id or host.
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
`docs/evidence/WO-NNNN/acceptance.md`). No force-push, no squash, no
amending commits cited by SHA.

## 12. Quality and Testing

- `python -m pytest -q` must pass **offline with no `.env` and no network**
  on every Work Order branch. Live checks are `@pytest.mark.live`, skipped
  by default, run by the Delivery Controller as operator checks with the
  host's `.env` and recorded in evidence.
- `ruff check .` clean; `gitleaks detect` clean.
- Every Work Order names its tests and what each proves; tests relied on as
  proof must be shown capable of failing (Forge Engineer rule 14).
- Acceptance criteria are observable and numbered; file-based outputs are
  inspected as artefacts, not inferred from code.

## 13. Acceptance Definition

This master PID closes when PID-ARGUS-0001 through 0004 are Closed and the
Product Owner confirms, in a PR comment on the final Work Order, that the
Target Outcome in §3 is met on the delivery host for ten consecutive
trading days. PID-ARGUS-0005 is optional and does not gate closure.

## 14. Development Inputs

- `docs/architecture/DESIGN.md` (v1.0) and ADR-0001 … ADR-0006
- `docs/governance/DELIVERY-CHAIN.md` and the prompts in
  `docs/governance/prompts/`
- Forge: `.claude/skills/forge/SKILL.md`, `.claude/agents/forge-engineer.md`,
  `.claude/agents/forge-auditor.md`, `docs/EVIDENCE-DOCTRINE.md`
- Phase PIDs in `docs/pids/` as they are approved
