# Accepted residuals

Known limitations the Architect has considered and **accepted**, with the
reason. An Auditor that rediscovers one of these records it as an
observation, **not a finding**, and it never blocks a GREEN. The Delivery
Controller does not stop for one. Adding or removing an entry is an
Amendment.

| # | Residual | Scope | Why accepted | Recorded by |
|---|---|---|---|---|
| R1 | Root-level Markdown with a credential-shaped filename (`secret.md`, `token.md`, `api-key.md`) is stageable. | `.gitignore` | `!/*.md` must keep `README.md` and `PID.md` tracked. A filename pattern cannot protect prose: a secret pasted into `notes.md` is the same risk. Gitleaks **content** scanning is the control for all Markdown. Blocking `secret.md` while allowing `notes.md` would be theatre. | AMD-0008 |
| R2 | The `argus-bare-key-file` gitleaks rule cannot flag a zero-byte key file. | `.gitleaks.toml` | Gitleaks scans diff **content**; an empty file offers none. `.gitignore` is the load-bearing control — it stops `git add -A` staging the file at all — and this rule is defence in depth for the force-added case, where a real key has content. A zero-byte file contains no secret. | AMD-0007 |
| R3 | `ib_host` defaults to `127.0.0.1` in `argus/settings.py`. | `argus/settings.py` | Required by PID §8.2 and ADR-0008 constraint 4: a configurable default, not an assumption. It is not a hostname disclosure. | AMD-0010 |
| R4 | Public `astral-sh/uv` GitHub release URLs appear in `docs/evidence/WO-0001/host-setup.md`. | evidence | ADR-0007 requires the version, URL and SHA-256 of the toolchain to be recorded. A public vendor URL is not an internal service URL. | AMD-0010 |
| R5 | Bars coverage for delisted historical members is incomplete — the free source serves no data for a material share of them (measured at the WO-0005 live run: historical cohort 110 of 237 covered, **46.4%** — AMD-0017 §2E; the earlier 79.8% figure used a different denominator). | `bars_raw`, and every composite built from it | No free source covers delisted history well; this is what paid point-in-time datasets exist for. Accepted **only because the bias is made measurable**: DESIGN §6.1 requires `n_members_with_bars` alongside `n_members` per date, breadth reported with its coverage ratio, a `coverage_flag` below 95%, and exclusion from the PID-ARGUS-0004 lead-time study unless explicitly included. Accepting it silently would have put unstated optimism into every backtest. Over **half** of delisted historical members have no bars at all, so periods with material turnover lean substantially toward survivors; PID-ARGUS-0004's lead-time study must **weight** coverage, not merely record it. | AMD-0015 |
