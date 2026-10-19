"""Repository hygiene checks for WO-0010 (secret-drop hardening).

Standard library only; does not import `argus`; offline; needs `git` on PATH.
The repository root is located from this file, not from the working directory.

Invocations (either works, non-zero exit on failure):
    python tests/test_repo_hygiene.py
    python -m pytest -q tests/test_repo_hygiene.py

Delivery Controller: record in tests.md which invocation was used.

Ignore behaviour is checked with `git check-ignore` inside a throwaway
repository (a temp dir outside the worktree) that holds only a copy of this
repository's `.gitignore`, so the real index is never touched.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Names that must be ignored (root-level, as a dropped file would be).
CREDENTIAL_NAMES = [
    "polygon.txt",
    "secrets.json",  # *secret*
    "my-api-key",
    "id.pem",
    "svc.token",
]


def _ignored(repo: Path, name: str) -> bool:
    """True if `git check-ignore -q` says `name` is ignored in `repo`."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", name],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed: {result.stderr!r}")
    return result.returncode == 0


class _TempRepo:
    """Throwaway git repo carrying a copy of the real .gitignore."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.mkdtemp(prefix="hygiene-")
        repo = Path(self._tmp)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
        return repo

    def __exit__(self, *exc: object) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


def test_env_ignored() -> None:
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in lines, ".gitignore must list .env"
    with _TempRepo() as repo:
        assert _ignored(repo, ".env")


def test_credential_patterns_ignored() -> None:
    with _TempRepo() as repo:
        missing = [n for n in CREDENTIAL_NAMES if not _ignored(repo, n)]
    assert not missing, f"not ignored: {missing}"


def test_env_example_still_tracked() -> None:
    with _TempRepo() as repo:
        assert not _ignored(repo, ".env.example"), ".env.example must not be ignored"
    assert (ROOT / ".env.example").is_file()


def test_gitleaks_rule_present() -> None:
    text = (ROOT / ".gitleaks.toml").read_text()
    assert 'id = "argus-bare-key-file"' in text
    assert "useDefault = true" in text


def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001 - report every failure
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
