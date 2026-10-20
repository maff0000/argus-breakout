# WO-0004 — Spec gaps and residuals (for the Architect)

1. **Historical members have no `symbols` row** → the §validation rule rejects every pre-2025-08-23 day (210 of 521). See `operator-checks.md` AC2. Needs an Amendment (and shares its cause with WO-0005 AC1).
2. **Same-date split+dividend** is not demonstrable on Polygon data (0 pairs); proven by tests and on WO-0005's yfinance data.
3. **Today's grouped-daily** is not published when the backfill's last day (today) runs → `failed=1`, exit 1. The WO says `<today>` as the end; a nightly run uses yesterday. Suggest the AC end the range at the last trading day.
4. **Unpinned guards:** `ratio <> 1` filter and the `.unique` dedupe in the actions path.
5. **Operator-check ordering:** run before WO-0003 merged (see `operator-checks.md`).
6. **Price series across renames** (BK→BNY etc.): Polygon serves each ticker as it traded; the alias question is a P0-D design item (see WO-0003/WO-0005 spec-gaps).
