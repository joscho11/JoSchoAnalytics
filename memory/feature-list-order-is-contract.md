---
name: feature-list-order-is-contract
description: PROD_FEATURES_35 / FEATURE_COLS_85 list order determines X_tr column order; reordering them breaks pkl byte-equivalence
metadata:
  type: project
---

In `betting/features.ipynb`, the order of entries in `PROD_FEATURES_35` (and
`FEATURE_COLS_85`) is part of the **contract**, not a stylistic choice. The
production retrain in `model_comparison.ipynb` does:

```python
avail = [c for c in PROD_FEATURES_35 if c in avail_full]
X_tr = g.loc[train_m, avail].fillna(0).values.astype("float32")
```

That `avail` list preserves the order of `PROD_FEATURES_35`. `X_tr` columns are
ordered the same way. Reordering the list — even keeping the same 35 features —
gives the model a different column layout → different fits → different
trained pkl bytes (XGBoost, LightGBM, Ridge all sensitive in at least one of
their internals: tree split feature indices, coefficient indices, gain calcs).

The canonical order is the descending-importance order produced by the
2026-05-20 ablation study (`betting/experiments/feature_ablation.py` →
`feature_importance_ranking.csv`). It must be preserved exactly.

**How to apply:**
- Never reorder `PROD_FEATURES_35` or `FEATURE_COLS_85` "for readability".
- If you change which 35 features are in the list (ablation rerun), retrain
  the production pkls and document it in CLAUDE.md's Completed Work.
- The Phase 2a dedup (2026-05-23) introduced exactly this bug by grouping
  related features together when extracting the list into `features.ipynb`.
  Caught by comparing pkl md5s before/after retrain — the safety net worked.

Related: [[prefer-ipynb-not-py]] (same refactor introduced this).
