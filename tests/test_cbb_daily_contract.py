from pathlib import Path

import pandas as pd

import pytest

from publishing.cbb_daily import (
    CARD_COLUMNS,
    RESULT_COLUMNS,
    cbb_status,
    publish_card_candidate,
    publish_result_candidate,
    rollback_cbb_card,
    rollback_cbb_results,
    validate_card_candidate,
)
from publishing.contract import PublicationError
from publishing.contract import sha256_file


def _empty_candidate(tmp_path: Path):
    artifact = tmp_path / "card.csv"
    pd.DataFrame(columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    digest = sha256_file(artifact)
    metadata = {
        "schema_version": "cbb_daily_card_v1",
        "product": "cbb_daily_spreads",
        "season": 2027,
        "game_date_et": "2026-11-02",
        "status": "no_games_scheduled",
        "artifact_sha256": digest,
        "expected_rows": 0,
        "model_hash": "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800",
        "feature_hash": "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f",
        "historical_benchmark_hash": "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930",
        "policy_hash": "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d",
        "threshold": 8.5,
        "prediction_run_hash": "pred",
    }
    return artifact, metadata


def test_no_game_card_is_valid_and_publishable(tmp_path):
    artifact, metadata = _empty_candidate(tmp_path)
    checked = validate_card_candidate(artifact, metadata)
    assert checked["frame"].empty
    entry = publish_card_candidate(artifact, metadata, root=tmp_path)
    assert entry["status"] == "no_games_scheduled"
    assert cbb_status(root=tmp_path)["latest_date"] == "2026-11-02"


def test_exact_threshold_card_is_valid(tmp_path):
    artifact = tmp_path / "card.csv"
    row = {column: "" for column in CARD_COLUMNS}
    row.update({
        "game_id": "g1", "season": 2027, "game_date_et": "2026-11-02", "tipoff_utc": "2026-11-02T20:00:00Z",
        "home_team_id": "h", "home_team": "Home", "away_team_id": "a", "away_team": "Away",
        "neutral_site": False, "conference_game": True, "predicted_home_score": 80.0,
        "predicted_away_score": 70.0, "predicted_margin": 10.0, "predicted_total": 150.0,
        "predicted_winner": "home", "home_win_probability": 0.7, "market_home_spread": -1.5,
        "market_home_margin": 1.5, "provider_count": 2, "market_status": "available",
        "model_edge": 8.5, "ats_pick": "home", "ats_status": "candidate",
        "prediction_at_utc": "2026-11-02T13:00:00Z", "line_retrieved_at_utc": "2026-11-02T14:00:00Z",
        "decision_time_utc": "2026-11-02T14:00:00Z", "model_hash": "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800",
        "feature_hash": "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f",
        "policy_hash": "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d",
        "prediction_run_hash": "pred", "ats_card_run_hash": "ats",
    })
    pd.DataFrame([row], columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "cbb_daily_card_v1", "product": "cbb_daily_spreads", "season": 2027,
        "game_date_et": "2026-11-02", "status": "published", "artifact_sha256": sha256_file(artifact),
        "expected_rows": 1, "expected_game_ids": ["g1"], "model_hash": row["model_hash"],
        "feature_hash": row["feature_hash"], "historical_benchmark_hash": "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930",
        "policy_hash": row["policy_hash"], "threshold": 8.5, "prediction_run_hash": "pred",
    }
    assert validate_card_candidate(artifact, metadata)["frame"].loc[0, "ats_pick"] == "home"


def _published_card(tmp_path):
    artifact = tmp_path / "published-card.csv"
    row = {column: "" for column in CARD_COLUMNS}
    row.update({
        "game_id": "g1", "season": 2027, "game_date_et": "2026-11-02", "tipoff_utc": "2026-11-02T20:00:00Z",
        "home_team_id": "h", "home_team": "Home", "away_team_id": "a", "away_team": "Away", "neutral_site": False,
        "conference_game": True, "predicted_home_score": 80.0, "predicted_away_score": 70.0, "predicted_margin": 10.0,
        "predicted_total": 150.0, "predicted_winner": "home", "home_win_probability": 0.7, "market_home_spread": -1.5,
        "market_home_margin": 1.5, "provider_count": 2, "market_status": "available", "model_edge": 8.5,
        "ats_pick": "home", "ats_status": "candidate", "prediction_at_utc": "2026-11-02T13:00:00Z",
        "line_retrieved_at_utc": "2026-11-02T14:00:00Z", "decision_time_utc": "2026-11-02T14:00:00Z",
        "model_hash": "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800",
        "feature_hash": "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f",
        "policy_hash": "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d",
        "prediction_run_hash": "pred", "ats_card_run_hash": "ats",
    })
    pd.DataFrame([row], columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "cbb_daily_card_v1", "product": "cbb_daily_spreads", "season": 2027, "game_date_et": "2026-11-02",
        "status": "published", "artifact_sha256": sha256_file(artifact), "expected_rows": 1, "expected_game_ids": ["g1"],
        "model_hash": row["model_hash"], "feature_hash": row["feature_hash"],
        "historical_benchmark_hash": "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930",
        "policy_hash": row["policy_hash"], "threshold": 8.5, "prediction_run_hash": "pred",
    }
    return publish_card_candidate(artifact, metadata, root=tmp_path), row


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
