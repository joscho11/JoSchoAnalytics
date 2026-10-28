import json
from pathlib import Path

import pandas as pd

import pytest

from publishing.cbb_daily import (
    CARD_COLUMNS,
    CARD_SCHEMA_VERSION,
    LINE_SNAPSHOT_STATUSES,
    OPTIONAL_CARD_COLUMNS,
    RESULT_COLUMNS,
    cbb_status,
    load_cbb_card,
    load_cbb_results,
    publish_card_candidate,
    publish_result_candidate,
    rollback_cbb_card,
    rollback_cbb_results,
    validate_card_candidate,
)
from publishing.contract import PublicationError
from publishing.contract import sha256_file


MODEL_HASH = "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800"
FEATURE_HASH = "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f"
BENCHMARK_HASH = "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930"
POLICY_HASH = "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d"
TOP25 = {"poll": "AP Top 25", "poll_date": "2026-10-20", "week": 1, "source": "static_snapshot"}


def _lined_row(game_id: str = "g1", **overrides) -> dict:
    """An `available` row: a pre-tip official line captured at 09:00 ET on game day."""
    row = {column: "" for column in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS}
    row.update({
        "home_conference": "SEC", "away_conference": "A-10", "home_rank": 3, "away_rank": "",
        "game_id": game_id, "season": 2027, "game_date_et": "2026-11-02", "tipoff_utc": "2026-11-02T20:00:00Z",
        "home_team_id": "h", "home_team": "Home", "away_team_id": "a", "away_team": "Away",
        "neutral_site": False, "conference_game": True, "predicted_home_score": 80.0,
        "predicted_away_score": 70.0, "predicted_margin": 10.0, "predicted_total": 150.0,
        "predicted_winner": "home", "home_win_probability": 0.7, "market_home_spread": -1.5,
        "market_home_margin": 1.5, "provider_count": 2, "market_status": "available",
        "model_edge": 8.5, "ats_pick": "home", "ats_status": "candidate",
        "prediction_at_utc": "2026-11-02T13:00:00Z", "line_retrieved_at_utc": "2026-11-02T14:00:00Z",
        "decision_time_utc": "2026-11-02T14:00:00Z", "model_hash": MODEL_HASH,
        "feature_hash": FEATURE_HASH, "policy_hash": POLICY_HASH,
        "prediction_run_hash": "pred", "ats_card_run_hash": "ats",
    })
    row.update(overrides)
    return row


def _unlined_row(game_id: str = "g2", **overrides) -> dict:
    """A `missing_line` row: prediction fields only, every market field blank."""
    row = _lined_row(game_id)
    row.update({
        "market_home_spread": "", "market_home_margin": "", "provider_count": 0,
        "market_status": "missing_line", "model_edge": "", "ats_pick": "no_play_line_unavailable",
        "ats_status": "line_unavailable", "line_retrieved_at_utc": "", "decision_time_utc": "",
        "ats_card_run_hash": "",
    })
    row.update(overrides)
    return row


def _late_row(game_id: str = "g1", **overrides) -> dict:
    row = _lined_row(game_id)
    row.update({
        "market_status": "late_available", "model_edge": "", "ats_pick": "no_play_late_snapshot",
        "ats_status": "late_not_graded", "line_retrieved_at_utc": "2026-11-02T14:30:00Z",
        "decision_time_utc": "2026-11-02T14:30:00Z", "ats_card_run_hash": "",
    })
    row.update(overrides)
    return row


def _card(tmp_path: Path, rows: list[dict], *, line_snapshot_status: str | None = "official", name: str = "card.csv", columns=None, **meta):
    """Write a card. Rows carry the optional conference and rank columns unless ``columns`` names another set."""
    artifact = tmp_path / name
    pd.DataFrame(rows, columns=columns or CARD_COLUMNS + OPTIONAL_CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": CARD_SCHEMA_VERSION, "product": "cbb_daily_spreads", "season": 2027,
        "game_date_et": "2026-11-02", "status": "published" if rows else "no_games_scheduled",
        "artifact_sha256": sha256_file(artifact), "expected_rows": len(rows),
        "expected_game_ids": [row["game_id"] for row in rows], "model_hash": MODEL_HASH,
        "feature_hash": FEATURE_HASH, "historical_benchmark_hash": BENCHMARK_HASH,
        "policy_hash": POLICY_HASH, "threshold": 8.5, "prediction_run_hash": "pred",
        "line_snapshot_status": line_snapshot_status, "top25": dict(TOP25),
    }
    if line_snapshot_status is None:
        del metadata["line_snapshot_status"]
    metadata.update(meta)
    return artifact, metadata


def _empty_candidate(tmp_path: Path, line_snapshot_status: str = "unavailable"):
    return _card(tmp_path, [], line_snapshot_status=line_snapshot_status)


def test_card_schema_version_is_pinned_to_v2():
    assert CARD_SCHEMA_VERSION == "cbb_daily_card_v2"
    assert LINE_SNAPSHOT_STATUSES == {"official", "catch_up", "mixed", "unavailable", "rejected"}


def test_no_game_card_is_valid_and_publishable(tmp_path):
    artifact, metadata = _empty_candidate(tmp_path)
    checked = validate_card_candidate(artifact, metadata)
    assert checked["frame"].empty
    entry = publish_card_candidate(artifact, metadata, root=tmp_path)
    assert entry["status"] == "no_games_scheduled"
    assert cbb_status(root=tmp_path)["latest_date"] == "2026-11-02"


@pytest.mark.parametrize("status", sorted(LINE_SNAPSHOT_STATUSES - {"catch_up", "mixed"}))
def test_empty_card_accepts_every_snapshot_status(tmp_path, status):
    artifact, metadata = _empty_candidate(tmp_path, status)
    assert validate_card_candidate(artifact, metadata)["frame"].empty


@pytest.mark.parametrize("status", ["catch_up", "mixed"])
def test_empty_card_rejects_snapshot_statuses_that_require_lines(tmp_path, status):
    artifact, metadata = _empty_candidate(tmp_path, status)
    with pytest.raises(PublicationError, match="empty CBB daily card cannot use line_snapshot_status"):
        validate_card_candidate(artifact, metadata)


def test_exact_threshold_card_is_valid(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row()])
    assert validate_card_candidate(artifact, metadata)["frame"].loc[0, "ats_pick"] == "home"


def test_predictions_only_card_is_valid(tmp_path):
    rows = [_unlined_row("g1"), _unlined_row("g2", home_team="Other Home", away_team="Other Away", home_team_id="h2", away_team_id="a2")]
    artifact, metadata = _card(tmp_path, rows, line_snapshot_status="unavailable")
    checked = validate_card_candidate(artifact, metadata)
    assert checked["frame"]["market_status"].eq("missing_line").all()
    entry = publish_card_candidate(artifact, metadata, root=tmp_path)
    assert entry["status"] == "published" and entry["row_count"] == 2
    frame, stored_meta, _ = load_cbb_card("2026-11-02", root=tmp_path)
    assert len(frame) == 2 and stored_meta["line_snapshot_status"] == "unavailable"
    assert stored_meta["schema_version"] == "cbb_daily_card_v2"


def test_rejected_snapshot_card_is_valid_without_lines(tmp_path):
    artifact, metadata = _card(tmp_path, [_unlined_row()], line_snapshot_status="rejected")
    assert validate_card_candidate(artifact, metadata)["metadata"]["line_snapshot_status"] == "rejected"


def test_official_card_may_carry_games_without_a_line(tmp_path):
    rows = [_lined_row("g1"), _unlined_row("g2", home_team="Early", away_team="Tip", home_team_id="h2", away_team_id="a2")]
    artifact, metadata = _card(tmp_path, rows, line_snapshot_status="official")
    assert validate_card_candidate(artifact, metadata)["frame"]["market_status"].tolist() == ["available", "missing_line"]


def test_catch_up_card_carries_spreads_without_shadow_picks(tmp_path):
    artifact, metadata = _card(tmp_path, [_late_row()], line_snapshot_status="catch_up")
    checked = validate_card_candidate(artifact, metadata)
    row = checked["frame"].iloc[0]
    assert row["market_status"] == "late_available"
    assert row["ats_pick"] == "no_play_late_snapshot" and row["ats_status"] == "late_not_graded"
    assert pd.isna(pd.to_numeric(row["model_edge"], errors="coerce"))


def test_mixed_card_keeps_official_picks_and_unscored_recovery_spreads(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row("official-game"), _late_row("recovered-game")], line_snapshot_status="mixed")
    checked = validate_card_candidate(artifact, metadata)
    assert checked["frame"]["market_status"].tolist() == ["available", "late_available"]
    entry = publish_card_candidate(artifact, metadata, root=tmp_path / "published")
    frame, saved_meta, _ = load_cbb_card("2026-11-02", root=tmp_path / "published")
    assert entry["status"] == "published" and saved_meta["line_snapshot_status"] == "mixed"
    assert frame.loc[0, "ats_pick"] == "home"
    assert frame.loc[1, "ats_pick"] == "no_play_late_snapshot" and frame.loc[1, "ats_status"] == "late_not_graded"


@pytest.mark.parametrize("overrides", [
    {"line_retrieved_at_utc": "2026-11-02T13:00:00Z", "decision_time_utc": "2026-11-02T13:00:00Z"},
    {"line_retrieved_at_utc": "2026-11-02T16:01:00Z", "decision_time_utc": "2026-11-02T16:01:00Z"},
    {"tipoff_utc": "2026-11-02T14:30:00Z"},
    {"ats_pick": "home", "ats_status": "candidate"},
])
def test_invalid_catch_up_spreads_are_rejected(tmp_path, overrides):
    artifact, metadata = _card(tmp_path, [_late_row(**overrides)], line_snapshot_status="catch_up")
    with pytest.raises(PublicationError):
        validate_card_candidate(artifact, metadata)


@pytest.mark.parametrize("status", ["unavailable", "rejected"])
def test_unavailable_snapshot_rejects_available_rows(tmp_path, status):
    artifact, metadata = _card(tmp_path, [_lined_row()], line_snapshot_status=status)
    with pytest.raises(PublicationError, match="must not contain available lines"):
        validate_card_candidate(artifact, metadata)
    with pytest.raises(PublicationError, match="must not contain available lines"):
        publish_card_candidate(artifact, metadata, root=tmp_path)
    assert not (tmp_path / "data" / "releases" / "cbb_daily" / "manifest.json").exists()


def test_official_status_requires_an_available_row(tmp_path):
    artifact, metadata = _card(tmp_path, [_unlined_row()], line_snapshot_status="official")
    with pytest.raises(PublicationError, match="requires at least one available line"):
        validate_card_candidate(artifact, metadata)


def test_v1_schema_rejected(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row()], schema_version="cbb_daily_card_v1")
    with pytest.raises(PublicationError, match="unsupported CBB daily card"):
        validate_card_candidate(artifact, metadata)
    # A real v1 card has no line_snapshot_status at all; it is still named as v1.
    artifact_v1, metadata_v1 = _card(tmp_path, [_lined_row()], line_snapshot_status=None, name="v1.csv", schema_version="cbb_daily_card_v1")
    with pytest.raises(PublicationError, match="cbb_daily_card_v1"):
        validate_card_candidate(artifact_v1, metadata_v1)
    with pytest.raises(PublicationError, match="unsupported CBB daily card"):
        publish_card_candidate(artifact_v1, metadata_v1, root=tmp_path)


def test_snapshot_status_is_required_and_must_be_known(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row()], line_snapshot_status=None)
    with pytest.raises(PublicationError, match="line_snapshot_status"):
        validate_card_candidate(artifact, metadata)
    for bad in ("Official", "ok", "", None, ["official"]):
        artifact, metadata = _card(tmp_path, [_lined_row()], name="bad.csv")
        metadata["line_snapshot_status"] = bad
        with pytest.raises(PublicationError, match="line_snapshot_status must be one of"):
            validate_card_candidate(artifact, metadata)


def test_eight_point_four_six_edge_cannot_be_labelled_a_play(tmp_path):
    # Edge 8.46 is below the locked 8.5 threshold: the validator must insist on no play.
    row = _lined_row(predicted_margin=9.96, predicted_home_score=79.98, predicted_away_score=70.02, model_edge=8.46, ats_pick="home")
    artifact, metadata = _card(tmp_path, [row])
    with pytest.raises(PublicationError, match="8.5-point threshold"):
        validate_card_candidate(artifact, metadata)
    row["ats_pick"] = "no_play_below_threshold"
    artifact, metadata = _card(tmp_path, [row], name="ok.csv")
    assert validate_card_candidate(artifact, metadata)["frame"].loc[0, "ats_pick"] == "no_play_below_threshold"


def test_available_line_outside_the_official_window_is_still_rejected(tmp_path):
    # 14:01Z is 09:01 ET on 2026-11-02 (EST): one minute past the decision clock.
    artifact, metadata = _card(tmp_path, [_lined_row(line_retrieved_at_utc="2026-11-02T14:01:00Z")])
    with pytest.raises(PublicationError, match="08:45"):
        validate_card_candidate(artifact, metadata)


def _published_card(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row()], name="published-card.csv")
    return publish_card_candidate(artifact, metadata, root=tmp_path), _lined_row()


def test_result_binding_recomputes_cover_and_supports_pointer_rollback(tmp_path):
    card_entry, row = _published_card(tmp_path)
    artifact = tmp_path / "results.csv"
    result = {
        "game_id": "g1", "game_date_et": "2026-11-02", "home_score": 82, "away_score": 70,
        "actual_home_margin": 12, "actual_cover_margin": 10.5, "ats_result": "win",
        "finalized_at_utc": "2026-11-03T03:00:00Z", "source_card_build_id": card_entry["build_id"],
    }
    pd.DataFrame([result], columns=RESULT_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "cbb_daily_results_v1", "product": "cbb_daily_spreads_results", "season": 2027,
        "game_date_et": "2026-11-02", "source_card_build_id": card_entry["build_id"],
        "source_card_sha256": card_entry["sha256"], "artifact_sha256": sha256_file(artifact), "expected_rows": 1,
        "model_hash": row["model_hash"], "feature_hash": row["feature_hash"], "policy_hash": row["policy_hash"],
    }
    first = publish_result_candidate(artifact, metadata, root=tmp_path)
    assert "2026-11-02" in cbb_status(root=tmp_path)["dates"]
    bad = pd.DataFrame([{**result, "actual_cover_margin": 99}], columns=RESULT_COLUMNS)
    bad_path = tmp_path / "bad.csv"
    bad.to_csv(bad_path, index=False, lineterminator="\n")
    bad_meta = {**metadata, "artifact_sha256": sha256_file(bad_path)}
    with pytest.raises(PublicationError, match="cover margin"):
        publish_result_candidate(bad_path, bad_meta, root=tmp_path)


def _results_metadata(card_entry: dict, artifact: Path, rows: int) -> dict:
    return {
        "schema_version": "cbb_daily_results_v1", "product": "cbb_daily_spreads_results", "season": 2027,
        "game_date_et": "2026-11-02", "source_card_build_id": card_entry["build_id"],
        "source_card_sha256": card_entry["sha256"], "artifact_sha256": sha256_file(artifact), "expected_rows": rows,
        "model_hash": MODEL_HASH, "feature_hash": FEATURE_HASH, "policy_hash": POLICY_HASH,
    }


def test_results_for_no_line_card_are_no_play(tmp_path):
    """A predictions-only card still grades: finalized games are `no_play`, cover margin is blank (NaN)."""
    rows = [_unlined_row("g1"), _unlined_row("g2", home_team="Other Home", away_team="Other Away", home_team_id="h2", away_team_id="a2")]
    card_artifact, card_meta = _card(tmp_path, rows, line_snapshot_status="unavailable")
    card_entry = publish_card_candidate(card_artifact, card_meta, root=tmp_path)
    build = card_entry["build_id"]
    finalized = {
        "game_id": "g1", "game_date_et": "2026-11-02", "home_score": 82, "away_score": 70,
        "actual_home_margin": 12, "actual_cover_margin": float("nan"), "ats_result": "no_play",
        "finalized_at_utc": "2026-11-03T03:00:00Z", "source_card_build_id": build,
    }
    pending = {
        "game_id": "g2", "game_date_et": "2026-11-02", "home_score": float("nan"), "away_score": float("nan"),
        "actual_home_margin": float("nan"), "actual_cover_margin": float("nan"), "ats_result": "ungraded",
        "finalized_at_utc": "", "source_card_build_id": build,
    }
    artifact = tmp_path / "results.csv"
    pd.DataFrame([finalized, pending], columns=RESULT_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    published = publish_result_candidate(artifact, _results_metadata(card_entry, artifact, 2), root=tmp_path)
    assert published["build_id"].startswith("cbb-results-2026-11-02-")
    stored = load_cbb_results("2026-11-02", root=tmp_path)
    assert stored["ats_result"].tolist() == ["no_play", "ungraded"]
    assert pd.isna(stored.loc[0, "actual_cover_margin"])
    # The same results can never claim an ATS win or loss for a game with no line.
    for fake in ("win", "loss", "push"):
        lying = pd.DataFrame([{**finalized, "ats_result": fake}], columns=RESULT_COLUMNS)
        lying_path = tmp_path / f"lying-{fake}.csv"
        lying.to_csv(lying_path, index=False, lineterminator="\n")
        with pytest.raises(PublicationError, match="does not match the source card pick"):
            publish_result_candidate(lying_path, _results_metadata(card_entry, lying_path, 1), root=tmp_path)


def test_mixed_recovery_spread_cannot_enter_the_graded_record(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row("official"), _late_row("recovery")], line_snapshot_status="mixed")
    card_entry = publish_card_candidate(artifact, metadata, root=tmp_path)
    results = pd.DataFrame([
        {"game_id": "official", "game_date_et": "2026-11-02", "home_score": 82, "away_score": 70,
         "actual_home_margin": 12, "actual_cover_margin": 10.5, "ats_result": "win",
         "finalized_at_utc": "2026-11-03T03:00:00Z", "source_card_build_id": card_entry["build_id"]},
        {"game_id": "recovery", "game_date_et": "2026-11-02", "home_score": 82, "away_score": 70,
         "actual_home_margin": 12, "actual_cover_margin": "", "ats_result": "no_play",
         "finalized_at_utc": "2026-11-03T03:00:00Z", "source_card_build_id": card_entry["build_id"]},
    ], columns=RESULT_COLUMNS)
    result_path = tmp_path / "mixed-results.csv"
    results.to_csv(result_path, index=False, lineterminator="\n")
    published = publish_result_candidate(result_path, _results_metadata(card_entry, result_path, 2), root=tmp_path)
    stored = load_cbb_results("2026-11-02", root=tmp_path)
    assert published["build_id"].startswith("cbb-results-2026-11-02-")
    assert len(stored) == 2
    assert stored.set_index("game_id").loc["recovery", "ats_result"] == "no_play"
    results.loc[results["game_id"] == "recovery", "ats_result"] = "win"
    lying_path = tmp_path / "mixed-results-win.csv"
    results.to_csv(lying_path, index=False, lineterminator="\n")
    with pytest.raises(PublicationError, match="does not match the source card pick"):
        publish_result_candidate(lying_path, _results_metadata(card_entry, lying_path, 2), root=tmp_path)


def test_card_rollback_pointer_still_works_for_a_predictions_only_correction(tmp_path):
    first_artifact, first_meta = _card(tmp_path, [_unlined_row()], line_snapshot_status="unavailable", name="first.csv")
    first = publish_card_candidate(first_artifact, first_meta, root=tmp_path)
    second_artifact, second_meta = _card(
        tmp_path, [_unlined_row(predicted_home_score=81.0, predicted_away_score=71.0, predicted_total=152.0)],
        line_snapshot_status="unavailable", name="second.csv",
    )
    second = publish_card_candidate(second_artifact, second_meta, root=tmp_path)
    assert second["build_id"] != first["build_id"]
    assert rollback_cbb_card("2026-11-02", root=tmp_path)["build_id"] == first["build_id"]
    with pytest.raises(PublicationError):
        rollback_cbb_results("2026-11-02", root=tmp_path)


def _coverage(predicted: int, **overrides) -> dict:
    coverage = {
        "scheduled_games": predicted + 5, "predicted_games": predicted, "excluded_games": 5,
        "excluded_by_reason": {"start_time_tbd": 3, "not_d1_v_d1": 2},
    }
    coverage.update(overrides)
    return coverage


def test_card_with_valid_coverage_is_accepted_and_stored(tmp_path):
    coverage = _coverage(2)
    artifact, metadata = _card(tmp_path, [_unlined_row("g1"), _unlined_row("g2", home_team_id="h2", away_team_id="a2")], line_snapshot_status="unavailable", coverage=coverage)
    assert validate_card_candidate(artifact, metadata)["metadata"]["coverage"] == coverage
    publish_card_candidate(artifact, metadata, root=tmp_path)
    _, stored, _ = load_cbb_card("2026-11-02", root=tmp_path)
    assert stored["coverage"] == coverage


def test_coverage_is_optional(tmp_path):
    artifact, metadata = _card(tmp_path, [_lined_row()])
    assert "coverage" not in metadata and validate_card_candidate(artifact, metadata)


def test_empty_card_may_carry_coverage(tmp_path):
    coverage = {"scheduled_games": 4, "predicted_games": 0, "excluded_games": 4, "excluded_by_reason": {"not_d1_v_d1": 4}}
    artifact, metadata = _empty_candidate(tmp_path)
    metadata["coverage"] = coverage
    assert validate_card_candidate(artifact, metadata)["frame"].empty
    metadata["coverage"] = _coverage(1)
    with pytest.raises(PublicationError, match="predicted_games does not match"):
        validate_card_candidate(artifact, metadata)


@pytest.mark.parametrize("bad, message", [
    (_coverage(1, predicted_games=2, scheduled_games=7), "predicted_games does not match"),
    (_coverage(1, scheduled_games=7), "scheduled_games must equal"),
    (_coverage(1, excluded_by_reason={"start_time_tbd": 3}), "must sum to excluded_games"),
    (_coverage(1, excluded_games=-5, scheduled_games=-4, excluded_by_reason={"a": -5}), "non-negative"),
    (_coverage(1, excluded_games=5.0), "non-negative"),
    (_coverage(1, excluded_games=True, scheduled_games=2, excluded_by_reason={"a": 1}), "non-negative"),
    (_coverage(1, scheduled_games="6"), "non-negative"),
    (_coverage(1, excluded_by_reason={7: 3, "not_d1_v_d1": 2}), "reason names"),
    (_coverage(1, excluded_by_reason={"": 3, "not_d1_v_d1": 2}), "reason names"),
    (_coverage(1, excluded_by_reason={"start_time_tbd": 3.0, "not_d1_v_d1": 2}), "reason names"),
    (_coverage(1, excluded_by_reason=[3, 2]), "reason names"),
    ({k: v for k, v in _coverage(1).items() if k != "excluded_by_reason"}, "exactly"),
    ({**_coverage(1), "extra": 1}, "exactly"),
    ("80 of 181", "must be an object"),
    (None, "must be an object"),
])
def test_invalid_coverage_is_rejected(tmp_path, bad, message):
    artifact, metadata = _card(tmp_path, [_unlined_row("g1")], line_snapshot_status="unavailable", coverage=bad)
    with pytest.raises(PublicationError, match=message):
        validate_card_candidate(artifact, metadata)
    with pytest.raises(PublicationError):
        publish_card_candidate(artifact, metadata, root=tmp_path)


# ---- Optional conference, rank and top25 fields ---------------------------------------------------

def _extras_card(tmp_path: Path, rows: list[dict], *, name: str = "extras.csv", **meta):
    return _card(tmp_path, rows, line_snapshot_status="unavailable", name=name, **meta)


def _plain(game_id: str = "g1", **overrides) -> dict:
    return _unlined_row(game_id, **overrides)


def test_card_with_conferences_ranks_and_top25_is_accepted_and_round_trips(tmp_path):
    rows = [
        _plain("g1", home_conference="SEC", away_conference="A-10", home_rank=3, away_rank=25),
        _plain("g2", home_team_id="h2", away_team_id="a2", home_conference="", away_conference="Pac-12", home_rank="", away_rank=""),
    ]
    artifact, metadata = _extras_card(tmp_path, rows)
    checked = validate_card_candidate(artifact, metadata)
    assert checked["metadata"]["top25"] == TOP25
    publish_card_candidate(artifact, metadata, root=tmp_path)
    frame, stored, _ = load_cbb_card("2026-11-02", root=tmp_path)
    assert stored["top25"] == TOP25
    assert frame["home_conference"].tolist()[0] == "SEC" and frame["away_conference"].tolist() == ["A-10", "Pac-12"]
    assert pd.isna(frame.loc[1, "home_conference"]), "a blank conference stays blank, never the text 'nan'"
    assert frame["home_rank"].tolist()[0] == 3 and pd.isna(frame.loc[1, "home_rank"])
    written = pd.read_csv(artifact, dtype=str, keep_default_na=False)
    assert written["home_rank"].tolist() == ["3", ""] and written["away_rank"].tolist() == ["25", ""], "the CSV prints 3, not 3.0"


def test_ties_are_legal_and_conferences_may_be_blank(tmp_path):
    rows = [
        _plain("g1", home_conference="", away_conference="", home_rank=25, away_rank=25),
        _plain("g2", home_team_id="h2", away_team_id="a2", home_rank=25, away_rank=1),
    ]
    artifact, metadata = _extras_card(tmp_path, rows)
    assert validate_card_candidate(artifact, metadata)["frame"][["home_rank", "away_rank"]].stack().tolist() == [25, 25, 25, 1]


def test_card_without_the_optional_columns_still_validates_and_loads(tmp_path):
    """A card written before these fields existed has no extra columns and no top25, and is still valid."""
    artifact, metadata = _card(tmp_path, [_unlined_row()], line_snapshot_status="unavailable", columns=CARD_COLUMNS)
    del metadata["top25"]
    checked = validate_card_candidate(artifact, metadata)
    assert not set(OPTIONAL_CARD_COLUMNS) & set(checked["frame"].columns)
    publish_card_candidate(artifact, metadata, root=tmp_path)
    frame, stored, _ = load_cbb_card("2026-11-02", root=tmp_path)
    assert len(frame) == 1 and "top25" not in stored


def test_top25_may_be_null_when_no_rank_is_on_the_card(tmp_path):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank="", away_rank="")], top25=None)
    assert validate_card_candidate(artifact, metadata)["metadata"]["top25"] is None


@pytest.mark.parametrize("home, away", [(0, ""), (26, ""), ("", 100), (2.5, ""), (-1, ""), ("", "abc"), (1, 0)])
def test_ranks_must_be_blank_or_a_whole_number_from_1_to_25(tmp_path, home, away):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank=home, away_rank=away)])
    with pytest.raises(PublicationError, match="rank must be blank or a whole number from 1 to 25"):
        validate_card_candidate(artifact, metadata)
    with pytest.raises(PublicationError):
        publish_card_candidate(artifact, metadata, root=tmp_path)


def test_a_rank_requires_a_top25_poll(tmp_path):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank=3)], top25=None)
    with pytest.raises(PublicationError, match="ranks require top25"):
        validate_card_candidate(artifact, metadata)
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank=3)], name="no-key.csv")
    del metadata["top25"]
    with pytest.raises(PublicationError, match="ranks require top25"):
        validate_card_candidate(artifact, metadata)


@pytest.mark.parametrize("keep", [
    [c for c in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS if c != "away_rank"],
    [c for c in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS if c != "home_rank"],
    [c for c in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS if c != "away_conference"],
    [c for c in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS if c != "home_conference"],
])
def test_extra_columns_come_in_home_away_pairs(tmp_path, keep):
    artifact, metadata = _extras_card(tmp_path, [_plain()], columns=tuple(keep))
    with pytest.raises(PublicationError, match="come in home/away pairs"):
        validate_card_candidate(artifact, metadata)


@pytest.mark.parametrize("bad, message", [
    ("AP Top 25", "must be null or an object"),
    ([], "must be null or an object"),
    ({k: v for k, v in TOP25.items() if k != "week"}, "exactly"),
    ({**TOP25, "extra": 1}, "exactly"),
    ({**TOP25, "poll": "Coaches Poll"}, "poll must be 'AP Top 25'"),
    ({**TOP25, "poll_date": "10/20/2026"}, "poll_date must be YYYY-MM-DD"),
    ({**TOP25, "poll_date": "2026-13-40"}, "poll_date must be YYYY-MM-DD"),
    ({**TOP25, "poll_date": "2026-10-20T00:00:00"}, "poll_date must be YYYY-MM-DD"),
    ({**TOP25, "poll_date": None}, "poll_date must be YYYY-MM-DD"),
    ({**TOP25, "week": -1}, "week must be null or a non-negative integer"),
    ({**TOP25, "week": "1"}, "week must be null or a non-negative integer"),
    ({**TOP25, "week": True}, "week must be null or a non-negative integer"),
    ({**TOP25, "week": 1.5}, "week must be null or a non-negative integer"),
    ({**TOP25, "source": "espn"}, "source must be one of"),
    ({**TOP25, "source": None}, "source must be one of"),
])
def test_a_bad_top25_is_rejected(tmp_path, bad, message):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank="", away_rank="")], top25=bad)
    with pytest.raises(PublicationError, match=message):
        validate_card_candidate(artifact, metadata)


@pytest.mark.parametrize("week, source", [(None, "cbbd"), (0, "cbbd"), (1, "static_snapshot"), (14, "cbbd")])
def test_top25_accepts_a_null_or_whole_number_week_and_both_sources(tmp_path, week, source):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_rank=7)], top25={**TOP25, "week": week, "source": source})
    assert validate_card_candidate(artifact, metadata)["metadata"]["top25"]["source"] == source


def test_a_conference_column_that_holds_numbers_is_rejected(tmp_path):
    artifact, metadata = _extras_card(tmp_path, [_plain(home_conference="12", away_conference="SEC")])
    with pytest.raises(PublicationError, match="home_conference must hold conference names"):
        validate_card_candidate(artifact, metadata)


def test_an_empty_card_may_carry_the_poll_and_a_bad_poll_still_fails(tmp_path):
    artifact, metadata = _card(tmp_path, [], line_snapshot_status="unavailable")
    assert validate_card_candidate(artifact, metadata)["frame"].empty
    metadata["top25"] = {**TOP25, "source": "espn"}
    with pytest.raises(PublicationError, match="source must be one of"):
        validate_card_candidate(artifact, metadata)


# ---- data/cbb/conference_order_2027.json -----------------------------------------------------------

CBBD_2027_SHORT_NAMES = [
    "A-10", "ACC", "ASUN", "Am. East", "American", "Big 12", "Big East", "Big Sky", "Big South", "Big Ten", "Big West", "CAA", "CUSA",
    "Horizon", "Ivy", "Metro", "MAC", "MEAC", "MVC", "Mountain West", "NEC", "OVC", "Patriot", "SEC", "SWAC", "SoCon", "Southland",
    "Summit", "Sun Belt", "UAC", "WCC", "Pac-12",
]
CONFERENCE_ORDER_FILE = Path(__file__).resolve().parents[1] / "data" / "cbb" / "conference_order_2027.json"


def _conference_order() -> dict:
    return json.loads(CONFERENCE_ORDER_FILE.read_text(encoding="utf-8"))


def test_conference_order_file_has_32_unique_names_in_the_warrennolan_order():
    data = _conference_order()
    order = data["order"]
    assert len(order) == 32 and len(set(order)) == 32
    assert order[:6] == ["SEC", "Big 12", "Big Ten", "ACC", "Big East", "Pac-12"] and order[-3:] == ["America East", "SWAC", "MEAC"]
    assert data["source"] == "https://www.warrennolan.com/basketball/2027/net-conference"
    assert data["captured_on"] == "2026-10-24"
    assert "NET" in data["note"] and "refresh" in data["note"].lower()


def test_every_alias_points_at_a_name_in_the_order():
    data = _conference_order()
    assert data["aliases"] and all(target in data["order"] for target in data["aliases"].values())
    assert not set(data["aliases"]) & set(data["order"]), "an alias key is a CBBD name that differs from its display name"
    assert len(set(data["aliases"].values())) == len(data["aliases"])


def test_all_32_cbbd_2027_conference_names_resolve_to_one_listed_conference_each():
    data = _conference_order()
    assert len(CBBD_2027_SHORT_NAMES) == 32 and len(set(CBBD_2027_SHORT_NAMES)) == 32
    resolved = [data["aliases"].get(name, name) for name in CBBD_2027_SHORT_NAMES]
    assert all(name in data["order"] for name in resolved), [n for n in resolved if n not in data["order"]]
    assert sorted(resolved) == sorted(data["order"]), "the 32 CBBD names map one to one onto the 32 listed conferences"


def test_conference_order_file_has_no_em_or_en_dashes():
    text = CONFERENCE_ORDER_FILE.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_loader_reads_the_repo_file_and_fails_soft(tmp_path, monkeypatch):
    import cbb_daily_data

    cbb_daily_data.load_conference_order.clear()
    loaded = cbb_daily_data.load_conference_order()
    assert loaded["available"] and loaded["order"] == _conference_order()["order"] and loaded["captured_on"] == "2026-10-24"
    # The release fixture directory never replaces it, even with the offline flag set.
    monkeypatch.setenv("APP_OFFLINE", "1")
    monkeypatch.setenv("JSA_CBB_FIXTURE_DIR", str(tmp_path))
    cbb_daily_data.load_conference_order.clear()
    assert cbb_daily_data.load_conference_order()["available"]

    def read(payload: object) -> dict:
        path = tmp_path / "order.json"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(cbb_daily_data, "CONFERENCE_ORDER_PATH", path)
        cbb_daily_data.load_conference_order.clear()
        return cbb_daily_data.load_conference_order()

    unavailable = {"order": [], "aliases": {}, "captured_on": None, "source": None, "available": False}
    monkeypatch.setattr(cbb_daily_data, "CONFERENCE_ORDER_PATH", tmp_path / "does-not-exist.json")
    cbb_daily_data.load_conference_order.clear()
    assert cbb_daily_data.load_conference_order() == unavailable
    assert read("{not json") == unavailable
    assert read([]) == unavailable
    assert read({"order": []}) == unavailable
    assert read({"order": ["A", "A"]}) == unavailable
    assert read({"order": ["A", "B"], "aliases": {"a": "C"}}) == unavailable
    assert read({"order": ["A", "B"], "captured_on": "not a date"}) == unavailable
    good = read({"order": ["A", "B"], "aliases": {"a": "A"}, "captured_on": "2026-10-24"})
    assert good["available"] and good["order"] == ["A", "B"] and good["aliases"] == {"a": "A"}
    cbb_daily_data.load_conference_order.clear()
