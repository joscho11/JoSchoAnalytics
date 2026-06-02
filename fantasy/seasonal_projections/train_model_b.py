"""Train Model B (availability / games played).

One pooled CatBoost regressor predicting target_games (0-17) for the upcoming
season, trained on ALL rows 2014-2024 INCLUDING the reconstructed 0-game
(full-miss) seasons, so the model sees the durability tail. `position` is a
native CatBoost categorical. No sample weighting here — each player-season is
one equally-weighted observation of availability (weighting by games would bias
toward healthy players, defeating the purpose).

Honest expectation: most injury variance is irreducible (freak hits). This model
captures the *systematic* component (history, age, position, workload), so it
should separate durable vs fragile tiers, not predict exact games. We report MAE
plus rank correlation, against two naive baselines (repeat prior games / predict
the league mean).

Hyperparameters tuned with a small grid via walk-forward CV (validate on
2021-2024, train on prior). 2025 is the untouched holdout.

Output: models/availability_model.pkl + models/model_b_metrics.json
Run:    python fantasy/seasonal_projections/train_model_b.py
"""
import sys
import json
import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from scipy.stats import spearmanr
from catboost import CatBoostRegressor

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE       = Path(__file__).resolve().parent
DATA       = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
MODELS_DIR.mkdir(exist_ok=True)
TRAIN_SEASONS  = list(range(2014, 2025))
CV_VAL_SEASONS = [2021, 2022, 2023, 2024]
HOLDOUT    = 2025
SEED       = 42

# Availability-relevant features, all known pre-season (no leakage). position is
# categorical; the rest numeric (NaN routed natively by CatBoost).
FEATURES = [
    "age", "years_exp", "is_rookie", "missed_prior_season",
    "prior_games", "prior_games_missed",
    "prior_carries_pg", "prior_touches_pg", "prior_targets_pg", "prior_snap_share_pg",
    "draft_round", "draft_pick", "position",
]
CAT_FEATURES = ["position"]


def cat_grid():
    for depth, lr, l2 in itertools.product([4, 6], [0.03, 0.06], [3.0, 6.0]):
        yield dict(iterations=500, depth=depth, learning_rate=lr, l2_leaf_reg=l2,
                   loss_function="MAE", random_seed=SEED, verbose=0, allow_writing_files=False)


def _prep(d):
    # CatBoost wants the categorical column as a non-null string.
    d = d.copy()
    d["position"] = d["position"].astype(str)
    return d


def fit(params, tr):
    m = CatBoostRegressor(**params, cat_features=CAT_FEATURES)
    m.fit(tr[FEATURES], tr["target_games"])
    return m


def tune(train):
    best, best_mae = None, np.inf
    for params in cat_grid():
        scores = []
        for vs in CV_VAL_SEASONS:
            tr = train[train.season < vs]
            va = train[train.season == vs]
            if len(tr) < 100 or len(va) < 20:
                continue
            m = fit(params, tr)
            pred = np.clip(m.predict(va[FEATURES]), 0, 17)
            scores.append(float(np.mean(np.abs(va["target_games"].values - pred))))
        if scores:
            s = float(np.mean(scores))
            if s < best_mae:
                best, best_mae = params, s
    return best, best_mae


def main():
    df = _prep(pd.read_csv(DATA))
    # target_games is present for every row (including reconstructed 0-game seasons)
    train = df[df.season.isin(TRAIN_SEASONS)]
    hold  = df[df.season == HOLDOUT]
    print(f"Train rows: {len(train):,} (incl. {int((train.reconstructed==1).sum())} full-miss 0-game) "
          f"| holdout: {len(hold):,}")
    print(f"  target_games: train mean={train.target_games.mean():.1f}  holdout mean={hold.target_games.mean():.1f}\n")

    best, cv_mae = tune(train)
    print(f"Best params (cv MAE={cv_mae:.3f}): "
          f"{ {k: best[k] for k in ('depth','learning_rate','l2_leaf_reg')} }")

    model = fit(best, train)
    joblib.dump({"model": model, "feature_cols": FEATURES, "cat_features": CAT_FEATURES,
                 "target": "target_games", "train_seasons": TRAIN_SEASONS},
                MODELS_DIR / "availability_model.pkl")

    pred = np.clip(model.predict(hold[FEATURES]), 0, 17)
    mae  = float(np.mean(np.abs(hold.target_games.values - pred)))
    rho  = float(spearmanr(pred, hold.target_games).statistic)
    # baselines on the same holdout rows
    base_prior = hold[hold.prior_games.notna()]
    mae_prior  = float(np.mean(np.abs(base_prior.target_games.values
                                      - base_prior.prior_games.clip(0, 17).values)))
    mae_mean   = float(np.mean(np.abs(hold.target_games.values - train.target_games.mean())))

    metrics = {"cv_mae": round(cv_mae, 3), "holdout_mae": round(mae, 3),
               "holdout_rho": round(rho, 3),
               "baseline_prior_games_mae": round(mae_prior, 3),
               "baseline_mean_mae": round(mae_mean, 3),
               "n_holdout": len(hold), "best_params": {k: best[k] for k in ('depth','learning_rate','l2_leaf_reg')}}
    (MODELS_DIR / "model_b_metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"\nHoldout (2025, n={len(hold)}):")
    print(f"  Model B  MAE={mae:.3f} games   rank rho={rho:.3f}")
    print(f"  baseline (repeat prior games)  MAE={mae_prior:.3f}")
    print(f"  baseline (predict league mean) MAE={mae_mean:.3f}")
    print(f"\nSaved availability_model.pkl + model_b_metrics.json to {MODELS_DIR}")
    return metrics


if __name__ == "__main__":
    main()
