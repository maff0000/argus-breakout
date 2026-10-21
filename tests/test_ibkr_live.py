"""Live smoke against the paper gateway (opt-in: `pytest -m live`). Skipped by default."""

from datetime import date, timedelta

import pytest

from argus.commands.ibkr_cmds import check_paper_port
from argus.data.providers.ibkr import IBAsyncClient
from argus.settings import get_settings


@pytest.mark.live
def test_connect_smoke():
    settings = get_settings()
    settings.require("ib_port")
    check_paper_port(settings.ib_port)
    client = IBAsyncClient(settings.ib_host, settings.ib_port, settings.ib_client_id)
    try:
        client.connect()
        df = client.daily_bars("SPY", date.today() - timedelta(days=1), 5, "TRADES")
        assert df.height > 0
    finally:
        client.disconnect()
