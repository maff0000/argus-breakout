import os

import pytest
import structlog

from argus.settings import Settings, get_settings

_PREFIXES = ("ARGUS_", "POLYGON_", "FMP_", "IB_", "LLM_")


@pytest.fixture
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(_PREFIXES):
            monkeypatch.delenv(key)
    monkeypatch.setitem(Settings.model_config, "env_file", "/nonexistent/none.env")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_structlog():
    yield
    # configure_logging() binds a closed test stdout; reset so later tests can log.
    structlog.reset_defaults()
