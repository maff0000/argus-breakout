import json

from argus.logging import configure_logging


def test_json_and_redaction(clean_env, capsys):
    configure_logging("INFO")
    import structlog

    structlog.get_logger().info("call api_key=XYZ done", run_id="r1", step="s1")
    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert "XYZ" not in out
    assert "REDACTED" in record["event"]
    assert record["run_id"] == "r1"
    assert record["step"] == "s1"
    assert record["level"] == "info"
    assert record["ts"].endswith("Z")


def test_configured_secret_redacted(clean_env, capsys):
    clean_env.setenv("POLYGON_API_KEY", "topsecretvalue")
    configure_logging("INFO")
    import structlog

    structlog.get_logger().info("x", detail="topsecretvalue")
    out = capsys.readouterr().out
    assert "topsecretvalue" not in out
