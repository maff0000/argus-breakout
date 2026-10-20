# WO-0004 — Operator checks (live, host-run)

Run at head `db714d9` (code under audit; `b5948ae` adds only a main merge). Polygon key from the git-ignored `.env`, never printed. Store seeded from WO-0003's real `universe refresh` (no scaffold). Free tier: 5 calls/min.

**Sequencing disclosure.** AMD-0013 §3 orders WO-0004's operator checks after WO-0003 merges. WO-0003 is not merged yet (awaiting the Architect's confirmation); these checks used WO-0003's real refresh output from its branch head. They should be re-run (AC1 only, a few seconds) after WO-0003 merges if the Architect wants strict ordering.

## AC1 — met
`argus ingest polygon --date 2026-10-19` → `days=1 rows=518 ok=1`, wall 2.61 s (518 = current members 503 + 15 ETFs; ≥ 95% of members).

## AC3 — met in part; one sub-check not demonstrable live
`argus ingest polygon-actions --since 2024-01-01` → `split and dividend rows upserted: 4683`, wall 6,629 s (rate-limited).
Tables: `splits` source=polygon **43**; `dividends` source=polygon **4,640**. Known 2026 splits present: AMCR 2026-01-15 (0.2), BKNG 2026-04-06 (25), CVNA 2026-05-08 (5), KLAC 2026-06-12 (10), DD 2026-06-24 (⅓), CRWD 2026-07-02 (4), MNST 2026-08-11 (2), APH 2026-09-03 (2).
**Same-date split + dividend: 0 pairs exist in this Polygon data**, so "a symbol with a same-date split and dividend retains both rows" cannot be shown on live data; it is proven by `test_same_date_split_and_dividend_retain_both`-style tests (audited, mutation-checked), and live on WO-0005's yfinance data (3 pairs retained: XRX, DHR, DXC).

## AC2 — run completes and is resumable, but 210 weekdays are rejected (needs a ruling)
`argus ingest polygon --backfill 2024-10-21 2026-10-20` → `days=521 rows=147853 failed=1 holiday=21 ok=289 rejected=210`, wall 6,218 s, exit 1.
`ingest_log` (source=polygon): ok 290 (2025-08-25…2026-10-19), holiday 21, rejected 210 (**every weekday 2024-10-21…2025-08-22**), failed 1 (2026-10-20: today's grouped-daily is not yet published).
Literal AC2 (“one row per weekday with status ok/holiday/rejected”) is met; its purpose (two years of bars) is **not**: nothing before 2025-08-25 was stored.
**Root cause.** Every rejected day fails the §validation gate with, e.g., `coverage 0.9125 below 0.95 (459/503 members); 44 member(s) lack an industry group (e.g. AMTM, ANSS, AVB, BK, BLDR)`. `members_on(d)` for a pre-2025-08-23 date includes historical
members (AVB, BK, BLDR, CAG, CPB, …) that are no longer in the index; WO-0003 writes only *current* constituents (and ETFs) to `symbols`, so historical members have no `symbols` row, no industry group, and are not in the bars filter, so coverage < 95%.
Not a Polygon problem and not a code defect in WO-0004: a seam between WO-0003 (`symbols` = current only) and the validation rule (every member on the date must have an industry group), which only bites for historical dates. **Needs an Architect ruling / Amendment**
(options: write historical members into `symbols` with their last-known group and `active=false`; or define the historical-date validation population as members that have a `symbols` row; or accept a coverage gate relative to symbols). The same gap is behind WO-0005 AC1.
