"""Read-only harness for PREREG_wr_generic_ppg_total_sensitivity_2026-07-26.md."""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from wr_pearsall_sensitivity_harness import (
    BASE_FEATURES,
    DATA,
    PEARSALL_ID,
    RESULTS,
    artifact_state,
    assert_protected,
    load_panel,
    load_target,
    make_model,
)


GAMES_MULTIPLIER = 16.5


def build_panel() -> pd.DataFrame:
    panel = load_panel().merge(
        load_target(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    observed = panel["season"].le(2025)
    panel.loc[observed, "y"] = panel.loc[observed, "y"].fillna(0.0)

    labels = pd.read_csv(
        DATA,
        usecols=[
            "player_id",
            "season",
            "position",
            "is_rookie",
            "target_ppg",
            "target_games",
        ],
        low_memory=False,
    )
    labels = labels[
        labels["position"].eq("WR") & labels["is_rookie"].eq(0)
    ][["player_id", "season", "target_ppg", "target_games"]]
    panel = panel.merge(
        labels,
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    return panel


def structural_report(panel: pd.DataFrame) -> dict:
    assert len(BASE_FEATURES) == 32
    assert not panel.duplicated(["player_id", "season"]).any()
    pearsall = panel[
        panel["season"].eq(2026) & panel["player_id"].eq(PEARSALL_ID)
    ]
    assert len(pearsall) == 1
    ppg_train = panel[
        panel["season"].le(2025)
        & panel["target_games"].gt(0)
        & panel["target_ppg"].notna()
    ]
    assert len(ppg_train) > 1_500
    assert ppg_train["target_games"].between(1, 18).all()
    return {
        "feature_count": len(BASE_FEATURES),
        "total_training_rows": int(
            panel[panel["season"].le(2025)]["y"].notna().sum()
        ),
        "ppg_training_rows": len(ppg_train),
        "ppg_training_weight_range": [
            float(ppg_train["target_games"].min()),
            float(ppg_train["target_games"].max()),
        ],
        "games_multiplier": GAMES_MULTIPLIER,
        "market_columns_loaded": [],
        "other_player_predictions_computed": 0,
    }


def score_pearsall(panel: pd.DataFrame) -> dict:
    total_train = panel[panel["season"].le(2025)].dropna(subset=["y"])
    ppg_train = panel[
        panel["season"].le(2025)
        & panel["target_games"].gt(0)
        & panel["target_ppg"].notna()
    ]
    pearsall = panel[
        panel["season"].eq(2026) & panel["player_id"].eq(PEARSALL_ID)
    ]
    assert len(pearsall) == 1

    total_model = make_model()
    total_model.fit(total_train[BASE_FEATURES], total_train["y"])
    total_baseline = float(
        np.clip(total_model.predict(pearsall[BASE_FEATURES])[0], 0.0, None)
    )

    projections = {}
    for name, sample_weight in (
        ("ppg_unweighted", None),
        ("ppg_games_weighted", ppg_train["target_games"]),
    ):
        model = make_model()
        model.fit(
            ppg_train[BASE_FEATURES],
            ppg_train["target_ppg"],
            sample_weight=sample_weight,
        )
        ppg = float(
            np.clip(model.predict(pearsall[BASE_FEATURES])[0], 0.0, None)
        )
        projections[name] = {
            "projected_ppg": ppg,
            "projected_total_at_16_5": ppg * GAMES_MULTIPLIER,
        }

    shipped = pd.read_csv(RESULTS / "wr_projection_2026.csv")
    shipped = shipped[shipped["player_id"].eq(PEARSALL_ID)]
    assert len(shipped) == 1
    return {
        "shipped_context": float(shipped.iloc[0]["projection"]),
        "corrected_total_baseline": total_baseline,
        "ppg_variants": projections,
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
