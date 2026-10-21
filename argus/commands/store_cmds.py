"""`argus init-store` (WO-0002) and `argus migrate-store` (WO-0013); AMD-0002 command module."""

import typer

from argus.cli import app
from argus.data.schema import SCHEMA_VERSION
from argus.data.store import Store
from argus.settings import get_settings


@app.command("init-store")
def init_store() -> None:
    """Create the store (idempotent) and list its tables."""
    store = Store(get_settings().argus_store_dir)
    store.init_schema()
    tables = store.read(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = ? ORDER BY table_name",
        ["main"],
    )["table_name"].to_list()
    if store.repaired_from is not None:
        typer.echo(f"store relocated: repaired views (was {store.repaired_from})")
    typer.echo(f"store ready: {len(tables)} tables")
    typer.echo(f"store_dir: {store.recorded_store_dir()}")
    for name in tables:
        typer.echo(f"  {name}")


@app.command("migrate-store")
def migrate_store() -> None:
    """Bring the store to the current schema in place (idempotent, from stored data only).

    Rebuilds `dividends` with a per-source `basis`, widens float32 price columns of `bars` /
    `etf_bars` to float64, records the schema version; prints row counts before and after per
    table. `bars_raw` is never written. Run it on a COPY of the store first."""
    store = Store(get_settings().argus_store_dir)
    rows = store.migrate()
    if store.repaired_from is not None:
        typer.echo(f"store relocated: repaired views (was {store.repaired_from})")
    typer.echo(f"store migrated to schema {SCHEMA_VERSION}: table, rows before, rows after")
    for name, before, after in rows:
        typer.echo(f"  {name}: {before} -> {after}")
