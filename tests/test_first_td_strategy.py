from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import publishing.first_td_strategy as strategy
from publishing.contract import PublicationError


def _release_fixture(tmp_path: Path, monkeypatch, frame: pd.DataFrame):
    source = tmp_path / "week07.csv"
    source.write_text("fixture\n", encoding="utf-8")
    metadata_path = tmp_path / "week07.json"
    metadata = {
        "season": 2026,
        "week": 7,
        "release_mode": "live",
        "publish_now_et": "2026-10-20T19:15:00",
        "first_td_candidate_mass": {
            game_id: {
                "complete": True,
                "status": "frozen_complete",
                "candidate_lambdas": {str(player_id): 0.1 for player_id in rows.player_id},
                "record_sha256": "a" * 64,
            }
            for game_id, rows in frame.groupby("game_id")
        },
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    entry = {
        "metadata_path": metadata_path,
        "metadata_sha256": "b" * 64,
        "csv": "week07.csv",
        "season": 2026,
        "week": 7,
        "prediction_mode": "live",
        "model_version": "frozen-test-model",
    }
    monkeypatch.setattr(strategy, "release_for_path", lambda path: entry)
    monkeypatch.setattr(strategy, "read_td_release", lambda path: frame.copy())
    return source, metadata


def _quotes():
    rows = [
        ("g1", "a", 0.30, 300, True),
        ("g1", "b", 0.20, 300, True),
        ("g1", "c", 0.25, 300, True),  # exactly zero EV
        ("g2", "d", 0.10, 100, True),  # verified price, zero picks
        ("g3", "e", float("nan"), 100, True),  # invalid probability, zero picks
        ("g4", "f", 0.50, 0, True),  # invalid price cannot lock a game
        ("g5", "h", 0.30, 300, False),  # generic identity/history/availability exclusion
    ]
    return pd.DataFrame([{
        "season": 2026,
        "week": 7,
        "game_id": game_id,
        "player_id": player_id,
        "player_display_name": f"Player {player_id}",
        "team": "AAA",
        "opponent_team": "BBB",
        "p_first": probability,
        "first_amer": price,
        "snapped_at_et": "2026-10-20T19:10:00-04:00",
        "bet_eligible": eligible,
        "model_version": "frozen-test-model",
    } for game_id, player_id, probability, price, eligible in rows])


def test_actual_ev_rule_uses_actual_price_and_strict_positive_return():
    from site_pages.attd_tracker import qualifies_first_td_actual_ev

    qualified = qualifies_first_td_actual_ev(
        pd.Series([0.30, 0.25, 0.20, 1.01, float("nan")]),
        pd.Series([300, 300, "bad", 300, 300]),
    )
    assert qualified.tolist() == [True, False, False, False, False]


def test_actual_ev_tracker_does_not_need_no_vig_or_v1_eligibility():
    from site_pages import attd_tracker as tracker

    rows = pd.DataFrame([{
        "season": 2026, "week": 7, "game_id": "g1", "player_id": "p1",
        "p_first": 0.30, "first_amer": 300, "scored_first": 1,
        "settlement_status_first": "settled", "bet_eligible": True,
        "bet_eligible_first": False, "bet_eligible_first_actual_v2": True,
    }])
    paper = tracker.season_tracker(
        rows,
        model_probability_col="p_first",
        book_probability_col=None,
        book_price_col="first_amer",
        outcome_col="scored_first",
        qualifies=lambda frame: tracker.qualifies_first_td_actual_ev(
            frame["_model_probability"], frame["_book_price"],
        ),
        eligibility_col="bet_eligible_first_actual_v2",
    )
    assert paper["summary"]["bets"] == 1
    assert paper["summary"]["wins"] == 1
    assert paper["summary"]["net_units"] == 3.0


def test_freeze_records_positive_ev_and_zero_pick_games_idempotently(tmp_path, monkeypatch):
    frame = _quotes()
    source, _ = _release_fixture(tmp_path, monkeypatch, frame)
    root = tmp_path / "ledger"
    kickoffs = {game: "2026-10-20T20:00:00-04:00" for game in ("g1", "g2", "g3", "g4", "g5")}

    first = strategy.freeze_first_td_actual_ev_v2(
        source,
        frozen_at_et="2026-10-20T19:30:00-04:00",
        kickoff_by_game=kickoffs,
        ledger_root=root,
    )
    assert first["added_games"] == 4
    assert first["selected_bets"] == 1
    assert first["zero_pick_games"] == 3
    ledger = json.loads(Path(first["ledger_path"]).read_text(encoding="utf-8"))
    by_game = {game["game_id"]: game for game in ledger["games"]}
    assert [bet["player_id"] for bet in by_game["g1"]["bets"]] == ["a"]
    assert by_game["g2"]["selected_bet_count"] == 0
    assert by_game["g3"]["exclusion_counts"]["invalid_model_probability"] == 1
    assert by_game["g5"]["exclusion_counts"]["identity_history_or_availability_exclusion"] == 1
    assert "g4" not in by_game  # invalid price does not count as a validated quote

    again = strategy.freeze_first_td_actual_ev_v2(
        source,
        frozen_at_et="2026-10-20T19:31:00-04:00",
        kickoff_by_game=kickoffs,
        ledger_root=root,
    )
    assert again["added_games"] == 0
    assert again["skipped_locked_games"] == 4
    assert again["ledger_sha256"] == first["ledger_sha256"]

    changed = frame.copy()
    changed.loc[changed.player_id.eq("a"), "p_first"] = 0.31
    monkeypatch.setattr(strategy, "read_td_release", lambda path: changed.copy())
    with pytest.raises(PublicationError, match="inputs changed"):
        strategy.freeze_first_td_actual_ev_v2(
            source,
            frozen_at_et="2026-10-20T19:32:00-04:00",
            kickoff_by_game=kickoffs,
            ledger_root=root,
        )


@pytest.mark.parametrize(
    "frozen_at,capture,kickoff,expected",
    [
        ("2026-10-20T19:00:00-04:00", "2026-10-20T19:10:00-04:00", "2026-10-20T20:00:00-04:00", "precedes"),
        ("2026-10-20T19:30:00-04:00", "2026-10-20T20:01:00-04:00", "2026-10-20T20:00:00-04:00", "post-kickoff"),
        ("2026-10-20T19:30:00-04:00", "2026-10-20T19:31:00-04:00", "2026-10-20T20:00:00-04:00", "post-freeze"),
        ("2026-10-20T19:30:00-04:00", "2026-10-20T19:20:00-04:00", "2026-10-20T20:00:00-04:00", "after release publication"),
    ],
)
def test_freeze_rejects_invalid_time_cutoffs(tmp_path, monkeypatch, frozen_at, capture, kickoff, expected):
    frame = _quotes().iloc[[0]].copy()
    frame.loc[:, "snapped_at_et"] = capture
    source, _ = _release_fixture(tmp_path, monkeypatch, frame)
    with pytest.raises(PublicationError, match=expected):
        strategy.freeze_first_td_actual_ev_v2(
            source,
            frozen_at_et=frozen_at,
            kickoff_by_game={"g1": kickoff},
            ledger_root=tmp_path / "ledger",
        )


def test_grading_outcomes_attach_without_changing_frozen_selection(tmp_path, monkeypatch):
    frame = _quotes().iloc[[0]].copy()
    source, _ = _release_fixture(tmp_path, monkeypatch, frame)
    root = tmp_path / "ledger"
    frozen = strategy.freeze_first_td_actual_ev_v2(
        source,
        frozen_at_et="2026-10-20T19:30:00-04:00",
        kickoff_by_game={"g1": "2026-10-20T20:00:00-04:00"},
        ledger_root=root,
    )
    before = Path(frozen["ledger_path"]).read_bytes()
    sidecar = source.with_name("first_td_results_2026_week07.json")
    sidecar.write_text(json.dumps({
        "schema_version": 1,
        "season": 2026,
        "week": 7,
        "source_release": source.name,
        "games": [{"game_id": "g1", "player_settlements": {
            "a": {"status": "settled", "scored_first": 1.0},
        }}],
    }), encoding="utf-8")
    bets, metadata = strategy.load_first_td_actual_ev_v2(
        ledger_root=root,
        releases={(2026, 7): source},
    )
    assert bets.loc[0, "scored_first"] == 1.0
    assert bets.loc[0, "settlement_status_first"] == "settled"
    assert metadata["games"][0]["week"] == 7
    assert Path(frozen["ledger_path"]).read_bytes() == before


def test_published_board_rankings_cover_ties_outside_board_void_and_pending():
    board = pd.DataFrame([
        {"game_id": "g1", "player_id": "a", "player_display_name": "A", "team": "AAA", "p_first": 0.4, "settlement_status_first": "void"},
        {"game_id": "g1", "player_id": "b", "player_display_name": "B", "team": "BBB", "p_first": 0.4},
        {"game_id": "g1", "player_id": "c", "player_display_name": "C", "team": "AAA", "p_first": 0.2},
        {"game_id": "g2", "player_id": "d", "player_display_name": "D", "team": "AAA", "p_first": 0.6},
        {"game_id": "g2", "player_id": "e", "player_display_name": "E", "team": "BBB", "p_first": 0.4},
        {"game_id": "g3", "player_id": "f", "player_display_name": "F", "team": "AAA", "p_first": 0.7},
        {"game_id": "g4", "player_id": "g", "player_display_name": "G", "team": "AAA", "p_first": 0.5},
    ])
    results = {
        "g1": {"status": "resolved", "outcome_kind": "offense_skill", "scorer_player_id": "b", "scorer_name": "B", "scorer_team": "BBB", "scorer_on_board": True},
        "g2": {"status": "resolved", "outcome_kind": "offense_skill", "scorer_player_id": "outside", "scorer_name": "Outside scorer", "scorer_on_board": False},
        "g3": {"status": "resolved", "outcome_kind": "no_touchdown"},
        "g4": {"status": "pending", "outcome_kind": "unresolved"},
    }
    table, summary = strategy.published_board_rankings(board, results)
    by_game = table.set_index("Game")
    assert "A · AAA" in by_game.loc["g1", "Top 1"]
    assert by_game.loc["g1", "Top 1 result"] == "Miss"
    assert by_game.loc["g1", "Top 3 result"] == "Hit"
    assert by_game.loc["g2", "Top 1 result"] == "Miss"
    assert "outside board" in by_game.loc["g2", "First TD result"]
    assert by_game.loc["g3", "Top 1 result"] == "Miss"
    assert by_game.loc["g4", "Top 1 result"] == "Awaiting evidence"
    assert summary == {
        "ranked_games": 4,
        "graded_games": 3,
        "pending_games": 1,
        "unavailable_games": 0,
        "top1_hits": 0,
        "top3_hits": 1,
    }


def test_published_board_ranking_marks_invalid_model_mass_unavailable():
    board = pd.DataFrame([
        {"game_id": "g1", "player_id": "a", "player_display_name": "A", "p_first": 0.5},
        {"game_id": "g1", "player_id": "b", "player_display_name": "B", "p_first": float("nan")},
    ])
    table, summary = strategy.published_board_rankings(board)
    assert table.loc[0, "Top 1"] == "Model probability unavailable"
    assert summary["unavailable_games"] == 1
    assert summary["graded_games"] == 0
