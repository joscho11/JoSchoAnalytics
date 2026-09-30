import sys
from pathlib import Path

import pandas as pd

_SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SITE))

from publishing.grader import grade_anytime_td_file, load_reviewed_td_settlements


def test_public_registry_preserves_v1_decisions_with_market_scoped_evidence():
    registry = load_reviewed_td_settlements(_SITE)
    assert len(registry) == 39
    assert {key[4] for key in registry} == {"anytime", "two_plus", "first"}
    assert all(value["status"] == "void" and value["evidence"].get("source_sha256") for value in registry.values())


def _inputs(path: Path):
    pd.DataFrame({
        "game_id": ["2026_03_MIN_TB", "2026_03_MIN_TB"],
        "player_id": ["DNP", "PRICE"],
        "player_display_name": ["DNP Player", "Myles Price"],
        "team": ["TB", "MIN"],
        "scored_anytime": [None, None], "scored_two_plus": [None, None],
        "status": ["final", "final"],
    }).to_csv(path, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 3, "game_id": "2026_03_MIN_TB",
        "home_team": "TB", "away_team": "MIN", "home_score": 0, "away_score": 6,
    }])
    actuals = pd.DataFrame([
        {"season": 2026, "week": 3, "season_type": "REG", "game_id": "2026_03_MIN_TB",
         "player_id": "PRICE", "team": "MIN", "player_display_name": "Myles Price",
         "rushing_tds": 0, "receiving_tds": 0, "special_teams_tds": 1},
        {"season": 2026, "week": 3, "season_type": "REG", "game_id": "2026_03_MIN_TB",
         "player_id": "QB", "team": "TB", "player_display_name": "TB Quarterback",
         "rushing_tds": 0, "receiving_tds": 0, "special_teams_tds": 0},
    ])
    participation = pd.DataFrame([
        {"season": 2026, "week": 3, "player_id": "PRICE", "team": "MIN",
         "player_display_name": "Myles Price", "offense_snaps": 0, "defense_snaps": 0, "st_snaps": 1},
        {"season": 2026, "week": 3, "player_id": "QB", "team": "TB",
         "player_display_name": "TB Quarterback", "offense_snaps": 1, "defense_snaps": 0, "st_snaps": 0},
    ])
    return schedule, actuals, participation


def test_return_touchdown_counts_and_reviewed_dnp_void_survives_replay(tmp_path):
    path = tmp_path / "anytime_td_2026_week03.csv"
    schedule, actuals, participation = _inputs(path)
    reviewed = {}
    for market in ("anytime", "two_plus"):
        reviewed[(2026, 3, "2026_03_MIN_TB", "DNP", market)] = {
            "status": "void", "evidence": {"source": "reviewed-migration-v2"},
        }

    grade_anytime_td_file(
        path, schedule, actuals, season=2026, week=3,
        participation=participation, reviewed_settlements=reviewed,
    )
    graded = pd.read_csv(path)
    dnp, price = graded.iloc[0], graded.iloc[1]
    assert dnp["settlement_status_anytime"] == "void"
    assert dnp["settlement_status_two_plus"] == "void"
    assert pd.isna(dnp["scored_anytime"]) and pd.isna(dnp["scored_two_plus"])
    assert price["scored_anytime"] == 1
    assert price["settlement_status_anytime"] == "settled"
    assert price["scored_two_plus"] == 0
    assert price["settlement_status_two_plus"] == "settled"


def test_missing_stats_or_participation_does_not_create_a_void(tmp_path):
    path = tmp_path / "anytime_td_2026_week03.csv"
    schedule, actuals, participation = _inputs(path)
    grade_anytime_td_file(
        path, schedule, actuals, season=2026, week=3,
        participation=participation, reviewed_settlements={},
    )
    graded = pd.read_csv(path)
    dnp = graded.iloc[0]
    assert pd.isna(dnp["scored_anytime"])
    assert dnp["settlement_status_anytime"] == "awaiting_evidence"
