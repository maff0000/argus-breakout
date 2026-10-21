# WO-0009 — Nightly orchestration, systemd units, runbook, operator acceptance

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §3, §8.7 (`nightly`), §13 ; `DESIGN.md` §10 |
| **Applicable Amendments** | AMD-0002, AMD-0003, AMD-0004, AMD-0019, AMD-0020 (delta — §2, §4, §6) |
| **Base SHA** | main at Closure of WO-0003, WO-0006, WO-0007, WO-0008 |
| **Branch** | `wo/0009-nightly-orchestration` |
| **Depends on** | WO-0003, WO-0006, WO-0007, WO-0008 |
| **Parallel group** | P0-F |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0009/` |

## 1. Objective
One command, `argus nightly --date D`, that runs the Phase 0 pipeline in
order with per-step status, is safe to re-run, and is installed as a
systemd timer on the delivery host under a dedicated service user; plus
the runbook and the phase-level operator acceptance evidence.

## 2. Scope (exhaustive)
```
argus/data/reconcile.py              modify  AMD-0020 §3.1 — per-field treatment: close breaches as now; VOLUME rows are recorded with
                                             breach=False (our consolidated volume and IBKR TRADES volume are not the same quantity,
                                             measured median 2.03× at WO-0008). ReconcileReport carries per-field pass/fail plus the
                                             volume median ratio and its drift against the trailing 20-session median (>25% alerts).
                                             Close gate: max |pct_diff| <= 0.5% AND at most one comparison > 0.1%, each exceedance named.
                                             WO-0009 is the ONLY Work Order that may touch this file; WO-0013 does not, so the two stay
                                             concurrent
argus/pipeline.py                    create  STEPS: ordered list of (name, callable, required: bool):
                                               universe_refresh (weekly: only if weekday==0 or symbols empty; required=False)
                                               ingest_polygon_day from argus.data.ingest_polygon (required=True)
                                               ingest_polygon_actions since D-7 (required=True)
                                               events_refresh days=45 (required=False)
                                               materialise (required=True)
                                               ibkr_reconcile (required=False; skipped with --skip-ibkr or when ib_port unset)
                                               ibkr_iv (required=False; same)
                                             run_nightly(settings, date, skip_ibkr: bool) -> NightlyReport(run_id, date, steps: list[StepResult(name, status, seconds, detail)], ok)
                                               (a failed required step stops the run and marks ok=False; optional step failures are recorded and the run continues;
                                                every StepResult is written to ingest_log(source=f'nightly:{name}'); the report is written as JSON to
                                                ARGUS_OUT_DIR/nightly/<date>.json)
argus/commands/nightly_cmds.py       create  `nightly --date D [--skip-ibkr]`; exit 0 iff report.ok (registers onto the root app)
argus/cli.py                         modify  add exactly one import line for argus.commands.nightly_cmds in the append-only block (AMD-0002)
ops/systemd/argus-nightly.service    create  Type=oneshot; User=argus; Group=argus; WorkingDirectory=/srv/argus-breakout;
                                             EnvironmentFile=/srv/argus-breakout/.env; ExecStart=/srv/argus-breakout/ops/nightly.sh;
                                             hardening: NoNewPrivileges=yes, ProtectSystem=strict (which leaves /srv/argus-breakout-tools readable), ProtectHome=yes, PrivateTmp=yes,
                                             ReadWritePaths=/srv/argus-breakout/store /srv/argus-breakout/out
ops/systemd/argus-nightly.timer      create  OnCalendar=Mon..Fri 23:30 Europe/London; Persistent=true; Unit=argus-nightly.service
ops/nightly.sh                       create  POSIX sh; computes the target trading date = last weekday ≤ now in America/New_York
                                             (honours ARGUS_NOW=YYYY-MM-DDTHH:MM for tests); exec /srv/argus-breakout/.venv/bin/argus nightly --date <that date>
docs/runbook/OPERATIONS.md           create  install steps (toolchain per ADR-0007: project-local uv + managed CPython 3.12 under
                                             /srv/argus-breakout-tools, mode 0755; service user; `uv venv --python 3.12 .venv && uv sync --all-extras`;
                                             .env permissions 0600; bootstrap; systemd enable), daily checks,
                                             how to re-run a day, how to read ingest_log/reconcile_log, backup of store/ (rsync to second disk), recovery
tests/test_pipeline.py               create  see §5 (steps monkeypatched with fakes)
tests/test_nightly_sh.py             create  see §5 (runs ops/nightly.sh with ARGUS_NOW set and a stub `argus` on PATH that echoes its arguments)
```

## 3. Exclusions
No new providers or data logic; no features/composites; no alerting
channel; no changes to systemd beyond the two units and wrapper; no
`docs/` outside `docs/runbook/`.

## 4. Design constraints
DESIGN §10 schedule and security, plus ADR-0008: the systemd unit and
`ops/nightly.sh` carry **no application logic** beyond computing the target
date, and must be replaceable by a container scheduler without any change
under `argus/` (AMD-0004). `argus nightly` must run correctly when invoked
directly, with no systemd present. The service user owns `store/` and
`out/`; the repo checkout is read-only to it except those two paths. No
secrets in unit files (EnvironmentFile only). `run_nightly` is
idempotent for a date: re-running after a partial failure skips steps
whose `ingest_log` row for that date is `ok`.

**The pipeline reads verdicts, never exit codes or aggregate rates**
(AMD-0020 §3.2): the `ibkr_reconcile` step reads the **per-field**
reconciliation verdict, not `breach_rate`; the ingest steps read the
per-day `ingest_log` verdicts, because a quarantined day exits 0 by
design (ratified WO-0004 spec-gap 5).

**IBKR pacing is a stated constraint** (AMD-0020 §2D): the nightly budget
is 46 history requests against the pacer's 50 per 10 minutes — four of
headroom — so the step reports the pacer's sleep time, and growing the
sample or the ETF list is an architectural decision, not a parameter
change. Logging emits one JSON line
per step start/finish with `run_id`.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_pipeline.py::test_required_failure_stops_run` | fake ingest raising → later steps not called; ok=False; exit 1 | call recording |
| `test_pipeline.py::test_optional_failure_continues` | fake ibkr raising → materialise still runs; ok=True; step recorded failed | — |
| `test_pipeline.py::test_rerun_skips_ok_steps` | second run for same date calls only non-ok steps | call counts |
| `test_pipeline.py::test_skip_ibkr_flag` | `--skip-ibkr` → ibkr steps status 'skipped' | status values |
| `test_pipeline.py::test_report_written` | JSON report exists with all step names | file + keys |
| `test_nightly_sh.py::test_date_computation` | Saturday 03:00 London → previous Friday; Monday 23:30 London → Monday (NY date) | string compare |

## 6. Acceptance criteria (Work Order + phase closure)
- **AC1** — `argus nightly --date <last trading day>` exits 0 on the host with all required steps ok (operator check: report JSON filed).
- **AC2** — systemd timer installed, enabled and shown by `systemctl list-timers` (operator check; output filed with hostnames redacted).
- **AC3** — **Three consecutive unattended nightly runs** complete with ok=True (operator check: three report JSONs filed) — phase criterion.
- **AC4** — Every current member and ETF has ≥ 10 years of bars where source history exists; exceptions listed with reasons (operator check) — phase criterion.
- **AC5** — `members_on` for 2016-06-30, 2020-03-31, 2024-12-31 matches hanshof within ±3 (operator check from WO-0003 evidence re-run) — phase criterion.
- **AC6** — (replaced, AMD-0020 §3.4) Across the three nights, **every night's close comparison passes the per-field gate** — `max |pct_diff| ≤ 0.5%` and at most one comparison over 0.1%, each exceedance named — **and** the volume median ratio is reported per night with its drift against the trailing median (operator check) — phase criterion. An aggregate `breach_rate` is **not** a criterion: at n=100 it permits zero breaches and cannot express "one symbol needs a look".
- **AC7** — Zero members without an industry group (operator check) — phase criterion.
- **AC8** — Runbook present and followed verbatim for the install (Auditor reads it; DC confirms each step executed).
- **AC9** — (AMD-0020 §2B, §2C) `docs/evidence/WO-0009/ibkr-volume-basis.md` records the same 20 symbols re-requested with **`useRTH=False`** and the resulting ratio, settling whether the ≈2× gap is regular-hours scoping or off-exchange print exclusion; the conclusion is written into DESIGN §3.1. `docs/evidence/WO-0009/skyd-contract.md` confirms IBKR's `conId`, `primaryExchange` and long name against our **SKYD** and accounts for the 2.09% close difference on 2026-10-13. SKYD is one of the five renamed tickers, so a symbol-string contract mismatch there is a finding against the ticker mapping and a CI-2 question, not a tolerance question.
- **AC10** — The nightly run completes on the host with `IB_PORT` set to a paper port; with a non-paper port the `ibkr_reconcile` step reports a configuration error and the pipeline **continues** (the step is `required=False`) rather than failing the night (operator check: both runs' report JSONs filed, port values not recorded).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC8 outputs), `phase-closure.md` summarising
PID-ARGUS-0001 §13 with pointers to the evidence.

## 8. Implementer notes
Keep `pipeline.py` declarative: the STEPS list is the single place the
order lives. The wrapper script exists so the unit file stays static.
Hardening directives must not break DuckDB's need to write under
`store/`; test the unit on the host before declaring AC2.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
