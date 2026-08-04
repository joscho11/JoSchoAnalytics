"""Retrain all fantasy models (4 main + 8 per-stat) and STAGE the artifacts.

Nothing under `fantasy/models/` is touched. Artifacts, metrics and a run manifest go to
`fantasy/staging/models/` and `fantasy/staging/`; promotion is a separate, gated step
(`promote_staging.py`).

    python retrain_models.py                      # train from the staged dataset
    python retrain_models.py --run-tag repeat     # second run, for determinism hashing
    python retrain_models.py --data features_dataset.csv --out-dir staging/models_olddata

2025 is the HOLDOUT and is never added to training.

The four-way comparison written to `staging/metrics.json`:
    old_model_old_data   published pkl scored on the published features_dataset.csv
    old_model_new_data   published pkl scored on the corrected staged dataset
    new_model_new_data   freshly trained pkl scored on the corrected staged dataset
    baseline_new_data    fantasy_points_half_ppr_roll3 as the prediction
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from xgboost import XGBRegressor

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

RANDOM_SEED = 42
PROD_DATA_PATH = _HERE / "features_dataset.csv"
PROD_RAW_PATH = _HERE / "raw_dataset.csv"
STAGING = _HERE / "staging"
DEFAULT_DATA = STAGING / "features_dataset.staging.csv"
DEFAULT_RAW = STAGING / "raw_dataset.staging.csv"
DEFAULT_OUT = STAGING / "models"
PROD_MODEL_DIR = _HERE / "models"

TRAIN_SEASONS = [2020, 2021, 2022, 2023, 2024]
TEST_SEASON = max(TRAIN_SEASONS) + 1          # 2025 holdout — never trained on
POSITIONS = ["QB", "RB", "WR", "TE"]

XGB_PARAMS = dict(
    n_estimators=500, max_depth=4, learning_rate=0.05, min_child_weight=5,
    subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5, reg_lambda=1.0,
    objective="reg:squarederror", random_state=RANDOM_SEED, tree_method="hist",
    n_jobs=-1, early_stopping_rounds=25,
)

IDENTITY_COLS = ["player_id", "player_display_name", "position", "team",
                 "opponent_team", "season", "week"]
TARGET_COL = "target_half_ppr"

STAT_SPECS = [
    ("QB", "qb_pass_yards", "passing_yards"),
    ("QB", "qb_rush_yards", "rushing_yards"),
    ("RB", "rb_rush_yards", "rushing_yards"),
    ("RB", "rb_rec_yards", "receiving_yards"),
    ("WR", "wr_receptions", "receptions"),
    ("WR", "wr_rec_yards", "receiving_yards"),
    ("TE", "te_receptions", "receptions"),
    ("TE", "te_rec_yards", "receiving_yards"),
]


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def feature_order_hash(cols) -> str:
    return hashlib.sha256("\n".join(cols).encode("utf-8")).hexdigest()[:16]


def feature_sets(df):
    feature_cols = [c for c in df.columns if c not in IDENTITY_COLS + [TARGET_COL]]
    qb_excl = [c for c in feature_cols if any(k in c for k in [
        "targets", "receptions", "receiving", "target_share", "air_yards_share", "wopr",
    ])] + ["depth_chart_position"]
    return {"QB": [c for c in feature_cols if c not in qb_excl],
            "RB": feature_cols, "WR": feature_cols, "TE": feature_cols}


def _metrics(y_true, y_pred):
    return {"n": int(len(y_true)),
            "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
            "rmse": round(float(root_mean_squared_error(y_true, y_pred)), 4)}


def score_saved_model(pkl_path, frame):
    """Score an existing pkl on `frame`. A missing REQUIRED feature ABORTS."""
    saved = joblib.load(pkl_path)
    cols = saved["feature_cols"]
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise RuntimeError(f"{Path(pkl_path).name}: dataset is missing required model "
                           f"features {missing} — refusing to score on filled values")
    return saved["model"].predict(frame[cols])


def train_main_models(df, out_dir, feats_by_pos):
    out = {}
    for pos in POSITIONS:
        cols = feats_by_pos[pos]
        pos_df = df[df["position"] == pos]
        train = pos_df[pos_df["season"].isin(TRAIN_SEASONS)]
        test = pos_df[pos_df["season"] == TEST_SEASON]
        X, y = train[cols], train[TARGET_COL]
        cut = int(len(X) * 0.85)
        model = XGBRegressor(**XGB_PARAMS)
        model.fit(X.iloc[:cut], y.iloc[:cut],
                  eval_set=[(X.iloc[cut:], y.iloc[cut:])], verbose=False)
        path = out_dir / f"{pos.lower()}_model.pkl"
        joblib.dump({"model": model, "feature_cols": cols}, path)
        out[pos] = {"path": path, "n_train": int(len(X)), "n_test": int(len(test)),
                    "n_features": len(cols),
                    "feature_order_hash": feature_order_hash(cols),
                    "best_iteration": int(getattr(model, "best_iteration", -1))}
    return out


def stat_target_table(raw, stat_col):
    raw = raw.sort_values(["player_id", "season", "week"]).copy()
    raw[f"target_{stat_col}"] = raw.groupby(["player_id", "season"])[stat_col].shift(-1)
    return raw[["player_id", "season", "week", f"target_{stat_col}"]]


def train_stat_models(df, raw, out_dir, feats_by_pos):
    out = {}
    for pos, name, raw_col in STAT_SPECS:
        cols = feats_by_pos[pos]
        tbl = stat_target_table(raw, raw_col)
        tgt = tbl.columns[-1]
        sdf = df[df["position"] == pos].merge(
            tbl, on=["player_id", "season", "week"], how="left").dropna(subset=[tgt])
        train = sdf[sdf["season"].isin(TRAIN_SEASONS)]
        test = sdf[sdf["season"] == TEST_SEASON]
        X, y = train[cols], train[tgt]
        cut = int(len(X) * 0.85)
        model = XGBRegressor(**XGB_PARAMS)
        model.fit(X.iloc[:cut], y.iloc[:cut],
                  eval_set=[(X.iloc[cut:], y.iloc[cut:])], verbose=False)
        path = out_dir / f"{name}_model.pkl"
        joblib.dump({"model": model, "feature_cols": cols}, path)
        preds = np.clip(model.predict(test[cols]), 0, None)
        out[name] = {"path": path, "position": pos, "raw_col": raw_col,
                     "n_train": int(len(X)), "n_test": int(len(test)),
                     "feature_order_hash": feature_order_hash(cols),
                     "new_model_new_data": _metrics(test[tgt], preds)}
    return out


def four_way(df_new, df_old, raw_new, raw_old, new_models):
    """The four requested comparisons for the holdout season."""
    main = {}
    for pos in POSITIONS:
        new_hold = df_new[(df_new["position"] == pos) & (df_new["season"] == TEST_SEASON)]
        old_hold = df_old[(df_old["position"] == pos) & (df_old["season"] == TEST_SEASON)]
        prod_pkl = PROD_MODEL_DIR / f"{pos.lower()}_model.pkl"
        entry = {
            "old_model_old_data": _metrics(
                old_hold[TARGET_COL], score_saved_model(prod_pkl, old_hold)),
            "old_model_new_data": _metrics(
                new_hold[TARGET_COL], score_saved_model(prod_pkl, new_hold)),
            "new_model_new_data": _metrics(
                new_hold[TARGET_COL],
                score_saved_model(new_models[pos]["path"], new_hold)),
            "baseline_new_data": _metrics(
                new_hold[TARGET_COL], new_hold["fantasy_points_half_ppr_roll3"]),
            "baseline_old_data": _metrics(
                old_hold[TARGET_COL], old_hold["fantasy_points_half_ppr_roll3"]),
        }
        # paired per-row |error| difference, new model vs the rolling baseline, on the
        # SAME holdout rows — a mean MAE gap smaller than ~2 SE is not a real win
        y = new_hold[TARGET_COL].to_numpy(float)
        e_model = np.abs(y - score_saved_model(new_models[pos]["path"], new_hold))
        e_base = np.abs(y - new_hold["fantasy_points_half_ppr_roll3"].to_numpy(float))
        d = e_base - e_model
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        entry["new_vs_baseline_paired"] = {
            "mean_mae_gain": round(float(d.mean()), 4),
            "se": round(se, 4),
            "t": round(float(d.mean() / se), 2) if se else None,
            "n": int(len(d)),
        }
        main[pos] = entry

    stats = {}
    for pos, name, raw_col in STAT_SPECS:
        prod_pkl = PROD_MODEL_DIR / f"{name}_model.pkl"
        rows = {}
        for label, df_, raw_ in (("old_data", df_old, raw_old), ("new_data", df_new, raw_new)):
            tbl = stat_target_table(raw_, raw_col)
            tgt = tbl.columns[-1]
            sdf = df_[df_["position"] == pos].merge(
                tbl, on=["player_id", "season", "week"], how="left").dropna(subset=[tgt])
            hold = sdf[sdf["season"] == TEST_SEASON]
            rows[f"old_model_{label}"] = _metrics(
                hold[tgt], np.clip(score_saved_model(prod_pkl, hold), 0, None))
            rows[f"baseline_{label}"] = _metrics(hold[tgt], hold[raw_col + "_roll3"]) \
                if f"{raw_col}_roll3" in hold.columns else None
            if label == "new_data":
                rows["new_model_new_data"] = _metrics(
                    hold[tgt],
                    np.clip(score_saved_model(
                        DEFAULT_OUT / f"{name}_model.pkl", hold), 0, None))
        stats[name] = rows
    return {"main": main, "per_stat": stats}


def git_head():
    try:
        return subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
                              cwd=_HERE, capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--run-tag", default="primary")
    ap.add_argument("--skip-comparison", action="store_true")
    args = ap.parse_args()

    np.random.seed(RANDOM_SEED)
    data_path, raw_path = Path(args.data), Path(args.raw)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path)
    raw = pd.read_csv(raw_path)
    req = {"position", "season", "week", "player_id", TARGET_COL}
    missing = req - set(df.columns)
    if missing:
        raise RuntimeError(f"{data_path.name} missing required columns: {sorted(missing)}")
    assert TEST_SEASON not in TRAIN_SEASONS, "holdout season leaked into training"

    feats_by_pos = feature_sets(df)
    print(f"Dataset {data_path.name}: {df.shape[0]:,} x {df.shape[1]}")
    print(f"Features: QB={len(feats_by_pos['QB'])}  RB/WR/TE={len(feats_by_pos['RB'])}")

    print("\n=== Main per-position models ===")
    new_models = train_main_models(df, out_dir, feats_by_pos)
    for pos, m in new_models.items():
        print(f"  {pos}: train={m['n_train']} holdout={m['n_test']} "
              f"feats={m['n_features']} best_iter={m['best_iteration']}")

    print("\n=== Per-stat prop models ===")
    stat_models = train_stat_models(df, raw, out_dir, feats_by_pos)
    for name, m in stat_models.items():
        print(f"  {name:<16} train={m['n_train']:>6} holdout={m['n_test']:>5} "
              f"MAE={m['new_model_new_data']['mae']:.4f}")

    manifest = {
        "run_tag": args.run_tag,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "executable": sys.executable,
            "pandas": pd.__version__, "numpy": np.__version__,
            "xgboost": __import__("xgboost").__version__,
            "sklearn": __import__("sklearn").__version__,
            "joblib": joblib.__version__,
        },
        "git_head": git_head(),
        "seed": RANDOM_SEED,
        "xgb_params": {k: v for k, v in XGB_PARAMS.items()},
        "train_seasons": TRAIN_SEASONS,
        "holdout_season": TEST_SEASON,
        "data": {"features": str(data_path), "features_sha256": sha256(data_path),
                 "raw": str(raw_path), "raw_sha256": sha256(raw_path)},
        "code_sha256": {p.name: sha256(_HERE / p.name) for p in [
            Path("depth_adapter.py"), Path("depth_features.py"),
            Path("build_staging_dataset.py"), Path("retrain_models.py"),
            Path("gate_staging_dataset.py"), Path("equivalence_checks.py")]},
        "feature_order_hash": {pos: feature_order_hash(c)
                               for pos, c in feats_by_pos.items()},
        "artifacts": {},
        "models": {pos: {k: v for k, v in m.items() if k != "path"}
                   for pos, m in new_models.items()},
        "stat_models": {n: {k: (v if k != "path" else None) for k, v in m.items()}
                        for n, m in stat_models.items()},
    }
    for p in sorted(out_dir.glob("*.pkl")):
        manifest["artifacts"][p.name] = sha256(p)

    if not args.skip_comparison:
        print("\n=== Four-way holdout comparison ===")
        df_old = pd.read_csv(PROD_DATA_PATH)
        raw_old = pd.read_csv(PROD_RAW_PATH)
        cmp = four_way(df, df_old, raw, raw_old, new_models)
        manifest["comparison"] = cmp
        hdr = f"{'Pos':<4} {'n_new':>6} {'oldM/oldD':>10} {'oldM/newD':>10} " \
              f"{'newM/newD':>10} {'base/newD':>10}"
        print(hdr)
        for pos, e in cmp["main"].items():
            print(f"{pos:<4} {e['new_model_new_data']['n']:>6} "
                  f"{e['old_model_old_data']['mae']:>10.4f} "
                  f"{e['old_model_new_data']['mae']:>10.4f} "
                  f"{e['new_model_new_data']['mae']:>10.4f} "
                  f"{e['baseline_new_data']['mae']:>10.4f}")

    mpath = STAGING / f"manifest_{args.run_tag}.json"
    mpath.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(f"\nStaged {len(manifest['artifacts'])} artifacts in {out_dir}")
    print(f"Manifest: {mpath}")


if __name__ == "__main__":
    main()
