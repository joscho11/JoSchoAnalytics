"""grader.py's first-TD classification must match first_td/src/labels.py exactly.

These are two independent implementations of one rule (live grading here,
offline label-building there). Regression coverage for a real bug found by
independent audit 2026-09: both copies checked scorer position before
return_touchdown, misclassifying a skill-position kick/punt returner's
score as offense_skill instead of special_teams.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))

from publishing.grader import _classify_first_td_row


def test_skill_position_kickoff_return_is_special_teams_not_offense():
    row = {
        "td_player_id": "WR1", "td_team": "AAA",
        "posteam": "AAA", "defteam": "BBB",
        "return_touchdown": 1,
    }
    assert _classify_first_td_row(row, {"WR1": "WR"}) == "special_teams"


def test_ordinary_offensive_skill_td_still_classifies_correctly():
    row = {
        "td_player_id": "RB1", "td_team": "AAA",
        "posteam": "AAA", "defteam": "BBB",
        "return_touchdown": 0,
    }
    assert _classify_first_td_row(row, {"RB1": "RB"}) == "offense_skill"


def test_defensive_score_is_defense():
    row = {
        "td_player_id": "LB1", "td_team": "BBB",
        "posteam": "AAA", "defteam": "BBB",
        "return_touchdown": 1,
    }
    assert _classify_first_td_row(row, {"LB1": "LB"}) == "defense"


def test_non_skill_offensive_scorer_is_defense_bucket():
    """An OL recovering a fumble: td_team==posteam, not a return, not skill."""
    row = {
        "td_player_id": "OL1", "td_team": "AAA",
        "posteam": "AAA", "defteam": "BBB",
        "return_touchdown": 0,
    }
    assert _classify_first_td_row(row, {"OL1": "OL"}) == "defense"


def _grade_fixture(tmp_path, pbp_rows, home_score, away_score):
    import pandas as pd
    from publishing.grader import grade_first_td_file

    csv = tmp_path / "anytime_td_2026_week02.csv"
    pd.DataFrame({
        "game_id": ["2026_02_MIN_CHI"] * 2,
        "player_id": ["JJ", "CW"],
        "scored_first": [float("nan")] * 2,
        "status": ["scheduled"] * 2,
    }).to_csv(csv, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 2, "game_id": "2026_02_MIN_CHI",
        "home_team": "CHI", "away_team": "MIN",
        "home_score": home_score, "away_score": away_score,
    }])
    pbp = pd.DataFrame(pbp_rows)
    actuals = pd.DataFrame({"player_id": ["JJ", "CW"], "position": ["WR", "QB"]})
    result = grade_first_td_file(csv, schedule, pbp, actuals, season=2026, week=2)
    return result, pd.read_csv(csv)


def _plays(final_home, final_away, touchdown=0):
    return [
        {"game_id": "2026_02_MIN_CHI", "play_id": 1, "qtr": 1, "touchdown": 0,
         "total_home_score": 0, "total_away_score": 0},
        {"game_id": "2026_02_MIN_CHI", "play_id": 2, "qtr": 4, "touchdown": touchdown,
         "total_home_score": final_home, "total_away_score": final_away},
    ]


def test_final_game_with_no_touchdown_grades_every_player_no(tmp_path):
    """MIN 9, CHI 3 on four field goals: nobody scored first, so every row is a real No."""
    result, graded = _grade_fixture(tmp_path, _plays(3, 9), home_score=3, away_score=9)
    assert result["status"] == "graded" and result["complete"] is True
    assert graded["scored_first"].tolist() == [0.0, 0.0]
    assert graded["status"].tolist() == ["final", "final"]


def test_no_touchdown_game_stays_pending_until_pbp_reaches_final_score(tmp_path):
    """pbp that has not caught up (running score below the final) must not be read as a no-TD game."""
    result, graded = _grade_fixture(tmp_path, _plays(0, 3), home_score=3, away_score=9)
    assert result["status"] == "pending" and result["pending_games"] == ["2026_02_MIN_CHI"]
    assert graded["scored_first"].isna().all()


def test_touchdown_game_still_grades_the_scorer(tmp_path):
    rows = _plays(3, 9)
    rows[1].update({
        "touchdown": 1, "td_player_id": "JJ", "td_team": "MIN",
        "posteam": "MIN", "defteam": "CHI", "return_touchdown": 0,
    })
    result, graded = _grade_fixture(tmp_path, rows, home_score=3, away_score=9)
    assert graded["scored_first"].tolist() == [1.0, 0.0]


def test_first_td_grading_keeps_void_status_set_by_the_anytime_grader(tmp_path):
    import pandas as pd
    from publishing.grader import grade_first_td_file

    csv = tmp_path / "anytime_td_2026_week02.csv"
    pd.DataFrame({
        "game_id": ["2026_02_MIN_CHI"] * 2, "player_id": ["JJ", "CW"],
        "scored_first": [float("nan")] * 2, "status": ["void", "scheduled"],
    }).to_csv(csv, index=False)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 2, "game_id": "2026_02_MIN_CHI",
        "home_team": "CHI", "away_team": "MIN", "home_score": 3, "away_score": 9,
    }])
    actuals = pd.DataFrame({"player_id": ["JJ", "CW"], "position": ["WR", "QB"]})
    grade_first_td_file(csv, schedule, pd.DataFrame(_plays(3, 9)), actuals, season=2026, week=2)
    assert pd.read_csv(csv)["status"].tolist() == ["void", "final"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
