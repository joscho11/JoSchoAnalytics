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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
