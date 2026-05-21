"""Feature ablation study: rank features by XGB gain + Ridge |coef|, drop bottom-K, re-run CV.

Tests whether the 85-feature set has noise features that are net-negative for the production
direction voters (XGBoost, Ridge, LightGBM).

Outputs:
  feature_ablation_results.json  — full per-subset CV results
  feature_importance_ranking.csv — combined ranking of all 85 features
"""
import json, sys, time, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

# ── 1. Run data prep ─────────────────────────────────────────────────────────
print("Loading data prep from model_comparison.ipynb (cells 1-37)...")
t0 = time.time()

with open(ROOT / 'betting/model_comparison.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

ns = {'__name__': '__main__'}
for i in range(1, 38):
    cell = nb['cells'][i]
    if cell['cell_type'] != 'code': continue
    src = ''.join(cell['source'])
    if 'assert' in src and ('passed' in src or 'tests' in src.lower()): continue
    try:
        exec(src, ns)
    except Exception:
        if 'EXPECTED' in src or 'assert' in src: continue
        raise

print(f"  Prep done in {time.time()-t0:.1f}s — g.shape={ns['g'].shape}, avail={len(ns['avail'])} features")

g       = ns['g']
avail   = ns['avail']
ats_acc = ns['ats_acc']

# ── 2. CV folds ──────────────────────────────────────────────────────────────
CV_FOLDS = [
    {"train": list(range(2014, 2020)), "test": [2020]},
    {"train": list(range(2014, 2021)), "test": [2021]},
    {"train": list(range(2014, 2022)), "test": [2022]},
    {"train": list(range(2014, 2023)), "test": [2023]},
    {"train": list(range(2014, 2024)), "test": [2024]},
    {"train": list(range(2014, 2025)), "test": [2025]},
]

def build_fold_data(feat_subset):
    """Build CV folds restricted to a given feature subset."""
    fold_data = []
    for fold in CV_FOLDS:
        tr_m = g["season"].isin(fold["train"])
        te_m = g["season"].isin(fold["test"])
        _wk = g.loc[tr_m].groupby("week")["home_margin"].apply(lambda x: x.abs().mean())
        g_fold = g.copy()
        g_fold["league_rolling_avg_abs_margin_by_week"] = g_fold["week"].map(_wk).fillna(_wk.mean())
        fold_data.append({
            "yr": fold["test"][0],
            "X_tr": g_fold.loc[tr_m, feat_subset].fillna(0).values.astype("float32"),
            "y_tr": g_fold.loc[tr_m, "home_margin"].values.astype("float32"),
            "X_te": g_fold.loc[te_m, feat_subset].fillna(0).values.astype("float32"),
            "y_te": g_fold.loc[te_m, "home_margin"].values.astype("float32"),
            "sp":   g_fold.loc[te_m, "spread_line"].fillna(0).values,
        })
    return fold_data

# ── 3. Compute feature importance on full data ──────────────────────────────
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

print("\nComputing feature importances on full 2014-2024 training data...")
full_tr_m = g["season"].isin(list(range(2014, 2025)))
X_full = g.loc[full_tr_m, avail].fillna(0).values.astype("float32")
y_full = g.loc[full_tr_m, "home_margin"].values.astype("float32")

# XGBoost importance (gain) — use tuned hyperparams (alpha=2, lambda=5)
xgb_m = xgb.XGBRegressor(n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
                         subsample=0.6, colsample_bytree=0.6, reg_alpha=2.0, reg_lambda=5.0,
                         objective="reg:squarederror", random_state=42, n_jobs=-1,
                         importance_type="gain")
xgb_m.fit(X_full, y_full)
xgb_imp = xgb_m.feature_importances_

# Ridge |coef| — must scale first
sc = StandardScaler()
X_full_sc = sc.fit_transform(X_full)
ridge_m = Ridge(alpha=50.0)
ridge_m.fit(X_full_sc, y_full)
ridge_imp = np.abs(ridge_m.coef_)

# LightGBM importance (gain) — use tuned hyperparams
cut = int(len(X_full) * 0.85)
lgb_tr = lgb.Dataset(X_full[:cut], label=y_full[:cut])
lgb_val = lgb.Dataset(X_full[cut:], label=y_full[cut:], reference=lgb_tr)
lgb_params = dict(objective="regression", metric="rmse", learning_rate=0.01,
                  num_leaves=15, max_depth=4, min_data_in_leaf=20,
                  feature_fraction=0.6, bagging_fraction=0.6, bagging_freq=5,
                  reg_alpha=1.0, reg_lambda=3.0, verbose=-1, n_jobs=-1, seed=42,
                  feature_fraction_seed=42, bagging_seed=42)
lgb_m = lgb.train(lgb_params, lgb_tr, num_boost_round=500, valid_sets=[lgb_val],
                  callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
lgb_imp = lgb_m.feature_importance(importance_type="gain")

# Normalize each to [0, 1] for fair averaging
def norm(x): return x / (x.max() + 1e-12)
xgb_n = norm(xgb_imp)
ridge_n = norm(ridge_imp)
lgb_n = norm(lgb_imp)

combined_score = (xgb_n + ridge_n + lgb_n) / 3.0

imp_df = pd.DataFrame({
    "feature": avail,
    "xgb_gain_norm": xgb_n,
    "ridge_abs_coef_norm": ridge_n,
    "lgb_gain_norm": lgb_n,
    "combined": combined_score,
}).sort_values("combined", ascending=False).reset_index(drop=True)
imp_df["rank"] = imp_df.index + 1
imp_df.to_csv(HERE / "feature_importance_ranking.csv", index=False)

print("\nTop 15 features:")
print(imp_df.head(15)[["rank", "feature", "combined", "xgb_gain_norm", "ridge_abs_coef_norm", "lgb_gain_norm"]].to_string(index=False))
print("\nBottom 15 features (candidates to drop):")
print(imp_df.tail(15)[["rank", "feature", "combined", "xgb_gain_norm", "ridge_abs_coef_norm", "lgb_gain_norm"]].to_string(index=False))

# ── 4. Ablation sweep ────────────────────────────────────────────────────────
print(f"\n{'='*100}\nFEATURE ABLATION: walk-forward CV at multiple feature counts\n{'='*100}")

KEEP_COUNTS = [85, 75, 65, 55, 45, 35, 25]
ranked_features = imp_df["feature"].tolist()

def run_xgb(fd):
    m = xgb.XGBRegressor(n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
                         subsample=0.6, colsample_bytree=0.6, reg_alpha=2.0, reg_lambda=5.0,
                         objective="reg:squarederror", random_state=42, n_jobs=-1)
    m.fit(fd["X_tr"], fd["y_tr"])
    return m.predict(fd["X_te"])

def run_ridge(fd):
    sc_f = StandardScaler()
    Xtr = sc_f.fit_transform(fd["X_tr"])
    Xte = sc_f.transform(fd["X_te"])
    m = Ridge(alpha=50.0)
    m.fit(Xtr, fd["y_tr"])
    return m.predict(Xte)

def run_lgbm(fd):
    cut = int(len(fd["X_tr"]) * 0.85)
    lgb_tr = lgb.Dataset(fd["X_tr"][:cut], label=fd["y_tr"][:cut])
    lgb_val = lgb.Dataset(fd["X_tr"][cut:], label=fd["y_tr"][cut:], reference=lgb_tr)
    m = lgb.train(lgb_params, lgb_tr, num_boost_round=500, valid_sets=[lgb_val],
                  callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    return m.predict(fd["X_te"])

results = {}
for k in KEEP_COUNTS:
    feat_subset = ranked_features[:k]
    fd_list = build_fold_data(feat_subset)
    print(f"\n--- Keep top {k} features ({85-k} dropped) ---")
    sub_results = {}
    for name, run_fn in [("XGBoost", run_xgb), ("Ridge", run_ridge), ("LightGBM", run_lgbm)]:
        t0 = time.time()
        accs, maes = [], []
        for fd in fd_list:
            preds = run_fn(fd)
            accs.append(ats_acc(preds, fd["sp"], fd["y_te"]))
            maes.append(float(np.abs(preds - fd["y_te"]).mean()))
        accs, maes = np.array(accs), np.array(maes)
        score = accs.mean() - accs.std()
        sub_results[name] = dict(mean=float(accs.mean()), std=float(accs.std()),
                                  min=float(accs.min()), max=float(accs.max()),
                                  mae=float(maes.mean()), score=float(score))
        print(f"  {name:<10} mean={accs.mean():.1%}  std={accs.std():.1%}  "
              f"(min={accs.min():.1%} max={accs.max():.1%})  MAE={maes.mean():.2f}  score={score:.3f}  [{time.time()-t0:.1f}s]")
    # Average across the 3 models — proxy for "ensemble quality"
    avg_score = np.mean([sub_results[m]["score"] for m in sub_results])
    avg_mean  = np.mean([sub_results[m]["mean"] for m in sub_results])
    print(f"  AVG       mean={avg_mean:.1%}  score={avg_score:.3f}")
    sub_results["AVG"] = dict(mean=float(avg_mean), score=float(avg_score))
    results[k] = sub_results

# ── 5. Summary table ─────────────────────────────────────────────────────────
print(f"\n{'='*100}\nSUMMARY: ATS Mean by feature count\n{'='*100}")
print(f"{'#features':>10}{'XGB Mean':>11}{'XGB Score':>11}{'Ridge Mean':>13}{'Ridge Score':>13}{'LGB Mean':>11}{'LGB Score':>11}{'AVG Score':>11}")
print('-'*100)
for k in KEEP_COUNTS:
    r = results[k]
    print(f"{k:>10}{r['XGBoost']['mean']*100:>10.2f}%{r['XGBoost']['score']*100:>10.2f}%"
          f"{r['Ridge']['mean']*100:>12.2f}%{r['Ridge']['score']*100:>12.2f}%"
          f"{r['LightGBM']['mean']*100:>10.2f}%{r['LightGBM']['score']*100:>10.2f}%"
          f"{r['AVG']['score']*100:>10.2f}%")

with open(HERE / "feature_ablation_results.json", 'w') as f:
    json.dump({"results": results, "ranking": imp_df.to_dict('records')}, f, indent=2)

print(f"\n  Saved: feature_ablation_results.json, feature_importance_ranking.csv")

# ── 6. Verdict ───────────────────────────────────────────────────────────────
print(f"\n{'='*100}\nVERDICT\n{'='*100}")
best_k = max(KEEP_COUNTS, key=lambda k: results[k]["AVG"]["score"])
baseline_score = results[85]["AVG"]["score"]
best_score = results[best_k]["AVG"]["score"]
delta = (best_score - baseline_score) * 100
print(f"  Best subset: top {best_k} features (AVG score {best_score*100:.2f}%)")
print(f"  Baseline (all 85): AVG score {baseline_score*100:.2f}%")
print(f"  Δ score: {delta:+.2f}pp")
if best_k == 85:
    print("  → No improvement from dropping features. The 85-feature set is well-chosen.")
elif delta > 0.5:
    print(f"  → Real improvement: dropping {85-best_k} low-importance features helps. Consider reducing the feature set.")
else:
    print(f"  → Marginal/noisy improvement ({delta:+.2f}pp). Not worth the engineering complexity.")
