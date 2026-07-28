# Pearsall college-talent / depth-chart sensitivity — frozen 2026-07-26

## Question

Ricky Pearsall's shipped 2026 non-rookie WR projection is low after two injury-shortened
NFL seasons. Test whether two information sources that are absent from the 32-feature
production model materially change his projection:

1. a decaying college-talent feature;
2. a preseason depth-chart tier;
3. both features together.

This is a player-specific sensitivity study, not a model-selection or shipping run.
Pearsall's output cannot promote a feature. Existing model and result artifacts must remain
byte-identical.

## Frozen data and baseline

- Panel: WR, `is_rookie == 0`, seasons 2014–2026 from the corrected
  `season_dataset_2014_2026.csv`.
- Outcome: regular-season half-PPR season total from the pinned
  `player_stats_1999_2025.parquet`.
- Baseline features: the exact 32-feature non-rookie WR pool.
- Learner: fixed LightGBM (`objective="mae"`, `num_leaves=15`,
  `learning_rate=0.03`, `n_estimators=400`, `random_state=42`).
- Historical comparison: expanding-window 2021–2025 walk-forward. The final Pearsall
  scores train once on all 2014–2025 rows and score only his 2026 row.
- No ADP or Sleeper value enters a feature, fit, metric, or decision. The existing shipped
  projection may be read after scoring solely as a contextual reference.

The corrected-panel refit baseline is the apples-to-apples comparator for the three
challengers. The shipped 63.9-point result was produced by the protected, pre-correction
model artifact and is reported separately rather than silently treated as the same fit.

## Frozen challenger 1: decaying college talent

Use the already-frozen richer PFF WR college composite from
`PREREG_pff_richer_rookie_2026-07-20.md`; do not search for new weights:

| Facet | Weight |
|---|---:|
| PFF pass-route grade | .400 |
| yards per route run | .250 |
| contested-catch rate | .100 |
| avoided tackles / receptions | .100 |
| PFF hands/drop grade | .075 |
| yards after catch / reception | .075 |

Each facet is opportunity-weighted over the player's college career (routes for the five
level facets; summed avoided tackles divided by summed receptions for the rate). Within
each walk-forward fold, z-score facets using only mapped WRs whose final college season
precedes the test season. Missing facets are omitted and remaining weights are
proportionally renormalized, matching the frozen richer-index rule.

Carry the composite into the first three NFL seasons with fixed half-life decay:

- first NFL season (`years_exp == 0`): `1.00 × college_index`;
- second (`years_exp == 1`): `0.50 × college_index`;
- third (`years_exp == 2`): `0.25 × college_index`;
- later seasons: `0`.

The non-rookie model therefore observes the 0.50 and 0.25 stages. The prior for this
feature is explicitly weak: the richer PFF WR index previously measured only +0.198
disattenuated correlation with the NFL talent target and was classified DEAD.

## Frozen challenger 2: preseason depth tier

Source nflverse depth charts through `nflreadpy.load_depth_charts`.

- 2014–2024: Week 1 regular-season offensive WR rows; use legacy `depth_team`.
- 2025: latest dated team snapshot strictly before the first 2025 regular-season game.
- 2026: latest dated team snapshot available at fire time.
- New ESPN schema: rank a player within `(team, pos_slot)` by `pos_rank`; the first player
  in each slot is tier 1, the second is tier 2, and so on. This is the schema-compatible
  translation to legacy `depth_team`; raw `pos_rank` is not directly comparable.
- Retain only tiers 1–2 from the new dated feed. This was frozen after the no-outcome
  structural check showed that unrestricted July camp rosters covered 96.3% of 2026 panel
  rows versus 67–79% historically. The legacy feed contained tiers 1–3 but fewer parallel
  WR slots; the new top two layers produce comparable player coverage (62.9% in 2026 versus
  63.9% when the same cap is applied historically). No target or model output was read
  before this coverage-only amendment, and Pearsall's tier-1 input is unchanged.

The audited 2026 San Francisco snapshot has Mike Evans raw WR ordinal 1, Ricky Pearsall 2,
Christian Kirk 3, and De'Zhaun Stribling 4. Because Evans, Pearsall, and Kirk occupy three
different `pos_slot` values, all three normalize to depth tier 1; Stribling is tier 2.

Score the official tier-1 Pearsall row. Also score a disclosed tier-2 counterfactual after
the primary outputs to quantify sensitivity; it is not a fifth trained model.

This feature represents declared preseason lineup position only. It does not independently
encode George Kittle's injury/recovery probability or allocate targets among Evans,
Pearsall, Kirk, Stribling, and the tight ends.

## Frozen variants and reporting

Fit exactly four models per fold and for the final 2026 score:

1. `baseline`: 32 production features;
2. `college`: baseline + `college_talent_decay`;
3. `depth`: baseline + `preseason_depth_tier`;
4. `both`: baseline + both new features.

Report pooled and per-season MAE and Spearman correlation, the number of MAE-winning folds,
and Pearsall's final projection for every variant. Report the `years_exp == 2` historical
slice because it is the relevant career stage, but do not tune on it.

A challenger is historically credible only if all three fixed conditions hold:

- pooled MAE improves by at least 0.25 points;
- pooled Spearman does not decline;
- MAE improves in at least 3 of 5 seasons.

This gate is descriptive here: passing would justify a separate production-wide
preregistered validation, not shipping. Failing rejects the feature as a general point
forecast change even if it raises Pearsall.

## Integrity

Before and after the run, assert:

- `wr_veteran_model.pkl` MD5 remains
  `17dfbcf01054bdd5ce032f2b55df9ad2`;
- `wr_rookie_model.pkl` MD5 remains
  `6c9a3f3ed02ce32c53594f383aade882`;
- every existing CSV under `fantasy/projections/results/` is byte-identical.

The structural check must also show that 2026 depth-feature coverage is within 10 percentage
points of pooled 2021–2025 coverage after the new-feed tier cap.

## OUTCOMES (recorded after the fact; rules above were not modified)

Fired once on 2026-07-26 with
`wr_pearsall_sensitivity_harness.py --fire`, SHA256
`c3ec4951a71ef4a996c736ecc4fcad297081af4c8b97b4bb42b0c1bb3fea64d6`.
The preceding `--check` verified the target-blind feature construction, Pearsall's inputs,
and the 7.1-point 2026-versus-2021–2025 depth-coverage shift. No ADP/Sleeper column entered
the panel, features, fit, or historical decision.

### Historical walk-forward, 2021–2025

| Variant | n | MAE | ΔMAE vs baseline | Spearman | Δrho | MAE-winning seasons | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| baseline | 1,006 | 31.071 | — | .75341 | — | — | — |
| college | 1,006 | 30.943 | -0.128 | .75192 | -.00149 | 3/5 | **FAIL** |
| depth | 1,006 | **29.053** | **-2.017** | .80523 | **+.05182** | 3/5 | **PASS** |
| both | 1,006 | 29.058 | -2.012 | **.80601** | +.05261 | 4/5 | **PASS** |

College missed the fixed 0.25-point MAE threshold and reduced rank correlation.
**Verdict: REJECT college talent as a general point-forecast feature.**

Depth cleared all three frozen conditions. The combined model also cleared them, but it did
not improve on depth alone: MAE was 0.005 points worse and rho only 0.00078 higher. That
provides no incremental evidence for college talent. **Verdict: depth is a developmental
candidate; the combination is not a distinct candidate.** Passing this sensitivity gate
does not authorize a production model change.

For the relevant third-NFL-season slice (n=168), baseline MAE 33.033 / rho .7714 /
mean residual +8.79 moved to 30.729 / .8157 / +5.14 with depth. College alone moved to
32.696 / .7763 / +8.62.

### Pearsall 2026 score

The shipped 63.9 is contextual only: its protected model was trained before the corrected
season panel. The apples-to-apples baseline for the challengers is the corrected-panel
refit.

| Score | Half-PPR points | Change vs corrected refit |
|---|---:|---:|
| Shipped projection (context) | 63.9 | n/a |
| Corrected-panel refit baseline | 76.1 | — |
| College | 76.1 | +0.0 |
| Depth, official tier 1 | 89.4 | +13.3 |
| Both | 91.0 | +14.9 |
| Depth, tier-2 counterfactual | 79.2 | +3.1 |
| Both, tier-2 counterfactual | 79.0 | +2.9 |

Pearsall's opportunity-weighted college index is only +0.115 SD; the fixed third-season
decay reduces the observed feature to +0.029. The college-only score moves by 0.04 point.
The substantive lift is entirely the depth assumption: tier 1 adds 13.3 points, while
tier 2 adds only 3.1.

The depth result does not encode George Kittle's return probability or a target-allocation
model. It says that declared first-tier WR status has historically added useful information
beyond last-season volume. The July depth chart can still change before Week 1, and the
historical feature used Week 1 charts, so Pearsall's 89.4 is a current-role scenario rather
than a settled production projection. It remains 50.3 points below Sleeper's 139.7.

Both protected model MD5s and every existing result CSV were byte-identical before and
after the run. No model or projection artifact changed.
