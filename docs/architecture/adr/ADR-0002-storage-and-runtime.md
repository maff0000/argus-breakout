# ADR-0002 — Storage and runtime: Python 3.12, polars, DuckDB + Parquet

**Status:** Accepted · **Date:** 2026-10-19

## Context
~500 symbols × ~2,500 daily bars ≈ 1.25M rows plus a wide feature table.
Nightly batch; one writer; a few readers (CLI, report, MCP server).

## Decision
Parquet files partitioned by year (bars) and by date (features), catalogued
and queried by DuckDB (`store/argus.duckdb`). Feature computation in
`polars`. No database server. Python 3.12. HTTP via `httpx`, config via
`pydantic-settings`, CLI via `typer`, quality via `pytest` + `ruff`.

## Alternatives considered
PostgreSQL/TimescaleDB — more operations, only justified by a served UI
with concurrent writers; may be added later as a serving layer. SQLite —
poor for columnar scans over the feature table.

## Consequences
- Zero-ops storage; whole store fits in RAM; reproducible point-in-time
  queries.
- Concurrency is single-writer; the nightly pipeline is the only writer.
