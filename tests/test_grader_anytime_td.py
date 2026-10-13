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


def test_td_grader_uses_name_alias_participation_and_inactive_roster_evidence(tmp_path):
    path = tmp_path / "anytime_td_2026_week03.csv"
    pd.DataFrame({
        "game_id": ["2026_03_BAL_ATL"] * 5,
        "player_id": [
            "sleeper:hibner-unmatched", "sleeper:inactive-id", "sleeper:inactive-name",
            "PART", "UNKNOWN",
        ],
        "player_display_name": [
            "Matthew Hibner", "Inactive By ID", "Name Inactive", "Participated",
            "Unknown Player",
        ],
        "team": ["BAL", "BAL", "BAL", "ATL", "ATL"],
        "scored_anytime": [None] * 5, "scored_two_plus": [None] * 5,
        "status": ["pregame"] * 5,
    }).to_csv(path, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 3, "game_id": "2026_03_BAL_ATL",
        "home_team": "BAL", "away_team": "ATL", "home_score": 14, "away_score": 10,
    }])
    actuals = pd.DataFrame([
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "HIBNER-GSIS",
         "player_display_name": "Matt Hibner", "team": "BAL", "rushing_tds": 0, "receiving_tds": 0},
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "ATL-PLAYER",
         "player_display_name": "Atlanta Player", "team": "ATL", "rushing_tds": 0, "receiving_tds": 0},
    ])
    participation = pd.DataFrame([{
        "season": 2026, "week": 3, "player_id": "PART", "team": "ATL",
        "player_display_name": "Participated", "offense_snaps": 12,
    }])
    weekly_rosters = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "BAL", "status": "INA",
         "gsis_id": "ROSTER-ID", "sleeper_id": "inactive-id", "full_name": "Different Name"},
        {"season": 2026, "week": 3, "team": "BAL", "status": "INA",
         "gsis_id": "OTHER-ID", "sleeper_id": "other-sleeper-id", "full_name": "Name Inactive"},
    ])

    result = grade_anytime_td_file(
        path, schedule, actuals, participation=participation,
        weekly_rosters=weekly_rosters, season=2026, week=3,
    )

    graded = pd.read_csv(path).set_index("player_id")
    assert result["status"] == "graded"
    assert graded.loc["sleeper:hibner-unmatched", "scored_anytime"] == 0
    assert graded.loc["sleeper:hibner-unmatched", "settlement_status_two_plus"] == "settled"
    assert graded.loc["sleeper:inactive-id", "settlement_status_anytime"] == "void"
    assert graded.loc["sleeper:inactive-id", "settlement_status_two_plus"] == "void"
    assert graded.loc["sleeper:inactive-name", "settlement_status_anytime"] == "void"
    assert graded.loc["PART", "scored_anytime"] == 0
    assert graded.loc["PART", "settlement_status_two_plus"] == "settled"
    assert pd.isna(graded.loc["UNKNOWN", "scored_anytime"])
    assert graded.loc["UNKNOWN", "settlement_status_anytime"] == "awaiting_evidence"


def test_incomplete_stats_feed_keeps_positive_snap_missing_stat_pending_but_voids_ina(tmp_path):
    path = tmp_path / "anytime_td_2026_week03.csv"
    pd.DataFrame({
        "game_id": ["2026_03_BAL_ATL"] * 4,
        "player_id": ["PART", "INACTIVE", "BAL-ZERO", "BAL-SCORER"],
        "player_display_name": ["Participated", "Inactive Player", "Zero TD", "Scorer"],
        "team": ["ATL", "BAL", "BAL", "BAL"], "scored_anytime": [None] * 4,
        "scored_two_plus": [None] * 4, "status": ["pregame"] * 4,
    }).to_csv(path, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 3, "game_id": "2026_03_BAL_ATL",
        "home_team": "BAL", "away_team": "ATL", "home_score": 14, "away_score": 10,
    }])
    actuals = pd.DataFrame([
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "BAL-ZERO",
         "team": "BAL", "rushing_tds": 0, "receiving_tds": 0},
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "BAL-SCORER",
         "team": "BAL", "rushing_tds": 1, "receiving_tds": 0},
    ])
    participation = pd.DataFrame([{
        "season": 2026, "week": 3, "player_id": "PART", "team": "ATL",
        "player_display_name": "Participated", "offense_snaps": 12,
    }])
    weekly_rosters = pd.DataFrame([{
        "season": 2026, "week": 3, "team": "BAL", "status": "INA",
        "gsis_id": "INACTIVE", "full_name": "Inactive Player",
    }])

    grade_anytime_td_file(
        path, schedule, actuals, participation=participation,
        weekly_rosters=weekly_rosters, season=2026, week=3,
    )

    graded = pd.read_csv(path).set_index("player_id")
    assert graded.loc["INACTIVE", "settlement_status_anytime"] == "void"
    assert graded.loc["INACTIVE", "settlement_status_two_plus"] == "void"
    assert pd.isna(graded.loc["PART", "scored_anytime"])
    assert graded.loc["PART", "settlement_status_anytime"] == "awaiting_evidence"
    assert pd.isna(graded.loc["BAL-ZERO", "scored_anytime"])
    assert graded.loc["BAL-ZERO", "settlement_status_anytime"] == "awaiting_evidence"
    assert graded.loc["BAL-SCORER", "scored_anytime"] == 1
    assert graded.loc["BAL-SCORER", "settlement_status_anytime"] == "settled"


def test_positive_snaps_settle_missing_stat_as_loss_when_both_team_feeds_are_complete(tmp_path):
    path = tmp_path / "anytime_td_2026_week03.csv"
    pd.DataFrame({
        "game_id": ["2026_03_BAL_ATL"], "player_id": ["PART"],
        "player_display_name": ["Participated"], "team": ["ATL"],
        "scored_anytime": [None], "scored_two_plus": [None], "status": ["pregame"],
    }).to_csv(path, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 3, "game_id": "2026_03_BAL_ATL",
        "home_team": "BAL", "away_team": "ATL", "home_score": 14, "away_score": 10,
    }])
    actuals = pd.DataFrame([
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "BAL-PLAYER",
         "team": "BAL", "rushing_tds": 0, "receiving_tds": 0},
        {"season": 2026, "week": 3, "season_type": "REG", "player_id": "ATL-PLAYER",
         "team": "ATL", "rushing_tds": 0, "receiving_tds": 0},
    ])
    participation = pd.DataFrame([{
        "season": 2026, "week": 3, "player_id": "PART", "team": "ATL",
        "player_display_name": "Participated", "offense_snaps": 12,
    }])

    grade_anytime_td_file(
        path, schedule, actuals, participation=participation, season=2026, week=3,
    )

    graded = pd.read_csv(path).iloc[0]
    assert graded["scored_anytime"] == 0
    assert graded["settlement_status_anytime"] == "settled"
