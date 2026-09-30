import sys
from pathlib import Path

import pandas as pd

_SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SITE))

from publishing.cli import _grade_published


def test_scheduled_td_grading_fetches_participation_once_per_season(tmp_path, monkeypatch):
    td_dir = tmp_path / "betting" / "anytime_td"
    td_dir.mkdir(parents=True)
    schedules = []
    pbp_rows = []
    stats_rows = []
    snap_rows = []
    for week, game_id, team, opponent, home, away, player_id in (
        (1, "2026_01_AAA_BBB", "AAA", "BBB", "AAA", "BBB", "P1"),
        (2, "2026_02_CCC_DDD", "CCC", "DDD", "DDD", "CCC", "P2"),
    ):
        pd.DataFrame({
            "game_id": [game_id], "player_id": [player_id],
            "player_display_name": [f"Player {player_id}"], "team": [team],
            "scored_anytime": [None], "scored_two_plus": [None], "scored_first": [None],
        }).to_csv(td_dir / f"anytime_td_2026_week{week:02d}.csv", index=False)
        schedules.append({
            "season": 2026, "week": week, "game_id": game_id,
            "home_team": home, "away_team": away,
            "home_score": 6 if home == team else 0,
            "away_score": 6 if away == team else 0,
        })
        pbp_rows.append({
            "game_id": game_id, "play_id": 1, "qtr": 1, "touchdown": 1,
            "td_player_id": player_id, "td_team": team, "posteam": team,
            "defteam": opponent, "return_touchdown": 0,
            "total_home_score": 6 if home == team else 0,
            "total_away_score": 6 if away == team else 0,
        })
        for current_team, current_id, is_player in ((team, player_id, True), (opponent, f"QB{week}", False)):
            stats_rows.append({
                "season": 2026, "week": week, "season_type": "REG", "game_id": game_id,
                "player_id": current_id, "position": "WR" if is_player else "QB",
                "team": current_team, "player_display_name": f"Player {current_id}",
                "rushing_tds": 0, "receiving_tds": 0, "special_teams_tds": 0,
            })
            snap_rows.append({
                "season": 2026, "week": week, "player_id": current_id,
                "team": current_team, "player_display_name": f"Player {current_id}",
                "offense_snaps": 1, "defense_snaps": 0, "st_snaps": 0,
            })

    calls = {"snaps": 0}
    monkeypatch.setattr("publishing.grader.fetch_nfl_schedule", lambda season: pd.DataFrame(schedules))
    monkeypatch.setattr("publishing.grader.fetch_player_stats", lambda season: pd.DataFrame(stats_rows))
    monkeypatch.setattr("publishing.grader.fetch_nfl_pbp", lambda season: pd.DataFrame(pbp_rows))
    def fetch_snaps(season):
        calls["snaps"] += 1
        return pd.DataFrame(snap_rows)
    monkeypatch.setattr("publishing.grader.fetch_snap_counts", fetch_snaps)

    result = _grade_published(tmp_path, "anytime_td")
    assert result["anytime_td"]["2026w01"]["graded_rows"] == 1
    assert result["first_td"]["2026w02"]["graded_rows"] == 1
    assert calls["snaps"] == 1
