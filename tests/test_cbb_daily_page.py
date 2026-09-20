import os
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from publishing.cbb_daily import CARD_COLUMNS, publish_card_candidate
from publishing.contract import sha256_file


ROOT = Path(__file__).resolve().parents[1]


def test_cbb_page_renders_published_card(tmp_path):
    release_root = tmp_path / "data" / "releases" / "cbb_daily"
    artifact = tmp_path / "card.csv"
    row = {column: "" for column in CARD_COLUMNS}
    row.update({
        "game_id": "g1", "season": 2027, "game_date_et": "2026-11-02", "tipoff_utc": "2026-11-02T20:00:00Z",
        "home_team_id": "h", "home_team": "Home", "away_team_id": "a", "away_team": "Away",
        "neutral_site": False, "conference_game": True, "predicted_home_score": 80.0, "predicted_away_score": 70.0,
        "predicted_margin": 10.0, "predicted_total": 150.0, "predicted_winner": "home", "home_win_probability": 0.7,
        "market_home_spread": -1.5, "market_home_margin": 1.5, "provider_count": 2, "market_status": "available",
        "model_edge": 8.5, "ats_pick": "home", "ats_status": "candidate", "prediction_at_utc": "2026-11-02T13:00:00Z",
        "line_retrieved_at_utc": "2026-11-02T14:00:00Z", "decision_time_utc": "2026-11-02T14:00:00Z",
        "model_hash": "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800",
        "feature_hash": "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f",
        "policy_hash": "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d",
        "prediction_run_hash": "pred", "ats_card_run_hash": "ats",
    })
    pd.DataFrame([row], columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "cbb_daily_card_v1", "product": "cbb_daily_spreads", "season": 2027,
        "game_date_et": "2026-11-02", "status": "published", "artifact_sha256": sha256_file(artifact),
        "expected_rows": 1, "expected_game_ids": ["g1"], "model_hash": row["model_hash"], "feature_hash": row["feature_hash"],
        "historical_benchmark_hash": "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930",
        "policy_hash": row["policy_hash"], "threshold": 8.5, "prediction_run_hash": "pred",
    }
    publish_card_candidate(artifact, metadata, root=tmp_path)
    harness = tmp_path / "harness.py"
    harness.write_text(
        f"import os, sys; os.environ['APP_OFFLINE']='1'; os.environ['JSA_CBB_FIXTURE_DIR']=r'{tmp_path}'; sys.path[:0]=[r'{ROOT}', r'{ROOT / 'site_pages'}']\n"
        "import page_cbb_daily; page_cbb_daily.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [error.value for error in at.error]
    assert any("8.5-point play" in str(value.value) for value in at.success)

