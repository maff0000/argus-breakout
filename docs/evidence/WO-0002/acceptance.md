# Acceptance — WO-0002 (Delegated, AMD-0011 §3)

```
WORK ORDER:        WO-0002 — DuckDB schema, Store and ticker normalisation
PARENT PID:        PID-ARGUS-0001 (Foundations)
AMENDMENTS:        AMD-0002, AMD-0011
BASE SHA:          75b230dacb555dbe2f3f4347d640262348bf2b4a
AUDITED SHA:       19ad58f96e100f90f57ebfc3b2fdb87e46516c39
PR:                #3  https://github.com/maff0000/argus-breakout/pull/3
AUDIT VERDICT:     GREEN, no findings  (docs/evidence/WO-0002/audit.md)
ACCEPTANCE:        ACCEPTED
AUTHORITY:         AMD-0011 §3 (pre-committed acceptance for the boundary-test delta), with AMD-0010 §2B conditions 2, 3, 5, 6, 7, 9
                   (AMD-0010's mandate itself does not apply: WO-0002 triggered an Amendment)
DATE (UTC):        2026-10-20
VERIFIED BY:       Rogue (Delivery Controller)
```

## AMD-0011 §3 conditions, each checked against the artefact
1. **Re-audit GREEN, no findings** — fresh Auditor at the audited SHA, whole branch: `AUDIT_VERDICT: GREEN`, `findings: none` (audit.md). Only observations, none a finding.
2. **`test_members_on_boundaries` exists with all six cases** — `tests/test_store.py`: closed interval [S,E] asserts S in, E in, S−1 day out, E+1 day out; NULL interval asserts start in and 2099-12-31 in.
3. **Both AC7 mutations run, each failed the test, output filed** — `mutation-runs.md` (Delivery Controller, on a `git archive` copy): `end_date >= ?`→`>` fails at `tests/test_store.py:130`; `start_date <= ?`→`<` fails at `:129`; unmutated and restored runs pass. Independently reproduced by the Auditor.
4. **Delta touches only `tests/test_store.py`** (plus evidence/clerical) — `git show --name-only 0958745` lists `tests/test_store.py` only; `argus/` unchanged by the delta.
5. **AMD-0010 §2B 2, 3, 5, 6, 7, 9:**
   - (2) `non_vacuity_established: yes`.
   - (3) AC1–AC7 all verified with commands and outputs filed (`operator-checks.md`, `tests.md`, `mutation-runs.md`, `audit.md`).
   - (5) `offline_tests_pass: yes` (38 passed, also under `unshare -n`); `ruff check .` clean; `gitleaks detect` clean (37 commits); CI green on the PR (`secrets`, `test`); `mergeable_state: clean` at head `5cb2230`.
   - (6) `commit_identity_clean: yes` — `c582c61..HEAD` lists only the Architect and Delivery Controller noreply identities plus GitHub's own merge identity.
   - (7) `git diff --name-only 19ad58f HEAD` lists only `docs/evidence/**` paths and `DELIVERY-LOG.md`; empty over `argus/`, `tests/`, `pyproject.toml`, `uv.lock`, `.github/`.
   - (9) Access mechanism recorded in `tests.md`: ssh only, no mount; §7.1(3) n/a.

## Notes
- The first audit (GREEN at `e5682b9`, `scope_fidelity: no`) is disclosed in `tests.md` and superseded.
- `main` (`92cb752`) was merged into the branch by hand; the single conflict (WO header) was resolved by taking main's Amendments line and re-applying Base SHA.
- Architect retrospective review applies at the P0-C group boundary.
