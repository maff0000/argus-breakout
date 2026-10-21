from typer.testing import CliRunner

from argus.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init_store_creates_store(clean_env, tmp_path):
    clean_env.setenv("ARGUS_STORE_DIR", str(tmp_path / "store"))
    result = runner.invoke(app, ["init-store"])
    assert result.exit_code == 0
    assert "store ready: 21 tables" in result.output
    assert (tmp_path / "store" / "argus.duckdb").exists()
