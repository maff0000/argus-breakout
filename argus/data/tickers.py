"""Ticker normalisation (PID 8.4). Canonical form uses `.` for share classes."""

import re
from typing import Literal

Source = Literal["polygon", "yfinance", "ibkr", "fmp", "wikipedia", "hanshof"]

CANONICAL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# Separator each provider uses between a root ticker and its share class.
_SEPARATOR: dict[str, str] = {
    "polygon": ".",
    "fmp": ".",
    "wikipedia": ".",
    "hanshof": ".",
    "yfinance": "-",
    "ibkr": " ",
}

# Known share-class tickers: canonical -> provider-specific form (where it differs).
KNOWN_SHARE_CLASSES: dict[str, dict[str, str]] = {
    "BRK.A": {"yfinance": "BRK-A", "ibkr": "BRK A"},
    "BRK.B": {"yfinance": "BRK-B", "ibkr": "BRK B"},
    "BF.A": {"yfinance": "BF-A", "ibkr": "BF A"},
    "BF.B": {"yfinance": "BF-B", "ibkr": "BF B"},
    "HEI.A": {"yfinance": "HEI-A", "ibkr": "HEI A"},
    "LEN.B": {"yfinance": "LEN-B", "ibkr": "LEN B"},
    "MOG.A": {"yfinance": "MOG-A", "ibkr": "MOG A"},
    "CWEN.A": {"yfinance": "CWEN-A", "ibkr": "CWEN A"},
    "UHAL.B": {"yfinance": "UHAL-B", "ibkr": "UHAL B"},
}

_REVERSE: dict[tuple[str, str], str] = {
    (src, form): canon
    for canon, forms in KNOWN_SHARE_CLASSES.items()
    for src, form in forms.items()
}

_CANON_CLASS = re.compile(r"^([A-Z]{1,5})\.([A-Z])$")


def is_valid(symbol: str) -> bool:
    """True if `symbol` is in canonical form."""
    if not isinstance(symbol, str) or CANONICAL.fullmatch(symbol) is None:
        return False
    return ".." not in symbol


def _check_source(source: str) -> str:
    if source not in _SEPARATOR:
        raise ValueError(f"unknown source: {source!r}")
    return _SEPARATOR[source]


def normalize(symbol: str, source: Source) -> str:
    """Provider form -> canonical form. Raises ValueError if the result is invalid."""
    sep = _check_source(source)
    if not isinstance(symbol, str):
        raise ValueError(f"invalid symbol: {symbol!r}")
    canon = _REVERSE.get((source, symbol))
    if canon is None:
        canon = symbol
        if sep != ".":
            m = re.fullmatch(r"([A-Z]{1,5})" + re.escape(sep) + r"([A-Z])", symbol)
            if m:
                canon = f"{m.group(1)}.{m.group(2)}"
    if not is_valid(canon):
        raise ValueError(f"invalid symbol for {source}: {symbol!r}")
    return canon


def to_provider(symbol: str, source: Source) -> str:
    """Canonical form -> provider form. Raises ValueError if `symbol` is not canonical."""
    sep = _check_source(source)
    if not is_valid(symbol):
        raise ValueError(f"invalid canonical symbol: {symbol!r}")
    known = KNOWN_SHARE_CLASSES.get(symbol, {}).get(source)
    if known is not None:
        return known
    m = _CANON_CLASS.fullmatch(symbol)
    if m and sep != ".":
        return f"{m.group(1)}{sep}{m.group(2)}"
    return symbol
