# PRE-REGISTRATION - WR VETERAN AGE-TAIL CALIBRATION (2026-07-24)

**STATUS: DRAFTED, NOT ACCEPTED, NOT BUILT, NOT FIT, NOT FIRED.** This is a direct
season-total forecast calibration study. It is separate from the seasonal value-signal
campaign, makes no ADP or Sleeper performance claim, and does not change the deployed
WR model, its model files, or any board CSV.

## 1. Question and mechanism

**Hypothesis.** Replacing the veteran WR model's raw age feature with `min(age, 30)` will
reduce direct half-PPR season-total absolute error for veteran WR player-seasons aged 30+
without materially harming the under-30 veteran population.

**Mechanism.** The frozen model slate uses tree learners with a small number of older-WR
examples. Raw age permits unsupported within-tail splits among 30+ players; capping it
shares the age signal across that sparse tail while retaining the full pre-30 age response.
The challenger does not assume that older players are healthy, good, or bad. Prior
production, receiving usage, availability, team environment, and every other feature stay
available to the model.

**Expected result.** Reject. Two visible older-veteran projection gaps are not enough
reason to expect a fixed cap to improve direct out-of-sample accuracy.

## 2. Frozen scope

- Position and route: `position == "WR"` and `is_rookie == 0` only. Rookie WRs,
  including De'Zhaun Stribling, are out of scope.
- Target: the existing observed regular-season half-PPR season total from
  `season_total_target()` in `build_rb_projection.py`. Partial, zero, and injury-shortened
  seasons remain in the target exactly as they are in
  `PREREG_wr_projection_2026-07-21.md` section 1.
- Evaluation panel: outer walk-forward test seasons 2021, 2022, 2023, 2024, and 2025.
  For test year `Y`, training is strictly `season < Y`; 2026 is never scored or inspected
  by this study.
- Baseline: the current WR veteran path, using the exact 32-column `WR_VET_ALL` / `VET_FEATS`
  pool, including raw `age`, the frozen four-family slate, frozen grids, native-missing
  behavior, seed, and inner leave-one-season-out selection in
  `PREREG_wr_projection_2026-07-21.md` sections 3, 5, 7, and 8.
- Challenger: replace only the `age` column, at the same position in the feature order,
  with `age_capped_30 = min(age, 30.0)`. Raw `age` is not also supplied. The other 31
  columns, target, folds, model families, hyperparameter grids, random seed, and inner-CV
  selection are byte-for-byte the baseline definition.
- No feature is added. In particular, this does not add historical PFF/talent data, alter
  opportunity/team-context inputs, use ADP/Sleeper in fitting or scoring, reweight history,
  or remove/toggle `prior_games_missed` or `missed_prior_season`.

## 3. Blind structural feasibility and power

The allowed structure-only probe read only `player_id`, position, rookie flag, season, and
age from `season_dataset_2014_2026.csv`; it read no targets, predictions, player names, ADP,
or Sleeper values. The veteran-WR age-30+ cell counts are 20, 18, 29, 27, and 29 across
2021-2025: 123 player-seasons from 65 unique players. Age is present for all 1,006
veteran-WR player-seasons in the panel.

The primary statistic clusters repeated player-seasons by player, so the conservative
power unit is the 65 unique older players, not 123 rows. Under a unit-variance independent
player-cluster approximation, a one-sided 5% test has 80% power at standardized effect
`d = (1.645 + 0.842) / sqrt(65) = 0.308`. This is powered only for a moderate correction;
a negative result cannot exclude a smaller age-tail effect. At that effect size, the
fold-level positive-direction probabilities for the observed 18-29 rows per season are
about 90-95%, so the four-of-five consistency rule is not the binding power cost.

## 4. Exact fire-time construction

The future harness must use `usecols` so it never loads `sleeper*`, `adp*`, or market-rank
columns. It must write only to a new temporary directory and must not call `--ship`,
`--refresh-deploy`, or overwrite any model or result artifact.

For each outer test row `i`, calculate the paired absolute-error improvement:

```
d_i = abs(y_i - baseline_prediction_i) - abs(y_i - capped_age_prediction_i)
```

Positive values favor the challenger. For the age-30+ population, form one value per
player `D_j` by averaging that player's `d_i` values across all of their qualifying outer
test seasons. The primary statistic is the standardized cluster mean
`T_30plus = mean(D_j) / sample_sd(D_j)`; it fails if fewer than two nonconstant clusters
remain. The unstandardized pooled and per-season MAE deltas are reported for interpretation
but only the named rules below decide the result.

Structural assertions before any metric is printed:

1. The five test years, rows, and `(player_id, season)` identities exactly match between
   baseline and challenger; every training row has `season < Y`.
2. Baseline has raw `age` and no `age_capped_30`; challenger has `age_capped_30` and no
   raw `age`; each otherwise has exactly 32 features in the frozen order.
3. Every outer test age is present; the age-30+ counts equal 20/18/29/27/29 and the
   65-player count above.
4. The run reads no market columns, scores no 2026 row, and leaves WR pkl MD5 hashes and
   every `results/*.csv` hash unchanged.

## 5. Decision rule - PASS iff all conditions hold

Metrics are printed to three decimals. The test fires once, in a fresh session, only after
Joseph accepts this disclosure and the structural harness has passed without printing a
single outcome metric.

1. **Age-tail primary.** `T_30plus` exceeds the empirical 95th percentile of a 1,000-draw
   placebo distribution. Each draw independently permutes the age-30+ membership labels
   within each outer test season, preserving that season's older-player count, then
   reconstructs player-cluster means and `T` exactly as above. Seed is fixed at 42. The
   fire-time placebo percentile binds; no fixed threshold is substituted after seeing it.
2. **Fold consistency.** The raw age-30+ MAE delta is strictly positive in at least four
   of the five outer test seasons.
3. **Younger-veteran floor.** On the same player-cluster construction for `age < 30`,
   `T_under30 >= -0.100`. This inherited standardized subgroup-loss floor prevents a
   localized older-tail gain from licensing a material loss across the larger veteran
   population.
4. **One shot.** Rejection is final for this mechanism: no alternate cap, threshold,
   spline, age interaction, tail definition, re-pooled panel, different metric, recency
   weighting, injury ablation, or ADP/Sleeper rescue test. A genuinely different mechanism
   would require a new preregistration written before its outcome is evaluated.

## 6. Consequences fixed in advance

**PASS** licenses only the narrow statement that, on this 2021-2025 direct-total panel,
the specified capped-age input improved this veteran-WR age-tail calibration under the
frozen rule. It does not establish talent, health, market inefficiency, ADP value, or a
2026 player call. Before any public projection is rebuilt, Joseph must separately approve
the exact deploy change; that implementation must retain all availability features, retrain
only under this frozen challenger definition, preserve the rookie model, and pass the
normal pkl/output/dashboard validation gates.

**FAIL** retains raw age in the deployed WR veteran model. It closes the age-cap mechanism
above; it does not justify an injury-feature removal or a new attempt tuned around the
observed result. The proper headline is the pre-committed power caveat: a moderate
cluster-standardized effect of about `d = 0.308` was not established, while smaller effects
were not excluded.

## 7. Blindness disclosure

This is **PARTIALLY BLIND**. Before drafting it, the outlier audit inspected two named
older veterans (Terry McLaurin and Mike Evans) with unusually low 2026 model outputs versus
market context and frozen-model probes indicating an age/career contribution larger than
the availability contribution. That is exactly why an age-tail challenger is being tested;
it is not aggregate evidence that the cap works. Stribling's rookie profile-coverage issue
was also observed but is excluded by scope.

This drafting session also read the already-published all-WR 2021-2025 summary in
`GUIDE.md`, but did not inspect age-tail outcomes, any challenger prediction, any
baseline-vs-challenger metric, or player names/outcomes in the feasibility probe. The cap
value 30 is therefore post-observation and disclosed, not presented as a blind biological
threshold. Mitigations: one cap only, a direct-target test rather than a market comparison,
a player-clustered statistic, a 1,000-draw within-season placebo, and a four-of-five
season requirement. Joseph decides whether this partial blindness is acceptable before any
harness build or one-shot fire.

## 8. Explicit fences

- The 2026 rookie deployment recovery is a completed identity/coverage correction, not
  evidence for this veteran study; it remains untouched.
- The established injury-return guard remains. This study cannot remove, zero, or reweight
  availability inputs.
- The seasonal value-signal H4/H6/H7/H8/H11/H12 work is a separate market-research record.
  Nothing here reopens a closed ADP claim or spends any sealed seasonal slice.
- Historical veteran PFF/talent panels and historical college-talent scores remain data
  prerequisites, not features to be slipped into this challenger.

*Drafted 2026-07-24. Rules become locked only if Joseph accepts the stated partial blindness
and explicitly authorizes the structural-harness build. No outcome is recorded above.*

## Acceptance and structural-harness record (2026-07-24, Step 7)

Joseph accepted the partial-blindness disclosure and authorized the structural-harness
build. The rules above are now **LOCKED**. This record adds no alternative feature, cap,
panel, metric, threshold, or release path; it only records the authorized no-metrics stage.

`wr_veteran_age_cap_harness.py --check` passed with SHA-256
`288350a7c3b36c5298cc2c98b7b5c9fe030092e8efd058ed52a4f84afd1a1225`. It verified the
32-to-32 raw-age-to-capped-age feature replacement, strict 2021-2025 walk-forward scope,
older-WR counts 20/18/29/27/29 (65 unique players), zero market-column loading, zero 2026
scoring, and no artifact write. The protected model files remained byte-identical:
`wr_veteran_model.pkl` MD5 `17dfbcf01054bdd5ce032f2b55df9ad2`; `wr_rookie_model.pkl`
MD5 `6c9a3f3ed02ce32c53594f383aade882`.

No model fit, target construction, prediction, error metric, ADP/Sleeper comparison, or
placebo value was computed in this stage. The one-shot fire remains for one fresh session
only; it must use this exact harness contract and append its outcome below without changing
the locked rules above.

## Interrupted fire / contamination record (2026-07-24)

The subsequent attempted fire did not reach `T_30plus`, the placebo, or PASS/FAIL, but it
was not blind: a 2021 baseline selection and inner-CV MAE were printed, paired 2021 fold
predictions were persisted, and inner-CV configuration-score tuples were persisted in
`C:\tmp`. Therefore this preregistration is **NOT CLEANLY FIRED** and must not be rerun as
its one-shot test. The exploratory age study below is not an outcome for this preregistration
and cannot restore its blindness; any later confirmatory age change needs a fresh design.
