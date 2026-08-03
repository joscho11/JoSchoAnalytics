# Claude handoff: point-in-time leakage audit for the ADP-consensus study

Work in:

`C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics`

Joseph wants a defensible answer to one question: does any form of outcome leakage contaminate the model plus Sleeper agreement results?

Joseph's main concern is the historical Sleeper projection itself. The historical endpoint may expose a value revised with regular-season information, as the project confirmed for 2020. A less severe possibility is that Sleeper froze its projection near the opening kickoff while ADP represents drafts accumulated across the summer. Either case could explain part of the agreement rate without our model adding forecast skill. Audit this as the central risk, not a footnote.

Perform a read-only audit. Do not modify the research notebook, production code, datasets, models, results, memory, or project documentation. Do not install packages or register kernels. Use existing environments and terminal analysis. Return the complete audit in your response.

Read-only network requests are allowed for official Sleeper documentation, the current historical endpoint, public web archives, and dated third-party snapshots. Do not write fetched data into the repository or overwrite any local cache. A current re-fetch can establish endpoint stability; it cannot prove what Sleeper displayed before a historical season unless a dated copy supports it.

## Read first

Read:

- `CLAUDE.md`
- `memory/MEMORY.md`
- `memory/prefer-ipynb-not-py.md`
- `fantasy/projections/GUIDE.md`
- `fantasy/seasonal_projections/GUIDE.md`
- `fantasy/projections/research/adp_consensus_agreement_2026-08-02/README.md`
- all eight active notebooks, `00_shared_pipeline.ipynb` through `07_synthesis_and_reproducibility.ipynb`
- every file under the active `interim/` and `artifacts/` directories
- the archived monolithic notebook and move receipt under `archive/monolithic_2026-08-02/`
- the archived original notebook, report, manifest, and handoffs under `archive/original_2026-08-02/`
- `fantasy/projections/build_{rb,wr,te,qb}_projection.py`
- `fantasy/seasonal_projections/build_season_dataset.py`
- `fantasy/seasonal_projections/fetch_adp.py`
- `fantasy/seasonal_projections/snapshots.py` and its manifest
- the code that generates every rookie college, combine, and PFF feature used by the four projection builders
- the applicable point-in-time and Sleeper-freshness sections of `fantasy/seasonal_projections/PREREGISTRATION.md`

## Current pipeline architecture

Claude split the former 65-cell monolith into this active pipeline:

```text
00_shared_pipeline.ipynb               shared paths, parameters, ranks/signals, scoring, inference
01_data_and_provenance.ipynb           hashes, generator audit, joins, population filter
02_ranks_and_signals.ipynb             rank universes, populations, gaps, agreement
03_main_results.ipynb                  primary tables and undrafted-tail artifact
04_stability.ipynb                     panels, seasons, positions, veteran/rookie
05_inference.ipynb                     permutation null, bootstrap lifts, logistic analysis
06_freshness_and_player_audit.ipynb    dated Underdog market and player calls
07_synthesis_and_reproducibility.ipynb reconstruction, hashes, structural audit, manifest, verdict
```

The eight notebooks contain 124 cells. Each stage loads code from `00_shared_pipeline.ipynb` through `json` plus `exec` with `RUN_TESTS=False`. Stage handoffs use `interim/`. Each stage prints the shared notebook's SHA-256. The monolith remains byte-preserved under `archive/monolithic_2026-08-02/`.

Audit the active eight-stage pipeline. Use the monolith as a regression reference, not as the current implementation.

Prove that each stage loaded the same shared-library bytes, consumed the intended upstream handoff, and did not reuse a stale `interim/` file from another run. Check whether every handoff carries enough provenance to bind it to the source inputs, shared-library hash, parameters, and upstream stage. Running notebooks in a fresh process must reproduce the same deterministic outputs without hidden state from an earlier notebook.

`RUN_TESTS=False` means consumer stages skip the shared notebook's inline tests. Identify where the active pipeline runs those tests and whether stage 07 proves they passed for the exact shared-library hash loaded by stages 01 through 06. A matching hash proves code identity; it does not prove the tests ran in each consumer namespace.

## Known provenance gap that the audit must resolve

The active pipeline's generator audit now lives in `01_data_and_provenance.ipynb`. It reads the current `walk_forward()` and treats it as proof of how the saved prediction CSVs were generated. That is insufficient.

The saved files have these timestamps:

- RB walk-forward: 2026-07-21 19:19
- WR walk-forward: 2026-07-21 21:28
- TE walk-forward: 2026-07-21 22:56
- QB walk-forward: 2026-07-21 23:48

The current builders changed after those outputs. TE and QB changed July 24, while RB and WR changed by July 26. The current `season_dataset_2014_2026.csv` was created July 26, five days after the predictions. The original experiment manifest hashes the walk-forward CSVs and the later `season_dataset_2014_2025.csv`; it does not hash the exact builder source or exact training dataset that produced the July 21 predictions.

Recover the generating logic and input version before declaring the predictions clean. Search repository history, retained scratch directories, logs, archived files, notebook scratchpads, and other persisted sources. Do not call the provenance unrecoverable while any generating source remains available. Establish whether the tracked July 21 source and its contemporaneous dataset match the files that produced the saved predictions. Use hashes or exact reproduction where possible.

## Distinguish these questions

Give separate verdicts for:

1. Direct target leakage into the projection model.
2. Point-in-time feature leakage, including information unavailable at the intended draft-time cutoff.
3. Sleeper projection and ADP timestamp contamination. Split this into outcome leakage and a non-leaking cutoff mismatch.
4. Leakage or outcome use inside the agreement-analysis notebook.
5. Post-hoc selection, repeated reuse of 2021 to 2025 outcomes, and threshold multiplicity. These can inflate confidence without constituting row-level leakage.
6. Freshness asymmetry. This can create a useful late-draft signal without constituting outcome leakage.

Do not collapse those into one clean/dirty label.

## Audit the model walk-forward

For each position and veteran/rookie arm, prove or refute:

- outer test season Y trains on outcome seasons strictly before Y;
- model-family and hyperparameter selection sees training seasons only;
- preprocessing statistics, imputation values, feature eligibility, and missingness handling are fitted on training rows only;
- no test-season outcome affects row inclusion, feature selection, model choice, or preprocessing;
- the target `y` and any target-derived columns stay out of the feature matrix;
- the exact saved prediction is reproducible from the recovered source and recovered inputs, or explain the narrowest unresolved provenance gap;
- no later model or dataset rebuild was mixed into only part of the 2021 to 2025 panel.

Inner leave-one-season-out folds may use later seasons within the outer training window. Classify that correctly: it can bias inner-CV diagnostics but does not leak the outer test season when all inner rows precede outer Y.

## Build a feature availability ledger

For every feature used by any saved walk-forward arm, report:

- feature name and position/group;
- source file or endpoint;
- transformation and lag;
- latest source date used for prediction season Y;
- intended availability cutoff;
- clean, contaminated, or unresolved status;
- number and percentage of drafted-board agreement calls affected by any fallback or unresolved provenance.

Audit at least these seams in code and data:

- all `prior_*`, `ppg_2yr`, `ppg_3yr`, `ppg_trend`, and `career_high_ppg` shifts;
- `age`, `years_exp`, draft capital, combine inputs, college production, and college PFF fields;
- `context_team`, including the stats-team fallback for players absent from the week-1 roster;
- `coach_changed` and `qb_changed`;
- `vacated_target_share` and `vacated_rush_share`;
- depth-chart features and proof that they were excluded from the July 21 feature matrices;
- current-season roster, schedule, depth-chart, and player metadata fields;
- name-based rookie fallback joins and entry-year alignment;
- reconstructed zero-game seasons and whether reconstruction uses knowledge after prediction season Y to decide a training or test row exists.

Week-1 information may be clean for a week-1-eve forecast while still being newer than summer-average ADP. State the cutoff used for each claim.

## Audit Sleeper and ADP provenance

The Sleeper endpoint exposes historical values without observation timestamps. The project quarantines 2020 because its stored projections resemble realized outcomes. Do not infer that 2021 to 2025 are clean from comments alone.

Test two separate hypotheses.

### Hypothesis S1: Sleeper historical projections contain regular-season results

Sleeper may have overwritten a preseason field during or after the season, or its historical endpoint may now return a terminal state that incorporates games played, injuries, or realized statistics. The known 2020 contamination is the positive control. Use it to calibrate tests, then apply the same tests blind to 2021 through 2025.

For each season and position, compare every available Sleeper component with realized NFL data, including projected `gp`, passing, rushing, receiving, touchdowns, receptions, and half-PPR points. Report:

- Pearson and Spearman correlations with the matching realized component;
- exact matches, near-exact matches, suspicious integer or rounding relationships, and player-level examples;
- the share of projected `gp` values equal to realized games played;
- whether projected `gp` forms a preseason full-slate distribution or mirrors player-specific missed games;
- whether component totals reconcile to Sleeper projected points and whether those components resemble final box scores;
- anomaly scores using 2020 as the contaminated reference and clean dated preseason sources as negative controls;
- early injury busts, season-ending injuries, suspensions, holdouts, and late-season absences that a clean preseason projection should fail to foresee;
- players whose realized workload changed after Week 1 through injury, trade, benching, or breakout, and whether Sleeper's stored projection tracks the later event.

High correlation alone does not prove contamination because Sleeper may forecast well. Give more weight to impossible foresight, realized-game matching, component-level equality, and dated-source disagreement.

### Hypothesis S2: Sleeper had a later information cutoff than ADP

Sleeper may have published a clean projection near the season opener while `adp_half_ppr` remained a summer-long aggregate. That is a freshness advantage, not outcome leakage, but it can create the measured agreement signal.

Do not assume that ADP "going until the last moment" cancels this advantage. Establish how Sleeper constructs historical ADP if possible: last draft only, rolling average, weighted recent window, or full-period average. A final ADP value can include late drafts while retaining substantial weight from older drafts. Compare the latest plausible information timestamp and effective averaging window for both series.

Test whether late preseason news explains the agreement calls:

- classify calls involving training-camp injuries, depth-chart decisions, suspensions, trades, signings, or role changes after much of the ADP sample formed;
- recompute results after excluding those calls;
- compare Sleeper ADP with the final dated Underdog window and any other retained dated market snapshots;
- compare the stored Sleeper projection with dated preseason projections or rankings captured before final cuts, when available;
- report results under a strict common-cutoff population where both projection and market evidence existed by the same date.

If ADP timing or weighting cannot be established, say so. Do not describe two unknown timestamps as matched.

Reproduce and extend the existing contamination probes for each season:

- projection games-played distribution and its relationship to realized games;
- correlation of Sleeper projected points with realized points, compared with ADP and surrounding seasons;
- known injury busts and late-season absences that distinguish preseason projections from realized values;
- refetch stability evidence and any retained dated snapshots;
- comparison with dated Underdog windows where identity coverage permits;
- field-level checks for impossible post-outcome values.

Search for dated historical copies before settling for inference: web archives, public repositories, prior local caches, old notebook outputs, downloaded CSVs, and package caches. Record source dates and hashes for any candidate snapshot. A re-fetch that matches the current local cache proves stability since the local fetch date, not preseason provenance.

Add a contamination stress test. Starting from a market projection with no realized input, inject increasing amounts of realized rank or realized component statistics into the Sleeper signal. Measure how much contamination would be required to reproduce the observed agreement hit rates at each threshold. Label this a sensitivity analysis rather than an estimate of contamination unless the component tests identify a defensible contamination fraction.

Classify 2021 to 2025 as verified point-in-time, empirically consistent with preseason but unverified, or contaminated. Absence of a timestamp prevents the strongest classification unless a dated archive exists.

## Audit the agreement pipeline

Trace the signal from stages 01 through 03 and the inference inputs in stage 05. Prove that model rank, Sleeper rank, ADP rank, agreement direction, threshold eligibility, drafted top-180 membership, and all comparison groups use no realized outcome. Confirm that `actual_rank` and `actual_gap` enter only after signal eligibility and serve only as outcomes.

Check that:

- ranks stay within season-position;
- universe A and B restrictions use prediction/market availability rather than realized performance;
- the top-180 control uses preseason overall ADP;
- no injury, games-played, season-total, or availability filter defines the signal population after outcomes are known;
- the permutation and bootstrap procedures do not feed results back into threshold choice;
- ties and missing values cannot inflate hit rates through selective exclusion.

Audit the `interim/` schemas as data-flow boundaries. A handoff may contain realized outcomes for later scoring, but stages that define ranks, agreement, eligibility, or population membership must not use those columns. Check column access in code rather than relying on stage descriptions.

## Audit the resampling correction

The split pipeline exposed an order-dependence bug in the archived monolith's permutation and bootstrap resamplers. The monolith drew within strata in construction order. The active pipeline reads sorted CSV handoffs, so the same seed produced different Monte Carlo draws. Claude changed both resamplers to use `canonical_strata`, sorting by season, position, and player ID before drawing.

The reported comparison is:

- all deterministic point estimates and the 1,346-row summary grid match the archive;
- bootstrap confidence bounds moved by at most 0.0071;
- one permutation p-value moved from 0.0001 to 0.0002;
- `ci_crosses_zero` changed in 0 of 96 comparisons;
- no substantive verdict changed.

Verify those statements from the archived and active artifacts. Then audit the correction itself:

- canonical sort keys must produce a unique and stable order inside every resampling stratum;
- no sort key may use realized outcome, hit status, gap magnitude, ADP, or projection value;
- missing or duplicate player IDs need an explicit stable tie-breaker that carries no outcome information;
- shuffling input rows before calling either resampler must produce identical results at a fixed seed;
- population, universe, panel, threshold, and comparator enumeration order must not change the random stream assigned to a cell;
- permutation must preserve signal labels and cell sizes while reassigning outcomes within the declared season-position exchangeability block;
- bootstrap must implement the documented stratified estimand and must not pair or unpair agreement comparators through row-order accidents.

Run the order-invariance test across each population, universe, panel, and threshold rather than relying on one planted fixture. Distinguish three conclusions: leakage, reproducibility, and inferential design. The old order dependence is a reproducibility defect. It becomes a leakage concern only if outcome information determines the order. Repeated players across seasons or an incorrect resampling unit can weaken confidence intervals without leaking outcomes; report that under inferential design.

## Required sensitivity tests

Run these without changing saved artifacts:

1. Restrict to rows whose feature provenance is verified at the chosen cutoff. Recompute drafted-board threshold results and incremental lift over Sleeper.
2. Remove all season-Y contextual features (`coach_changed`, `qb_changed`, `vacated_*`, and rows using the `context_team` fallback) from a clean reproduction if the exact old pipeline can be rerun. Report whether the conclusion changes.
3. Run a shuffled-target negative control within training season-position. Model performance should collapse without changing the market baselines.
4. Test each feature for suspicious same-season alignment by comparing its association with outcome Y against the correctly lagged source. Investigate any feature whose behavior matches a season-Y statistic more than its documented lag.
5. Restrict the agreement study to 2021 to 2025 Sleeper rows that pass the empirical preseason-provenance probes. Report counts and results.
6. Recompute after excluding every identity join that relies on normalized name rather than stable player ID. Report changed rows by player and season.
7. Remove calls tied to late-preseason news and recompute the drafted-board hit rates and incremental lift over Sleeper.
8. Use the best dated common-cutoff projection and market pair available. Recompute the core thresholds on matched players and compare them with the primary result.
9. Run the contamination-injection stress test and report the injected realized-information level needed to match the stored-Sleeper result.
10. Shuffle every stage-05 input within its declared stratum under several fixed seeds. Require bit-identical permutation and bootstrap outputs between original and shuffled order, then compare active versus monolithic inference values and `ci_crosses_zero` decisions.

Do not use the high agreement hit rate as evidence that the inputs are clean. Leakage can create that rate.

## Verdict standard

Use one of these labels for each of the six audit categories:

- `CLEAN`: exact source and input provenance recovered, cutoff verified, and tests found no prohibited information.
- `LIMITED CONFIDENCE`: no confirmed leakage, but missing timestamps or unrecovered historical inputs prevent certification.
- `CONTAMINATED`: confirmed use of outcome-season or post-outcome information.
- `NOT APPLICABLE`: for a bias category that is not leakage, followed by its effect on inference.

The overall verdict cannot be stronger than the weakest category that can produce the reported signal.

## Response format

Return:

1. A one-sentence answer to Joseph's question.
2. A compact table with each leakage category, verdict, evidence, affected row count, and impact on the headline.
3. The provenance chain for the July 21 prediction files, including the exact source and training-data versions or the unresolved break.
4. The feature availability ledger, grouped where features share one source and lag.
5. Results of the ten sensitivity tests with sample sizes and deltas from the published drafted-board rates.
6. A separate resampling verdict covering order invariance, inferential design, and the active-versus-monolith numerical differences.
7. A final claim license: what Joseph may say now, what must wait, and whether the current video premise survives.

Treat Joseph's desire for confidence as a request for evidence, not reassurance. If the audit cannot certify the historical Sleeper snapshot or exact prediction generator, say `LIMITED CONFIDENCE` and identify the smallest missing proof.
