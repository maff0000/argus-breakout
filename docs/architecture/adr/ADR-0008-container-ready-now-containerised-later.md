# ADR-0008 — Container-ready now, containerised in PID-ARGUS-0006

**Status:** Accepted · **Date:** 2026-10-19 · **Supersedes nothing; constrains ADR-0002, ADR-0007**

## Context
The Product Owner's house standard is to build in Docker: `dell-debian` is
a **development** server and the delivered application must be portable to
a production host. ADR-0007 chose a project-local `uv` toolchain on the
development host because the Delivery Controller had no authority for
system installs; the Product Owner has accepted that for the build phase
and asked to move to Docker once the application is complete.

Accepting the deferral without constraints is the expensive path: nine
Work Orders of code written against an absolute repo path, a local DuckDB
file, a systemd scheduler and `127.0.0.1` for IB Gateway would make
containerisation a rewrite rather than a packaging step.

`uv` is also the current standard for reproducible Python images
(`uv sync --frozen --no-dev` in a multi-stage build), so ADR-0007's
`uv.lock` is the artefact the eventual Dockerfile wants. The toolchain
choice is forward-compatible.

## Decision
**Build the application container-ready from WO-0001 onward; containerise
in a later phase (PID-ARGUS-0006), not now.**

Binding portability constraints on every Work Order of every phase:

1. **No absolute paths in application code.** Every filesystem location
   comes from settings: `ARGUS_STORE_DIR`, `ARGUS_OUT_DIR`,
   `ARGUS_CONFIG_DIR` (added by AMD-0004). Nothing resolves against the
   repository root, `/srv/...`, or the current working directory.
2. **Write only under `ARGUS_STORE_DIR` and `ARGUS_OUT_DIR`.** These are
   the only two mutable paths; in a container they are volumes. No writes
   to the package directory, no caches or temp files outside
   `tempfile.mkdtemp()`.
3. **All configuration from environment variables** through
   `argus/settings.py` only (already PID §8.9). No config discovered by
   walking parent directories.
4. **Every network endpoint is configurable**, including `IB_HOST` and
   `IB_PORT` — `127.0.0.1` is a default, never an assumption. Code must
   work when IB Gateway is on another host (in a container it is).
5. **The CLI is the only entrypoint.** `argus <command>` must do the whole
   job with no host services required. Anything host-coupled —
   systemd units, the `ops/nightly.sh` wrapper, the backup rsync — lives
   under `ops/`, contains **no application logic**, and is replaceable by a
   container scheduler without touching `argus/`.
6. **Logs to stdout** as structured JSON (already PID §8.3). No log files,
   no syslog, no journal-specific behaviour.
7. **No root required at runtime.** The process runs as an unprivileged
   user and must not depend on the uid; `store/` and `out/` permissions are
   set by the operator or the volume mount.
8. **Nothing in `argus/` may import or shell out to `uv`, `systemd`,
   `apt`, or anything under `/srv/argus-breakout-tools`.** The toolchain is
   build-time only.

PID-ARGUS-0006 (Containerisation) will add a multi-stage `Dockerfile`
(`uv sync --frozen --no-dev` into a slim runtime image), a
`compose.yaml` with `store/` and `out/` volumes and an env-file, and a
scheduler (`compose` + host cron, or the orchestrator's own). It will not
need to change `argus/` if the constraints above hold — that is the
acceptance test for this decision.

## Consequences
- One settings field and a handful of discipline rules now; a packaging
  phase later instead of a rewrite.
- The Auditor gains a portability check per Work Order (AMD-0004).
- ADR-0007's tools directory stays development-only and is not part of the
  delivered artefact.

## Alternatives considered
**Containerise now, before WO-0001.** Rejected for this build phase on the
Product Owner's instruction, and because it would couple every Work
Order's test loop and the IB Gateway path to a Docker daemon shared with
other work on the development host. Revisit only by Amendment.

**Ignore portability until the end.** Rejected: the four constraints that
cost nothing now (paths, endpoints, entrypoint, logs) are precisely the
ones that are expensive to retrofit across four phases of code.
