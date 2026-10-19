"""`argus ingest polygon` and `argus ingest polygon-actions` (WO-0004; AMD-0002 module)."""

from datetime import date

import typer

from argus.commands.ingest import app
from argus.data.ingest_polygon import backfill_polygon, ingest_polygon_actions, ingest_polygon_day
from argus.data.providers.base import ProviderError
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store
from argus.logging import configure_logging
from argus.settings import ConfigError, get_settings


def _client_and_store() -> tuple[PolygonClient, Store]:
    settings = get_settings()
    configure_logging(settings.argus_log_level)
    try:
        settings.require("polygon_api_key")
    except ConfigError as exc:
        typer.echo(f"missing configuration: {exc}", err=True)
        raise typer.Exit(2) from None
    assert settings.polygon_api_key is not None  # noqa: S101 - narrowed by require()
    return PolygonClient(settings.polygon_api_key), Store(settings.argus_store_dir)


def _iso(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        typer.echo(f"invalid ISO date: {value!r}", err=True)
        raise typer.Exit(2) from None


@app.command("polygon")
def polygon(
    day: str | None = typer.Option(None, "--date", help="Ingest one day (ISO date)."),
    backfill: tuple[str, str] | None = typer.Option(
        None, "--backfill", help="START END (ISO dates); resumable."
    ),
) -> None:
    """Ingest Polygon grouped-daily bars: --date D or --backfill START END."""
    if (day is None) == (backfill is None):
        typer.echo("give exactly one of --date or --backfill", err=True)
        raise typer.Exit(2)
    client, store = _client_and_store()
    try:
        if day is not None:
            results = [ingest_polygon_day(store, client, _iso(day))]
        else:
            start, end = _iso(backfill[0]), _iso(backfill[1])
            if start > end:
                typer.echo("backfill START must not be after END", err=True)
                raise typer.Exit(2)
            results = backfill_polygon(store, client, start, end)
    finally:
        client.close()
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    rows = sum(r.rows for r in results)
    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to do"
    typer.echo(f"days={len(results)} rows={rows} {summary}")
    for r in results:
        if r.status in ("rejected", "failed") and day is not None:
            typer.echo(f"{r.status}: {r.detail}", err=True)
    if counts.get("failed") or counts.get("rejected"):
        raise typer.Exit(1)


@app.command("polygon-actions")
def polygon_actions(
    since: str = typer.Option(..., "--since", help="Earliest execution/ex-dividend date (ISO)."),
) -> None:
    """Ingest Polygon splits and dividends into adjustments."""
    since_d = _iso(since)
    client, store = _client_and_store()
    try:
        n = ingest_polygon_actions(store, client, since_d)
    except ProviderError as exc:
        typer.echo(f"failed: {exc}", err=True)
        raise typer.Exit(1) from None
    finally:
        client.close()
    typer.echo(f"adjustments upserted: {n}")
