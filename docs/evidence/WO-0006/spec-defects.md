# WO-0006 — Specification defects handled under standing ruling 7 (AMD-0016 §2A)

**Criterion: AC1** — "`argus events refresh` populates earnings for ≥ 60% of active symbols for the next 45 days" (operator check on the host).

**External data fact.** On this FMP plan `/stable/earnings-calendar` returns a thin sample of the market's reports: 70 rows for the 56-day window and 27 rows for the 26–30 October peak week (a real
season has hundreds of S&P 500 reports in that week), unchanged by `limit=4000`. The same endpoint carries no `time` field (bmo/amc is not provided). The code stores what the provider returns; the shortfall is the provider's.

**Measured, named beside the aggregate (CI-8):**
| Figure | Value |
|---|---|
| Active symbols | 518 |
| Earnings rows stored (active symbols) | 46 |
| Active symbols with upcoming earnings | **39 of 518 = 7.5%** (AC1 target ≥ 60%) |
| Earnings rows with a known time of day | **0 of 46** (the CLI prints `time of day known for X of Y earnings rows`) |
| Ex-dividend rows stored | 12 |
| FMP calls used | 2 (AC3 met) |

**Hard guards, each checked:**
1. *Critical invariant touched?* No. CI-8 is upheld: the coverage ratio and the time-of-day coverage travel with the figures in the report and the CLI. CI-6: an unavailable calendar is named, and the absence of a date is returned as **unknown** (`days_to_earnings` None), never as "no earnings soon".
2. *Would the fix change behaviour rather than report?* Yes. The only remedy is another earnings source (a new provider and Work Order), which is raised to the Architect, not applied here.
3. *Weakens non-vacuity?* No. Tests use recorded real-shape rows; bmo/amc mapping tests use labelled synthetic data; mutation results are in `audit.md`.

**Consequence the Architect should weigh.** Consumers of `days_to_earnings` / `next_earnings` must treat None as **unknown**. With 7.5% coverage, an earnings gate built on this calendar would silently pass over 90% of names. The Product Owner's breakout/earnings plan needs a complete earnings schedule (and report timing) from another source before any earnings-based rule is trusted.
