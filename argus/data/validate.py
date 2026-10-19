"""Nightly day validation (DESIGN 3.3). Pure: never mutates its inputs."""

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


def validate_day(
    bars: pl.DataFrame,
    members: list[str],
    prior_close: pl.DataFrame,
    splits_today: set[str],
    groups: pl.DataFrame,
) -> ValidationResult:
    """Apply the four DESIGN 3.3 rules.

    bars: symbol, close, volume (one row per symbol). prior_close: symbol, close.
    groups: symbol, gics_industry_group.
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
    missing = sorted(member_set - grouped)
    if missing:
        sample = ", ".join(missing[:5])
        reasons.append(f"{len(missing)} member(s) lack an industry group (e.g. {sample})")

    return ValidationResult(not reasons, reasons, coverage, n_zero, n_jump)
