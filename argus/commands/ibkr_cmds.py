"""`argus ibkr reconcile` and `argus ibkr iv` (WO-0008; AMD-0002 command module)."""

from datetime import date

import typer
import yaml

from argus.commands.ibkr import app
from argus.data.providers.base import ProviderError
from argus.data.providers.ibkr import IBAsyncClient, IBClient
from argus.data.reconcile import choose_sample, fetch_iv, reconcile_day
from argus.data.store import Store
from argus.data.validate import FLAG_JUMP_UNEXPLAINED
from argus.logging import configure_logging
from argus.settings import ConfigError, Settings, get_settings

# AMD-0019 3: only paper gateways are ever spoken to (7497 TWS paper, 4002 IB Gateway paper).
PAPER_PORTS = frozenset({7497, 4002})


def check_paper_port(port: int) -> None:
    """Raise ConfigError naming `port` unless it is a paper port."""
    if port not in PAPER_PORTS:
        raise ConfigError(
            f"ib_port {port} is not a paper port (allowed: {sorted(PAPER_PORTS)}); "
            "refusing to connect"
        )


def _make_client(settings: Settings) -> IBClient:
    return IBAsyncClient(settings.ib_host, settings.ib_port, settings.ib_client_id)


def _setup() -> tuple[Settings, Store]:
    """Settings checks run before any client exists, so a bad port never reaches a socket."""
    settings = get_settings()
    try:
        settings.require("ib_port")
        check_paper_port(settings.ib_port)
    except ConfigError as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(2) from exc
    configure_logging(settings.argus_log_level)
    return settings, Store(settings.argus_store_dir, settings.argus_config_dir)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        typer.echo(f"invalid --date: {value!r} (want YYYY-MM-DD)", err=True)
        raise typer.Exit(2) from exc


def _priority_symbols(store: Store, members: list[str], on: date) -> list[str]:
    """Members with a `jump_unexplained` flag on the previous session and no reconcile_log
    close comparison for that day yet (AMD-0019 2A). Previous session = latest `bars` date < on.
    """
    if not members:
        return []
    prev = store.read("SELECT max(date) AS d FROM bars WHERE date < ?", [on])["d"][0]
    if prev is None:
        return []
    flags = store.read_bar_flags(members, [FLAG_JUMP_UNEXPLAINED])
    flagged = sorted(set(flags.filter(flags["date"] == prev)["symbol"].to_list()))
    if not flagged:
        return []
    done = store.read(
        "SELECT DISTINCT symbol FROM reconcile_log "
        "WHERE date = ? AND field = 'close' AND symbol IN (SELECT unnest(?))",
        [prev, flagged],
    )["symbol"].to_list()
    return [s for s in flagged if s not in done]


def _iv_symbols(settings: Settings) -> list[str]:
    """Benchmarks plus sector ETFs from universe.yaml (13 symbols)."""
    path = settings.argus_config_dir / "universe.yaml"
    if not path.is_file():
        raise ConfigError("missing config file: universe.yaml (in ARGUS_CONFIG_DIR)")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = [*(cfg.get("benchmarks") or []), *(cfg.get("sector_etfs") or {}).values()]
    return list(dict.fromkeys(found))


@app.command("reconcile")
def reconcile_cmd(
    on: str = typer.Option(..., "--date", help="Trading day to reconcile (YYYY-MM-DD)."),
    sample: int = typer.Option(20, "--sample", min=1, help="Members to sample."),
) -> None:
    """Compare a rotating sample of bars with IBKR daily bars; log every comparison."""
    d = _parse_date(on)
    settings, store = _setup()
    members = store.members_on(d)
    chosen = choose_sample(members, d, sample, _priority_symbols(store, members, d))
    client = _make_client(settings)
    try:
        client.connect()
        report = reconcile_day(store, client, d, chosen)
    except ProviderError as exc:
        typer.echo(f"ibkr error: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        client.disconnect()
    typer.echo(
        f"symbols={report.n_symbols} fields={report.n_fields} breaches={report.n_breaches} "
        f"breach_rate={report.breach_rate:.4f}"
    )
    for row in report.rows.filter(report.rows["breach"]).iter_rows(named=True):
        typer.echo(
            f"breach: {row['symbol']} {row['date']} {row['field']} pct_diff={row['pct_diff']}"
        )


@app.command("iv")
def iv_cmd(
    on: str = typer.Option(..., "--date", help="Trading day (YYYY-MM-DD)."),
) -> None:
    """Store 30-day implied and historical volatility for the benchmark and sector ETFs."""
    d = _parse_date(on)
    settings, store = _setup()
    try:
        symbols = _iv_symbols(settings)
    except ConfigError as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(2) from exc
    client = _make_client(settings)
    try:
        client.connect()
        rows = fetch_iv(store, client, d, symbols)
    except ProviderError as exc:
        typer.echo(f"ibkr error: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        client.disconnect()
    typer.echo(f"symbols={len(symbols)} rows={rows}")
