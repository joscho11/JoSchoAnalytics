"""Release safety: validation, immutable activation, rollback, status, and grading."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from publishing.candidate import build_candidate_metadata
from publishing.contract import PublicationError, sha256_file
from publishing.grader import grade_anytime_td_file, grade_fantasy, grade_predictions
from publishing.manifest import (
    default_selection,
    load_manifest,
    release_status,
    track_record_default_season,
)
from publishing.publisher import publish_candidate, rollback_release, schedule_release
from publishing.validators import validate_candidate
from dashboard_data import overlay_published_predictions
from publishing.cli import _grade_published


def _prediction_candidate(tmp_path: Path, *, shift: float = 0.0, week: int = 1):
    artifact = tmp_path / f"predictions-w{week}-{shift}.csv"
    first_day, second_day = (9, 10) if week == 1 else (16, 17)
    rows = pd.DataFrame([
        {
            "game_id": f"2026_{week:02d}_NE_SEA", "home_team": "SEA", "away_team": "NE",
            "season": 2026, "week": week, "gameday": f"2026-09-{first_day:02d}", "gametime": "20:20",
            "predicted_margin": 4.0 + shift, "model_edge": 0.5 + shift,
            "recommendation": "HOME (SEA)", "logged_at": "2026-09-08T13:00:00Z",
            "tuesday_spread_line": 3.0, "tuesday_spread_book": "DraftKings",
            "tuesday_spread_price": -110, "tuesday_median_spread_line": 3.5,
            "consensus_tier": "",
        },
        {
            "game_id": f"2026_{week:02d}_SF_LA", "home_team": "LA", "away_team": "SF",
            "season": 2026, "week": week, "gameday": f"2026-09-{second_day:02d}", "gametime": "20:35",
            "predicted_margin": -1.5 + shift, "model_edge": -3.0 + shift,
            "recommendation": "AWAY (SF)", "logged_at": "2026-09-08T13:00:00Z",
            "tuesday_spread_line": 2.0, "tuesday_spread_book": "BetRivers",
            "tuesday_spread_price": -108, "tuesday_median_spread_line": 1.5,
            "consensus_tier": "HIGH" if shift <= 0 else "",
        },
    ])
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=week,
        model_version=f"spread-v3-test-{shift}", produced_at="2026-09-08T13:00:00Z",
    )
    schedule = pd.DataFrame([
        {"game_id": f"2026_{week:02d}_NE_SEA", "home_team": "SEA", "away_team": "NE",
         "season": 2026, "week": week, "game_type": "REG", "gameday": f"2026-09-{first_day:02d}", "gametime": "20:20"},
        {"game_id": f"2026_{week:02d}_SF_LA", "home_team": "LA", "away_team": "SF",
         "season": 2026, "week": week, "game_type": "REG", "gameday": f"2026-09-{second_day:02d}", "gametime": "20:35"},
    ])
    return artifact, metadata, schedule


def _fantasy_candidate(tmp_path: Path):
    artifact = tmp_path / "fantasy.csv"
    counts = {"QB": 24, "RB": 60, "WR": 72, "TE": 24}
    rows = []
    teams = [("SEA", "NE"), ("NE", "SEA")]
    for position, count in counts.items():
        for index in range(count):
            team, opponent = teams[index % 2]
            rows.append({
                "player_id": f"{position}-{index}",
                "player_display_name": f"{position} Player {index}",
                "position": position,
                "team": team,
                "opponent_team": opponent,
                "season": 2026,
                "week": 1,
                "projected_pts": float(index) / 10,
            })
    pd.DataFrame(rows).to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "fantasy", artifact, season=2026, week=1,
        model_version="weekly-fantasy-test", produced_at="2026-09-08T13:00:00Z",
    )
    schedule = pd.DataFrame([{
        "game_id": "2026_01_NE_SEA", "home_team": "SEA", "away_team": "NE",
        "season": 2026, "week": 1, "game_type": "REG",
        "gameday": "2026-09-09", "gametime": "20:20",
    }])
    return artifact, metadata, schedule


def test_text_artifact_hash_is_stable_across_git_line_endings(tmp_path):
    lf = tmp_path / "release-lf.csv"
    crlf = tmp_path / "release-crlf.csv"
    lf.write_bytes(b"game_id,week\n2026_01_NE_SEA,1\n")
    crlf_payload = b"game_id,week\r\n2026_01_NE_SEA,1\r\n"
    crlf.write_bytes(crlf_payload)

    expected = hashlib.sha256(crlf_payload).hexdigest()
    assert sha256_file(lf) == expected
    assert sha256_file(crlf) == expected


def test_published_release_survives_git_line_ending_normalization(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    build = publish_candidate(artifact, metadata, schedule=schedule, root=site)
    stored = site / build["artifact"]
    stored.write_bytes(stored.read_bytes().replace(b"\r\n", b"\n"))

    status = release_status("predictions", 2026, 1, root=site)
    assert status["status"] == "Published"


def test_prediction_contract_detects_duplicates_and_schedule_gaps(tmp_path):
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    assert validate_candidate(artifact, metadata, schedule=schedule).ok
    bad = pd.read_csv(artifact)
    bad.loc[1, "game_id"] = bad.loc[0, "game_id"]
    bad.to_csv(artifact, index=False)
    metadata["artifact_sha256"] = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-test", produced_at="2026-09-08T13:00:00Z",
    )["artifact_sha256"]
    report = validate_candidate(artifact, metadata, schedule=schedule)
    assert not report.ok
    assert any("duplicate game_id" in error for error in report.errors)
    assert any("schedule coverage mismatch" in error for error in report.errors)


def test_public_prediction_contract_rejects_gameday_mode(tmp_path):
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows["mode"] = "gameday"
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-gameday-test", produced_at="2026-09-08T13:00:00Z",
    )
    report = validate_candidate(artifact, metadata, schedule=schedule)
    assert not report.ok
    assert any("gameday spread rows" in error for error in report.errors)


def test_live_prediction_contract_requires_and_checks_shopped_quote(tmp_path):
    artifact, _, schedule = _prediction_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows = rows.drop(columns=["tuesday_spread_book"])
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-test", produced_at="2026-09-08T13:00:00Z",
    )
    missing = validate_candidate(artifact, metadata, schedule=schedule)
    assert not missing.ok
    assert any("missing shopped-line fields" in error for error in missing.errors)

    artifact, _, schedule = _prediction_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows.loc[0, "tuesday_median_spread_line"] = 2.5
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-test", produced_at="2026-09-08T13:00:00Z",
    )
    worse = validate_candidate(artifact, metadata, schedule=schedule)
    assert not worse.ok
    assert any("worse than the US median" in error for error in worse.errors)


def test_live_prediction_contract_rejects_shopped_triggered_high(tmp_path):
    artifact, _, schedule = _prediction_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows.loc[0, "predicted_margin"] = 5.7
    rows.loc[0, "model_edge"] = 2.2
    rows.loc[0, "consensus_tier"] = "HIGH"
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-shop-trigger-test", produced_at="2026-09-08T13:00:00Z",
    )
    report = validate_candidate(artifact, metadata, schedule=schedule)
    assert not report.ok
    assert any("Tuesday-median edge" in error for error in report.errors)


def test_live_prediction_timestamp_must_be_timezone_aware(tmp_path):
    artifact, _, schedule = _prediction_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows["logged_at"] = "2026-09-08 13:00:00"
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-test", produced_at="2026-09-08T13:00:01Z",
    )
    report = validate_candidate(artifact, metadata, schedule=schedule)
    assert not report.ok
    assert any("logged_at must be timezone-aware" in error for error in report.errors)


def test_fantasy_contract_checks_identity_position_and_schedule_coverage(tmp_path):
    artifact, metadata, schedule = _fantasy_candidate(tmp_path)
    report = validate_candidate(artifact, metadata, schedule=schedule)
    assert report.ok, report.errors
    assert report.row_count == 180
    assert report.checks["scheduled_teams"] == 2
    rows = pd.read_csv(artifact)
    rows.loc[(rows["position"] == "QB") & (rows["team"] == "NE"), ["team", "opponent_team"]] = [
        "SEA", "NE"
    ]
    rows.to_csv(artifact, index=False)
    missing_players_meta = build_candidate_metadata(
        "fantasy", artifact, season=2026, week=1,
        model_version="weekly-fantasy-test", produced_at="2026-09-08T13:00:00Z",
    )
    missing = validate_candidate(artifact, missing_players_meta, schedule=schedule)
    assert not missing.ok
    assert any("lack projected skill-position players" in error for error in missing.errors)


def test_publish_is_immutable_and_failed_candidate_does_not_move_pointer(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    first = publish_candidate(artifact, metadata, schedule=schedule, root=site)
    assert default_selection("predictions", (2025, 10), root=site) == (2026, 1)
    stored = site / first["artifact"]
    original = stored.read_bytes()

    invalid = pd.read_csv(artifact).iloc[:1]
    invalid.to_csv(artifact, index=False)
    bad_meta = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="bad", produced_at="2026-09-08T13:00:00Z",
    )
    with pytest.raises(PublicationError):
        publish_candidate(artifact, bad_meta, schedule=schedule, root=site)
    manifest = load_manifest(site)
    assert manifest["products"]["predictions"]["active_build"] == first["build_id"]
    assert stored.read_bytes() == original


def test_same_artifact_cannot_change_immutable_release_metadata(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    publish_candidate(artifact, metadata, schedule=schedule, root=site)
    changed = dict(metadata)
    changed["model_version"] = "different-model-version"
    with pytest.raises(PublicationError, match="immutable metadata collision"):
        publish_candidate(artifact, changed, schedule=schedule, root=site)


def test_later_prediction_release_cannot_promote_new_high(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    publish_candidate(artifact, metadata, schedule=schedule, root=site)

    rows = pd.read_csv(artifact)
    rows.loc[0, "predicted_margin"] = 6.5
    rows.loc[0, "model_edge"] = 3.0
    rows.loc[0, "consensus_tier"] = "HIGH"
    rows.to_csv(artifact, index=False)
    promoted = build_candidate_metadata(
        "predictions", artifact, season=2026, week=1,
        model_version="spread-v3-promoted", produced_at="2026-09-08T13:05:00Z",
    )
    with pytest.raises(PublicationError, match="cannot promote new HIGH"):
        publish_candidate(artifact, promoted, schedule=schedule, root=site)


def test_audited_correction_can_promote_high_without_changing_tuesday_lines(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    original = publish_candidate(artifact, metadata, schedule=schedule, root=site)

    rows = pd.read_csv(artifact)
    rows.loc[0, "predicted_margin"] = 6.5
    rows.loc[0, "model_edge"] = 3.0
    rows.loc[0, "consensus_tier"] = "HIGH"
    rows.to_csv(artifact, index=False)
    corrected = build_candidate_metadata(
        "predictions",
        artifact,
        season=2026,
        week=1,
        model_version=metadata["model_version"],
        produced_at="2026-09-11T13:05:00Z",
    )
    corrected["correction"] = {
        "supersedes_build_id": original["build_id"],
        "reason": "Correct the Week 1 team-state construction.",
        "source_snapshot_captured_at": "2026-09-08T11:23:16-04:00",
        "source_snapshot_sha256": "a" * 64,
    }
    entry = publish_candidate(artifact, corrected, schedule=schedule, root=site)
    assert entry["status"] == "Published"
    assert entry["correction"] == corrected["correction"]
    assert entry["validation"]["checks"]["post_kickoff_correction"] is True
    assert load_manifest(site)["products"]["predictions"]["active_build"] == entry["build_id"]
    status = release_status("predictions", 2026, 1, root=site)
    assert status["status"] == "Published"

    retried = publish_candidate(artifact, corrected, schedule=schedule, root=site)
    assert retried["build_id"] == entry["build_id"]
    assert load_manifest(site)["products"]["predictions"]["previous_build"] == original["build_id"]


def test_audited_model_update_can_promote_high_without_changing_tuesday_lines(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    original = publish_candidate(artifact, metadata, schedule=schedule, root=site)

    rows = pd.read_csv(artifact)
    rows.loc[0, "predicted_margin"] = 6.5
    rows.loc[0, "model_edge"] = 3.0
    rows.loc[0, "consensus_tier"] = "HIGH"
    rows.to_csv(artifact, index=False)
    updated = build_candidate_metadata(
        "predictions",
        artifact,
        season=2026,
        week=1,
        model_version="spread-v3-clean-ridge",
        produced_at="2026-09-11T13:05:00Z",
    )
    updated["correction"] = {
        "supersedes_build_id": original["build_id"],
        "reason": "Promote the validated causal-cleanup model.",
        "source_snapshot_captured_at": "2026-09-08T11:23:16-04:00",
        "source_snapshot_sha256": "a" * 64,
        "model_update": True,
    }
    entry = publish_candidate(artifact, updated, schedule=schedule, root=site)
    assert entry["status"] == "Published"
    assert entry["correction"]["model_update"] is True
    assert entry["validation"]["checks"]["post_kickoff_correction"] is True
    assert load_manifest(site)["products"]["predictions"]["active_build"] == entry["build_id"]


def test_correction_cannot_change_frozen_tuesday_lines(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    original = publish_candidate(artifact, metadata, schedule=schedule, root=site)
    rows = pd.read_csv(artifact)
    rows.loc[0, "tuesday_median_spread_line"] = 4.0
    rows.loc[0, "model_edge"] = rows.loc[0, "predicted_margin"] - 4.0
    rows.to_csv(artifact, index=False)
    corrected = build_candidate_metadata(
        "predictions",
        artifact,
        season=2026,
        week=1,
        model_version=metadata["model_version"],
        produced_at="2026-09-11T13:05:00Z",
    )
    corrected["correction"] = {
        "supersedes_build_id": original["build_id"],
        "reason": "Correction with a changed line must fail.",
        "source_snapshot_captured_at": "2026-09-08T11:23:16-04:00",
        "source_snapshot_sha256": "a" * 64,
    }
    with pytest.raises(PublicationError, match="changed the frozen Tuesday median"):
        publish_candidate(artifact, corrected, schedule=schedule, root=site)


def test_pointer_only_rollback_and_release_status(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    first_artifact, first_meta, schedule = _prediction_candidate(tmp_path, shift=0.0)
    first = publish_candidate(first_artifact, first_meta, schedule=schedule, root=site)
    assert first["status"] == "Published"
    second_artifact, second_meta, schedule = _prediction_candidate(tmp_path, shift=0.5)
    second = publish_candidate(second_artifact, second_meta, schedule=schedule, root=site)
    assert first["build_id"] != second["build_id"]
    rolled = rollback_release("predictions", root=site)
    assert rolled["build_id"] == first["build_id"]
    status = release_status("predictions", 2026, 1, root=site)
    assert status["status"] == "Published"

    schedule_release(
        "fantasy", 2026, 1, scheduled_for="2026-09-08T13:00:00Z", root=site
    )
    manifest = load_manifest(site)
    assert manifest["products"]["fantasy"]["next_release"]["status"] == "Scheduled"
    scheduled = release_status(
        "fantasy", 2026, 1, root=site,
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert scheduled["status"] == "Scheduled"
    awaiting = release_status(
        "fantasy", 2026, 1, root=site,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    assert awaiting["status"] == "Awaiting projections"


def test_prediction_grader_is_separate_idempotent_and_enables_2026_record(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _prediction_candidate(tmp_path)
    build = publish_candidate(artifact, metadata, schedule=schedule, root=site)
    frozen = (site / build["artifact"]).read_bytes()
    finals = schedule.copy()
    finals["home_score"] = [27, 24]
    finals["away_score"] = [20, 22]
    first = grade_predictions(2026, 1, finals, root=site)
    second = grade_predictions(2026, 1, finals, root=site)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["graded_at"] == second["graded_at"]
    assert first["final_games"] == 2
    assert first["graded_rows"] == 1
    assert first["pushes"] == 1
    assert (site / build["artifact"]).read_bytes() == frozen
    assert track_record_default_season(root=site) == 2026


def test_fantasy_grading_is_separate_and_zero_fills_only_complete_feed(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _fantasy_candidate(tmp_path)
    build = publish_candidate(artifact, metadata, schedule=schedule, root=site)
    frozen = (site / build["artifact"]).read_bytes()
    finals = schedule.assign(home_score=27, away_score=20)
    actuals = pd.DataFrame([
        {"player_id": "QB-0", "team": "SEA", "actual_half_ppr": 18.5},
        {"player_id": "QB-1", "team": "NE", "actual_half_ppr": 14.0},
    ])
    first = grade_fantasy(2026, 1, actuals, schedule=finals, root=site)
    second = grade_fantasy(2026, 1, actuals, schedule=finals, root=site)
    assert first["complete"] is True
    assert first["graded_rows"] == 180
    assert first["zero_filled_after_complete_feed"] is True
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["graded_at"] == second["graded_at"]
    assert (site / build["artifact"]).read_bytes() == frozen


def test_fantasy_grading_reconciles_gsis_alias_for_synthetic_serving_id(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    artifact, metadata, schedule = _fantasy_candidate(tmp_path)
    rows = pd.read_csv(artifact)
    rows["sleeper_id"] = rows["player_id"].str.replace("QB-0", "123", regex=False)
    rows["gsis_id"] = ""
    rows.loc[rows["player_id"].eq("QB-0"), "player_id"] = "sleeper:123"
    rows.to_csv(artifact, index=False)
    metadata = build_candidate_metadata(
        "fantasy", artifact, season=2026, week=1,
        model_version="weekly-fantasy-alias-test", produced_at="2026-09-08T13:00:00Z",
    )
    publish_candidate(artifact, metadata, schedule=schedule, root=site)
    actuals = pd.DataFrame([{"gsis_id": "123", "team": "SEA", "actual_half_ppr": 7.0}])
    result = grade_fantasy(2026, 1, actuals, root=site)
    assert result["graded_rows"] == 1


def test_dashboard_overlay_retains_prior_week_after_next_week_activates(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    week1_artifact, week1_meta, week1_schedule = _prediction_candidate(tmp_path, week=1)
    publish_candidate(week1_artifact, week1_meta, schedule=week1_schedule, root=site)
    week2_artifact, week2_meta, week2_schedule = _prediction_candidate(tmp_path, week=2)
    publish_candidate(week2_artifact, week2_meta, schedule=week2_schedule, root=site)
    tracker = pd.DataFrame([{
        "game_id": "2025_17_HIST", "season": 2025, "week": 17,
        "home_team": "H", "away_team": "A",
    }])
    overlaid = overlay_published_predictions(tracker, site)
    assert len(overlaid) == 5
    assert set(overlaid.loc[overlaid["season"].eq(2026), "week"].astype(int)) == {1, 2}
    assert "2025_17_HIST" in set(overlaid["game_id"].astype(str))


def test_scheduled_grader_catches_incomplete_prior_published_weeks(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    schedules = []
    for week in (1, 2):
        artifact, metadata, schedule = _prediction_candidate(tmp_path, week=week)
        publish_candidate(artifact, metadata, schedule=schedule, root=site)
        schedules.append(schedule.assign(home_score=[27, 24], away_score=[20, 22]))
    full_schedule = pd.concat(schedules, ignore_index=True)
    monkeypatch.setattr(
        "publishing.cli.fetch_nfl_schedule", lambda season: full_schedule.copy()
    )
    result = _grade_published(site, "predictions")
    assert set(result["predictions"]) == {"2026w01", "2026w02"}
    assert result["predictions"]["2026w01"]["final_games"] == 2
    assert result["predictions"]["2026w02"]["final_games"] == 2


def _anytime_board(tmp_path: Path) -> Path:
    path = tmp_path / "anytime_td_2026_week01.csv"
    pd.DataFrame([
        {
            "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
            "player_id": "SEA-RB", "player_display_name": "Sea RB", "team": "SEA",
            "opponent_team": "NE", "p_ge1": 0.40, "p_book": 0.30,
            "p_ge2": 0.20, "two_plus_amer": 400,
            "scored_anytime": None, "status": "pregame",
        },
        {
            "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
            "player_id": "NE-RB", "player_display_name": "Ne RB", "team": "NE",
            "opponent_team": "SEA", "p_ge1": 0.35, "p_book": 0.30,
            "p_ge2": 0.15, "two_plus_amer": 566,
            "scored_anytime": None, "status": "pregame",
        },
        {
            "season": 2026, "week": 1, "game_id": "2026_01_SF_LA",
            "player_id": "SF-RB", "player_display_name": "Sf RB", "team": "SF",
            "opponent_team": "LA", "p_ge1": 0.30, "p_book": 0.25,
            "p_ge2": 0.10, "two_plus_amer": 900,
            "scored_anytime": None, "status": "pregame",
        },
    ]).to_csv(path, index=False)
    return path


def test_anytime_td_grading_updates_final_games_and_leaves_partial_slate_pending(tmp_path):
    path = _anytime_board(tmp_path)
    schedule = pd.DataFrame([
        {
            "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
            "home_team": "SEA", "away_team": "NE", "home_score": 27, "away_score": 20,
        },
        {
            "season": 2026, "week": 1, "game_id": "2026_01_SF_LA",
            "home_team": "LA", "away_team": "SF", "home_score": None, "away_score": None,
        },
    ])
    actuals = pd.DataFrame([
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "SEA-RB",
            "team": "SEA", "rushing_tds": 2, "receiving_tds": 0, "offense_snaps": 55,
        },
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "NE-RB",
            "team": "NE", "rushing_tds": 0, "receiving_tds": 0, "offense_snaps": 0,
        },
    ])

    first = grade_anytime_td_file(path, schedule, actuals, season=2026, week=1)
    assert first["status"] == "graded"
    assert first["final_games"] == 1
    assert first["updated_games"] == ["2026_01_NE_SEA"]
    assert first["pending_games"] == ["2026_01_SF_LA"]
    graded = pd.read_csv(path)
    assert list(graded.loc[graded.game_id.eq("2026_01_NE_SEA"), "scored_anytime"]) == [1, 0]
    assert list(graded.loc[graded.game_id.eq("2026_01_NE_SEA"), "scored_two_plus"]) == [1, 0]
    assert graded.loc[graded.game_id.eq("2026_01_NE_SEA"), "status"].eq("final").all()
    assert pd.isna(graded.loc[graded.game_id.eq("2026_01_SF_LA"), "scored_anytime"]).all()

    second = grade_anytime_td_file(path, schedule, actuals, season=2026, week=1)
    assert second["changed"] is False


def test_anytime_td_grading_does_not_zero_fill_an_incomplete_feed(tmp_path):
    path = _anytime_board(tmp_path)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
        "home_team": "SEA", "away_team": "NE", "home_score": 27, "away_score": 20,
    }])
    actuals = pd.DataFrame([{
        "season": 2026, "week": 1, "season_type": "REG", "player_id": "SEA-RB",
        "team": "SEA", "rushing_tds": 1, "receiving_tds": 0,
    }])

    result = grade_anytime_td_file(path, schedule, actuals, season=2026, week=1)
    assert result["status"] == "pending"
    assert result["changed"] is False
    assert result["graded_rows"] == 0
    assert pd.read_csv(path)["scored_anytime"].isna().all()


def test_anytime_td_grading_voids_zero_snap_dnp_instead_of_false_loss(tmp_path):
    path = _anytime_board(tmp_path)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
        "home_team": "SEA", "away_team": "NE", "home_score": 27, "away_score": 20,
    }])
    actuals = pd.DataFrame([
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "SEA-RB",
            "team": "SEA", "rushing_tds": 1, "receiving_tds": 0,
        },
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "NE-COVERAGE",
            "team": "NE", "rushing_tds": 0, "receiving_tds": 0,
        },
    ])
    participation = pd.DataFrame([
        {"season": 2026, "week": 1, "player_id": "SEA-RB", "team": "SEA", "offense_snaps": 44},
        {"season": 2026, "week": 1, "player_id": "NE-RB", "team": "NE", "offense_snaps": 0},
    ])

    result = grade_anytime_td_file(
        path, schedule, actuals, participation=participation, season=2026, week=1
    )
    graded = pd.read_csv(path)
    # The fixture deliberately retains an unrelated pending SF game; the
    # completed NE-SEA game is nevertheless fully resolved with one void.
    assert result["final_games"] == 1
    assert result["void_rows"] == 1
    assert list(graded.loc[graded.player_id.eq("SEA-RB"), "scored_anytime"]) == [1]
    assert pd.isna(graded.loc[graded.player_id.eq("NE-RB"), "scored_anytime"]).all()
    assert graded.loc[graded.player_id.eq("NE-RB"), "status"].eq("void").all()


def test_anytime_td_grading_matches_player_name_when_feed_id_differs(tmp_path):
    path = _anytime_board(tmp_path)
    schedule = pd.DataFrame([{
        "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
        "home_team": "SEA", "away_team": "NE", "home_score": 27, "away_score": 20,
    }])
    actuals = pd.DataFrame([
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "00-0041395",
            "player_display_name": "Sea RB", "team": "SEA", "rushing_tds": 0, "receiving_tds": 1,
            "offense_snaps": 41,
        },
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "00-0041396",
            "player_display_name": "Ne RB", "team": "NE", "rushing_tds": 0, "receiving_tds": 0,
            "offense_snaps": 32,
        },
    ])

    result = grade_anytime_td_file(path, schedule, actuals, season=2026, week=1)

    assert result["status"] == "graded"
    graded = pd.read_csv(path)
    assert list(graded.loc[graded.game_id.eq("2026_01_NE_SEA"), "scored_anytime"]) == [1, 0]


def test_scheduled_grader_dispatches_anytime_td(monkeypatch, tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    expected = {"status": "skipped", "reason": "test"}
    monkeypatch.setattr("publishing.cli.grade_anytime_td_releases", lambda root: expected)

    result = _grade_published(site, "anytime_td")
    assert result["anytime_td"] == expected


def test_scheduled_grader_dispatches_first_td(monkeypatch, tmp_path):
    """grade_first_td_releases was defined but never wired into the CLI dispatch;
    the live board's scored_first column went ungraded as a result. Regression
    coverage for that gap, not just the anytime_td half of the same bucket."""
    site = tmp_path / "site"
    site.mkdir()
    expected_anytime = {"status": "skipped", "reason": "test-anytime"}
    expected_first = {"status": "skipped", "reason": "test-first"}
    monkeypatch.setattr("publishing.cli.grade_anytime_td_releases", lambda root: expected_anytime)
    monkeypatch.setattr("publishing.cli.grade_first_td_releases", lambda root: expected_first)

    result = _grade_published(site, "anytime_td")
    assert result["anytime_td"] == expected_anytime
    assert result["first_td"] == expected_first


def test_anytime_td_grading_handles_the_real_publisher_schema_end_to_end(tmp_path):
    """Every other grading test here uses a hand-trimmed board missing most
    of td_count_model_beta.live_publish.SITE_COLUMNS (lambda, fair_amer,
    bet_eligible, eligibility_reason, ...). This uses the REAL column set so
    a real cold-start row (bet_eligible=False) is proven to grade correctly
    -- neither crashing on the extra columns nor letting eligibility fields
    leak into the outcome. This is the seam between td_count_model_beta's
    real publish output and JoSchoAnalytics's real grader."""
    site_columns = (
        "season", "week", "player_id", "player_display_name", "position", "team",
        "opponent_team", "game_id", "kickoff_et", "snapped_at_et", "book",
        "book_amer", "first_amer", "two_plus_amer", "p_book", "lambda", "p_ge1", "p_ge2", "fair_amer",
        "scored_anytime", "scored_two_plus", "status", "slate",
        "identity_source", "l4w_games_available", "forward_history_missing",
        "bet_eligible", "eligibility_reason",
    )
    rows = [
        {
            "season": 2026, "week": 1, "player_id": "SEA-RB", "player_display_name": "Sea RB",
            "position": "RB", "team": "SEA", "opponent_team": "NE", "game_id": "2026_01_NE_SEA",
            "kickoff_et": "2026-09-10 20:20", "snapped_at_et": "2026-09-10 17:20",
            "book": "DraftKings", "book_amer": 150, "first_amer": None, "two_plus_amer": 400,
            "p_book": 0.30, "lambda": 0.55, "p_ge1": 0.40, "p_ge2": 0.20, "fair_amer": 150,
            "scored_anytime": None, "scored_two_plus": None, "status": "pregame", "slate": "test",
            "identity_source": "gsis", "l4w_games_available": 4, "forward_history_missing": False,
            "bet_eligible": True, "eligibility_reason": "",
        },
        {
            "season": 2026, "week": 1, "player_id": "sleeper:rookie", "player_display_name": "Rookie Nobody",
            "position": "WR", "team": "SEA", "opponent_team": "NE", "game_id": "2026_01_NE_SEA",
            "kickoff_et": "2026-09-10 20:20", "snapped_at_et": "2026-09-10 17:20",
            "book": "DraftKings", "book_amer": None, "first_amer": None, "two_plus_amer": None,
            "p_book": None, "lambda": 0.10, "p_ge1": 0.09, "p_ge2": 0.01, "fair_amer": 1000,
            "scored_anytime": None, "scored_two_plus": None, "status": "pregame", "slate": "test",
            "identity_source": "synthetic_sleeper", "l4w_games_available": 0, "forward_history_missing": True,
            "bet_eligible": False, "eligibility_reason": "synthetic_or_unresolved_identity",
        },
    ]
    path = tmp_path / "anytime_td_2026_week01.csv"
    pd.DataFrame(rows, columns=list(site_columns)).to_csv(path, index=False)

    schedule = pd.DataFrame([{
        "season": 2026, "week": 1, "game_id": "2026_01_NE_SEA",
        "home_team": "SEA", "away_team": "NE", "home_score": 27, "away_score": 20,
    }])
    # "sleeper:rookie" is deliberately absent from actuals (a box-score feed
    # has no row for him at all), matching the real void scenario: he is only
    # resolved via the separate participation feed's confirmed zero snaps.
    # NE-COVERAGE is present so both teams clear the complete-feed check.
    actuals = pd.DataFrame([
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "SEA-RB",
            "team": "SEA", "rushing_tds": 2, "receiving_tds": 0, "offense_snaps": 55,
        },
        {
            "season": 2026, "week": 1, "season_type": "REG", "player_id": "NE-COVERAGE",
            "team": "NE", "rushing_tds": 0, "receiving_tds": 0, "offense_snaps": 0,
        },
    ])
    participation = pd.DataFrame([
        {"season": 2026, "week": 1, "player_id": "sleeper:rookie", "team": "SEA", "offense_snaps": 0},
    ])

    result = grade_anytime_td_file(
        path, schedule, actuals, participation=participation, season=2026, week=1
    )
    assert result["status"] == "graded"
    graded = pd.read_csv(path)

    real = graded.set_index("player_id").loc["SEA-RB"]
    assert int(real["scored_anytime"]) == 1
    assert real["status"] == "final"

    # The cold-start row's eligibility fields must survive grading untouched
    # and must not have influenced its outcome. Absent from the box score but
    # confirmed zero snaps in the participation feed is exactly the DNP/void
    # case (Phase 3 of this review): void, not a loss -- being non-bettable
    # is a separate question from having actually played.
    cold = graded.set_index("player_id").loc["sleeper:rookie"]
    assert bool(cold["bet_eligible"]) is False
    assert cold["eligibility_reason"] == "synthetic_or_unresolved_identity"
    assert pd.isna(cold["scored_anytime"])
    assert cold["status"] == "void"

    # Every real SITE_COLUMNS field must still be present after grading.
    assert set(site_columns).issubset(graded.columns)
