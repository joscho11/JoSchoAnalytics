"""Read-only harness for PREREG_wr_depth_signal_falsification_2026-07-26.md."""

from __future__ import annotations

import argparse
import json

import nflreadpy as nfl
import numpy as np
import pandas as pd

import wr_pearsall_sensitivity_harness as base


LISTED_FEATURE = "depth_listed"
ALIGNED_FEATURE = "depth_tier_aligned"
VARIANTS = {
    "baseline": base.BASE_FEATURES,
    "listed": base.BASE_FEATURES + [LISTED_FEATURE],
    "tier_fired": base.BASE_FEATURES + [base.DEPTH_FEATURE],
    "tier_aligned": base.BASE_FEATURES + [ALIGNED_FEATURE],
}


def prepare_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = base.load_panel().merge(
        base.load_target(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    historical = panel["season"].le(2025)
    panel.loc[historical, "y"] = panel.loc[historical, "y"].fillna(0.0)
    depth, audit = base.load_depth_features()
    panel = base.add_depth_feature(panel, depth)
    panel[ALIGNED_FEATURE] = panel[base.DEPTH_FEATURE].where(
        panel[base.DEPTH_FEATURE].le(2)
    )
    panel[LISTED_FEATURE] = panel[ALIGNED_FEATURE].notna().astype(int)
    return panel, audit


def predict_full_panel(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in base.TEST_YEARS:
        train = panel[panel["season"].lt(year)]
        test = panel[panel["season"].eq(year)].copy()
        for variant, features in VARIANTS.items():
            model = base.make_model()
            model.fit(train[features], train["y"])
            test[variant] = np.clip(
                model.predict(test[features]), 0.0, None
            )
        rows.append(test)
    return pd.concat(rows, ignore_index=True)


def predict_complete_cases(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in base.TEST_YEARS:
        train = panel[
            panel["season"].lt(year) & panel[ALIGNED_FEATURE].notna()
        ]
        test = panel[
            panel["season"].eq(year) & panel[ALIGNED_FEATURE].notna()
        ].copy()
        baseline = base.make_model()
        tier = base.make_model()
        baseline.fit(train[base.BASE_FEATURES], train["y"])
        tier.fit(
            train[base.BASE_FEATURES + [ALIGNED_FEATURE]],
            train["y"],
        )
        test["complete_baseline"] = np.clip(
            baseline.predict(test[base.BASE_FEATURES]), 0.0, None
        )
        test["complete_tier"] = np.clip(
            tier.predict(test[base.BASE_FEATURES + [ALIGNED_FEATURE]]),
            0.0,
            None,
        )
        rows.append(test)
    return pd.concat(rows, ignore_index=True)


def metric(frame: pd.DataFrame, prediction: str) -> dict:
    error = frame["y"] - frame[prediction]
    return {
        "n": len(frame),
        "mae": float(error.abs().mean()),
        "rho": base.rho(frame, prediction),
        "bias_y_minus_prediction": float(error.mean()),
    }


def by_year_metrics(
    frame: pd.DataFrame, predictions: list[str]
) -> dict:
    return {
        str(int(year)): {
            prediction: metric(rows, prediction)
            for prediction in predictions
        }
        for year, rows in frame.groupby("season")
    }


def full_panel_report(frame: pd.DataFrame) -> dict:
    pooled = {
        variant: metric(frame, variant)
        for variant in VARIANTS
    }
    by_year = by_year_metrics(frame, list(VARIANTS))
    baseline_mae = pooled["baseline"]["mae"]
    fired_gain = baseline_mae - pooled["tier_fired"]["mae"]
    listed_gain = baseline_mae - pooled["listed"]["mae"]
    assert fired_gain > 0
    presence_recovery = listed_gain / fired_gain

    reproduction = {
        "baseline_mae": abs(baseline_mae - 31.070501613280012) < 1e-9,
        "baseline_rho": (
            abs(pooled["baseline"]["rho"] - 0.7534097624961813) < 1e-9
        ),
        "depth_mae": (
            abs(pooled["tier_fired"]["mae"] - 29.053002665868398) < 1e-9
        ),
        "depth_rho": (
            abs(pooled["tier_fired"]["rho"] - 0.8052332086149587) < 1e-9
        ),
    }
    assert all(reproduction.values()), (reproduction, pooled)
    return {
        "pooled": pooled,
        "by_year": by_year,
        "fired_depth_mae_gain": float(fired_gain),
        "listed_mae_gain": float(listed_gain),
        "presence_recovery_fraction": float(presence_recovery),
        "predominantly_presence": bool(presence_recovery >= 0.75),
        "fired_result_reproduced_exactly": reproduction,
    }


def complete_case_report(frame: pd.DataFrame) -> dict:
    predictions = ["complete_baseline", "complete_tier"]
    pooled = {prediction: metric(frame, prediction) for prediction in predictions}
    by_year = by_year_metrics(frame, predictions)
    delta_mae = (
        pooled["complete_tier"]["mae"]
        - pooled["complete_baseline"]["mae"]
    )
    delta_rho = (
        pooled["complete_tier"]["rho"]
        - pooled["complete_baseline"]["rho"]
    )
    mae_wins = sum(
        by_year[str(year)]["complete_tier"]["mae"]
        < by_year[str(year)]["complete_baseline"]["mae"]
        for year in base.TEST_YEARS
    )
    conditions = {
        "mae_improves_at_least_0.25": delta_mae <= -0.25,
        "rho_does_not_decline": delta_rho >= 0,
        "mae_improves_in_at_least_3_of_5": mae_wins >= 3,
    }
    tiers = {}
    for tier, rows in frame.groupby(ALIGNED_FEATURE):
        residual = rows["y"] - rows["complete_baseline"]
        tiers[str(int(tier))] = {
            "n": len(rows),
            "actual_mean": float(rows["y"].mean()),
            "actual_median": float(rows["y"].median()),
            "zero_outcome_rate": float(rows["y"].eq(0).mean()),
            "baseline_bias_y_minus_prediction": float(residual.mean()),
            "baseline_mae": float(residual.abs().mean()),
        }
    return {
        "pooled": pooled,
        "by_year": by_year,
        "delta_mae_tier_minus_baseline": float(delta_mae),
        "delta_rho_tier_minus_baseline": float(delta_rho),
        "mae_winning_folds": mae_wins,
        "conditions": conditions,
        "tier_ordering_has_incremental_evidence": all(conditions.values()),
        "outcomes_by_tier": tiers,
    }


def new_schema_snapshot(
    depth: pd.DataFrame, latest: bool
) -> pd.DataFrame:
    selector = "max" if latest else "min"
    timestamp = depth.groupby("team", as_index=False)["dt"].agg(selector)
    snapshot = depth.merge(
        timestamp,
        on=["team", "dt"],
        how="inner",
        validate="many_to_one",
    )
    snapshot = snapshot.sort_values(
        ["team", "pos_slot", "pos_rank", "player_name"]
    )
    snapshot[ALIGNED_FEATURE] = (
        snapshot.groupby(["team", "pos_slot"]).cumcount() + 1
    ).astype(float)
    return (
        snapshot[snapshot[ALIGNED_FEATURE].le(2)]
        .sort_values(["gsis_id", ALIGNED_FEATURE])
        .drop_duplicates("gsis_id")
        [["gsis_id", ALIGNED_FEATURE]]
        .rename(columns={"gsis_id": "player_id"})
    )


def timing_report(panel: pd.DataFrame) -> dict:
    schedules = pd.read_parquet(
        base.SCHEDULES, columns=["season", "game_type", "gameday"]
    )
    opener = pd.to_datetime(
        schedules[
            schedules["season"].eq(2025)
            & schedules["game_type"].eq("REG")
        ]["gameday"].min(),
        utc=True,
    )
    depth = nfl.load_depth_charts(seasons=[2025]).to_pandas()
    depth["dt"] = pd.to_datetime(depth["dt"], utc=True)
    depth = depth[
        depth["dt"].lt(opener)
        & depth["pos_abb"].eq("WR")
        & depth["gsis_id"].notna()
        & depth["pos_slot"].notna()
        & depth["pos_rank"].notna()
    ].copy()
    early = new_schema_snapshot(depth, latest=False).rename(
        columns={ALIGNED_FEATURE: "early_tier"}
    )
    late = new_schema_snapshot(depth, latest=True).rename(
        columns={ALIGNED_FEATURE: "late_tier"}
    )
    eligible = set(
        panel.loc[panel["season"].eq(2025), "player_id"].dropna()
    )
    early = early[early["player_id"].isin(eligible)]
    late = late[late["player_id"].isin(eligible)]
    comparison = early.merge(
        late,
        on="player_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    common = comparison[comparison["_merge"].eq("both")]
    retained = len(common) / len(early) if len(early) else np.nan
    exact = (
        common["early_tier"].eq(common["late_tier"]).mean()
        if len(common)
        else np.nan
    )
    conditions = {
        "at_least_80pct_early_listed_retained": retained >= 0.80,
        "at_least_80pct_exact_tier_agreement": exact >= 0.80,
    }
    return {
        "feed_first_timestamp": str(depth["dt"].min()),
        "feed_last_preopener_timestamp": str(depth["dt"].max()),
        "early_listed_n": len(early),
        "late_listed_n": len(late),
        "common_n": len(common),
        "early_listed_retained_rate": float(retained),
        "exact_tier_agreement_common": float(exact),
        "early_only_n": int(comparison["_merge"].eq("left_only").sum()),
        "late_only_n": int(comparison["_merge"].eq("right_only").sum()),
        "conditions": conditions,
        "timing_evidence_adequate": all(conditions.values()),
        "limitation": "The dated feed begins in August and cannot validate July stability.",
    }


def decision(
    full: dict, complete: dict, timing: dict
) -> dict:
    conditions = {
        "presence_recovers_less_than_75pct": (
            not full["predominantly_presence"]
        ),
        "complete_case_tier_test_passes": (
            complete["tier_ordering_has_incremental_evidence"]
        ),
        "timing_test_passes": timing["timing_evidence_adequate"],
    }
    return {
        "conditions": conditions,
        "ordinal_depth_remains_candidate": all(conditions.values()),
        "verdict": (
            "ORDINAL DEPTH REMAINS DEVELOPMENTAL CANDIDATE"
            if all(conditions.values())
            else "REJECT ORDINAL DEPTH FOR JULY MODEL"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--fire", action="store_true")
    args = parser.parse_args()

    before = base.artifact_state()
    base.assert_protected(before)
    panel, audit = prepare_panel()
    structure = {
        "baseline_feature_count": len(base.BASE_FEATURES),
        "market_columns_loaded": [],
        "test_years": base.TEST_YEARS,
        "aligned_depth_coverage": {
            str(int(year)): float(rows[ALIGNED_FEATURE].notna().mean())
            for year, rows in panel.groupby("season")
        },
        "sf_2026_audit": audit.to_dict(orient="records"),
    }
    output = {
        "mode": "check" if args.check else "fire",
        "structure": structure,
    }
    if args.fire:
        full = full_panel_report(predict_full_panel(panel))
        complete = complete_case_report(predict_complete_cases(panel))
        timing = timing_report(panel)
        output.update(
            {
                "full_panel": full,
                "complete_cases": complete,
                "timing_2025": timing,
                "decision": decision(full, complete, timing),
            }
        )

    after = base.artifact_state()
    assert after == before, "Protected model or result artifact changed"
    output["protected_artifacts_unchanged"] = True
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
