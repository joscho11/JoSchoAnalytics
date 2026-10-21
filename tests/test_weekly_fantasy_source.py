"""2025 weekly CSVs stay as the site demo. 2026 files come from weekly_projections_v2."""
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd
import streamlit as st

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


def test_last_updated_tag_formats_release_time_in_eastern_time():
    assert weekly._format_last_updated("2026-10-01T02:40:07Z") == (
        "Last updated Sep 30, 2026 at 10:40 PM ET"
    )
    assert weekly._format_last_updated("not-a-timestamp") is None


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


def test_selected_build_details_exposes_review_note_and_postgame_state(tmp_path):
    metadata_path = tmp_path / "data" / "releases" / "builds" / "week07" / "metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(json.dumps({
        "season": 2026, "week": 7,
        "release_review": {"public_note": "No BAL QB is present in the source projection."},
    }), encoding="utf-8")
    manifest_path = tmp_path / "data" / "releases" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"products": {"fantasy": {"builds": {
        "build-7": {
            "season": 2026, "week": 7,
            "metadata": "data/releases/builds/week07/metadata.json",
            "grading": {"complete": True},
        }
    }}}}), encoding="utf-8")

    metadata, grading = weekly._selected_build_details(
        {"build_id": "build-7"}, season=2026, week=7, root=tmp_path
    )
    assert metadata["release_review"]["public_note"].startswith("No BAL QB")
    assert grading["complete"] is True


def test_week05_graded_release_restores_projection_team_column():
    path = weekly.available_projection_files()[(2026, 5)]
    assert path.name.endswith("-graded.csv")

    frame = weekly._load_proj_csv(str(path))

    assert "team" in frame.columns
    assert frame["team"].notna().all()


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


def test_week05_postgame_view_renders_graded_release(tmp_path):
    path = weekly.available_projection_files()[(2026, 5)]

    at = _render_weekly_release(tmp_path, path, season=2026, week=5)

    warnings = " ".join(str(item.value) for item in at.warning)
    assert "Projection CSV is missing columns" not in warnings
    tables = [item.value for item in at.dataframe if "Player" in item.value.columns]
    assert tables
    assert any(frame["Actual Pts"].notna().any() for frame in tables if "Actual Pts" in frame)


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


def test_manual_qb_default_renders_source_out_warning_and_player(tmp_path):
    path = tmp_path / "projections_2026_week07.csv"
    pd.DataFrame({
        "player_id": ["00-0034796", "00-0039918"],
        "player_display_name": ["Lamar Jackson", "Caleb Williams"],
        "position": ["QB", "QB"],
        "team": ["BAL", "CHI"],
        "opponent_team": ["CLE", "ATL"],
        "season": [2026, 2026], "week": [7, 7],
        "projected_pts": [15.31, 16.45],
        "injury_status": ["Out", "Out"],
        "reported_injury_status": ["Out", "Out"],
        "injury_status_source": ["sleeper_player_directory"] * 2,
        "slp_proj": [20.75, 17.91],
        "tuesday_sleeper_projection_signal": [True, True],
        "injury_status_score": [0.0, 0.0],
        "is_home": [0.0, 0.0], "off_epa_rank": [8.0, 7.0],
        "implied_team_total": [22.75, 26.25],
        "qb_manual_assumption": [True, True],
        "qb_assumption_source": ["user_manual_override", "user_manual_override"],
        "qb_assumption_reason": ["Approved main path", "Approved main path"],
        "qb_assumption_as_of_utc": ["2026-10-13T13:53:14Z"] * 2,
        "kickoff": ["2026-10-25 13:00:00-04:00"] * 2,
    }).to_csv(path, index=False)

    at = _render_weekly_release(tmp_path, path, season=2026, week=7)
    warnings = " ".join(str(item.value) for item in at.warning)
    assert "Tuesday Sleeper signal" in warnings
    assert "does not confirm they will play" in warnings
    assert "Lamar Jackson (BAL)" in warnings
    assert "Caleb Williams (CHI)" in warnings
    assert "not clearance" in warnings
    tables = [item.value for item in at.dataframe if "Player" in item.value.columns]
    assert tables and any("Lamar Jackson - BAL" in frame.Player.tolist() for frame in tables)


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


def test_approved_manual_qb_default_can_show_with_source_out_label():
    frame = pd.DataFrame({
        "player_id": ["qb-out", "qb-out-unapproved"],
        "player_display_name": ["Approved QB", "Unapproved QB"],
        "position": ["QB", "QB"],
        "team": ["BAL", "CHI"],
        "injury_status": ["Out", "Out"],
        "injury_status_score": [0.0, 0.0],
        "qb_manual_assumption": [True, False],
        "qb_assumption_source": ["user_manual_override", ""],
        "qb_assumption_reason": ["Approved main path", ""],
        "qb_assumption_as_of_utc": ["2026-10-13T13:53:14Z", ""],
    })
    shown = weekly.eligible_board_rows(frame, 2026, 6)

    assert set(shown.player_id.astype(str)) == {"qb-out"}
    assert shown.iloc[0].injury_status == "Out"


def test_tuesday_projection_signal_keeps_directory_out_but_not_terminal_or_manual_out():
    frame = pd.DataFrame({
        "player_id": ["projected-out", "projected-ir", "inactive-roster", "manual-out", "no-projection"],
        "player_display_name": ["Projected Out", "IR Player", "Inactive Roster", "Manual Out", "No Projection"],
        "position": ["WR", "WR", "WR", "RB", "TE"],
        "team": ["CAR", "CLE", "DEN", "PIT", "CHI"],
        "season": [2026] * 5, "week": [7] * 5,
        "kickoff": ["2026-10-25 13:00:00-04:00"] * 5,
        "injury_status": ["Out"] * 5,
        "reported_injury_status": ["Out", "IR", "Out", "Out", "Out"],
        "injury_status_source": [
            "sleeper_player_directory", "sleeper_player_directory",
            "sleeper_player_directory", "lineup_override", "sleeper_player_directory",
        ],
        "sleeper_roster_status": ["Active", "Active", "Inactive", "Active", "Active"],
        "sleeper_is_active": [True] * 5,
        "tuesday_sleeper_projection_signal": [True] * 5,
        "slp_proj": [8.5, 7.0, 6.0, 9.0, float("nan")],
    })
    shown = weekly.eligible_board_rows(frame, 2026, 7)

    assert set(shown.player_id.astype(str)) == {"projected-out"}


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
    # Postgame with a Finish rank: it follows Actual Pts and stays inside a 390px grid.
    assert page.PREVIEW_PHONE_RANK_COLUMNS == [
        "#", "Player", "Proj Pts", "Actual Pts", "Finish", "Opponent", "Health",
    ]
    inside_phone = ["#", "Player", "Proj Pts", "Actual Pts", "Finish"]
    assert sum(page._WF_PHONE_WIDTHS[column] for column in inside_phone) <= 358


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


def test_phone_column_config_preserves_desktop_help_and_formats():
    row_help = "Row number in this table as currently sorted and filtered."
    opponent_help = "The matchup label sorts alphabetically."
    desktop = {
        "#": st.column_config.NumberColumn("#", format="%d", help=row_help),
        "Player": st.column_config.TextColumn("Player", help="Player name and NFL team."),
        "Opponent": st.column_config.TextColumn("Opponent", help=opponent_help),
        "Proj Pts": st.column_config.NumberColumn("Proj Pts", format="%.1f"),
    }

    phone = weekly._phone_column_config(["#", "Player", "Opponent", "Proj Pts"], desktop)

    assert phone["#"]["help"] == row_help
    assert phone["#"]["type_config"]["format"] == "%d"
    assert phone["#"]["pinned"] is True
    assert phone["Player"]["help"] == "Player name and NFL team."
    assert phone["Player"]["pinned"] is True
    assert phone["Opponent"]["help"] == opponent_help
    assert phone["Proj Pts"]["type_config"]["format"] == "%.1f"


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


def _scorecard_shown(at):
    return any("How the rankings did" in str(item.value) for item in at.markdown)


def _rank_columns_shown(at):
    return any({"Our Rk", "Rk Δ"} & set(item.value.columns) for item in at.dataframe)


def test_postgame_rank_columns_follow_actual_pts_only_when_requested():
    assert ["#", *weekly._preview_table_columns("WR", False, True, actual_detail=False)] == [
        "#", "Player", "Opponent", "Proj Pts", "Actual Pts",
    ]
    assert ["#", *weekly._preview_table_columns(
        "WR", False, True, actual_detail=False, rank_columns=True,
    )] == ["#", "Player", "Opponent", "Proj Pts", "Actual Pts", "Our Rk", "Finish", "Rk Δ"]
    assert ["#", *weekly._preview_table_columns("RB", False, True, rank_columns=True)] == [
        "#", "Player", "Opponent", "Proj Pts", "Actual Pts", "Our Rk", "Finish", "Rk Δ",
        "Actual Rush Yds", "Actual Rec Yds",
    ]
    # The phone grid keeps Finish (right after Actual Pts) and drops Our Rk and Rk Δ, and
    # only when the table has Finish. Without it the phone list is unchanged.
    with_ranks = ["#", "Player", "Opponent", "Proj Pts", "Actual Pts", "Our Rk", "Finish", "Rk Δ"]
    assert weekly._preview_phone_columns(with_ranks, show_sleeper=False) == [
        "#", "Player", "Proj Pts", "Actual Pts", "Finish", "Opponent",
    ]
    assert weekly._preview_phone_columns(with_ranks[:5], show_sleeper=False) == [
        "#", "Player", "Opponent", "Proj Pts", "Actual Pts",
    ]
    assert weekly._WF_PHONE_WIDTHS["Finish"] == 52


def test_rank_delta_is_green_above_zero_red_below_and_plain_at_zero_or_missing():
    assert "#35D08A" in weekly._rank_delta_style(3)
    assert "#F08A8A" in weekly._rank_delta_style(-2)
    assert weekly._rank_delta_style(0) == ""
    assert weekly._rank_delta_style(pd.NA) == ""
    assert weekly._rank_delta_style(float("nan")) == ""


def test_graded_week_paths_use_the_latest_build_per_week_and_only_when_it_is_complete(
    tmp_path, monkeypatch,
):
    def build(season, week, build_id, published_at, complete=None):
        grading = {} if complete is None else {"complete": complete}
        return {
            "season": season, "week": week, "build_id": build_id,
            "published_at": published_at, "grading": grading,
        }

    builds = [
        build(2025, 17, "demo", "2026-08-21T00:00:00Z", True),
        build(2026, 1, "w1-old", "2026-09-08T00:00:00Z", True),
        build(2026, 1, "w1-new", "2026-09-09T00:00:00Z", False),  # newest revision is not graded
        build(2026, 2, "w2-old", "2026-09-15T00:00:00Z", False),
        build(2026, 2, "w2-new", "2026-09-16T00:00:00Z", True),
        build(2026, 3, "w3", "2026-09-22T00:00:00Z"),
    ]
    (tmp_path / "w2-new-graded.csv").write_text("player_id\n", encoding="utf-8")
    monkeypatch.setattr(weekly.page_common, "load_release_manifest", lambda: {})
    monkeypatch.setattr(weekly, "published_builds", lambda *args, **kwargs: builds)
    monkeypatch.setattr(
        weekly, "resolve_build_artifact",
        lambda item, **kwargs: tmp_path / f"{item['build_id']}-graded.csv",
    )

    assert weekly._graded_week_paths(2026) == ((2, str(tmp_path / "w2-new-graded.csv")),)
    assert weekly._graded_week_paths(2027) == ()


def test_season_accuracy_figure_plots_ours_and_sleeper_rank_correlation():
    rows = pd.DataFrame({
        "week": [2, 1, 3], "our_rho": [0.41, 0.30, 0.50], "slp_rho": [0.35, 0.45, 0.50],
    })

    fig = weekly._season_accuracy_figure(rows)

    assert [trace.name for trace in fig.data] == ["Ours", "Sleeper"]
    assert list(fig.data[0].x) == [1, 2, 3]
    assert list(fig.data[0].y) == [0.30, 0.41, 0.50]
    assert list(fig.data[1].y) == [0.45, 0.35, 0.50]
    # Level at the last week, so the two end labels are split above and below.
    assert {trace.textposition for trace in fig.data} == {"top right", "bottom right"}
    low, high = fig.layout.yaxis.range
    assert low <= 0.30 and high >= 0.50
    assert fig.layout.legend.orientation == "h"
    assert fig.layout.dragmode is False


def test_week06_graded_release_shows_ranking_scorecard_and_rank_columns(tmp_path):
    at = _render_weekly(tmp_path)
    at = next(w for w in at.selectbox if w.key == "wf_week").set_value(6).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    assert _scorecard_shown(at)
    assert {m.label: (m.value, m.delta) for m in at.metric} == {
        "Top-tier hits": ("39 of 72", "Sleeper 39 of 72"),
        "Average miss": ("5.02 pts", "Sleeper 5.35 pts"),
        "Rank correlation": ("0.34", "Sleeper 0.30"),
    }
    frames = [item.value for item in at.dataframe]
    scorecard = next(f for f in frames if {"Position", "Sleeper hits"} <= set(f.columns))
    assert scorecard["Position"].tolist() == ["QB", "RB", "WR", "TE", "All"]
    assert scorecard["Top-tier hits"].tolist() == [
        "7 of 12", "14 of 24", "13 of 24", "5 of 12", "39 of 72",
    ]
    assert scorecard["Sleeper hits"].tolist() == [
        "9 of 12", "15 of 24", "12 of 24", "3 of 12", "39 of 72",
    ]
    assert scorecard["Rank corr"].tolist() == [0.34, 0.48, 0.20, 0.37, 0.34]
    assert scorecard["Sleeper corr"].tolist() == [0.53, 0.42, 0.08, 0.26, 0.30]
    assert scorecard["Avg miss"].tolist() == [5.42, 5.02, 4.95, 4.78, 5.02]
    assert scorecard["Sleeper miss"].tolist() == [5.21, 5.45, 5.54, 4.97, 5.35]
    # The phone copy stacks ours and Sleeper's as two narrow rows per position.
    phone_card = next(f for f in frames if {"Position", "Who"} <= set(f.columns))
    assert phone_card["Position"].tolist() == [p for p in ("QB", "RB", "WR", "TE", "All") for _ in (0, 1)]
    assert phone_card["Who"].tolist() == ["Ours", "Sleeper"] * 5
    assert phone_card["Top-tier hits"].tolist()[:2] == ["7 of 12", "9 of 12"]
    assert phone_card["Rank corr"].tolist()[-2:] == [0.34, 0.30]
    assert phone_card["Avg miss"].tolist()[-2:] == [5.02, 5.35]

    # Season to date: one collapsed expander with a row for each graded week.
    assert [exp.label for exp in at.expander] == ["Season to date"]
    by_week = next(f for f in frames if {"Week", "Sleeper hits"} <= set(f.columns))
    assert by_week["Week"].tolist() == [1, 2, 3, 4, 5, 6]
    assert by_week["Top-tier hits"].tolist()[-1] == "39 of 72"
    # Phone copy: two rows a week, newest first, since the site caps phone tables at 26rem.
    phone_weeks = next(f for f in frames if {"Week", "Who"} <= set(f.columns))
    assert phone_weeks["Week"].tolist() == [w for w in (6, 5, 4, 3, 2, 1) for _ in (0, 1)]
    assert phone_weeks["Who"].tolist()[:2] == ["Ours", "Sleeper"]
    texts = [str(item.value) for item in at.markdown]
    assert (
        "We beat Sleeper on top-tier hits at 2 of 4 positions, "
        "on rank correlation at 3 of 4, and on average miss at 3 of 4."
    ) in texts
    assert (
        "Over 6 graded weeks we beat Sleeper on top-tier hits in 3, "
        "on rank correlation in 3, and on average miss in 4."
    ) in texts

    # Desktop grid: Our Rk, Finish and Rk Δ right after Actual Pts. Phone grid: Finish only.
    desktop = next(f for f in frames if "Rk Δ" in f.columns)
    phone = next(f for f in frames if "Finish" in f.columns and "Rk Δ" not in f.columns)
    columns = list(desktop.columns)
    assert columns[columns.index("Actual Pts") + 1:][:3] == ["Our Rk", "Finish", "Rk Δ"]
    assert list(phone.columns) == ["#", "Player", "Proj Pts", "Actual Pts", "Finish", "Opponent"]
    assert (desktop["Rk Δ"] == desktop["Our Rk"] - desktop["Finish"]).all()
    # Half-PPR default: the QB tab is sorted by the same projection that sets Our Rk.
    assert desktop["#"].tolist() == desktop["Our Rk"].tolist()
    assert desktop["Finish"].between(1, 28).all()


def test_rank_columns_sit_between_actual_pts_and_live_actual_yardage(tmp_path):
    h = tmp_path / "h_weekly_live_yardage.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_weekly_fantasy as p\n"
        "_live = p.load_actual_stats\n"
        "try:\n"
        "    p.load_actual_stats = lambda season, week: {\n"
        "        'qb_pass_yds': {'00-0034857': 250.0}, 'qb_rush_yds': {'00-0034857': 12.0},\n"
        "    }\n"
        "    p.render()\n"
        "finally:\n"
        "    p.load_actual_stats = _live\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    at = next(w for w in at.selectbox if w.key == "wf_week").set_value(6).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    frames = [item.value for item in at.dataframe]
    desktop = next(f for f in frames if "Rk Δ" in f.columns)
    phone = next(f for f in frames if "Finish" in f.columns and "Rk Δ" not in f.columns)
    assert list(desktop.columns) == [
        "#", "Player", "Opponent", "Proj Pts", "Actual Pts", "Our Rk", "Finish", "Rk Δ",
        "Actual Pass Yds", "Actual Rush Yds",
    ]
    assert list(phone.columns) == ["#", "Player", "Proj Pts", "Actual Pts", "Finish", "Opponent"]
    assert desktop.loc[desktop["Player"].str.startswith("Josh Allen"), "Actual Pass Yds"].iloc[0] == 250


def test_scorecard_ignores_the_scoring_toggle_and_new_copy_has_no_dashes(tmp_path):
    at = _render_weekly(tmp_path)
    at = next(w for w in at.selectbox if w.key == "wf_week").set_value(6).run()
    half_ppr = [(m.label, m.value, m.delta) for m in at.metric]

    at = next(w for w in at.segmented_control if w.key == "wf_scoring").set_value("PPR").run()

    assert not at.exception, at.exception
    assert [(m.label, m.value, m.delta) for m in at.metric] == half_ppr
    new_copy = [
        str(item.value) for item in list(at.caption) + list(at.markdown)
        if any(key in str(item.value) for key in (
            "Half-PPR points, whatever", "We beat Sleeper", "Rank correlation by week",
            "same definitions as the week scorecard", "How the rankings did",
        ))
    ]
    new_copy += [m.proto.help for m in at.metric] + [str(m.proto.label) for m in at.metric]
    assert len(new_copy) >= 9
    assert not [text for text in new_copy if "—" in text or "–" in text]


def test_ungraded_demo_and_unflagged_weeks_show_no_ranking_scorecard(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    # The same rows before any points settle: an ungraded 2026 week.
    ungraded = tmp_path / "projections_2026_week07.csv"
    pd.read_csv(graded).drop(
        columns=["actual_half_ppr", "projection_error", "absolute_error"]
    ).to_csv(ungraded, index=False)

    at = _render_weekly_release(tmp_path, ungraded, season=2026, week=7)
    assert not any("Results are in" in str(item.value) for item in at.success)
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert not at.expander

    demo = _HERE / "fantasy" / "fantasy_projections" / "projections_2025_week17.csv"
    at = _render_weekly_release(tmp_path, demo, season=2025, week=17)
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert not at.expander

    # Settled points without the release's complete-grade flag (no release state): no scorecard.
    at = _render_weekly_release(tmp_path, graded, season=2026, week=6)
    assert any("Results are in" in str(item.value) for item in at.success)
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert not at.expander


def _render_weekly_graded(tmp_path, projection_path, *, extra="", season=2026, week=6):
    """Render one release as if its grading were complete, with optional page patches."""
    h = tmp_path / "h_weekly_graded.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "from pathlib import Path\n"
        "import page_weekly_fantasy as p\n"
        "_saved = (p.available_projection_files, p.page_common.release_default_selection,\n"
        "          p.page_common.render_release_status, p._selected_build_details,\n"
        "          p.fantasy_accuracy.position_scorecard, p._season_accuracy_table)\n"
        "try:\n"
        f"    p.available_projection_files = lambda: {{({season}, {week}): Path(r'{projection_path}')}}\n"
        f"    p.page_common.release_default_selection = lambda *a, **k: ({season}, {week})\n"
        "    p.page_common.render_release_status = lambda *a, **k: {'build_id': 'stub'}\n"
        "    p._selected_build_details = lambda *a, **k: ({}, {'complete': True})\n"
        f"{extra}"
        "    p.render()\n"
        "finally:\n"
        "    (p.available_projection_files, p.page_common.release_default_selection,\n"
        "     p.page_common.render_release_status, p._selected_build_details,\n"
        "     p.fantasy_accuracy.position_scorecard, p._season_accuracy_table) = _saved\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


_ACCURACY_UNAVAILABLE = "Ranking accuracy is not available for this release."


def _board_still_shows_actual_points(at):
    return any("Actual Pts" in item.value.columns for item in at.dataframe)


def test_graded_release_missing_slp_proj_shows_one_line_and_keeps_the_board(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    broken = tmp_path / "projections_2026_week06.csv"
    pd.read_csv(graded).drop(columns=["slp_proj"]).to_csv(broken, index=False)

    at = _render_weekly_graded(tmp_path, broken)

    assert [item.value for item in at.info if "Ranking accuracy" in str(item.value)] == [
        _ACCURACY_UNAVAILABLE
    ]
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert not at.expander and not at.metric
    assert any("Results are in" in str(item.value) for item in at.success)
    assert _board_still_shows_actual_points(at)


def test_unexpected_error_in_the_week_scorecard_degrades_to_one_line(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    boom = (
        "    def _boom(*args, **kwargs):\n"
        "        raise RuntimeError('boom')\n"
        "    p.fantasy_accuracy.position_scorecard = _boom\n"
    )

    at = _render_weekly_graded(tmp_path, graded, extra=boom)

    assert [item.value for item in at.info if "Ranking accuracy" in str(item.value)] == [
        _ACCURACY_UNAVAILABLE
    ]
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert _board_still_shows_actual_points(at)


def test_unexpected_error_in_the_season_view_leaves_the_week_scorecard_intact(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    boom = (
        "    def _boom(*args, **kwargs):\n"
        "        raise OSError('graded file unreadable')\n"
        "    p._season_accuracy_table = _boom\n"
    )

    at = _render_weekly_graded(tmp_path, graded, extra=boom)

    assert _scorecard_shown(at) and _rank_columns_shown(at)
    assert [exp.label for exp in at.expander] == ["Season to date"]
    assert [item.value for item in at.info if "Season ranking" in str(item.value)] == [
        "Season ranking accuracy is not available right now."
    ]
    assert not any(_ACCURACY_UNAVAILABLE in str(item.value) for item in at.info)


def test_graded_release_with_nothing_to_score_shows_no_scorecard(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    frame = pd.read_csv(graded)
    frame["projected_pts"] = float("nan")
    unscorable = tmp_path / "projections_2026_week06.csv"
    frame.to_csv(unscorable, index=False)

    at = _render_weekly_graded(tmp_path, unscorable)

    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    assert not at.expander and not at.metric


def test_default_release_shows_the_scorecard_only_once_it_is_completely_graded(tmp_path):
    """The newest published week is ungraded until its games finish, then picks this up unaided."""
    import page_common

    season, week = page_common.release_default_selection("fantasy", (2025, 10))
    graded = weekly.available_projection_files()[(season, week)].name.endswith("-graded.csv")

    at = _render_weekly(tmp_path)

    assert _scorecard_shown(at) is graded
    assert _rank_columns_shown(at) is graded
    assert any(exp.label == "Season to date" for exp in at.expander) is graded


def _nflverse_schedule():
    """The real nflverse shape: a game_type column (REG, WC, ...) and no season_type."""
    return pd.DataFrame({
        "season": [2026, 2026, 2026, 2026, 2026],
        "game_type": ["REG", "REG", "REG", "REG", "WC"],
        "week": [1, 1, 2, 2, 1],
        "home_score": [24.0, 17.0, 21.0, None, None],
        "away_score": [20.0, 14.0, 10.0, None, None],
    })


def test_nflverse_game_type_schedule_marks_a_finished_week_complete():
    schedule = _nflverse_schedule()
    assert "season_type" not in schedule.columns

    # Week 1 also lists an unscored postseason-labeled game, which must not hold it back.
    assert weekly._week_is_complete(schedule, 2026, 1) is True
    # Week 2 has a regular-season game with no score yet.
    assert weekly._week_is_complete(schedule, 2026, 2) is False
    postseason_only = schedule.assign(game_type="WC")
    assert weekly._week_is_complete(postseason_only, 2026, 1) is False
    # Either column name works, and the frame itself is not modified.
    renamed = schedule.rename(columns={"game_type": "season_type"})
    assert weekly._week_is_complete(renamed, 2026, 1) is True
    assert "season_type" not in schedule.columns


def test_schedule_with_neither_type_column_degrades_to_not_complete():
    no_type = _nflverse_schedule().drop(columns=["game_type"])

    assert weekly._week_is_complete(no_type, 2026, 1) is False


def _fake_player_stats():
    return pd.DataFrame({
        "season_type": ["REG", "REG", "POST"],
        "week": [1, 1, 1],
        "position": ["QB", "WR", "QB"],
        "player_id": ["qb1", "wr1", "qb-post"],
        "passing_yards": [300.0, None, 400.0],
        "passing_tds": [2, None, 3],
        "passing_interceptions": [1, None, 0],
        "rushing_yards": [10.0, None, 0.0],
        "rushing_tds": [0, None, 0],
        "receptions": [None, 6, None],
        "receiving_yards": [None, 80.0, None],
        "receiving_tds": [None, 1, None],
        "rushing_fumbles_lost": [0, None, 0],
        "receiving_fumbles_lost": [None, 0, None],
    })


def _live_feed(monkeypatch, schedule):
    """Point load_actual_stats at fake nflverse frames, with no network and clean caches."""
    import nflreadpy

    weekly._load_schedule_season.clear()
    weekly._load_actual_stats_season.clear()
    monkeypatch.setattr(weekly, "_OFFLINE", False)
    monkeypatch.setattr(nflreadpy, "load_schedules", lambda seasons: schedule)
    monkeypatch.setattr(nflreadpy, "load_player_stats", lambda seasons: _fake_player_stats())


def test_live_actuals_turn_on_once_every_game_in_the_week_has_a_score(monkeypatch):
    try:
        _live_feed(monkeypatch, _nflverse_schedule())

        done = weekly.load_actual_stats(2026, 1)
        # QB: 12 pass yds pts + 8 TD - 2 INT + 1 rush yds pts. WR: 3 reception pts + 8 + 6 TD.
        assert {k: round(v, 6) for k, v in done["half_ppr"].items()} == {"qb1": 19.0, "wr1": 17.0}
        assert done["qb_pass_yds"] == {"qb1": 300.0}
        assert done["wr_recs"] == {"wr1": 6.0}
        # Week 2 still has an unscored game: no live actuals yet.
        assert weekly.load_actual_stats(2026, 2) == {}
    finally:
        weekly._load_schedule_season.clear()
        weekly._load_actual_stats_season.clear()


def test_live_actuals_stay_off_when_the_schedule_has_no_type_column(monkeypatch):
    try:
        _live_feed(monkeypatch, _nflverse_schedule().drop(columns=["game_type"]))

        assert weekly.load_actual_stats(2026, 1) == {}
    finally:
        weekly._load_schedule_season.clear()
        weekly._load_actual_stats_season.clear()


def _render_demo_week_with_live_actuals(tmp_path, week):
    """Run the real page on a 2025 demo week with the live feed returning a score for everyone."""
    csv = _HERE / "fantasy" / "fantasy_projections" / f"projections_2025_week{week}.csv"
    h = tmp_path / f"h_demo_actuals_{week}.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import pandas as pd\n"
        "import page_weekly_fantasy as p\n"
        f"_ids = pd.read_csv(r'{csv}')['player_id'].astype(str).tolist()\n"
        "_live = p.load_actual_stats\n"
        "try:\n"
        "    p.load_actual_stats = lambda season, week: {'half_ppr': {i: 12.5 for i in _ids}}\n"
        "    p.render()\n"
        "finally:\n"
        "    p.load_actual_stats = _live\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    at = next(w for w in at.selectbox if w.key == "wf_season").set_value(2025).run()
    at = next(w for w in at.selectbox if w.key == "wf_week").set_value(week).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def test_demo_week_with_live_actuals_keeps_actual_pts_inside_the_phone_grid(tmp_path):
    at = _render_demo_week_with_live_actuals(tmp_path, 10)

    assert any("Results are in" in str(item.value) for item in at.success)
    assert not _scorecard_shown(at) and not _rank_columns_shown(at)
    frames = [item.value for item in at.dataframe if "Player" in item.value.columns]
    desktop = next(f for f in frames if "Off EPA" in f.columns)
    phone = next(f for f in frames if "Off EPA" not in f.columns)
    assert desktop["Actual Pts"].eq(12.5).all()
    assert list(phone.columns) == weekly.LEGACY_PHONE_COLUMNS
    # Without actuals the phone grid is unchanged: Health follows Proj Pts as before.
    assert weekly.LEGACY_PHONE_COLUMNS == ["#", "Player", "Opponent", "Proj Pts", "Actual Pts", "Health"]


def test_demo_week_with_live_actuals_leaves_the_frozen_csvs_untouched(tmp_path):
    folder = _HERE / "fantasy" / "fantasy_projections"
    before = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in folder.glob("projections_2025_week*.csv")}

    _render_demo_week_with_live_actuals(tmp_path, 17)

    after = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in folder.glob("projections_2025_week*.csv")}
    assert after == before == DEMO_MD5


def test_standard_scoring_actual_pts_are_filled_when_the_live_feed_supplies_receptions(tmp_path):
    graded = weekly.available_projection_files()[(2026, 6)]
    h = tmp_path / "h_standard_actuals.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import pandas as pd\n"
        "import page_weekly_fantasy as p\n"
        f"_ids = pd.read_csv(r'{graded}')['player_id'].astype(str).tolist()\n"
        "_live = p.load_actual_stats\n"
        "try:\n"
        "    p.load_actual_stats = lambda season, week: {\n"
        "        key: {i: 3.0 for i in _ids} for key in ('qb_recs', 'rb_recs', 'wr_recs', 'te_recs')}\n"
        "    p.render()\n"
        "finally:\n"
        "    p.load_actual_stats = _live\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    at = next(w for w in at.selectbox if w.key == "wf_week").set_value(6).run()
    half = next(f.value for f in at.dataframe if "Rk Δ" in f.value.columns)
    at = next(w for w in at.segmented_control if w.key == "wf_scoring").set_value("Standard").run()
    assert not at.exception, at.exception
    standard = next(f.value for f in at.dataframe if "Rk Δ" in f.value.columns)

    # Standard drops the half point per reception: 3 receptions each is 1.5 fewer points.
    assert standard["Actual Pts"].notna().all()
    assert (half["Actual Pts"] - standard["Actual Pts"]).round(1).eq(1.5).all()
