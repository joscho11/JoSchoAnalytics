# Generic WR injury/role feature sensitivity — frozen 2026-07-26

## Question

Can generic, point-in-time transformations separate a wide receiver's active-game role
from his prior-season availability strongly enough to raise Ricky Pearsall's 2026 score
without changing any player-specific constant?

This is a Pearsall-only scoring sensitivity. Historical WR rows may be used to fit the
fixed learner, but no other player prediction or model-quality metric may be computed or
reported. Nothing in this run can promote a production feature.

## Blindness disclosure

This experiment is fully outcome-aware. Pearsall's shipped 63.9, corrected-panel refit
76.1, depth sensitivity 89.4, player-specific scenario center 110–125, and the preceding
post-hoc tune-to-120 path are all known. The features below were proposed after seeing
those results. Therefore the output is a mechanism sensitivity only, not independent
evidence that any feature improves WR forecasts.

## Frozen panel and learner

- Panel: non-rookie WR rows, seasons 2014–2026, from the corrected
  `season_dataset_2014_2026.csv`.
- Target: regular-season half-PPR season total from the pinned
  `player_stats_1999_2025.parquet`.
- Training: every observed 2014–2025 non-rookie WR row.
- Scored row: Ricky Pearsall 2026 only (`00-0039916`).
- Baseline features: the exact ordered 32-column veteran WR feature contract.
- Learner for every variant: fixed LightGBM (`objective="mae"`, `num_leaves=15`,
  `learning_rate=0.03`, `n_estimators=400`, `random_state=42`).
- No ADP, Sleeper, depth chart, roster status, or player-name flag enters a feature or fit.

## Frozen generic features

### 1. Availability-neutral prior points

`prior_points_at_16_5 = prior_ppg × 16.5`.

The 16.5-game constant is inherited from the existing seasonal totals experiment, where
constant games beat the learned availability model. It is not chosen from Pearsall's
desired output. The original `prior_half_ppr`, `prior_games`, and
`prior_games_missed` remain in the feature set unchanged.

### 2. Active-week target share

For prior season `S`, identify games in which the WR recorded more than zero offensive
snaps in the pinned snap-count snapshot. Map PFR IDs to GSIS IDs through the pinned player
crosswalk. For those games:

`active_target_share(S) = sum(player targets) / sum(team targets)`.

The denominator includes only the same games in which that WR logged an offensive snap.
Zero-target active games remain in the denominator. Join this value to projection season
`S+1` as `prior_active_target_share`.

### 3. Active-week air-yards share

On the identical active-game set:

`active_air_yards_share(S) = sum(player receiving air yards) / sum(team receiving air yards)`.

Join to `S+1` as `prior_active_air_yards_share`.

### 4. Availability gaps

- `prior_target_share_availability_gap =
  prior_active_target_share - prior_target_share`
- `prior_air_yards_share_availability_gap =
  prior_active_air_yards_share - prior_air_yards_share`

The existing full-season shares stay in the feature set. The gaps expose how much role was
compressed by missed games without overwriting the original data.

## Frozen variants

1. `baseline`: the 32 production features.
2. `neutral_points`: baseline plus `prior_points_at_16_5`.
3. `active_role`: baseline plus both active-week shares and both availability gaps.
4. `both`: baseline plus all five generic features.

Fit all four models on the identical historical rows and score only Pearsall's 2026 row.
Report his five new feature values, four projections, and split counts for the new
features. Do not tune a threshold, add another feature, or select a preferred variant
after seeing the scores.

## Integrity

Before and after:

- `wr_veteran_model.pkl` MD5 must remain
  `17dfbcf01054bdd5ce032f2b55df9ad2`;
- `wr_rookie_model.pkl` MD5 must remain
  `6c9a3f3ed02ce32c53594f383aade882`;
- every existing result CSV must remain byte-identical.

No dataset, board, production model, or result artifact may be written.

## Structural amendment before scoring — missingness

The first target-blind build found 90.2–91.7% historical coverage across the five new
features. Missing `prior_points_at_16_5` rows are primarily honest full-miss/no-prior-PPG
cases; filling them would invent performance. All missing new-feature values therefore
remain native `NaN`, matching the frozen LightGBM treatment. Require at least 85% pooled
2014–2025 coverage for each new feature before scoring. No projection had been computed
when this handling was pinned.

## OUTCOME

Scored once on 2026-07-26. The corrected-panel baseline was 76.06. Adding
`prior_points_at_16_5` left the score exactly 76.06 and the feature received zero splits:
it is algebraically redundant with `prior_ppg`. The active-role bundle scored 75.19, and
all five features together also scored 75.19. The active-role features were used by the
trees, but they moved Pearsall down by 0.87 rather than repairing the availability
penalty.

**Verdict: generic injury/role feature additions do not lift Pearsall under this
season-total learner.** This says nothing about cross-player accuracy because none was
computed. No other player prediction was produced, and every protected artifact remained
byte-identical.
