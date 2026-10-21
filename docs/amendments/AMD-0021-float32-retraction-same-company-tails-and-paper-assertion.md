# AMD-0021 — The float32 diagnosis retracted; §2F narrowed to reassigned tickers; publication is an allowlist; the paper gateway is asserted, not inferred

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0019` §1(c) (retracted) and §2A (publication predicate); `AMD-0018` §2F (narrowed); `docs/architecture/DESIGN.md` §3.3, §6.1, §10; `docs/governance/DELIVERY-CHAIN.md` §9 ruling 9 (widened); `docs/work-orders/WO-0009-nightly-orchestration.md` §2, §6 (delta); adds `docs/work-orders/WO-0014-boundary-and-warning-corrections.md` |
| **Related ADR** | ADR-0003, ADR-0006, ADR-0008 |
| **Raised by** | Delivery Controller, 2026-10-21, WO-0013 `spec-gaps.md` 1–10; and the Product Owner's correction of the gateway topology |
| **Affects Work Orders** | WO-0014 (new), WO-0009 (delta), WO-0013 (accepted and merging — no change) |

## 1. Problem

### (a) AMD-0019 §1(c) was a misdiagnosis of mine
I wrote that `float32` storage broke DESIGN §3.2's `DOUBLE` and called it a
conformance break. **There was never any float32.** The views already cast
to `DOUBLE` and the polars frames were `Float64`. The 48 rows differing at
5.1e-8 were **yfinance rows published under the flag fallback** — whose
prices are float32-valued — and removing that fallback took the count to
**zero**.

So I inferred a storage-type defect from an observed numeric difference
without checking a single dtype, and recorded it in an Amendment as
established fact. §2A of that same Amendment cured the symptom; §2C was
belt and braces on something already correct. Harmless in effect and wrong
in method — and it is the *third* instance of the same method error in this
project: ADR-0003's FMP tier, AMD-0018's threshold, this. The pattern is
always the same shape: an observation, a plausible mechanism, and no check
of the mechanism before writing it down as the cause.

Contrast WO-0013's `dividend-basis.md`, which is what the method should
look like: a prediction (the ratio equals the cumulative later-split
ratio), a population (199 crossing pairs, 4,915 non-crossing), a result
(198 and 4,876), the misfits identified individually, and worked
comparisons against the **declared** amounts — including a reverse split,
which exercises the relation in the opposite direction.

### (b) §2F drops same-company tails — 118,027 bars
AMD-0018 §2F excludes a symbol's bars after its final
`membership.end_date` unless `ticker_renames.yaml` maps it forward. I wrote
it for **ticker reassignment** — STI, where the bars after the boundary are
a different company — then applied it to **any** membership exit, which is
a different event entirely. AAL, AAP, ALK, K, M and WHR are the same
companies, still trading; their post-exit bars were dropped because no
rename continuity exists.

Rename continuity is the wrong discriminator. **A trading gap is the right
one**: a reassigned ticker has a hiatus of months or years (SunTrust
delisted December 2019; Solidion took STI in February 2024), while a
company that leaves the index trades straight through its `end_date`. The
data to tell them apart is already in `bars_raw`.

This also cuts against R5: dropping same-company tails made the
survivorship picture *worse*, not better.

### (c) Publication withholds by blocklist where it should admit by allowlist
`bars` publication withholds a day whose `ingest_log.status` is
`'quarantined'`. A historic `'failed'` day that holds `bars_raw` rows — from
before AMD-0019 §2E changed that path — therefore becomes **publishable
without ever having been judged.** A blocklist leaks the moment a new
status exists, and AMD-0019 §2E created one. The same gap sits in
`revalidate_range`, where a judging failure returns in the results with no
log row at all, so a day can keep a stale verdict indefinitely.

### (d) A coverage field hard-coded to 0
`n_symbol_days_flag_excluded` is kept at a constant 0 so the CLI still
runs. A coverage figure that always reads zero says *"nothing was
excluded"* when it means *"not computed"* — exactly the unstated optimism
CI-8 exists to prevent, and indistinguishable from a real measurement at
the point of reading.

### (e) The gateway topology was not what the evidence assumed
The Product Owner has confirmed the intended arrangement: **the paper
gateway on `dell-debian`, the live gateway on a separate host** (not named
here — CI-7 and AMD-0001 permit only `dell-debian` in this repository).
The gateway found listening on the **live** port on `dell-debian` is
therefore a stray that should not be running there.

The live checks ran against `dell-debian`'s paper-port gateway, which is
the correct target under that topology, so WO-0008's evidence stands and
needs no re-run. But it means the only thing that stood between the
application and a live gateway was the **port allowlist**, one barrier
rather than two, and it means the port number is being used as a *proxy*
for "this is a paper account" rather than as a check of it.

## 2. Change

### A. §1(c) is retracted
AMD-0019 §1(c) is **withdrawn as a misdiagnosis**; a pointer to this
section is recorded in that file so no reader acts on it. AMD-0019 §2C
(prices stored `DOUBLE`) **stands** — it is now belt and braces on
behaviour that was already correct, which is a cheap place to be. The
cause of the 5.1e-8 differences was the cross-source substitution removed
by AMD-0019 §2A.

**The method obligation on me, stated so it can be held against me:** a
mechanism I have not checked is a hypothesis, and it is written down as a
hypothesis — never as the cause, and never as the premise of a change.
WO-0013's `dividend-basis.md` is the standard.

### B. §2F is narrowed to reassigned tickers, by trading gap
`DESIGN.md` §3.3's listing-life rule becomes:
> - A symbol's `bars` tail is bounded only where the **ticker was
>   reassigned to a different entity** (AMD-0021 §2B, narrowing AMD-0018
>   §2F). The discriminator is a **trading gap**, not rename continuity:
>   where `bars_raw` is continuous across the final
>   `membership.end_date` — no gap exceeding **20 trading days** — the
>   post-exit bars are the same company's and are **retained**, because a
>   company that merely leaves the index keeps trading and may re-enter.
>   Where a gap exceeds 20 trading days, the tail is excluded and the
>   symbol warned: that is the reassignment hazard, where joining the two
>   runs would splice a different company's prices onto the member's
>   history. `ticker_renames.yaml` continuity still suppresses the
>   warning. Leading history before the first `start_date` is retained
>   unconditionally (AMD-0019 §2D).

### C. Publication admits by allowlist; a judging failure always logs
`DESIGN.md` §3.3:
> - Publication admits a day **only** where `ingest_log.status = 'ok'`
>   (AMD-0021 §2C) — never "any status other than `'quarantined'`". A day
>   with stored rows and no completed verdict is unjudged data, and the
>   remedy is `ingest revalidate`, not publication. A blocklist admits
>   every status invented after it was written.
> - A judging failure **always** writes an `ingest_log` row, in
>   `revalidate_range` as well as in `ingest_polygon_day`. A path that
>   returns a failure without recording it lets a day keep a stale verdict
>   indefinitely.

### D. Comparisons normalise basis before comparing
> - `dividend_disagreement` compares two sources only after normalising
>   both to one basis with the same `split_cum` (AMD-0021 §2D). Comparing
>   an `as_paid` amount with a `split_adjusted` one reports the split ratio
>   as a vendor disagreement: 228 warnings over 42 symbols, every one
>   generated by the correction itself.
> - A split dated **on** the ex-date is divided out: the dividend was
>   declared before it. The divisor takes the last bar **before** the
>   ex-date, not the first on or after it.

### E. The paper gateway is asserted, not inferred
`DESIGN.md` §10:
> - Gateway topology: the **paper** gateway runs on `dell-debian`; any live
>   gateway runs on another host and is never reachable from this
>   application's configuration. A gateway listening on a live port on
>   `dell-debian` is a misconfiguration to be removed, not a thing to
>   defend against by port number alone.
> - **The paper account is asserted on connect, not inferred from the
>   port** (AMD-0021 §2E). After `connect(readonly=True)`, the managed
>   account identifier delivered in the handshake must carry IBKR's
>   paper prefix (`DU`/`DF`); otherwise the client disconnects
>   immediately and raises. **Only a boolean leaves the check**: the
>   identifier is never logged, stored, filed in evidence or included in
>   an exception message (CI-7). This reads handshake data already
>   received and is **not** an account, order or position request, which
>   WO-0008 §3 continues to exclude.

`ib_host`'s `127.0.0.1` default (**R3**) is **retained**, and the
topology is why: with the live gateway on another host, a loopback default
plus the paper-port allowlist plus the account assertion means the
application on `dell-debian` can reach nothing but `dell-debian`'s paper
gateway. Three independent barriers, two of which only exist if the stray
local live-port gateway is removed. I had intended to withdraw R3 and that
would have been wrong — it is the default that makes the live host
unreachable.

### F. A coverage field reports or is absent; it is never a constant
> - `n_symbol_days_flag_excluded` reports the measured count or is
>   **NULL** — never `0` when uncomputed (AMD-0021 §2F, CI-8). A figure
>   that always reads zero is indistinguishable from a measurement of
>   zero. It must report truthfully or be removed before
>   PID-ARGUS-0002 computes a feature, and the Work Order that builds the
>   aggregates must call `equal_weight_aggregate` rather than reimplement
>   it.

`DESIGN.md` §6.1 gains the same obligation for every coverage figure it
lists.

### G. Ruling 9 widened
`DELIVERY-CHAIN` §9 ruling 9's first sentence gains: *"…and, more
generally, any test that fails **purely because a mandated column or table
was added** — including a positional literal that must gain the new
column's value, and the test module belonging to a source module named in
§2."* WO-0013's three edits (`test_store.py`, `test_schema.py`'s positional
`INSERT`, `test_ingest_polygon.py`) are **ratified** under it; ruling 6
already covered the first and third as consequential.

### H. Ratified with no action
WO-0013 spec-gaps **6** (`equal_weight_aggregate` proven at function level
— acceptable; §2F above binds the consumer), **7** (the retraction above),
and the same-date split/dividend observation. WO-0013's result stands:
flags published, 20 of 20 identical, differing Polygon rows 48 → 0,
boundary warnings 3,403 → 121, `bars_raw` byte-identical (CI-9).

## 3. Work Orders

### WO-0014 — new, Approved
`docs/work-orders/WO-0014-boundary-and-warning-corrections.md` carries
§2B, §2C, §2D and §2F. All of it is in `argus/data/adjust.py`,
`argus/data/ingest_polygon.py` and their tests. **It does not block
WO-0009** and makes no provider call.

### WO-0009 — delta addition
§2 gains `argus/data/providers/ibkr.py` for §2E's paper-account
assertion, and a new **AC11**. This is the only remaining Work Order that
touches that file; WO-0014 does not, so the two run concurrently.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0021)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
