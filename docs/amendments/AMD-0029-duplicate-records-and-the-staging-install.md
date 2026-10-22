# AMD-0029 — Summing vendor records created a duplicate-record exposure; and the install runs from staging, not the production checkout

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0027` §2D (narrowed); `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/work-orders/WO-0009-nightly-orchestration.md` §4, §6 (AC2, AC6, new AC13); `docs/governance/ACCEPTED-RESIDUALS.md`; adds `docs/work-orders/WO-0017-dividend-duplicate-guard.md` |
| **Related ADR** | ADR-0006, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-22: WO-0016 delivered (all 13 pairs **collapse**, 34 records recovered, PGR −5.931%), with two unattributed §2D hits — **TEL 2024-11-22 Polygon 1.30 vs yfinance 0.65** and **SKYD 2026-09-15 0.05 vs 0.10** — plus three blockers on WO-0009's install |
| **Affects Work Orders** | WO-0017 (new), WO-0009 (§4, §6), WO-0016 (accepted @ `bb42776`, no change) |

## 1. Problem

### (a) I fixed an under-count and created an over-count
WO-0016's result is unambiguous: **all thirteen pairs are collapse, none
omission, none neither.** 34 dividend records the old key had dropped are
back, and PGR's `adj_close` moved **−5.931%**, matching WO-0015's
prediction to three decimals. The key fix was right.

But look at the two hits §2D's "take the larger total" produced:

| Pair | Polygon | yfinance | Ratio | Taken |
|---|---|---|---|---|
| TEL 2024-11-22 | **1.30** | 0.65 | **exactly 2×** | Polygon |
| SKYD 2026-09-15 | 0.05 | **0.10** | **exactly 2×** | yfinance |

**An exact integer multiple is the duplicate signature, not the omission
signature.** TEL's quarterly dividend in that period is about 0.65, so
1.30 is very likely *the same dividend counted twice* — and the old
collapsing key was **protectively correct** there, by accident. By keying
on `vendor_id` and summing, I removed a guard I had not noticed I was
relying on, and §2D's rule then actively prefers the doubled figure.

This is the standard shape of a correctness fix: closing an under-count
opens an over-count. The error is small — roughly 0.43% of price on TEL,
0.55% on SKYD, one date each, against PGR's 5.93% now removed — so the net
is strongly positive. It still has to be guarded, and it cannot be guarded
from what `dividends` currently stores.

### (b) WO-0009's acceptance design is circular, and that is my fault
Acceptance requires three unattended nights and an install; the install
requires the code on the host; and the code cannot merge before
acceptance. **I wrote a gate that cannot be satisfied in the order it
specifies.**

The Delivery Controller's proposed way out — check the WO-0009 branch out
in `/srv/argus-breakout`, the production checkout — would make the
production path hold unmerged, unaccepted code for three days, where
anything else reading that path picks it up. That is the wrong resolution
to my error.

### (c) A credential copy with no owner and no expiry
A copy of `.env` sits in `/root`, mode 600, taken before the `IB_PORT`
edit. Mode and location are sensible and the intent was careful. It is
still an unmanaged copy of two live API keys, outside the one path the
project manages, with nothing scheduled to remove it — and `/root` is the
kind of place backups reach.

## 2. Change

### A. `dividends` records what makes a record distinguishable
`DESIGN.md` §3.2:
```
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, basis TEXT NOT NULL,
                source TEXT, vendor_id TEXT NOT NULL,
                declaration_date DATE NULL, frequency INT NULL)
                -- PK unchanged: (symbol, date, source, vendor_id)
                -- declaration_date and frequency come straight from the payload (AMD-0029 §2A) and
                -- are what separates a genuine second dividend from a duplicated record: PGR's
                -- 2026-01-02 pair differ on both (declared 2025-12-08 freq 4; 2025-12-05 freq 1),
                -- while a duplicate repeats them. NULL where a source does not supply them.
                -- frequency also distinguishes a regular from a special payment, which the
                -- event features want in their own right.
```

### B. Two records that agree on everything but their id are one dividend
`DESIGN.md` §3.3 gains:
> - Before summing an ex-date's records, **deduplicate**: records of one
>   `(symbol, date, source)` sharing `cash_amount`, `declaration_date` and
>   `frequency` are **one** dividend, however many `vendor_id`s they carry
>   (AMD-0029 §2B). Keying on the vendor record id stopped a genuine
>   second dividend being discarded and removed an accidental guard
>   against a duplicated one; this restores the guard deliberately,
>   on fields rather than by collapsing.

### C. §2D's "larger total wins" excludes integer multiples
`AMD-0027 §2D` is narrowed:
> The larger-total rule **does not apply** where one source's total is an
> integer multiple of the other's within one cent (2×, 3×, …). That is the
> **duplicate** signature, not the omission signature, and "take the
> larger" is then exactly backwards (AMD-0029 §2C). Such a pair is
> **warned and left on source precedence**, and named in the materialise
> report for attribution. Omission remains the asymmetry argument's
> province — a vendor dropping a component is observed; a vendor inventing
> one is not — and a clean doubling is not omission.

### D. The install runs from staging, with the store born in its final home
`WO-0009` §4 gains:
> **Do not check a feature branch out in `/srv/argus-breakout`.** The
> production checkout holds merged code only.
>
> The install and the three nights run **from the WO-0009 worktree**, with
> **`ARGUS_STORE_DIR` set to the production store path from the first
> load**, so the store is created in its final home and never needs
> relocating. ADR-0008 constraint 1 — no absolute paths in `argus/`, every
> location from settings — is what makes the code location and the data
> location independent, and this is the third time that constraint has
> paid for itself.
>
> The systemd unit's `ExecStart` points at the worktree for the staging
> nights. **On acceptance and merge it is repointed at the production
> checkout and one run is verified from there** (new AC13). The staged
> nights remain valid evidence because the commit is identical and the path
> is immaterial by construction — which is itself a test of ADR-0008.
>
> Creating the `argus` service user and installing the units is **approved**:
> both are already WO-0009 §2 scope. The first-install load — roughly 500
> Polygon calls, the yfinance bootstrap and a materialise — is approved.

**Sequencing, as the Delivery Controller proposed and for his reason:
WO-0016 merges first**, so the production store bootstraps directly at
`SCHEMA_VERSION` 6 and never holds a legacy row. Then `main` merges into
the WO-0009 branch.

**New AC13:** after merge, the unit runs from `/srv/argus-breakout`, one
nightly run completes from there, and the staging worktree's unit is
removed. Filed with the unit file's `ExecStart` path only — no host, port
or user values beyond the documented service account (CI-7).

### E. The close-reconciliation gate allows a corroborated exceedance
AMD-0020 §2A's close gate — `max |pct_diff| ≤ 0.5%` and at most one
comparison over 0.1% — would **fail** on SKYD's 2.09%, where **our value
and yfinance agree at 9.27 against IBKR's 9.08**. WO-0009's evidence
establishes that SKYD maps to the intended issuer, so this is not a
wrong-contract match.

When two independent sources agree against IBKR, the evidence favours
**us**, and failing the night on it would be the gate punishing the better
number. `WO-0009` AC6 is amended:
> At most **one** close exceedance per night is permitted **where a second
> independent source corroborates our value**, recorded with all three
> figures and named. An **uncorroborated** exceedance fails the gate,
> unchanged. Corroboration means a different vendor's close for the same
> symbol-date within 0.1% of ours.

That keeps the gate's teeth — it still fails on a value only we believe —
while not failing on one IBKR disagreed with two sources.

### F. The `.env` copy is deleted, and copies are not how a config change is recorded
**Delete `/root`'s copy of `.env` now.** The file is reconstructible from
the operator's own key custody, and an unmanaged credential copy with no
owner and no expiry is a standing liability (PID §9, CI-7).

Recorded as a rule for the runbook: **a configuration change is recorded
as a described diff — which key, old value class, new value — never as a
copy of the file.** `IB_PORT` changed from a non-allowlisted value to
4002; that sentence is the whole record, and it contains no secret.

### G. Ratified with no action
- **WO-0016 scope extensions** (`store.py`, `ingest_bootstrap.py`, the
  fixture and beyond-count test edits): ratified. The migration belongs in
  `store.py` and I listed `store_cmds.py`; `providers/bootstrap.py` was
  listed where `ingest_bootstrap.py` was also needed. **My §2 list was
  incomplete** — a consequential change under ruling 6, not a breach.
- **FCX's twelve omission dates**: the rule resolves them and the upstream
  Polygon gap remains. A vendor's completeness is not ours to fix;
  recorded as **R9**.
- **The `test_dividend_disagreement_normalises_basis` change** (0.50 vs
  0.52 now takes the larger): the intended consequence of AMD-0027 §2D.
- **AC9's volume finding.** With `useRTH=False` the ratio falls from ≈2.03×
  to **1.41×**, so **extended hours explain roughly half** and the
  remainder is attributed to off-exchange prints **without being
  measured**, as the Delivery Controller states plainly. My own reasoning
  (AMD-0020 §1c) argued the dispersion *favoured* off-exchange exclusion
  over regular-hours scoping; the measurement says it is **both**, in
  similar proportion. I preferred one mechanism where there were two — the
  same error as the dividends, caught the same way.
  The unattributed residual is **acceptable and needs no further work**,
  because AMD-0020 §2A gates on **drift**, not level: we never needed to
  explain the level, only to notice it changing. Recorded as **R10**.
- **SKYD's contract identity**: confirmed as the intended issuer, so the
  CI-2 wrong-contract concern is **cleared**. The one-day 2.09%
  disagreement is unexplained and handled by §2E.
- **Duplicate agent reports**: operational noise, correctly handled by
  stopping the duplicating agents. No governance consequence.

## 3. WO-0017 and its pre-committed acceptance
`docs/work-orders/WO-0017-dividend-duplicate-guard.md` carries §2A–§2C and
attributes TEL and SKYD from raw payloads. **It does not block WO-0009.**

**Acceptance is pre-committed**, conditional on: every AMD-0010 §2B
condition; TEL and SKYD both attributed from verbatim payloads with a
stated verdict; the dedupe proven not to discard PGR's genuine pair; the
non-vacuity mutations filed; and `bars_raw` byte-identical (CI-9). Any one
false → stop and report.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0029)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
