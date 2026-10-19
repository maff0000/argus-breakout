"""`argus init-store` (WO-0002; AMD-0002 command module)."""

import typer

from argus.cli import app
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
    typer.echo(f"store ready: {len(tables)} tables")
    for name in tables:
        typer.echo(f"  {name}")
