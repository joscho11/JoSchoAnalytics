# WR depth signal falsification — frozen 2026-07-26

## Why this follow-up exists

The Pearsall sensitivity run found a large 2021–2025 improvement from preseason depth
tier: MAE 31.071 to 29.053 and Spearman .7534 to .8052. That result does not establish
that the ordinal tier is useful. Historical rows missing from the Week 1 depth chart are
often fringe or inactive players, so the model may be learning roster presence. The
historical feature is also measured at Week 1 while Pearsall's 2026 value is observed in
July.

This preregistration freezes falsification tests before their outputs are read. It does not
authorize a model, dataset, board, or projection change.

## Data and fixed model

- Same corrected WR non-rookie panel, target, 32 baseline features, fixed LightGBM, and
  expanding 2021–2025 walk-forward used by
  `PREREG_wr_pearsall_sensitivity_2026-07-26.md`.
- No Sleeper or ADP value is loaded.
- Existing model and result artifacts must remain byte-identical.
- Reproduce the fired baseline and depth metrics before interpreting a diagnostic.

## Test 1 — presence versus ordinal tier

Fit four full-panel variants:

1. `baseline`: 32 features;
2. `listed`: baseline + binary `depth_listed`;
3. `tier_fired`: the exact depth feature previously fired;
4. `tier_aligned`: cap both legacy and new-schema depth charts at tiers 1–2, turning
   legacy tier 3 into missing. This makes historical feature support match the 2026 input.

Define the proportion of the fired depth MAE gain recovered by presence:

`presence_recovery = (MAE_baseline - MAE_listed) /
                     (MAE_baseline - MAE_tier_fired)`.

If `presence_recovery >= 0.75`, classify the original result as predominantly roster
presence rather than tier ordering.

## Test 2 — complete-case tier value

Within every fold, retain only rows with an aligned tier in both training and test data.
Fit:

1. the 32-feature baseline;
2. baseline + ordinal tier.

Tier ordering has incremental evidence only if all hold:

- pooled MAE improves by at least 0.25 points;
- pooled Spearman does not decline;
- MAE improves in at least 3 of 5 seasons.

Also report actual outcome, zero rate, baseline residual, and baseline MAE separately for
tier 1 and tier 2 out-of-fold rows. These are diagnostics, not additional gates.

## Test 3 — timing stability

The dated ESPN-format nflverse feed begins on 2025-08-03, so it cannot validate July
stability. Within the 2025 WR non-rookie panel:

- construct aligned top-two tiers at each team's earliest available dated snapshot before
  the regular season;
- construct them again at the latest team snapshot before the regular season;
- report early and late listed counts, the share of early-listed players still listed,
  and exact tier agreement among players listed at both times.

Call the timing evidence adequate only if:

- at least 80% of early-listed players remain listed at the pre-opener snapshot; and
- exact tier agreement among common players is at least 80%.

Even a pass applies only to early August through Week 1, not July.

## Decision

The ordinal depth feature remains a developmental candidate only if:

1. presence recovers less than 75% of the original MAE gain;
2. the complete-case tier model clears all three accuracy conditions;
3. the 2025 timing check clears both stability conditions.

Otherwise reject ordinal depth tier for the current July production model. A strong
presence-only result may motivate a separately defined roster-status feature, but cannot
promote one here.

## Integrity

Before and after the run, assert:

- `wr_veteran_model.pkl` MD5
  `17dfbcf01054bdd5ce032f2b55df9ad2`;
- `wr_rookie_model.pkl` MD5
  `6c9a3f3ed02ce32c53594f383aade882`;
- every existing CSV under `fantasy/projections/results/` is byte-identical.

## OUTCOMES (recorded after the fact; rules above were not modified)

Fired exactly once on 2026-07-26 with
`wr_depth_signal_falsification_harness.py --fire`, SHA256
`46941297722d9a7de92696bdeef0ec665c76cb2008339383d6dfdca44c57d200`.
The prior baseline and fired-depth metrics reproduced to 1e-9 before any diagnostic was
interpreted.

### Presence versus tier

Across 1,006 expanding-window 2021–2025 WR non-rookie rows:

| Variant | MAE | ΔMAE vs baseline | Spearman | Δrho |
|---|---:|---:|---:|---:|
| baseline | 31.071 | — | .75341 | — |
| listed only | 29.712 | -1.358 | .79261 | +.03920 |
| aligned tier 1–2 | 29.229 | -1.841 | .80058 | +.04717 |
| originally fired tier | 29.053 | -2.017 | .80523 | +.05182 |

The binary listed flag recovered **67.3%** of the originally fired MAE gain, below the
frozen 75% threshold. Roster presence explains most of the result, but not enough to
classify the ordinal signal as merely presence. Applying the same tier 1–2 support
historically reduced the gain by only 0.176 point.

### Complete cases

Among 658 out-of-fold rows with an aligned tier:

- baseline MAE 38.368 / rho .71085;
- tier MAE **37.753** / rho **.73213**;
- ΔMAE **-0.615**, Δrho **+.02127**, with MAE better in **3/5** seasons.

All three frozen conditions passed. Tier ordering has incremental historical evidence
beyond roster presence.

Tier 1 actual outcomes averaged 122.9 with a 114.8 median over n=392, versus tier 2 mean
40.1 and median 28.7 over n=266. The complete-case baseline was nearly unbiased on tier 1
(+0.9 actual minus prediction) but overprojected tier 2 by 6.1, so the rank feature mainly
identifies low-volume secondary players rather than applying a blanket tier-1 uplift.

### Timing

The 2025 dated feed runs from 2025-08-03 through the 2025-09-03 pre-opener snapshot.
Within the non-rookie WR panel, 144 players were listed in the early top two tiers and 143
pre-opener; 127 appeared in both. **88.2%** of early-listed players remained listed, and
exact tier agreement among common players was **86.6%**. Both registered stability
conditions passed. This establishes early-August to Week-1 stability only, not July.

### Decision and current-schema caveat

All three preregistered falsification conditions passed, so the mechanical verdict is
**ORDINAL DEPTH REMAINS A DEVELOPMENTAL CANDIDATE**.

That is not a production recommendation. The 2025 fold is the only evaluated season using
the same dated ESPN schema as 2026, and it moved the wrong way:

- aligned-tier MAE 28.672 to **29.191** (+0.518 worse);
- rho .81991 to **.81571** (-.00420);
- complete-case tier MAE 34.468 to **34.943** (+0.475 worse).

The positive pooled evidence is carried by the legacy nflverse schema. Ordinal depth tier
is historically informative but **not yet shown to transport to the current source**, so
it should not enter the July production model. The correct next evidence is forward
observation of the current schema or another full season of comparable dated snapshots,
not another historical transformation.

Both protected model hashes and every existing result CSV remained byte-identical.
