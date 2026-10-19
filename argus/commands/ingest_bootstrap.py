"""`argus ingest bootstrap` (WO-0005; AMD-0002 command module)."""

from datetime import UTC, date, datetime

import typer

from argus.commands.ingest import app
from argus.data.ingest_bootstrap import bootstrap_history
from argus.data.providers.base import ProviderError
from argus.data.providers.bootstrap import YFinanceProvider
from argus.data.store import Store
from argus.settings import get_settings

MAX_FAILED_FRACTION = 0.02  # AC1: at least 98% of symbols must load


def _parse_date(value: str, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option} must be an ISO date (YYYY-MM-DD)") from exc


@app.command("bootstrap")
def bootstrap(
    start: str = typer.Option(..., "--start", help="First date, YYYY-MM-DD."),
    end: str | None = typer.Option(None, "--end", help="Last date (default: today UTC)."),
    symbols: str | None = typer.Option(None, "--symbols", help="Comma-separated symbols."),
) -> None:
    """Load multi-year daily history from yfinance (resumable, one-off)."""
    start_d = _parse_date(start, "--start")
    end_d = _parse_date(end, "--end") if end else datetime.now(UTC).date()
    wanted = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    store = Store(get_settings().argus_store_dir)
    try:
        result = bootstrap_history(store, YFinanceProvider(), start_d, end_d, wanted)
    except (ProviderError, ValueError) as exc:
        typer.echo(f"bootstrap failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"symbols={result.n_symbols} rows={result.n_rows} "
        f"skipped={len(result.skipped)} failed={len(result.failed)}"
    )
    if result.failed:
        typer.echo("failed: " + ",".join(result.failed))
    total = result.n_symbols + len(result.failed)
    if total and len(result.failed) / total > MAX_FAILED_FRACTION:
        raise typer.Exit(1)
