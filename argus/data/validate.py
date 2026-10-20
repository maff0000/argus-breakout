"""Nightly day validation (DESIGN 3.3). Pure: never mutates its inputs."""

from collections.abc import Collection
from dataclasses import dataclass, field

import polars as pl

_COVERAGE_MIN_PCT = 95  # coverage >= 95%
_JUMP_MAX = 0.25
_ZERO_VOL_MAX_PCT = 2  # zero-volume members <= 2%


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    coverage: float = 0.0
    n_zero_vol: int = 0
    n_jump: int = 0
    n_unclassified_members: int = 0  # historical-only members without a group (never rejects)


def validate_day(
    bars: pl.DataFrame,
    members: list[str],
    prior_close: pl.DataFrame,
    splits_today: set[str],
    groups: pl.DataFrame,
    current_members: Collection[str] | None = None,
) -> ValidationResult:
    """Apply the four DESIGN 3.3 rules.

    bars: symbol, close, volume (one row per symbol). prior_close: symbol, close.
    groups: symbol, gics_industry_group.
    current_members: the members that are CURRENT, i.e. have an open membership interval
    (end_date IS NULL). Only these are subject to the classification check (AMD-0016 2C); a
    historical-only member without a group is counted in n_unclassified_members and never
    rejects. None (default) treats every member as current (the strict, pre-AMD-0016 check).
    """
    reasons: list[str] = []
    member_set = set(members)
    n_members = len(member_set)
    if n_members == 0:
        return ValidationResult(False, ["no active members"], 0.0, 0, 0)

    member_bars = bars.filter(pl.col("symbol").is_in(list(member_set)))
    present = member_bars["symbol"].n_unique()
    coverage = present / n_members
    if present * 100 < _COVERAGE_MIN_PCT * n_members:
        reasons.append(f"coverage {coverage:.4f} below 0.95 ({present}/{n_members} members)")

    n_zero = member_bars.filter(pl.col("volume").fill_null(0) == 0)["symbol"].n_unique()
    if n_zero * 100 > _ZERO_VOL_MAX_PCT * n_members:
        reasons.append(f"zero-volume members {n_zero}/{n_members} exceeds 2%")

    jumps = (
        bars.select("symbol", pl.col("close").alias("close_today"))
        .join(prior_close.select("symbol", pl.col("close").alias("close_prior")), on="symbol")
        .filter(pl.col("close_prior") > 0)
        .filter((pl.col("close_today") / pl.col("close_prior") - 1).abs() > _JUMP_MAX)
        .filter(~pl.col("symbol").is_in(list(splits_today)))
    )
    n_jump = jumps["symbol"].n_unique()
    if n_jump:
        sample = ", ".join(sorted(jumps["symbol"].to_list())[:5])
        reasons.append(f"{n_jump} close(s) moved >25% without a split (e.g. {sample})")

    grouped = set(
        groups.filter(
            pl.col("gics_industry_group").is_not_null()
            & (pl.col("gics_industry_group").str.strip_chars() != "")
        )["symbol"].to_list()
    )
    current_set = member_set if current_members is None else member_set & set(current_members)
    missing = sorted(current_set - grouped)
    if missing:
        sample = ", ".join(missing[:5])
        reasons.append(f"{len(missing)} current member(s) lack an industry group (e.g. {sample})")
    n_unclassified = len((member_set - current_set) - grouped)

    return ValidationResult(not reasons, reasons, coverage, n_zero, n_jump, n_unclassified)
