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


@app.command("init-store")
def init_store() -> None:
    """Initialise the store (stub until WO-0002)."""
    typer.echo("store not implemented (WO-0002)", err=True)
    raise typer.Exit(2)
