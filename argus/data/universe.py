"""Universe and point-in-time S&P 500 membership (WO-0003; PID 8.8, DESIGN 3.1/3.3, ADR-0005).

`refresh()` is free of CLI concerns so that the nightly orchestration can call it.
Membership intervals are closed on both ends (AMD-0011): a symbol removed on
date D has `end_date` = the last exchange trading day before D.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import httpx
import polars as pl
import structlog
import yaml

from argus.data.providers.base import ProviderError
from argus.data.providers.fmp import FMPClient, ProviderUnavailable
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
# AC7 (AMD-0013): more bounded-removal rows than this is a malfunction, not turnover.
MAX_BOUNDED_ROWS = 40
SRC_HANSHOF = "hanshof"
SRC_FMP = "fmp"
SRC_WIKI_CHANGES = "wikipedia-changes"
SRC_DERIVED_EXACT = "wikipedia-derived-exact"
SRC_DERIVED_BOUNDED = "wikipedia-derived-bounded"
SRC_RENAME_MAPPED = "rename-mapped"
SRC_RENAME_BOUNDED = "rename-bounded"
ROUTE_FMP = "fmp"
ROUTE_WIKI_CHANGES = "wikipedia-changes"
ROUTE_DERIVED = "wikipedia-derived"
ROUTE_NONE = "none"

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


_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_LONG_DATE = re.compile(r"([A-Z][a-z]+)\.? (\d{1,2}), (\d{4})")


def _parse_wiki_date(text: str | None) -> date | None:
    """A date cell ('2025-09-22' or 'September 22, 2025', footnotes tolerated); else None."""
    raw = (text or "").strip()
    if m := _ISO_DATE.search(raw):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if m := _LONG_DATE.search(raw):
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(f"{m[1]} {m[2]}, {m[3]}", fmt).date()
            except ValueError:
                continue
    return None


class _TablesParser(HTMLParser):
    """Rows of every top-level table that is not the constituents table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._skip = False
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._depth:
                self._depth += 1
            else:
                self._depth = 1
                self._skip = dict(attrs).get("id") == "constituents"
                self._rows = []
        elif self._depth == 1 and not self._skip:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th") and self._row is not None:
                self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._depth:
            self._depth -= 1
            if self._depth == 0 and not self._skip and self._rows:
                self.tables.append(self._rows)
        elif self._depth == 1 and not self._skip:
            if tag in ("td", "th") and self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self._rows.append(self._row)
                self._row = None

    def handle_data(self, data: str) -> None:
        if self._depth == 1 and not self._skip and self._cell is not None:
            self._cell.append(data)


CHANGES_SCHEMA = {
    "date": pl.Date,
    "symbol": pl.String,
    "action": pl.String,
    "reason": pl.String,
}


def parse_wikipedia_changes(html_text: str) -> pl.DataFrame | None:
    """Route (b): the index changes table on the constituents page, or None if absent.

    A changes table is a table other than `constituents` whose header rows contain a
    "Date" column and both an "Added" and a "Removed" column. Data rows are those whose
    first cell is a date; the layout is Date | Added ticker | Added security |
    Removed ticker | Removed security | Reason. Returns [date, symbol, action, reason].
    """
    parser = _TablesParser()
    parser.feed(html_text)
    for rows in parser.tables:
        head = " ".join(" ".join(r) for r in rows[:2]).lower()
        if not ("date" in head and "added" in head and "removed" in head):
            continue
        out: list[dict] = []
        for row in rows:
            when = _parse_wiki_date(row[0]) if row else None
            if when is None or len(row) < 5:
                continue
            reason = row[5] if len(row) > 5 else ""
            for idx, action in ((1, "added"), (3, "removed")):
                raw = row[idx].strip()
                if not raw:
                    continue
                try:
                    sym = normalize(raw, "wikipedia")
                except ValueError:
                    continue
                out.append({"date": when, "symbol": sym, "action": action, "reason": reason})
        if out:
            return pl.DataFrame(out, schema=CHANGES_SCHEMA)
    return None


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
    try:
        i_added: int | None = col("date", "added")
    except ValueError:
        i_added = None  # column absent: every date_added is null
    out: dict[str, dict] = {}
    for row in parser.rows[1:]:
        if len(row) <= max(i_sym, i_name, i_sector, i_sub):
            continue
        sym = normalize(row[i_sym].strip(), "wikipedia")
        out[sym] = {
            "symbol": sym,
            "name": row[i_name],
            "gics_sector": row[i_sector],
            "gics_sub_industry": row[i_sub],
            "date_added": (
                _parse_wiki_date(row[i_added])
                if i_added is not None and i_added < len(row)
                else None
            ),
        }
    df = pl.DataFrame(
        list(out.values()),
        schema={
            "symbol": pl.String,
            "name": pl.String,
            "gics_sector": pl.String,
            "gics_sub_industry": pl.String,
            "date_added": pl.Date,
        },
    )
    if df.height < _MIN_WIKI_ROWS:
        raise ValueError(f"wikipedia: only {df.height} rows (need >= {_MIN_WIKI_ROWS})")
    n_sectors = df["gics_sector"].n_unique()
    if n_sectors != _N_SECTORS:
        raise ValueError(f"wikipedia: {n_sectors} sectors (need {_N_SECTORS})")
    return df


def fetch_wikipedia(http: httpx.Client) -> tuple[pl.DataFrame, pl.DataFrame | None]:
    """One GET of the fixed URL; (constituents, changes table or None)."""
    resp = http.get(
        WIKIPEDIA_URL,
        headers={"User-Agent": _USER_AGENT},
        timeout=_WIKI_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_wikipedia_constituents(resp.text), parse_wikipedia_changes(resp.text)


def fetch_wikipedia_constituents(http: httpx.Client) -> pl.DataFrame:
    """One GET of the fixed URL; [symbol, name, gics_sector, gics_sub_industry, date_added]."""
    return fetch_wikipedia(http)[0]


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


# ---------------------------------------------------------------------- renames
@dataclass(frozen=True)
class Rename:
    """A mapped ticker rename (AMD-0014): one continuous membership under a changed symbol."""

    old: str
    new: str
    effective: date | None


class MembershipInvariantError(ValueError):
    """The current-membership invariant failed (AMD-0014 2B): a failure, never a statistic."""


def _parse_renames(data: dict) -> list[Rename]:
    entries = data.get("renames")
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ConfigError("invalid ticker_renames.yaml: 'renames' must be a list")
    out: list[Rename] = []
    seen_old: set[str] = set()
    seen_new: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"ticker_renames.yaml entry {i}"
        if not isinstance(entry, dict) or set(entry) != {"old", "new", "effective"}:
            raise ConfigError(f"invalid {where}: need exactly the keys old, new, effective")
        old, new, eff = entry["old"], entry["new"], entry["effective"]
        for label, sym in (("old", old), ("new", new)):
            if not isinstance(sym, str) or not is_valid(sym):
                raise ConfigError(f"invalid {where}: bad {label} symbol {sym!r}")
        if old == new:
            raise ConfigError(f"invalid {where}: old and new are both {old!r}")
        if old in seen_old or new in seen_new or old in seen_new or new in seen_old:
            raise ConfigError(f"invalid {where}: {old!r}/{new!r} repeats another entry")
        seen_old.add(old)
        seen_new.add(new)
        if eff is None:
            effective = None
        elif isinstance(eff, date) and not isinstance(eff, datetime):
            effective = eff
        elif isinstance(eff, str):
            try:
                effective = date.fromisoformat(eff)
            except ValueError:
                raise ConfigError(f"invalid {where}: effective {eff!r} is not YYYY-MM-DD") from None
        else:
            raise ConfigError(f"invalid {where}: effective must be YYYY-MM-DD or null")
        out.append(Rename(old, new, effective))
    return out


def load_renames(config_dir: Path) -> list[Rename]:
    """The operator-maintained rename map; an absent file is an empty map."""
    path = Path(config_dir) / "ticker_renames.yaml"
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ConfigError("invalid config file: ticker_renames.yaml")
    return _parse_renames(data)


def _apply_renames(
    open_: dict[str, tuple[date, str]],
    closed: list[tuple[str, date, date | None, str]],
    renames: list[Rename],
    current: set[str],
    last_hanshof: date,
    as_of: date | None,
) -> None:
    """Turn each applicable mapped pair into one continuous membership (AMD-0014 2C).

    Applies only when the NEW ticker is a current member with no open interval and the OLD
    ticker is open at the gap; a pair already covered by explicit change rows is untouched.
    A rename whose start lies after `as_of` is not applied: the new ticker then has no open
    row and the unconditional invariant (AMD-0015 2A) fails loudly.
    """
    for r in renames:
        if r.new not in current or r.new in open_ or r.old not in open_:
            continue
        if r.effective is None:
            old_end, src = last_hanshof, SRC_RENAME_BOUNDED
            new_start = next_trading_day(last_hanshof)
        elif r.effective > last_hanshof:
            old_end, src = previous_trading_day(r.effective), SRC_RENAME_MAPPED
            new_start = r.effective
        else:
            log.warning("rename_not_after_hanshof_ignored", old=r.old, new=r.new)
            continue
        if as_of is not None and new_start > as_of:
            continue
        began, _ = open_.pop(r.old)
        closed.append((r.old, began, old_end, src))
        open_[r.new] = (new_start, src)
        log.info(
            "rename_applied",
            old=r.old,
            new=r.new,
            source=src,
            old_closes=old_end.isoformat(),
            new_opens=new_start.isoformat(),
        )


# ---------------------------------------------------------------------- membership
def build_membership(
    hanshof: pl.DataFrame,
    current_table: pl.DataFrame | None,
    fmp_changes: pl.DataFrame | None,
    start: date = MEMBERSHIP_START,
    as_of: date | None = None,
    changes_source: str = SRC_FMP,
    renames: list[Rename] | None = None,
    current_symbols: set[str] | None = None,
) -> pl.DataFrame:
    """Point-in-time intervals [symbol, start_date, end_date, source] (AMD-0013 2C).

    hanshof snapshots are diffed in order up to the last snapshot H (source 'hanshof').
    The gap after H is filled by the first available route: `fmp_changes` when given
    (a: source 'fmp', or b: source 'wikipedia-changes' - pass `changes_source`), else
    (c) derivation from `current_table` [symbol, date_added]: a current row whose
    `date_added` is in (H, as_of] starts that day ('wikipedia-derived-exact'); a symbol in
    hanshof@H but absent from the current table ends at H ('wikipedia-derived-bounded').
    A symbol removed on D is not a member on D: `end_date` is the last trading day before
    D (closed interval, AMD-0011). Contiguous or overlapping intervals of one symbol are
    merged; `end_date` NULL means current.

    `renames` (AMD-0014) map an OLD ticker in hanshof@H to a NEW current ticker: the pair is
    one continuous membership. Known `effective`: old ends the trading day before it, new
    starts on it ('rename-mapped'); unknown: old ends at H, new starts the next trading day
    ('rename-bounded'). A mapped old ticker is never a bounded removal. `current_symbols`
    (default: `current_table`) says which NEW tickers are in the index today.
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
            open_[sym] = (d, SRC_HANSHOF)
        for sym in sorted(prev - members):
            began, src = open_.pop(sym)
            closed.append((sym, began, previous_trading_day(d), src))
        prev = members

    renames = renames or []
    current_set = set(current_symbols) if current_symbols is not None else (
        set(current_table["symbol"].to_list()) if current_table is not None else set()
    )

    if fmp_changes is not None:
        changes = fmp_changes.filter(pl.col("date") > last_hanshof).sort(["date", "action"])
        for rec in changes.iter_rows(named=True):
            sym, d, action = rec["symbol"], rec["date"], rec["action"]
            if action == "added":
                if sym not in open_:
                    open_[sym] = (d, changes_source)
            elif action == "removed":
                if sym in open_:
                    began, src = open_.pop(sym)
                    src = f"{SRC_HANSHOF}+{changes_source}" if src == SRC_HANSHOF else src
                    closed.append((sym, began, previous_trading_day(d), src))
            else:
                raise ValueError(f"unknown change action: {action!r}")
        _apply_renames(open_, closed, renames, current_set, last_hanshof, as_of)
    elif current_table is not None and (as_of is None or as_of > last_hanshof):
        current = set(current_table["symbol"].to_list())
        _apply_renames(open_, closed, renames, current, last_hanshof, as_of)
        for sym in sorted(set(open_) - current):  # left the index somewhere in (H, today]
            began, _ = open_.pop(sym)
            closed.append((sym, began, last_hanshof, SRC_DERIVED_BOUNDED))
        added = current_table.filter(pl.col("date_added") > last_hanshof)
        if as_of is not None:
            added = added.filter(pl.col("date_added") <= as_of)
        for rec in added.sort(["date_added", "symbol"]).iter_rows(named=True):
            if rec["symbol"] not in open_:
                open_[rec["symbol"]] = (rec["date_added"], SRC_DERIVED_EXACT)
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
    gap_route: str = ROUTE_NONE
    rows_by_source: dict[str, int] = field(default_factory=dict)
    n_current_table: int = 0
    # AMD-0014 2B: current-table symbols with no open (end_date IS NULL) membership interval
    current_members_without_row: int = 0
    current_members_without_row_symbols: list[str] = field(default_factory=list)
    # AMD-0016 2C: symbols that only ever appear in `membership` (not current, not ETFs) and
    # were left without an industry group; counted, never an error and never a default
    n_unclassified: int = 0


def members_on_date(membership: pl.DataFrame, d: date) -> set[str]:
    """Symbols whose closed interval contains `d`."""
    return set(
        membership.filter(
            (pl.col("start_date") <= d) & (pl.col("end_date").is_null() | (pl.col("end_date") >= d))
        )["symbol"].to_list()
    )


def current_members_without_open_row(membership: pl.DataFrame, current: list[dict]) -> list[str]:
    """Current-table symbols that do not have exactly one open (`end_date IS NULL`) interval.

    The AMD-0014 / AMD-0015 2A invariant, always evaluated against the fetched current
    constituents table and independent of the run date (CI-1).
    """
    open_counts: dict[str, int] = {}
    for sym in membership.filter(pl.col("end_date").is_null())["symbol"].to_list():
        open_counts[sym] = open_counts.get(sym, 0) + 1
    return [r["symbol"] for r in current if open_counts.get(r["symbol"], 0) != 1]


def _today_utc() -> date:
    return datetime.now(UTC).date()


# AMD-0015 2A: the constituents table exists only as of now; a refresh dated further back
# than this cannot be correct, so it is refused rather than given invented semantics.
MAX_BACKDATE_DAYS = 7


class BackDatedRefreshError(ValueError):
    """`--date` is too far in the past for a refresh to be correct (AMD-0015 2A, AC10)."""


def check_refresh_date(as_of: date) -> None:
    """Raise BackDatedRefreshError if `as_of` is more than 7 calendar days before today (UTC)."""
    today = _today_utc()
    if (today - as_of).days > MAX_BACKDATE_DAYS:
        raise BackDatedRefreshError(
            f"--date {as_of.isoformat()} is more than {MAX_BACKDATE_DAYS} days before "
            f"{today.isoformat()}: the current constituents table has no historical snapshot, "
            "so a back-dated refresh cannot be correct"
        )


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
                "date_added": None,
            }
    if wiki is not None:
        for r in wiki.iter_rows(named=True):
            merged[r["symbol"]] = {
                "symbol": r["symbol"],
                "name": r["name"],
                "sector": r["gics_sector"],
                "sub_industry": r["gics_sub_industry"],
                "date_added": r["date_added"],
            }
    return [merged[k] for k in sorted(merged)]


def refresh(
    store: Store, settings: Settings, http: httpx.Client, as_of: date | None = None
) -> UniverseReport:
    """Populate `symbols` and rebuild `membership`; returns a UniverseReport."""
    as_of = as_of or _today_utc()
    check_refresh_date(as_of)  # before anything is read, fetched or written (AC10)
    settings.require("fmp_api_key")
    gics = _load_yaml(settings.argus_config_dir, "gics.yaml")
    universe_cfg = _load_yaml(settings.argus_config_dir, "universe.yaml")
    etfs = configured_etfs(universe_cfg)
    fmp = FMPClient(settings.fmp_api_key, settings.fmp_daily_call_budget, store, http=http)
    renames = load_renames(settings.argus_config_dir)
    sources: list[str] = []

    # --- current constituents with GICS classification
    wiki: pl.DataFrame | None = None
    wiki_changes: pl.DataFrame | None = None
    try:
        wiki, wiki_changes = fetch_wikipedia(http)
        sources.append("wikipedia")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("wikipedia_unavailable", error=type(exc).__name__)
    fmp_current: pl.DataFrame | None = None
    try:
        fmp_current = fmp.current_sp500()
        sources.append("fmp:sp500-constituent")
    except ProviderUnavailable as exc:  # 402/403: not a failure (AMD-0013)
        log.warning("fmp_current_unavailable", error=str(exc))
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
    hanshof = hanshof.filter(pl.col("date") <= as_of)
    # gap H -> today: first available route (AMD-0013 2C): (a) FMP, (b) page changes table,
    # (c) derivation from the current table
    changes: pl.DataFrame | None = None
    changes_source = SRC_FMP
    gap_route = ROUTE_DERIVED
    try:
        changes = fmp.historical_sp500_changes().filter(pl.col("date") <= as_of)
        gap_route = ROUTE_FMP
        sources.append("fmp:historical-sp500-constituent")
    except ProviderUnavailable as exc:
        log.warning("fmp_changes_unavailable", error=str(exc))
    if changes is None and wiki_changes is not None:
        changes = wiki_changes.filter(pl.col("date") <= as_of)
        changes_source = SRC_WIKI_CHANGES
        gap_route = ROUTE_WIKI_CHANGES
        sources.append("wikipedia:changes")
    if changes is None:
        if wiki is None:
            raise ProviderError("no route available for the membership gap after hanshof")
        sources.append("wikipedia:derived")
    membership = build_membership(
        hanshof,
        pl.DataFrame(
            {
                "symbol": [r["symbol"] for r in current],
                "date_added": [r["date_added"] for r in current],
            },
            schema={"symbol": pl.String, "date_added": pl.Date},
        )
        if changes is None
        else None,
        changes,
        start=MEMBERSHIP_START,
        as_of=as_of,
        changes_source=changes_source,
        renames=renames,
        current_symbols={r["symbol"] for r in current},
    )
    bad = [s for s in membership["symbol"].unique().to_list() if not is_valid(s)]
    if bad:
        raise ValueError(f"non-canonical membership symbols: {bad[:5]}")

    # --- AMD-0014 2B / AMD-0015 2A: ALWAYS enforced, independent of --date, before any write
    without_row = current_members_without_open_row(membership, current)
    n_current_table = len(current)
    if without_row:
        raise MembershipInvariantError(
            f"{len(without_row)} current index members do not have exactly one open membership "
            f"row: {', '.join(without_row)} "
            "(a ticker rename missing from ticker_renames.yaml, or not yet effective? AMD-0014)"
        )
    on_as_of = members_on_date(membership, as_of)
    if len(on_as_of) != n_current_table:
        raise MembershipInvariantError(
            f"membership on {as_of.isoformat()} has {len(on_as_of)} members but the current "
            f"table has {n_current_table} symbols"
        )

    # --- industry group for every current member (no silent defaults), then for historical-only
    # symbols (AMD-0016 2C). One cap and one availability flag cover BOTH cohorts, and current
    # members are classified first, so a historical symbol can never starve a current one.
    valid_sectors = set(gics["sectors"])
    group_sector: dict[str, str] = gics["industry_groups"]
    rows: list[dict] = []
    missing: list[str] = []
    fallbacks = 0
    profile_unavailable = False

    def via_profile(sym: str) -> str | None:
        nonlocal fallbacks, profile_unavailable
        if fallbacks >= MAX_PROFILE_FALLBACKS or profile_unavailable:
            return None
        fallbacks += 1
        try:
            group = map_industry_group(fmp.profile(sym).get("industry"), gics)
        except ProviderUnavailable:
            profile_unavailable = True  # 402/403: stop spending calls, not an error
            return None
        except (ProviderError, ValueError):
            return None
        if "fmp:profile" not in sources:
            sources.append("fmp:profile")
        return group

    for rec in current:
        sym = rec["symbol"]
        try:
            group: str | None = map_industry_group(rec["sub_industry"], gics)
        except ValueError:
            group = via_profile(sym)
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

    current_rows = {r["symbol"]: r for r in rows}
    new_of_old = {r.old: r.new for r in renames}
    historical_only = sorted(set(membership["symbol"].to_list()) - set(current_rows) - set(etfs))
    n_unclassified = 0
    for sym in historical_only:
        target = current_rows.get(new_of_old.get(sym, ""))
        if target is not None and target["gics_industry_group"]:
            group, sector = target["gics_industry_group"], target["gics_sector"]  # same company
        else:
            group = via_profile(sym)
            sector = group_sector[group] if group else None
        if group is None:
            n_unclassified += 1
        rows.append(
            {
                "symbol": sym,
                "name": None,
                "gics_sector": sector,
                "gics_industry_group": group,
                "active": False,
            }
        )
    if n_unclassified:
        log.warning("unclassified_historical_symbols", count=n_unclassified)

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

    rows_by_source = {
        str(k): int(v)
        for k, v in membership.group_by("source").len().sort("source").iter_rows()
    }
    n_members_today = len(store.members_on(as_of))
    if n_members_today != n_current_table:
        raise MembershipInvariantError(
            f"members_on({as_of.isoformat()}) returned {n_members_today} but the current table "
            f"has {n_current_table} symbols (AMD-0014)"
        )
    n_symbols = store.read("SELECT count(*) AS n FROM symbols")["n"][0]
    return UniverseReport(
        n_symbols=int(n_symbols),
        n_members_today=n_members_today,
        n_missing_group=len(missing),
        membership_rows=membership.height,
        sources_used=sources,
        gap_route=gap_route,
        rows_by_source=rows_by_source,
        n_current_table=n_current_table,
        current_members_without_row=len(without_row),
        current_members_without_row_symbols=without_row,
        n_unclassified=n_unclassified,
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
