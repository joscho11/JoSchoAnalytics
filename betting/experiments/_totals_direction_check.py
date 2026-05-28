"""Diagnostic: what does the v2 model ACTUALLY predict? If Ridge is just
predicting UNDER 80%+ of the time, the 52.6% hit-rate is mostly a base-
rate artifact, not real edge. We want to see:
  - Distribution of model predictions (% OVER vs % UNDER)
  - Hit rate conditional on direction (OVER picks hit X%, UNDER picks Y%)
  - Comparison to the naive "always UNDER" baseline within each fold

A real edge means: among games where the model SAYS OVER, the OVER hits
materially more than the league average (i.e., > 48.2% OVER rate). And
among UNDER picks, UNDER hits more than 51.8%. Anything less and the
model is just adopting the market's bias.
"""
import sys, json, time, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tune_time_decay import load_prep_cells, decay_weights, MODELS
from totals_baseline_v3_5 import build_totals_features_v3_5, make_cv_folds, build_fold_data

ns = load_prep_cells(earliest=2014)
new_features = build_totals_features_v3_5(ns)
feature_cols = list(ns['avail']) + new_features
g = ns['g']
g = g[g['total_line'].notna() & g['total_points'].notna()].copy()
ns['g'] = g

fold_data = build_fold_data(make_cv_folds(2014), ns, feature_cols)

print(f"\n{'='*78}")
print(f"  DIRECTION-CONDITIONED ANALYSIS — does the model add signal vs naive UNDER?")
print(f"{'='*78}")
print(f"  Baseline: across 2020-2025, 'always UNDER' would hit 51.2%")
print(f"  Real edge means OVER picks > 48.2% AND/OR UNDER picks > 51.8%")
print()
print(f"  {'Model':14}  {'#OVER':>5}  {'#UND':>5}  {'OVER hit%':>10}  {'UND hit%':>10}  {'Overall':>8}")
print('-'*78)

for model_name, run_fn in MODELS:
    all_pred_over = []
    all_actual_over = []
    for fd in fold_data:
        fd_for_model = {
            "X_tr": fd["X_tr"], "y_tr": fd["y_tr"],
            "X_te": fd["X_te"], "y_te": fd["y_te"],
            "sp": fd["total_line_te"], "tr_seasons": fd["tr_seasons"],
            "max_train_year": fd["max_train_year"],
        }
        preds_diff = run_fn(fd_for_model, None)
        preds_total = fd["total_line_te"] + preds_diff
        push = fd["actual_total_te"] == fd["total_line_te"]
        valid = ~push
        all_pred_over.extend((preds_total[valid] > fd["total_line_te"][valid]).tolist())
        all_actual_over.extend((fd["actual_total_te"][valid] > fd["total_line_te"][valid]).tolist())

    pred = np.array(all_pred_over)
    actual = np.array(all_actual_over)
    n_over_pred = pred.sum()
    n_under_pred = (~pred).sum()
    over_hit = (actual[pred] == True).mean() if n_over_pred > 0 else 0
    under_hit = (actual[~pred] == False).mean() if n_under_pred > 0 else 0
    overall = (pred == actual).mean()
    print(f"  {model_name:14}  {n_over_pred:>5}  {n_under_pred:>5}  {over_hit*100:>9.1f}%  {under_hit*100:>9.1f}%  {overall*100:>7.1f}%")

print()
print(f"  Total games (push-excluded): {len(actual)}")
print(f"  Actual OVER rate in test:    {actual.mean()*100:.1f}%   (UNDER rate: {(1-actual.mean())*100:.1f}%)")

# ── Consensus analysis: Ridge + XGB agree ────────────────────────────────────
print(f"\n{'='*78}")
print(f"  CONSENSUS FILTER — when Ridge + XGBoost agree, hit-rate goes up?")
print(f"{'='*78}")

ridge_preds_over, xgb_preds_over = [], []
all_actual = []
for fd in fold_data:
    fd_for_model = {
        "X_tr": fd["X_tr"], "y_tr": fd["y_tr"], "X_te": fd["X_te"], "y_te": fd["y_te"],
        "sp": fd["total_line_te"], "tr_seasons": fd["tr_seasons"], "max_train_year": fd["max_train_year"],
    }
    push = fd["actual_total_te"] == fd["total_line_te"]
    valid = ~push
    for name, fn in MODELS:
        if name == 'Ridge':
            r_diff = fn(fd_for_model, None)
            ridge_preds_over.extend(((fd["total_line_te"][valid] + r_diff[valid]) > fd["total_line_te"][valid]).tolist())
        elif name == 'XGBoost':
            x_diff = fn(fd_for_model, None)
            xgb_preds_over.extend(((fd["total_line_te"][valid] + x_diff[valid]) > fd["total_line_te"][valid]).tolist())
    all_actual.extend((fd["actual_total_te"][valid] > fd["total_line_te"][valid]).tolist())

ridge_o = np.array(ridge_preds_over)
xgb_o = np.array(xgb_preds_over)
actual = np.array(all_actual)

both_over = ridge_o & xgb_o
both_under = ~ridge_o & ~xgb_o
disagree = ridge_o != xgb_o

print(f"  Both OVER  picks: {both_over.sum():>5}   hit-rate: {(actual[both_over]==True).mean()*100:.1f}%")
print(f"  Both UNDER picks: {both_under.sum():>5}   hit-rate: {(actual[both_under]==False).mean()*100:.1f}%")
print(f"  Disagree (PASS):  {disagree.sum():>5}   (we'd skip these)")
print()
consensus_correct = ((actual[both_over]==True).sum() + (actual[both_under]==False).sum())
consensus_total = both_over.sum() + both_under.sum()
print(f"  Consensus overall (Ridge + XGB agree): {consensus_correct}/{consensus_total} = "
      f"{consensus_correct/consensus_total*100:.1f}% on {consensus_total/len(actual)*100:.1f}% of games")
print()
print(f"  vs single-model Ridge:  52.6% on 100% of games")
print(f"  vs single-model XGB:    51.8% on 100% of games")
