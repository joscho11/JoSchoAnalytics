"""Train the production rookie PPG model (CatBoost) -> models/rookie_ppg_model.pkl.

A dedicated rookie season-PPG projection on draft capital + combine measurables +
landing spot (see rookie_features.ROOKIE_FEATS). It does NOT beat ADP standalone
(rho ~0.26 vs ADP ~0.46), but blended 30/70 with ADP it improves the ROOKIE slice
of the draft board -- rookie-slice rho 0.457 -> 0.488, beating pure ADP, with no
overall regression (see rookie_blend_test.py). build_draft_board.py uses it for
rookies' PPG inside the blend; the standalone-vs-ADP edge backtest does NOT use it.

Games-weighted, tuned via walk-forward CV (val 2021-2024), train 2014-2024 / holdout 2025.
Run:  python fantasy/seasonal_projections/train_rookie_model.py
"""
import sys
import json
import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from catboost import CatBoostRegressor

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rookie_features as rf

HERE       = Path(__file__).resolve().parent
DATA       = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
MODELS_DIR.mkdir(exist_ok=True)
TRAIN_SEASONS = list(range(2014, 2025))
CV_VAL_SEASONS = [2021, 2022, 2023, 2024]
HOLDOUT = 2025
SEED = 42


def cat_grid():
    for depth, lr, l2 in itertools.product([3, 4, 6], [0.03, 0.06], [3.0, 6.0]):
        yield dict(iterations=400, depth=depth, learning_rate=lr, l2_leaf_reg=l2,
                   loss_function="MAE", random_seed=SEED, verbose=0, allow_writing_files=False)


def fit(params, tr):
    m = CatBoostRegressor(**params, cat_features=rf.CAT)
    m.fit(tr[rf.ROOKIE_FEATS], tr.target_ppg, sample_weight=tr.sample_weight)
    return m


def tune(train_rk):
    best, best_mae = None, np.inf
    for params in cat_grid():
        sc = []
        for vs in CV_VAL_SEASONS:
            tr = train_rk[train_rk.season < vs]
            va = train_rk[train_rk.season == vs]
            if len(tr) < 80 or len(va) < 15:
                continue
            m = fit(params, tr)
            pred = np.clip(m.predict(va[rf.ROOKIE_FEATS]), 0, None)
            sc.append(float(np.average(np.abs(va.target_ppg - pred), weights=va.sample_weight)))
        if sc and np.mean(sc) < best_mae:
            best, best_mae = params, float(np.mean(sc))
    return best, best_mae


def main():
    df = rf.add_rookie_features(pd.read_csv(DATA))
    rookies = df[(df.is_rookie == 1) & df.target_ppg.notna()]
    cov = df.loc[df.is_rookie == 1, "wt"].notna().mean()
    print(f"rookies w/ PPG target: {len(rookies)} (train {len(rookies[rookies.season < HOLDOUT])}, "
          f"holdout {len(rookies[rookies.season == HOLDOUT])}) | combine coverage {cov:.0%}")

    tr = rookies[rookies.season.isin(TRAIN_SEASONS)]
    best, cv = tune(tr)
    print(f"tuned (cv wMAE={cv:.3f}): { {k: best[k] for k in ('depth','learning_rate','l2_leaf_reg')} }")

    model = fit(best, tr)
    joblib.dump({"model": model, "feature_cols": rf.ROOKIE_FEATS, "cat_features": rf.CAT,
                 "target": "target_ppg", "train_seasons": TRAIN_SEASONS},
                MODELS_DIR / "rookie_ppg_model.pkl")

    ho = rookies[rookies.season == HOLDOUT]
    pred = np.clip(model.predict(ho[rf.ROOKIE_FEATS]), 0, None)
    wmae = float(np.average(np.abs(ho.target_ppg - pred), weights=ho.sample_weight))
    posmean = tr.groupby("position").apply(lambda g: np.average(g.target_ppg, weights=g.sample_weight))
    base = float(np.average(np.abs(ho.target_ppg - ho.position.map(posmean)), weights=ho.sample_weight))
    metrics = {"cv_wmae": round(cv, 3), "holdout_wmae": round(wmae, 3),
               "baseline_posmean_wmae": round(base, 3), "n_holdout": len(ho),
               "best_params": {k: best[k] for k in ("depth", "learning_rate", "l2_leaf_reg")},
               "combine_coverage": round(float(cov), 3)}
    (MODELS_DIR / "rookie_metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"2025 holdout rookie PPG wMAE: model={wmae:.3f}  position-mean baseline={base:.3f}  (n={len(ho)})")
    print(f"Saved rookie_ppg_model.pkl + rookie_metrics.json to {MODELS_DIR}")


if __name__ == "__main__":
    main()
