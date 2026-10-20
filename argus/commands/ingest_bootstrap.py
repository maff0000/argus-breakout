"""`argus ingest bootstrap` (WO-0005; AMD-0002 command module)."""

from datetime import UTC, date, datetime

import typer

from argus.commands.ingest import app
from argus.data.ingest_bootstrap import bootstrap_history
from argus.data.providers.base import ProviderError
from argus.data.providers.bootstrap import YFinanceProvider
from argus.data.store import Store
from argus.settings import get_settings

MIN_WRITTEN_PERCENT = 98  # AC1 / AMD-0012: exit 0 only when >= 98% of requested symbols succeed


def meets_threshold(succeeded: int, failed: int) -> bool:
    """True when succeeded / (succeeded + failed) >= 98% (integer arithmetic, no float edge).

    AMD-0014 section 2E: callers pass written + skipped as `succeeded`; a skipped symbol is
    already complete, so only symbols in `failed` count against the threshold.
    """
    total = succeeded + failed
    return total == 0 or succeeded * 100 >= MIN_WRITTEN_PERCENT * total


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
    if not meets_threshold(result.n_symbols + len(result.skipped), len(result.failed)):
        raise typer.Exit(1)
