"""`argus universe refresh` (WO-0003; AMD-0002 command module)."""

from datetime import UTC, datetime
from typing import Annotated

import httpx
import typer

from argus.commands.universe import app
from argus.data.providers.base import ProviderError
from argus.data.store import Store
from argus.data.universe import MAX_BOUNDED_ROWS, SRC_DERIVED_BOUNDED, refresh
from argus.settings import ConfigError, get_settings

_HTTP_TIMEOUT = 30.0


@app.command("refresh")
def refresh_cmd(
    date_: Annotated[
        datetime | None,
        typer.Option(
            "--date", formats=["%Y-%m-%d"], help="As-of date (UTC, YYYY-MM-DD); default today."
        ),
    ] = None,
) -> None:
    """Populate symbols (GICS) and point-in-time S&P 500 membership."""
    settings = get_settings()
    as_of = date_.date() if date_ is not None else datetime.now(UTC).date()
    store = Store(settings.argus_store_dir)
    store.init_schema()
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as http:
            report = refresh(store, settings, http, as_of=as_of)
    except (ConfigError, ProviderError, ValueError, httpx.HTTPError) as exc:
        store.log_ingest(as_of, "universe", 0, "failed", f"{type(exc).__name__}: {exc}"[:500])
        typer.echo(f"universe refresh failed: {exc}", err=True)
        raise typer.Exit(1) from None
    n_bounded = report.rows_by_source.get(SRC_DERIVED_BOUNDED, 0)
    too_many_bounded = n_bounded > MAX_BOUNDED_ROWS
    healthy = report.n_missing_group == 0 and not too_many_bounded
    status = "ok" if healthy else "failed"
    detail = f"gap route {report.gap_route}; " + ",".join(report.sources_used)
    if report.n_missing_group:
        detail = f"{report.n_missing_group} symbols without industry group; {detail}"
    if too_many_bounded:
        detail = f"{n_bounded} bounded removals (max {MAX_BOUNDED_ROWS}); {detail}"
    store.log_ingest(as_of, "universe", report.membership_rows, status, detail[:500])
    typer.echo(f"symbols: {report.n_symbols}")
    typer.echo(f"members on {as_of.isoformat()}: {report.n_members_today}")
    typer.echo(f"current table symbols: {report.n_current_table}")
    typer.echo(f"current members without row: {report.current_members_without_row}")
    typer.echo(f"missing industry group: {report.n_missing_group}")
    typer.echo(f"membership rows: {report.membership_rows}")
    typer.echo(f"sources: {', '.join(report.sources_used)}")
    typer.echo(f"membership gap route: {report.gap_route}")
    typer.echo(
        "rows by source: "
        + ", ".join(f"{k}={v}" for k, v in sorted(report.rows_by_source.items()))
    )
    if too_many_bounded:
        typer.echo(
            f"STOP: {n_bounded} {SRC_DERIVED_BOUNDED} rows exceeds {MAX_BOUNDED_ROWS} (AC7)",
            err=True,
        )
    if report.n_missing_group or too_many_bounded:
        raise typer.Exit(1)
