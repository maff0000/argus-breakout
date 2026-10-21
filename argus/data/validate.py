"""Nightly day validation (DESIGN 3.3, AMD-0016/0017/0018). Pure: never mutates its inputs.

`ok=False` means QUARANTINE: the day is stored in bars_raw and not published to bars. It never
means "not stored" (CI-9).
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from fractions import Fraction

import polars as pl

_COVERAGE_MIN_PCT = 95  # coverage >= 95%
_ZERO_VOL_MAX_PCT = 2  # zero-volume members <= 2%
_PRIOR_CLOSE_MISSING_MAX_PCT = 5  # AMD-0017 2B: prior_close missing for > 5% => rule inapplicable

# A close that moved more than this fraction day-on-day is FLAGGED (AMD-0018 2C). For a single
# equity a 25% move is routine (earnings, guidance), so it is a finding on that symbol-day, never
# a verdict on the market's day by itself.
_JUMP_MAX = 0.25

# The day is quarantined for jumps only when this fraction of members_on(d) is flagged
# jump_unexplained (AMD-0018 2C). Reasoning: the day-level rule exists to catch a vendor-side
# failure (prices in the wrong scale, a wrong or duplicated file) and those are near-total --
# essentially every symbol moves. Real market action is not: on the heaviest single sessions in
# the 2024-2026 window, S&P 500 members moving more than 25% number in the tens, not the
# hundreds. 20% of members is ~100 symbols: above anything the market produces and far below
# what corruption produces. The separation is wide, so the exact value inside it is not
# load-bearing. Changeable only by Amendment.
_JUMP_DAY_QUARANTINE_FRACTION = 0.20

# After a split the nightly basis boundary (yesterday fetched pre-split, today post-split)
# makes close_today / close_prior ~= 1 / ratio; a move is reconciled when the ratio puts it
# back within this tolerance of 1 (WO-0004 2, AMD-0018 2C).
_SPLIT_RECONCILE_TOLERANCE = 0.05

FLAG_JUMP_UNEXPLAINED = "jump_unexplained"
FLAG_JUMP_SPLIT_RECONCILED = "jump_split_reconciled"
FLAGS = frozenset({FLAG_JUMP_UNEXPLAINED, FLAG_JUMP_SPLIT_RECONCILED})

_FLAG_SCHEMA = {"symbol": pl.String, "flag": pl.String, "detail": pl.String}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    coverage: float = 0.0
    n_zero_vol: int = 0
    n_jump_unexplained: int = 0  # members_on(d) flagged jump_unexplained (the decided population)
    n_jump_reconciled: int = 0  # members_on(d) flagged jump_split_reconciled
    n_unclassified_members: int = 0  # historical-only members without a group (never quarantines)
    n_without_prior_close: int = 0  # members_on(d) with no usable prior_close
    jump_rule_applied: bool = True  # False only on a genuine first-ever ingest date
    # Every flagged symbol in the fetched frame, members or not: symbol, flag, detail.
    flags: pl.DataFrame = field(default_factory=lambda: pl.DataFrame(schema=_FLAG_SCHEMA))


def _jump_flags(
    bars: pl.DataFrame, prior_close: pl.DataFrame, splits_today: dict[str, float]
) -> pl.DataFrame:
    """One flag row per symbol in `bars` whose close moved more than _JUMP_MAX."""
    joined = (
        bars.select("symbol", pl.col("close").alias("close_today"))
        .join(prior_close.select("symbol", pl.col("close").alias("close_prior")), on="symbol")
        .filter(pl.col("close_prior") > 0)
        .with_columns((pl.col("close_today") / pl.col("close_prior")).alias("ratio_move"))
        .filter((pl.col("ratio_move") - 1).abs() > _JUMP_MAX)
    )
    rows: list[dict[str, str]] = []
    for sym, move in zip(joined["symbol"].to_list(), joined["ratio_move"].to_list(), strict=True):
        r = splits_today.get(sym)
        if r is not None and round(abs(move * r - 1), 9) <= _SPLIT_RECONCILE_TOLERANCE:
            flag, detail = FLAG_JUMP_SPLIT_RECONCILED, f"move={move - 1:+.4f} split_ratio={r:g}"
        else:
            flag, detail = FLAG_JUMP_UNEXPLAINED, f"move={move - 1:+.4f}"
            if r is not None:
                detail += f" split_ratio={r:g} (inconsistent)"
        rows.append({"symbol": sym, "flag": flag, "detail": detail})
    return pl.DataFrame(rows, schema=_FLAG_SCHEMA).sort("symbol")


def validate_day(
    bars: pl.DataFrame,
    members: list[str],
    prior_close: pl.DataFrame,
    splits_today: dict[str, float],
    groups: pl.DataFrame,
    is_first_date: bool,
    current_members: Collection[str] | None = None,
) -> ValidationResult:
    """Apply the DESIGN 3.3 rules as amended by AMD-0016/0017/0018.

    bars: symbol, close, volume (one row per symbol; the whole fetched frame).
    members: members_on(d). prior_close: symbol, close. groups: symbol, gics_industry_group.
    splits_today: symbol -> split_to/split_from for splits executing on d.
    is_first_date: True only when no earlier row exists in bars_raw (AMD-0017 2B).
    current_members: members with an open membership interval; only these are subject to the
    classification check (AMD-0016 2C). None treats every member as current.

    The jump rule is RECORDED for every symbol in `bars` (the `flags` frame) and DECIDED over
    members only: a non-member never contributes to a day-level verdict (AMD-0018 2B).
    """
    reasons: list[str] = []
    member_set = set(members)
    n_members = len(member_set)
    flags = _jump_flags(bars, prior_close, splits_today)
    if n_members == 0:
        return ValidationResult(
            False, ["no active members"], jump_rule_applied=not is_first_date, flags=flags
        )

    member_bars = bars.filter(pl.col("symbol").is_in(list(member_set)))
    present = member_bars["symbol"].n_unique()
    coverage = present / n_members
    if present * 100 < _COVERAGE_MIN_PCT * n_members:
        reasons.append(f"coverage {coverage:.4f} below 0.95 ({present}/{n_members} members)")

    n_zero = member_bars.filter(pl.col("volume").fill_null(0) == 0)["symbol"].n_unique()
    if n_zero * 100 > _ZERO_VOL_MAX_PCT * n_members:
        reasons.append(f"zero-volume members {n_zero}/{n_members} exceeds 2%")

    # Jump rule: decided over members_on(d) only (AMD-0018 2B).
    member_flags = flags.filter(pl.col("symbol").is_in(list(member_set)))
    unexplained = member_flags.filter(pl.col("flag") == FLAG_JUMP_UNEXPLAINED)["symbol"].to_list()
    n_unexplained = len(unexplained)
    n_reconciled = member_flags.filter(pl.col("flag") == FLAG_JUMP_SPLIT_RECONCILED).height
    if Fraction(n_unexplained, n_members) >= Fraction(str(_JUMP_DAY_QUARANTINE_FRACTION)):
        sample = ", ".join(sorted(unexplained)[:5])
        reasons.append(
            f"{n_unexplained}/{n_members} members flagged jump_unexplained "
            f"(>= 20% breadth, e.g. {sample})"
        )

    # AMD-0017 2B: a rule that cannot be applied is never counted as a pass.
    usable = set(
        prior_close.filter(pl.col("close") > 0)["symbol"].to_list()
    )
    n_no_prior = len(member_set - usable)
    if not is_first_date and n_no_prior * 100 > _PRIOR_CLOSE_MISSING_MAX_PCT * n_members:
        reasons.append(
            f"jump rule inapplicable: prior_close missing for {n_no_prior} of {n_members} members"
        )

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

    return ValidationResult(
        not reasons,
        reasons,
        coverage,
        n_zero,
        n_unexplained,
        n_reconciled,
        n_unclassified,
        n_no_prior,
        not is_first_date,
        flags,
    )
