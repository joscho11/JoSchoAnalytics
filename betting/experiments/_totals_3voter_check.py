"""Quick check: does adding RF as a 3rd voter to the consensus filter
improve hit-rate further? Uses v3.5 features. Mirrors spread model's
3-voter pattern (XGB + Ridge + LGB) but substitutes RF for LGB since
RF outperforms here."""
import sys, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tune_time_decay import load_prep_cells, MODELS
from totals_baseline_v3_5 import build_totals_features_v3_5, make_cv_folds, build_fold_data

ns = load_prep_cells(earliest=2014)
new_features = build_totals_features_v3_5(ns)
feature_cols = list(ns['avail']) + new_features
g = ns['g']
g = g[g['total_line'].notna() & g['total_points'].notna()].copy()
ns['g'] = g
fold_data = build_fold_data(make_cv_folds(2014), ns, feature_cols)

# Collect per-game predictions from XGB, Ridge, RF
ridge_o, xgb_o, rf_o, actual = [], [], [], []
for fd in fold_data:
    fd_m = {"X_tr": fd["X_tr"], "y_tr": fd["y_tr"], "X_te": fd["X_te"], "y_te": fd["y_te"],
            "sp": fd["total_line_te"], "tr_seasons": fd["tr_seasons"],
            "max_train_year": fd["max_train_year"]}
    push = fd["actual_total_te"] == fd["total_line_te"]
    valid = ~push
    for name, fn in MODELS:
        if name == 'XGBoost':
            xgb_o.extend((fn(fd_m, None)[valid] > 0).tolist())
        elif name == 'Ridge':
            ridge_o.extend((fn(fd_m, None)[valid] > 0).tolist())
        elif name == 'Random Forest':
            rf_o.extend((fn(fd_m, None)[valid] > 0).tolist())
    actual.extend((fd["actual_total_te"][valid] > fd["total_line_te"][valid]).tolist())

xgb_o = np.array(xgb_o); ridge_o = np.array(ridge_o); rf_o = np.array(rf_o); actual = np.array(actual)
n_total = len(actual)
print(f"\n{'='*78}\n  3-VOTER CONSENSUS (XGB + Ridge + RF) vs 2-VOTER (XGB + Ridge)")
print(f"  {n_total:,} push-excluded games total\n{'='*78}\n")

def report(name, mask_pred_under, mask_pred_over):
    n_u = mask_pred_under.sum()
    n_o = mask_pred_over.sum()
    if n_u > 0:
        h_u = (actual[mask_pred_under] == False).mean()
    else:
        h_u = 0
    if n_o > 0:
        h_o = (actual[mask_pred_over] == True).mean()
    else:
        h_o = 0
    print(f"  {name}")
    print(f"    UNDER picks: n={n_u}  hit-rate {h_u*100:.1f}%  ({n_u/n_total*100:.1f}% of games)")
    print(f"    OVER picks:  n={n_o}  hit-rate {h_o*100:.1f}%  ({n_o/n_total*100:.1f}% of games)")
    print()

# 2-voter consensus (XGB + Ridge)
report("2-voter consensus (XGB + Ridge agree):",
       (~xgb_o) & (~ridge_o),
       xgb_o & ridge_o)

# 3-voter consensus (all three agree)
report("3-voter consensus (XGB + Ridge + RF all agree):",
       (~xgb_o) & (~ridge_o) & (~rf_o),
       xgb_o & ridge_o & rf_o)

# Standard error
both_under_2v = (~xgb_o) & (~ridge_o)
all_under_3v = (~xgb_o) & (~ridge_o) & (~rf_o)
n_2v_under = both_under_2v.sum(); h_2v_under = (actual[both_under_2v] == False).mean()
n_3v_under = all_under_3v.sum();  h_3v_under = (actual[all_under_3v]  == False).mean()
se_2v = (h_2v_under * (1 - h_2v_under) / n_2v_under) ** 0.5
se_3v = (h_3v_under * (1 - h_3v_under) / n_3v_under) ** 0.5
print(f"  Statistical comparison (UNDER picks):")
print(f"    2-voter: {h_2v_under*100:.1f}% ± {se_2v*100:.1f}pp on n={n_2v_under}  (95% CI: {(h_2v_under-1.96*se_2v)*100:.1f}-{(h_2v_under+1.96*se_2v)*100:.1f}%)")
print(f"    3-voter: {h_3v_under*100:.1f}% ± {se_3v*100:.1f}pp on n={n_3v_under}  (95% CI: {(h_3v_under-1.96*se_3v)*100:.1f}-{(h_3v_under+1.96*se_3v)*100:.1f}%)")
