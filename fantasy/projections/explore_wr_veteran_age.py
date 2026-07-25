"""Exploratory, scratch-only WR veteran age-treatment bake-off.

This is explicitly not a preregistered result and must not alter a model pkl or board
CSV. It uses one fixed LightGBM configuration to make four fast, comparable diagnostics:
raw age, age capped at 30, age capped at 32, and no raw-age feature.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

import build_rb_projection as B
import wr_veteran_age_cap_harness as H


HERE = Path(__file__).resolve().parent
LOCAL_STATS = HERE.parent / "seasonal_projections" / "snapshots" / "player_stats_2011_2025.parquet"
TEST_SEASONS = H.TEST_SEASONS
FIXED_LGBM = {"num_leaves": 31, "learning_rate": 0.06, "n_estimators": 400}
VARIANTS = {
    "raw_age": tuple(H.FROZEN_BASELINE_FEATURES),
    "cap_30": tuple("age_cap_30" if col == "age" else col for col in H.FROZEN_BASELINE_FEATURES),
    "cap_32": tuple("age_cap_32" if col == "age" else col for col in H.FROZEN_BASELINE_FEATURES),
    "drop_age": tuple(col for col in H.FROZEN_BASELINE_FEATURES if col != "age"),
}


def _mae(y: pd.Series, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y.to_numpy(float) - np.asarray(pred, dtype=float))))


def _protected_hashes() -> dict[str, str]:
    return H.artifact_hashes()


def load_panel() -> pd.DataFrame:
    required = {"player_id", "player", "position", "is_rookie", "season", *H.FROZEN_BASELINE_FEATURES}
    frame = pd.read_csv(H.SEASON_DATASET, usecols=lambda col: col in required)
    missing = required.difference(frame.columns)
    assert not missing, f"season dataset missing columns: {sorted(missing)}"
    assert not any(any(token in col.lower() for token in H.FORBIDDEN_MARKET_TOKENS) for col in frame.columns)
    frame = frame[(frame.position == "WR") & (frame.is_rookie == 0)].copy()
    # Use the checked-in snapshot rather than nflreadpy's network loader.  The formula
    # matches season_total_target(): regular-season fantasy_points + 0.5 * receptions.
    stats = pd.read_parquet(LOCAL_STATS, columns=["player_id", "season", "season_type", "fantasy_points", "receptions"])
    stats = stats[(stats.season.between(2014, B.MAXOBS)) & (stats.season_type == "REG")].copy()
    stats["half_ppr"] = stats.fantasy_points.fillna(0.0) + 0.5 * stats.receptions.fillna(0.0)
    target = stats.groupby(["player_id", "season"], as_index=False).half_ppr.sum().rename(columns={"half_ppr": "y"})
    frame = frame.merge(target, on=["player_id", "season"], how="left")
    frame.loc[frame.season <= B.MAXOBS, "y"] = frame.loc[frame.season <= B.MAXOBS, "y"].fillna(0.0)
    frame["age_cap_30"] = frame["age"].clip(upper=30.0)
    frame["age_cap_32"] = frame["age"].clip(upper=32.0)
    reference = pd.read_csv(
        HERE / "results" / "wr_walkforward_predictions.csv",
        usecols=["season", "grp", "player_id", "y"],
    )
    reference = reference[(reference.grp == "vet") & reference.season.isin(TEST_SEASONS)].drop(columns="grp")
    observed = frame[frame.season.isin(TEST_SEASONS)][["season", "player_id", "y"]]
    check = reference.merge(observed, on=["season", "player_id"], suffixes=("_stored", "_snapshot"), validate="one_to_one")
    assert len(check) == len(reference) == len(observed) and np.allclose(check.y_stored, check.y_snapshot), \
        "local snapshot target differs from the stored WR walk-forward target"
    return frame


def _model() -> LGBMRegressor:
    # Sequential one-core fitting is deliberate: this is a desktop diagnostic, not nested-CV selection.
    return LGBMRegressor(objective="mae", random_state=B.SEED, verbose=-1, n_jobs=1, **FIXED_LGBM)


def walk_forward(panel: pd.DataFrame, features: tuple[str, ...], variant: str) -> pd.DataFrame:
    rows = []
    for year in TEST_SEASONS:
        train = panel[(panel.season < year) & panel.y.notna()].copy()
        test = panel[(panel.season == year) & panel.y.notna()].copy()
        assert not train.empty and not test.empty and (train.season < year).all()
        model = _model()
        model.fit(train[list(features)].to_numpy(float), train.y.to_numpy(float))
        pred = np.clip(model.predict(test[list(features)].to_numpy(float)), 0, None)
        rows.append(pd.DataFrame({
            "variant": variant, "season": year, "player_id": test.player_id.to_numpy(),
            "player": test.player.to_numpy(), "age": test.age.to_numpy(float),
            "y": test.y.to_numpy(float), "prediction": pred,
        }))
    return pd.concat(rows, ignore_index=True)


def deploy(panel: pd.DataFrame, features: tuple[str, ...], variant: str) -> pd.DataFrame:
    train = panel[(panel.season <= B.MAXOBS) & panel.y.notna()].copy()
    score = panel[panel.season == B.DEPLOY].copy()
    model = _model()
    model.fit(train[list(features)].to_numpy(float), train.y.to_numpy(float))
    score = score[["player_id", "player", "age"]].copy()
    score["variant"] = variant
    score["projection"] = np.clip(model.predict(panel.loc[panel.season == B.DEPLOY, list(features)].to_numpy(float)), 0, None)
    return score


def summarize(walkforward: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant, frame in walkforward.groupby("variant", sort=False):
        older = frame[frame.age >= 30.0]
        rows.append({
            "variant": variant,
            "all_mae": _mae(frame.y, frame.prediction),
            "age_30_plus_mae": _mae(older.y, older.prediction),
            "age_30_plus_rows": len(older),
            "age_30_plus_players": older.player_id.nunique(),
        })
    return pd.DataFrame(rows)


def run() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    before = _protected_hashes()
    panel = load_panel()
    output = []
    deploy_rows = []
    for variant, features in VARIANTS.items():
        print(f"running {variant} ({len(features)} features; fixed single-core LightGBM)...")
        output.append(walk_forward(panel, features, variant))
        deploy_rows.append(deploy(panel, features, variant))
    wf = pd.concat(output, ignore_index=True)
    dep = pd.concat(deploy_rows, ignore_index=True)
    summary = summarize(wf)
    assert before == _protected_hashes(), "exploration changed a protected WR artifact"

    return summary, wf, dep


def main() -> None:
    parser = argparse.ArgumentParser(description="Scratch-only WR veteran age exploration")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("pass --run; no production artifacts are written")
    summary, _, deploy_predictions = run()
    print("\nEXPLORATORY WALK-FORWARD MAE (not a preregistered result)")
    print(summary.round(3).to_string(index=False))
    focus = deploy_predictions[deploy_predictions.player.str.casefold().isin({"terry mclaurin", "mike evans"})]
    print("\n2026 exploratory projections for McLaurin and Evans")
    print(focus.pivot(index="player", columns="variant", values="projection").round(1).to_string())
    print("\nNo exploratory predictions or metrics were written to disk.")


if __name__ == "__main__":
    main()
