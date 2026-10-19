# AMD-0002 — One command module per Work Order; append-only import block in cli.py

| Field | Value |
|---|---|
| **Status** | Applied |
| **Amends** | `docs/pids/PID-ARGUS-0001-foundations.md` §8.7; scope tables of WO-0001 … WO-0009 |
| **Related ADR** | none |
| **Raised by** | Architect (pre-delivery review), 2026-10-19 |
| **Affects Work Orders** | WO-0001 … WO-0009 (all Approved, none In Progress) — scope tables edited in place in the same commit |

## 1. Problem
As approved, WO-0004 and WO-0005 (parallel group P0-C) both *modified*
`argus/data/ingest.py` and `argus/cli.py`, and WO-0003/0006/0007/0008 all
modified `argus/cli.py`. Concurrent Work Orders editing the same files
guarantees integration conflicts for the Delivery Controller and
contradicts the groups' claimed independence.

## 2. Change
- PID §8.7 gains the **command-module rule**: `argus/cli.py` (WO-0001)
  defines the root app, the five sub-app objects in
  `argus/commands/{universe,ingest,events,adjust,ibkr}.py`, and a marked
  append-only import block. Each later Work Order creates its own module
  under `argus/commands/` and adds exactly one import line to that block.
- WO-0004's ingestion logic moves from `argus/data/ingest.py` to
  `argus/data/ingest_polygon.py`; WO-0005's to `argus/data/ingest_bootstrap.py`.
- Each Work Order's scope table replaces its `argus/cli.py modify` line with
  a `create` line for its own `argus/commands/<name>_cmds.py` (or
  `ingest_polygon.py` / `ingest_bootstrap.py`) plus the one-line
  `argus/cli.py` import addition.
- WO-0002 implements `init-store` in `argus/commands/store_cmds.py` and
  removes WO-0001's stub.

## 3. Consequences
No change to behaviour, CLI surface, tests or acceptance criteria. The
only remaining shared edit between concurrent Work Orders is one appended
line each in a block designed for it; the Delivery Controller resolves any
textual overlap by keeping all lines.

## 4. Application
Applied in the commit introducing this file. Changed sections tagged
`(AMD-0002)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
