"""`argus diagnose dividends` and `diagnose renames` (WO-0015; AMD-0002 command module).

Both are READ-ONLY: the store is opened read-only (a relocated store raises, CI-5) and nothing
is written to the store or to config. `diagnose renames` is wholly offline; `diagnose dividends`
touches the network only with --raw (exactly one Polygon call).
"""

from datetime import date

import duckdb
import polars as pl
import typer

from argus.commands.diagnose import app
from argus.data.providers.base import ProviderError
from argus.data.providers.polygon import PolygonClient
from argus.data.store import Store, StoreRelocatedError
from argus.data.tickers import is_valid
from argus.diagnostics.dividends import same_date_dividend_report
from argus.diagnostics.renames import (
    DEFAULT_GAP_DAYS,
    severed_current_members,
    undeclared_rename_candidates,
)
from argus.logging import configure_logging
from argus.settings import ConfigError, get_settings

_STORE_ERRORS = (StoreRelocatedError, duckdb.Error)


def _iso(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        typer.echo(f"invalid ISO date: {value!r}", err=True)
        raise typer.Exit(2) from None


def _echo_frame(df: pl.DataFrame) -> None:
    typer.echo("\t".join(df.columns))
    for row in df.iter_rows():
        typer.echo("\t".join("" if v is None else str(v) for v in row))


@app.command("dividends")
def dividends(
    symbol: str | None = typer.Option(None, "--symbol", help="Canonical symbol, e.g. PGR."),
    day: str | None = typer.Option(None, "--date", help="Ex-dividend date (ISO)."),
    raw: bool = typer.Option(
        False, "--raw", help="Also fetch the raw Polygon payload (one call; needs the API key)."
    ),
) -> None:
    """Report the >2x Polygon/yfinance dividend disagreements, or one (symbol, date)."""
    if (symbol is None) != (day is None):
        typer.echo("give both --symbol and --date, or neither", err=True)
        raise typer.Exit(2)
    if raw and symbol is None:
        typer.echo("--raw needs --symbol and --date", err=True)
        raise typer.Exit(2)
    if symbol is not None and not is_valid(symbol):
        typer.echo(f"invalid --symbol: {symbol!r}", err=True)
        raise typer.Exit(2)
    on_date = _iso(day) if day is not None else None
    settings = get_settings()
    configure_logging(settings.argus_log_level)
    client = None
    if raw:
        try:
            settings.require("polygon_api_key")
        except ConfigError as exc:
            typer.echo(f"missing configuration: {exc}", err=True)
            raise typer.Exit(2) from None
        assert settings.polygon_api_key is not None  # noqa: S101 - narrowed by require()
        client = PolygonClient(settings.polygon_api_key)
    store = Store(settings.argus_store_dir, settings.argus_config_dir)
    try:
        report = same_date_dividend_report(store, client, symbol, on_date)
    except _STORE_ERRORS as exc:
        typer.echo(f"store error: {exc}", err=True)
        raise typer.Exit(1) from None
    except ProviderError as exc:
        typer.echo(f"failed: {exc}", err=True)
        raise typer.Exit(1) from None
    finally:
        if client is not None:
            client.close()
    typer.echo(f"rows={report.height}")
    _echo_frame(report)


@app.command("renames")
def renames(
    gap_days: int = typer.Option(
        DEFAULT_GAP_DAYS, "--gap-days", min=0, help="Max trading days between two intervals."
    ),
) -> None:
    """Ranked candidates for undeclared ticker renames, for operator review. Writes nothing."""
    settings = get_settings()
    configure_logging(settings.argus_log_level)
    store = Store(settings.argus_store_dir, settings.argus_config_dir)
    try:
        severed = severed_current_members(store)
        candidates = undeclared_rename_candidates(store, gap_days)
    except _STORE_ERRORS as exc:
        typer.echo(f"store error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"undeclared rename candidates: {candidates.height} (operator review only)")
    _echo_frame(candidates)
    typer.echo(f"current members severed (membership starts after first bar): {severed.height}")
    _echo_frame(severed)
