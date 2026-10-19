import pytest

from argus.data.tickers import is_valid, normalize, to_provider


@pytest.mark.parametrize(
    ("source", "provider_form"),
    [
        ("yfinance", "BRK-B"),
        ("ibkr", "BRK B"),
        ("polygon", "BRK.B"),
        ("fmp", "BRK.B"),
        ("wikipedia", "BRK.B"),
        ("hanshof", "BRK.B"),
    ],
)
def test_roundtrip_all_sources(source, provider_form):
    assert normalize(provider_form, source) == "BRK.B"
    assert to_provider("BRK.B", source) == provider_form
    assert normalize(to_provider("BRK.B", source), source) == "BRK.B"


@pytest.mark.parametrize("source", ["yfinance", "ibkr", "polygon"])
def test_plain_symbol_unchanged(source):
    assert normalize("AAPL", source) == "AAPL"
    assert to_provider("AAPL", source) == "AAPL"


def test_generic_share_class_rule():
    assert normalize("ZZZ-A", "yfinance") == "ZZZ.A"
    assert to_provider("ZZZ.A", "ibkr") == "ZZZ A"


@pytest.mark.parametrize("bad", ["brk.b", "BRK..B", "TOOLONGSYMBOL1", ""])
def test_invalid_rejected(bad):
    assert not is_valid(bad)
    with pytest.raises(ValueError):
        normalize(bad, "polygon")
    with pytest.raises(ValueError):
        to_provider(bad, "polygon")
