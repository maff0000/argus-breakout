# WO-0015 rename candidates (AC3, AC4)

Full output: renames-output.tsv (500 candidates, 184 severed current members).

## Measured
- Ranked candidates (signal 1 AND 2): 500. by confidence: 17 high (closes within 10%), 186 medium (no price comparison possible), 297 low (closes more than 10% apart).
- FB (to 2022-06-08) -> META (from 2022-06-09), gap 1 trading day, medium confidence, present in the output and not in the declared map. META has stored bars from 2015-01-02 (1872 bars before membership start) and the membership row starts 2022-06-09. Adjudication: probable rename — the history under META predates 2022 and the old symbol ends the day before; FB also pairs with VICI on the same date, which is index-swap coincidence, not a rename.
- CERN 2022-06-07 -> META also appears (gap 2). Not a rename: it is a leaver in the same reconstitution.

## Honest limit of the discriminator (spec-gap)
The rule as specified (new membership starts materially after its first stored bar, AND an old interval ends within a few trading days) cannot separate a rename from an index swap: any stock joining the index shortly after another leaves is a candidate, and every long-listed stock that joins later has bars before membership. Result: 500 candidates and 184 severed members, e.g. the single new symbol VMRK pairs with 32 different leavers. Signal 3 (price ratio) only fires when the old symbol has stored bars; true renames under AMD-0016 2D have none, so they are medium by construction, the same tier as the noise. The command is a candidate generator for operator review, not a classifier. A usable discriminator needs a different signal (for example the same bars_raw series continuing under the new name, or an external ticker-change feed). Recorded for the Architect.
- AC4 list: 184 current members whose membership starts more than 30 days after their first stored bar; the dominant cause is ordinary later index additions of long-listed stocks, so the list is NOT evidence of missing renames by itself.
