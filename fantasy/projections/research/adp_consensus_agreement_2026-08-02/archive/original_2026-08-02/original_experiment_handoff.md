# Claude handoff: current-model + Sleeper agreement against ADP

Work in `C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics`.

Read `..\CLAUDE.md`, `CLAUDE.md`, the Claude memory index, `fantasy/projections/GUIDE.md`, and the generating sections of `fantasy/projections/build_{rb,wr,te,qb}_projection.py` before computing anything. Treat Joseph's expected direction as a hypothesis, not evidence. If the numbers reject it, say so without hedging.

## Objective

Test whether the current season-total projection model and Sleeper's preseason projection agreeing in their disagreement with ADP identifies players who finish on the predicted side of ADP. Evaluate strict positional-rank disagreement thresholds greater than 5, 7.5, and 10 spots. Also report all same-direction, nonzero disagreements as the threshold-0 reference.

Use 2024-2025 as the primary "last couple years" panel. Report 2023-2025 as a stability panel and 2021-2025 as the full available out-of-sample context. Report each season on its own. Exclude 2020 because the stored Sleeper projection artifact is provenance-contaminated and near-actual.

This is descriptive post-hoc research requested on 2026-08-02. Do not call it preregistered or live-validated. Do not choose a winning threshold after seeing the results.

## Model and artifacts

Use the saved walk-forward predictions from the current `fantasy/projections` season-total models:

- RB: `fantasy/projections/results/walkforward_predictions.csv`
- WR: `fantasy/projections/results/wr_walkforward_predictions.csv`
- TE: `fantasy/projections/results/te_walkforward_predictions.csv`
- QB: `fantasy/projections/results/qb_walkforward_predictions.csv`
- Historical ADP and identity fields: `fantasy/seasonal_projections/season_dataset_2014_2025.csv`

Trace and cite the generator code before using the CSVs. Confirm that each walk-forward row represents a prediction for season Y trained only on seasons before Y. Verify row counts, columns, season coverage, uniqueness of `(season, player_id)`, and the join to the season dataset. Record SHA-256 hashes for every input in the output manifest.

"My model" means the raw current walk-forward `pred` column. Do not use the retired seasonal model, the old blended board, the 2026 fitted values, or `analyst_projection_adjustments_2026.csv`. Exclude QB rookie rows because the QB rookie arm was held from the shipped surface. Include veteran and rookie rows for RB, WR, and TE.

Use half-PPR observed season total `y` as the outcome. Do not filter injuries or games played because both projection systems forecast season totals and availability belongs in the target.

## Population and ranks

Build two analyses.

### A. Production-board analogue, primary

For each season-position:

1. Start with current-model walk-forward rows that join to the season dataset and have nonmissing `adp_half_ppr`, `pred`, and `y`.
2. Rank ADP by `adp_half_ppr` ascending with `method="min"`.
3. Rank the current model by `pred` descending with `method="min"` across the ADP-bearing model population.
4. Rank Sleeper by `sleeper` descending with `method="min"`; missing Sleeper rows retain a missing Sleeper rank.
5. Rank actual `y` descending with `method="min"` across the ADP-bearing model population.
6. Restrict signal evaluation to rows with all four ranks present.

This mirrors the current Draft Board's rank construction as closely as the historical artifacts permit.

### B. Common-universe ranks, required sensitivity

Within each season-position, first restrict to rows with nonmissing ADP, current-model prediction, Sleeper prediction, and actual total. Re-rank all four quantities inside that identical common universe. Repeat every table. A conclusion that changes between A and B must be reported as population-sensitive.

Do not use the stored `adp_pos_rank` without checking it against the reconstructed rank. Explain any discrepancy.

## Signal definitions

Use these signed gaps, where positive means the source ranks the player above ADP and negative means below ADP:

```text
model_gap   = adp_rank - model_rank
sleeper_gap = adp_rank - sleeper_rank
actual_gap  = adp_rank - actual_rank
```

The two projections agree against ADP at threshold `t` only when:

```text
sign(model_gap) == sign(sleeper_gap)
abs(model_gap) > t
abs(sleeper_gap) > t
```

Evaluate `t in {0, 5, 7.5, 10}` with strict `>` as Joseph requested. Since ranks are integers, explain that `>7.5` means at least 8 spots. Define:

```text
consensus_score = sign(model_gap) * min(abs(model_gap), abs(sleeper_gap))
```

Use the weaker of the two gaps so one extreme projection cannot carry the agreement label.

A directional hit requires `sign(actual_gap) == sign(consensus_score)` and nonzero `actual_gap`. Count an actual tie as a miss in the primary hit rate. Report tie counts and a sensitivity that excludes ties.

## Required results

For each threshold and panel, report:

- eligible n, hits, misses, ties, hit rate, Wilson 95% interval, mean actual gap, median actual gap, and Spearman correlation between `consensus_score` and `actual_gap`;
- results split by buy direction, fade direction, season, and position;
- pooled 2024-2025, pooled 2023-2025, and pooled 2021-2025;
- player-level 2024-2025 rows, sorted by threshold eligibility and consensus strength, with player, position, season, every rank and gap, actual total, hit/miss/tie, and veteran/rookie group;
- the largest 2024-2025 hits and misses for audit and possible video examples.

Mark any cell with `n < 10` as too small for a directional conclusion.

The main question is incremental confirmation, not agreement versus a nominal coin flip. Add these comparisons at each threshold:

1. Among current-model calls above the threshold, compare rows where Sleeper agrees with rows where Sleeper does not agree.
2. Among Sleeper calls above the threshold, compare rows where the current model agrees with rows where it does not agree.
3. Compare the agreement hit rate against an empirical null formed by permuting `actual_gap` within season-position 10,000 times while preserving signals, thresholds, and cell sizes.
4. Report the hit-rate lift and confidence interval for agreement versus each nonagreement comparator. Use stratified bootstrap resampling within season-position. Do not claim independence between the two projection systems.

Report 50% as a visual reference only. The empirical permutation baseline decides whether the observed result exceeds chance for this sample.

If sample size supports it, fit a descriptive logistic model for directional correctness using signed agreement, absolute model gap, absolute Sleeper gap, position, and season. Use it only to test whether agreement adds information after gap magnitude. Label unstable or separated fits and do not force a coefficient table when the data cannot support it.

## Freshness confound

Read the `SLEEPER FRESHNESS ASYMMETRY` section of `fantasy/seasonal_projections/PREREGISTRATION.md`. The stored Sleeper projection is a week-1-eve snapshot while Sleeper ADP is a late-frozen summer aggregate with no timestamp. Any positive result may capture late news that entered the projection after part of the ADP sample had already drafted.

Label the primary result as a late-draft, board-analogue signal, not pure forecast skill.

As a secondary robustness check, inspect `h11_freshness_signal.py` and `h12_volatile_signal.py`. If their local data and functions can reconstruct final dated Underdog ADP for the same 2021-2025 player-seasons without network access or changing frozen research artifacts, repeat the core thresholds against that contemporaneous final market. Keep this result separate because Underdog best ball differs from Sleeper half-PPR redraft. If the dated market cannot be joined cleanly, document the blocker and do not substitute another source.

## Outputs

Create this new, self-contained directory without modifying production code or existing research artifacts:

`fantasy/projections/research/adp_consensus_agreement_2026-08-02/`

Write:

- `adp_consensus_experiment.ipynb`: complete reproducible analysis with inline assertions;
- `threshold_summary.csv`: every panel, threshold, universe, position, season, and direction summary;
- `player_season_results.csv`: row-level joined data and all derived ranks, gaps, eligibility flags, and outcomes;
- `REPORT.md`: concise verdict, exact numbers, limitations, and video-safe claim language;
- `manifest.json`: input paths, SHA-256 hashes, row counts, join diagnostics, definitions, and run timestamp.

Prefer the notebook over a new `.py` file. Keep all new code inside the research directory. Do not change models, projection results, the Draft Board, preregistrations, or TikTok files.

## Integrity checks

The notebook must fail if:

- a walk-forward key duplicates within a position;
- a row fails the `(season, player_id)` join;
- a joined dataset position disagrees with the file's position;
- a test season falls outside 2021-2025;
- QB rookie rows survive the eligibility filter;
- a rank or gap uses a cross-position population;
- the summary cannot be reconstructed exactly from `player_season_results.csv`;
- any source artifact changes during the run.

Do not fetch new data. Do not rerun or retune projection models. Preserve null and negative results. End your response with the report path and a short table containing the 2024-2025 pooled results at thresholds 0, >5, >7.5, and >10 for both rank universes.
