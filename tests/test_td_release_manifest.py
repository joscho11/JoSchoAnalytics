"""Public artifact selection and reconstructed/live cohort isolation."""
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import attd_tracker as tracker
import page_anytime_td as page
from publishing.contract import PublicationError
from publishing.td_releases import canonical_td_releases, read_td_release

ROOT = Path(__file__).resolve().parents[1]


def _write_manifest(directory, entries):
    (directory / "releases_manifest.json").write_text(json.dumps({"schema_version": 1, "releases": entries}))


def _entry(directory, *, week=1, mode="retrospective", version="ngs44"):
    row = {"season": 2026, "week": week, "csv": f"ngs_week{week:02d}.csv",
           "metadata": f"ngs_week{week:02d}.json", "prediction_mode": mode, "model_version": version}
    (directory / row["metadata"]).write_text(json.dumps(row))
    pd.DataFrame({"season": [2026], "week": [week], "game_id": [f"2026_{week:02d}_A_B"], "player_id": ["p"],
                  "p_ge1": [.6], "p_book": [.5], "book_amer": [100],
                  "scored_anytime": [1], "status": ["final"]}).to_csv(directory / row["csv"], index=False)
    return row


def test_manifest_wins_and_suffix_csv_cannot_replace_canonical(tmp_path):
    legacy = tmp_path / "anytime_td_2026_week01.csv"
    legacy.write_text("game_id,player_id\ng,p\n")
    (tmp_path / "anytime_td_2026_week01_zzz.csv").write_text(legacy.read_text())
    assert canonical_td_releases(tmp_path)[(2026, 1)]["csv_path"] == legacy
    entry = _entry(tmp_path)
    _write_manifest(tmp_path, [entry])
    assert canonical_td_releases(tmp_path)[(2026, 1)]["csv_path"] == (tmp_path / entry["csv"]).resolve()
    frame = read_td_release(tmp_path / entry["csv"])
    assert frame.prediction_mode.tolist() == ["retrospective"]
    assert frame.model_version.tolist() == ["ngs44"]


@pytest.mark.parametrize("problem", ["duplicate", "escape", "metadata", "missing", "unknown_mode", "hash"])
def test_manifest_fails_closed(tmp_path, problem):
    entry = _entry(tmp_path)
    entries = [entry]
    if problem == "duplicate":
        entries.append(dict(entry))
    elif problem == "escape":
        entry["csv"] = "../outside.csv"
    elif problem == "metadata":
        entry["model_version"] = "other"
    elif problem == "missing":
        (tmp_path / entry["csv"]).unlink()
    elif problem == "hash":
        entry["csv_sha256"] = "0" * 64
    else:
        entry["prediction_mode"] = "diagnostic"
    _write_manifest(tmp_path, entries)
    with pytest.raises(PublicationError):
        canonical_td_releases(tmp_path)


def test_manifest_detects_artifact_tampering(tmp_path):
    entry = _entry(tmp_path)
    entry["csv_sha256"] = __import__("hashlib").sha256(
        (tmp_path / entry["csv"]).read_bytes()
    ).hexdigest()
    entry["metadata_sha256"] = __import__("hashlib").sha256(
        (tmp_path / entry["metadata"]).read_bytes()
    ).hexdigest()
    _write_manifest(tmp_path, [entry])
    with (tmp_path / entry["csv"]).open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(PublicationError, match="csv_sha256 mismatch"):
        canonical_td_releases(tmp_path)


def test_retrospective_file_cannot_claim_live_rows(tmp_path):
    entry = _entry(tmp_path)
    _write_manifest(tmp_path, [entry])
    frame = pd.read_csv(tmp_path / entry["csv"])
    frame["prediction_mode"] = "live"
    frame.to_csv(tmp_path / entry["csv"], index=False)
    with pytest.raises(PublicationError, match="contains live"):
        read_td_release(tmp_path / entry["csv"])


def test_season_tracker_filters_mode_and_model_before_accounting(tmp_path):
    retro = _entry(tmp_path)
    live = _entry(tmp_path, week=2, mode="live")
    legacy = _entry(tmp_path, week=3, mode="live", version="legacy35")
    _write_manifest(tmp_path, [retro, live, legacy])
    paths = tuple(str(tmp_path / entry["csv"]) for entry in (retro, live, legacy))
    page._load_season_tracker.clear()
    ngs_live = page._load_season_tracker(paths, (1, 2, 3), prediction_mode="live", model_version="ngs44")
    ngs_retro = page._load_season_tracker(paths, (1, 2, 3), prediction_mode="retrospective", model_version="ngs44")
    assert ngs_live["summary"]["bets"] == ngs_retro["summary"]["bets"] == 1
    assert ngs_live["rows"].week.tolist() == [2]
    combined = tracker.aggregate_published_csvs(paths)
    duplicate_game = combined.iloc[[0, 1]].copy()
    duplicate_game.loc[:, "game_id"] = "same"
    assert len(tracker.deduplicate_player_games([duplicate_game])) == 2


def test_retrospective_page_labels_and_isolates_scorecards(tmp_path, monkeypatch):
    source = page.available_releases()[(2026, 1)]
    directory = tmp_path / "td"
    directory.mkdir()
    entry = _entry(directory)
    board = pd.read_csv(source)
    board["prediction_mode"] = "retrospective"
    board["model_version"] = "ngs44"
    board.to_csv(directory / entry["csv"], index=False)
    _write_manifest(directory, [entry])
    monkeypatch.setattr(page, "_DIR", directory)
    harness = tmp_path / "ngs_page.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{ROOT}', r'{ROOT / 'site_pages'}']\n"
        f"import page_anytime_td as p; p._DIR = __import__('pathlib').Path(r'{directory}')\n"
        "p._load_season_tracker.clear(); p.render()\n"
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception
    captions = " ".join(str(c.value) for c in at.caption)
    assert "Retrospective reconstruction; historical input availability unverified" in captions
    assert "paper tracker · retrospective reconstruction" in captions
    assert "paper tracker · live published" not in captions


def test_graders_only_visit_canonical_manifest_week(tmp_path, monkeypatch):
    from publishing import grader
    directory = tmp_path / "betting" / "anytime_td"
    directory.mkdir(parents=True)
    entry = _entry(directory, mode="live")
    _write_manifest(directory, [entry])
    (directory / "anytime_td_2026_week02_backup.csv").write_text("invalid")
    schedule = pd.DataFrame({"season": [2026], "week": [1], "game_id": ["2026_01_A_B"],
                             "home_score": [None], "away_score": [None]})
    monkeypatch.setattr(grader, "fetch_nfl_schedule", lambda season: schedule)
    assert set(grader.grade_anytime_td_releases(tmp_path)) == {"2026w01"}
    assert set(grader.grade_first_td_releases(tmp_path)) == {"2026w01"}


def test_graders_leave_retrospective_settlements_unchanged(tmp_path, monkeypatch):
    from publishing import grader
    retrospective = {"season": 2026, "week": 1, "prediction_mode": "retrospective",
                     "csv_path": tmp_path / "ngs.csv"}
    monkeypatch.setattr(grader, "canonical_td_releases", lambda directory: {(2026, 1): retrospective})
    monkeypatch.setattr(grader, "fetch_nfl_schedule", lambda season: pytest.fail("retro rows must not be regraded"))
    assert grader.grade_anytime_td_releases(tmp_path) == {
        "status": "skipped", "reason": "no published 2026 Anytime TD releases"
    }
    assert grader.grade_first_td_releases(tmp_path) == {
        "status": "skipped", "reason": "no published 2026 Anytime TD releases"
    }
