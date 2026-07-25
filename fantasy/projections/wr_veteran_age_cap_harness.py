"""Structural-only harness for PREREG_wr_veteran_age_cap_2026-07-24.

This module deliberately does not fit a model, construct the season-total target, load
market columns, print an outcome metric, or write an artifact.  It is the preregistration's
Step-7 machinery check; the one-shot comparison belongs in a fresh later session.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
SEASON_DATASET = HERE.parent / "seasonal_projections" / "season_dataset_2014_2026.csv"
MODELS = HERE / "models"
RESULTS = HERE / "results"
ENGINE = HERE / "build_rb_projection.py"
TEST_SEASONS = (2021, 2022, 2023, 2024, 2025)
EXPECTED_OLDER_COUNTS = {2021: 20, 2022: 18, 2023: 29, 2024: 27, 2025: 29}
EXPECTED_OLDER_PLAYERS = 65

# Pinned from PREREG_wr_projection_2026-07-21.md section 3.  Keep age at its
# original list position so the only challenger change is its capped transform.
FROZEN_BASELINE_FEATURES = (
    "prior_ppg", "prior_half_ppr", "prior_games", "ppg_2yr", "ppg_3yr", "ppg_trend",
    "career_high_ppg", "prior_snap_share_pg", "prior_targets_pg", "prior_carries_pg",
    "prior_receptions_pg", "prior_touches_pg", "prior_target_share", "prior_air_yards_share",
    "prior_adot", "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa",
    "prior_rush_epa", "age", "years_exp", "draft_round", "draft_pick", "prior_team_pass_rate",
    "prior_team_plays", "vacated_target_share", "vacated_rush_share", "coach_changed",
    "qb_changed", "prior_games_missed", "missed_prior_season",
)
CHALLENGER_AGE_COL = "age_capped_30"
FORBIDDEN_MARKET_TOKENS = ("sleeper", "adp", "market")
ARTIFACTS = (
    MODELS / "wr_veteran_model.pkl",
    MODELS / "wr_rookie_model.pkl",
    RESULTS / "wr_projection_2026.csv",
    RESULTS / "wr_rookie_board_projection.csv",
)


def challenger_features(baseline: tuple[str, ...] = FROZEN_BASELINE_FEATURES) -> tuple[str, ...]:
    """Return the sole preregistered challenger feature definition."""
    assert baseline.count("age") == 1, "baseline must contain raw age exactly once"
    return tuple(CHALLENGER_AGE_COL if col == "age" else col for col in baseline)


def current_veteran_features() -> tuple[str, ...]:
    """Read the current engine's literal feature contract without importing model code."""
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"), filename=str(ENGINE))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "VET_FEATS" for target in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, list) and all(isinstance(col, str) for col in value)
            return tuple(value)
    raise AssertionError("could not statically read VET_FEATS from the projection engine")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def artifact_hashes() -> dict[str, str]:
    missing = [str(path) for path in ARTIFACTS if not path.exists()]
    assert not missing, f"missing protected WR artifacts: {missing}"
    return {path.name: _md5(path) for path in ARTIFACTS}


def load_structural_panel(path: Path = SEASON_DATASET) -> pd.DataFrame:
    """Load only point-in-time structural columns; targets and market columns are excluded."""
    required = {"player_id", "position", "is_rookie", "season", *FROZEN_BASELINE_FEATURES}
    forbidden = [col for col in required if any(token in col.lower() for token in FORBIDDEN_MARKET_TOKENS)]
    assert not forbidden, f"harness requested forbidden market columns: {forbidden}"
    panel = pd.read_csv(path, usecols=lambda col: col in required)
    missing = required.difference(panel.columns)
    assert not missing, f"season dataset missing structural columns: {sorted(missing)}"
    assert not any(any(token in col.lower() for token in FORBIDDEN_MARKET_TOKENS) for col in panel.columns)
    panel = panel[(panel["position"] == "WR") & (panel["is_rookie"] == 0)].copy()
    panel[CHALLENGER_AGE_COL] = panel["age"].clip(upper=30.0)
    return panel


def structural_summary(panel: pd.DataFrame) -> dict[str, object]:
    """Assert the frozen scope and return counts only (never a model/outcome metric)."""
    baseline = FROZEN_BASELINE_FEATURES
    challenger = challenger_features(baseline)
    assert current_veteran_features() == baseline, "current veteran feature contract drifted from prereg"
    assert len(baseline) == len(challenger) == 32
    assert baseline.index("age") == challenger.index(CHALLENGER_AGE_COL)
    assert "age" not in challenger and CHALLENGER_AGE_COL not in baseline
    assert all(a == b or (a == "age" and b == CHALLENGER_AGE_COL) for a, b in zip(baseline, challenger))

    test = panel[panel["season"].isin(TEST_SEASONS)].copy()
    assert test["age"].notna().all(), "age is missing in an outer test row"
    assert (test[CHALLENGER_AGE_COL] <= 30.0).all(), "challenger age cap exceeded 30"
    assert (test[CHALLENGER_AGE_COL] == test["age"].clip(upper=30.0)).all(), "incorrect age transform"

    counts = {
        year: int((test.loc[test["season"] == year, "age"] >= 30.0).sum())
        for year in TEST_SEASONS
    }
    assert counts == EXPECTED_OLDER_COUNTS, f"older-WR counts drifted: {counts}"
    older = test[test["age"] >= 30.0]
    assert int(older["player_id"].nunique()) == EXPECTED_OLDER_PLAYERS, "older-player count drifted"

    for year in TEST_SEASONS:
        train = panel[panel["season"] < year]
        test_year = panel[panel["season"] == year]
        assert not train.empty and not test_year.empty, f"empty walk-forward fold {year}"
        assert (train["season"] < year).all(), f"walk-forward leakage in fold {year}"

    return {
        "test_rows": int(len(test)),
        "older_player_seasons": int(len(older)),
        "older_unique_players": int(older["player_id"].nunique()),
        "older_counts": counts,
        "baseline_feature_count": len(baseline),
        "challenger_feature_count": len(challenger),
    }


def run_check() -> dict[str, object]:
    """Run only structural assertions and protected-artifact identity checks."""
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_execution = ("." + "fit(", "season_total" + "_target(", "nested" + "_select(")
    found = [token for token in forbidden_execution if token in source]
    assert not found, f"structural harness contains forbidden evaluation code: {found}"

    before = artifact_hashes()
    summary = structural_summary(load_structural_panel())
    after = artifact_hashes()
    assert before == after, "structural harness changed a protected WR artifact"
    print("WR AGE-CAP STRUCTURAL HARNESS: PASS (no fit, no outcome metric, no market columns)")
    print(f"  features: baseline={summary['baseline_feature_count']} challenger={summary['challenger_feature_count']}")
    print(f"  age-30+ rows by fold: {summary['older_counts']} | unique players={summary['older_unique_players']}")
    print("  protected WR pkl/result hashes: unchanged")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Structural-only age-cap preregistration harness")
    parser.add_argument("--check", action="store_true", help="run structural assertions only")
    args = parser.parse_args()
    if not args.check:
        raise SystemExit("pass --check; this harness has no fit or fire mode")
    run_check()


if __name__ == "__main__":
    main()
