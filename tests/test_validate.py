import polars as pl

from argus.data.validate import validate_day

N = 100
MEMBERS = [f"M{i:03d}" for i in range(N)]


def _bars(present=N, zero_vol=0, closes=None):
    syms = MEMBERS[:present]
    return pl.DataFrame(
        {
            "symbol": syms,
            "close": [closes.get(s, 100.0) if closes else 100.0 for s in syms],
            "volume": [0.0 if i < zero_vol else 1000.0 for i in range(len(syms))],
        }
    )


def _prior():
    return pl.DataFrame({"symbol": MEMBERS, "close": [100.0] * N})


def _groups(missing=()):
    return pl.DataFrame(
        {
            "symbol": MEMBERS,
            "gics_industry_group": [None if s in missing else "Software" for s in MEMBERS],
        }
    )


def _run(bars, splits=frozenset(), groups=None):
    g = groups if groups is not None else _groups()
    return validate_day(bars, MEMBERS, _prior(), set(splits), g)


def test_all_good():
    r = _run(_bars())
    assert r.ok and r.reasons == [] and r.coverage == 1.0 and r.n_zero_vol == 0 and r.n_jump == 0


def test_coverage_rule():
    assert not _run(_bars(present=94)).ok
    assert _run(_bars(present=94)).coverage == 0.94
    assert _run(_bars(present=95)).ok  # exactly 95% passes (rule is "< 95% rejects")
    assert _run(_bars(present=96)).ok
    assert any("coverage" in x for x in _run(_bars(present=94)).reasons)


def test_jump_requires_split():
    bars = _bars(closes={"M005": 130.0})  # +30%
    rejected = _run(bars)
    assert not rejected.ok and rejected.n_jump == 1
    assert _run(bars, splits={"M005"}).ok
    assert _run(_bars(closes={"M005": 74.0})).n_jump == 1  # -26%
    assert _run(_bars(closes={"M005": 124.0})).ok  # +24% is allowed


def test_zero_volume_rule():
    r = _run(_bars(zero_vol=3))
    assert not r.ok and r.n_zero_vol == 3
    assert _run(_bars(zero_vol=2)).ok  # exactly 2% passes


def test_missing_group_rule():
    r = _run(_bars(), groups=_groups(missing={"M010"}))
    assert not r.ok and any("industry group" in x for x in r.reasons)
    grp = pl.col("gics_industry_group")
    blank = _groups().with_columns(
        pl.when(pl.col("symbol") == "M010").then(pl.lit("  ")).otherwise(grp)
        .alias("gics_industry_group")
    )
    assert not _run(_bars(), groups=blank).ok
    absent = _groups().filter(pl.col("symbol") != "M010")
    assert not _run(_bars(), groups=absent).ok


HIST = [f"H{i:03d}" for i in range(4)]  # historical-only members (delisted), no bars today


def _hist_run(groups, current, bars=None):
    members = MEMBERS + HIST
    prior = pl.DataFrame({"symbol": members, "close": [100.0] * len(members)})
    bars = bars if bars is not None else _bars()
    return validate_day(bars, members, prior, set(), groups, current_members=current)


def _hist_groups(hist_group=None, missing=()):
    syms = MEMBERS + HIST
    return pl.DataFrame(
        {
            "symbol": syms,
            "gics_industry_group": [
                hist_group if s in HIST else (None if s in missing else "Software") for s in syms
            ],
        }
    )


def test_historical_unclassified_member_never_rejects():
    r = _hist_run(_hist_groups(), current=MEMBERS)
    assert r.ok and r.reasons == [] and r.n_unclassified_members == len(HIST)
    # historical members that DO have a group are not counted
    assert _hist_run(_hist_groups("Software"), current=MEMBERS).n_unclassified_members == 0


def test_current_member_without_group_still_rejects_amid_historical():
    r = _hist_run(_hist_groups(missing={"M010"}), current=MEMBERS)
    assert not r.ok and any("current member" in x and "industry group" in x for x in r.reasons)
    assert r.n_unclassified_members == len(HIST)


def test_current_members_default_is_strict():
    # without current_members every member is current: historical-only gaps reject
    members = MEMBERS + HIST
    prior = pl.DataFrame({"symbol": members, "close": [100.0] * len(members)})
    r = validate_day(_bars(), members, prior, set(), _hist_groups())
    assert not r.ok and r.n_unclassified_members == 0


def test_coverage_gate_unchanged_with_current_members():
    # 90 of 104 members have bars (86.5%) -> rejected even though classification is fine
    r = _hist_run(_hist_groups("Software"), current=MEMBERS, bars=_bars(present=90))
    assert not r.ok and any("coverage" in x for x in r.reasons)


def test_no_members_rejected():
    r = validate_day(_bars(), [], _prior(), set(), _groups())
    assert not r.ok


def test_does_not_mutate_inputs():
    bars, prior = _bars(), _prior()
    b0, p0 = bars.clone(), prior.clone()
    validate_day(bars, MEMBERS, prior, set(), _groups())
    assert bars.equals(b0) and prior.equals(p0)
