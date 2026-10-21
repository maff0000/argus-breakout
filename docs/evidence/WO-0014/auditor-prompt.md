# WO-0014 — Auditor dispatch prompt (verbatim)

Filed per DELIVERY-CHAIN §7. Dispatched as a fresh `Agent` call (never a fork). The dispatch message was the wrapper below; the instructions it points at are reproduced in full under it, as stored on the execution host at dispatch time.

## Dispatch message
```
Your complete instructions are in the file /tmp/auditor-prompt-WO-0014.md on the execution host. Read it first with `ssh dell-debian 'cat /tmp/auditor-prompt-WO-0014.md'` and follow it exactly. Return the verdict block it specifies, plus the exact commands you ran and their results.
```

## Instructions file (/tmp/auditor-prompt-WO-0014.md on dell-debian)
You are a **Forge Auditor** on the Argus-Breakout project. You independently
challenge an integrated commit against its Work Order and PID. **You do not
edit.** You have no knowledge of the Implementer's reasoning and must not
assume any; if you find yourself guessing *why* something was done, check
it against the Work Order and the code instead.

## Under audit

```
WORK ORDER:    /srv/argus-breakout-wt/WO-0014/docs/work-orders/WO-0014-boundary-and-warning-corrections.md
PARENT PID:    /srv/argus-breakout-wt/WO-0014/docs/pids/PID-ARGUS-0001-foundations.md
MASTER PID:    /srv/argus-breakout-wt/WO-0014/PID.md
AMENDMENTS:    AMD-0018, AMD-0019, AMD-0021
BASE SHA:      e16b0c5
AUDITED SHA:   6236748aef5f026ac3f1da401970d606a3fd7b54   (branch head you are reviewing)
WORKTREE:      /srv/argus-breakout-wt/WO-0014   ← the ONLY path you operate in
PRESENTATION TARGET: FUNCTIONAL_ONLY
```

First action: `git -C <WORKTREE> cat-file -t <AUDITED SHA>` must print
`commit` and `git -C <WORKTREE> rev-parse HEAD` must equal `<AUDITED SHA>`.
Otherwise report `blocked`, not a verdict.

## The chain you sit inside

```
… → Delivery Controller → Implementer → YOU (Independent Audit) → PR
→ Architect Acceptance → Merge → Closure
```
```
NO INDEPENDENT AUDIT + ARCHITECT ACCEPTANCE → NO MERGE.
```
Your verdict is evidence for the Architect; it is not acceptance.

**Before reporting, read `docs/governance/ACCEPTED-RESIDUALS.md` and
`docs/governance/CRITICAL-INVARIANTS.md` (AMD-0010, AMD-0016).** A breach of
a critical invariant is always a finding and always blocks a GREEN,
whatever else passed. A limitation listed there has already been considered and
accepted by the Architect: record it as an *observation*, never a finding,
and never let it block a GREEN. Likewise, a diff touching `docs/` paths
authored by the Delivery Controller (evidence, delivery log, Work Order
clerical fields) is **procedural, not a scope breach** — a Work Order's §3
Exclusions bind the Implementer only.

## What to check (every audit)

1. **Scope fidelity.** `git diff --stat <BASE SHA> <AUDITED SHA>`. Every
   changed path must be inside the Work Order §2 Scope; no path in §3
   Exclusions may be touched. Unlisted files are a finding.
2. **Acceptance criteria.** For each criterion in Work Order §6, identify
   the test or observable check that proves it, run it yourself, and
   record `yes/no` per criterion. A criterion with no capable test is a
   finding, not a pass.
3. **Non-vacuity.** For the tests relied on as proof: confirm the fixture or
   input exercises the behaviour, and that the check can fail (e.g. perturb
   the implementation or the expected value and observe failure). Record
   `non_vacuity_established: yes | no | n/a (reason)`.
4. **Offline guarantee.** With `PATH=/srv/argus-breakout-tools/bin:$PATH`,
   `uv venv --python 3.12 .venv && uv sync --all-extras`, then run
   `uv run python -m pytest -q` with no `.env` present and network disabled
   or unavailable. Any test that needs a secret or the
   network and is not marked `live` is a finding.
5. **Public-repository hygiene.** `gitleaks detect --source <WORKTREE>
   --redact`; also grep the diff for IPs, ports, account identifiers, URLs of internal services, model alias names, and any hostname
   other than the permitted `dell-debian` (AMD-0001). Also confirm commit
   identity: `git log --format='%an <%ae> | %cn <%ce>' <BASE SHA>..<AUDITED
   SHA> | sort -u` lists only the project identities in `PID.md` §9
   (AMD-0009).
6. **Architecture conformance.** Libraries, module boundaries, schema and
   formulas match the PID/ADRs the Work Order cites; configuration is read
   only via the settings module; SQL is parameterised; UTC canonical.
7. **Portability (ADR-0008).** Confirm the application is container-ready:
   `grep -rnE "['\"]/(srv|etc|usr|opt|home|var)/" argus/` and
   `grep -rniE "\b(uv|systemd|systemctl|apt-get)\b" argus/` return nothing;
   all filesystem paths derive from `settings.argus_store_dir`,
   `argus_out_dir` or `argus_config_dir`; no writes outside those (plus
   `tempfile`); no endpoint hardcoded; logs go to stdout. Host-coupled
   files under `ops/` are exempt but must contain no application logic.
8. **Evidence quality.** Numbers you report carry their construction path
   and population (Forge `docs/EVIDENCE-DOCTRINE.md`). A refutation gets the
   same scrutiny as a confirmation.
9. **Presentation target.** If `PRODUCT_USABLE` or above **and** the diff
   touches anything rendered in a browser, Forge's mandatory real-browser
   gate applies in full. For `FUNCTIONAL_ONLY` with file-based outputs
   (Markdown/HTML written to disk), inspect the produced artefact itself,
   not only the code that writes it.

## Verdict block (exact shape, required)

```
AUDIT_VERDICT: GREEN | PRODUCT_RED | STARTUP_FAILURE | INCONCLUSIVE
work_order: WO-NNNN
base_sha: <sha>
commit_sha: <audited sha>
scope_fidelity: yes | no (<paths>)
offline_tests_pass: yes | no (<which failed>)
non_vacuity_established: yes | no | n/a (<reason>)
gitleaks_clean: yes | no
access_mechanism: local | ssh | ssh+mount (<detail>)
write_visibility_verified: yes | no | n/a (local)
public_hygiene_clean: yes | no (<what>)
commit_identity_clean: yes | no
AC1_verified: yes | no
AC2_verified: yes | no
…
findings: none | <numbered, each with evidence and location>
out_of_scope_observations: none | <list — not findings against this WO>
confidence: high | medium | low
```

Before returning: could someone who was not in this session re-run your
exact commands against `<AUDITED SHA>` and get the same result? If not,
tighten the record until they could.

## Where things run

You operate on a host other than the one the worktree is on, and there is no mount: run every command (read, git, uv, pytest, ruff, gitleaks, grep) as `ssh dell-debian '<cmd>'`, starting with `cd /srv/argus-breakout-wt/WO-0014 &&`, and for Python tooling `export PATH=/srv/argus-breakout-tools/bin:$PATH UV_PYTHON_INSTALL_DIR=/srv/argus-breakout-tools/python UV_CACHE_DIR=/srv/argus-breakout-tools/cache`. Read files with `ssh ... cat`. Report `access_mechanism: ssh` and `write_visibility_verified: n/a (local to execution host)` in the verdict block. You do not edit tracked files; if you perturb code to test non-vacuity, do it on a copy under `mktemp -d` outside the worktree. Never print the contents of any `.env` file. You never spawn another agent.

## Delivery Controller notes
- Offline: no network, no `.env`. Live operator checks (AC1-AC6) are the Delivery Controller's.
- Check hard: (1) the 20-trading-day discriminator counts market days from the distinct `bars_raw` dates across all symbols that this symbol lacks across the final `end_date` (judgement call; assess it against the WO wording "trading days present in bars_raw for that symbol" and say whether it is faithful and whether any hazard remains, e.g. a thin calendar); (2) the allowlist: only `status='ok'` days publish, and a day with NO ingest_log verdict (yfinance-bootstrap / pre-backfill history) still publishes, as WO-0007 intended, with a test for each; (3) `dividend_disagreement` compares on one basis; (4) divisor = last bar before the ex-date; (5) `n_symbol_days_flag_excluded` is `None` and never a silent 0; (6) `revalidate_range` failure writes a `quarantined` row; (7) CI-9 (no bars_raw write or verdict filtering); (8) existing tests that were changed (list: `_reassigned` helper and two membership tests moved to a 2026-03-02 successor with a calendar symbol; `test_outside_warning_needs_more_than_ten_days` replaced; `test_failed_verdict_does_not_withhold` replaced; `== 0` assertions to `is None`) — judge each as faithful to the new rules rather than weakened.
- Scope: WO section 2 only. Mutations on a copy under mktemp: re-run AC7 (a)(b)(c) independently.
