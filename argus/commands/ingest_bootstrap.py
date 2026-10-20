"""`argus ingest bootstrap` (WO-0005; AMD-0002 command module)."""

from datetime import UTC, date, datetime

import typer

from argus.commands.ingest import app
from argus.data.ingest_bootstrap import bootstrap_history, current_cohort
from argus.data.providers.base import ProviderError
from argus.data.providers.bootstrap import YFinanceProvider
from argus.data.store import Store
from argus.settings import get_settings

# Exit rule (AMD-0012, AMD-0015 2B): exit 0 only when >= 98% of the CURRENT cohort succeeds.
# AC1a's 99% is the operator-check threshold, not this rule.
MIN_WRITTEN_PERCENT = 98


def meets_threshold(succeeded: int, failed: int) -> bool:
    """True when succeeded / (succeeded + failed) >= 98% (integer arithmetic, no float edge).

    AMD-0014 section 2E: callers pass written + skipped as `succeeded`; a skipped symbol is
    already complete, so only symbols in `failed` count against the threshold.
    """
    total = succeeded + failed
    return total == 0 or succeeded * 100 >= MIN_WRITTEN_PERCENT * total


def _percent(ok: int, bad: int) -> str:
    total = ok + bad
    return "n/a" if total == 0 else f"{100 * ok / total:.1f}%"


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
    cur = current_cohort(store, result.skipped)
    cur_skipped = len([x for x in result.skipped if x in cur])
    hist_skipped = len(result.skipped) - cur_skipped
    cur_ok = result.current_written + cur_skipped
    hist_ok = result.historical_written + hist_skipped
    typer.echo(
        f"symbols={result.n_symbols} rows={result.n_rows} "
        f"skipped={len(result.skipped)} failed={len(result.failed)}"
    )
    typer.echo(
        f"current: written={result.current_written} skipped={cur_skipped} "
        f"failed={len(result.current_failed)} "
        f"({_percent(cur_ok, len(result.current_failed))})"
    )
    typer.echo(
        f"historical: written={result.historical_written} skipped={hist_skipped} "
        f"unavailable={len(result.historical_unavailable)} "
        f"({_percent(hist_ok, len(result.historical_unavailable))})"
    )
    typer.echo("current failed: " + ",".join(result.current_failed))
    typer.echo("historical unavailable: " + ",".join(result.historical_unavailable))
    if result.failed:
        typer.echo("failed (current + historical): " + ",".join(result.failed))
    if not meets_threshold(cur_ok, len(result.current_failed)):
        raise typer.Exit(1)
