from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

import publishing.first_td_strategy as strategy
import publishing.first_td_v3 as v3
from publishing.contract import PublicationError
from publishing.td_releases import read_td_release


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


# ---------------------------------------------------------------------------
# v2 retirement and the real Week 7 v2 ledger
# ---------------------------------------------------------------------------

_REAL_V2_LEDGER = Path(strategy.DEFAULT_LEDGER_ROOT) / "2026_week07.json"
_REAL_RELEASES = Path(strategy.DEFAULT_LEDGER_ROOT).parents[1] / "releases" / "td_product_ngs_44_frozen_2025_v1"


def test_v2_is_superseded_by_a_marker_and_its_freeze_refuses(tmp_path):
    marker = json.loads((Path(strategy.DEFAULT_LEDGER_ROOT) / "SUPERSEDED.json").read_text(encoding="utf-8"))
    assert marker["status"] == "superseded"
    assert marker["superseded_by"] == "first_td_best_value_v3"
    assert marker["note"] == "Week 7 selections never tracked"
    # retired before the Thursday Night Football kickoff of Week 7
    assert pd.Timestamp(marker["superseded_at_et"]) < pd.Timestamp("2026-10-22T20:15:00-04:00")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "SUPERSEDED.json").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(PublicationError, match="superseded by first_td_best_value_v3"):
        strategy.freeze_first_td_actual_ev_v2(
            tmp_path / "x.csv", frozen_at_et="2026-10-21T10:00:00-04:00",
            kickoff_by_game={}, ledger_root=ledger,
        )
    # the real folder is retired too, so the default call refuses before touching anything
    with pytest.raises(PublicationError, match="superseded"):
        strategy.freeze_first_td_actual_ev_v2(
            tmp_path / "x.csv", frozen_at_et="2026-10-21T10:00:00-04:00", kickoff_by_game={},
        )


def test_real_week07_v2_ledger_still_verifies_and_refreezes_to_identical_bytes(tmp_path):
    payload = json.loads(_REAL_V2_LEDGER.read_text(encoding="utf-8"))
    assert payload["ledger_sha256"].startswith("290964a9")
    bets, meta = strategy.load_first_td_actual_ev_v2()
    assert len(meta["games"]) == 6 and len(bets) == 21

    # Rebuild a one-release tree around the exact frozen files; no SUPERSEDED marker there.
    source_rel = payload["games"][0]["source_release"]          # part of every frozen decision
    source_name = source_rel.split("/")[-1]
    td_dir = tmp_path / "td"
    csv_path = td_dir / source_rel
    csv_path.parent.mkdir(parents=True)
    meta_path = csv_path.with_suffix(".json")
    shutil.copyfile(_REAL_RELEASES / source_name, csv_path)
    shutil.copyfile(_REAL_RELEASES / source_name.replace(".csv", ".json"), meta_path)
    metadata_sha = hashlib.sha256(meta_path.read_bytes()).hexdigest()
    assert metadata_sha == payload["games"][0]["source_metadata_sha256"]
    (td_dir / "releases_manifest.json").write_text(json.dumps({"schema_version": 1, "releases": [{
        "season": 2026, "week": 7, "prediction_mode": "live",
        "model_version": payload["games"][0]["source_model_version"],
        "csv": source_rel, "metadata": source_rel.replace(".csv", ".json"),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "metadata_sha256": metadata_sha,
    }]}), encoding="utf-8")

    frozen_at = {game["frozen_at_et"] for game in payload["games"]}
    assert len(frozen_at) == 1
    result = strategy.freeze_first_td_actual_ev_v2(
        csv_path,
        frozen_at_et=frozen_at.pop(),
        kickoff_by_game={game["game_id"]: game["kickoff_et"] for game in payload["games"]},
        ledger_root=tmp_path / "ledger",
    )
    assert result["ledger_sha256"] == payload["ledger_sha256"]
    assert (tmp_path / "ledger" / "2026_week07.json").read_bytes() == _REAL_V2_LEDGER.read_bytes()


# ---------------------------------------------------------------------------
# v3: parity fixture, params, selector
# ---------------------------------------------------------------------------

# Shared with the model repository's tests: lambda {a: .5, b: .3, c: .2}, p_offense .94, k = 1.5.
PARITY_LAMBDAS = {"a": 0.5, "b": 0.3, "c": 0.2}
PARITY_Q = {
    "a": 0.5472305952568765,
    "b": 0.25432979783580645,
    "c": 0.13843960690731716,
}


def _write_params(path: Path, *, k=1.5, p_offense=0.94, cap=2500, **extra) -> Path:
    # TEST VALUES ONLY. The real frozen params are fitted in the model repository.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"k": k, "p_offense_2026": p_offense, "price_cap_american": cap, **extra}), encoding="utf-8")
    return path


def _params(tmp_path: Path, **kwargs):
    return v3.load_params(_write_params(tmp_path / "params.json", **kwargs))


def test_v3_sharpen_matches_the_shared_parity_fixture():
    q = v3.sharpen_lambdas(PARITY_LAMBDAS, 0.94, 1.5)
    assert q == pytest.approx(PARITY_Q, rel=1e-12)
    assert sum(q.values()) == pytest.approx(0.94, rel=1e-12)


def test_v3_k_one_is_the_flat_lambda_share_and_mass_sums_to_p_offense():
    q = v3.sharpen_lambdas(PARITY_LAMBDAS, 0.94, 1.0)
    assert q == pytest.approx({"a": 0.47, "b": 0.282, "c": 0.188}, rel=1e-12)
    assert sum(q.values()) == pytest.approx(0.94, rel=1e-12)
    with pytest.raises(ValueError):
        v3.sharpen_lambdas({"a": 0.0}, 0.94, 1.5)
    with pytest.raises(ValueError):
        v3.sharpen_lambdas({"a": float("nan"), "b": 0.1}, 0.94, 1.5)


def test_v3_params_load_validate_and_hash(tmp_path):
    params = _params(tmp_path)
    assert (params.k, params.p_offense, params.price_cap) == (1.5, 0.94, 2500)
    # the digest is over canonical JSON, so reformatting the file does not change it
    reformatted = tmp_path / "other.json"
    reformatted.write_text(json.dumps(json.loads((tmp_path / "params.json").read_text()), indent=4) + "\r\n", encoding="utf-8")
    assert v3.load_params(reformatted).sha256 == params.sha256
    assert v3.load_params(_write_params(tmp_path / "k.json", k=1.6)).sha256 != params.sha256
    assert v3.load_params(_write_params(tmp_path / "cap.json", cap="+2000")).price_cap == 2000
    # the model repository's own spelling, and an explicit null meaning no cap
    assert v3.load_params(_write_params(tmp_path / "m.json", cap=None)).price_cap is None
    modelrepo = tmp_path / "modelrepo.json"
    modelrepo.write_text(json.dumps({"k": 1.1, "p_offense_2026": 0.94, "cap_american": 599, "schema_version": 1}), encoding="utf-8")
    assert v3.load_params(modelrepo).price_cap == 599
    base = {"k": 1.5, "p_offense_2026": 0.94, "price_cap_american": 2500}
    for change in ({"k": 0}, {"k": "x"}, {"p_offense_2026": 1.5}, {"price_cap_american": 50}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({**base, **change}), encoding="utf-8")
        with pytest.raises(PublicationError):
            v3.load_params(path)
    with pytest.raises(PublicationError, match="not found"):
        v3.load_params(tmp_path / "missing.json")
    no_cap = tmp_path / "nocap.json"
    no_cap.write_text(json.dumps({"k": 1.5, "p_offense_2026": 0.94}), encoding="utf-8")
    with pytest.raises(PublicationError, match="price cap"):
        v3.load_params(no_cap)


def _record(game_id: str, lambdas: dict) -> dict:
    record = {
        "schema_version": 1, "game_id": game_id, "frozen_at_et": "2026-10-20T19:15:00",
        "candidate_player_ids": sorted(lambdas), "quoted_player_ids": sorted(lambdas),
        "excluded_player_ids": [], "candidate_lambdas": dict(lambdas), "missing_player_ids": [],
        "complete": True, "total_lambda": float(sum(lambdas.values())), "unquoted_lambda_remainder": 0.0,
        "status": "frozen_complete",
    }
    record["record_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return record


def _rows(game_id: str, players: list[tuple], **overrides) -> pd.DataFrame:
    """players: (player_id, lambda, american price or None, bet_eligible)."""
    return pd.DataFrame([{
        "season": 2026, "week": 7, "game_id": game_id, "player_id": pid,
        "player_display_name": f"Player {pid}", "position": "WR", "team": "AAA", "opponent_team": "BBB",
        "lambda": lam, "p_first": lam, "first_amer": price, "bet_eligible": eligible,
        "snapped_at_et": "2026-10-20 18:52:50", "kickoff_et": "2026-10-25 13:00:00",
        "model_version": "frozen-test-model", "prediction_mode": "live", **overrides,
    } for pid, lam, price, eligible in players])


# k = 1 and p_offense = 1 with dyadic lambdas keep every q and return exactly representable.
def _exact_params(tmp_path, cap=2500):
    return _params(tmp_path, k=1.0, p_offense=1.0, cap=cap)


def _select(tmp_path, players, cap=2500, **row_overrides):
    rows = _rows("g", players, **row_overrides)
    mass = _record("g", {pid: lam for pid, lam, *_ in players})
    return strategy.select_first_td_best_value_v3(rows, mass, _exact_params(tmp_path, cap))


def test_v3_cap_excludes_a_higher_expected_return_long_shot(tmp_path):
    players = [
        ("a", 0.5, 100, True),     # return 0.0, not above zero
        ("b", 0.25, 500, True),    # +50%
        ("c", 0.125, 1000, True),  # +37.5%
        ("d", 0.125, 3500, True),  # +350%, but priced above the +2500 cap
    ]
    bets, exclusions = _select(tmp_path, players)
    assert [bet["player_id"] for bet in bets] == ["b"]
    assert exclusions == {"price_above_cap": 1}
    assert bets[0]["expected_return"] == pytest.approx(0.5)
    assert bets[0]["p_first_v3"] == 0.25 and bets[0]["stake_units"] == 1.0
    # with the cap lifted to the long shot's price it is allowed, and wins on return
    bets, _ = _select(tmp_path, players, cap=3500)
    assert [bet["player_id"] for bet in bets] == ["d"]
    # a null cap means no cap at all
    bets, exclusions = _select(tmp_path, players, cap=None)
    assert [bet["player_id"] for bet in bets] == ["d"] and exclusions == {}


def test_v3_picks_at_most_one_player_per_game_and_records_zero_pick_games(tmp_path):
    many = [("a", 0.5, 400, True), ("b", 0.25, 500, True), ("c", 0.25, 600, True)]
    bets, _ = _select(tmp_path, many)
    assert len(bets) == 1
    none_positive = [("a", 0.5, 100, True), ("b", 0.5, 100, True)]
    bets, exclusions = _select(tmp_path, none_positive)
    assert bets == [] and exclusions == {}


def test_v3_tie_break_is_return_then_probability_then_player_id(tmp_path):
    # equal return (+100%): the larger model chance wins
    bets, _ = _select(tmp_path, [("f", 0.25, 700, True), ("e", 0.5, 300, True), ("z", 0.25, 100, True)])
    assert [bet["player_id"] for bet in bets] == ["e"]
    # equal return and equal chance: the lowest player_id wins, whatever the row order
    for order in ([("i", 0.25, 700, True), ("h", 0.25, 700, True), ("j", 0.5, 100, True)],
                  [("h", 0.25, 700, True), ("i", 0.25, 700, True), ("j", 0.5, 100, True)]):
        bets, _ = _select(tmp_path, order)
        assert [bet["player_id"] for bet in bets] == ["h"]


def test_v3_keeps_v2_exclusions_and_has_no_pool_or_no_vig_requirement(tmp_path):
    players = [
        ("m", 0.25, 700, False),   # not eligible: would win on return otherwise
        ("n", 0.25, 500, True),
        ("o", 0.25, 600, True),
        ("p", 0.25, 5, True),      # invalid American price
    ]
    rows = _rows("g", players, bet_eligible_first=False, first_quote_pool_complete=False)
    rows.loc[rows.player_id.eq("o"), "player_id"] = "not-in-mass"
    mass = _record("g", {"m": 0.25, "n": 0.25, "o": 0.25, "p": 0.25})
    bets, exclusions = strategy.select_first_td_best_value_v3(rows, mass, _exact_params(tmp_path))
    assert [bet["player_id"] for bet in bets] == ["n"]
    assert exclusions == {
        "identity_history_or_availability_exclusion": 1,
        "player_missing_from_frozen_model_mass": 1,
        "invalid_american_price": 1,
    }


def test_v3_release_probability_is_used_and_a_disagreement_is_a_mass_mismatch(tmp_path):
    players = [("a", 0.5, 400, True), ("b", 0.5, 300, True)]
    mass = _record("g", {"a": 0.5, "b": 0.5})
    params = _exact_params(tmp_path)
    rows = _rows("g", players)
    rows["p_first_v3"] = [0.5, 0.5 + 1e-10]
    bets, exclusions = strategy.select_first_td_best_value_v3(rows, mass, params)
    assert [bet["player_id"] for bet in bets] == ["a"] and exclusions == {}
    rows["p_first_v3"] = [0.5 + 1e-8, 0.5]
    bets, exclusions = strategy.select_first_td_best_value_v3(rows, mass, params)
    assert [bet["player_id"] for bet in bets] == ["b"]
    assert exclusions == {"model_mass_mismatch": 1}
    # a missing release value, or a lambda that disagrees with the frozen mass, is a mismatch too
    rows["p_first_v3"] = [float("nan"), 0.5]
    assert strategy.select_first_td_best_value_v3(rows, mass, params)[1] == {"model_mass_mismatch": 1}
    rows = _rows("g", players)
    rows.loc[0, "lambda"] = 0.4
    assert strategy.select_first_td_best_value_v3(rows, mass, params)[1] == {"model_mass_mismatch": 1}


def test_v3_attach_adds_probability_and_the_single_game_pick(tmp_path):
    params_path = _write_params(tmp_path / "params.json", k=1.0, p_offense=1.0, cap=2500)
    players = [("a", 0.5, 100, True), ("b", 0.25, 500, True), ("c", 0.25, None, True)]
    board = pd.concat([_rows("g1", players), _rows("g2", [("x", 1.0, 200, True)])], ignore_index=True)
    metadata = {"first_td_candidate_mass": {
        "g1": _record("g1", {"a": 0.5, "b": 0.25, "c": 0.25}),
        "g2": {**_record("g2", {"x": 1.0}), "record_sha256": "0" * 64},  # tampered record
    }}
    out = strategy.attach_first_td_v3(board, metadata=metadata, params_path=params_path)
    assert out.p_first_v3.iloc[:3].tolist() == [0.5, 0.25, 0.25]   # unpriced player still has a chance
    assert out.p_first_v3.iloc[3:].isna().all()                      # no intact mass: blank
    assert out.first_td_v3_pick.tolist() == [False, True, False, False]
    assert out.first_td_v3_over_cap.tolist() == [False, False, False, False]
    capped = strategy.attach_first_td_v3(
        board, metadata=metadata, params_path=_write_params(tmp_path / "cap.json", k=1.0, p_offense=1.0, cap=400),
    )
    assert capped.first_td_v3_over_cap.tolist() == [False, True, False, False]   # b is +500, positive, over +400
    assert capped.first_td_v3_pick.tolist() == [False, False, False, False]
    assert "p_first_v3" not in board.columns                         # input untouched
    with pytest.raises(PublicationError, match="not found"):
        strategy.attach_first_td_v3(board, metadata=metadata, params_path=tmp_path / "nope.json")


# ---------------------------------------------------------------------------
# v3 freeze: a real manifest tree, the CLI, slate by slate
# ---------------------------------------------------------------------------

PUBLISH_A = "2026-10-20T19:15:00"
FROZEN_A = "2026-10-20T20:00:00-04:00"


def _write_release(
    root: Path, slate: str, games: dict, *, publish: str, snapped: str,
    kickoffs: dict, week: int = 7,
) -> Path:
    """Write one live release (csv, metadata, manifest entry) under root/betting/anytime_td."""
    td = root / "betting" / "anytime_td"
    (td / "releases").mkdir(parents=True, exist_ok=True)
    frames, masses = [], {}
    for game_id, players in games.items():
        frames.append(_rows(
            game_id, players, week=week, snapped_at_et=snapped, kickoff_et=kickoffs[game_id],
        ))
        masses[game_id] = _record(game_id, {pid: lam for pid, lam, *_ in players})
    csv_path = td / "releases" / f"anytime_td_2026_week{week:02d}_{slate}.csv"
    meta_path = csv_path.with_suffix(".json")
    pd.concat(frames, ignore_index=True).to_csv(csv_path, index=False, lineterminator="\n")
    meta_path.write_text(json.dumps({
        "season": 2026, "week": week, "prediction_mode": "live", "release_mode": "live",
        "model_version": "frozen-test-model", "publish_now_et": publish,
        "model_bundle_sha256": "c" * 64, "first_td_candidate_mass": masses,
    }), encoding="utf-8")
    _register(root, csv_path, week)
    return csv_path


def _register(root: Path, csv_path: Path, week: int = 7) -> None:
    """(Re)write the manifest entry for a week so its hashes match the files on disk."""
    td = root / "betting" / "anytime_td"
    meta_path = csv_path.with_suffix(".json")
    manifest_path = td / "releases_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": 1, "releases": []}
    manifest["releases"] = [r for r in manifest["releases"] if r["week"] != week] + [{
        "season": 2026, "week": week, "prediction_mode": "live", "model_version": "frozen-test-model",
        "csv": f"releases/{csv_path.name}", "metadata": f"releases/{meta_path.name}",
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
    }]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _v3_dir(root: Path) -> Path:
    return root / "betting" / "anytime_td" / "strategies" / "first_td_best_value_v3"


def _freeze(root: Path, csv_path: Path, frozen_at: str = FROZEN_A, **kwargs):
    board = read_td_release(csv_path)
    return strategy.freeze_first_td_best_value_v3(
        csv_path, frozen_at_et=frozen_at, kickoff_by_game=strategy.kickoffs_from_release(board),
        ledger_root=_v3_dir(root), **kwargs,
    )


def _ledger_file(root: Path) -> Path:
    return _v3_dir(root) / "2026_week07.json"


def _ledger(root: Path) -> dict:
    return json.loads(_ledger_file(root).read_text(encoding="utf-8"))


G1 = [("a", 0.5, 100, True), ("b", 0.25, 500, True), ("c", 0.125, 1000, True), ("d", 0.125, 3500, True)]
G2 = [("e", 0.5, 300, True), ("f", 0.25, 700, True), ("g", 0.25, 100, True)]
G3 = [("k", 0.5, 100, True), ("l", 0.5, 100, True)]            # nothing above zero: a zero-pick game
G4 = [("m", 0.5, None, True), ("n", 0.5, None, True)]          # not priced yet
FAR = "2026-10-25 13:00:00"


def _first_release(tmp_path):
    _write_params(_v3_dir(tmp_path) / "params.json", k=1.0, p_offense=1.0, cap=2500)
    return _write_release(
        tmp_path, "slate_a", {"g1": G1, "g2": G2, "g3": G3, "g4": G4},
        publish=PUBLISH_A, snapped="2026-10-20 18:52:50", kickoffs={g: FAR for g in ("g1", "g2", "g3", "g4")},
    )


def test_v3_freeze_records_one_pick_per_priced_game_and_zero_pick_games(tmp_path):
    csv_path = _first_release(tmp_path)
    result = _freeze(tmp_path, csv_path)
    assert (result["added_games"], result["selected_bets"], result["zero_pick_games"]) == (3, 2, 1)
    assert result["refused_started_games"] == []
    ledger = _ledger(tmp_path)
    assert ledger["strategy_id"] == "first_td_best_value_v3"
    by_game = {game["game_id"]: game for game in ledger["games"]}
    assert set(by_game) == {"g1", "g2", "g3"}                       # g4 has no price: not locked
    assert [b["player_id"] for b in by_game["g1"]["bets"]] == ["b"]   # d is above the cap
    assert by_game["g1"]["exclusion_counts"] == {"price_above_cap": 1}
    assert [b["player_id"] for b in by_game["g2"]["bets"]] == ["e"]   # return tie with f, larger chance wins
    assert by_game["g3"]["selected_bet_count"] == 0 and by_game["g3"]["bets"] == []
    params = v3.load_params(_v3_dir(tmp_path) / "params.json")
    assert {game["params_sha256"] for game in ledger["games"]} == {params.sha256} == {result["params_sha256"]}
    # the same ledger is readable by the loader, with the v3 eligibility flag and unsettled outcomes
    bets, meta = strategy.load_first_td_best_value_v3(ledger_root=_v3_dir(tmp_path))
    assert sorted(bets.player_id) == ["b", "e"] and bets.bet_eligible_first_best_value_v3.all()
    assert meta["strategy_id"] == "first_td_best_value_v3" and len(meta["games"]) == 3


def test_v3_freeze_is_idempotent_and_a_changed_input_raises_inputs_changed(tmp_path):
    csv_path = _first_release(tmp_path)
    first = _freeze(tmp_path, csv_path)
    before = _ledger_file(tmp_path).read_bytes()
    again = _freeze(tmp_path, csv_path, frozen_at="2026-10-20T20:05:00-04:00")
    assert (again["added_games"], again["skipped_locked_games"]) == (0, 3)
    assert again["ledger_sha256"] == first["ledger_sha256"]
    assert _ledger_file(tmp_path).read_bytes() == before

    # same release, one frozen game's price edited: inputs changed
    board = pd.read_csv(csv_path)
    board.loc[board.player_id.eq("e"), "first_amer"] = 350
    board.to_csv(csv_path, index=False, lineterminator="\n")
    _register(tmp_path, csv_path)
    with pytest.raises(PublicationError, match="inputs changed"):
        _freeze(tmp_path, csv_path)
    assert _ledger_file(tmp_path).read_bytes() == before


def test_v3_changed_params_copy_raises_inputs_changed(tmp_path):
    csv_path = _first_release(tmp_path)
    _freeze(tmp_path, csv_path)
    before = _ledger_file(tmp_path).read_bytes()
    _write_params(_v3_dir(tmp_path) / "params.json", k=1.2, p_offense=1.0, cap=2500)
    with pytest.raises(PublicationError, match="inputs changed"):
        _freeze(tmp_path, csv_path)
    assert _ledger_file(tmp_path).read_bytes() == before


def test_v3_freeze_needs_the_params_copy_and_never_invents_one(tmp_path):
    csv_path = _write_release(
        tmp_path, "slate_a", {"g1": G1}, publish=PUBLISH_A, snapped="2026-10-20 18:52:50", kickoffs={"g1": FAR},
    )
    with pytest.raises(PublicationError, match="params file not found"):
        _freeze(tmp_path, csv_path)
    assert not _ledger_file(tmp_path).exists()
    assert not (_v3_dir(tmp_path) / "params.json").exists()


def test_v3_freeze_refuses_games_at_or_past_kickoff_but_still_freezes_the_rest(tmp_path):
    _write_params(_v3_dir(tmp_path) / "params.json", k=1.0, p_offense=1.0, cap=2500)
    csv_path = _write_release(
        tmp_path, "slate_a", {"g1": G1, "g2": G2}, publish=PUBLISH_A, snapped="2026-10-20 18:52:50",
        kickoffs={"g1": "2026-10-20 19:45:00", "g2": FAR},
    )
    result = _freeze(tmp_path, csv_path, frozen_at="2026-10-20T19:50:00-04:00")
    assert result["refused_started_games"] == ["g1"]
    assert (result["added_games"], result["selected_bets"]) == (1, 1)
    assert [game["game_id"] for game in _ledger(tmp_path)["games"]] == ["g2"]   # never retroactive
    # exactly at kickoff is also refused
    at_kickoff = _freeze(tmp_path, csv_path, frozen_at="2026-10-20T19:45:00-04:00")
    assert at_kickoff["refused_started_games"] == ["g1"] and at_kickoff["added_games"] == 0


def test_v3_freeze_works_slate_by_slate_and_leaves_frozen_games_immutable(tmp_path):
    first = _first_release(tmp_path)
    _freeze(tmp_path, first)
    frozen_games = {game["game_id"]: game for game in _ledger(tmp_path)["games"]}

    # Later paste: a new release that re-prices the slate (g4 now priced) and adds a game that
    # has already kicked off (g5) next to one that has not (g6).
    second = _write_release(
        tmp_path, "slate_b",
        {
            "g1": [("a", 0.4, 120, True), ("b", 0.3, 450, True), ("c", 0.15, 900, True), ("d", 0.15, 3000, True)],
            "g2": G2, "g3": G3,
            "g4": [("m", 0.5, 250, True), ("n", 0.5, 400, True)],
            "g5": G2,
            "g6": [("s", 0.5, 500, True), ("t", 0.5, 150, True)],
        },
        publish="2026-10-21T09:00:00", snapped="2026-10-21 08:52:00",
        kickoffs={"g1": FAR, "g2": FAR, "g3": FAR, "g4": FAR, "g5": "2026-10-21 09:30:00", "g6": FAR},
    )
    result = _freeze(tmp_path, second, frozen_at="2026-10-21T10:00:00-04:00")
    assert result["added_games"] == 2 and result["skipped_locked_games"] == 3
    assert result["refused_started_games"] == ["g5"]
    by_game = {game["game_id"]: game for game in _ledger(tmp_path)["games"]}
    assert set(by_game) == {"g1", "g2", "g3", "g4", "g6"}
    for game_id, decision in frozen_games.items():
        assert by_game[game_id] == decision                           # earlier decisions untouched
    assert [b["player_id"] for b in by_game["g4"]["bets"]] == ["n"]
    assert [b["player_id"] for b in by_game["g6"]["bets"]] == ["s"]
    assert by_game["g4"]["source_release"].endswith("slate_b.csv")

    # a third run on the same release changes nothing
    snapshot = _ledger_file(tmp_path).read_bytes()
    third = _freeze(tmp_path, second, frozen_at="2026-10-21T10:05:00-04:00")
    assert (third["added_games"], third["skipped_locked_games"]) == (0, 5)
    assert _ledger_file(tmp_path).read_bytes() == snapshot

    # an edit to a frozen game inside the same release still raises
    board = pd.read_csv(second)
    board.loc[board.player_id.eq("n"), "first_amer"] = 410
    board.to_csv(second, index=False, lineterminator="\n")
    _register(tmp_path, second)
    with pytest.raises(PublicationError, match="inputs changed"):
        _freeze(tmp_path, second, frozen_at="2026-10-21T10:10:00-04:00")
    assert _ledger_file(tmp_path).read_bytes() == snapshot


def test_v3_freeze_cli_freezes_the_active_release_and_reports_errors(tmp_path, monkeypatch, capsys):
    from publishing import cli

    csv_path = _write_release(
        tmp_path, "slate_a", {"g1": G1, "g2": G2}, publish=PUBLISH_A, snapped="2026-10-20 18:52:50",
        kickoffs={"g1": FAR, "g2": "2026-10-22 20:15:00"},
    )
    monkeypatch.setattr(cli, "_now_et", lambda: "2026-10-20T21:00:00-04:00")
    args = ["--root", str(tmp_path), "freeze-first-td-v3", "--season", "2026", "--week", "7"]

    # no frozen params copy yet: a clear error, nothing written
    assert cli.main(args) == 1
    assert "params file not found" in capsys.readouterr().out
    assert not _ledger_file(tmp_path).exists()

    _write_params(_v3_dir(tmp_path) / "params.json", k=1.0, p_offense=1.0, cap=2500)
    assert cli.main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["added_games"], out["selected_bets"], out["refused_started_games"]) == (2, 2, [])
    assert csv_path.name in _ledger(tmp_path)["games"][0]["source_release"]
    assert cli.main(args) == 0                                       # idempotent
    assert json.loads(capsys.readouterr().out)["added_games"] == 0

    # after Thursday kickoff a not-yet-frozen game is refused and reported on stderr
    _write_release(
        tmp_path, "slate_b", {"g1": G1, "g2": G2, "g3": G3}, publish="2026-10-22T08:00:00",
        snapped="2026-10-22 07:50:00", kickoffs={"g1": FAR, "g2": "2026-10-22 20:15:00", "g3": "2026-10-22 20:15:00"},
    )
    monkeypatch.setattr(cli, "_now_et", lambda: "2026-10-22T21:00:00-04:00")
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["refused_started_games"] == ["g3"]
    assert "g3" in captured.err

    # tracking starts with Week 7
    assert cli.main(["--root", str(tmp_path), "freeze-first-td-v3", "--season", "2026", "--week", "6"]) == 1
    assert "starts with the 2026 Week 7" in capsys.readouterr().out
