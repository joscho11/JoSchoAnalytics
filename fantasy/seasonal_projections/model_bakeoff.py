"""Model bakeoff for the seasonal PPG projection — can we beat the current CatBoost?

Predicts target_ppg (half-PPR points per game) from situational+college features,
games-weighted, walk-forward (train < N, test N), evaluated by games-weighted MAE/RMSE on
the drafted pool. Tests other algorithms (XGBoost, LightGBM, Ridge, RandomForest) and a grid
of CatBoost hyperparameters against the current production-style CatBoost. 2025 is the live test.

Run:  python model_bakeoff.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
from college_rookie_test import attach_college, COLLEGE

from catboost import CatBoostRegressor, Pool
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.ensemble import RandomForestRegressor

FEATS = avm.SITU + avm.BIAS + COLLEGE
CAT = "position"


def _numeric(df, feats, medians=None):
    """Numeric matrix for non-CatBoost models: features + one-hot position."""
    X = df[feats].copy()
    dums = pd.get_dummies(df[CAT], prefix="pos")
    X = pd.concat([X.reset_index(drop=True), dums.reset_index(drop=True)], axis=1)
    for c in ["pos_QB", "pos_RB", "pos_WR", "pos_TE"]:
        if c not in X.columns:
            X[c] = 0
    return X, dums.columns.tolist()


def fit_predict(family, params, tr, te, feats):
    y, w = tr["target_ppg"].values, tr["sample_weight"].clip(lower=1).values
    if family == "catboost":
        Xtr, Xte = tr[feats + [CAT]].copy(), te[feats + [CAT]].copy()
        Xtr[CAT], Xte[CAT] = Xtr[CAT].astype(str), Xte[CAT].astype(str)
        m = CatBoostRegressor(loss_function="MAE", random_seed=42, verbose=0,
                              allow_writing_files=False, **params)
        m.fit(Pool(Xtr, y, cat_features=[CAT], weight=w))
        return m.predict(Xte)
    Xtr, cols = _numeric(tr, feats)
    Xte, _ = _numeric(te, feats)
    Xte = Xte.reindex(columns=Xtr.columns, fill_value=0)
    if family in ("ridge", "elasticnet", "rf"):
        med = Xtr.median(numeric_only=True)
        Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
    if family == "xgb":
        m = XGBRegressor(objective="reg:absoluteerror", random_state=42, **params)
    elif family == "lgbm":
        m = LGBMRegressor(objective="mae", random_state=42, verbose=-1, **params)
    elif family == "ridge":
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import make_pipeline
        m = make_pipeline(StandardScaler(), Ridge(**params))
    elif family == "elasticnet":
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import make_pipeline
        m = make_pipeline(StandardScaler(), ElasticNet(**params))
    elif family == "rf":
        m = RandomForestRegressor(random_state=42, n_jobs=-1, **params)
    m.fit(Xtr, y, **({"sample_weight": w} if family in ("xgb", "lgbm", "rf") else {}))
    return m.predict(Xte)


CONFIGS = [
    ("CatBoost CURRENT (d5,lr.04,l2 4,400)", "catboost", dict(depth=5, learning_rate=0.04, l2_leaf_reg=4, iterations=400)),
    ("CatBoost d4 lr.03 l2 3",               "catboost", dict(depth=4, learning_rate=0.03, l2_leaf_reg=3, iterations=600)),
    ("CatBoost d6 lr.03 l2 6",               "catboost", dict(depth=6, learning_rate=0.03, l2_leaf_reg=6, iterations=600)),
    ("CatBoost d4 lr.02 l2 6 (800)",         "catboost", dict(depth=4, learning_rate=0.02, l2_leaf_reg=6, iterations=800)),
    ("CatBoost d8 lr.03 l2 3",               "catboost", dict(depth=8, learning_rate=0.03, l2_leaf_reg=3, iterations=500)),
    ("XGBoost d4 lr.03",                     "xgb", dict(max_depth=4, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8)),
    ("LightGBM 31 leaves lr.03",             "lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8)),
    ("Ridge a=10",                           "ridge", dict(alpha=10)),
    ("ElasticNet a=.5",                      "elasticnet", dict(alpha=0.5, l1_ratio=0.3)),
    ("RandomForest 400",                     "rf", dict(n_estimators=400, max_depth=8, min_samples_leaf=5)),
]


def wmae(e, w):
    return float(np.sum(np.abs(e) * w) / np.sum(w))


def wrmse(e, w):
    return float(np.sqrt(np.sum(e ** 2 * w) / np.sum(w)))


def run(test_seasons=range(2021, 2026), drafted_max=180):
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    feats = [c for c in FEATS if c in df.columns]
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()].copy()
    trainable = df[df["target_ppg"].notna()].copy()   # train on ALL players with a target, more data

    print(f"bakeoff: {len(feats)} features, train on all-with-target, test drafted pool\n")
    print(f"  {'config':38s} {'MAE':>5} {'RMSE':>5} | {'2025 MAE':>8} {'2025 RMSE':>9}")
    rows = []
    for name, fam, params in CONFIGS:
        chunks = []
        for N in test_seasons:
            tr = trainable[trainable["season"] < N]
            te = pool[pool["season"] == N].copy()
            if len(te) < 20 or len(tr) < 200:
                continue
            te["pred"] = fit_predict(fam, params, tr, te, feats)
            chunks.append(te)
        allp = pd.concat(chunks, ignore_index=True)
        e, w = allp["pred"] - allp["target_ppg"], allp["sample_weight"].clip(lower=1)
        a25 = allp[allp["season"] == 2025]
        e25, w25 = a25["pred"] - a25["target_ppg"], a25["sample_weight"].clip(lower=1)
        mae, rmse, mae25, rmse25 = wmae(e, w), wrmse(e, w), wmae(e25, w25), wrmse(e25, w25)
        rows.append((name, mae, rmse, mae25, rmse25))
        print(f"  {name:38s} {mae:5.3f} {rmse:5.3f} | {mae25:8.3f} {rmse25:9.3f}")

    best = min(rows, key=lambda r: r[1])
    cur = next(r for r in rows if "CURRENT" in r[0])
    print(f"\n  best pooled MAE: {best[0]}  ({best[1]:.3f})")
    print(f"  current:         {cur[0]}  ({cur[1]:.3f})")
    print(f"  improvement vs current: {cur[1] - best[1]:+.3f} PPG "
          f"({'meaningful' if cur[1]-best[1] > 0.03 else 'within noise'})")


if __name__ == "__main__":
    run()
