# WO-0003 — Spec gaps and residuals (for the Architect)

Resolved: the rename gap (audit pass-1 finding) → AMD-0014; the back-dated invariant (pass-2 finding) → fixed in `4c10c60`.

Open / for the retrospective:
1. **Whole-interval relabelling.** `_apply_renames` re-sources the mapped old ticker's *entire* open-at-H interval (back to its hanshof start) as `rename-*`, per AMD-0014 §2C "both rows". Dates are exact; the precision label of the early start is lost. A `hanshof+rename-*` form (cf. `hanshof+fmp`) would preserve it. Ask: keep or change.
2. **PARA→PSKY inside hanshof.** PSKY appears in hanshof only at the 2025-08-23 snapshot (PARA ends 2025-08-22), so the same continuity defect exists *inside* hanshof, for any `as_of` before 2025-08-23 (SKYD is then named as an orphan on a back-dated run). Not in the five-pair seed; adding a PARA→SKYD/PSKY pair would fix it. The same may hold for other renames inside the 2015–2025 history (hanshof series are ticker-keyed); price series across such renames are a WO-0004/0005/0006 concern.
3. **Effective dates** for the five pairs are null (no free source). Operator-maintained; fill when known.
4. **Price series across renames.** `bars` for an old ticker come from yfinance/Polygon under that ticker; yfinance serves old-ticker history only under the new ticker (WO-0005 live bootstrap: BK, FI, MMC, EQR(?), PSKY, … fail as "possibly delisted"). The membership model is now continuous, but the *price* continuity across a rename needs a rule (alias table in the bars layer). Not WO-0003's scope; flag for WO-0006/0007 design.
5. **Observed (audit):** orphan exemption trusts the map (obs 1); back-dated runs on an FMP-only current table fail closed (obs 2); route-(b) detector is fixture-only (no live changes table exists); the `httpx` logger could log `apikey` URLs if a handler is attached (note for WO-0009).
6. **AMD-0014 §3 diff condition.** The delta also touches `argus/commands/universe_cmds.py` (two report lines + exit path), which is in WO-0003 §2 but not in AMD-0014 §3's three-file list. The condition is therefore not literally satisfied; reported rather than self-waived.
