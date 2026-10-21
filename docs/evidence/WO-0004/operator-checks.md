# WO-0004 — Operator checks (live, AMD-0018 re-run)

Run by the Delivery Controller on dell-debian against head `46ad537e5b0a95253957b7db7b0dbfd980b443d3`, 2026-10-20T20:48Z to 2026-10-21T00:24Z. Store seeded from the WO-0003 seed (copy; `init_schema` re-run, schema v3). No key value is printed; no host, port or alias appears below.

```
$ argus ingest polygon --date 2026-10-19            (AC1)
days=1 rows=619 ok=1                                wall=2.37s
$ argus ingest polygon --backfill 2024-10-21 2026-10-19   (AC2)
days=520 rows=311406 holiday=21 ok=499              wall=6210.32s
$ argus ingest revalidate --start 2024-10-21 --end 2026-10-19   (AC7; no provider call)
days=500 rows=312025 ok=500                         wall=144.35s
$ argus ingest polygon-actions --since 2024-01-01   (AC3)
split and dividend rows upserted: 5494              wall=6604.56s
```

## Store facts (queried from the store after the run)
- `ingest_log` for the bars source: 499 `ok`, 21 `holiday`, **0 `quarantined`, 0 `failed`** (the 1053-row `ok` total in the table also holds other sources' rows). The prior run on 16a65bf rejected 268 of 520 days.
- `bars_raw`: 500 distinct dates, 312,025 rows (every provider row stored, CI-9).
- Revalidate does not touch `bars_raw`: digest (count, sum of per-row hash over symbol/date/close/volume) `(312025, 2878357238825817981218817)` before and after a second `revalidate` over 2025-01-02..2025-03-31 (60 days, 37,656 rows, all `ok`).
- AC3: 46 splits and 5,448 dividends (one source). 2026 splits present: APH 2026-09-03 (2:1), CRWD 2026-07-02 (4:1), DD 2026-06-24 (1:3), KLAC 2026-06-12 (10:1), MNST 2026-08-11 (2:1).
- `bar_flags`: **128 `jump_unexplained` rows over 99 dates and 81 symbols**; no `jump_split_reconciled` rows (no same-day provider split coincided with a jump in this window).
  - 41 of the 128 are on symbols that were members on that date (36 days). The worst day has 2 flagged members of 476 (0.42%) against the 20% breadth threshold, so no day approaches quarantine.
  - 87 of the 128 are on non-members (recorded for all, decided over `members_on(d)` only: AMD-0018 §2B). The member rows are listed below; they are large single-name moves (SMCI, QRVO, AXON, ...), i.e. earnings gaps and similar, not data defects.
- STI, AIV, NKTR: 22 `jump_unexplained` rows between them (STI 16, NKTR 4, AIV 2); **none of those symbols was a member on any flagged date**, and no day carries a day-level verdict (no day was quarantined).

## Member-day `jump_unexplained` flags (41)
| date | symbol | detail |
|---|---|---|
| 2024-10-30 | QRVO | move=-0.2731 |
| 2024-10-30 | SMCI | move=-0.3268 |
| 2024-10-31 | HII | move=-0.2616 |
| 2024-11-05 | CE | move=-0.2632 |
| 2024-11-08 | AXON | move=+0.2868 |
| 2024-11-19 | SMCI | move=+0.3124 |
| 2024-12-02 | SMCI | move=+0.2868 |
| 2025-01-10 | CEG | move=+0.2516 |
| 2025-01-10 | WBA | move=+0.2755 |
| 2025-01-27 | VST | move=-0.2827 |
| 2025-02-05 | FMC | move=-0.3353 |
| 2025-02-13 | WST | move=-0.3822 |
| 2025-02-24 | WDC | move=-0.2865 |
| 2025-04-09 | MCHP | move=+0.2705 |
| 2025-04-09 | UAL | move=+0.2614 |
| 2025-04-10 | CRL | move=-0.2813 |
| 2025-05-12 | NRG | move=+0.2621 |
| 2025-07-02 | CNC | move=-0.4037 |
| 2025-07-31 | ALGN | move=-0.3663 |
| 2025-08-04 | IDXX | move=+0.2749 |
| 2025-08-05 | IT | move=-0.2755 |
| 2025-08-08 | TTD | move=-0.3861 |
| 2025-08-13 | PSKY | move=+0.3674 |
| 2025-08-18 | DAY | move=+0.2598 |
| 2025-09-10 | ORCL | move=+0.3595 |
| 2025-09-10 | SNPS | move=-0.3584 |
| 2026-01-06 | SNDK | move=+0.2756 |
| 2026-03-20 | SMCI | move=-0.3332 |
| 2026-04-24 | CHTR | move=-0.2550 |
| 2026-04-29 | NXPI | move=+0.2555 |
| 2026-05-07 | DDOG | move=+0.3133 |
| 2026-05-08 | AKAM | move=+0.2658 |
| 2026-05-29 | DELL | move=+0.3276 |
| 2026-06-10 | SMCI | move=-0.2798 |
| 2026-07-14 | IBM | move=-0.2521 |
| 2026-07-30 | SNDK | move=+0.2599 |
| 2026-08-04 | PLTR | move=+0.2945 |
| 2026-08-04 | ZBRA | move=+0.2647 |
| 2026-08-19 | MRNA | move=+1.7697 |
| 2026-09-29 | FICO | move=-0.2652 |
| 2026-10-05 | PTC | move=+0.3349 |

```
$ grep -rnE '([0-9]{1,3}\.){3}[0-9]{1,3}' docs/evidence/WO-0004     # (empty: no IP in any evidence file)
```
