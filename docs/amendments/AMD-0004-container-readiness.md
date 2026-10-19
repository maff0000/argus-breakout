# AMD-0004 — Container readiness: ARGUS_CONFIG_DIR, portability constraints, PID-ARGUS-0006

| Field | Value |
|---|---|
| **Status** | Applied |
| **Amends** | `PID.md` §6, §7, §8, §13; `docs/pids/PID-ARGUS-0001-foundations.md` §8.2, §8.8, §8.9; WO-0001 §2/§4/§5/§6; WO-0003 §4; WO-0009 §4; `docs/governance/prompts/IMPLEMENTER-PROMPT.md`, `AUDITOR-PROMPT.md`; `docs/architecture/DESIGN.md` §2, §10 |
| **Related ADR** | ADR-0008 (new), ADR-0002, ADR-0007 |
| **Raised by** | Human (Product Owner), 2026-10-19: house standard is Docker; `dell-debian` is a development server and the application must be portable to production; happy to containerise after completion |
| **Affects Work Orders** | WO-0001, WO-0003, WO-0009 (all Approved, none started — edited in place); all others gain the portability constraint via the prompts and PID §8.9 |

## 1. Problem
The Product Owner builds in Docker and requires the delivered application
to be portable to a production host; ADR-0007's project-local `uv`
toolchain is accepted for the build phase only. As approved, the PIDs
would allow host-coupled code to accumulate across four phases: config read
from a relative `config/` directory, a systemd-only scheduler, and
`127.0.0.1` treated as where IB Gateway is rather than a default. Each is
cheap to prevent now and expensive to retrofit.

## 2. Change

**`PID.md` §6** — add a phase row after PID-ARGUS-0005:
> | PID-ARGUS-0006 | Containerisation | multi-stage Dockerfile (`uv sync --frozen --no-dev`), compose with `store/`+`out/` volumes and env-file, container scheduler, production deployment notes |

and replace the closing sentence of §6:
> Only PID-ARGUS-0001 is Approved at v1.0 of this document.

with
> Only PID-ARGUS-0001 is Approved at v1.0 of this document. PID-ARGUS-0006
> is planned, not yet authored: the application is built container-ready
> from WO-0001 under ADR-0008 and packaged in that phase (AMD-0004).

**`PID.md` §7** — the bullet
> - A served web dashboard (would be a new Phase PID with a new presentation target).

gains a following bullet:
> - Containerisation **in this phase**. Docker packaging is deferred to
>   PID-ARGUS-0006, not excluded; ADR-0008's portability constraints are
>   binding on every Work Order in the meantime (AMD-0004).

**`PID.md` §8** — add to the fixed-decision list:
> - **Portability:** built container-ready; no absolute paths, writes only
>   under `ARGUS_STORE_DIR`/`ARGUS_OUT_DIR`, every endpoint configurable,
>   the CLI is the only entrypoint, logs to stdout, no root at runtime.
>   (ADR-0008)

and to the "may not change without an Amendment" sentence, add
`ADR-0008's portability constraints`.

**`PID.md` §13** — append:
> Containerisation (PID-ARGUS-0006) does not gate closure of this master
> PID, but ADR-0008's constraints are part of every phase's acceptance.

**Phase PID §8.2** — `Settings` gains, after `argus_out_dir`:
```python
    argus_config_dir: Path = Path("config")
```
and the note: *every path in the application comes from these three fields
(ADR-0008); nothing resolves against the repository root or the current
working directory.*

**Phase PID §8.8** — prefix: *Config files are read from
`settings.argus_config_dir` (default `config/`), never from a path relative
to the package or discovered by walking parents (ADR-0008).*

**Phase PID §8.9** — add:
> - **Portability (ADR-0008):** no absolute paths in `argus/`; writes only
>   under `ARGUS_STORE_DIR` and `ARGUS_OUT_DIR`; every network endpoint
>   configurable; nothing in `argus/` imports or shells out to `uv`,
>   `systemd`, `apt`, or `/srv/argus-breakout-tools`; logs to stdout.

**WO-0001 §2** — `argus/settings.py` gains `argus_config_dir`; §4 gains the
ADR-0008 constraint; §5 gains `test_settings.py::test_config_dir_default_and_override`;
§6 gains **AC7**.

**WO-0003 §4** — config files are loaded from `settings.argus_config_dir`.

**WO-0009 §4** — the systemd unit and `ops/nightly.sh` contain no
application logic beyond date computation and must be replaceable by a
container scheduler without touching `argus/` (ADR-0008 constraint 5).

**Prompts** — the Implementer gains a Portability rule; the Auditor gains a
portability check with a concrete grep.

**DESIGN.md** — §2 layout note that `config/` is `ARGUS_CONFIG_DIR`; §10
gains a "Portability" paragraph pointing at ADR-0008.

## 3. Consequences
- One new settings field and one new test; no behaviour change.
- PID-ARGUS-0006's acceptance test is that it changes nothing under
  `argus/`.
- The `uv.lock` from ADR-0007 is the input to the eventual image build, so
  no toolchain rework is implied.

## 4. Application
Applied in the commit introducing this file; changed sections tagged
`(AMD-0004)`.

## 5. Approval
```
Approved by: Claude (Architect), on Product Owner instruction
Date (UTC):  2026-10-19
Commit:      the commit introducing this file
```
