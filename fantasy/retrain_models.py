"""
Retrain all fantasy models (4 main + 8 per-stat) using the current features_dataset.csv.
Automatically picks up any new columns (e.g. snap_pct_roll3/5/trend).
Run from the fantasy/ directory.
"""

import os
import sys
import pandas as pd
import numpy as np
import joblib
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

# ── Constants ──────────────────────────────────────────────────────────────────
RANDOM_SEED   = 42
DATA_PATH     = "features_dataset.csv"
RAW_PATH      = "raw_dataset.csv"
MODEL_DIR     = "models"
TRAIN_SEASONS = [2020, 2021, 2022, 2023, 2024]
TEST_SEASON   = 2025
POSITIONS     = ["QB", "RB", "WR", "TE"]

np.random.seed(RANDOM_SEED)

XGB_PARAMS = dict(
    n_estimators     = 500,
    max_depth        = 4,
    learning_rate    = 0.05,
    min_child_weight = 5,
    subsample        = 0.8,
    colsample_bytree = 0.8,
    reg_alpha        = 0.5,
    reg_lambda       = 1.0,
    objective        = "reg:squarederror",
    random_state     = RANDOM_SEED,
    tree_method      = "hist",
    n_jobs           = -1,
)

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading features_dataset.csv ...")
df = pd.read_csv(DATA_PATH)
print(f"Dataset: {df.shape[0]:,} rows x {df.shape[1]} cols")

IDENTITY_COLS = ["player_id", "player_display_name", "position", "team",
                 "opponent_team", "season", "week"]
TARGET_COL    = "target_half_ppr"
FEATURE_COLS  = [c for c in df.columns if c not in IDENTITY_COLS + [TARGET_COL]]

QB_EXCL = [c for c in FEATURE_COLS if any(k in c for k in [
    "targets", "receptions", "receiving",
    "target_share", "air_yards_share", "wopr",
])] + ["depth_chart_position"]

FEATURE_COLS_BY_POS = {
    "QB": [c for c in FEATURE_COLS if c not in QB_EXCL],
    "RB": FEATURE_COLS,
    "WR": FEATURE_COLS,
    "TE": FEATURE_COLS,
}

print(f"Feature counts: QB={len(FEATURE_COLS_BY_POS['QB'])}  "
      f"RB/WR/TE={len(FEATURE_COLS_BY_POS['RB'])}")

# ── Show OLD model feature counts for comparison ───────────────────────────────
print("\n--- OLD model feature counts ---")
for pos in POSITIONS:
    path = os.path.join(MODEL_DIR, f"{pos.lower()}_model.pkl")
    if os.path.exists(path):
        old = joblib.load(path)
        print(f"  {pos}: {len(old['feature_cols'])} features")

# ── Step 1: Retrain main per-position models ───────────────────────────────────
print("\n=== Step 1: Main per-position models ===")
print(f"{'Pos':<5} {'Feats':>5} {'Train':>6} {'Test':>5}  {'Old MAE':>7}  {'New MAE':>7}  {'Baseline':>8}  {'RMSE':>6}")

results = {}
for pos in POSITIONS:
    pos_feats = FEATURE_COLS_BY_POS[pos]
    pos_df    = df[df["position"] == pos].copy()
    train     = pos_df[pos_df["season"].isin(TRAIN_SEASONS)]
    test      = pos_df[pos_df["season"] == TEST_SEASON]

    X_train, y_train = train[pos_feats], train[TARGET_COL]
    X_test,  y_test  = test[pos_feats],  test[TARGET_COL]

    # Old MAE
    old_path = os.path.join(MODEL_DIR, f"{pos.lower()}_model.pkl")
    old_mae = None
    if os.path.exists(old_path):
        old_m    = joblib.load(old_path)
        old_pred = old_m["model"].predict(test[old_m["feature_cols"]])
        old_mae  = mean_absolute_error(y_test, old_pred)

    model = XGBRegressor(**XGB_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    new_pred = model.predict(X_test)
    new_mae  = mean_absolute_error(y_test, new_pred)
    rmse     = root_mean_squared_error(y_test, new_pred)
    baseline = mean_absolute_error(y_test, test["fantasy_points_half_ppr_roll3"])

    save_path = os.path.join(MODEL_DIR, f"{pos.lower()}_model.pkl")
    joblib.dump({"model": model, "feature_cols": pos_feats}, save_path)

    old_str = f"{old_mae:.2f}" if old_mae is not None else "  N/A"
    delta   = f" ({'+' if new_mae > old_mae else ''}{new_mae - old_mae:.2f})" if old_mae else ""
    print(f"  {pos:<3} {len(pos_feats):>5} {len(X_train):>6} {len(X_test):>5}  "
          f"{old_str:>7}  {new_mae:.2f}{delta:<10}  {baseline:.2f}   {rmse:.2f}")

    results[pos] = {"mae": new_mae, "rmse": rmse, "baseline": baseline}

# ── Step 2: Retrain per-stat prop models ───────────────────────────────────────
print("\n=== Step 2: Per-stat prop models ===")

raw = pd.read_csv(RAW_PATH)
raw = raw.sort_values(["player_id", "season", "week"])

def make_stat_target(raw_df, stat_col):
    raw_df = raw_df.copy()
    raw_df[f"target_{stat_col}"] = raw_df.groupby(["player_id", "season"])[stat_col].shift(-1)
    return raw_df[["player_id", "season", "week", f"target_{stat_col}"]]

def train_stat_model(features_df, pos, stat_name, target_col, pos_feats):
    stat_df = features_df[features_df["position"] == pos].merge(
        target_col, on=["player_id", "season", "week"], how="left"
    ).dropna(subset=[target_col.columns[-1]])

    tgt   = target_col.columns[-1]
    train = stat_df[stat_df["season"].isin(TRAIN_SEASONS)]
    test  = stat_df[stat_df["season"] == TEST_SEASON]

    X_tr, y_tr = train[pos_feats], train[tgt]
    X_te, y_te = test[pos_feats],  test[tgt]

    model = XGBRegressor(**XGB_PARAMS)
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    preds = np.clip(model.predict(X_te), 0, None)
    mae  = mean_absolute_error(y_te, preds)
    rmse = root_mean_squared_error(y_te, preds)

    save_path = os.path.join(MODEL_DIR, f"{stat_name}_model.pkl")
    joblib.dump({"model": model, "feature_cols": pos_feats}, save_path)
    return mae, rmse, len(X_tr), len(X_te)

STAT_SPECS = [
    ("QB", "qb_pass_yards",   "passing_yards"),
    ("QB", "qb_rush_yards",   "rushing_yards"),
    ("RB", "rb_rush_yards",   "rushing_yards"),
    ("RB", "rb_rec_yards",    "receiving_yards"),
    ("WR", "wr_receptions",   "receptions"),
    ("WR", "wr_rec_yards",    "receiving_yards"),
    ("TE", "te_receptions",   "receptions"),
    ("TE", "te_rec_yards",    "receiving_yards"),
]

print(f"{'Model':<25} {'Train':>6} {'Test':>5}  {'MAE':>7}  {'RMSE':>6}")
for pos, model_name, raw_col in STAT_SPECS:
    pos_feats  = FEATURE_COLS_BY_POS[pos]
    target_tbl = make_stat_target(raw, raw_col)
    mae, rmse, n_tr, n_te = train_stat_model(df, pos, model_name, target_tbl, pos_feats)
    print(f"  {model_name:<23} {n_tr:>6} {n_te:>5}  {mae:>7.2f}  {rmse:>6.2f}")

print("\nDone. All models saved to", MODEL_DIR)
