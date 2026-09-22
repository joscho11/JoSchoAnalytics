"""2025 weekly CSVs stay as the site demo. 2026 files come from weekly_projections_v2."""
import hashlib
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SITE_PAGES))

from streamlit.testing.v1 import AppTest

import page_weekly_fantasy as weekly

DEMO_MD5 = {
    "projections_2025_week10.csv": "46d2797210f539e89a427fb07ab94ca0",
    "projections_2025_week11.csv": "7f974deb1399ec5cea7085b3465276e6",
    "projections_2025_week12.csv": "fb458ba5fbeaf1de003a2cdae1c82d12",
    "projections_2025_week13.csv": "08c1ee32cb21cae99b5bd552a57ac7f7",
    "projections_2025_week14.csv": "8a41574dd3f066e81ca2198667a08193",
    "projections_2025_week15.csv": "1a17329c9c0c1a51babd9729416cdba7",
    "projections_2025_week16.csv": "46bd8859fe805f17f6ea12a502cb1bda",
    "projections_2025_week17.csv": "e384d1f6baa0af1f7dd9a17be743a18d",
}


def test_2025_demo_csvs_byte_identical():
    folder = _HERE / "fantasy" / "fantasy_projections"
    assert sorted(DEMO_MD5) == sorted(p.name for p in folder.glob("projections_2025_week*.csv"))
    for name, digest in DEMO_MD5.items():
        payload = (folder / name).read_bytes()
        assert hashlib.md5(payload).hexdigest() == digest, name


def test_parse_proj_name():
    assert weekly._parse_proj_name("projections_2026_week01.csv") == (2026, 1)
    assert weekly._parse_proj_name("notes.txt") is None


def test_available_files_are_demo_csvs_only_without_releases(tmp_path, monkeypatch):
    jsa = tmp_path / "jsa"
    jsa.mkdir()
    (jsa / "projections_2025_week10.csv").write_text("player_id\n1\n", encoding="utf-8")
    (jsa / "projections_2026_week01.csv").write_text("site\n", encoding="utf-8")
    monkeypatch.setattr(weekly, "_JSA_PROJ_DIR", jsa)
    monkeypatch.setattr(weekly, "published_builds", lambda *args, **kwargs: [])
    got = weekly.available_projection_files()
    assert got[(2025, 10)] == jsa / "projections_2025_week10.csv"
    assert (2026, 1) not in got


def test_unvalidated_2026_files_are_not_public(tmp_path, monkeypatch):
    jsa = tmp_path / "jsa"
    jsa.mkdir()
    (jsa / "projections_2026_week01.csv").write_text("site\n", encoding="utf-8")
    monkeypatch.setattr(weekly, "_JSA_PROJ_DIR", jsa)
    monkeypatch.setattr(weekly, "published_builds", lambda *args, **kwargs: [])
    got = weekly.available_projection_files()
    assert (2026, 1) not in got


def test_complete_week1_release_prefers_graded_postgame_artifact():
    path = weekly.available_projection_files()[(2026, 1)]
    assert path.name.endswith("-graded.csv")
    frame = pd.read_csv(path)
    assert "actual_half_ppr" in frame.columns
    assert frame["actual_half_ppr"].notna().all()
    actuals = weekly._actuals_from_graded_projection(frame)
    assert len(actuals["half_ppr"]) == len(frame)


def _render_weekly(tmp_path):
    h = tmp_path / "h_weekly.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_weekly_fantasy as p\np.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _render_weekly_release(tmp_path, projection_path, season=2026, week=1):
    h = tmp_path / "h_weekly_release.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "from pathlib import Path\n"
        "import page_weekly_fantasy as p\n"
        "_available = p.available_projection_files\n"
        "_default = p.page_common.release_default_selection\n"
        "_status = p.page_common.render_release_status\n"
        "try:\n"
        f"    p.available_projection_files = lambda: {{({season}, {week}): Path(r'{projection_path}')}}\n"
        f"    p.page_common.release_default_selection = lambda *a, **k: ({season}, {week})\n"
        "    p.page_common.render_release_status = lambda *a, **k: None\n"
        "    p.render()\n"
        "finally:\n"
        "    p.available_projection_files = _available\n"
        "    p.page_common.release_default_selection = _default\n"
        "    p.page_common.render_release_status = _status\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def test_week1_graded_release_renders_postgame_actuals(tmp_path):
    path = weekly.available_projection_files()[(2026, 1)]
    at = _render_weekly_release(tmp_path, path)
    assert any("Results are in" in str(item.value) for item in at.success)
    actual_frames = [frame.value for frame in at.dataframe if "Actual Pts" in frame.value.columns]
    assert actual_frames
    assert any(frame["Actual Pts"].notna().any() for frame in actual_frames)
    assert all("Sleeper" not in frame.columns for frame in actual_frames)
    assert all(
        not {"Actual Pass Yds", "Actual Rush Yds", "Actual Rec Yds"} & set(frame.columns)
        for frame in actual_frames
    )


def test_weekly_fantasy_defaults_to_live_2026_release(tmp_path):
    at = _render_weekly(tmp_path)
    blob = " ".join(
        str(getattr(w, "value", ""))
        for w in list(at.caption) + list(at.info) + list(at.markdown) + list(at.title)
    ).lower()
    assert "published" in blob
    assert "2026" in blob
    assert "weekly fantasy projections" in blob


def test_weekly_fantasy_defaults_to_latest_published_week(tmp_path):
    """The default follows the newest published release, so it must not be pinned to a week."""
    import page_common

    season, week = page_common.release_default_selection("fantasy", (2025, 10))
    at = _render_weekly(tmp_path)
    by_key = {getattr(w, "key", None): w.value for w in at.selectbox}
    assert int(by_key["wf_season"]) == 2026 == int(season)
    assert int(by_key["wf_week"]) == int(week)
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "green-badge" in markdown and "Published" in markdown
    assert "Published" in markdown
    infos = " ".join(str(w.value) for w in at.info).lower()
    assert "no agent notes for this week" not in infos
    assert "sleeper's projection beside ours" not in infos
    assert not any(exp.label == "Why Sleeper is included for Week 1" for exp in at.expander)


def test_coming_soon_copy_points_at_2025_demo():
    text = weekly._coming_soon_copy(2026, 1)
    assert "2026 Week 1" in text
    assert "2025" in text
    assert "demo" in text.lower()


def test_preview_column_contract_matches_simple_and_detailed_views():
    path = _HERE / "fantasy" / "fantasy_projections" / "projections_2025_week17.csv"
    source = pd.read_csv(path)

    assert weekly._preview_detail_available(source)
    assert ["#", *weekly._preview_table_columns("QB", False, False)] == [
        "#", "Player", "Opponent", "Proj Pts",
    ]
    assert ["#", *weekly._preview_table_columns("QB", True, False)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Pass Yds", "Proj Rush Yds",
        "EPA Rank", "Team Total", "Health",
    ]
    assert ["#", *weekly._preview_table_columns("RB", True, False)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Rush Yds", "Proj Rec Yds",
        "EPA Rank", "Team Total", "Health",
    ]
    assert ["#", *weekly._preview_table_columns("WR", True, False)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Rec Yds",
        "EPA Rank", "Team Total", "Health",
    ]
    assert ["#", *weekly._preview_table_columns("TE", True, False)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Rec Yds",
        "EPA Rank", "Team Total", "Health",
    ]
    assert ["#", *weekly._preview_table_columns("QB", True, True)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Pass Yds", "Proj Rush Yds",
        "EPA Rank", "Team Total", "Health",
        "Actual Pts", "Actual Pass Yds", "Actual Rush Yds",
    ]
    assert ["#", *weekly._preview_table_columns("RB", True, True)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Rush Yds", "Proj Rec Yds",
        "EPA Rank", "Team Total", "Health",
        "Actual Pts", "Actual Rush Yds", "Actual Rec Yds",
    ]
    assert ["#", *weekly._preview_table_columns("WR", True, True)] == [
        "#", "Player", "Opponent", "Proj Pts", "Proj Rec Yds",
        "EPA Rank", "Team Total", "Health",
        "Actual Pts", "Actual Rec Yds",
    ]


def test_preview_layout_covers_week17_and_every_future_live_season():
    assert weekly._uses_preview_layout(2025, 17)
    assert not weekly._uses_preview_layout(2025, 16)
    assert weekly._uses_preview_layout(2026, 1)
    assert weekly._uses_preview_layout(2027, 18)


def test_week17_excludes_skattebo_without_changing_the_frozen_source():
    path = _HERE / "fantasy" / "fantasy_projections" / "projections_2025_week17.csv"
    source = pd.read_csv(path)
    skattebo_id = "00-0040715"

    assert skattebo_id in set(source["player_id"].astype(str))
    displayed = weekly._apply_display_exclusions(source, 2025, 17)
    assert skattebo_id not in set(displayed["player_id"].astype(str))

    other_week = weekly._apply_display_exclusions(source, 2025, 16)
    future_release = weekly._apply_display_exclusions(source, 2026, 1)
    pd.testing.assert_frame_equal(other_week, source)
    pd.testing.assert_frame_equal(future_release, source)


def _week17_id(source: pd.DataFrame, name: str) -> str:
    hit = source.loc[source["player_display_name"].eq(name), "player_id"]
    assert not hit.empty, name
    return str(hit.iloc[0])


def test_board_drops_dnp_and_doubtful_for_demo_and_live_weeks():
    path = _HERE / "fantasy" / "fantasy_projections" / "projections_2025_week17.csv"
    source = pd.read_csv(path)
    mixon = _week17_id(source, "Joe Mixon")
    lamar = _week17_id(source, "Lamar Jackson")
    montgomery = _week17_id(source, "David Montgomery")
    played = set(source["player_id"].astype(str)) - {mixon}

    shown = weekly.eligible_board_rows(source, 2025, 17, played_ids=played)
    ids = set(shown["player_id"].astype(str))
    assert mixon not in ids
    assert lamar not in ids
    assert montgomery in ids

    live = weekly.eligible_board_rows(source, 2026, 1, played_ids=played)
    live_ids = set(live["player_id"].astype(str))
    assert mixon not in live_ids
    assert lamar not in live_ids
    assert montgomery in live_ids


def test_pregame_board_drops_roster_ir_and_keeps_questionable():
    frame = pd.DataFrame({
        "player_id": ["ir1", "q1", "healthy"],
        "player_display_name": ["IR Back", "Q Receiver", "Starter"],
        "position": ["RB", "WR", "RB"],
        "injury_status_score": [1.0, 0.5, 1.0],
        "projected_pts": [14.0, 12.0, 10.0],
    })
    shown = weekly.eligible_board_rows(
        frame, 2026, 1, unavailable_ids={"ir1"},
    )
    ids = set(shown["player_id"].astype(str))
    assert ids == {"q1", "healthy"}


def test_unavailable_roster_ids_uses_weekly_ina_then_season_ir(monkeypatch):
    weekly_frame = pd.DataFrame({
        "gsis_id": ["act1", "ina1"],
        "week": [1, 1],
        "status": ["ACT", "INA"],
    })
    season_frame = pd.DataFrame({
        "gsis_id": ["res1"],
        "status": ["RES"],
    })
    monkeypatch.setattr(weekly, "_OFFLINE", False)
    monkeypatch.setattr(weekly, "_load_weekly_rosters_season", lambda season: weekly_frame)
    monkeypatch.setattr(weekly, "_load_season_rosters", lambda season: season_frame)
    assert weekly.unavailable_roster_ids(2026, 1) == frozenset({"ina1", "res1"})

    empty_week = pd.DataFrame({
        "gsis_id": ["act1"],
        "week": [2],
        "status": ["ACT"],
    })
    monkeypatch.setattr(weekly, "_load_weekly_rosters_season", lambda season: empty_week)
    assert weekly.unavailable_roster_ids(2026, 1) == frozenset({"res1"})

    monkeypatch.setattr(weekly, "_OFFLINE", True)
    assert weekly.unavailable_roster_ids(2026, 1) == frozenset()


def test_slim_2026_dnp_filter_without_injury_column():
    frame = pd.DataFrame({
        "player_id": ["play", "sit"],
        "player_display_name": ["Play", "Sit"],
        "position": ["RB", "RB"],
        "projected_pts": [12.0, 11.0],
    })
    shown = weekly.eligible_board_rows(frame, 2026, 1, played_ids={"play"})
    assert set(shown["player_id"].astype(str)) == {"play"}


def test_slim_2026_schema_has_core_columns():
    frame = pd.DataFrame({
        "player_id": ["00-1"],
        "player_display_name": ["Test"],
        "position": ["RB"],
        "team": ["NE"],
        "opponent_team": ["SEA"],
        "season": [2026],
        "week": [1],
        "projected_pts": [12.4],
    })
    for col in ("player_id", "player_display_name", "position", "team",
                "opponent_team", "projected_pts"):
        assert col in frame.columns
    assert "depth_chart_position" not in frame.columns
    assert "off_epa_roll4" not in frame.columns


def test_weekly_scoring_recalculates_sleeper_projection():
    frame = pd.DataFrame({
        "player_id": ["rb", "wr", "te", "qb"],
        "player_display_name": ["Runner", "Receiver", "Tight End", "Passer"],
        "position": ["RB", "WR", "TE", "QB"],
        "projected_pts": [10.0, 12.0, 8.0, 20.0],
        "slp_proj": [11.0, 13.0, 9.0, 21.0],
    })
    standard = weekly.apply_weekly_scoring(frame, "Standard")
    ppr = weekly.apply_weekly_scoring(frame, "PPR")

    assert standard["_sleeper_scoring_pts"].tolist() == [9.75, 10.25, 6.75, 21.0]
    assert ppr["_sleeper_scoring_pts"].tolist() == [12.25, 15.75, 11.25, 21.0]
    assert standard["_scoring_pts"].tolist() == [8.75, 9.25, 5.75, 20.0]
    assert ppr["_scoring_pts"].tolist() == [11.25, 14.75, 10.25, 20.0]


def test_future_release_uses_enabled_player_prop_toggle(tmp_path):
    projection_path = tmp_path / "projections_2026_week01.csv"
    pd.DataFrame({
        "player_id": ["00-1"],
        "player_display_name": ["Test Quarterback"],
        "position": ["QB"],
        "team": ["NE"],
        "opponent_team": ["SEA"],
        "season": [2026],
        "week": [1],
        "projected_pts": [20.4],
        "pred_qb_pass_yards": [252.5],
        "pred_qb_rush_yards": [28.0],
        "pred_rush_yards": [None],
        "pred_rec_yards": [None],
        "pred_wr_rec_yards": [None],
        "pred_te_rec_yards": [None],
        "off_epa_rank": [7],
        "implied_team_total": [24.5],
        "injury_status_score": [1.0],
    }).to_csv(projection_path, index=False)

    at = _render_weekly_release(tmp_path, projection_path)

    more_info = next(widget for widget in at.toggle if widget.key == "wf_more_info")
    assert more_info.disabled is False
    assert more_info.label == "More info: projected yards for player props"
    captions = " ".join(str(item.value) for item in at.caption)
    assert "player-prop over/under lines" in captions
    infos = " ".join(str(item.value) for item in at.info).lower()
    assert "no agent notes for this week" not in infos

    at = more_info.set_value(True).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert next(widget for widget in at.toggle if widget.key == "wf_more_info").value is True


def test_week17_renders_simple_and_detailed_2026_preview(tmp_path):
    at = _render_weekly(tmp_path)
    week = next(widget for widget in at.selectbox if widget.key == "wf_week")
    at = week.set_value(17).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    infos = " ".join(str(item.value) for item in at.info)
    assert "immutable revision" in infos
    assert "lock at kickoff" in infos
    assert "No agent notes for this week" not in infos
    assert all(widget.key != "wf_view" for widget in at.segmented_control)
    assert not any(widget.key == "wf_more_info" for widget in at.toggle)


def test_preview_phone_grid_keeps_ranking_columns():
    import page_weekly_fantasy as page

    assert page.PREVIEW_PHONE_COLUMNS == [
        "#", "Player", "Opponent", "Proj Pts", "Health", "Actual Pts",
    ]
    assert set(page.PREVIEW_SIMPLE_COLUMNS).issubset(page.PREVIEW_PHONE_COLUMNS)


def test_week_one_phone_grid_keeps_sleeper_beside_model_projection():
    import page_weekly_fantasy as page

    available = [
        "#", "Player", "Opponent", "Proj Pts", "Sleeper", "Health", "Actual Pts",
    ]
    assert page._preview_phone_columns(available, show_sleeper=True) == [
        "#", "Player", "Proj Pts", "Sleeper", "Opponent", "Health", "Actual Pts",
    ]
    assert page._preview_phone_columns(available, show_sleeper=False) == [
        "#", "Player", "Opponent", "Proj Pts", "Health", "Actual Pts",
    ]


def test_actuals_wait_for_every_game_in_the_week():
    schedule = pd.DataFrame({
        "season": [2026, 2026, 2026, 2026],
        "season_type": ["REG", "REG", "REG", "POST"],
        "week": [1, 1, 2, 1],
        "home_score": [24, None, 17, 30],
        "away_score": [20, None, 14, 27],
    })

    assert weekly._week_is_complete(schedule, 2026, 1) is False

    schedule.loc[1, ["home_score", "away_score"]] = [21, 10]
    assert weekly._week_is_complete(schedule, 2026, 1) is True


def test_actuals_fail_closed_when_week_schedule_is_missing():
    assert weekly._week_is_complete(None, 2026, 1) is False
    assert weekly._week_is_complete(pd.DataFrame(), 2026, 1) is False
    assert weekly._week_is_complete(
        pd.DataFrame({"season": [2026], "week": [1]}), 2026, 1
    ) is False
