"""
Adds total_line and team_spread to features_dataset.csv, then retrains all models.

total_line  : over/under (game pace — higher = more plays = more opportunity)
team_spread : spread from this team's perspective, negative = favored
              (game script — underdogs trail and throw more)

Schedules are already loaded in data_pipeline.ipynb; this just pulls them directly
to avoid re-running the full pipeline.
"""

import os
import sys
import numpy as np
import pandas as pd
import joblib
import nflreadpy as nfl
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

# ── Step 1: Add spread/total features to features_dataset.csv ─────────────────
print("Loading features_dataset.csv ...")
df = pd.read_csv("features_dataset.csv")
print(f"  Before: {df.shape[0]:,} rows x {df.shape[1]} cols")

seasons = sorted(df["season"].unique().tolist())
print(f"  Loading schedules for seasons {seasons[0]}–{seasons[-1]} ...")
sched = nfl.load_schedules(seasons).to_pandas()
sched = sched[sched["game_type"] == "REG"][
    ["season", "week", "home_team", "away_team", "spread_line", "total_line"]
].copy()

home = sched[["season", "week", "home_team", "spread_line", "total_line"]].copy()
home.rename(columns={"home_team": "team"}, inplace=True)
home["team_spread"] = home["spread_line"]           # negative = home favored

away = sched[["season", "week", "away_team", "spread_line", "total_line"]].copy()
away.rename(columns={"away_team": "team"}, inplace=True)
away["team_spread"] = -away["spread_line"]           # flip to away-team perspective

game_ctx = pd.concat([home, away], ignore_index=True)[
    ["season", "week", "team", "total_line", "team_spread"]
]

# Drop if re-running
df = df.drop(columns=["total_line", "team_spread"], errors="ignore")
df = df.merge(game_ctx, on=["season", "week", "team"], how="left")

null_total  = df["total_line"].isna().mean()
null_spread = df["team_spread"].isna().mean()
print(f"  total_line  null rate: {null_total:.1%}")
print(f"  team_spread null rate: {null_spread:.1%}")

# Fill nulls with medians (early-season games occasionally missing lines)
df["total_line"]  = df["total_line"].fillna(df["total_line"].median())
df["team_spread"] = df["team_spread"].fillna(0.0)

df.to_csv("features_dataset.csv", index=False)
print(f"  After:  {df.shape[0]:,} rows x {df.shape[1]} cols")
print("  Saved features_dataset.csv")

# ── Step 2: Retrain all models ─────────────────────────────────────────────────
print("\nRetraining models ...")

RANDOM_SEED   = 42
RAW_PATH      = "raw_dataset.csv"
MODEL_DIR     = "models"
TRAIN_SEASONS = [2020, 2021, 2022, 2023, 2024]
TEST_SEASON   = 2025
POSITIONS     = ["QB", "RB", "WR", "TE"]

np.random.seed(RANDOM_SEED)

XGB_PARAMS = dict(
    n_estimators=500, max_depth=4, learning_rate=0.05,
    min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.5, reg_lambda=1.0, objective="reg:squarederror",
    random_state=RANDOM_SEED, tree_method="hist", n_jobs=-1,
)

IDENTITY_COLS = ["player_id", "player_display_name", "position", "team",
                 "opponent_team", "season", "week"]
TARGET_COL    = "target_half_ppr"
FEATURE_COLS  = [c for c in df.columns if c not in IDENTITY_COLS + [TARGET_COL]]

QB_EXCL = [c for c in FEATURE_COLS if any(k in c for k in [
    "targets", "receptions", "receiving", "target_share", "air_yards_share", "wopr",
])] + ["depth_chart_position"]

FEATURE_COLS_BY_POS = {
    "QB": [c for c in FEATURE_COLS if c not in QB_EXCL],
    "RB": FEATURE_COLS, "WR": FEATURE_COLS, "TE": FEATURE_COLS,
}

print(f"\n=== Main per-position models ===")
print(f"{'Pos':<5} {'Feats':>5} {'Train':>6} {'Test':>5}  {'Old MAE':>7}  {'New MAE':>7}  {'Baseline':>8}")

for pos in POSITIONS:
    pos_feats = FEATURE_COLS_BY_POS[pos]
    pos_df    = df[df["position"] == pos].copy()
    train     = pos_df[pos_df["season"].isin(TRAIN_SEASONS)]
    test      = pos_df[pos_df["season"] == TEST_SEASON]

    X_train, y_train = train[pos_feats], train[TARGET_COL]
    X_test,  y_test  = test[pos_feats],  test[TARGET_COL]

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
    baseline = mean_absolute_error(y_test, test["fantasy_points_half_ppr_roll3"])

    joblib.dump({"model": model, "feature_cols": pos_feats},
                os.path.join(MODEL_DIR, f"{pos.lower()}_model.pkl"))

    old_str = f"{old_mae:.2f}" if old_mae else "  N/A"
    delta   = f"({'+' if new_mae >= (old_mae or new_mae) else ''}{new_mae - old_mae:.2f})" if old_mae else ""
    print(f"  {pos:<3} {len(pos_feats):>5} {len(X_train):>6} {len(X_test):>5}  "
          f"{old_str:>7}  {new_mae:.2f} {delta:<10}  {baseline:.2f}")

print(f"\n=== Per-stat prop models ===")
print(f"{'Model':<25} {'MAE':>7}  {'Old MAE':>7}")

raw = pd.read_csv(RAW_PATH)
raw = raw.sort_values(["player_id", "season", "week"])

def make_stat_target(raw_df, stat_col):
    r = raw_df.copy()
    r[f"target_{stat_col}"] = r.groupby(["player_id", "season"])[stat_col].shift(-1)
    return r[["player_id", "season", "week", f"target_{stat_col}"]]

STAT_SPECS = [
    ("QB", "qb_pass_yards",  "passing_yards"),
    ("QB", "qb_rush_yards",  "rushing_yards"),
    ("RB", "rb_rush_yards",  "rushing_yards"),
    ("RB", "rb_rec_yards",   "receiving_yards"),
    ("WR", "wr_receptions",  "receptions"),
    ("WR", "wr_rec_yards",   "receiving_yards"),
    ("TE", "te_receptions",  "receptions"),
    ("TE", "te_rec_yards",   "receiving_yards"),
]

for pos, model_name, raw_col in STAT_SPECS:
    pos_feats  = FEATURE_COLS_BY_POS[pos]
    target_tbl = make_stat_target(raw, raw_col)
    tgt        = target_tbl.columns[-1]

    stat_df = df[df["position"] == pos].merge(
        target_tbl, on=["player_id", "season", "week"], how="left"
    ).dropna(subset=[tgt])

    train = stat_df[stat_df["season"].isin(TRAIN_SEASONS)]
    test  = stat_df[stat_df["season"] == TEST_SEASON]

    old_path = os.path.join(MODEL_DIR, f"{model_name}_model.pkl")
    old_mae = None
    if os.path.exists(old_path):
        old_m    = joblib.load(old_path)
        old_pred = np.clip(old_m["model"].predict(test[old_m["feature_cols"]]), 0, None)
        old_mae  = mean_absolute_error(test[tgt], old_pred)

    model = XGBRegressor(**XGB_PARAMS)
    model.fit(train[pos_feats], train[tgt],
              eval_set=[(test[pos_feats], test[tgt])], verbose=False)

    new_pred = np.clip(model.predict(test[pos_feats]), 0, None)
    new_mae  = mean_absolute_error(test[tgt], new_pred)

    joblib.dump({"model": model, "feature_cols": pos_feats},
                os.path.join(MODEL_DIR, f"{model_name}_model.pkl"))

    old_str = f"{old_mae:.2f}" if old_mae else "  N/A"
    delta   = f"({'+' if new_mae >= (old_mae or new_mae) else ''}{new_mae - old_mae:.2f})" if old_mae else ""
    print(f"  {model_name:<23} {new_mae:>7.2f}  {old_str:>7} {delta}")

print("\nDone.")
