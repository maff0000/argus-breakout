# WO-0015 spec gaps for the Architect
1. Rename discriminator (see rename-candidates.md): signals 1+2 yield 500 candidates and 184 severed members; they cannot separate a rename from an index swap or a later addition. Needs a different signal.
2. AC6(b) test is weaker than its purpose (audit finding 1); one extra seeded case would close it.
3. cli.py change is 3 lines, not one import line (new Typer app needs add_typer).
4. Private accessors used: PolygonClient._get, Store._renames; public accessors would be cleaner if the diagnostics are kept.
5. Dividend mechanism: PGR = two Polygon records collapsed by key (symbol,date,source); FCX = Polygon carries one record only. Two mechanisms; a fix WO needs a decision on key/aggregation AND on the Polygon completeness gap.
