"""`argus events refresh` (WO-0006; AMD-0002 command module)."""

from datetime import UTC, datetime
from typing import Annotated

import httpx
import typer

from argus.commands.events import app
from argus.data.providers.base import ProviderError
from argus.data.providers.fmp import FMPClient
from argus.data.store import Store
from argus.events.earnings import refresh_events
from argus.settings import ConfigError, get_settings

_HTTP_TIMEOUT = 30.0
_SOURCE = "events"


@app.command("refresh")
def refresh_cmd(
    days: Annotated[
        int, typer.Option("--days", min=1, max=366, help="Days ahead to cover (default 45).")
    ] = 45,
) -> None:
    """Refresh earnings and ex-dividend events for active symbols (next N days + trailing 10)."""
    today = datetime.now(UTC).date()
    try:
        settings = get_settings()
        settings.require("fmp_api_key")
    except ConfigError as exc:
        typer.echo(f"events refresh failed: missing configuration: {exc}", err=True)
        raise typer.Exit(1) from None
    store = Store(settings.argus_store_dir)
    store.init_schema()
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as http:
            fmp = FMPClient(settings.fmp_api_key, settings.fmp_daily_call_budget, store, http=http)
            report = refresh_events(store, fmp, today, days_ahead=days)
    except (ProviderError, ValueError, httpx.HTTPError) as exc:
        store.log_ingest(today, _SOURCE, 0, "failed", f"{type(exc).__name__}: {exc}"[:500])
        typer.echo(f"events refresh failed: {exc}", err=True)
        raise typer.Exit(1) from None
    status = "partial" if report.unavailable else "ok"
    detail = (
        "unavailable on this plan: " + ",".join(report.unavailable) if report.unavailable else ""
    )
    store.log_ingest(today, _SOURCE, report.n_earnings + report.n_exdiv, status, detail)
    typer.echo(f"earnings rows: {report.n_earnings}")
    typer.echo(
        f"time of day known for {report.n_earnings_with_time} of {report.n_earnings} earnings rows"
    )
    typer.echo(f"ex-dividend rows: {report.n_exdiv}")
    typer.echo(
        "symbols with upcoming earnings: "
        f"{report.n_symbols_with_upcoming_earnings} of {report.n_active_symbols} active"
    )
    typer.echo(f"fmp calls used: {report.calls_used}")
    for half in report.unavailable:
        typer.echo(f"UNAVAILABLE: {half} calendar not served on this plan; 0 rows for it")
