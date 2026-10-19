from typer.testing import CliRunner

from argus.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init_store_stub_exits_2():
    result = runner.invoke(app, ["init-store"])
    assert result.exit_code == 2
