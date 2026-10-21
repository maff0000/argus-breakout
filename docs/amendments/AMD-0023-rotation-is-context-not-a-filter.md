# AMD-0023 — Rotation is headline context, never a filter; candle geometry and levels; the weakness list is always computed

| Field | Value |
|---|---|
| **Status** | Approved |
| **Amends** | `docs/architecture/DESIGN.md` §5 (two new factor groups), §7 (exclusion removed; report layout added as §7.1) |
| **Related ADR** | ADR-0005 |
| **Raised by** | Product Owner, 2026-10-21: *"sector rotation is something I wish to be aware of and should form the headline on the report, but stocks identified in screening should not be defined only if they are part of sector rotation — a good stock to long can still be in a sector that is being rotated out of"* |
| **Affects Work Orders** | None. §5 and §7 belong to PID-ARGUS-0002 and PID-ARGUS-0004, neither authored. This is a specification change with no delivered code behind it |

## 1. Problem

### (a) Rotation was wired as a gate, and that is the same mistake a fourth time
DESIGN §7's hard filters read: *"members of EXIT_WARNING groups excluded
from long lists."* The Product Owner is right that this is wrong, and it
is worth recording **why** it is wrong, because it is the fourth instance
of one structural error in this project:

| | A judgement was used to remove data |
|---|---|
| AMD-0018 §2A | a day-level verdict gated `bars_raw` |
| AMD-0019 §2A | a symbol-level flag deleted a row from `bars` |
| AMD-0021 §2C | a status blocklist admitted unjudged days |
| **AMD-0023** | **a group-level rotation verdict removed a stock from the list** |

Each time the fix is the same shape: **carry the judgement with the thing,
let the consumer decide.** Rotation is information about a group; it is not
a verdict on a company.

And there is a market mechanism, not merely a preference, behind the
Product Owner's instinct. Rotation is computed on a group **average**,
while dispersion within a group is wide. A name with a high `rs_sector` in
an `EXIT_WARNING` group is outperforming both its sector and the index —
which is frequently the position institutions **keep** while leaving the
rest of the sector. Excluding it discards the most interesting observation
in the group, and §5 already computes `rs_sector` and `rs_ig` precisely to
surface it.

### (b) The weakness list disappears when it is most useful as context
§7 gates the Breakdown playbook to `bull_narrow`, `correction` and `bear`.
In `bull_broad` nothing is produced at all — yet that list is also the
**trim-and-avoid** list for longs already held, which is useful in every
regime. Gating the *computation* conflated "is this tradeable" with "is
this worth knowing".

### (c) Named candle patterns and price levels are absent
No candle geometry, no pivots, no swing-based support or resistance
anywhere in §5. The Product Owner reviews each ticker by eye afterwards, so
the screen should hand over the levels its own stop sits against.

## 2. Change

### A. Rotation tags; it never removes
§7's hard filters: **"members of EXIT_WARNING groups excluded from long
lists" is deleted.** Replaced by:
> Every candidate carries its group's rotation state — `quadrant`,
> `rotation_score`, and `ENTRY_WATCH`/`EXIT_WARNING` — as **displayed
> fields**. Rotation never removes a name from a list (AMD-0023 §2A).
>
> Rotation may **tilt the ordering** and may not determine membership:
> `rank_final = rank_raw + clamp(0.5 · z(rotation_score), −10, +10)`
> percentile points. **Both `rank_raw` and `rank_final` are shown**, so the
> size and direction of the rotation effect is visible rather than baked
> in. The tilt is bounded by construction: no rotation state can push a
> name off a list, and a strong stock in a weak group is tagged, demoted a
> little, and still reviewed.
>
> A high `rs_sector` or `rs_ig` percentile inside an `EXIT_WARNING` group
> is **highlighted, not penalised twice**: it is the name holding up while
> its sector is sold.

### B. §7.1 — report layout, rotation leading
DESIGN gains §7.1:
> The report leads with rotation as **context**, then lists candidates
> independently of it.
>
> 1. **Headline — rotation and regime.** The regime label, what changed
>    since yesterday, and two explicit lists:
>    - **Rotating IN** — groups in `ENTRY_WATCH`, or `Improving` with
>      `d_rs_mom5 > 0` three sessions running, each followed by **its
>      member tickers that appear on any candidate list**.
>    - **Rotating OUT** — groups in `EXIT_WARNING`, or `Leading`/`Weakening`
>      with `d_rs_mom5 < 0` three sessions running, same treatment.
>
>    Groups with no candidates are still listed, with an empty ticker set:
>    that a group is turning and holds nothing worth buying is itself a
>    finding.
> 2. **Long candidates** — ranked per playbook, each row tagged with its
>    group's quadrant and rotation state, **not filtered by either**.
> 3. **Weakness / short candidates** — always present (§2C).
> 4. **Plain ticker lines** — one comma-separated line per bucket, for
>    copy-paste into the Product Owner's own charting tool. This is a
>    convenience in the report, **not** an integration with any third-party
>    platform and no such integration is in scope.
>
> Every ticker shown carries its nearest support and resistance levels
> (§2D) alongside the ATR stop, so the operator can judge whether the stop
> sits in a sensible place rather than taking `1.5 · ATR` on faith.

### C. The weakness list is always computed; the regime gates action only
§7's Breakdown row: the playbook **always runs** and its output is always
shown, re-titled **"Weakness — short / trim / avoid"**. The regime decides
only the **label on the actionability column**: `shortable` in
`bull_narrow`, `correction`, `bear`; `trim/avoid only` in `bull_broad` and
`neutral`. Per §8's existing rule, "short" means exit, avoid or inverse
unless the account allows margin.

### D. §5 gains two factor groups
> | Factor | Feature | Definition |
> |---|---|---|
> | Candle geometry | `body_pct` | abs(close − open) / (high − low); NULL where high = low |
> | | `upper_wick_pct`, `lower_wick_pct` | (high − max(open,close)) / (high − low); (min(open,close) − low) / (high − low) |
> | | `marubozu` | sign(close − open) where `body_pct` ≥ 0.90, else 0 |
> | | `doji` | 1 where `body_pct` ≤ 0.10, else 0 |
> | | `range_atr` | (high − low) / atr14 — today's candle measured in the stock's own volatility |
> | Levels | `pivot_d r1_d s1_d r2_d s2_d` | from the prior session's H/L/C: P = (H+L+C)/3, R1 = 2P − L, S1 = 2P − H, R2 = P + (H − L), S2 = P − (H − L). `_w` and `_m` variants from the prior week and month |
> | | `dist_pivot_atr`, `dist_r1_atr`, `dist_s1_atr` | (close − level) / atr14 |
> | | `swing_hi`, `swing_lo` | fractal pivot: a bar whose high (low) is the extreme of the 5 bars either side |
> | | `dist_res_atr`, `dist_sup_atr` | distance to the nearest clustered swing level above / below, in ATR. Levels within 0.5 · ATR of each other are one level |
> | | `res_touches`, `sup_touches` | touch count of that level — a level tested four times is not the same object as one tested once |
>
> **Distances are in ATR, never per cent** (AMD-0023 §2D). "2% from
> resistance" means something different for a 12%-volatility utility and a
> 70%-volatility biotech; ATR units make the figure comparable across the
> universe, which is what the §5 percentile system depends on.

**Stated plainly, because it would otherwise be oversold:** a single
candle pattern on a daily bar is weak evidence on its own. The literature
and ordinary experience both put its value in *confirmation* — a marubozu
**on a breakout day**, a doji or long lower wick **at a tested support
level** — not in standalone signalling. So these features enter playbooks
as confirmation terms and **never as a trigger in their own right**:
- *Breakout watch* — `marubozu = 1` on a Donchian-20 break raises
  conviction; a `doji` on the break lowers it.
- *Pullback buys* and *Bounce* — `lower_wick_pct` high, or `doji`, within
  0.5 ATR of a support level with `sup_touches ≥ 2`, is confirmation.
- *Weakness* — `marubozu = −1` breaking a Donchian-20 low, likewise.

PID-ARGUS-0004's factor-IC study measures whether any of them carries
information. If one does not, it stays a displayed field and leaves the
scoring.

## 3. Why this is free today
§5 is PID-ARGUS-0002's and §7 is PID-ARGUS-0004's; **neither Phase PID is
authored and no Work Order exists against either.** There is no code, no
test and no evidence to revise — only this document. The same change after
those phases ship would be a post-merge correction across the feature
layer, the ranker and the report. This is what designing ahead of
implementation is for, and it is the Product Owner's question that found
it.

## 4. Application
Applied by the Architect in the commit introducing this file; changed
sections tagged `(AMD-0023)`.

## 5. Approval
```
Approved by: Claude (Architect)
Date (UTC):  2026-10-21
Commit:      the commit introducing this file
```
