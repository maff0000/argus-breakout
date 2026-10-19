"""Universe and point-in-time S&P 500 membership (WO-0003; PID 8.8, DESIGN 3.1/3.3, ADR-0005).

`refresh()` is free of CLI concerns so that the nightly orchestration can call it.
Membership intervals are closed on both ends (AMD-0011): a symbol removed on
date D has `end_date` = the last exchange trading day before D.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import httpx
import polars as pl
import structlog
import yaml

from argus.data.providers.base import ProviderError
from argus.data.providers.fmp import FMPClient
from argus.data.store import Store
from argus.data.tickers import is_valid, normalize
from argus.settings import ConfigError, Settings

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HANSHOF_URL = (
    "https://raw.githubusercontent.com/hanshof/sp500_constituents/main/"
    "sp_500_historical_components.csv"
)
_WIKI_TIMEOUT = 20.0
_HTTP_TIMEOUT = 30.0
_USER_AGENT = "argus-breakout/0.1 (universe refresh)"
_MIN_WIKI_ROWS = 490
_N_SECTORS = 11
MEMBERSHIP_START = date(2015, 1, 1)
# Keeps one refresh well inside the 60-FMP-call acceptance bound (AC6):
# 1 (historical) + 1 (current) + at most this many profile lookups.
MAX_PROFILE_FALLBACKS = 50
ETF_LABEL = "ETF"

log = structlog.get_logger()

MEMBERSHIP_SCHEMA = {
    "symbol": pl.String,
    "start_date": pl.Date,
    "end_date": pl.Date,
    "source": pl.String,
}


# ---------------------------------------------------------------------- trading days
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = (h + el - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _observed(d: date, saturday_to_friday: bool = True) -> date | None:
    if d.weekday() == 5:
        return d - timedelta(days=1) if saturday_to_friday else None
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


# NYSE closures that are not rule-based (national days of mourning).
_SPECIAL_CLOSURES = frozenset({date(2018, 12, 5), date(2025, 1, 9)})


@cache
def _nyse_holidays(year: int) -> frozenset[date]:
    days: list[date | None] = [
        _observed(date(year, 1, 1), saturday_to_friday=False),  # New Year's Day
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    ]
    if year >= 2022:
        days.append(_observed(date(year, 6, 19)))  # Juneteenth
    out = {d for d in days if d is not None}
    out |= {d for d in _SPECIAL_CLOSURES if d.year == year}
    return frozenset(out)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _nyse_holidays(d.year)


def previous_trading_day(d: date) -> date:
    """The latest trading day strictly before `d`."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    """The earliest trading day strictly after `d`."""
    cur = d + timedelta(days=1)
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


# ---------------------------------------------------------------------- wikipedia
class _ConstituentsParser(HTMLParser):
    """Collects the cell text of every row of `<table id="constituents">`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._depth:
                self._depth += 1
            elif dict(attrs).get("id") == "constituents":
                self._depth = 1
        elif self._depth == 1:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th") and self._row is not None:
                self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._depth:
            self._depth -= 1
        elif self._depth == 1:
            if tag in ("td", "th") and self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self.rows.append(self._row)
                self._row = None

    def handle_data(self, data: str) -> None:
        if self._depth == 1 and self._cell is not None:
            self._cell.append(data)


def parse_wikipedia_constituents(html_text: str) -> pl.DataFrame:
    parser = _ConstituentsParser()
    parser.feed(html_text)
    if not parser.rows:
        raise ValueError("wikipedia: constituents table not found")
    header = [h.lower() for h in parser.rows[0]]

    def col(*needles: str) -> int:
        for i, h in enumerate(header):
            if all(n in h for n in needles):
                return i
        raise ValueError(f"wikipedia: column {' '.join(needles)!r} not found")

    i_sym, i_name = col("symbol"), col("security")
    i_sector, i_sub = col("gics", "sector"), col("gics", "sub")
    out: dict[str, dict[str, str]] = {}
    for row in parser.rows[1:]:
        if len(row) <= max(i_sym, i_name, i_sector, i_sub):
            continue
        sym = normalize(row[i_sym].strip(), "wikipedia")
        out[sym] = {
            "symbol": sym,
            "name": row[i_name],
            "gics_sector": row[i_sector],
            "gics_sub_industry": row[i_sub],
        }
    df = pl.DataFrame(
        list(out.values()),
        schema={
            "symbol": pl.String,
            "name": pl.String,
            "gics_sector": pl.String,
            "gics_sub_industry": pl.String,
        },
    )
    if df.height < _MIN_WIKI_ROWS:
        raise ValueError(f"wikipedia: only {df.height} rows (need >= {_MIN_WIKI_ROWS})")
    n_sectors = df["gics_sector"].n_unique()
    if n_sectors != _N_SECTORS:
        raise ValueError(f"wikipedia: {n_sectors} sectors (need {_N_SECTORS})")
    return df


def fetch_wikipedia_constituents(http: httpx.Client) -> pl.DataFrame:
    """One GET of the fixed URL; returns [symbol, name, gics_sector, gics_sub_industry]."""
    resp = http.get(
        WIKIPEDIA_URL,
        headers={"User-Agent": _USER_AGENT},
        timeout=_WIKI_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_wikipedia_constituents(resp.text)


# ---------------------------------------------------------------------- hanshof
def _hanshof_symbol(raw: str) -> str:
    raw = raw.strip()
    if "(" in raw:  # e.g. "RVTY (Previously PKI)": keep the leading ticker
        raw = raw.split("(", 1)[0].strip()
    # hanshof writes share classes with a hyphen (BF-B), which is the yfinance form.
    return normalize(raw, "yfinance")


def load_hanshof_csv(
    path_or_url: str | Path, http: httpx.Client | None = None
) -> pl.DataFrame:
    """Snapshots as [date, symbols:list[str]], ascending by date, canonical tickers."""
    text_in = str(path_or_url)
    if text_in.startswith(("https://", "http://")):
        client = http if http is not None else httpx.Client(timeout=_HTTP_TIMEOUT)
        resp = client.get(text_in, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text
    else:
        text = Path(path_or_url).read_text(encoding="utf-8")
    rows = []
    for rec in csv.DictReader(io.StringIO(text)):
        syms = sorted({_hanshof_symbol(s) for s in rec["tickers"].split(",") if s.strip()})
        rows.append({"date": date.fromisoformat(rec["date"].strip()), "symbols": syms})
    if not rows:
        raise ValueError("hanshof: no rows")
    return pl.DataFrame(rows, schema={"date": pl.Date, "symbols": pl.List(pl.String)}).sort(
        "date"
    )


# ---------------------------------------------------------------------- membership
def build_membership(
    hanshof: pl.DataFrame, fmp_changes: pl.DataFrame, start: date = MEMBERSHIP_START
) -> pl.DataFrame:
    """Point-in-time intervals [symbol, start_date, end_date, source].

    hanshof snapshots are diffed in order (primary). FMP changes dated strictly after
    hanshof's last snapshot extend the result. A symbol removed on D is not a member on D:
    its `end_date` is the last trading day before D (closed interval, AMD-0011). Contiguous
    or overlapping intervals of one symbol are merged; `end_date` NULL means current.
    """
    snapshots = sorted(
        ((r["date"], set(r["symbols"])) for r in hanshof.iter_rows(named=True)),
        key=lambda t: t[0],
    )
    if not snapshots:
        raise ValueError("hanshof has no snapshots")
    last_hanshof = snapshots[-1][0]

    open_: dict[str, tuple[date, str]] = {}
    closed: list[tuple[str, date, date | None, str]] = []

    prev: set[str] = set()
    for d, members in snapshots:
        for sym in sorted(members - prev):
            open_[sym] = (d, "hanshof")
        for sym in sorted(prev - members):
            began, src = open_.pop(sym)
            closed.append((sym, began, previous_trading_day(d), src))
        prev = members

    changes = fmp_changes.filter(pl.col("date") > last_hanshof).sort(["date", "action"])
    for rec in changes.iter_rows(named=True):
        sym, d, action = rec["symbol"], rec["date"], rec["action"]
        if action == "added":
            if sym not in open_:
                open_[sym] = (d, "fmp")
        elif action == "removed":
            if sym in open_:
                began, src = open_.pop(sym)
                src = "hanshof+fmp" if src == "hanshof" else src
                closed.append((sym, began, previous_trading_day(d), src))
        else:
            raise ValueError(f"unknown change action: {action!r}")
    closed.extend((sym, began, None, src) for sym, (began, src) in open_.items())

    by_symbol: dict[str, list[tuple[date, date | None, str]]] = {}
    for sym, began, end, src in closed:
        if end is not None and end < start:
            continue
        by_symbol.setdefault(sym, []).append((max(began, start), end, src))

    out: list[dict] = []
    for sym in sorted(by_symbol):
        merged: list[list] = []
        for began, end, src in sorted(by_symbol[sym], key=lambda t: t[0]):
            if merged:
                m_end = merged[-1][1]
                if m_end is None or began <= next_trading_day(m_end):
                    merged[-1][1] = None if (m_end is None or end is None) else max(m_end, end)
                    continue
            merged.append([began, end, src])
        out.extend(
            {"symbol": sym, "start_date": b, "end_date": e, "source": s} for b, e, s in merged
        )
    return pl.DataFrame(out, schema=MEMBERSHIP_SCHEMA)


# ---------------------------------------------------------------------- GICS
def map_industry_group(sub_industry: str | None, gics_yaml: dict) -> str:
    """GICS sub-industry name -> industry group; raises ValueError on unknown."""
    name = (sub_industry or "").strip()
    try:
        return gics_yaml["sub_industry_to_group"][name]
    except KeyError:
        raise ValueError(f"unknown GICS sub-industry: {name!r}") from None


# ---------------------------------------------------------------------- config
def _load_yaml(config_dir: Path, name: str) -> dict:
    path = Path(config_dir) / name
    if not path.is_file():
        raise ConfigError(f"missing config file: {name} (in ARGUS_CONFIG_DIR)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"invalid config file: {name}")
    return data


def configured_etfs(universe_yaml: dict) -> list[str]:
    """Benchmarks, sector ETFs and ratio-pair legs, de-duplicated, validated."""
    found: list[str] = []
    found.extend(universe_yaml.get("benchmarks") or [])
    found.extend((universe_yaml.get("sector_etfs") or {}).values())
    for pair in universe_yaml.get("ratio_pairs") or []:
        found.extend(pair)
    out: list[str] = []
    for sym in found:
        if not is_valid(sym):
            raise ConfigError(f"invalid ETF symbol in universe.yaml: {sym!r}")
        if sym not in out:
            out.append(sym)
    return out


# ---------------------------------------------------------------------- refresh
@dataclass
class UniverseReport:
    n_symbols: int
    n_members_today: int
    n_missing_group: int
    membership_rows: int
    sources_used: list[str]


def _resolve_current(
    wiki: pl.DataFrame | None, fmp_current: pl.DataFrame | None
) -> list[dict]:
    """Merge the two current-constituent sources; Wikipedia wins, FMP fills what it lacks."""
    merged: dict[str, dict] = {}
    if fmp_current is not None:
        for r in fmp_current.iter_rows(named=True):
            merged[r["symbol"]] = {
                "symbol": r["symbol"],
                "name": r["name"],
                "sector": r["sector"],
                "sub_industry": r["sub_industry"],
            }
    if wiki is not None:
        for r in wiki.iter_rows(named=True):
            merged[r["symbol"]] = {
                "symbol": r["symbol"],
                "name": r["name"],
                "sector": r["gics_sector"],
                "sub_industry": r["gics_sub_industry"],
            }
    return [merged[k] for k in sorted(merged)]


def refresh(
    store: Store, settings: Settings, http: httpx.Client, as_of: date | None = None
) -> UniverseReport:
    """Populate `symbols` and rebuild `membership`; returns a UniverseReport."""
    settings.require("fmp_api_key")
    as_of = as_of or datetime.now(UTC).date()
    gics = _load_yaml(settings.argus_config_dir, "gics.yaml")
    universe_cfg = _load_yaml(settings.argus_config_dir, "universe.yaml")
    etfs = configured_etfs(universe_cfg)
    fmp = FMPClient(settings.fmp_api_key, settings.fmp_daily_call_budget, store, http=http)
    sources: list[str] = []

    # --- current constituents with GICS classification
    wiki: pl.DataFrame | None = None
    try:
        wiki = fetch_wikipedia_constituents(http)
        sources.append("wikipedia")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("wikipedia_unavailable", error=type(exc).__name__)
    fmp_current: pl.DataFrame | None = None
    try:
        fmp_current = fmp.current_sp500()
        sources.append("fmp:sp500-constituent")
    except ProviderError as exc:
        if wiki is None:
            raise
        log.warning("fmp_current_unavailable", error=str(exc))
    if wiki is None and fmp_current is None:
        raise ProviderError("no source of current S&P 500 constituents")
    current = _resolve_current(wiki, fmp_current)

    # --- historical membership
    hanshof = load_hanshof_csv(HANSHOF_URL, http)
    sources.append("hanshof")
    changes = fmp.historical_sp500_changes().filter(pl.col("date") <= as_of)
    sources.append("fmp:historical-sp500-constituent")
    hanshof = hanshof.filter(pl.col("date") <= as_of)
    membership = build_membership(hanshof, changes, start=MEMBERSHIP_START)
    bad = [s for s in membership["symbol"].unique().to_list() if not is_valid(s)]
    if bad:
        raise ValueError(f"non-canonical membership symbols: {bad[:5]}")

    # --- industry group for every current member (no silent defaults)
    valid_sectors = set(gics["sectors"])
    group_sector: dict[str, str] = gics["industry_groups"]
    rows: list[dict] = []
    missing: list[str] = []
    fallbacks = 0
    for rec in current:
        sym = rec["symbol"]
        group: str | None = None
        try:
            group = map_industry_group(rec["sub_industry"], gics)
        except ValueError:
            if fallbacks < MAX_PROFILE_FALLBACKS:
                fallbacks += 1
                try:
                    prof = fmp.profile(sym)
                    group = map_industry_group(prof.get("industry"), gics)
                    if "fmp:profile" not in sources:
                        sources.append("fmp:profile")
                except (ProviderError, ValueError):
                    group = None
        if group is None:
            missing.append(sym)
        sector = group_sector[group] if group else rec["sector"]
        if sector not in valid_sectors:
            sector = None
        rows.append(
            {
                "symbol": sym,
                "name": rec["name"],
                "gics_sector": sector,
                "gics_industry_group": group,
                "active": True,
            }
        )
    if missing:
        log.warning("missing_industry_group", count=len(missing), symbols=missing[:20])

    etf_rows = [
        {
            "symbol": e,
            "name": None,
            "gics_sector": ETF_LABEL,
            "gics_industry_group": ETF_LABEL,
            "active": True,
        }
        for e in etfs
        if e not in {r["symbol"] for r in rows}
    ]
    symbols_df = pl.DataFrame(
        rows + etf_rows,
        schema={
            "symbol": pl.String,
            "name": pl.String,
            "gics_sector": pl.String,
            "gics_industry_group": pl.String,
            "active": pl.Boolean,
        },
    )
    store.init_schema()
    store.upsert("symbols", symbols_df, ["symbol"])
    _deactivate_departed(store, keep=set(symbols_df["symbol"].to_list()))
    _replace_membership(store, membership)

    n_members_today = len(store.members_on(as_of))
    n_symbols = store.read("SELECT count(*) AS n FROM symbols")["n"][0]
    return UniverseReport(
        n_symbols=int(n_symbols),
        n_members_today=n_members_today,
        n_missing_group=len(missing),
        membership_rows=membership.height,
        sources_used=sources,
    )


def _deactivate_departed(store: Store, keep: set[str]) -> None:
    """Mark previously stored symbols that are no longer current members/ETFs inactive."""
    stored = store.read("SELECT symbol FROM symbols WHERE active")["symbol"].to_list()
    gone = [s for s in stored if s not in keep]
    if gone:
        store.upsert(
            "symbols",
            pl.DataFrame({"symbol": gone, "active": [False] * len(gone)}),
            ["symbol"],
        )


def _replace_membership(store: Store, membership: pl.DataFrame) -> None:
    """Full rebuild in one transaction (the table is derived entirely from the sources)."""
    con = store.connect()
    try:
        con.register("incoming", membership.to_arrow())
        con.execute("BEGIN")
        try:
            con.execute("DELETE FROM membership")
            con.execute(
                "INSERT INTO membership SELECT symbol, start_date, end_date, source FROM incoming"
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.unregister("incoming")
    finally:
        con.close()
