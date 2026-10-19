# WO-0001 — Operator checks

Run by the Delivery Controller on dell-debian (execution host) against the final head. No real credential appears
below; dummy credential files contain the documented fake `AKIAIOSFODNN7EXAMPLE`. No host/port/key value is involved.

```
host=dell-debian head=be5a224bf98cb5ffb25e4d462663d72f3c45c6f9
--- AC5: clean checkout of the branch, then uv sync --all-extras
clean checkout at be5a224bf98cb5ffb25e4d462663d72f3c45c6f9
uv.lock
$ uv venv --python 3.12 .venv && uv sync --all-extras   (AC1 + AC5)
Activate with: source .venv/bin/activate
 + websockets==17.3
 + yfinance==1.7.0
sync rc=0
$ .venv/bin/python --version
Python 3.12.15
$ uv lock --check
Resolved 61 packages in 1ms
$ uv run ruff check .   (AC2)
All checks passed!
$ gitleaks detect --source . --redact   (AC6)
11:28PM INF scanned ~564964 bytes (564.96 KB) in 460ms
11:28PM INF no leaks found
rc=0
--- spot-check 1 (auditor finding 1: authorship of the two commits)
be5a224 Rogue (Delivery Controller) <noreply@anthropic.com> WO-0001: log rebase onto 02ddd97de53c34fb2914cab17ca7cf3e832d659f (clerical, DELIVERY-CHAIN 6.3)
2c6acd6 Rogue (Delivery Controller) <noreply@anthropic.com> WO-0001: repository skeleton, settings, logging, CLI, tooling, CI
27909a4 Rogue (Delivery Controller) <noreply@anthropic.com> WO-0001: mark In Progress, record base SHA, file host-setup evidence
02ddd97 Claude (Architect) <noreply@anthropic.com> AMD-0007: name hatchling as the build backend; stop .gitignore swallowing governance docs
cc2480a Claude (Architect) <noreply@anthropic.com> AMD-0006: worktree access path and cross-host evidence provenance
--- spot-check 2 (auditor perturbation: default config dir changed must fail tests)
=========================== short test summary info ============================
FAILED tests/test_settings.py::test_defaults_without_env - AssertionError: as...
FAILED tests/test_settings.py::test_config_dir_default_and_override - Asserti...
2 failed, 7 passed in 0.39s
(restored; empty diff above)
9 passed in 0.14s
```
