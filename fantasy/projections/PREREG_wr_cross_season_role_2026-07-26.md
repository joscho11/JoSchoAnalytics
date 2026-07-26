# PRE-REGISTRATION — WR CROSS-SEASON ROLE STATE (2026-07-26)

**STATUS: LOCKED BEFORE OUTCOME EVALUATION.** This is a read-only development experiment
on the non-rookie WR season-total model. It cannot rewrite a model, projection CSV, board
artifact, or market claim. Sleeper and ADP are excluded from loading, fitting, scoring,
and the decision rule.

## 1. Question and mechanism

The current 32-feature model knows a WR's prior-season target share but not whether that
share rose or fell across seasons. The hypothesis is that one additional lag and its
deterministic change contain ranking information not represented by `ppg_trend`:

```
target_share_lag2 = target share in season Y-2
target_share_delta = prior_target_share - target_share_lag2
```

This is not another within-season trajectory test. First-half, second-half, last-four,
EWMA, slope, rise thresholds, and `years_exp == 2` interactions were already evaluated
and are fenced. The challenger supplies the same two cross-season role-state features to
all non-rookie WRs.

Expected result: reject. The candidate arose after roughly ten 2021-2025 subgroup cuts,
and raw within-season role features already failed.

## 2. Frozen data and feature construction

- Universe: `position == "WR"` and `is_rookie == 0`, including zero-game reconstructed
  seasons. Rookies remain untouched.
- Target: observed regular-season half-PPR season total from the pinned weekly-stat
  snapshot, `fantasy_points + 0.5 * receptions`, summed by `(player_id, season)`;
  unmatched panel rows are real zero outcomes.
- Baseline features: the exact ordered 32-column `VET_FEATS` list.
- Challenger features: those 32 columns followed by `target_share_lag2` and
  `target_share_delta`. No other input changes.
- Learner: fixed deployed non-rookie configuration:
  `LGBMRegressor(objective="mae", num_leaves=15, learning_rate=0.03,
  n_estimators=400, random_state=42, verbose=-1, n_jobs=-1)`.
- Missing values retain LightGBM's native handling. No imputation is added.
- For target season `Y`, `prior_target_share` is the corrected volume-weighted share
  from `Y-1`. `target_share_lag2` is the same corrected field from `Y-2`, recovered
  mechanically from the prior target-season row for that player.
- A source player-season with more than one distinct weekly regular-season team is a
  mover season. Because the current share field is keyed to the season-final team, both
  new features are set to missing if either `Y-1` or `Y-2` is a mover season. The
  baseline's existing `prior_target_share` is not altered.
- No minimum share, direction threshold, third-year filter, injury filter, age filter,
  or named-player exception is permitted.

## 3. Panels and walk-forward protocol

Two panels are frozen:

1. **Primary, less-contaminated development panel:** outer test seasons 2018-2020. The
   third-year negative-gap search did not inspect this panel, although these seasons are
   not a pristine holdout because they participated in earlier model development.
2. **Compatibility panel:** outer test seasons 2021-2025. This panel generated the
   hypothesis and can supply compatibility evidence only, never confirmation.

For every outer year `Y`, each arm trains only on panel rows with `season < Y` and fits
the same target rows. Test identities must match one-to-one. The 2026 rows are used only
for feature-coverage counts; no 2026 target or prediction is computed.

Before any outcome is loaded, `--check` must establish:

- all baseline and challenger columns exist and the challenger differs by exactly the
  two named features;
- no loaded dataset column begins with `sleeper` or `adp`;
- at least 100 training rows exist for every outer fold;
- both new features are observed on at least 40% of each test fold;
- pooled 2026 coverage differs from pooled 2018-2025 test coverage by no more than
  10 percentage points;
- the protected WR model MD5s are unchanged:
  `17dfbcf01054bdd5ce032f2b55df9ad2` and
  `6c9a3f3ed02ce32c53594f383aade882`.

Failure of a structural assertion stops the experiment before outcomes.

## 4. Metrics

For each row, paired absolute-error improvement is:

```
d_i = abs(y_i - baseline_i) - abs(y_i - challenger_i)
```

Positive values favor the challenger. Report pooled and per-season MAE and Spearman
rank correlation for both arms. Report `mean(d_i)` with a 20,000-draw player-clustered
percentile interval using seed `20260726`; player clusters are resampled and all of a
sampled player's rows travel together.

The top tail is the highest `ceil(0.10 * n_Y)` actual outcomes within each outer season.
Report mean residual `y - prediction` in that tail. The no-harm population is every
non-top-tail row; report its paired MAE change.

The already-seen `years_exp == 2` population is diagnostic only: report its pooled bias,
MAE, and per-season bias. It cannot make the challenger pass.

## 5. Frozen decision rule

The challenger is a **developmental candidate** only if every condition holds:

1. Primary 2018-2020 pooled MAE improves by at least 0.25 points.
2. Primary pooled Spearman improves by at least 0.005.
3. Both MAE and Spearman improve in at least two of three primary folds.
4. The player-clustered 95% interval for primary `mean(d_i)` has a lower bound above 0.
5. Primary top-tail mean underprojection is reduced, and non-top-tail MAE worsens by no
   more than 0.25 points.
6. On the contaminated 2021-2025 compatibility panel, pooled MAE does not worsen,
   pooled Spearman does not fall, and both improve in at least three of five folds.

Anything else is **REJECT**. A developmental-candidate verdict licenses neither shipping
nor a 2026 point adjustment. Confirmation requires 2026 forward outcomes or a genuinely
untouched panel.

## 6. Multiplicity and fences

Exactly one challenger is evaluated. Rejection closes alternate lags, rolling windows,
share thresholds, mover thresholds, deltas conditioned on career stage, interactions,
objective changes, and threshold-tail rescue on these panels. The result cannot be
rescored against Sleeper/ADP, re-pooled, or reframed around named 2026 players.

This experiment does not reopen H7, H8v, the retired target-room arithmetic, the rejected
within-season trajectory family, alternative losses/rankers, or short-season uplifts.

## 7. Blindness disclosure

This is **PARTIALLY BLIND**. Before these rules were frozen, the 2021-2025 residual panel
had been searched through roughly ten cuts. The pre-fix broad third-season group showed
mean underprojection of +6.79 points over 168 rows; after the target-share correction it
showed +8.79 over the same 168 rows, positive in all five seasons, with a
player-clustered 95% interval of [+1.83, +16.07]. The pre-fix
`years_exp == 2 and prior_target_share >= 0.15` refinement showed +17.48 over 47 rows;
after correction it shrank to 37 rows, +12.25, four of five positive seasons, and interval
[-7.51, +31.58]. Eleven former members fell below the threshold because the old share
calculation was wrong. That threshold is therefore abandoned and cannot be reused.

No cross-season-role challenger prediction, 2018-2020 challenger metric, or corrected
cross-season feature had been computed when this file was written. The 2021-2025 panel is
explicitly contaminated; the 2018-2020 panel is only less contaminated, not sealed.

*Locked 2026-07-26 before `wr_cross_season_role_harness.py --check` or `--fire` existed.*

## OUTCOME (recorded after the fact; rules above were not modified)

**VERDICT: REJECT.** The frozen harness was created with SHA-256
`748837e0794acf8a70eadfc78ab1e66f5ebf8a13bb2d7cfc72e76a5f8ee9ddf5`.
`--check` passed before any outcome was loaded: coverage was 1,005/1,572 (63.9%) on
pooled 2018-2025 test rows and 138/245 (56.3%) on 2026 rows, a 7.6-point shift inside
the frozen 10-point cap. All test folds exceeded 57% coverage. The baseline had 32
features, the challenger 34, no market column was loaded, and protected artifacts were
unchanged.

`--fire` then ran exactly once.

On the primary 2018-2020 panel (n=566), baseline MAE 35.393 and Spearman 0.6858 moved
to challenger MAE 35.336 and Spearman 0.6835: MAE improved only 0.057 points, far below
the required 0.25, while rank correlation fell 0.0023 instead of improving 0.005. Both
metrics improved in two of three folds, but the paired player-clustered absolute-error
interval was [-0.439, +0.547], failing the required positive lower bound. Top-tail mean
underprojection was effectively unchanged (64.360 to 64.350 points).

On the contaminated 2021-2025 compatibility panel (n=1,006), baseline MAE 31.071 and
Spearman 0.75341 moved to challenger MAE 31.082 and Spearman 0.75355. That is a
0.011-point MAE worsening and a 0.00014 rank increase—practical parity. Both metrics
improved in only two of five seasons, the clustered interval was
[-0.394, +0.373], and top-tail underprojection worsened from 54.588 to 55.495 points.

The challenger failed six of nine frozen conditions: primary MAE magnitude, primary
rank magnitude, primary clustered interval, compatibility MAE, compatibility fold
consistency, and primary tail improvement. Cross-season target-share lag/delta is closed
on these panels. No alternate lag, threshold, interaction, career-stage slice, or
tail-event rescue using these two features is licensed.

The protected WR model MD5s and every existing `fantasy/projections/results/*.csv` hash
were identical before and after the check and fire. No model, projection, or board
artifact was written.
