# Architect Acceptance — WO-0010

```
WORK ORDER:        WO-0010 — Secret-drop hardening
PARENT PID:        PID-ARGUS-0000 §9 (Public Repository Security)
AMENDMENTS:        AMD-0005, AMD-0006, AMD-0007, AMD-0008
BASE SHA:          4d1f2f1 (merged main for AMD-0008/0009 mid-flight)
AUDITED SHA:       7a0cf85556be311f050de0aa36449ee06e60c2d1
BRANCH HEAD:       1428f6c0cd5147bfd658783f7034e2d48faf0f2c
PR:                #2  https://github.com/maff0000/argus-breakout/pull/2
AUDIT VERDICT:     GREEN, whole branch, with AC9 and commit_identity_clean
ACCEPTANCE:        ACCEPTED
AUTHORITY:         explicit Architect acceptance — WO-0010 triggered Amendments
                   (AMD-0007, AMD-0008), so AMD-0010's mandate would not apply
                   to it in any case
DATE (UTC):        2026-10-19
ARCHITECT:         Claude (Architect)
```

## Checks performed by the Architect
- [x] AC1–AC9 verified with recorded command output, including all 19 AC9
      rows and the four AC8 commands.
- [x] Auditor dispatch prompt filed verbatim; no diff-specific hint.
- [x] Audit GREEN on the **whole branch** at the post-delta SHA, after the
      superseded evidence was removed so the Auditor could not see the
      earlier verdict — the right handling of a re-audit.
- [x] Diff within scope: `.gitignore`, `.gitleaks.toml`, `README.md`,
      `tests/test_repo_hygiene.py`, plus DC evidence and clerical paths
      (procedural per AMD-0010 §2A).
- [x] No secrets committed. AC5's force-staged dummy used a fake key.
- [x] Commit identity clean over `c582c61..1428f6c` (AMD-0009).

## Architect spot-check, run directly against the artefact
I extracted the branch's actual `.gitignore` into a scratch git repository
and re-ran the **entire AC9 matrix** myself with `git check-ignore -q` —
not against the Auditor's narrative or the Delivery Controller's report:

- **All 12 "must be ignored" rows ignored:** `.env`, `.env.local`,
  `secret.key`, `id.pem`, `polygon.txt`, `docs/x/polygon.txt`,
  `deep/a/b/fmp.txt`, `docs/x/.env`, `docs/secret.key`, `docs/id.pem`,
  `docs/credentials.json`, `sub/secret.md`.
- **All 7 "must not be ignored" rows tracked:**
  `docs/amendments/AMD-0011-secret-rotation.md`,
  `docs/work-orders/WO-0099-token-test.md`, `docs/runbook/OPERATIONS.md`,
  `docs/README.md`, `README.md`, `PID.md`, `.env.example`.
- **0 mismatches.** The extension-scoped negations (`!/docs/**/*.md`,
  `!/*.md`) and `*.txt` at all depths behave exactly as AMD-0008 specifies.

I also read the `argus-bare-key-file` rule: `[extend] useDefault = true` is
intact, the existing allowlist is unchanged, and the path regex requires a
provider/credential word so `requirements.txt`-style names cannot match.

## Residuals confirmed as accepted, not findings
- **R1** — root-level credential-shaped Markdown names stay stageable.
- **R2** — the path rule cannot flag a zero-byte key file.

Both are recorded in `docs/governance/ACCEPTED-RESIDUALS.md` with reasons.
`.gitignore` is the load-bearing control; the gitleaks rule is defence in
depth. AC5 keeps a fake key **with content** as the non-vacuity check for
AC4, and must not be weakened to chase the empty-file case.

## Note on origin
This Work Order exists because a credential file was dropped inside the
repository working tree and the Delivery Controller reported it rather than
quietly tidying up. The near-miss produced a durable control. That is the
behaviour the governance is for.
