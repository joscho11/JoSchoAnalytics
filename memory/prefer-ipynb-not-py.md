---
name: prefer-ipynb-not-py
description: In this repo, new shared/library code goes in .ipynb notebooks, and every notebook pipeline uses explain-code-interpret cell triplets with an introduction and conclusion
metadata:
  type: feedback
---

In JoSchoAnalytics, prefer `.ipynb` (Jupyter notebooks) over `.py` modules for any
new file. When extracting/refactoring code into something shared between
notebooks, create an `.ipynb` with the repo's standard **markdown → code →
inline-test** cell pattern. Consume it from other notebooks via `json.load` + `exec` over its code cells (see `betting/predict_betting.ipynb` cell 28 for the canonical pattern). `%run` is brittle across runners (papermill / nbclient / VSCode); json+exec works everywhere.

Each cell must make sense on its own, be testable, and follow best practices
(self-contained, re-runnable, no hidden state mutations the consumer doesn't expect).

**Why:** The repo is notebook-centric — every existing piece of code lives in a
notebook (`predict_betting.ipynb`, `model_comparison.ipynb`, `data_pipeline.ipynb`,
fantasy `features.ipynb` / `model.ipynb`, dfs `optimizer.ipynb` / `dfs_pipeline.ipynb`).
The CLAUDE.md spec documents the markdown→code→inline-test convention. User
explicitly corrected a `.py` extraction in 2026-05-23 and asked for `.ipynb`
with testable cells instead. .py modules break that convention.

**How to apply:**
- When a refactor wants to share code, create `<name>.ipynb` not `<name>.py`.
- Structure: title md → parameters md+code (RUN_TESTS flag) → imports → constants → helpers (each with md→code→test) → main function → integration test.
- Consume via `json.load` + `exec` over each code cell (see `betting/predict_betting.ipynb` cell 28); set `RUN_TESTS = False` in the caller's namespace before the load to skip inline tests during production runs.
- Do NOT create scratch .py files for smoke tests — put tests inline in the notebook.
- One exception: setup/automation scripts (CI, retrain helpers like `betting/experiments/*.py`) stay as .py — they aren't shared notebook code.
- Second exception, granted by Joseph 2026-08-03: **guard/contract modules that several notebooks must import** stay as .py. `futures/season_team_totals/tier_lock.py` is the case — a Tier-C lock that every downstream notebook calls should be *imported*, not reconstructed by exec-ing another notebook's code cells, because exec-ing means N copies that can drift. It carries its own `python tier_lock.py` self-test (10 red / 5 green controls).

Related: [[notebook-edit-via-json]] (notebooks are edited via `json.load/dump`, not Read/NotebookEdit tools, for large files).

## Required notebook-pipeline structure

Whenever Joseph asks for a notebook pipeline, use as many cells as the work needs and enforce this structure in every notebook:

1. Begin with a markdown **Introduction** cell that states the objective, inputs, the notebook's pipeline stage, and its expected outputs.
2. Put a markdown **Explain** cell immediately before every code cell. It must state the code cell's purpose, inputs, outputs, transformations, assumptions, and checks at a level Joseph can follow.
3. Put a markdown **Interpretation** cell immediately after every code cell. It must explain the executed output, quote the important values, analyze what they mean, name caveats, and state how the result affects the next pipeline step. Generic or prospective interpretations do not count.
4. Never place code cells next to each other. The required sequence is `Explain markdown -> code -> Interpretation markdown`.
5. End with a markdown **Conclusion and Next Steps** cell that summarizes supported findings, limitations, and the downstream stage.
6. Execute the notebook, retain useful outputs, and verify that every interpretation matches those outputs. The observed numbers override the expected direction.

Keep all lasting analysis logic, result explanations, and conclusions in the notebooks. Project-specific generated artifacts may sit beside them when a notebook creates and documents those artifacts, but a separate report must not contain unique analysis that the notebooks omit.

## When a notebook pipeline gets large, split it (2026-08-03)

Joseph, on a 65-cell research notebook: *"that is a very large notebook, can you break that into
separate notebooks that make sense in layout?"* One notebook per pipeline STAGE, not one notebook
per project. Target a reading unit of roughly 10-25 cells.

**The shape that worked** (`fantasy/projections/research/adp_consensus_agreement_2026-08-02/`):

- `00_<name>_shared.ipynb` - a LIBRARY notebook holding paths, pinned parameters and every analysis
  function, with its own inline test cells. Run standalone it is a full self-test.
- `01_…` … `07_…` - one stage each, numbered in run order. Every stage's first code cell loads the
  library with the repo's json+exec pattern and `RUN_TESTS = False` / `SHARED_VERBOSE = False`.
- Stage-to-stage state goes through an `interim/` directory, final outputs to `artifacts/`.
- Each stage prints the library's SHA-256, so "all stages ran the same library" is checkable rather
  than assumed.
- A short navigational `README.md` mapping run order. Map only - never analysis.

**Two traps found doing it:**

1. A stage notebook that audits notebooks (structure, execution counts, stored outputs) cannot see
   its own executed state on the pass that writes it. Execute the pipeline **twice**: on the second
   pass every file on disk is complete, so the audit decides against real artifacts. Exclude the
   auditing cell itself from any error-output scan or it fails forever on its own traceback.
2. Splitting changed **row order** (construction order -> sorted CSV), which silently changed
   stratified permutation/bootstrap draws. Point estimates were bit-identical, CI bounds moved.
   Canonicalise strata inside the resampler; assert order-invariance.

**Regression bar for a split:** every deterministic point estimate must be bit-identical to the
pre-split run. Monte Carlo quantities may differ within tolerance, but any verdict-bearing flag
(e.g. "CI crosses zero") must not move.
