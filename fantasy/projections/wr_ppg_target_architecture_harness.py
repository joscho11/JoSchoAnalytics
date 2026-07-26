"""Read-only harness for PREREG_wr_ppg_target_architecture_2026-07-26.md."""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from wr_pearsall_sensitivity_harness import (
    BASE_FEATURES,
    DATA,
    RESULTS,
    artifact_state,
    assert_protected,
    load_panel,
    load_target,
    make_model,
)


TEST_YEARS = [2021, 2022, 2023, 2024, 2025]
GAMES_MULTIPLIER = 16.5
BOOTSTRAP_DRAWS = 2_000
SEED = 42
CASE_IDS = {
    "00-0039916": "Ricky Pearsall",
    "00-0039919": "Rome Odunze",
    "00-0040735": "Luther Burden III",
}


def build_panel() -> pd.DataFrame:
    panel = load_panel().merge(
        load_target(),
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    historical = panel["season"].le(2025)
    panel.loc[historical, "y"] = panel.loc[historical, "y"].fillna(0.0)

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
    assert not panel.duplicated(["player_id", "season"]).any()
    return panel


def ppg_training_rows(panel: pd.DataFrame, before_year: int) -> pd.DataFrame:
    return panel[
        panel["season"].lt(before_year)
        & panel["target_games"].gt(0)
        & panel["target_ppg"].notna()
    ]


def synthetic_metric_probe() -> dict:
    rng = np.random.default_rng(SEED)
    y = rng.normal(size=2_000)
    noise = rng.normal(size=2_000)
    signal = y + rng.normal(scale=0.35, size=2_000)
    peek = y.copy()
    noise_rho = float(spearmanr(y, noise).statistic)
    signal_rho = float(spearmanr(y, signal).statistic)
    peek_rho = float(spearmanr(y, peek).statistic)
    assert abs(noise_rho) < 0.08
    assert signal_rho > 0.80
    assert peek_rho > 0.999
    return {
        "noise_abs_rho_below_0_08": abs(noise_rho) < 0.08,
        "planted_signal_rho_above_0_80": signal_rho > 0.80,
        "future_peek_rho_above_0_999": peek_rho > 0.999,
    }


def structural_report(panel: pd.DataFrame) -> dict:
    assert len(BASE_FEATURES) == 32
    outer = panel[panel["season"].isin(TEST_YEARS)].copy()
    assert len(outer) == 1_006
    case_rows = panel[
        panel["season"].eq(2026) & panel["player_id"].isin(CASE_IDS)
    ]
    assert set(case_rows["player_id"]) == set(CASE_IDS)
    assert len(case_rows) == len(CASE_IDS)

    folds = {}
    for year in TEST_YEARS:
        direct_train = panel[
            panel["season"].lt(year) & panel["y"].notna()
        ]
        ppg_train = ppg_training_rows(panel, year)
        test = panel[panel["season"].eq(year) & panel["y"].notna()]
        assert direct_train["season"].max() < year
        assert ppg_train["season"].max() < year
        assert test["season"].eq(year).all()
        folds[str(year)] = {
            "direct_total_train_rows": len(direct_train),
            "ppg_train_rows": len(ppg_train),
            "identical_test_rows": len(test),
        }

    all_ppg_train = ppg_training_rows(panel, 2026)
    assert all_ppg_train["target_games"].between(1, 18).all()
    return {
        "feature_count_each_architecture": len(BASE_FEATURES),
        "feature_order_identical": True,
        "outer_test_rows": len(outer),
        "outer_unique_player_clusters": int(outer["player_id"].nunique()),
        "test_rows_by_year": {
            str(int(year)): int(count)
            for year, count in outer.groupby("season").size().items()
        },
        "fold_structure": folds,
        "full_ppg_training_rows": len(all_ppg_train),
        "ppg_training_weight_range": [
            float(all_ppg_train["target_games"].min()),
            float(all_ppg_train["target_games"].max()),
        ],
        "games_multiplier": GAMES_MULTIPLIER,
        "case_players": {
            player_id: CASE_IDS[player_id]
            for player_id in sorted(case_rows["player_id"])
        },
        "market_columns_loaded_for_fit_or_gate": [],
        "synthetic_metric_probe": synthetic_metric_probe(),
    }


def walk_forward(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in TEST_YEARS:
        direct_train = panel[
            panel["season"].lt(year) & panel["y"].notna()
        ]
        ppg_train = ppg_training_rows(panel, year)
        test = panel[
            panel["season"].eq(year) & panel["y"].notna()
        ].copy()
        assert direct_train["season"].max() < year
        assert ppg_train["season"].max() < year
        assert not test.duplicated(["player_id", "season"]).any()

        direct = make_model()
        direct.fit(direct_train[BASE_FEATURES], direct_train["y"])
        test["direct_total"] = np.clip(
            direct.predict(test[BASE_FEATURES]), 0.0, None
        )

        ppg = make_model()
        ppg.fit(
            ppg_train[BASE_FEATURES],
            ppg_train["target_ppg"],
            sample_weight=ppg_train["target_games"],
        )
        test["challenger_ppg"] = np.clip(
            ppg.predict(test[BASE_FEATURES]), 0.0, None
        )
        test["games_weighted_ppg_x_16_5"] = (
            test["challenger_ppg"] * GAMES_MULTIPLIER
        )
        rows.append(test)
    out = pd.concat(rows, ignore_index=True)
    assert len(out) == 1_006
    assert not out.duplicated(["player_id", "season"]).any()
    return out


def metric_block(frame: pd.DataFrame, prediction: str) -> dict:
    residual = frame["y"] - frame[prediction]
    return {
        "n": len(frame),
        "mae": float(residual.abs().mean()),
        "rmse": float(np.sqrt(np.mean(np.square(residual)))),
        "spearman": float(spearmanr(frame["y"], frame[prediction]).statistic),
        "bias_actual_minus_prediction": float(residual.mean()),
    }


def paired_cluster_bootstrap(frame: pd.DataFrame) -> dict:
    work = frame[["player_id", "y", "direct_total", "games_weighted_ppg_x_16_5"]].copy()
    work["absolute_error_delta"] = (
        (work["y"] - work["games_weighted_ppg_x_16_5"]).abs()
        - (work["y"] - work["direct_total"]).abs()
    )
    clusters = (
        work.groupby("player_id", as_index=False)
        .agg(delta_sum=("absolute_error_delta", "sum"), row_count=("y", "size"))
    )
    delta_sum = clusters["delta_sum"].to_numpy(float)
    row_count = clusters["row_count"].to_numpy(float)
    rng = np.random.default_rng(SEED)
    draws = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    n_clusters = len(clusters)
    for draw in range(BOOTSTRAP_DRAWS):
        sampled = rng.integers(0, n_clusters, size=n_clusters)
        draws[draw] = delta_sum[sampled].sum() / row_count[sampled].sum()
    low, high = np.quantile(draws, [0.025, 0.975])
    return {
        "clusters": n_clusters,
        "draws": BOOTSTRAP_DRAWS,
        "seed": SEED,
        "delta_definition": "challenger_mae_minus_incumbent_mae",
        "ci_95": [float(low), float(high)],
    }


def comparison_report(frame: pd.DataFrame) -> dict:
    incumbent_name = "direct_total"
    challenger_name = "games_weighted_ppg_x_16_5"
    pooled = {
        incumbent_name: metric_block(frame, incumbent_name),
        challenger_name: metric_block(frame, challenger_name),
    }
    by_year = {
        str(int(year)): {
            incumbent_name: metric_block(rows, incumbent_name),
            challenger_name: metric_block(rows, challenger_name),
        }
        for year, rows in frame.groupby("season")
    }
    incumbent = pooled[incumbent_name]
    challenger = pooled[challenger_name]
    delta_mae = challenger["mae"] - incumbent["mae"]
    delta_rmse = challenger["rmse"] - incumbent["rmse"]
    delta_spearman = challenger["spearman"] - incumbent["spearman"]
    absolute_bias_worsening = (
        abs(challenger["bias_actual_minus_prediction"])
        - abs(incumbent["bias_actual_minus_prediction"])
    )
    winning_years = [
        year
        for year in map(str, TEST_YEARS)
        if by_year[year][challenger_name]["mae"]
        < by_year[year][incumbent_name]["mae"]
    ]
    bootstrap = paired_cluster_bootstrap(frame)
    conditions = {
        "pooled_mae_improves_at_least_0_50": delta_mae <= -0.50,
        "cluster_bootstrap_ci_upper_below_zero": bootstrap["ci_95"][1] < 0.0,
        "mae_better_in_at_least_3_of_5_years": len(winning_years) >= 3,
        "pooled_spearman_does_not_decline": delta_spearman >= 0.0,
        "pooled_rmse_does_not_increase": delta_rmse <= 0.0,
        "absolute_bias_worsens_no_more_than_1_00": absolute_bias_worsening <= 1.0,
    }
    return {
        "pooled": pooled,
        "by_year": by_year,
        "deltas_challenger_minus_incumbent": {
            "mae": delta_mae,
            "rmse": delta_rmse,
            "spearman": delta_spearman,
            "absolute_bias": absolute_bias_worsening,
        },
        "challenger_mae_winning_years": winning_years,
        "challenger_mae_winning_year_count": len(winning_years),
        "paired_player_cluster_bootstrap": bootstrap,
        "switch_conditions": conditions,
        "earns_switch_recommendation": all(conditions.values()),
    }


def diagnostic_report(frame: pd.DataFrame) -> dict:
    incumbent_name = "direct_total"
    challenger_name = "games_weighted_ppg_x_16_5"
    realized_games = frame["target_games"].fillna(0.0)
    slices = {
        "prior_games_12_or_fewer": frame["prior_games"].le(12),
        "prior_games_above_12": frame["prior_games"].gt(12),
        "realized_games_12_or_fewer_outcome_conditioned": realized_games.le(12),
        "realized_games_13_or_more_outcome_conditioned": realized_games.ge(13),
    }
    return {
        name: {
            incumbent_name: metric_block(frame[mask], incumbent_name),
            challenger_name: metric_block(frame[mask], challenger_name),
        }
        for name, mask in slices.items()
    }


def case_report(panel: pd.DataFrame) -> dict:
    direct_train = panel[
        panel["season"].le(2025) & panel["y"].notna()
    ]
    ppg_train = ppg_training_rows(panel, 2026)
    cases = panel[
        panel["season"].eq(2026) & panel["player_id"].isin(CASE_IDS)
    ].copy()
    assert len(cases) == len(CASE_IDS)

    direct = make_model()
    direct.fit(direct_train[BASE_FEATURES], direct_train["y"])
    cases["corrected_direct_total_refit"] = np.clip(
        direct.predict(cases[BASE_FEATURES]), 0.0, None
    )
    ppg = make_model()
    ppg.fit(
        ppg_train[BASE_FEATURES],
        ppg_train["target_ppg"],
        sample_weight=ppg_train["target_games"],
    )
    cases["challenger_ppg"] = np.clip(
        ppg.predict(cases[BASE_FEATURES]), 0.0, None
    )
    cases["challenger_total_at_16_5"] = (
        cases["challenger_ppg"] * GAMES_MULTIPLIER
    )

    shipped = pd.read_csv(
        RESULTS / "wr_projection_2026.csv",
        usecols=["player_id", "player", "projection"],
    ).rename(columns={"projection": "shipped_projection"})
    cases = cases.merge(
        shipped,
        on=["player_id", "player"],
        how="left",
        validate="one_to_one",
    )
    cases = cases.sort_values("player_id")
    report = {}
    for row in cases.itertuples(index=False):
        report[row.player] = {
            "player_id": row.player_id,
            "shipped_projection_context": float(row.shipped_projection),
            "corrected_direct_total_refit": float(
                row.corrected_direct_total_refit
            ),
            "challenger_projected_ppg": float(row.challenger_ppg),
            "challenger_total_at_16_5": float(
                row.challenger_total_at_16_5
            ),
            "inputs": {
                "prior_games": float(row.prior_games),
                "prior_ppg": float(row.prior_ppg),
                "prior_half_ppr": float(row.prior_half_ppr),
                "years_exp": int(row.years_exp),
                "draft_pick": float(row.draft_pick),
            },
        }
    assert set(report) == set(CASE_IDS.values())
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--fire", action="store_true")
    args = parser.parse_args()

    before = artifact_state()
    assert_protected(before)
    panel = build_panel()
    output = {
        "mode": "check" if args.check else "fire",
        "structure": structural_report(panel),
    }
    if args.fire:
        predictions = walk_forward(panel)
        output["historical_2021_2025"] = comparison_report(predictions)
        output["diagnostic_slices"] = diagnostic_report(predictions)
        output["cases_2026"] = case_report(panel)

    after = artifact_state()
    assert before == after, "Protected model or result artifact changed"
    assert_protected(after)
    output["protected_artifacts_unchanged"] = True
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
