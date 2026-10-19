# ADR-0007 — Python 3.12 via project-local `uv`; no system installs on the delivery host

**Status:** Accepted · **Date:** 2026-10-19

## Context
The delivery host runs Debian 12 with system Python 3.11. The PID requires
Python 3.12. The Delivery Controller is not authorised to install system
packages, and the host runs other services (ADR-0002 least-privilege
posture). Raised by the Delivery Controller at Step 0 of PID-ARGUS-0001,
correctly, as a stop condition.

## Decision
Use **`uv`** (Astral) installed **project-locally**, with a `uv`-managed
CPython 3.12, under `/srv/argus-breakout-tools/`. Nothing is installed via
apt, nothing is placed on system paths, nothing is shared with other
services, and removal is `rm -rf /srv/argus-breakout-tools`.

```
UV_INSTALL_DIR=/srv/argus-breakout-tools/bin           # uv binary
UV_PYTHON_INSTALL_DIR=/srv/argus-breakout-tools/python # managed CPython 3.12
UV_CACHE_DIR=/srv/argus-breakout-tools/cache
```
- Install `uv` from a **versioned GitHub release asset** with its published
  SHA-256 verified; record the version and checksum in evidence. Do not
  pipe a remote script into a shell.
- `uv python install 3.12` then, per checkout/worktree:
  `uv venv --python 3.12 .venv && uv sync --all-extras` (reads
  `pyproject.toml` + `uv.lock`). Run everything through the venv:
  `uv run python -m pytest -q`, `uv run ruff check .`, `.venv/bin/argus`.
- The lockfile is **`uv.lock`**, committed; it replaces the
  `requirements.lock` named in WO-0001.
- CI uses `astral-sh/setup-uv` with `uv sync --all-extras` and `uv run`,
  so CI and host resolve identically.
- The systemd unit (WO-0009) keeps `ExecStart` on
  `/srv/argus-breakout/.venv/bin/…`; the tools directory is mode 0755 so the
  `argus` service user can read and execute it, and it is listed read-only
  under `ProtectSystem=strict` (no `ReadWritePaths` entry needed).

## Alternatives considered
Docker `python:3.12` — uses the shared daemon, adds a runtime boundary
between the pipeline, the store and IB Gateway; rejected. pyenv/source
build or apt backports — system-wide change needing host authority;
rejected. Downgrading the project to 3.11 — rejected; 3.12 is the agreed
runtime and the Debian system Python is not for application venvs.

## Consequences
- One more directory to back up or recreate; otherwise zero host footprint.
- Implementers and Auditors must prepend `/srv/argus-breakout-tools/bin` to
  `PATH` in their dispatch (the Delivery Controller states this in every
  prompt).
