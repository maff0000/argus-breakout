"""Argus command-line entrypoint (PID 8.7). No business logic lives here."""

import typer

from argus import __version__
from argus.commands import adjust, events, ibkr, ingest, universe

app = typer.Typer(help="Argus-Breakout data pipeline", no_args_is_help=True)

app.add_typer(universe.app, name="universe")
app.add_typer(ingest.app, name="ingest")
app.add_typer(events.app, name="events")
app.add_typer(adjust.app, name="adjust")
app.add_typer(ibkr.app, name="ibkr")

# --- command module imports (append only; one line per Work Order) ---
import argus.commands.ingest_bootstrap  # noqa: F401, E402
import argus.commands.store_cmds  # noqa: F401, E402


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Argus-Breakout data pipeline."""

