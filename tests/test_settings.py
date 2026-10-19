from pathlib import Path

import pytest

from argus.settings import ConfigError, Settings


def test_defaults_without_env(clean_env):
    s = Settings()
    assert s.argus_store_dir == Path("store")
    assert s.argus_out_dir == Path("out")
    assert s.argus_config_dir == Path("config")
    assert s.argus_log_level == "INFO"
    assert s.polygon_api_key is None
    assert s.fmp_api_key is None
    assert s.fmp_daily_call_budget == 200
    assert s.ib_host == "127.0.0.1"
    assert s.ib_port is None
    assert s.ib_client_id == 11
    assert s.ib_client_id_write == 12
    assert s.llm_base_url is None


def test_require_lists_all_missing(clean_env):
    s = Settings()
    with pytest.raises(ConfigError) as exc:
        s.require("polygon_api_key", "ib_port")
    assert "polygon_api_key" in str(exc.value)
    assert "ib_port" in str(exc.value)


def test_require_passes_when_set(clean_env):
    Settings(polygon_api_key="abc", ib_port=1).require("polygon_api_key", "ib_port")


def test_secret_not_in_repr(clean_env):
    s = Settings(polygon_api_key="abc")
    assert "abc" not in repr(s)
    assert "abc" not in str(s)


def test_config_dir_default_and_override(clean_env):
    assert Settings().argus_config_dir == Path("config")
    clean_env.setenv("ARGUS_CONFIG_DIR", "elsewhere")
    assert Settings().argus_config_dir == Path("elsewhere")
