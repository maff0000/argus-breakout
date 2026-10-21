import polars as pl

from argus.data.validate import validate_day

N = 100
MEMBERS = [f"M{i:03d}" for i in range(N)]
NON_MEMBERS = [f"X{i:03d}" for i in range(40)]  # e.g. reassigned tickers of delisted members


def _bars(present=N, zero_vol=0, closes=None, extra=()):
    syms = MEMBERS[:present] + list(extra)
    return pl.DataFrame(
        {
            "symbol": syms,
            "close": [closes.get(s, 100.0) if closes else 100.0 for s in syms],
            "volume": [0.0 if i < zero_vol else 1000.0 for i in range(len(syms))],
        }
    )


def _prior(symbols=MEMBERS):
    return pl.DataFrame(
        {"symbol": list(symbols), "close": [100.0] * len(symbols)},
        schema={"symbol": pl.String, "close": pl.Float64},
    )


def _groups(missing=()):
    return pl.DataFrame(
        {
            "symbol": MEMBERS,
            "gics_industry_group": [None if s in missing else "Software" for s in MEMBERS],
        }
    )


def _run(bars, splits=None, groups=None, prior=None, is_first_date=False):
    g = groups if groups is not None else _groups()
    p = prior if prior is not None else _prior(MEMBERS + NON_MEMBERS)
    return validate_day(bars, MEMBERS, p, dict(splits or {}), g, is_first_date)


def _flag_rows(r, flag):
    return r.flags.filter(pl.col("flag") == flag)["symbol"].to_list()


def test_all_good():
    r = _run(_bars())
    assert r.ok and r.reasons == [] and r.coverage == 1.0 and r.n_zero_vol == 0
    assert r.n_jump_unexplained == 0 and r.n_jump_reconciled == 0 and r.flags.is_empty()
    assert r.jump_rule_applied is True and r.n_without_prior_close == 0


def test_coverage_rule():
    assert not _run(_bars(present=94)).ok
    assert _run(_bars(present=94)).coverage == 0.94
    assert _run(_bars(present=95)).ok  # exactly 95% passes (rule is "< 95% quarantines")
    assert _run(_bars(present=96)).ok
    assert any("coverage" in x for x in _run(_bars(present=94)).reasons)


def test_one_member_jump_does_not_quarantine_the_day():
    r = _run(_bars(closes={"M005": 130.0}))  # +30%, no split
    assert r.ok is True and r.reasons == []
    assert r.n_jump_unexplained == 1
    assert _flag_rows(r, "jump_unexplained") == ["M005"]
    assert r.flags.height == 1


def test_jump_flag_threshold():
    assert _run(_bars(closes={"M005": 124.0})).flags.is_empty()  # +24% is not a jump
    assert _flag_rows(_run(_bars(closes={"M005": 126.0})), "jump_unexplained") == ["M005"]
    assert _flag_rows(_run(_bars(closes={"M005": 74.0})), "jump_unexplained") == ["M005"]  # -26%


def _jumping(n):
    return {s: 140.0 for s in MEMBERS[:n]}


def test_breadth_of_jumps_quarantines_the_day():
    r20 = _run(_bars(closes=_jumping(20)))
    assert r20.ok is False and r20.n_jump_unexplained == 20
    assert any("jump_unexplained" in x for x in r20.reasons)
    r19 = _run(_bars(closes=_jumping(19)))
    assert r19.ok is True and r19.n_jump_unexplained == 19 and r19.flags.height == 19


def test_non_member_jump_never_reaches_the_verdict():
    # 40 non-members (40% of the member count) move 90%: well past the 20% breadth line.
    closes = {s: 190.0 for s in NON_MEMBERS}
    r = _run(_bars(closes=closes, extra=NON_MEMBERS))
    assert r.ok is True and r.reasons == []
    assert r.n_jump_unexplained == 0
    assert sorted(_flag_rows(r, "jump_unexplained")) == sorted(NON_MEMBERS)  # recorded widely


def test_jump_with_consistent_split_is_reconciled():
    bars = _bars(closes={"M005": 50.0})  # -50%
    r = _run(bars, splits={"M005": 2.0})
    assert _flag_rows(r, "jump_split_reconciled") == ["M005"]
    assert _flag_rows(r, "jump_unexplained") == []
    assert r.n_jump_reconciled == 1 and r.n_jump_unexplained == 0
    r3 = _run(bars, splits={"M005": 3.0})
    assert _flag_rows(r3, "jump_unexplained") == ["M005"]
    assert _flag_rows(r3, "jump_split_reconciled") == []
    # tolerance: 52.5 * 2 / 100 = 1.05 reconciles, 55 * 2 / 100 = 1.10 does not
    assert _flag_rows(
        _run(_bars(closes={"M005": 52.5}), splits={"M005": 2.0}), "jump_split_reconciled"
    ) == ["M005"]
    assert _flag_rows(
        _run(_bars(closes={"M005": 55.0}), splits={"M005": 2.0}), "jump_unexplained"
    ) == ["M005"]


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
    return validate_day(bars, members, prior, {}, groups, False, current_members=current)


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


def test_historical_unclassified_member_never_quarantines():
    r = _hist_run(_hist_groups(), current=MEMBERS)
    assert r.ok and r.reasons == [] and r.n_unclassified_members == len(HIST)
    # historical members that DO have a group are not counted
    assert _hist_run(_hist_groups("Software"), current=MEMBERS).n_unclassified_members == 0


def test_current_member_without_group_still_quarantines_amid_historical():
    r = _hist_run(_hist_groups(missing={"M010"}), current=MEMBERS)
    assert not r.ok and any("current member" in x and "industry group" in x for x in r.reasons)
    assert r.n_unclassified_members == len(HIST)


def test_current_members_default_is_strict():
    # without current_members every member is current: historical-only gaps quarantine
    members = MEMBERS + HIST
    prior = pl.DataFrame({"symbol": members, "close": [100.0] * len(members)})
    r = validate_day(_bars(), members, prior, {}, _hist_groups(), False)
    assert not r.ok and r.n_unclassified_members == 0


def test_coverage_gate_unchanged_with_current_members():
    # 90 of 104 members have bars (86.5%) -> quarantined even though classification is fine
    r = _hist_run(_hist_groups("Software"), current=MEMBERS, bars=_bars(present=90))
    assert not r.ok and any("coverage" in x for x in r.reasons)


def test_missing_prior_close_quarantines_non_initial_day():
    # 6 of 100 members lack a prior_close (> 5%): the jump rule could not be applied
    r = _run(_bars(), prior=_prior(MEMBERS[6:]))
    assert r.ok is False and r.n_without_prior_close == 6 and r.jump_rule_applied is True
    assert "jump rule inapplicable: prior_close missing for 6 of 100 members" in r.reasons
    # exactly 5% is tolerated
    assert _run(_bars(), prior=_prior(MEMBERS[5:])).ok is True
    # an empty prior on a non-initial day is the whole-store version of the same failure
    r_all = _run(_bars(), prior=_prior([]))
    assert r_all.ok is False
    assert "jump rule inapplicable: prior_close missing for 100 of 100 members" in r_all.reasons


def test_first_ever_date_records_rule_not_applied():
    r = _run(_bars(), prior=_prior([]), is_first_date=True)
    assert r.jump_rule_applied is False
    assert r.ok is True and not any("inapplicable" in x for x in r.reasons)
    assert r.n_without_prior_close == N


def test_no_members_quarantined():
    r = validate_day(_bars(), [], _prior(), {}, _groups(), False)
    assert not r.ok


def test_does_not_mutate_inputs():
    bars, prior = _bars(closes={"M005": 130.0}), _prior()
    b0, p0 = bars.clone(), prior.clone()
    validate_day(bars, MEMBERS, prior, {"M005": 2.0}, _groups(), False)
    assert bars.equals(b0) and prior.equals(p0)
