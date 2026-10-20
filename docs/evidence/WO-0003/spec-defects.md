# WO-0003 — Specification defects handled under standing ruling 7 (AMD-0016 §2A)

Criterion: **AC6** ("Total FMP calls for one `universe refresh` ≤ 60 and the run completes successfully when every FMP endpoint returns 402; operator check: run once with the real key and once forced to 402") and the live half of **AC10** ("today and the last trading day exit 0") **at the final head `6896fe7`**.

External data fact: on 2026-10-20 the FMP key's allowance was exhausted by this day's earlier verification runs; the provider returned HTTP 429 on every endpoint (status-code probe after the run). The live real-key run at the final head therefore measured 96 call attempts (2 × 402, 28 × 200, 66 × 429, i.e. 22 profile calls × 3 retries) and the closing "today" run exited 1 on a 429 at the changes endpoint.

Measured, not assumed:
| Figure | Value |
|---|---|
| Real-key run at `8530a79` (allowance available) | 52 calls (2 × 402 + 50 profile 200), exit 0 for today and for the last trading day |
| Forced-402 run at `6896fe7` | 3 calls, exit 0, same route and counts |
| Real-key run at `6896fe7` (rate-limited) | 96 attempts; route, rows by source, AC9 = 0, members_on(today) = table = 503, AC2 diffs 0/0/0 all unchanged |
| AC10 refusals at `6896fe7` (CLI, live) | 30 days and 8 days back: exit 2, store counts unchanged |
| Within-window / today exit 0 at `6896fe7` | by tests (all three routes × 2 dates; 10/10 mutants killed), not live |

Hard guards, each checked:
1. *Critical invariant touched?* No. CI-1 (one open interval per current symbol) is measured live at the final head: current members without a row = 0, `members_on(today)` = the 503-symbol table. CI-8 coverage figures are reported beside the aggregate.
2. *Fix would change behaviour rather than report?* The only remedy (treating a 429 like a 402, or capping attempts) would change behaviour, so it is **not** applied; it is raised as spec gap 7 for the Architect. The merge changes nothing about it.
3. *Weakens a non-vacuity requirement?* No. The code paths under the shortfall (back-dated within window, set equality, window refusal) are guarded by killed mutants M1–M7; the delta since the last fully live run (`8530a79`) does not touch the FMP client or the profile cap.

Merge proceeds under the pre-committed acceptance; a post-reset live repeat is recommended, not conditional (spec gap 8).
