# AMD-0035 — Bound the feature run where it is computed, and make the nightly die before the host does

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `AMD-0034` §2G (the constraint moves from WO-0023 to WO-0018); `docs/architecture/DESIGN.md` §5, §10; `docs/work-orders/WO-0018-feature-layer.md` §2, §4, §6; `docs/work-orders/WO-0009-nightly-orchestration.md` §2, §6 |
| **Related ADR** | ADR-0008 |
| **Raised by** | Product Owner, 2026-10-22, on WO-0018's measured **7.9 GB peak RSS** |
| **Affects Work Orders** | WO-0018 (delta), WO-0009 (unit directive) |

## 1. Problem

### (a) The figure is explainable, and avoidable
1,565,316 rows × (87 features + 87 `_pct` + 87 `_pct_sector`) = **408.5M
values**. At float64 the finished frame is **3.27 GB**, so a 7.9 GB peak is
**2.4× the final frame** — ordinary for a dataframe pipeline holding
intermediates and join copies. Nothing is leaking.

It is also unnecessary. The recursive features (Wilder smoothing, OBV,
run lengths) need a symbol's **whole history**, but they are **independent
across symbols** — and the cross-sectional percentiles need **all symbols
for one date**, which is 594 × 261 × 8 = **1.24 MB**. So the two halves
chunk along different axes and neither needs the whole panel resident:

| | per-chunk frame (float32) |
|---|---|
| 25 symbols | 0.07 GB |
| 50 symbols | 0.14 GB |
| 100 symbols | 0.28 GB |

Chunking also removes the oddity in AC6: a **single-date** run took 24
seconds *because the recursions load the whole history*. Chunked, a single
date touches one symbol group at a time and that cost falls out.

### (b) I filed it against the wrong Work Order
AMD-0034 §2G made peak memory a constraint on **WO-0023**, the nightly
step. But WO-0023 only *calls* the computation — it cannot bound what
`compute_features` allocates. The constraint belongs where the allocation
happens: **WO-0018**.

### (c) The real risk is not tidiness; it is which process gets killed
`dell-debian` is a shared development host, running the Product Owner's
model stack — vLLM with LMCache, which offloads KV cache to **host** RAM,
not only VRAM. A nightly step peaking near 8 GB at 23:30, unattended, can
put the host under memory pressure.

**And the Linux OOM killer chooses by score, not by ownership.** The
process it kills may well be the model server rather than the nightly that
caused the pressure — a failure that is silent, happens while nobody is
watching, and looks nothing like its cause.

## 2. Change

### A. The feature layer computes in chunks — in WO-0018, not downstream
`WO-0018` §2 and §4:
> `compute_features` processes **symbols in configurable batches**
> (`ARGUS_FEATURE_SYMBOL_BATCH`, default **50**) for the per-symbol and
> recursive features, and computes the cross-sectional percentiles **per
> date**. Neither stage holds the whole panel resident. The batch size is a
> setting, never a literal (ADR-0008 constraint 3).
>
> **Peak RSS is measured and reported** for the full-history run, the
> single-date run, and per batch (AC6). **Target: under 1 GB.** Above
> **2 GB** is a finding to report with the largest contributor named, not a
> figure to pass silently.

### B. Features are stored `float32` and computed `float64`
`DESIGN.md` §5:
> Features are **computed in float64** and **stored float32**
> (AMD-0035 §2B). This does **not** touch `bars`, whose price columns stay
> **DOUBLE** (AMD-0019 §2C): a return is a difference of nearly equal
> numbers, where narrowing the inputs loses significance catastrophically.
> A stored **feature** is a bounded indicator or a 0–100 rank, where seven
> significant digits are ample, and it halves the frame from 3.27 GB to
> 1.63 GB.
>
> **The rule that makes this safe:** no consumer may take a **difference of
> two stored feature values**. Any such quantity — `dist20_atr`,
> `bb_width`, every `*_atr` distance — is computed **inside the feature
> layer in float64** and stored as its own feature. A playbook reads
> percentiles and stored features; it never subtracts one stored feature
> from another.

### C. The nightly is memory-capped, so it dies before the host does
`WO-0009` §2 — `ops/argus-nightly.service` gains:
```
MemoryMax=<cap>      # cgroup v2: the UNIT is killed, not a victim chosen by OOM score
MemoryHigh=<cap-1G>  # throttle and reclaim before the hard kill
```
> The cap is set **from the host's measured total RAM**, not guessed, and
> the Delivery Controller reports that total with the chosen value. Default
> **4 GB** unless the measurement says otherwise.
>
> The point is not to make the nightly succeed. It is to make its failure
> **predictable and attributable**: a capped unit that exceeds its limit is
> killed by its own cgroup, the journal says so, and **AC14's staleness
> alarm fires the next morning**. Uncapped, the kernel picks by OOM score
> and may take the model server instead — a silent overnight failure with
> no connection to its cause. This is also why AC14 exists.

`DESIGN.md` §10 records the same, and adds: **no nightly step may be
unbounded in memory on a shared host.**

### D. New AC16 on WO-0009
> **AC16** — The nightly units carry `MemoryMax`/`MemoryHigh`; the host's
> total RAM and the chosen cap are filed. A deliberately over-cap run is
> killed by **its own cgroup** (journal line filed) and **AC14's alarm
> fires** the following morning. No host, port or path values beyond the
> unit's own (CI-7).

### E. AMD-0034 §2G is superseded
The WO-0023 constraint is withdrawn in favour of §2A. WO-0023 inherits
whatever WO-0018 delivers and adds no memory logic of its own — a step that
cannot bound an allocation should not be made responsible for it.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0035)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-22
Commit:      the commit introducing this file
```
