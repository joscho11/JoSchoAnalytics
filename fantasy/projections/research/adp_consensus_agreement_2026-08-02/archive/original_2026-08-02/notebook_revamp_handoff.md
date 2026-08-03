# Claude handoff: turn the ADP-consensus experiment into a followable notebook pipeline

Work in this repository:

`C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics`

The existing experiment is here:

`fantasy/projections/research/adp_consensus_agreement_2026-08-02/`

Use that directory as the canonical project folder. Do not create another copy elsewhere in `fantasy/`.

## Read first

Read these files before changing anything:

- `CLAUDE.md`
- `fantasy/GUIDE.md`
- `fantasy/projections/GUIDE.md`
- `memory/MEMORY.md`
- `memory/prefer-ipynb-not-py.md`
- every current file in `fantasy/projections/research/adp_consensus_agreement_2026-08-02/`
- `..\CLAUDE_ADP_CONSENSUS_EXPERIMENT.md`, if it still exists

Also read the generating sections of `fantasy/projections/build_{rb,wr,te,qb}_projection.py` that created the walk-forward artifacts. The saved CSVs contain outputs, while those scripts establish how Claude produced them.

Treat the existing report as a result to reproduce, not as evidence that can replace execution. Recompute all reported values from the hashed inputs. If a recomputed number differs, use the recomputed number and explain the discrepancy without hedging.

## Objective

Revamp the experiment into one clear, linear, executed notebook pipeline that Joseph can follow from the research question through the video-safe conclusion.

The active source of truth must be:

`fantasy/projections/research/adp_consensus_agreement_2026-08-02/adp_consensus_pipeline.ipynb`

All lasting analysis code, study definitions, result explanations, limitations, conclusions, and content guidance must live in that notebook. Companion CSV and JSON files may remain only as machine-readable outputs generated and documented by the notebook. Do not keep an active `REPORT.md` with analysis found nowhere in the notebook. Do not add a persistent `.py` analysis or validation script.

The statistical verdict must remain faithful to the recomputed results. The current result says that the full-population 80 to 92 percent headline comes from the undrafted tail, the drafted-board agreement cell beats its empirical chance baseline, and the five-season data do not establish incremental value from our model beyond Sleeper alone at thresholds above zero. Do not weaken or strengthen those conclusions unless the rerun supports the change.

## Required notebook structure

Follow the standing rule in `memory/prefer-ipynb-not-py.md` without exceptions.

The notebook must start with a standalone markdown cell headed `# Introduction`. It must state the research question, primary and sensitivity populations, inputs, pipeline map, expected outputs, post-hoc status, and the distinction between beating chance and adding value beyond Sleeper.

Every code cell must use this exact three-cell pattern:

1. A markdown cell immediately above it with a heading that begins `### Explain`.
2. The code cell.
3. A markdown cell immediately below it with a heading that begins `### Interpretation`.

The Explain cell must cover the code cell's purpose, inputs, output, transformation, assumptions, and integrity checks in plain technical language. Joseph is an AI/ML engineer, so explain the experiment and the data logic without teaching basic Python.

The Interpretation cell must discuss the output produced by that code cell. Quote the key counts or estimates, explain what they support, note relevant caveats, and state how the result affects the next pipeline step. A generic statement about what the cell should produce does not count. If a setup cell only creates functions or constants, make it print a concise configuration or validation record that its Interpretation cell can analyze.

Do not place code cells next to each other. Do not use the Introduction cell as the Explain cell for the first code cell. Keep code visible and broken into sections small enough to follow. Use markdown tables, displayed DataFrames, plots, and assertion output where they help, but do not add decoration that does not clarify a result.

The last cell must be a standalone markdown cell headed `# Conclusion and Next Steps`. It must state the supported verdict, the claims the study rejects, sample-size and freshness limitations, what can be said in a video, what cannot be said, and the next honest validation step for 2026.

## Pipeline content

Build the notebook in this order. Use more than one Explain/code/Interpretation triplet inside a stage when that improves readability.

1. Study configuration and provenance. Define paths relative to the repository, parameters, seasons, thresholds, rank universes, populations, seed, and resampling counts. Display the resolved configuration.
2. Input hashes and generator audit. Hash every source, cite the generator logic, and show that each walk-forward prediction for season Y used only seasons before Y.
3. Load and join integrity. Verify schemas, row counts, uniqueness, joins, position consistency, season coverage, Sleeper coverage, and the QB-rookie exclusion.
4. Rank construction. Rebuild universe A and universe B within season-position, explain why stored `adp_pos_rank` is unused, and carry both the full ADP-bearing and drafted top-180 populations.
5. Signal and outcome construction. Define model, Sleeper, and actual gaps; same-direction eligibility; strict thresholds 0, greater than 5, greater than 7.5, and greater than 10; tie handling; and the weaker-gap consensus score.
6. Main threshold results. Show pooled 2024 to 2025 results for both rank universes and both populations. Make the undrafted-tail artifact visible with counts and ADP distribution summaries.
7. Stability results. Show pooled 2023 to 2025 and 2021 to 2025 panels, plus per-season and per-position results. Mark every cell with fewer than 10 calls as too small for a directional conclusion.
8. Empirical null and incremental comparisons. Run the within-season-position permutation test and the stratified bootstrap comparisons against model-only and Sleeper-only calls. Keep beating chance separate from adding value beyond Sleeper.
9. Descriptive logistic check. State the outcome direction and explain why this check tests Sleeper improving our model, not our model improving Sleeper.
10. Freshness sensitivity. Reproduce the dated Underdog check without network access and keep its format difference explicit.
11. Player-level audit. Show the drafted-board examples, with hits and misses, ranks, gaps, season totals, injury caveats, and call strength. Do not turn those examples into 2026 player recommendations.
12. Artifact export and reproducibility checks. Write the generated outputs, verify that summaries reconstruct from row-level data, rehash unchanged inputs, and display a compact pass/fail audit.
13. Final synthesis. Put the complete old report's useful analysis, limitations, and video-safe language into notebook markdown so the notebook stands alone.

## Active outputs and archive

After the new notebook reproduces the study, use this layout:

```text
fantasy/projections/research/adp_consensus_agreement_2026-08-02/
  adp_consensus_pipeline.ipynb
  artifacts/
    threshold_summary.csv
    player_season_results.csv
    incremental_comparisons.csv
    manifest.json
  archive/
    original_2026-08-02/
      adp_consensus_experiment.ipynb
      REPORT.md
      threshold_summary.csv
      player_season_results.csv
      incremental_comparisons.csv
      manifest.json
      original_experiment_handoff.md
      notebook_revamp_handoff.md
```

The archive records the original run and handoffs. The active notebook is the only narrative and code source of truth. Shared production inputs stay in their existing production locations; do not copy multi-use projection datasets or models into this research folder. The notebook must name and hash those upstream inputs.

Relocate `..\CLAUDE_ADP_CONSENSUS_EXPERIMENT.md` into the archive as `original_experiment_handoff.md`. Relocate this handoff into the archive as `notebook_revamp_handoff.md` after you have read it. Re-read and hash each exact source immediately before moving it. Do not move or delete any adjacent file. Preserve the original artifacts byte for byte in the archive.

## Execution and output retention

The current notebook has no stored outputs. Fix that in the new notebook.

Execute every code cell in order in one stateful Python process and retain useful outputs in the `.ipynb`. Use an available Jupyter kernel if one exists. If no registered kernel exists, first check whether the available environment has `ipykernel`, `nbclient`, or `nbformat`. A workspace-local temporary kernelspec is acceptable. If kernel execution remains unavailable, execute cells in one process and write captured text, tables, and figures into notebook outputs with `nbformat`. Do not claim notebook execution based only on a successful terminal run that leaves the notebook blank.

Set sequential execution counts. Keep compact outputs that each Interpretation cell can cite. No code cell may contain an error output. Definition and setup cells must print a small verification record so their interpretation is grounded in observed state.

After execution, revise every Interpretation cell against the stored output. If a value changed, the stored output wins. Do not leave placeholders such as "this should show" or "we expect."

## Required structural and numerical validation

Parse the finished notebook as JSON and hard-fail unless all of these checks pass:

- the first cell is markdown and begins with `# Introduction`;
- the last cell is markdown and begins with `# Conclusion and Next Steps`;
- every code cell's immediate predecessor is markdown with a heading beginning `### Explain`;
- every code cell's immediate successor is markdown with a heading beginning `### Interpretation`;
- no two code cells are adjacent;
- every code cell has an execution count;
- no code cell contains a traceback or error output;
- every active analysis function and every export is defined in `adp_consensus_pipeline.ipynb`, not in a new helper script;
- the notebook reconstructs every exported summary from its row-level data;
- the numerical result agrees with the archived run, or the notebook documents and resolves each difference;
- all source hashes match before and after execution.

The finished notebook must display the structural audit result in its final reproducibility section. Temporary terminal commands used to manipulate notebook JSON are acceptable, but do not leave behind scratch scripts.

## Scope fences

Do not fetch data, rerun projection training, retune models, change production code, alter the Draft Board, modify the TikTok project, or rewrite preregistrations. Preserve negative and null results. Do not describe post-hoc threshold results as preregistered or live-validated. Do not claim that our model adds value beyond Sleeper when the five-season drafted-board confidence intervals cross zero.

## Response

Complete the revamp before responding. Then report:

- the exact absolute folder path;
- the exact active notebook path;
- the number of markdown and code cells;
- the structural validator result;
- the execution method and whether outputs are stored;
- whether every archived artifact matches its pre-move hash;
- the recomputed one-paragraph verdict, including the five-season incremental confidence intervals over Sleeper at greater than 5, greater than 7.5, and greater than 10.

Do not stop after proposing the layout. Implement it, execute it, validate it, and return the paths and audit results.
