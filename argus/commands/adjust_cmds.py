"""`argus adjust materialise` (WO-0007; AMD-0002 command module)."""

import typer

from argus.commands.adjust import app
from argus.data.adjust import materialise
from argus.data.store import Store
from argus.data.tickers import is_valid
from argus.logging import configure_logging
from argus.settings import get_settings

_SHOWN = 10


@app.command("materialise")
def materialise_cmd(
    symbols: str | None = typer.Option(
        None, "--symbols", help="Comma-separated symbols (default: every symbol in bars_raw)."
    ),
) -> None:
    """Build bars and etf_bars from bars_raw, splits and dividends; a re-run is a no-op."""
    wanted = None
    if symbols is not None:
        wanted = [s.strip() for s in symbols.split(",") if s.strip()]
        bad = [s for s in wanted if not is_valid(s)]
        if not wanted or bad:
            typer.echo(f"invalid --symbols: {bad or symbols!r}", err=True)
            raise typer.Exit(2)
    settings = get_settings()
    configure_logging(settings.argus_log_level)
    store = Store(settings.argus_store_dir, settings.argus_config_dir)
    report = materialise(store, wanted)
    typer.echo(
        f"symbols={report.n_symbols} rows={report.n_rows} readjusted={report.n_readjusted} "
        f"warnings={len(report.warnings)}"
    )
    typer.echo(
        f"{report.n_days_quarantined_skipped} quarantined days not published, "
        f"{report.n_symbol_days_flag_excluded} flagged symbol-days excluded"
    )
    for line in report.warnings[:_SHOWN]:
        typer.echo(f"warning: {line}", err=True)
    if len(report.warnings) > _SHOWN:
        typer.echo(f"... {len(report.warnings) - _SHOWN} more (see ingest_log.detail)", err=True)
