from pathlib import Path

import pandas as pd

import pytest

from publishing.cbb_daily import (
    CARD_COLUMNS,
    CARD_SCHEMA_VERSION,
    LINE_SNAPSHOT_STATUSES,
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


def _lined_row(game_id: str = "g1", **overrides) -> dict:
    """An `available` row: a pre-tip official line captured at 09:00 ET on game day."""
    row = {column: "" for column in CARD_COLUMNS}
    row.update({
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


def _card(tmp_path: Path, rows: list[dict], *, line_snapshot_status: str | None = "official", name: str = "card.csv", **meta):
    artifact = tmp_path / name
    pd.DataFrame(rows, columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": CARD_SCHEMA_VERSION, "product": "cbb_daily_spreads", "season": 2027,
        "game_date_et": "2026-11-02", "status": "published" if rows else "no_games_scheduled",
        "artifact_sha256": sha256_file(artifact), "expected_rows": len(rows),
        "expected_game_ids": [row["game_id"] for row in rows], "model_hash": MODEL_HASH,
        "feature_hash": FEATURE_HASH, "historical_benchmark_hash": BENCHMARK_HASH,
        "policy_hash": POLICY_HASH, "threshold": 8.5, "prediction_run_hash": "pred",
        "line_snapshot_status": line_snapshot_status,
    }
    if line_snapshot_status is None:
        del metadata["line_snapshot_status"]
    metadata.update(meta)
    return artifact, metadata


def _empty_candidate(tmp_path: Path, line_snapshot_status: str = "unavailable"):
    return _card(tmp_path, [], line_snapshot_status=line_snapshot_status)


def test_card_schema_version_is_pinned_to_v2():
    assert CARD_SCHEMA_VERSION == "cbb_daily_card_v2"
    assert LINE_SNAPSHOT_STATUSES == {"official", "unavailable", "rejected"}


def test_no_game_card_is_valid_and_publishable(tmp_path):
    artifact, metadata = _empty_candidate(tmp_path)
    checked = validate_card_candidate(artifact, metadata)
    assert checked["frame"].empty
    entry = publish_card_candidate(artifact, metadata, root=tmp_path)
    assert entry["status"] == "no_games_scheduled"
    assert cbb_status(root=tmp_path)["latest_date"] == "2026-11-02"


@pytest.mark.parametrize("status", sorted(LINE_SNAPSHOT_STATUSES))
def test_empty_card_accepts_every_snapshot_status(tmp_path, status):
    artifact, metadata = _empty_candidate(tmp_path, status)
    assert validate_card_candidate(artifact, metadata)["frame"].empty


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
