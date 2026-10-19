# WO-0001 — host toolchain setup (ADR-0007, AMD-0003)

Performed by the Delivery Controller on dell-debian, 2026-10-19 (UTC).

| Item | Value |
|---|---|
| uv version | 0.13.0 (x86_64-unknown-linux-gnu) |
| Release URL | https://github.com/astral-sh/uv/releases/download/0.13.0/uv-x86_64-unknown-linux-gnu.tar.gz |
| Published checksum URL | https://github.com/astral-sh/uv/releases/download/0.13.0/uv-x86_64-unknown-linux-gnu.tar.gz.sha256 |
| SHA-256 (published) | `1468ebd5a5541121837c5a2817b9972ba6090fa6caa3d142620850a47fb75154` |
| Verification | `sha256sum -c` printed `uv-x86_64-unknown-linux-gnu.tar.gz: OK` before extraction |
| Install location | `/srv/argus-breakout-tools/bin` (uv, uvx), mode 0755 |
| Managed CPython | 3.12.15 under `/srv/argus-breakout-tools/python` (`uv python install 3.12`) |
| Cache | `/srv/argus-breakout-tools/cache` |
| Environment | `UV_INSTALL_DIR`, `UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR` set to the paths above |

Notes:
- 0.13.0 was chosen over the same-day 0.13.2 so the release had ten days of use.
- Nothing was piped into a shell; nothing was installed via apt or to a system path.
- `uv python install` created a `python3.12` symlink in the root user's local bin
  directory. It pointed into the tools directory (verified) and was removed, so
  nothing outside `/srv/argus-breakout-tools` remains.
