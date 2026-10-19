# Architect Acceptance — WO-0001

```
WORK ORDER:        WO-0001 — Repository skeleton, settings, logging, CLI, tooling, CI
PARENT PID:        PID-ARGUS-0001 (Foundations)
AMENDMENTS:        AMD-0002, AMD-0003, AMD-0004, AMD-0007
BASE SHA:          02ddd97de53c34fb2914cab17ca7cf3e832d659f
AUDITED SHA:       be5a224bf98cb5ffb25e4d462663d72f3c45c6f9
BRANCH HEAD:       96daf128972cbcba452a2c63084fd2df54d33a12
PR:                #1  https://github.com/maff0000/argus-breakout/pull/1
AUDIT VERDICT:     GREEN  (docs/evidence/WO-0001/audit.md)
ACCEPTANCE:        ACCEPTED
AUTHORITY:         explicit Architect acceptance (pre-dates AMD-0010; WO-0001 is
                   not in the Delegated Acceptance Mandate's scope)
DATE (UTC):        2026-10-19
ARCHITECT:         Claude (Architect)
```

Branch head differs from the audited SHA by three commits touching only
`docs/evidence/WO-0001/**`, `docs/evidence/DELIVERY-LOG.md` and this Work
Order's clerical fields — permitted post-audit per DELIVERY-CHAIN §7.

## Checks performed by the Architect
- [x] Every acceptance criterion has a corresponding test or operator check
      with recorded output. AC1–AC7 all verified in `operator-checks.md` and
      `tests.md`.
- [x] Auditor dispatch prompt filed verbatim (`auditor-prompt.md`) and
      contains no diff-specific hint. Read in full; it is the cc2480a
      template with worktree, SHA and Work Order fields completed.
- [x] Audit verdict GREEN. Non-vacuity established by five mutations on a
      `git archive` copy, each failing the intended test — this is the
      strong form, not an assertion.
- [x] Diff within scope. Implementer paths (`pyproject.toml`, `uv.lock`,
      `argus/`, `tests/`, `ci.yml`) are all in §2. DC-authored `docs/` paths
      are procedural per the ruling below.
- [x] No secrets, hostnames, ports, account identifiers or gateway details.
      Only hygiene hits are the `ib_host` default, the permitted
      `dell-debian`, and public `astral-sh` release URLs — now R3 and R4 in
      `docs/governance/ACCEPTED-RESIDUALS.md`.
- [x] Commit identity: `git log --format='%an <%ae> | %cn <%ce>'
      c582c61..96daf12 | sort -u` lists only
      `Rogue (Delivery Controller) <noreply@anthropic.com>` and
      `Claude (Architect) <noreply@anthropic.com>` (AMD-0009).

## Architect spot-checks, run directly against the artefact
Not against the Auditor's narrative or the Implementer's report:
1. **AC7 portability greps** re-run on a `git archive` extract of the branch:
   `grep -rnE "['\"]/(srv|etc|usr|opt|home|var)/" argus/` → no output;
   `grep -rniE "\b(uv|systemd|systemctl|apt-get)\b" argus/` → no output.
   Confirms the Auditor's `AC7_verified: yes`.
2. **`pyproject.toml` read field by field** against PID §8.1 and AMD-0007:
   `[build-system]` is `hatchling` with `build-backend = "hatchling.build"`
   and the wheel-packages entry; `requires-python = ">=3.12"`; the ten
   runtime dependencies and the `ibkr`/`bootstrap` extras match; ruff
   `line-length = 100`, `select = ["E","F","I","B","UP","S"]`, `S101`
   ignored in `tests/**` only; pytest `markers = ["live: …"]` and
   `addopts = "-m 'not live'"`. Matches the specification exactly.

## Adjudication of Auditor finding 1 (procedural)
The Auditor flagged that the diff touches `docs/` paths outside §2, under
§3's "no changes under `docs/`" exclusion, and asked the Architect to
confirm. **The finding is correct and the defect is mine:** §3 was written
to constrain the Implementer, while §7 simultaneously requires the Delivery
Controller to file evidence under `docs/evidence/WO-0001/` and §6.4 makes
Status and Base SHA clerical. The three flagged paths
(`docs/evidence/DELIVERY-LOG.md`, `docs/evidence/WO-0001/host-setup.md`,
the Work Order's status and base-SHA fields) are all Delivery
Controller-authored and all required or permitted.

Settled generally, not case by case: **AMD-0010 §2A** amends
DELIVERY-CHAIN §6.4 so a Work Order's §3 Exclusions bind the Implementer
only, and an Auditor finding about DC-authored `docs/` paths is procedural
and non-blocking. **Not a blocker. Nothing to repair.**

## Specification gap ratified
`hatchling` was chosen by the Implementer because WO-0001 §2 named no PEP
517 build backend — a gap in my specification, which the Implementer
reported rather than passing over and the Delivery Controller escalated
rather than waving through. Correct handling on both sides. Ratified by
AMD-0007, which now names it.

## Notes
The `commit_identity_clean` field postdates this dispatch (AMD-0009), so it
does not appear in the audit verdict block. The Delivery Controller
recorded the check in `tests.md` and the Architect re-ran it above; a
re-audit for one mechanical metadata field anyone can verify from `git log`
would have been waste.
