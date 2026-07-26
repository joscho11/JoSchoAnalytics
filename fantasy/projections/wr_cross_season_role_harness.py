"""Frozen read-only harness for PREREG_wr_cross_season_role_2026-07-26.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "fantasy/seasonal_projections/season_dataset_2014_2026.csv"
STATS = (
    ROOT
    / "fantasy/seasonal_projections/snapshots/player_stats_1999_2025.parquet"
)
MODELS = ROOT / "fantasy/projections/models"
RESULTS = ROOT / "fantasy/projections/results"

PROTECTED_MODELS = {
    "wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
    "wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
}
BASE_FEATURES = [
    "prior_ppg",
    "prior_half_ppr",
    "prior_games",
    "ppg_2yr",
    "ppg_3yr",
    "ppg_trend",
    "career_high_ppg",
    "prior_snap_share_pg",
    "prior_targets_pg",
    "prior_carries_pg",
    "prior_receptions_pg",
    "prior_touches_pg",
    "prior_target_share",
    "prior_air_yards_share",
    "prior_adot",
    "prior_td_rate",
    "prior_yptarget",
    "prior_ypc",
    "prior_rec_epa",
    "prior_rush_epa",
    "age",
    "years_exp",
    "draft_round",
    "draft_pick",
    "prior_team_pass_rate",
    "prior_team_plays",
    "vacated_target_share",
    "vacated_rush_share",
    "coach_changed",
    "qb_changed",
    "prior_games_missed",
    "missed_prior_season",
]
NEW_FEATURES = ["target_share_lag2", "target_share_delta"]
ID_COLS = ["player_id", "player", "position", "season", "is_rookie"]
DATA_COLS = list(dict.fromkeys(ID_COLS + BASE_FEATURES))
PRIMARY_YEARS = [2018, 2019, 2020]
COMPAT_YEARS = [2021, 2022, 2023, 2024, 2025]
ALL_TEST_YEARS = PRIMARY_YEARS + COMPAT_YEARS


def file_hash(path: Path, algorithm: str = "md5") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_state() -> dict:
    models = {name: file_hash(MODELS / name) for name in PROTECTED_MODELS}
    results = {
        path.name: file_hash(path, "sha256") for path in sorted(RESULTS.glob("*.csv"))
    }
    return {"models": models, "results": results}


def assert_protected(state: dict) -> None:
    assert state["models"] == PROTECTED_MODELS, (
        state["models"],
        PROTECTED_MODELS,
    )


def load_panel() -> pd.DataFrame:
    assert not any(
        column.startswith(("sleeper", "adp")) for column in DATA_COLS
    )
    panel = pd.read_csv(DATA, usecols=DATA_COLS, low_memory=False)
    panel = panel[
        panel["position"].eq("WR")
        & panel["is_rookie"].eq(0)
        & panel["season"].between(2014, 2026)
    ].copy()
    assert not panel.duplicated(["player_id", "season"]).any()
    return panel


def add_cross_season_role(panel: pd.DataFrame) -> pd.DataFrame:
    lag2 = panel[["player_id", "season", "prior_target_share"]].copy()
    lag2["season"] += 1
    lag2 = lag2.rename(columns={"prior_target_share": "target_share_lag2"})
    out = panel.merge(
        lag2, on=["player_id", "season"], how="left", validate="one_to_one"
    )

    teams = pd.read_parquet(
        STATS, columns=["player_id", "season", "season_type", "team"]
    )
    teams = teams[
        teams["season_type"].eq("REG")
        & teams["season"].between(2012, 2025)
        & teams["player_id"].notna()
        & teams["team"].notna()
    ]
    movers = (
        teams.groupby(["player_id", "season"])["team"]
        .nunique()
        .gt(1)
        .rename("is_mover")
        .reset_index()
    )
    for lag, name in ((1, "prior_is_mover"), (2, "lag2_is_mover")):
        flag = movers.copy()
        flag["season"] += lag
        flag = flag.rename(columns={"is_mover": name})
        out = out.merge(
            flag, on=["player_id", "season"], how="left", validate="one_to_one"
        )
    invalid = out["prior_is_mover"].fillna(False) | out["lag2_is_mover"].fillna(
        False
    )
    out.loc[invalid, "target_share_lag2"] = np.nan
    out["target_share_delta"] = (
        out["prior_target_share"] - out["target_share_lag2"]
    )
    out.loc[invalid, "target_share_delta"] = np.nan
    return out


def coverage_report(panel: pd.DataFrame) -> dict:
    present = panel[NEW_FEATURES].notna().all(axis=1)
    report = {}
    for year in ALL_TEST_YEARS + [2026]:
        rows = panel["season"].eq(year)
        report[str(year)] = {
            "n": int(rows.sum()),
            "covered": int((rows & present).sum()),
            "coverage": float(present[rows].mean()),
            "train_n": int((panel["season"] < year).sum())
            if year in ALL_TEST_YEARS
            else None,
        }
    historical = panel["season"].isin(ALL_TEST_YEARS)
    report["pooled_2018_2025"] = {
        "n": int(historical.sum()),
        "covered": int((historical & present).sum()),
        "coverage": float(present[historical].mean()),
    }
    return report


def structural_check(panel: pd.DataFrame) -> dict:
    coverage = coverage_report(panel)
    assert len(BASE_FEATURES) == 32
    assert len(BASE_FEATURES + NEW_FEATURES) == 34
    assert not set(BASE_FEATURES) & set(NEW_FEATURES)
    assert all(column in panel.columns for column in BASE_FEATURES + NEW_FEATURES)
    assert all(coverage[str(year)]["train_n"] >= 100 for year in ALL_TEST_YEARS)
    assert all(coverage[str(year)]["coverage"] >= 0.40 for year in ALL_TEST_YEARS)
    shift = abs(
        coverage["2026"]["coverage"]
        - coverage["pooled_2018_2025"]["coverage"]
    )
    assert shift <= 0.10, shift
    return {
        "baseline_feature_count": len(BASE_FEATURES),
        "challenger_feature_count": len(BASE_FEATURES + NEW_FEATURES),
        "new_features": NEW_FEATURES,
        "market_columns_loaded": [],
        "coverage": coverage,
        "coverage_shift_2026_vs_2018_2025": float(shift),
    }


def load_target() -> pd.DataFrame:
    stats = pd.read_parquet(
        STATS,
        columns=[
            "player_id",
            "season",
            "season_type",
            "fantasy_points",
            "receptions",
        ],
    )
    stats = stats[
        stats["season_type"].eq("REG") & stats["season"].between(2014, 2025)
    ].copy()
    stats["y"] = stats["fantasy_points"].fillna(0.0) + 0.5 * stats[
        "receptions"
    ].fillna(0.0)
    return stats.groupby(["player_id", "season"], as_index=False)["y"].sum()


def make_model() -> LGBMRegressor:
    return LGBMRegressor(
        objective="mae",
        num_leaves=15,
        learning_rate=0.03,
        n_estimators=400,
        random_state=42,
        verbose=-1,
        n_jobs=-1,
    )


def walk_forward(panel: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    rows = []
    for year in years:
        train = panel[panel["season"].lt(year)]
        test = panel[panel["season"].eq(year)].copy()
        assert len(train) >= 100 and len(test) > 0
        assert train["season"].max() < year
        baseline = make_model()
        challenger = make_model()
        baseline.fit(train[BASE_FEATURES], train["y"])
        challenger.fit(train[BASE_FEATURES + NEW_FEATURES], train["y"])
        test["baseline"] = np.clip(
            baseline.predict(test[BASE_FEATURES]), 0.0, None
        )
        test["challenger"] = np.clip(
            challenger.predict(test[BASE_FEATURES + NEW_FEATURES]), 0.0, None
        )
        rows.append(test)
    return pd.concat(rows, ignore_index=True)


def rho(y: pd.Series, prediction: pd.Series) -> float:
    return float(spearmanr(y, prediction).statistic)


def model_metrics(frame: pd.DataFrame, prediction: str) -> dict:
    error = frame["y"] - frame[prediction]
    return {
        "mae": float(error.abs().mean()),
        "rho": rho(frame["y"], frame[prediction]),
        "bias_y_minus_pred": float(error.mean()),
    }


def clustered_ci(
    frame: pd.DataFrame, seed: int = 20260726, reps: int = 20_000
) -> tuple[float, float]:
    work = frame.assign(
        improvement=(
            (frame["y"] - frame["baseline"]).abs()
            - (frame["y"] - frame["challenger"]).abs()
        )
    )
    clusters = work.groupby("player_id")["improvement"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(clusters), size=(reps, len(clusters)))
    sums = clusters["sum"].to_numpy()[draws].sum(axis=1)
    counts = clusters["count"].to_numpy()[draws].sum(axis=1)
    lo, hi = np.quantile(sums / counts, [0.025, 0.975])
    return float(lo), float(hi)


def mark_top_tail(frame: pd.DataFrame) -> pd.Series:
    top = pd.Series(False, index=frame.index)
    for _, rows in frame.groupby("season"):
        count = math.ceil(0.10 * len(rows))
        top.loc[rows.nlargest(count, "y").index] = True
    return top


def panel_report(frame: pd.DataFrame) -> dict:
    baseline = model_metrics(frame, "baseline")
    challenger = model_metrics(frame, "challenger")
    by_year = {}
    both_better = 0
    for year, rows in frame.groupby("season"):
        base_year = model_metrics(rows, "baseline")
        challenger_year = model_metrics(rows, "challenger")
        delta_mae = challenger_year["mae"] - base_year["mae"]
        delta_rho = challenger_year["rho"] - base_year["rho"]
        if delta_mae < 0 and delta_rho > 0:
            both_better += 1
        by_year[str(int(year))] = {
            "n": len(rows),
            "baseline": base_year,
            "challenger": challenger_year,
            "delta_mae_challenger_minus_baseline": float(delta_mae),
            "delta_rho_challenger_minus_baseline": float(delta_rho),
        }

    top = mark_top_tail(frame)
    base_abs = (frame["y"] - frame["baseline"]).abs()
    challenger_abs = (frame["y"] - frame["challenger"]).abs()
    third = frame[frame["years_exp"].eq(2)]
    third_by_year = {
        str(int(year)): float((rows["y"] - rows["challenger"]).mean())
        for year, rows in third.groupby("season")
    }
    return {
        "n": len(frame),
        "baseline": baseline,
        "challenger": challenger,
        "delta_mae_challenger_minus_baseline": float(
            challenger["mae"] - baseline["mae"]
        ),
        "delta_rho_challenger_minus_baseline": float(
            challenger["rho"] - baseline["rho"]
        ),
        "both_metrics_better_folds": both_better,
        "paired_abs_error_improvement": float((base_abs - challenger_abs).mean()),
        "player_clustered_95pct_ci": list(clustered_ci(frame)),
        "top_tail_n": int(top.sum()),
        "top_tail_baseline_bias_y_minus_pred": float(
            (frame.loc[top, "y"] - frame.loc[top, "baseline"]).mean()
        ),
        "top_tail_challenger_bias_y_minus_pred": float(
            (frame.loc[top, "y"] - frame.loc[top, "challenger"]).mean()
        ),
        "non_top_delta_mae_challenger_minus_baseline": float(
            challenger_abs[~top].mean() - base_abs[~top].mean()
        ),
        "third_year_diagnostic": {
            "n": len(third),
            "bias_y_minus_challenger": float(
                (third["y"] - third["challenger"]).mean()
            ),
            "challenger_mae": float(
                (third["y"] - third["challenger"]).abs().mean()
            ),
            "bias_by_year": third_by_year,
        },
        "by_year": by_year,
    }


def verdict(primary: dict, compatibility: dict) -> dict:
    p_base = primary["top_tail_baseline_bias_y_minus_pred"]
    p_challenger = primary["top_tail_challenger_bias_y_minus_pred"]
    conditions = {
        "primary_mae_improves_at_least_0.25": (
            primary["delta_mae_challenger_minus_baseline"] <= -0.25
        ),
        "primary_rho_improves_at_least_0.005": (
            primary["delta_rho_challenger_minus_baseline"] >= 0.005
        ),
        "primary_both_better_in_at_least_2_of_3": (
            primary["both_metrics_better_folds"] >= 2
        ),
        "primary_cluster_ci_lower_above_zero": (
            primary["player_clustered_95pct_ci"][0] > 0
        ),
        "primary_top_underprojection_reduced": (
            abs(p_challenger) < abs(p_base)
        ),
        "primary_non_top_mae_worsens_no_more_than_0.25": (
            primary["non_top_delta_mae_challenger_minus_baseline"] <= 0.25
        ),
        "compatibility_pooled_mae_not_worse": (
            compatibility["delta_mae_challenger_minus_baseline"] <= 0
        ),
        "compatibility_pooled_rho_not_lower": (
            compatibility["delta_rho_challenger_minus_baseline"] >= 0
        ),
        "compatibility_both_better_in_at_least_3_of_5": (
            compatibility["both_metrics_better_folds"] >= 3
        ),
    }
    return {
        "conditions": conditions,
        "verdict": "DEVELOPMENTAL CANDIDATE"
        if all(conditions.values())
        else "REJECT",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--fire", action="store_true")
    args = parser.parse_args()

    before = artifact_state()
    assert_protected(before)
    panel = add_cross_season_role(load_panel())
    structure = structural_check(panel)
    output = {"mode": "check" if args.check else "fire", "structure": structure}

    if args.fire:
        panel = panel.merge(
            load_target(),
            on=["player_id", "season"],
            how="left",
            validate="one_to_one",
        )
        panel["y"] = panel["y"].fillna(0.0)
        primary = panel_report(walk_forward(panel, PRIMARY_YEARS))
        compatibility = panel_report(walk_forward(panel, COMPAT_YEARS))
        output.update(
            {
                "primary_2018_2020": primary,
                "compatibility_2021_2025": compatibility,
                "decision": verdict(primary, compatibility),
            }
        )

    after = artifact_state()
    assert after == before, "Protected model or result artifact changed"
    output["protected_artifacts_unchanged"] = True
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
