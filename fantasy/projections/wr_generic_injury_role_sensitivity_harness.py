"""Read-only harness for PREREG_wr_generic_injury_role_sensitivity_2026-07-26.md."""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from wr_pearsall_sensitivity_harness import (
    BASE_FEATURES,
    PEARSALL_ID,
    PLAYERS,
    RESULTS,
    ROOT,
    STATS,
    artifact_state,
    assert_protected,
    load_panel,
    load_target,
    make_model,
)


SNAPS = (
    ROOT
    / "fantasy/seasonal_projections/snapshots/snap_counts_2013_2025.parquet"
)
NEUTRAL_POINTS = "prior_points_at_16_5"
ACTIVE_TARGET = "prior_active_target_share"
ACTIVE_AIR = "prior_active_air_yards_share"
TARGET_GAP = "prior_target_share_availability_gap"
AIR_GAP = "prior_air_yards_share_availability_gap"
ACTIVE_ROLE_FEATURES = [ACTIVE_TARGET, ACTIVE_AIR, TARGET_GAP, AIR_GAP]
TEAM_CANON = {
    "ARZ": "ARI",
    "AZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "SL": "LA",
    "STL": "LA",
    "SD": "LAC",
    "OAK": "LV",
}
VARIANT_FEATURES = {
    "baseline": BASE_FEATURES,
    "neutral_points": BASE_FEATURES + [NEUTRAL_POINTS],
    "active_role": BASE_FEATURES + ACTIVE_ROLE_FEATURES,
    "both": BASE_FEATURES + [NEUTRAL_POINTS] + ACTIVE_ROLE_FEATURES,
}


def active_week_shares() -> pd.DataFrame:
    stats = pd.read_parquet(
        STATS,
        columns=[
            "player_id",
            "season",
            "week",
            "season_type",
            "team",
            "targets",
            "receiving_air_yards",
        ],
    )
    stats = stats[
        stats["season_type"].eq("REG") & stats["season"].between(2013, 2025)
    ].copy()
    stats["targets"] = stats["targets"].fillna(0.0)
    stats["receiving_air_yards"] = stats["receiving_air_yards"].fillna(0.0)
    stats["team"] = stats["team"].replace(TEAM_CANON)

    team_game = (
        stats.groupby(["season", "week", "team"], as_index=False)
        .agg(
            team_targets=("targets", "sum"),
            team_air_yards=("receiving_air_yards", "sum"),
        )
    )
    player_game = (
        stats.groupby(["player_id", "season", "week"], as_index=False)
        .agg(
            player_targets=("targets", "sum"),
            player_air_yards=("receiving_air_yards", "sum"),
        )
    )

    snaps = pd.read_parquet(
        SNAPS,
        columns=[
            "season",
            "week",
            "game_type",
            "pfr_player_id",
            "position",
            "team",
            "offense_snaps",
        ],
    )
    snaps = snaps[
        snaps["game_type"].eq("REG")
        & snaps["season"].between(2013, 2025)
        & snaps["position"].eq("WR")
        & snaps["offense_snaps"].fillna(0.0).gt(0.0)
        & snaps["pfr_player_id"].notna()
    ].copy()
    snaps["team"] = snaps["team"].replace(TEAM_CANON)
    active = (
        snaps.groupby(
            ["pfr_player_id", "season", "week", "team"], as_index=False
        )["offense_snaps"]
        .sum()
    )

    players = pd.read_parquet(PLAYERS, columns=["pfr_id", "gsis_id"])
    crosswalk = players.dropna().drop_duplicates("pfr_id", keep=False)
    assert not crosswalk["pfr_id"].duplicated().any()
    active = active.merge(
        crosswalk,
        left_on="pfr_player_id",
        right_on="pfr_id",
        how="inner",
        validate="many_to_one",
    )
    active = active.merge(
        player_game,
        left_on=["gsis_id", "season", "week"],
        right_on=["player_id", "season", "week"],
        how="left",
        validate="one_to_one",
    )
    active[["player_targets", "player_air_yards"]] = active[
        ["player_targets", "player_air_yards"]
    ].fillna(0.0)
    active = active.merge(
        team_game,
        on=["season", "week", "team"],
        how="left",
        validate="many_to_one",
    )
    assert active["team_targets"].gt(0).all()

    season = (
        active.groupby(["gsis_id", "season"], as_index=False)
        .agg(
            player_targets=("player_targets", "sum"),
            player_air_yards=("player_air_yards", "sum"),
            team_targets=("team_targets", "sum"),
            team_air_yards=("team_air_yards", "sum"),
            active_games=("week", "nunique"),
        )
        .rename(columns={"gsis_id": "player_id"})
    )
    season[ACTIVE_TARGET] = season["player_targets"] / season["team_targets"]
    season[ACTIVE_AIR] = season["player_air_yards"] / season[
        "team_air_yards"
    ].replace(0.0, np.nan)
    season["season"] += 1
    return season[
        ["player_id", "season", ACTIVE_TARGET, ACTIVE_AIR, "active_games"]
    ]


def build_panel() -> pd.DataFrame:
    panel = load_panel().merge(
        load_target(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    observed = panel["season"].le(2025)
    panel.loc[observed, "y"] = panel.loc[observed, "y"].fillna(0.0)
    panel = panel.merge(
        active_week_shares(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    panel[NEUTRAL_POINTS] = panel["prior_ppg"] * 16.5
    panel[TARGET_GAP] = panel[ACTIVE_TARGET] - panel["prior_target_share"]
    panel[AIR_GAP] = panel[ACTIVE_AIR] - panel["prior_air_yards_share"]
    return panel


def structural_report(panel: pd.DataFrame) -> dict:
    assert len(BASE_FEATURES) == 32
    assert set(VARIANT_FEATURES) == {
        "baseline",
        "neutral_points",
        "active_role",
        "both",
    }
    assert not panel.duplicated(["player_id", "season"]).any()
    pearsall = panel[
        panel["season"].eq(2026) & panel["player_id"].eq(PEARSALL_ID)
    ]
    assert len(pearsall) == 1

    train = panel[panel["season"].between(2014, 2025)]
    coverage = {
        feature: float(train[feature].notna().mean())
        for feature in [NEUTRAL_POINTS] + ACTIVE_ROLE_FEATURES
    }
    assert all(value > 0.85 for value in coverage.values())

    row = pearsall.iloc[0]
    assert 0.18 < row[ACTIVE_TARGET] < 0.19
    return {
        "baseline_feature_count": len(BASE_FEATURES),
        "variant_feature_counts": {
            variant: len(features)
            for variant, features in VARIANT_FEATURES.items()
        },
        "train_feature_coverage": coverage,
        "pearsall_inputs": {
            "prior_points_at_16_5": float(row[NEUTRAL_POINTS]),
            "prior_active_target_share": float(row[ACTIVE_TARGET]),
            "prior_active_air_yards_share": float(row[ACTIVE_AIR]),
            "prior_target_share_availability_gap": float(row[TARGET_GAP]),
            "prior_air_yards_share_availability_gap": float(row[AIR_GAP]),
            "active_games": int(row["active_games"]),
        },
        "market_columns_loaded": [],
        "other_player_predictions_computed": 0,
    }


def score_pearsall(panel: pd.DataFrame) -> dict:
    train = panel[panel["season"].le(2025)].dropna(subset=["y"])
    pearsall = panel[
        panel["season"].eq(2026) & panel["player_id"].eq(PEARSALL_ID)
    ]
    assert len(pearsall) == 1

    projections = {}
    new_feature_split_counts = {}
    for variant, features in VARIANT_FEATURES.items():
        model = make_model()
        model.fit(train[features], train["y"])
        projections[variant] = float(
            np.clip(model.predict(pearsall[features])[0], 0.0, None)
        )
        new_feature_split_counts[variant] = {
            feature: int(
                model.booster_.feature_importance(importance_type="split")[
                    features.index(feature)
                ]
            )
            for feature in [NEUTRAL_POINTS] + ACTIVE_ROLE_FEATURES
            if feature in features
        }
    shipped = pd.read_csv(RESULTS / "wr_projection_2026.csv")
    shipped = shipped[shipped["player_id"].eq(PEARSALL_ID)]
    assert len(shipped) == 1
    return {
        "shipped_context": float(shipped.iloc[0]["projection"]),
        "projections": projections,
        "new_feature_split_counts": new_feature_split_counts,
        "other_player_predictions_computed": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--score", action="store_true")
    args = parser.parse_args()

    before = artifact_state()
    assert_protected(before)
    panel = build_panel()
    output = {
        "mode": "check" if args.check else "score",
        "structure": structural_report(panel),
    }
    if args.score:
        output["pearsall_2026"] = score_pearsall(panel)
    after = artifact_state()
    assert before == after
    assert_protected(after)
    output["protected_artifacts_unchanged"] = True
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
