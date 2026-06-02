"""Train production Model A (PPG / production), per position, with CatBoost.

CatBoost won the 3-way bakeoff (see model_a_compare.ipynb): lowest games-
weighted holdout MAE at all four positions, best out-of-fold CV, and the only
algorithm that beat the naive 3-year-average baseline at every position.

This trains one CatBoost regressor per position on 2014-2024 (games-weighted),
using the tuned hyperparameters from model_a_compare_results.json, and saves
{pos}_ppg_model.pkl to models/. Reports the 2025 holdout MAE per position
against the naive baseline on matched rows (rookies excluded, since the
baseline can't predict them).

Run:  python fantasy/seasonal_projections/train_model_a.py
"""
import sys
import json
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
TUNED      = HERE / "model_a_compare_results.json"
MODELS_DIR = HERE / "models"
MODELS_DIR.mkdir(exist_ok=True)
POSITIONS  = ["QB", "RB", "WR", "TE"]
TRAIN_SEASONS = list(range(2014, 2025))
HOLDOUT    = 2025
SEED       = 42

EXCLUDE = {
    "player_id", "player", "norm_name", "team", "position", "season", "reconstructed",
    "target_ppg", "target_games", "sample_weight",
    "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr",
}


def weighted_mae(y, p, w):
    return float(np.average(np.abs(np.asarray(y) - np.asarray(p)), weights=w))


def main():
    df = pd.read_csv(DATA)
    df = df[df.target_ppg.notna()].copy()
    feats = [c for c in df.columns if c not in EXCLUDE]

    tuned = json.loads(TUNED.read_text()) if TUNED.exists() else {}
    print(f"Features: {len(feats)}  | training Model A (CatBoost) per position\n")
    print(f"  {'pos':4} {'train':>6} {'holdout':>8} {'wMAE':>7} {'baseline':>9} {'better':>8} {'rho':>6}")

    summary = {}
    for pos in POSITIONS:
        pos_df = df[df.position == pos]
        train  = pos_df[pos_df.season.isin(TRAIN_SEASONS)]
        hold   = pos_df[pos_df.season == HOLDOUT]

        # tuned CatBoost params (depth / learning_rate / l2_leaf_reg) + fixed shell
        bp = tuned.get(pos, {}).get("algos", {}).get("catboost", {}).get("best_params", {})
        params = dict(iterations=500, loss_function="MAE", random_seed=SEED,
                      verbose=0, allow_writing_files=False, **bp)

        model = CatBoostRegressor(**params)
        model.fit(train[feats], train.target_ppg, sample_weight=train.sample_weight)

        joblib.dump({"model": model, "feature_cols": feats, "position": pos,
                     "target": "target_ppg", "train_seasons": TRAIN_SEASONS},
                    MODELS_DIR / f"{pos.lower()}_ppg_model.pkl")

        # holdout eval on matched rows (where ppg_3yr exists) for a fair baseline
        matched = hold[hold.ppg_3yr.notna()]
        pred  = model.predict(matched[feats])
        wmae  = weighted_mae(matched.target_ppg, pred, matched.sample_weight)
        base  = weighted_mae(matched.target_ppg, matched.ppg_3yr, matched.sample_weight)
        rho   = float(spearmanr(pred, matched.target_ppg).statistic)
        summary[pos] = {"wMAE": round(wmae, 3), "baseline_wMAE": round(base, 3),
                        "better_by": round(base - wmae, 3), "rho": round(rho, 3),
                        "n_holdout": len(matched), "params": bp}
        print(f"  {pos:4} {len(train):>6} {len(matched):>8} {wmae:>7.3f} {base:>9.3f} "
              f"{base - wmae:>+8.3f} {rho:>6.3f}")

    (MODELS_DIR / "model_a_metrics.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSaved 4 pkls + model_a_metrics.json to {MODELS_DIR}")
    return summary


if __name__ == "__main__":
    main()
