# Generic WR PPG × constant-games sensitivity — frozen 2026-07-26

## Question

Does separating scoring rate from availability materially change Ricky Pearsall's 2026
projection under a generic model that could later be validated for all WRs?

This is a Pearsall-only scoring sensitivity. Historical WR rows may be used for fitting,
but no other player prediction or model-quality metric may be computed. Nothing here can
promote a production architecture.

## Blindness disclosure

This run follows the negative generic-feature result: total-points baseline 76.06,
neutral-points 76.06, active-role 75.19. Pearsall's scenario range and all earlier
sensitivities are known. The architecture is therefore outcome-aware. Its only clean
provenance is that the existing seasonal totals work already found PPG multiplied by a
fixed 16.5 games superior to a learned availability model.

## Frozen panel and features

- Panel: non-rookie WR rows, seasons 2014–2026, from the corrected
  `season_dataset_2014_2026.csv`.
- Features: the exact ordered 32-column veteran WR feature contract. No new feature.
- Historical labels:
  - `target_ppg` from the corrected season dataset;
  - `target_games` from the same row, used only as a training weight in one variant.
- Training rows: observed 2014–2025 non-rookie WR seasons with `target_games > 0` and a
  non-missing `target_ppg`.
- Scored row: Ricky Pearsall 2026 only (`00-0039916`).
- Learner: fixed LightGBM (`objective="mae"`, `num_leaves=15`,
  `learning_rate=0.03`, `n_estimators=400`, `random_state=42`).
- Total conversion: `projected_ppg × 16.5`, clipped below at zero. The constant is fixed
  from the prior availability experiment, not chosen from Pearsall's output.
- No ADP, Sleeper, depth chart, current roster data, player-name flag, or manual injury
  override enters a feature or fit.

## Frozen variants

1. `total_baseline`: identical fixed learner trained on season-total half-PPR, retained
   only to reproduce the corrected 76.1 comparator.
2. `ppg_unweighted`: learner trained on `target_ppg`, every active season equal weight.
3. `ppg_games_weighted`: same learner and labels, `sample_weight = target_games`, so a
   17-game rate estimate is trusted more than a two-game rate estimate.

Fit all three on their frozen rows and score only Pearsall. Report the two PPG estimates
and their 16.5-game totals. Do not change the multiplier, add a cap, blend variants, or
select a preferred result after scoring.

## Integrity

Before and after:

- `wr_veteran_model.pkl` MD5 must remain
  `17dfbcf01054bdd5ce032f2b55df9ad2`;
- `wr_rookie_model.pkl` MD5 must remain
  `6c9a3f3ed02ce32c53594f383aade882`;
- every existing result CSV must remain byte-identical.

No dataset, board, production model, or result artifact may be written.

## Structural note before scoring

The label check found two historical WR seasons with 18 recorded games, a legitimate
trade/across-bye edge case. Training weights therefore retain the observed 3–18 range
without clipping. No projection had been computed when this was recorded.

## OUTCOME

Scored once on 2026-07-26. The fixed season-total baseline reproduced 76.06. The generic
PPG architectures produced:

| Variant | Pearsall projected PPG | Total at 16.5 games |
|---|---:|---:|
| `ppg_unweighted` | 7.134 | **117.71** |
| `ppg_games_weighted` | 7.238 | **119.42** |

The result reaches Pearsall's independently constructed 110–125 scenario center without
a player-specific feature, healthy-week selection, target-share override, TD assumption,
or tuned multiplier. The games-weighted model is 1.71 points higher because it trusts
longer observed seasons more heavily.

**Verdict: developmental architecture candidate, not validated for production.** The
test establishes only that a generic PPG × fixed-games decomposition resolves Pearsall's
season-total suppression. No other player prediction or cross-player accuracy metric was
computed, so it does not establish that either PPG variant improves WR forecasts.
Protected models and all existing result CSVs remained byte-identical.
