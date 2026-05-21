"""Seed-stability check: rerun XGBoost configs across 3 random seeds.
Averages results to confirm whether the (alpha=2, lambda=5) improvement is robust.
"""
import json, sys, time, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

# ── 1. Load notebook & run prep cells (1 through 37) in shared namespace ─────
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
    except Exception as e:
        if 'EXPECTED' in src or 'assert' in src: continue
        raise

print(f"  Prep done in {time.time()-t0:.1f}s — g.shape={ns['g'].shape}, avail={len(ns['avail'])} features")

g       = ns['g']
avail   = ns['avail']
ats_acc = ns['ats_acc']

CV_FOLDS = [
    {"train": list(range(2014, 2020)), "test": [2020]},
    {"train": list(range(2014, 2021)), "test": [2021]},
    {"train": list(range(2014, 2022)), "test": [2022]},
    {"train": list(range(2014, 2023)), "test": [2023]},
    {"train": list(range(2014, 2024)), "test": [2024]},
    {"train": list(range(2014, 2025)), "test": [2025]},
]

fold_data = []
for fold in CV_FOLDS:
    test_yr = fold["test"][0]
    tr_m = g["season"].isin(fold["train"])
    te_m = g["season"].isin(fold["test"])
    _wk = g.loc[tr_m].groupby("week")["home_margin"].apply(lambda x: x.abs().mean())
    g_fold = g.copy()
    g_fold["league_rolling_avg_abs_margin_by_week"] = g_fold["week"].map(_wk).fillna(_wk.mean())
    fold_data.append({
        "yr": test_yr,
        "X_tr": g_fold.loc[tr_m, avail].fillna(0).values.astype("float32"),
        "y_tr": g_fold.loc[tr_m, "home_margin"].values.astype("float32"),
        "X_te": g_fold.loc[te_m, avail].fillna(0).values.astype("float32"),
        "y_te": g_fold.loc[te_m, "home_margin"].values.astype("float32"),
        "sp":   g_fold.loc[te_m, "spread_line"].fillna(0).values,
    })

import xgboost as xgb

xgb_base = dict(n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
                subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0, reg_lambda=3.0)

configs = [
    ("Baseline (alpha=1, lambda=3)", xgb_base),
    ("More reg (alpha=2, lambda=5)", {**xgb_base, "reg_alpha": 2.0, "reg_lambda": 5.0}),
]

SEEDS = [42, 7, 123]

print(f"\n{'='*100}")
print(f"XGBoost seed-stability check: {len(configs)} configs × {len(SEEDS)} seeds × {len(fold_data)} folds")
print('='*100)

all_runs = {name: {"means": [], "stds": [], "fold_accs": []} for name, _ in configs}

for seed in SEEDS:
    print(f"\n--- seed={seed} ---")
    for cfg_name, params in configs:
        accs = []
        for fd in fold_data:
            m = xgb.XGBRegressor(objective="reg:squarederror", random_state=seed, n_jobs=-1, **params)
            m.fit(fd["X_tr"], fd["y_tr"])
            preds = m.predict(fd["X_te"])
            accs.append(ats_acc(preds, fd["sp"], fd["y_te"]))
        accs = np.array(accs)
        all_runs[cfg_name]["means"].append(accs.mean())
        all_runs[cfg_name]["stds"].append(accs.std())
        all_runs[cfg_name]["fold_accs"].append(accs.tolist())
        print(f"  {cfg_name:<35} mean={accs.mean():.1%} ± {accs.std():.1%}  folds={[f'{a:.1%}' for a in accs]}")

print(f"\n{'='*100}")
print("SEED-AGGREGATED RESULTS")
print('='*100)
print(f"{'Config':<40}{'Seed-avg Mean':>15}{'Seed-avg Std':>15}{'Mean Range':>20}{'Score':>10}")
print('-'*100)
summary = {}
for cfg_name in [n for n, _ in configs]:
    means = np.array(all_runs[cfg_name]["means"])
    stds  = np.array(all_runs[cfg_name]["stds"])
    mean_of_means = means.mean()
    mean_of_stds  = stds.mean()
    score = mean_of_means - mean_of_stds
    rng = f"[{means.min():.1%}, {means.max():.1%}]"
    summary[cfg_name] = dict(mean=mean_of_means, std=mean_of_stds, score=score, range=rng,
                              raw_means=means.tolist(), raw_stds=stds.tolist())
    print(f"{cfg_name:<40}{mean_of_means:>13.2%}{mean_of_stds:>15.2%}{rng:>20}{score*100:>8.2f}")

# Verdict
b = summary["Baseline (alpha=1, lambda=3)"]
r = summary["More reg (alpha=2, lambda=5)"]
delta_mean = (r["mean"] - b["mean"]) * 100
delta_std  = (r["std"] - b["std"]) * 100
delta_score = (r["score"] - b["score"]) * 100

print(f"\n{'='*100}")
print("VERDICT")
print('='*100)
print(f"  Δ mean:  {delta_mean:+.2f}pp  ({'more reg better' if delta_mean > 0 else 'baseline better'})")
print(f"  Δ std:   {delta_std:+.2f}pp  ({'more reg better' if delta_std < 0 else 'baseline better'})")
print(f"  Δ score: {delta_score:+.2f}pp")
print(f"\n  Recommendation: {'APPLY the more-reg config' if delta_score > 0.2 else 'NOISY — improvement does not hold across seeds; STAY with baseline'}")

with open(HERE / 'xgb_seed_stability_results.json', 'w') as f:
    json.dump({"summary": {k: {kk: vv for kk, vv in v.items()} for k, v in summary.items()},
               "raw": all_runs, "seeds": SEEDS}, f, indent=2)
print("\nResults saved to xgb_seed_stability_results.json")
