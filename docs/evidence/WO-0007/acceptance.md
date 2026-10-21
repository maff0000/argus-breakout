# WO-0007 — Acceptance (delegated, AMD-0010 §2B)

| # | Condition | Result | Evidence |
|---|---|---|---|
| 1 | Independent audit GREEN on the whole branch | **true, two non-blocking findings** | `audit.md` (F1 dividend tolerance, F2 yfinance fallback), recorded in `spec-gaps.md` for ratification |
| 2 | Every AC verified or an operator check filed | **true, with a recorded shortfall** | AC1, AC4 met live; AC3 by tests; **AC2 17 of 20 as literally worded** (the three misses are excluded by AMD-0018 §2F by design), filed in `spec-defects.md` with the population figures |
| 3 | Diff within the Work Order's §2 (AMD-0016 §2A) | **true** | Auditor `scope_fidelity: yes` |
| 4 | Non-vacuity shown for the new behaviour | **true** | 15 Auditor mutants, 14 + 7 Implementer mutants, all killed |
| 5 | No critical invariant breached | **true** | CI-9 (no write path to `bars_raw`), CI-2 (rename continuity), CI-5 (`adj_version` increments on any change to published rows), CI-8 (quarantine/flag counts in the report and CLI) |
| 6 | `gitleaks` clean; no IP in the diff or evidence | **true** | `tests.md`; evidence grep empty |
| 7 | Commit identity clean | **true** | the two identities in range are the Delivery Controller and the GitHub merge of PR #9 by the Product Owner's account (upstream) |
| 8 | Unachievable criterion handled | **by analogy with ruling 7, flagged for confirmation** | `spec-defects.md` |
