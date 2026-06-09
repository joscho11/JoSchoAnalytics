"""Train production Model A (PPG projection), per position, with LightGBM.

Switched CatBoost -> LightGBM (2026-06-08). A controlled bakeoff (model_bakeoff.py)
showed LightGBM / RandomForest / XGBoost all beat the old CatBoost by ~0.15-0.17
games-weighted PPG MAE at every position, while tuning CatBoost's own hyperparameters
did nothing -- it's the algorithm. The canonical ADP-mispricing eval (surprise_eval.py)
is built on this LightGBM config, so the board's Model A now matches it.

INJURY FEATURES REMOVED: prior_games_missed / missed_prior_season are dropped. PPG is a
RATE -- a player's per-game output is roughly injury-independent -- so injury-history
features are noise for this target, and dropping them slightly improves the holdout MAE.
(Availability is a separate, weakly-predictable problem handled by Model B; and on season
TOTALS even Model B hurts, so totals use a near-constant games estimate -- see eval_totals.py.)

One LightGBM regressor per position, trained 2014-2024 (games-weighted), 2025 holdout.
Saves {pos}_ppg_model.pkl to models/ in the same format the board expects
({'model', 'feature_cols', 'position', ...}).

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
from lightgbm import LGBMRegressor

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE       = Path(__file__).resolve().parent
DATA       = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
MODELS_DIR.mkdir(exist_ok=True)
POSITIONS  = ["QB", "RB", "WR", "TE"]
TRAIN_SEASONS = list(range(2014, 2025))
HOLDOUT    = 2025
SEED       = 42

# ids / targets / market signals are never features
EXCLUDE = {
    "player_id", "player", "norm_name", "team", "position", "season", "reconstructed",
    "target_ppg", "target_games", "sample_weight",
    "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr",
}
# injury-prediction features removed on purpose (not worth predicting; noise for a rate)
INJURY_FEATURES = {"prior_games_missed", "missed_prior_season"}

# LightGBM params (bakeoff config, lightly regularized for the smaller per-position samples)
LGBM_PARAMS = dict(objective="mae", num_leaves=20, learning_rate=0.03, n_estimators=600,
                   min_child_samples=25, reg_lambda=3.0, subsample=0.8, subsample_freq=1,
                   random_state=SEED, n_jobs=-1, verbose=-1)


def weighted_mae(y, p, w):
    return float(np.average(np.abs(np.asarray(y) - np.asarray(p)), weights=w))


def main():
    df = pd.read_csv(DATA)
    df = df[df.target_ppg.notna()].copy()
    feats = [c for c in df.columns if c not in EXCLUDE and c not in INJURY_FEATURES]

    print(f"Model A = LightGBM per position | {len(feats)} features "
          f"(injury features removed: {sorted(INJURY_FEATURES)})\n")
    print(f"  {'pos':4} {'train':>6} {'holdout':>8} {'wMAE':>7} {'baseline':>9} {'better':>8} {'rho':>6}")

    summary = {}
    for pos in POSITIONS:
        pos_df = df[df.position == pos]
        train  = pos_df[pos_df.season.isin(TRAIN_SEASONS)]
        hold   = pos_df[pos_df.season == HOLDOUT]

        model = LGBMRegressor(**LGBM_PARAMS)
        model.fit(train[feats], train.target_ppg, sample_weight=train.sample_weight)

        joblib.dump({"model": model, "feature_cols": feats, "position": pos,
                     "target": "target_ppg", "train_seasons": TRAIN_SEASONS,
                     "algo": "lightgbm"},
                    MODELS_DIR / f"{pos.lower()}_ppg_model.pkl")

        matched = hold[hold.ppg_3yr.notna()]            # matched rows so the baseline can compete
        pred  = model.predict(matched[feats])
        wmae  = weighted_mae(matched.target_ppg, pred, matched.sample_weight)
        base  = weighted_mae(matched.target_ppg, matched.ppg_3yr, matched.sample_weight)
        rho   = float(spearmanr(pred, matched.target_ppg).statistic)
        summary[pos] = {"wMAE": round(wmae, 3), "baseline_wMAE": round(base, 3),
                        "better_by": round(base - wmae, 3), "rho": round(rho, 3),
                        "n_holdout": len(matched)}
        print(f"  {pos:4} {len(train):>6} {len(matched):>8} {wmae:>7.3f} {base:>9.3f} "
              f"{base - wmae:>+8.3f} {rho:>6.3f}")

    (MODELS_DIR / "model_a_metrics.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSaved 4 LightGBM pkls + model_a_metrics.json to {MODELS_DIR}")
    return summary


if __name__ == "__main__":
    main()
