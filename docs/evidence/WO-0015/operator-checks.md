# WO-0015 operator checks (AC5 read-only)
- Store file sha256 prefix before all diagnose runs ad96a0cb313d414a; after (AC2, PGR raw, FCX raw, renames): ad96a0cb313d414a — identical.
- Row counts unchanged by construction (read-only connect): bars_raw 2055196, bars 1700331, dividends 26291, membership 751.
- config/ticker_renames.yaml unchanged; git status of the worktree clean after all runs.
- Live calls: exactly two (PGR, FCX), one HTTP request each, status 200; POLYGON_API_KEY exported from the private env file for the process only, never printed or filed.
