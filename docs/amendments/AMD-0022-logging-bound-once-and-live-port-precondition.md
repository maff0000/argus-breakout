# AMD-0022 — Logging is bound once per process and its arrival is proved; no live gateway on the nightly host

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/work-orders/WO-0009-nightly-orchestration.md` §4, §6 (delta); `docs/architecture/DESIGN.md` §10 |
| **Related ADR** | ADR-0008 (constraint 6) |
| **Raised by** | Delivery Controller, 2026-10-21: integrating WO-0013 with the merged WO-0008 failed two `tests/test_store.py` tests because `configure_logging()` left structlog bound to a stdout pytest had closed. Fixed test-side by an autouse `structlog.reset_defaults()` fixture, proved two ways. Plus the Product Owner's removal of the stray live-port gateway on `dell-debian` |
| **Affects Work Orders** | WO-0009 (delta), WO-0013 (accepted @ `affa975`, no change) |

## 1. Problem

### (a) The logger binds a stdout *object*, and nothing proves a line ever arrives
`configure_logging()` ends with
`logger_factory=structlog.PrintLoggerFactory(file=sys.stdout)`. That
captures the stdout **object** as it exists at call time rather than
resolving it at each write. Under pytest, `CliRunner` swaps `sys.stdout`,
the test ends, the object closes, and the next `log` call writes to a dead
file — which is exactly what the Delivery Controller hit and fixed
correctly on the test side.

The production edge is not the test fixture's business. **`argus nightly`
runs every step in a single process**, so anything that replaces
`sys.stdout` after configuration — a redirect, a capture, a library
wrapper — sends every subsequent JSON line to an object nobody reads,
**silently, with no error, and with the run still reporting success.**

Worse, ADR-0008 constraint 6 requires structured JSON on stdout and
**nothing anywhere checks that a line arrives.** A logging requirement with
no check that logging happened is a vacuous requirement — the same shape
as the jump rule that could not fire (AMD-0017 §2B) and the coverage field
hard-coded to zero (AMD-0021 §2F). Three instances now of a channel that
cannot report its own absence.

### (b) The nightly could install onto a host serving a live gateway
AMD-0021 §2E states the intended topology and names three barriers —
loopback default, port allowlist, paper-account assertion — but two of
them only hold once the stray live-port gateway on `dell-debian` is gone.
Nothing measured whether it was. An intention recorded in a design
document is not a control.

## 2. Change

### A. Logging is configured once, by the entrypoint
`WO-0009` §4 gains: `configure_logging()` is called **exactly once per
process**, before any step runs; no step re-enters it and nothing replaces
or redirects `sys.stdout` afterwards.

### B. Log arrival is an acceptance criterion
`WO-0009` **AC12**: the captured stdout holds valid JSON on every line,
with one start and one finish record per executed step carrying the shared
`run_id`, and the counts are filed. **Non-vacuity (CI-6):** configuring
logging against a stale stdout object, or redirecting stdout after
configuration, must make it fail.

### C. No live gateway on the nightly host
`WO-0009` **AC10a**, a precondition checked at install: nothing on the host
is listening on an IBKR live port, recorded pass/fail with **no port or
host values filed** (CI-7). **A fail is a stop** — the nightly does not
install onto a host that is also serving a live gateway.

`DESIGN.md` §10's topology bullet gains: the absence of a live gateway on
the nightly host is **verified at install (WO-0009 AC10a)**, not assumed.

### D. Credential hygiene when archiving a gateway container
Recorded because it applies to the Product Owner's archive of the removed
container, and because nothing in this repository should imply otherwise:
an `ib-gateway` container's filesystem and environment hold the brokerage
**login credentials** (IBC's `config.ini` and the container env). A
`docker export` or `commit` of a configured gateway therefore writes those
credentials into the archive at rest.

So an archive keeps the **configuration** — compose file, Dockerfile,
volume layout, image digest — with credential values referenced from the
secret store rather than embedded, **or** the archive is encrypted.
Exporting a running gateway's filesystem to an unencrypted backup share is
a credential copy, whatever it is called. This repository holds no
credential and never will (CI-7, PID §9); the same standard applies to
anything taken out of the host.

## 3. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0022)`.

## 4. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
