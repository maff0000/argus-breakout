# WO-0010 — Secret-drop hardening: ignore credential-shaped files, document the drop procedure

| Field | Value |
|---|---|
| **Status** | In Progress |
| **Parent PID** | `PID.md` (PID-ARGUS-0000) §9 Public Repository Security |
| **Applicable Amendments** | AMD-0005, AMD-0006, AMD-0007 |
| **Base SHA** | `02ddd97de53c34fb2914cab17ca7cf3e832d659f` (rebased from `c582c61…` under §6.3: in-scope diff empty; carries AMD-0006/0007 text) |
| **Branch** | `wo/0010-secret-drop-hardening` |
| **Depends on** | none |
| **Parallel group** | P0-A (independent of WO-0001; touches no path in its scope) |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0010/` |

## 1. Objective
Make it mechanically hard to commit a credential file that is dropped into
the repository working tree, and document where credentials are handed
over instead. Prompted by a real near-miss: a key file placed in the
repository root, protected only by nobody having run `git add -A`.

## 2. Scope (exhaustive)
```
.gitignore           modify  add a "credential-shaped files (never commit)" section, after the existing
                             secrets block, ignoring at minimum:
                               *.key  *.pem  *.p12  *.pfx  *.jks
                               *secret*  *credential*  *apikey*  *api-key*  *api_key*  *token*
                               /*.txt            # root-level .txt: the shape of a dropped key file
                             with a comment stating that a real documentation .txt must be added with
                             `git add -f` and a reviewer's attention, and that `.env.example` stays tracked
                             (it is already negated in the secrets block);
                             then, AFTER the credential patterns, re-include governance documents so no future
                             document can be silently ignored (AMD-0007):
                               !/docs/**
                               !/*.md
                             The negations must not re-include .env; verify every case with `git check-ignore -v`
.gitleaks.toml       modify  add a scoped `[[rules]]` entry `argus-bare-key-file` that flags any staged file whose
                             path matches `(?i)(polygon|fmp|ibkr|llm|api)[-_. ]?(key|token|secret)?\.(txt|key|json)$`
                             regardless of content, so an empty-looking or oddly formatted key file is still blocked;
                             keep `[extend] useDefault = true` and the existing allowlist intact
README.md            modify  in the "Setup (once per clone)" section, add one short paragraph: credential values are
                             handed over in `/tmp` only (e.g. `/tmp/<provider>.txt`), moved into `.env` without being
                             printed, then shredded; never place a credential file inside the repository working tree
tests/test_repo_hygiene.py   create  see §5 — pure-stdlib test, no package import, so it runs before WO-0001 exists
```

## 3. Exclusions
No changes to `scripts/hooks/pre-commit`, `ops/`, `.github/workflows/`,
`PID.md`, or anything under `docs/` other than nothing (evidence is filed
by the Delivery Controller). No `argus/` code — this Work Order must not
depend on the package existing, so that it can run concurrently with
WO-0001.

## 4. Design constraints
`tests/test_repo_hygiene.py` must use only the standard library and must
not import `argus`, so it passes on a checkout where WO-0001 has not
landed. It locates the repository root from its own `__file__`, not from
the working directory. If `pytest` is not yet available on the branch, the
file must also be runnable as `python tests/test_repo_hygiene.py` and exit
non-zero on failure — state in the test module's docstring which invocation
the Delivery Controller used.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_repo_hygiene.py::test_env_ignored` | `.env` is ignored | asserts on `.gitignore` content |
| `test_repo_hygiene.py::test_credential_patterns_ignored` | each of `polygon.txt`, `secrets.json`→(`*secret*`), `my-api-key`, `id.pem`, `svc.token` matches an ignore rule, checked with `git check-ignore -q` in a temp worktree or by pattern match against the file | a pattern removed from `.gitignore` makes it fail |
| `test_repo_hygiene.py::test_env_example_still_tracked` | `.env.example` is NOT ignored | would fail if a broad rule swallowed it |
| `test_repo_hygiene.py::test_gitleaks_rule_present` | `.gitleaks.toml` contains the `argus-bare-key-file` rule id and still sets `useDefault = true` | string assertions |

## 6. Acceptance criteria
- **AC1** — `git check-ignore -q polygon.txt` succeeds from the repository root (operator check: command + exit status).
- **AC2** — `git check-ignore -q .env.example` **fails** (the file remains tracked) and `git ls-files .env.example` lists it (operator check).
- **AC3** — With a dummy file `polygon.txt` containing a fake key, `git add -A` stages nothing (operator check: `git status --porcelain` output filed; dummy file then removed).
- **AC4** — `gitleaks detect --source . --redact` and `gitleaks protect --staged --redact` both exit 0 on the branch with no such file staged (operator check).
- **AC5** — With a dummy `polygon.txt` force-staged (`git add -f polygon.txt`), `gitleaks protect --staged --redact` exits non-zero and names the `argus-bare-key-file` rule (operator check; unstage and delete the dummy afterwards). This is the non-vacuity check for AC4.
- **AC6** — README documents the `/tmp`-only drop procedure (Auditor reads it).
- **AC7** — Tests in §5 pass (`uv run python -m pytest -q tests/test_repo_hygiene.py`, or `python tests/test_repo_hygiene.py` if `uv` has not been set up on this branch).
- **AC8** — Governance documents are never ignored, in either direction (AMD-0007): `git check-ignore -q docs/amendments/AMD-0099-secret-test.md` **fails**, `git check-ignore -q docs/work-orders/WO-0099-token-test.md` **fails**, `git check-ignore -q .env` **succeeds**, `git check-ignore -q polygon.txt` **succeeds**. Operator check: all four commands and exit statuses filed (`check-ignore` does not require the paths to exist).

## 7. Evidence the Delivery Controller must file
`tests.md`, `auditor-prompt.md`, `audit.md`, `acceptance.md`,
`operator-checks.md` (AC1–AC5 outputs; **never** paste a real key — use an
obvious fake such as `AKIAIOSFODNN7EXAMPLE`).

## 8. Implementer notes
Order the `.gitignore` additions after the existing secrets block so the
`!.env.example` negation keeps working; verify with `git check-ignore -v`.
The `/*.txt` rule is deliberately broad for this repository, which has no
root-level `.txt` files; it is the pattern that would have caught the real
near-miss. Keep the gitleaks rule narrow enough not to fire on `requirements.txt`-style
names (the regex above requires a provider/credential word).

`gitleaks` scans diff **content**, so the path-only rule cannot fire on a
zero-byte key file (AMD-0007). That is accepted and bounds the rule's
claim: **`.gitignore` is the load-bearing control** — it stops `git add -A`
staging the file at all — and the gitleaks rule is defence in depth for the
force-added case, where a real key has content. AC5 therefore uses a fake
key **with content** and remains the non-vacuity check for AC4. Do not
weaken AC5 to chase the empty-file case, and do not claim the rule covers
it.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```

## 10. Delivery log (DC appends)
```
```
