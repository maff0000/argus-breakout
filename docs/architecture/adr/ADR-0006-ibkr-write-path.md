# ADR-0006 — IBKR interaction: paper account, local gateway, read-mostly

**Status:** Accepted · **Date:** 2026-10-19

## Decision
All IBKR access is to the **paper** account through a locally run IB
Gateway and `ib_async`. The ingestion client uses a read-only API
configuration. The only write the system ever performs (PID-ARGUS-0004) is
maintaining a named watchlist on the paper account, from a separate client
id. No order submission, modification or cancellation code exists in this
repository. Third-party connectors (e.g. assistant-side IBKR connectors)
are not a write path for this system.

## Consequences
- A live account is never reachable from this codebase by configuration
  alone; adding order code would require an Amendment to the master PID §7.
- Paper simulates margin and borrow, so the short/avoid playbook can be
  trialled realistically.
