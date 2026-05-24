---
name: prefer-ipynb-not-py
description: In this repo, new shared/library code goes in .ipynb notebooks, not .py modules
metadata:
  type: feedback
---

In BettingEdge, prefer `.ipynb` (Jupyter notebooks) over `.py` modules for any
new file. When extracting/refactoring code into something shared between
notebooks, create an `.ipynb` with the repo's standard **markdown → code →
inline-test** cell pattern. Consume it from other notebooks via `%run path/to/file.ipynb`.

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
- Consume via `%run betting/<name>.ipynb` from other notebooks; set `RUN_TESTS = False` in the caller's namespace before `%run` to skip inline tests during production runs.
- Do NOT create scratch .py files for smoke tests — put tests inline in the notebook.
- One exception: setup/automation scripts (CI, retrain helpers like `betting/experiments/*.py`) stay as .py — they aren't shared notebook code.

Related: [[notebook-edit-via-json]] (notebooks are edited via `json.load/dump`, not Read/NotebookEdit tools, for large files).
