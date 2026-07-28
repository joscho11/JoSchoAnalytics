# Non-rookie WR PPG target-architecture validation — frozen 2026-07-26

## Question and mechanism

Does predicting active-game half-PPR rate and converting it to a season total with the
existing 16.5-game constant improve the full non-rookie WR projection model relative to
predicting season-total half-PPR directly?

The proposed mechanism is target separation. The direct-total target asks one MAE tree
to learn scoring rate and future availability jointly, which can suppress a player after
an injury-shortened prior season. A PPG target isolates scoring rate; games-weighting
trusts rate labels from long observed seasons more than labels from short samples; the
fixed 16.5 multiplier supplies the previously established availability convention.

## Blindness disclosure

This is a partially blind follow-up. The corrected direct-total LightGBM walk-forward
result is already known (n=1,006, 2021–2025; MAE 31.071, Spearman .75341), as are the
Pearsall-only 2026 challenger scores: 117.71 unweighted and 119.42 games-weighted at
16.5 games. No cross-player challenger prediction, historical challenger metric, Rome
Odunze challenger score, or Luther Burden challenger score has been computed.

The challenger was selected because the games-weighted version was the predeclared
Pearsall sensitivity variant and because the older seasonal totals experiment found a
constant-games conversion superior to a learned availability model. This is outcome-aware
architecture development, not a sealed hold-out. Its result can justify or reject a
production switch recommendation; it cannot establish market edge.

## Frozen panel, target, and model

- Universe: every `is_rookie == 0` WR row in the corrected
  `season_dataset_2014_2026.csv`.
- Historical outcome: observed regular-season half-PPR season total from
  `snapshots/player_stats_1999_2025.parquet`; a historical panel row with no weekly stat
  record is assigned zero, matching the shipped season-total target.
- Outer test seasons: 2021, 2022, 2023, 2024, 2025.
- Every outer test row is scored by both architectures. The primary panel therefore
  includes zero-game and very-short outcomes; a season-total model must own availability
  risk.
- Features: the exact ordered 32-column non-rookie WR production contract. No feature is
  added, deleted, reordered, rewritten, or player-specific.
- Learner on both sides: fixed LightGBM with `objective="mae"`,
  `num_leaves=15`, `learning_rate=0.03`, `n_estimators=400`,
  `random_state=42`. Fixing the same deployed configuration isolates the target
  architecture and prevents a model-family or hyperparameter search.
- Every fold trains strictly on seasons before its test season.

## Frozen architectures

1. **Incumbent — `direct_total`:** fit all earlier non-rookie WR rows to observed
   season-total half-PPR. Clip predictions below zero.
2. **Challenger — `games_weighted_ppg_x_16_5`:** fit earlier rows with non-missing
   `target_ppg` and `target_games > 0` to `target_ppg`, using
   `sample_weight=target_games`. Clip PPG below zero and multiply by exactly 16.5.

There is no unweighted challenger, learned-games model, multiplier sweep, blend, cap,
calibration shift, or post-hoc feature variant. The 16.5 constant is inherited from
`fantasy/seasonal_projections/eval_totals.py`, not chosen from this run.

## Frozen metrics and switch rule

Primary metrics are computed on the identical pooled n=1,006 outer-fold rows:

- MAE;
- RMSE;
- Spearman rank correlation;
- mean residual bias, defined as `actual - prediction`;
- MAE by test season;
- a paired player-cluster bootstrap of challenger-minus-incumbent MAE, 2,000 draws,
  resampling `player_id` clusters with replacement, seed 42.

The challenger earns a production-switch recommendation only if **all** conditions hold:

1. pooled MAE improves by at least 0.50 points:
   `MAE_challenger - MAE_incumbent <= -0.50`;
2. the paired player-cluster bootstrap 95% interval has upper bound below zero;
3. challenger MAE is lower in at least 3 of 5 test seasons;
4. pooled Spearman does not decline;
5. pooled RMSE does not increase;
6. absolute pooled bias does not worsen by more than 1.00 point.

One shot. Rejection is final for this exact architecture: no alternate multiplier,
unweighted rescue, caps, calibration offsets, panel swaps, or threshold changes after the
result. A future architecture would require a new mechanism and new preregistration.

## Frozen diagnostics — report-only

These explain the aggregate result and cannot promote a challenger that fails any switch
condition:

- historical rows with `prior_games <= 12` versus `prior_games > 12`, a
  forecast-time-known split;
- historical rows with realized `target_games <= 12` versus `target_games >= 13`, an
  outcome-conditioned explanatory split that cannot be used at forecast time;
- 2026 scores for exactly:
  - Ricky Pearsall (`00-0039916`);
  - Rome Odunze (`00-0039919`);
  - Luther Burden III (`00-0040735`).

For the three cases, report the unchanged shipped projection, corrected-panel
`direct_total` refit, challenger PPG, challenger total at 16.5, and the already-existing
prior-season context (`prior_games`, `prior_ppg`, `prior_half_ppr`, `years_exp`,
`draft_pick`). No case-specific input changes or thresholds are allowed.

## Interpretation pre-commitment

- **PASS:** recommend replacing the non-rookie WR target architecture, subject to a
  separate explicit production authorization and full artifact/regression validation.
  The three player scores are illustrations, not the reason for the recommendation.
- **FAIL:** keep the direct-total production architecture. The Pearsall-only 119.42
  remains a scenario/sensitivity output, not a calibrated projection. Rome or Burden
  looking better cannot rescue the failed aggregate result.

This test does not compare against Sleeper or ADP and makes no claim of beating a market
forecast.

## Integrity

Before and after both structural check and fire:

- `wr_veteran_model.pkl` MD5 must remain
  `17dfbcf01054bdd5ce032f2b55df9ad2`;
- `wr_rookie_model.pkl` MD5 must remain
  `6c9a3f3ed02ce32c53594f383aade882`;
- every existing CSV under `fantasy/projections/results/` must remain byte-identical.

The harness writes no model, dataset, board, result CSV, or projection artifact.

## Structural check before fire

`wr_ppg_target_architecture_harness.py --check` passed before any challenger-wide
prediction was computed. SHA256:
`3858a976845c2cd9b3813bf08266cfdc9c1fa62575bbc7e176b469414080bec6`.

The check fixed the outer panel at 1,006 rows / 363 player clusters, with fold sizes
210, 212, 193, 199, and 192 for 2021–2025. PPG training rows expanded from 1,097 in
the 2021 fold to 1,800 in the 2025 fold; the final training set has 1,981 rows and
observed-games weights from 3 to 18. Both architectures use the same ordered 32 features
and identical test rows. All three case IDs were present exactly once in 2026. Synthetic
noise, planted-signal, and future-peek metric probes passed. Protected model and result
artifacts were unchanged. No real challenger metric or case score was printed.

## OUTCOMES (recorded after the fact; rules above were not modified)

Fired exactly once on 2026-07-26 using the frozen harness SHA256 above.

### Primary walk-forward result, all non-rookie WR rows

| Architecture | n | MAE | RMSE | Spearman | Bias: actual − prediction |
|---|---:|---:|---:|---:|---:|
| Direct season total | 1,006 | **31.071** | **43.999** | **.75341** | +1.983 |
| Games-weighted PPG × 16.5 | 1,006 | 39.679 | 50.198 | .72907 | −22.052 |
| Challenger delta | — | **+8.609** | **+6.198** | **−.02434** | absolute bias **+20.070** worse |

The player-clustered paired bootstrap interval for challenger-minus-incumbent MAE was
**[+6.919, +10.372]** across 363 player clusters and 2,000 seed-42 draws. The challenger
lost MAE in every test season:

| Test season | Direct-total MAE | PPG × 16.5 MAE | Challenger delta |
|---|---:|---:|---:|
| 2021 | 36.628 | 45.130 | +8.502 |
| 2022 | 29.808 | 40.585 | +10.777 |
| 2023 | 27.902 | 36.346 | +8.444 |
| 2024 | 31.937 | 40.225 | +8.288 |
| 2025 | 28.672 | 35.502 | +6.830 |

### Frozen switch-rule arithmetic

1. Required MAE delta ≤ −0.50; observed **+8.609: FAIL**.
2. Required bootstrap upper bound < 0; observed **+10.372: FAIL**.
3. Required MAE wins in at least 3/5 seasons; observed **0/5: FAIL**.
4. Required non-declining Spearman; observed delta **−.02434: FAIL**.
5. Required non-increasing RMSE; observed delta **+6.198: FAIL**.
6. Required absolute bias to worsen no more than 1.00; observed **+20.070: FAIL**.

**Verdict: REJECT. Do not switch the non-rookie WR production target architecture.**
All six frozen conditions failed, and the MAE damage is large, season-consistent, and
outside the player-clustered uncertainty interval.

### Why the three cases looked attractive

| Player | Shipped context | Corrected direct-total refit | Challenger PPG | PPG × 16.5 |
|---|---:|---:|---:|---:|
| Ricky Pearsall | 63.9 | 76.1 | 7.238 | **119.4** |
| Rome Odunze | 94.4 | 100.1 | 8.285 | **136.7** |
| Luther Burden III | 110.4 | 113.2 | 7.619 | **125.7** |

Those scores are report-only. Pearsall and Odunze both enter 2026 after 12 or fewer
games. On the frozen forecast-time-known historical split, the challenger worsened MAE
from **22.428 to 36.659** on `prior_games <= 12` rows (n=451) and moved bias from
+1.288 to −25.566. It also worsened MAE on `prior_games > 12` rows (n=539), 38.635 to
42.522.

The outcome-conditioned diagnostic shows the intended mechanism and its fatal tradeoff.
For players who ultimately played at least 13 games, PPG × 16.5 improved MAE from
37.308 to 34.567 (n=512). For players who ultimately played 12 or fewer, it worsened MAE
from 24.606 to 44.978 (n=494). Future games are unknown at projection time, so the healthy
slice cannot be used to choose the architecture. The fixed multiplier systematically
prices near-full availability and overprojects the short-season half of the panel.

Pearsall's 119.4, Odunze's 136.7, and Burden's 125.7 remain plausible healthy-season
scenarios, not calibrated season-total point forecasts and not evidence for a generic
architecture change.

Both protected model MD5s and every existing result CSV were byte-identical before and
after the fire. No production model, dataset, board, or result artifact changed.
