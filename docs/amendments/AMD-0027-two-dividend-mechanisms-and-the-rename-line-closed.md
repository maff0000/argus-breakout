# AMD-0027 — Two dividend mechanisms, keyed on the vendor record id; the rename line is closed

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §3.2, §3.3; `docs/governance/CRITICAL-INVARIANTS.md` CI-4 and CI-2 scope notes; `docs/governance/ACCEPTED-RESIDUALS.md` R5; `AMD-0025` §1(b) (overstatement corrected); `docs/ROADMAP.md`; adds `docs/work-orders/WO-0016-dividend-record-identity.md` |
| **Related ADR** | ADR-0003 |
| **Raised by** | Delivery Controller, WO-0015 live evidence, 2026-10-21: PGR collapse **confirmed** from the raw payload, FCX collapse **refuted**; 500 rename candidates and 184 members where signal (1) holds |
| **Affects Work Orders** | WO-0016 (new), WO-0015 (accepted @ `193ec5a`, no change) |

## 1. Problem

### (a) Two mechanisms, established from payloads
**PGR 2026-01-02 — collapse confirmed.** Polygon returns **two records**
for one ex-date: a quarterly `0.10` (`frequency: 4`) and an annual special
`13.50` (`frequency: 1`). The store keeps one. yfinance's `13.60` is their
sum. The key `(symbol, date, source)` discards the other record, exactly as
AMD-0025 §1(a) suspected.

**FCX 2026-07-15 — collapse refuted.** Polygon returns **one** record
(`0.075`) and the store holds it faithfully. Polygon simply never carries
the second component that yfinance sums into `0.15`. That is an **upstream
vendor completeness gap**, not my key.

**One ruling would have fixed PGR, left FCX exactly as wrong, and left me
believing it was solved.** That is the whole return on a diagnostic-only
Work Order, and it is why no fix was designed from the hypothesis.

**It also caught a design error before I made it.** I had `dividend_type`
in mind as the discriminating key component. **Both PGR records carry
`dividend_type: "CD"`** — the quarterly and the special are
indistinguishable by type, so that key would have collapsed them exactly
as the present one does. `frequency` differs here and will not in general.

What the payload does carry, on every record, is **`id`** — a stable
per-record vendor identifier. Verified, not assumed.

### (b) Why this is worth fixing: the error is cumulative, not local
`adj_close` is built from a running product of dividend factors, so a
wrong amount on one ex-date shifts **every earlier `adj_close` for that
symbol**. PGR's entire pre-2026 history is off by **5.93%**, silently, and
every return crossing that date inherits it. Thirteen `(symbol, ex_date)`
pairs across twelve symbols, from 0.43% to 5.93% — all variable, special
or supplemental payers. Twelve of the thirteen are **not yet attributed**
to either mechanism.

### (c) The rename line cannot work, and I overstated its harm
500 candidates, and **VMRK pairing with 32 different leavers**, is the
answer rather than a tuning problem: **index maintenance is pairwise by
construction.** S&P replaces one name with another on a date, so *every*
addition has an adjacent leaver. Signal (2) is therefore as near-universal
as signal (1) (AMD-0026 §2C), and no combination separates a rename from a
swap, because the distinguishing fact is **corporate identity** and that is
not in our data at any price.

**AMD-0025 §1(b) overstated the consequence.** An *unmapped* rename does
**not** sever a price series: both free sources serve a renamed company's
whole history under the new ticker, so META's bars run continuously under
META and META's features are unaffected. The real consequence is that `FB`
counts as a member **without bars** in the 2013–2022 composites — one name
in roughly 500, equal-weighted. That is an **R5 coverage gap already
measured by CI-8**, not the CI-2 severance I described.

**"184 severed current members" also reads worse than it is.** It means
184 current members have bars predating their membership interval — which
is *normal*, because companies list years before they join. It is not 184
broken histories. The figure is right; my account of what it would mean was
wrong.

## 2. Change

### A. `dividends` is keyed on the vendor record identity
`DESIGN.md` §3.2:
```
dividends      (symbol TEXT, date DATE, cash_amount DOUBLE NOT NULL, basis TEXT NOT NULL,
                source TEXT, vendor_id TEXT NOT NULL)
                -- PK (symbol, date, source, vendor_id)  (AMD-0027 §2A)
                -- vendor_id: the SOURCE'S OWN per-record identifier. Polygon supplies `id` on
                -- every /v3/reference/dividends record (verified, WO-0015 evidence). A source
                -- with no record identifier — yfinance, which already delivers one summed
                -- figure per ex-date — uses the literal 'sum'.
                -- NOT dividend_type: both of PGR's 2026-01-02 records are "CD", so type does
                -- not discriminate a quarterly from a special. NOT frequency, for the same
                -- reason in the general case.
```

### B. The adjustment sums the records for an ex-date
`DESIGN.md` §3.3's dividend rule gains:
> - A symbol's dividend for an ex-date is the **sum of that source's
>   records** for it, taken after source precedence and after basis
>   normalisation (AMD-0027 §2A, §2D). One row per vendor record; one
>   total per ex-date.

### C. CI-4 is corrected
> | CI-4 | `splits` and `dividends` are separate tables with `NOT NULL` measures. `splits` is keyed `(symbol, date, source)`; **`dividends` is keyed `(symbol, date, source, vendor_id)`** because a source may legitimately report several dividends on one ex-date — a quarterly and a special — and the narrower key silently keeps one (AMD-0027 §2A, measured at WO-0015: PGR 0.10 + 13.50). The adjustment sums the records for an ex-date. |

CI-2's scope note is refined: an undeclared rename is an **R5 coverage
gap**, not a severance; detection from stored data was attempted at
WO-0015 and **is not possible** (§1c), so the map is maintained by hand
from index announcements.

### D. The vendor completeness gap — a stated precedence rule
Where two sources' **normalised, summed** totals for one `(symbol, date)`
differ by more than **one cent and 2% relative**, the adjustment takes the
**larger** total, records which source supplied it, and warns with both
figures.

The justification is asymmetry: a vendor **omitting** a dividend component
is observed (FCX), while a vendor **inventing** one is not. The comparison
must be on **basis-normalised** amounts (AMD-0019 §2B, AMD-0021 §2D) —
Polygon stores `as_paid` and yfinance `split_adjusted`, so comparing raw
amounts would read a split ratio as a completeness gap.

**This rule is conditional on attribution.** It is written now so WO-0016
needs no second ruling, but WO-0016 applies it only to pairs its own
measurement attributes to omission. A pair that is neither a collapse nor
an omission is a **stop**.

### E. The rename line is closed
No further rename classification work. `diagnose renames` is retained as a
**candidate generator for human review**; `config/ticker_renames.yaml`
stays operator-maintained. **R5** gains the coverage consequence:
undeclared renames add members-without-bars to historical composites, which
CI-8's per-date coverage already reports. `docs/ROADMAP.md` records that
classification from stored data was tried, measured and abandoned, with the
reason — so it is not attempted again.

## 3. WO-0016 — and its pre-committed acceptance
`docs/work-orders/WO-0016-dividend-record-identity.md` carries §2A–§2D. It
**attributes the remaining twelve pairs first**, then applies the branch
each one earns.

**Acceptance is pre-committed**, conditional on: every AMD-0010 §2B
condition 1–9; all thirteen pairs attributed with their raw payload
summaries filed; `adj_close` before/after reported per affected symbol; the
AC non-vacuity mutations filed; `bars_raw` byte-identical (CI-9); and **no
pair left unattributed** — an unattributed pair is a stop, not a residual.
Any one false → stop and report.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0027)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
