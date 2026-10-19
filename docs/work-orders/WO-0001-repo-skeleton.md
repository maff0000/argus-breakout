# WO-0001 — Repository skeleton, settings, logging, CLI, tooling, CI

| Field | Value |
|---|---|
| **Status** | Approved |
| **Parent PID** | `docs/pids/PID-ARGUS-0001-foundations.md` — §8.1, §8.2, §8.3, §8.7 (skeleton only), §9 |
| **Applicable Amendments** | none |
| **Base SHA** | `aec11259c066d7adb6db867c80bdb0c8b5c62a47` |
| **Branch** | `wo/0001-repo-skeleton` |
| **Depends on** | none |
| **Parallel group** | P0-A |
| **Presentation target** | FUNCTIONAL_ONLY |
| **PR** | — |
| **Evidence** | `docs/evidence/WO-0001/` |

## 1. Objective
An installable `argus` package with typed settings, structured logging, a
typer CLI skeleton, lint/test tooling and a lockfile, such that
`pip install -e ".[dev]" && ruff check . && python -m pytest -q` passes
offline and `argus --version` prints the version. No data code yet.

## 2. Scope (exhaustive)
```
pyproject.toml                       create  PEP 621; name=argus; version=0.1.0; requires-python>=3.12;
                                             deps/extras exactly per PID §8.1; [project.scripts] argus="argus.cli:app";
                                             [tool.ruff] per PID §8.1; [tool.pytest.ini_options] markers=["live: needs credentials/network"],
                                             addopts="-m 'not live'"
requirements.lock                    create  pinned output of `pip freeze` for the dev environment (python 3.12)
argus/__init__.py                    create  __version__ = "0.1.0"
argus/settings.py                    create  Settings, ConfigError, get_settings() exactly per PID §8.2
argus/logging.py                     create  configure_logging(level) per PID §8.3, incl. redaction processor
argus/cli.py                         create  typer app; `--version` callback; sub-apps registered as empty groups:
                                             universe, ingest, events, adjust, ibkr; command `init-store` stubbed to
                                             raise typer.Exit(2) with message "store not implemented (WO-0002)"
argus/py.typed                       create  empty marker
tests/__init__.py                    create
tests/conftest.py                    create  fixture `clean_env` (monkeypatch removes every ARGUS_/POLYGON_/FMP_/IB_/LLM_ var,
                                             sets env_file to a non-existent path)
tests/test_settings.py               create  see §5
tests/test_logging.py                create  see §5
tests/test_cli.py                    create  see §5
.github/workflows/ci.yml             modify  remove the `if [ -f pyproject.toml ]` guards (package now exists)
```

## 3. Exclusions
No `argus/data/`, no providers, no DuckDB code, no YAML config files, no
systemd units, no README changes, no changes under `docs/` (the Delivery
Controller adds evidence), no `.env`.

## 4. Design constraints
PID §8.1–8.3 and §8.9. Secrets are `pydantic.SecretStr`; `Settings.__repr__`
must not reveal them. `require()` raises `ConfigError` whose message lists
every missing field name, nothing else. Logging writes JSON lines to stdout
only. No network access anywhere in this Work Order.

## 5. Required tests
| Test | Proves | Capable of failing because… |
|---|---|---|
| `test_settings.py::test_defaults_without_env` | defaults load with no `.env` and no env vars | asserts exact default values |
| `test_settings.py::test_require_lists_all_missing` | `require("polygon_api_key","ib_port")` raises `ConfigError` naming both | asserts both names in message |
| `test_settings.py::test_secret_not_in_repr` | `repr(Settings(polygon_api_key="abc"))` lacks `abc` | string assertion |
| `test_logging.py::test_json_and_redaction` | a log line with `api_key=XYZ` is emitted as JSON with `XYZ` redacted | captures stdout, parses JSON |
| `test_cli.py::test_version` | `argus --version` exits 0 and prints `0.1.0` | typer `CliRunner` |
| `test_cli.py::test_init_store_stub_exits_2` | stub exits 2 | exit-code assertion |

## 6. Acceptance criteria
- **AC1** — `pip install -e ".[dev]"` succeeds on Python 3.12 (operator check, output filed).
- **AC2** — `ruff check .` reports no violations (test: CI lint job; operator check).
- **AC3** — `python -m pytest -q` passes with no `.env` present (tests above).
- **AC4** — `argus --version` prints `0.1.0` (test_version).
- **AC5** — `requirements.lock` exists and `pip install -r requirements.lock` resolves (operator check).
- **AC6** — `gitleaks detect --source .` clean (CI; operator check).

## 7. Evidence the Delivery Controller must file
`tests.md` (commands + summary), `auditor-prompt.md`, `audit.md`,
`acceptance.md`, `operator-checks.md` (AC1, AC2, AC5, AC6 outputs).

## 8. Implementer notes
Read PID §8.1–8.3 first; the signatures there are binding. Keep `cli.py`
free of business logic; sub-apps are empty `typer.Typer()` groups that
later Work Orders populate. Do not add dependencies beyond PID §8.1.

## 9. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-19
Commit:      the commit introducing docs/work-orders/README.md (git log -1 -- docs/work-orders/README.md)
```

## 10. Delivery log (DC appends)
```
```
