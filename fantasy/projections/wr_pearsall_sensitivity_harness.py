"""Read-only harness for PREREG_wr_pearsall_sensitivity_2026-07-26.md."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import nflreadpy as nfl
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
PLAYERS = ROOT / "fantasy/seasonal_projections/snapshots/players.parquet"
SCHEDULES = ROOT / "fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet"
PFF = ROOT / "fantasy/seasonal_projections/pff"
MODELS = ROOT / "fantasy/projections/models"
RESULTS = ROOT / "fantasy/projections/results"
SHIPPED_WR = RESULTS / "wr_projection_2026.csv"

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
COLLEGE_FEATURE = "college_talent_decay"
DEPTH_FEATURE = "preseason_depth_tier"
COLLEGE_WEIGHTS = {
    "grades_pass_route": 0.400,
    "yprr": 0.250,
    "contested": 0.100,
    "rec_avt": 0.100,
    "grades_hands_drop": 0.075,
    "yac_per_rec": 0.075,
}
VARIANT_FEATURES = {
    "baseline": BASE_FEATURES,
    "college": BASE_FEATURES + [COLLEGE_FEATURE],
    "depth": BASE_FEATURES + [DEPTH_FEATURE],
    "both": BASE_FEATURES + [COLLEGE_FEATURE, DEPTH_FEATURE],
}
TEST_YEARS = [2021, 2022, 2023, 2024, 2025]
PEARSALL_ID = "00-0039916"


def file_hash(path: Path, algorithm: str = "md5") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_state() -> dict:
    return {
        "models": {name: file_hash(MODELS / name) for name in PROTECTED_MODELS},
        "results": {
            path.name: file_hash(path, "sha256")
            for path in sorted(RESULTS.glob("*.csv"))
        },
    }


def assert_protected(state: dict) -> None:
    assert state["models"] == PROTECTED_MODELS, (
        state["models"],
        PROTECTED_MODELS,
    )


def load_panel() -> pd.DataFrame:
    columns = list(
        dict.fromkeys(
            [
                "player_id",
                "player",
                "position",
                "season",
                "is_rookie",
            ]
            + BASE_FEATURES
        )
    )
    panel = pd.read_csv(DATA, usecols=columns, low_memory=False)
    panel = panel[
        panel["position"].eq("WR")
        & panel["is_rookie"].eq(0)
        & panel["season"].between(2014, 2026)
    ].copy()
    assert len(BASE_FEATURES) == 32
    assert not panel.duplicated(["player_id", "season"]).any()
    return panel


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


def load_pff_receiving() -> pd.DataFrame:
    frames = []
    required = [
        "player_id",
        "position",
        "targets",
        "routes",
        "receptions",
        "avoided_tackles",
        "grades_pass_route",
        "yprr",
        "contested_catch_rate",
        "grades_hands_drop",
        "yards_after_catch_per_reception",
    ]
    for year in range(2014, 2026):
        path = PFF / f"college_{year}" / f"college_receiving_summary_{year}.csv"
        if not path.exists():
            path = PFF / f"college_{year}" / "receiving_summary.csv"
        frame = pd.read_csv(path, usecols=required, low_memory=False)
        frame["final_year"] = year
        frames.append(frame)
    receiving = pd.concat(frames, ignore_index=True)
    receiving = receiving[receiving["position"].eq("WR")].copy()
    numeric = [column for column in required if column not in {"position"}]
    receiving[numeric] = receiving[numeric].apply(pd.to_numeric, errors="coerce")
    return receiving


def weighted_player_mean(
    frame: pd.DataFrame, value: str, weight: str
) -> pd.Series:
    valid = frame[value].notna() & frame[weight].gt(0)
    work = frame.loc[valid, ["player_id", value, weight]].copy()
    work["_weighted"] = work[value] * work[weight]
    grouped = work.groupby("player_id")
    return grouped["_weighted"].sum() / grouped[weight].sum()


def build_college_facets() -> pd.DataFrame:
    receiving = load_pff_receiving()
    grouped = receiving.groupby("player_id")
    facets = pd.DataFrame(
        {
            "final_year": grouped["final_year"].max(),
            "career_targets": grouped["targets"].sum(),
        }
    )
    facets["grades_pass_route"] = weighted_player_mean(
        receiving, "grades_pass_route", "routes"
    )
    facets["yprr"] = weighted_player_mean(receiving, "yprr", "routes")
    facets["contested"] = weighted_player_mean(
        receiving, "contested_catch_rate", "routes"
    )
    facets["grades_hands_drop"] = weighted_player_mean(
        receiving, "grades_hands_drop", "routes"
    )
    facets["yac_per_rec"] = weighted_player_mean(
        receiving, "yards_after_catch_per_reception", "routes"
    )
    rate = grouped[["avoided_tackles", "receptions"]].sum(min_count=1)
    facets["rec_avt"] = rate["avoided_tackles"] / rate["receptions"].replace(0, np.nan)
    facets = facets[facets["career_targets"].ge(30)].reset_index()

    crosswalk = pd.read_parquet(PLAYERS, columns=["gsis_id", "pff_id"])
    crosswalk = crosswalk.dropna(subset=["gsis_id", "pff_id"]).copy()
    crosswalk["player_id"] = pd.to_numeric(
        crosswalk["pff_id"], errors="coerce"
    ).astype("Int64")
    crosswalk = crosswalk.dropna(subset=["player_id"])
    ambiguity = crosswalk.groupby("player_id")["gsis_id"].nunique()
    assert not ambiguity.gt(1).any(), "PFF ID maps to multiple GSIS IDs"
    crosswalk = crosswalk.drop_duplicates("player_id")
    facets = facets.merge(
        crosswalk[["player_id", "gsis_id"]],
        on="player_id",
        how="inner",
        validate="one_to_one",
    )
    facets = facets.sort_values(
        ["gsis_id", "career_targets"], ascending=[True, False]
    ).drop_duplicates("gsis_id")
    return facets


def college_scores(facets: pd.DataFrame, cutoff: int) -> pd.DataFrame:
    reference = facets[facets["final_year"].lt(cutoff)]
    scores = pd.Series(0.0, index=facets.index)
    present_weight = pd.Series(0.0, index=facets.index)
    for feature, weight in COLLEGE_WEIGHTS.items():
        mean = reference[feature].mean()
        std = reference[feature].std(ddof=1)
        assert np.isfinite(std) and std > 0
        zscore = (facets[feature] - mean) / std
        present = zscore.notna()
        scores = scores.add(weight * zscore.fillna(0.0))
        present_weight = present_weight.add(weight * present.astype(float))
    scores = scores.div(present_weight.replace(0.0, np.nan))
    scores[facets["final_year"].ge(cutoff)] = np.nan
    return pd.DataFrame(
        {
            "player_id": facets["gsis_id"],
            "college_talent_index": scores,
            "college_final_year": facets["final_year"],
        }
    )


def add_college_feature(
    panel: pd.DataFrame, facets: pd.DataFrame, cutoff: int
) -> pd.DataFrame:
    scores = college_scores(facets, cutoff)
    out = panel.drop(
        columns=[COLLEGE_FEATURE, "college_talent_index", "college_final_year"],
        errors="ignore",
    ).merge(scores, on="player_id", how="left", validate="many_to_one")
    active = out["years_exp"].between(0, 2)
    decay = np.power(0.5, out["years_exp"])
    out[COLLEGE_FEATURE] = 0.0
    out.loc[active, COLLEGE_FEATURE] = (
        out.loc[active, "college_talent_index"] * decay[active]
    )
    return out


def old_depth_season(season: int) -> pd.DataFrame:
    depth = nfl.load_depth_charts(seasons=[season]).to_pandas()
    depth = depth[
        depth["game_type"].eq("REG")
        & depth["week"].eq(1)
        & depth["formation"].eq("Offense")
        & depth["position"].eq("WR")
        & depth["depth_position"].eq("WR")
        & depth["gsis_id"].notna()
    ].copy()
    depth[DEPTH_FEATURE] = pd.to_numeric(depth["depth_team"], errors="coerce")
    depth["season"] = season
    return (
        depth.groupby(["gsis_id", "season"], as_index=False)[DEPTH_FEATURE]
        .min()
        .rename(columns={"gsis_id": "player_id"})
    )


def new_depth_season(
    season: int, regular_season_start: pd.Timestamp | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    depth = nfl.load_depth_charts(seasons=[season]).to_pandas()
    depth["dt"] = pd.to_datetime(depth["dt"], utc=True)
    if regular_season_start is not None:
        depth = depth[depth["dt"].lt(regular_season_start)]
    depth = depth[
        depth["pos_abb"].eq("WR")
        & depth["gsis_id"].notna()
        & depth["pos_slot"].notna()
        & depth["pos_rank"].notna()
    ].copy()
    latest = depth.groupby("team", as_index=False)["dt"].max()
    depth = depth.merge(latest, on=["team", "dt"], how="inner", validate="many_to_one")
    depth = depth.sort_values(["team", "pos_slot", "pos_rank", "player_name"])
    depth[DEPTH_FEATURE] = (
        depth.groupby(["team", "pos_slot"]).cumcount() + 1
    ).astype(float)
    depth["season"] = season
    feature = (
        depth[depth[DEPTH_FEATURE].le(2)]
        .sort_values(["gsis_id", DEPTH_FEATURE])
        .drop_duplicates("gsis_id")
        [["gsis_id", "season", DEPTH_FEATURE]]
        .rename(columns={"gsis_id": "player_id"})
    )
    audit = depth[
        depth["team"].eq("SF")
        & depth["player_name"].isin(
            ["Mike Evans", "Ricky Pearsall", "Christian Kirk", "De'Zhaun Stribling"]
        )
    ][
        [
            "dt",
            "player_name",
            "gsis_id",
            "pos_slot",
            "pos_rank",
            DEPTH_FEATURE,
        ]
    ].copy()
    return feature, audit


def load_depth_features() -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = [old_depth_season(season) for season in range(2014, 2025)]
    schedules = pd.read_parquet(
        SCHEDULES, columns=["season", "game_type", "gameday"]
    )
    opener_2025 = pd.to_datetime(
        schedules[
            schedules["season"].eq(2025) & schedules["game_type"].eq("REG")
        ]["gameday"].min(),
        utc=True,
    )
    depth_2025, _ = new_depth_season(2025, opener_2025)
    depth_2026, audit_2026 = new_depth_season(2026, None)
    frames.extend([depth_2025, depth_2026])
    depth = pd.concat(frames, ignore_index=True)
    assert not depth.duplicated(["player_id", "season"]).any()
    return depth, audit_2026


def add_depth_feature(panel: pd.DataFrame, depth: pd.DataFrame) -> pd.DataFrame:
    return panel.drop(columns=[DEPTH_FEATURE], errors="ignore").merge(
        depth,
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )


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


def prepare_fold(
    panel: pd.DataFrame,
    facets: pd.DataFrame,
    depth: pd.DataFrame,
    cutoff: int,
) -> pd.DataFrame:
    return add_depth_feature(
        add_college_feature(panel, facets, cutoff),
        depth,
    )


def walk_forward(
    panel: pd.DataFrame, facets: pd.DataFrame, depth: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for year in TEST_YEARS:
        fold = prepare_fold(panel, facets, depth, year)
        train = fold[fold["season"].lt(year)]
        test = fold[fold["season"].eq(year)].copy()
        assert train["season"].max() < year
        for variant, features in VARIANT_FEATURES.items():
            model = make_model()
            model.fit(train[features], train["y"])
            test[variant] = np.clip(model.predict(test[features]), 0.0, None)
        rows.append(test)
    return pd.concat(rows, ignore_index=True)


def rho(frame: pd.DataFrame, prediction: str) -> float:
    return float(spearmanr(frame["y"], frame[prediction]).statistic)


def metric_block(frame: pd.DataFrame, prediction: str) -> dict:
    error = frame["y"] - frame[prediction]
    return {
        "n": len(frame),
        "mae": float(error.abs().mean()),
        "rho": rho(frame, prediction),
        "bias_y_minus_prediction": float(error.mean()),
    }


def historical_report(frame: pd.DataFrame) -> dict:
    report = {
        "pooled": {
            variant: metric_block(frame, variant)
            for variant in VARIANT_FEATURES
        },
        "by_year": {},
        "third_year": {
            variant: metric_block(frame[frame["years_exp"].eq(2)], variant)
            for variant in VARIANT_FEATURES
        },
        "comparisons": {},
    }
    for year, rows in frame.groupby("season"):
        report["by_year"][str(int(year))] = {
            variant: metric_block(rows, variant)
            for variant in VARIANT_FEATURES
        }
    baseline = report["pooled"]["baseline"]
    for variant in ("college", "depth", "both"):
        candidate = report["pooled"][variant]
        mae_wins = sum(
            report["by_year"][str(year)][variant]["mae"]
            < report["by_year"][str(year)]["baseline"]["mae"]
            for year in TEST_YEARS
        )
        conditions = {
            "pooled_mae_improves_at_least_0.25": (
                candidate["mae"] - baseline["mae"] <= -0.25
            ),
            "pooled_rho_does_not_decline": (
                candidate["rho"] - baseline["rho"] >= 0
            ),
            "mae_improves_in_at_least_3_of_5": mae_wins >= 3,
        }
        report["comparisons"][variant] = {
            "delta_mae_candidate_minus_baseline": (
                candidate["mae"] - baseline["mae"]
            ),
            "delta_rho_candidate_minus_baseline": (
                candidate["rho"] - baseline["rho"]
            ),
            "mae_winning_folds": mae_wins,
            "conditions": conditions,
            "historically_credible": all(conditions.values()),
        }
    return report


def shipped_pearsall() -> dict:
    result = pd.read_csv(SHIPPED_WR)
    row = result[
        result["player"].astype(str).str.contains("Ricky Pearsall", case=False)
    ]
    assert len(row) == 1, row
    return row.iloc[0].to_dict()


def score_pearsall(
    panel: pd.DataFrame, facets: pd.DataFrame, depth: pd.DataFrame
) -> dict:
    final = prepare_fold(panel, facets, depth, 2026)
    train = final[final["season"].le(2025)]
    pearsall = final[
        final["season"].eq(2026) & final["player_id"].eq(PEARSALL_ID)
    ].copy()
    assert len(pearsall) == 1
    official = {}
    tier_two = {}
    new_feature_importance = {}
    for variant, features in VARIANT_FEATURES.items():
        model = make_model()
        model.fit(train[features], train["y"])
        official[variant] = float(
            np.clip(model.predict(pearsall[features])[0], 0.0, None)
        )
        if DEPTH_FEATURE in features:
            scenario = pearsall.copy()
            scenario[DEPTH_FEATURE] = 2.0
            tier_two[variant] = float(
                np.clip(model.predict(scenario[features])[0], 0.0, None)
            )
        new_feature_importance[variant] = {
            feature: int(model.booster_.feature_importance(importance_type="split")[
                features.index(feature)
            ])
            for feature in (COLLEGE_FEATURE, DEPTH_FEATURE)
            if feature in features
        }
    row = pearsall.iloc[0]
    return {
        "shipped_context": shipped_pearsall(),
        "corrected_panel_refit": official,
        "depth_tier_2_counterfactual": tier_two,
        "inputs": {
            "player_id": row["player_id"],
            "years_exp": int(row["years_exp"]),
            "prior_games": float(row["prior_games"]),
            "prior_ppg": float(row["prior_ppg"]),
            "prior_half_ppr": float(row["prior_half_ppr"]),
            "college_talent_index": float(row["college_talent_index"]),
            "college_talent_decay": float(row[COLLEGE_FEATURE]),
            "college_final_year": int(row["college_final_year"]),
            "preseason_depth_tier": float(row[DEPTH_FEATURE]),
        },
        "new_feature_split_counts": new_feature_importance,
    }


def structural_report(
    panel: pd.DataFrame,
    facets: pd.DataFrame,
    depth: pd.DataFrame,
    audit_2026: pd.DataFrame,
) -> dict:
    prepared = prepare_fold(panel, facets, depth, 2026)
    pearsall = prepared[
        prepared["season"].eq(2026) & prepared["player_id"].eq(PEARSALL_ID)
    ]
    assert len(pearsall) == 1
    sf = audit_2026.sort_values("pos_rank")
    expected = {
        "Mike Evans": (1, 1.0),
        "Ricky Pearsall": (2, 1.0),
        "Christian Kirk": (3, 1.0),
        "De'Zhaun Stribling": (4, 2.0),
    }
    observed = {
        row.player_name: (int(row.pos_rank), float(row[DEPTH_FEATURE]))
        for _, row in sf.iterrows()
    }
    assert observed == expected, (observed, expected)
    depth_coverage = (
        prepared.assign(depth_present=prepared[DEPTH_FEATURE].notna())
        .groupby("season")["depth_present"]
        .mean()
    )
    historical_depth_coverage = depth_coverage.loc[2021:2025].mean()
    depth_coverage_shift = abs(
        depth_coverage.loc[2026] - historical_depth_coverage
    )
    assert depth_coverage_shift <= 0.10, depth_coverage_shift
    early = prepared["years_exp"].between(0, 2)
    college_coverage = (
        prepared[early]
        .assign(college_present=lambda x: x[COLLEGE_FEATURE].notna())
        .groupby("season")["college_present"]
        .mean()
    )
    return {
        "baseline_feature_count": len(BASE_FEATURES),
        "variant_feature_counts": {
            name: len(features) for name, features in VARIANT_FEATURES.items()
        },
        "market_columns_loaded": [],
        "pff_mapped_wr_count": len(facets),
        "depth_coverage_by_season": {
            str(int(year)): float(value)
            for year, value in depth_coverage.items()
        },
        "depth_coverage_shift_2026_vs_2021_2025": float(
            depth_coverage_shift
        ),
        "college_coverage_first_three_years_by_season": {
            str(int(year)): float(value)
            for year, value in college_coverage.items()
        },
        "sf_2026_depth_audit": sf.to_dict(orient="records"),
        "pearsall_has_college_feature": bool(
            pearsall[COLLEGE_FEATURE].notna().iloc[0]
        ),
        "pearsall_depth_tier": float(pearsall[DEPTH_FEATURE].iloc[0]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--fire", action="store_true")
    args = parser.parse_args()

    before = artifact_state()
    assert_protected(before)
    panel = load_panel().merge(
        load_target(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    panel.loc[panel["season"].le(2025), "y"] = panel.loc[
        panel["season"].le(2025), "y"
    ].fillna(0.0)
    facets = build_college_facets()
    depth, audit_2026 = load_depth_features()
    structure = structural_report(panel, facets, depth, audit_2026)
    output = {
        "mode": "check" if args.check else "fire",
        "structure": structure,
    }
    if args.fire:
        predictions = walk_forward(panel, facets, depth)
        output["historical_2021_2025"] = historical_report(predictions)
        output["pearsall_2026"] = score_pearsall(panel, facets, depth)

    after = artifact_state()
    assert after == before, "Protected model or result artifact changed"
    output["protected_artifacts_unchanged"] = True
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
