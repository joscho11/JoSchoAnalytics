"""Anytime TDs demo page. Hermetic APP_OFFLINE=1."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))

import page_anytime_td as page
from publishing import first_td_v3
from publishing.td_releases import read_td_release


@pytest.fixture
def v3_params(tmp_path, monkeypatch):
    """Point the page at TEST v3 params. The real frozen file is fitted in the model repository."""
    path = tmp_path / "v3_params" / "params.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"k": 1.5, "p_offense_2026": 0.94, "price_cap_american": 2500}), encoding="utf-8")
    monkeypatch.setattr(first_td_v3, "PARAMS_PATH", path)
    return path


def _render(tmp_path, week=None):
    seed_week = "" if week is None else f"import streamlit as st; st.session_state['atd_week'] = {week}\n"
    harness = tmp_path / "h_anytime_td.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        f"{seed_week}import page_anytime_td as p\np.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _pick_props_matchup(at, matchup, week=1):
    """Select a game in the 2+ TD / First TD dropdown (default is Recommended)."""
    at.selectbox(key=f"atd_props_matchup_2026_{week}").set_value(matchup).run()
    return at


def test_anytime_td_renders_and_owns_controls(tmp_path):
    at = _render(tmp_path)
    keys = {getattr(w, "key", None) for w in list(at.selectbox)}
    assert {"atd_year", "atd_week"}.issubset(keys), keys
    assert len(at.tabs) == 0
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["atd_year"] == 2026
    latest = page.default_release(list(page.available_releases()))
    assert controls["atd_week"] == latest[1]
    titles = " ".join(str(t.value) for t in at.title)
    assert "Touchdown Props" in titles
    captions = " ".join(str(c.value) for c in at.caption)
    md = " ".join(str(item.value) for item in at.markdown)
    blob = captions + md + " ".join(str(item.value) for item in at.info)
    assert "Passing TDs are out" in blob or "rushing or receiving" in blob
    assert "not even money" in blob
    assert "Bet responsibly" in blob
    assert "closer in 5" in blob
    assert "No odds API is used" in blob
    assert "DraftKings" in blob
    assert "Eight players" not in blob
    assert any("How to read this board" in str(e.label) for e in at.expander)
    assert any(getattr(w, "key", None) == f"atd_matchup_{latest[0]}_{latest[1]}" for w in at.selectbox)
    assert any(getattr(w, "key", None) == f"atd_view_{latest[0]}_{latest[1]}" for w in at.segmented_control)
    assert any(getattr(w, "key", None) == "atd_search" for w in at.text_input)
    metric_labels = {str(metric.label) for metric in at.metric}
    assert {"Net units", "ROI", "Record", "Approx. 95% ROI range"} <= metric_labels
    if latest == (2026, 4):
        assert len(at.metric) == 8
        assert all(sum(str(metric.label) == label for metric in at.metric) == 2
                   for label in ("Net units", "ROI", "Record", "Approx. 95% ROI range"))
        captions = " ".join(str(c.value) for c in at.caption)
        headings = " ".join(str(item.value) for item in at.markdown)
        assert "Selected week" in captions
        assert "Season to date" in headings and "Week 4" in headings
        assert "Season totals include retrospective Weeks 1, 2, 3" in captions
        releases = page.available_releases()
        season_rows = pd.concat([
            pd.read_csv(path) for (season, week), path in releases.items()
            if season == 2026 and week <= 4
        ], ignore_index=True)
        assert set(season_rows.week) == {1, 2, 3, 4}
        scopes = (season_rows, pd.read_csv(releases[(2026, 4)]))
        expected_summaries = [
            page.tracker.strategy_summary(
                page.tracker.prepare_paper_bets(rows),
                threshold=page.tracker.ATTD_VALUE_THRESHOLD,
            )
            for rows in scopes
        ]
        assert [str(metric.value) for metric in at.metric if metric.label == "Net units"] == [
            f"{summary['net_units']:+.1f}U" for summary in expected_summaries
        ]
        assert [str(metric.value) for metric in at.metric if metric.label == "Record"] == [
            f"{summary['wins']}-{summary['losses']}" for summary in expected_summaries
        ]
    record_delta = next(str(metric.delta) for metric in at.metric if str(metric.label) == "Record")
    assert "void" in record_delta
    expected = pd.read_csv(page.available_releases()[latest])
    expected_default = page.default_matchup_label(list(page._matchup_groups(expected)))
    assert expected_default in {str(w.value) for w in at.selectbox}
    selected = next(
        group for label, _, group in page._matchup_groups(expected)
        if label == expected_default
    )
    expected_counts = sorted(selected.groupby("team").size().tolist())
    rendered_counts = sorted(len(frame.value) for frame in at.dataframe)
    assert rendered_counts == sorted(expected_counts * 2)
    # Hit appears once that week has graded outcomes; before grading it is absent.
    base_cols = {"#", "Player", "Pos", "Opp", "Model ATTD Odds", "Book ATTD Odds", "ATTD Value Gap"}
    rendered_cols = set(at.dataframe[0].value.columns)
    assert rendered_cols in (base_cols, base_cols | {"Hit"}), rendered_cols
    graded = pd.to_numeric(selected.scored_anytime, errors="coerce").notna().any()
    assert ("Hit" in rendered_cols) == bool(graded)


def test_week04_pit_cle_renders_all_three_markets(tmp_path):
    markets = {
        "Anytime TD": "Book ATTD Odds",
        "2+ TD": "Book 2+ TD Odds",
        "First TD": "Book First TD Odds",
    }
    for market, book_column in markets.items():
        at = _render(tmp_path, week=4)
        if market != "Anytime TD":
            at.segmented_control(key="atd_view_2026_4").set_value(market).run()
            at.selectbox(key="atd_props_matchup_2026_4").set_value("PIT vs CLE").run()
        else:
            # This game remains inspectable after kickoff; the default advances
            # to the next unstarted game and must not depend on today's date.
            at.selectbox(key="atd_matchup_2026_4").set_value("PIT vs CLE").run()
            assert at.selectbox(key="atd_matchup_2026_4").value == "PIT vs CLE"
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]
        assert len(at.metric) == (12 if market == "First TD" else 8)
        tables = [frame.value for frame in at.dataframe]
        assert tables
        assert any(book_column in table.columns for table in tables)
        if market == "First TD":
            captions = " ".join(str(c.value) for c in at.caption)
            assert "45 of 47 settled games" in captions


def test_week07_defaults_to_the_current_release_and_week05_history_still_renders(tmp_path):
    at = _render(tmp_path)
    releases = page.available_releases()
    assert page.default_release(list(releases)) == (2026, 7)
    assert any(w.key == "atd_week" and w.value == 7 for w in at.selectbox)
    assert any("Week 7" in str(item.value) for item in at.markdown)


def _first_td_text(at):
    parts = [item.value for item in list(at.markdown) + list(at.warning) + list(at.info) + list(at.caption)]
    return " ".join(str(part) for part in parts)


def _ev_numbers(table):
    return [int(cell.rstrip("%")) for cell in table["Expected Return"] if re.fullmatch(r"[+-]?\d+%", str(cell))]


def test_week07_first_td_shows_rankings_and_the_best_value_card(tmp_path, v3_params):
    at = _render(tmp_path, week=7)
    releases = page.available_releases()
    at.segmented_control(key="atd_view_2026_7").set_value("First TD").run()
    if page._week_is_complete(pd.read_csv(releases[(2026, 7)]), 2026, 7):
        at.selectbox(key="atd_props_matchup_2026_7").set_value(page.RECOMMENDED_LABEL).run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    headings = " ".join(str(item.value) for item in at.markdown)
    copy = _first_td_text(at)
    assert "Published board rankings" in headings
    assert "#### Best-value picks" in headings
    assert "first_td_actual_ev_v2" not in copy and "Experimental paper strategy" not in copy
    assert "Full market unavailable" not in copy
    assert "no-vig pending" not in copy.lower()
    assert all("probabilities are unavailable" not in str(w.value) for w in at.warning)
    assert any({"Matchup", "Top 1", "Top 3"} <= set(frame.value.columns) for frame in at.dataframe)
    # Recommended lists one pick per priced game, best expected return first
    boards = [frame.value for frame in at.dataframe if "Expected Return" in frame.value.columns]
    assert boards
    picks = boards[0]
    assert 1 <= len(picks) <= 6 and picks["Book First TD Odds"].str.contains("implied").all()
    evs = _ev_numbers(picks)
    assert evs and evs == sorted(evs, reverse=True) and all(value >= 0 for value in evs)
    assert picks["#"].tolist() == list(range(1, len(picks) + 1))   # numbered within the pick list


def test_week07_first_td_leaves_v3_cells_blank_with_a_warning_when_params_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(first_td_v3, "PARAMS_PATH", tmp_path / "absent" / "params.json")
    at = _render(tmp_path, week=7)
    at.segmented_control(key="atd_view_2026_7").set_value("First TD").run()
    at.selectbox(key="atd_props_matchup_2026_7").set_value("CIN vs BAL").run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    assert any("sharpened First TD probabilities are unavailable" in str(w.value) for w in at.warning)
    board = next(frame.value for frame in at.dataframe if "Expected Return" in frame.value.columns)
    assert board["Expected Return"].eq("").all() and board["Model First TD Odds"].eq("").all()
    assert board["Book First TD Odds"].str.contains("implied").all()
    assert "Full market unavailable" not in _first_td_text(at)


def test_week06_first_td_postgame_view_is_unchanged_apart_from_sort_order(tmp_path):
    at = _render(tmp_path, week=6)
    at.segmented_control(key="atd_view_2026_6").set_value("First TD").run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    assert at.selectbox(key="atd_props_matchup_2026_6").value == page.ALL_RESULTS_LABEL
    headings = " ".join(str(item.value) for item in at.markdown)
    assert "Published board rankings" in headings and "All First TD results across matchups" in headings
    copy = _first_td_text(at)
    assert "#### Best-value picks" not in copy and "Full market unavailable" not in copy
    assert not at.warning
    boards = [frame.value for frame in at.dataframe if "Expected Return" in frame.value.columns]
    assert len(boards) >= 28    # one desktop and one phone table per team
    for board in boards:
        assert "Hit" in board.columns
        assert set(board["Hit"]) <= {"Yes", "No", "Void", "Awaiting evidence", ""}
        evs = _ev_numbers(board)
        assert evs == sorted(evs, reverse=True)
    # sorted by return, not alphabetically by name (the Weeks 5 and 6 bug with no no-vig prices)
    names = [[p.split(" · ")[0] for p in board["Player"]] for board in boards]
    assert any(group != sorted(group) for group in names)
    assert any(board["Hit"].eq("Yes").any() for board in boards)


def test_week05_all_three_markets_still_render_and_first_td_recommended_stays_on_candidates(tmp_path):
    releases = page.available_releases()
    markets = {
        "Anytime TD": "Book ATTD Odds",
        "2+ TD": "Book 2+ TD Odds",
        "First TD": "Book First TD Odds",
    }
    for market, expected_column in markets.items():
        at = _render(tmp_path, week=5)
        if market != "Anytime TD":
            at.segmented_control(key="atd_view_2026_5").set_value(market).run()
            if page._week_is_complete(
                pd.read_csv(releases[(2026, 5)]), 2026, 5,
            ):
                at.selectbox(key="atd_props_matchup_2026_5").set_value(
                    page.RECOMMENDED_LABEL,
                ).run()
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]
        if market == "First TD":
            # Recommended stays on the candidate list; it must not dump every
            # priced First TD quote when a few quote pools are still incomplete.
            from publishing.td_releases import read_td_release
            priced = page.priced_rows(read_td_release(releases[(2026, 5)]))
            expected = page._first_td_display(priced)
            expected = expected[expected["_candidate"]].reset_index(drop=True)
            tables = [frame.value for frame in at.dataframe]
            first_tables = [table for table in tables if expected_column in table.columns]
            assert first_tables
            first_table = first_tables[0]
            assert len(first_table) == len(expected)
            assert not first_table["Model First TD Odds"].astype(str).str.contains("Pending").any()
            assert not first_table["Expected Return"].astype(str).str.contains("Pending").any()
            blob = " ".join(str(item.value) for item in list(at.info) + list(at.markdown) + list(at.caption))
            assert "Captured First TD prices awaiting verification" not in blob
            assert "Recommended First TD players this week" in blob
        else:
            assert any(expected_column in frame.value.columns for frame in at.dataframe)
            if market == "2+ TD":
                blob = " ".join(str(item.value) for item in list(at.caption) + list(at.markdown))
                assert "Every 2+ TD candidate across this week's matchups" in blob


def test_published_board_rankings_use_readable_matchup_labels():
    board = pd.DataFrame([
        {
            "game_id": "2026_06_ARI_LA", "player_id": f"player-{idx}",
            "player_display_name": f"Player {idx}", "p_first": 0.2 - idx * 0.01,
            "team": "LA", "opponent_team": "ARI", "kickoff_et": "2026-10-15 20:15",
        }
        for idx in range(3)
    ])
    table, summary = page._published_board_ranking_display(board, {})
    assert table["Game"].tolist() == ["ARI vs LAR"]
    assert summary["pending_games"] == 1


def test_two_plus_toggle_preserves_market_or_placeholder(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    _pick_props_matchup(at, "NO vs DET")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("2+ TD view" in str(item.value) for item in at.caption)
    # Week 1 is graded, so the 2+ board now carries a Hit column like the other markets.
    assert set(at.dataframe[0].value.columns) == set([
        "#", "Player", "Pos", "Opp", "Model 2+ TD Odds",
        "Book 2+ TD Odds", "2+ TD Value Gap", "Hit",
    ])
    assert set(at.dataframe[0].value["Hit"]) <= {"Yes", "No", ""}
    # The selected matchup may legitimately predate the 2+ sportsbook market;
    # the UI must keep that state explicit instead of treating placeholders as odds.
    book_values = at.dataframe[0].value["Book 2+ TD Odds"]
    value_values = at.dataframe[0].value["2+ TD Value Gap"]
    assert book_values.notna().all()
    assert value_values.notna().all()
    assert book_values.eq("Not implemented yet").equals(
        value_values.eq("Not implemented yet")
    )
    assert any(str(metric.label) == "Record" for metric in at.metric)
    assert any("2+ TD paper tracker" in str(item.value) for item in at.caption)


def test_results_updated_caption_reads_the_shared_grading_stamp(tmp_path, monkeypatch):
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site_pages"))
    import page_anytime_td as page

    monkeypatch.setattr(page, "_DIR", tmp_path)
    assert page._grading_stamp_caption(2026, 2) == ""  # never graded: no line, no crash
    (tmp_path / "grading_2026_week02.json").write_text(json.dumps({
        "graded_at": "2026-09-22T00:13:44Z", "final_games": 15, "awaiting_stat_rows": 10,
    }), encoding="utf-8")
    text = page._grading_stamp_caption(2026, 2)
    assert text.startswith("Results last updated Mon Sep 21, 8:13 PM ET.")
    assert "Anytime TD, 2+ TD and First TD are graded together" in text
    assert "15 final games" in text and "10 quoted players" in text
    (tmp_path / "grading_2026_week02.json").write_text("{not json", encoding="utf-8")
    assert page._grading_stamp_caption(2026, 2) == ""


def test_props_markets_default_to_recommended_and_list_every_game(tmp_path):
    for market in ("2+ TD", "First TD"):
        at = _render(tmp_path, week=1)
        at.segmented_control(key="atd_view_2026_1").set_value(market).run()
        assert not at.exception, at.exception
        # No "Recommended only" toggle here: Recommended is a dropdown entry.
        assert not any(w.key == f"atd_rec_2026_1_{market}" for w in at.toggle)
        box = next(w for w in at.selectbox if w.key == "atd_props_matchup_2026_1")
        assert box.value == "Recommended"
        assert box.options[0] == "Recommended"
        games = [o for o in box.options if o != "Recommended"]
        assert games
        assert any(
            f"Recommended {market} players this week" in str(m.value)
            for m in at.markdown
        )

        # A real game lists every priced player, not only the recommended ones.
        at.selectbox(key="atd_props_matchup_2026_1").set_value("NO vs DET").run()
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]
        assert at.selectbox(key="atd_props_matchup_2026_1").value == "NO vs DET"
        assert len(at.dataframe) >= 1
        assert any(
            "clear the" in str(c.value) or "Highlighted rows" in str(c.value)
            for c in at.caption
        )


def test_ne_sea_display_only_two_plus_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    _pick_props_matchup(at, "NE vs SEA")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical 2+ TD model view for NE vs SEA" in info
    rendered = list(at.dataframe)[-2:]
    assert len(rendered) == 2
    assert all(
        frame.value["Model 2+ TD Odds"].ne("Not implemented yet").all()
        for frame in rendered
    )
    assert all(
        frame.value["Book 2+ TD Odds"].eq("Not implemented yet").all()
        for frame in rendered
    )
    # The tally aggregates every published live week, not just NE vs SEA, so
    # the graded count grows as later weeks publish (48 at Week 1 launch,
    # 358 once Week 2 joined). Check shape and internal consistency instead
    # of a snapshot count that goes stale on every new live week.
    tally_captions = [
        str(item.value) for item in at.caption
        if "Results-only 2+ TD tally" in str(item.value)
    ]
    assert tally_captions, [str(item.value) for item in at.caption]
    match = re.search(r"(\d+) hits / (\d+) graded player-games", tally_captions[0])
    assert match, tally_captions[0]
    hits, graded = int(match.group(1)), int(match.group(2))
    assert 0 <= hits <= graded
    assert graded > 0


def test_sf_la_display_only_two_plus_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    _pick_props_matchup(at, "SF vs LAR")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical 2+ TD model view for SF vs LAR" in info
    rendered = list(at.dataframe)[-2:]
    assert len(rendered) == 2
    assert all(
        frame.value["Model 2+ TD Odds"].ne("Not implemented yet").all()
        for frame in rendered
    )
    assert all(
        frame.value["Book 2+ TD Odds"].eq("Not implemented yet").all()
        for frame in rendered
    )


def test_two_plus_results_tally_is_results_only():
    rows = pd.DataFrame({"scored_two_plus": [1, 0, None, 1]})
    assert page._two_plus_results_tally(rows) == {"graded": 3, "hits": 2}
    assert page._two_plus_results_tally(pd.DataFrame({"p_ge2": [0.2]})) == {
        "graded": 0,
        "hits": 0,
    }


def test_first_td_toggle_renders_priced_matchup(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    _pick_props_matchup(at, "NO vs DET")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("First TD" in str(item.value) for item in at.info)
    assert any("full scorer pool could not be verified" in str(item.value) for item in at.info)
    columns = set(at.dataframe[0].value.columns)
    assert {
        "#", "Player", "Pos", "Opp", "Model First TD Odds",
        "Book First TD Odds", "Expected Return",
    } <= columns
    book_values = at.dataframe[0].value["Book First TD Odds"]
    assert book_values.ne("Not implemented yet").all()
    assert any(str(metric.label) == "Record" for metric in at.metric)
    assert any("First TD paper tracker" in str(item.value) for item in at.caption)


def test_market_control_is_a_single_three_way_choice(tmp_path):
    at = _render(tmp_path, week=1)
    control = next(w for w in at.segmented_control if w.key == "atd_view_2026_1")
    assert set(control.options) == {"Anytime TD", "2+ TD", "First TD"}
    assert control.value == "Anytime TD"

    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    _pick_props_matchup(at, "NO vs DET")
    assert not at.exception, at.exception
    assert "Model 2+ TD Odds" in set(at.dataframe[0].value.columns)

    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    assert not at.exception, at.exception
    columns = set(at.dataframe[0].value.columns)
    assert "Model First TD Odds" in columns
    assert "Model 2+ TD Odds" not in columns

    at.segmented_control(key="atd_view_2026_1").set_value("Anytime TD").run()
    assert not at.exception, at.exception
    columns = set(at.dataframe[0].value.columns)
    assert "Model ATTD Odds" in columns
    assert "Model First TD Odds" not in columns


def test_team_header_matches_active_market(tmp_path):
    at = _render(tmp_path, week=1)
    md = " ".join(str(item.value) for item in at.markdown)
    assert "Anytime TDs**" in md
    assert "First TDs**" not in md

    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    _pick_props_matchup(at, "NO vs DET")
    md = " ".join(str(item.value) for item in at.markdown)
    assert "First TDs**" in md
    assert "Anytime TDs**" not in md

    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    md = " ".join(str(item.value) for item in at.markdown)
    assert "2+ TDs**" in md


def test_ne_sea_display_only_first_td_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    _pick_props_matchup(at, "NE vs SEA")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical First TD model view for NE vs SEA" in info
    rendered = list(at.dataframe)[-2:]
    assert len(rendered) == 2
    assert all(
        frame.value["Model First TD Odds"].ne("Not implemented yet").all()
        for frame in rendered
    )
    assert all(
        frame.value["Book First TD Odds"].eq("Not implemented yet").all()
        for frame in rendered
    )
    assert any(
        "First TD outcomes only" in str(item.value)
        for item in at.caption
    )


def test_sf_la_display_only_first_td_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    _pick_props_matchup(at, "SF vs LAR")
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical First TD model view for SF vs LAR" in info
    rendered = list(at.dataframe)[-2:]
    assert len(rendered) == 2
    assert all(
        frame.value["Model First TD Odds"].ne("Not implemented yet").all()
        for frame in rendered
    )
    assert all(
        frame.value["Book First TD Odds"].eq("Not implemented yet").all()
        for frame in rendered
    )
    # SF vs LA was graded live: Kyren Williams scored the first TD.
    assert any(
        frame.value["Hit"].eq("Yes").any() for frame in rendered
    )


def test_first_td_results_tally_is_results_only():
    rows = pd.DataFrame({"scored_first": [1, 0, None, 0]})
    assert page._first_td_results_tally(rows) == {"graded": 3, "hits": 1}
    assert page._first_td_results_tally(pd.DataFrame({"p_first": [0.1]})) == {
        "graded": 0,
        "hits": 0,
    }


def test_first_td_results_tally_counts_games_and_excludes_voids():
    rows = pd.DataFrame({
        "game_id": ["A", "A", "B", "C"],
        "scored_first": [1, 0, 0, 1],
        "settlement_status_first": ["settled", "settled", "settled", "void"],
    })
    assert page._first_td_results_tally(rows) == {"graded": 2, "hits": 1}


def test_first_td_display_shape_and_ordering():
    df = pd.DataFrame({
        "player_display_name": ["Alpha", "Beta", "Gamma"],
        "team": ["AAA", "AAA", "BBB"],
        "position": ["RB", "WR", "QB"],
        "opponent_team": ["BBB", "BBB", "AAA"],
        "game_id": ["2026_01_AAA_BBB"] * 3,
        "p_first": [0.20, 0.10, 0.05],
        "book_first_p_devigged": [0.15, 0.12, 0.06],
        "first_amer": [500, 700, 1500],
        "scored_first": [None, None, None],
    })
    table = page._first_td_display(df)
    # Alpha returns +20%; Beta and Gamma both return -20%, so the larger model chance (Beta) goes first
    assert list(table["Player"]) == ["Alpha · AAA", "Beta · AAA", "Gamma · BBB"]
    assert list(table["Expected Return"]) == ["+20%", "-20%", "-20%"]
    assert table.loc[0, "_ev"] > table.loc[1, "_ev"] >= table.loc[2, "_ev"]
    assert table.loc[0, "_candidate"]
    assert list(table["Book First TD Odds"])[0] == "+500 · 16.7% implied · no-vig 15.0%"
    assert list(table["_book_phone"])[0] == "+500 · 16.7% implied"


def test_first_td_display_sorts_by_expected_return_not_name_when_no_vig_is_missing():
    names = ["Zed", "Yan", "Xia", "Wes"]
    df = pd.DataFrame({
        "player_id": ["p4", "p3", "p2", "p1"],
        "player_display_name": names,
        "team": ["AAA"] * 4, "position": ["WR"] * 4, "opponent_team": ["BBB"] * 4,
        "game_id": ["2026_07_AAA_BBB"] * 4,
        "p_first": [0.10, 0.20, 0.05, 0.30],
        "book_first_p_devigged": [None] * 4,
        "first_amer": [1000, 400, 2500, 200],
        "scored_first": [None] * 4,
    })
    table = page._first_td_display(df)
    # decimal 11, 5, 26, 3 give returns +10%, 0%, +30%, -10%; alphabetical order would be Wes, Xia, Yan, Zed
    assert [value.split(" · ")[0] for value in table["Player"]] == ["Xia", "Zed", "Yan", "Wes"]
    assert list(table["Expected Return"]) == ["+30%", "+10%", "0%", "-10%"]


def test_first_td_display_without_a_price_sorts_by_model_chance_then_player_id():
    df = pd.DataFrame({
        "player_id": ["p3", "p2", "p1", "p0"],
        "player_display_name": ["Aaa", "Bbb", "Ccc", "Ddd"],
        "team": ["AAA"] * 4, "position": ["WR"] * 4, "opponent_team": ["BBB"] * 4,
        "p_first": [0.10, 0.20, 0.10, float("nan")],
        "first_amer": [None] * 4,
        "scored_first": [None] * 4,
    })
    table = page._first_td_display(df)
    # chance first (0.20), then the 0.10 tie by player_id (p1 before p3), unknown chance last
    assert [value.split(" · ")[0] for value in table["Player"]] == ["Bbb", "Ccc", "Aaa", "Ddd"]
    assert list(table["Expected Return"]) == ["", "", "", ""]


def test_first_td_display_v3_uses_the_sharpened_probability_and_game_pick():
    df = pd.DataFrame({
        "player_id": ["p1", "p2", "p3"],
        "player_display_name": ["One", "Two", "Three"],
        "team": ["AAA"] * 3, "position": ["WR"] * 3, "opponent_team": ["BBB"] * 3,
        "game_id": ["2026_07_AAA_BBB"] * 3,
        "p_first": [0.20, 0.20, 0.20],
        "p_first_v3": [0.30, float("nan"), 0.10],
        "first_td_v3_pick": [False, False, True],
        "bet_eligible": [True, True, True],
        "first_amer": [400, 400, 900],
        "scored_first": [None] * 3,
    })
    table = page._first_td_display(df).set_index("Player")
    assert list(table.index)[:2] == ["One · AAA", "Three · AAA"]          # 0.30 * 5 - 1 = +50%, 0.10 * 10 - 1 = 0%
    assert table.loc["One · AAA", "Expected Return"] == "+50%"
    assert table.loc["Two · AAA", "Expected Return"] == "" and table.loc["Two · AAA", "Model First TD Odds"] == ""
    # the highlight is the selector's game-level pick, not an expected-return threshold
    assert table["_candidate"].to_dict() == {"One · AAA": False, "Two · AAA": False, "Three · AAA": True}


def test_first_td_display_explains_a_positive_return_that_the_cap_rules_out():
    df = pd.DataFrame({
        "player_id": ["p1", "p2"],
        "player_display_name": ["Long", "Pick"],
        "team": ["AAA"] * 2, "position": ["WR"] * 2, "opponent_team": ["BBB"] * 2,
        "game_id": ["2026_07_AAA_BBB"] * 2,
        "p_first": [0.05, 0.2], "p_first_v3": [0.05, 0.2],
        "first_td_v3_pick": [False, True], "first_td_v3_over_cap": [True, False],
        "bet_eligible": [True, True], "first_amer": [4500, 450], "scored_first": [None, None],
    })
    table = page._first_td_display(df).set_index("Player")
    assert table.loc["Long · AAA", "Expected Return"] == "+130% · over cap"
    assert table.loc["Pick · AAA", "Expected Return"] == "+10%"
    assert not table.loc["Long · AAA", "_candidate"] and table.loc["Pick · AAA", "_candidate"]


def test_first_td_style_colors_expected_return_and_marks_the_pick():
    df = pd.DataFrame({
        "player_id": ["p1", "p2"],
        "player_display_name": ["One", "Two"],
        "team": ["AAA", "AAA"], "position": ["WR", "WR"], "opponent_team": ["BBB", "BBB"],
        "p_first": [0.30, 0.05], "p_first_v3": [0.30, 0.05], "first_td_v3_pick": [True, False],
        "first_amer": [400, 400], "scored_first": [None, None],
    })
    display = page._first_td_display(df)
    styles = page._first_td_style(display)(display[page.FIRST_TD_DESKTOP_COLS[:-1]])
    assert "#B7F7D0" in styles.loc[0, "Expected Return"]          # highlighted pick
    assert styles.loc[1, "Expected Return"] == "color: #F08A8A; font-weight: 700"
    assert "border-left: 3px solid #35D08A" in styles.loc[0, "Player"]


def test_amer_display_abbreviates_only_past_ten_thousand():
    # Below 10000, abbreviating costs precision for zero space saved.
    assert page._amer_display(1500) == "+1500"
    assert page._amer_display(9999) == "+9999"
    assert page._amer_display(-1500) == "-1500"
    # At/past 10000, k-notation is shorter and the real fix for phone overflow.
    assert page._amer_display(10000) == "+10.0k"
    assert page._amer_display(10805) == "+10.8k"
    assert page._amer_display(89070) == "+89.1k"
    assert page._amer_display(-15000) == "-15.0k"
    assert page._amer_display(None) == ""


def test_signed_int_display_matches_amer_display_cutoff():
    assert page._signed_int_display(1500) == "+1500"
    assert page._signed_int_display(-9999) == "-9999"
    assert page._signed_int_display(10805) == "+10.8k"
    assert page._signed_int_display(-81719) == "-81.7k"
    assert page._signed_int_display(0) == "0"


def test_phone_odds_column_widths_fit_the_widest_realistic_value():
    # Worst case: 5-digit book odds combined with a 3-digit percentage, e.g.
    # "+89.1k · 100.0%" (15 chars) must not be narrower than before the fix.
    assert page.PHONE_WIDTHS["Model ATTD Odds"] >= 130
    assert page.PHONE_WIDTHS["Book ATTD Odds"] >= 130


def test_result_status_column_fits_awaiting_evidence_on_desktop_and_phone():
    # Settlement labels must remain legible even when a player is still
    # awaiting participation evidence and has no betting recommendation.
    assert page.PHONE_WIDTHS["Hit"] >= 150
    assert page._desktop_column_config()["Hit"]["width"] >= 150
    assert page._two_plus_column_config()["Hit"]["width"] >= 150
    assert page._first_td_column_config()["Hit"]["width"] >= 150
    assert page._first_td_phone_column_config()["Hit"]["width"] >= 150


def test_year_and_week_selectors_keep_2025_available(tmp_path):
    at = _render(tmp_path)
    at.selectbox(key="atd_year").set_value(2025).run()
    assert not at.exception, at.exception
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["atd_year"] == 2025
    assert controls["atd_week"] == 10
    at.selectbox(key="atd_week").set_value(17).run()
    assert not at.exception, at.exception
    assert {w.key: w.value for w in at.selectbox}["atd_week"] == 17


def test_two_plus_view_on_2025_demo_does_not_crash(tmp_path):
    # The 2025 demo CSVs have no two_plus_amer column at all, so every gap
    # in that market is NaN. qualifies_probability_gap used to propagate
    # pd.NA through .ge() on a nullable dtype, and _two_plus_style's
    # `if candidate:` raised "boolean value of NA is ambiguous" the first
    # time it hit one -- reproducible by switching Year to 2025, then Market
    # to 2+ TD, on any matchup.
    at = _render(tmp_path)
    at.selectbox(key="atd_year").set_value(2025).run()
    control = next(w for w in at.segmented_control if w.key.startswith("atd_view"))
    at.segmented_control(key=control.key).set_value("2+ TD").run()
    props = next(w for w in at.selectbox if w.key.startswith("atd_props_matchup"))
    at.selectbox(key=props.key).set_value(props.options[1]).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(list(at.dataframe)) > 0


def test_first_td_view_on_2025_demo_does_not_crash(tmp_path):
    # The 2025 demo CSVs have no p_first/book_first_p_devigged/scored_first
    # columns at all (First TD is 2026-only). df.get(missing_column) returns
    # None, and pd.to_numeric(None, errors="coerce") silently collapses to a
    # bare scalar nan instead of a Series, so any later .map()/.notna() call
    # on that "column" crashed with an AttributeError -- reproducible by
    # switching Year to 2025, then Market to First TD.
    at = _render(tmp_path)
    at.selectbox(key="atd_year").set_value(2025).run()
    control = next(w for w in at.segmented_control if w.key.startswith("atd_view"))
    at.segmented_control(key=control.key).set_value("First TD").run()
    props = next(w for w in at.selectbox if w.key.startswith("atd_props_matchup"))
    at.selectbox(key=props.key).set_value(props.options[1]).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(list(at.dataframe)) > 0


def test_qualifies_probability_gap_never_returns_na():
    import attd_tracker as tracker

    gap = pd.Series([0.01, float("nan"), 0.06], dtype="Float64")
    result = tracker.qualifies_probability_gap(gap)
    assert result.dtype == bool
    assert list(result) == [True, False, True]


def test_pending_replacement_caption_pluralizes_the_verb():
    assert page._pending_replacement_caption(1).startswith(
        "1 quoted replacement row awaits model inputs"
    )
    assert page._pending_replacement_caption(2).startswith(
        "2 quoted replacement rows await model inputs"
    )
    assert page._pending_replacement_caption(0) is None


def test_retrospective_unavailable_rows_are_not_called_replacements(tmp_path):
    at = _render(tmp_path, week=1)
    captions = " ".join(str(c.value) for c in at.caption)
    assert "quoted rows have no reproducible retrospective probability" in captions
    assert "quoted replacement" not in captions


def test_anytime_td_files_cover_weeks_10_17():
    import page_anytime_td as page

    weeks = page.available_weeks()
    assert list(weeks) == list(range(10, 18)), weeks


def test_audited_strategy_artifact_has_fixed_rule_and_bootstrap_contract():
    import json

    path = _HERE / "betting" / "anytime_td" / "strategy_backtest_2025_draftkings.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    betting = payload["betting_profitability"]
    assert betting["fixed_gap"]["threshold"] == 0.005
    assert betting["fixed_gap"]["settled_bets"] > 0
    assert betting["fixed_gap_bootstrap"]["resamples"] == 10_000
    assert betting["fixed_gap_bootstrap"]["seed"] == 20260911
    assert len(betting["gap_scan"]) == 301


def test_roi_range_card_is_pending_until_ci_is_available():
    assert page._roi_range_value({"available": False}) == "Pending"
    assert page._roi_range_value({"available": True, "lower": -0.125, "upper": 0.275}) == (
        "-12.5% to 27.5%"
    )


def test_priced_rows_drop_unpriced_and_keep_rb_fb():
    import page_anytime_td as page

    hit = pd.DataFrame({
        "player_display_name": ["A", "B", "C"],
        "position": ["RB", "FB", "WR"],
        "team": ["KC", "SF", "PHI"],
        "opponent_team": ["LV", "SEA", "DAL"],
        "p_ge1": [0.40, 0.20, 0.30],
        "p_ge2": [0.10, 0.02, 0.05],
        "p_book": [0.35, None, 0.28],
        "fair_amer": [150, 400, 250],
        "book_amer": [-154, None, 257],
        "scored_anytime": [1, 0, 0],
    })
    priced = page.priced_rows(hit)
    assert list(priced.player_display_name) == ["A", "C"]
    backs = page.by_position(hit, "RB")
    assert list(backs.position) == ["RB", "FB"]
    summary = page.week_summary(priced)
    assert summary["n"] == 2
    assert summary["hits"] == 1
    display = page._display(priced)
    assert len(display) == len(priced)
    assert list(display["Player"]) == ["A · KC", "C · PHI"]


def test_display_sorts_highest_value_vs_book_first():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Negative", "Small", "Largest"],
        "position": ["WR", "RB", "TE"],
        "team": ["KC", "SF", "PHI"],
        "opponent_team": ["LV", "SEA", "DAL"],
        "p_ge1": [0.50, 0.35, 0.40],
        "p_ge2": [0.10, 0.02, 0.05],
        "p_book": [0.60, 0.30, 0.20],
        "fair_amer": [-100, 186, 150],
        "book_amer": [-150, 233, 400],
        "scored_anytime": [None, None, None],
    })

    display = page._display(page.priced_rows(rows))
    assert list(display["Player"]) == ["Largest · PHI", "Small · SF", "Negative · KC"]
    assert list(display["Model ATTD Odds"]) == ["+150 · 40.0%", "+186 · 35.0%", "-100 · 50.0%"]
    assert list(display["Book ATTD Odds"]) == ["+400 · 20.0%", "+233 · 30.0%", "-150 · 60.0%"]
    assert list(display["ATTD Value Gap"]) == ["+250 · +20.0%", "+47 · +5.0%", "-50 · -10.0%"]
    assert list(display["_candidate"]) == [True, True, False]
    assert page._value_gap(144, 150, 0.411, 0.400) == "+6 · +1.1%"


def test_ineligible_rows_carry_no_history_tag_on_every_market():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Rookie", "Vet", "Unconfirmed"],
        "position": ["TE", "RB", "WR"],
        "team": ["LA", "LA", "LA"],
        "opponent_team": ["NYG", "NYG", "NYG"],
        "p_ge1": [0.0855, 0.0428, 0.06],
        "p_ge2": [0.01, 0.003, 0.004],
        "p_first": [0.0157, 0.0077, 0.01],
        "p_book": [0.0588, 0.0323, 0.04],
        "book_first_p_devigged": [0.0112, 0.0088, 0.009],
        "fair_amer": [1069, 2234, 1567],
        "book_amer": [1600, 3000, 2400],
        "first_amer": [7000, 9000, 8000],
        "two_plus_amer": [20000, 20000, 20000],
        "scored_anytime": [None, None, None],
        "bet_eligible": [False, True, False],
        "eligibility_reason": [
            "synthetic_or_unresolved_identity", "", "participation_status_unresolved",
        ],
    })
    priced = page.priced_rows(rows)
    attd = page._display(priced).set_index(page._display(priced)["Player"].str.split(" · ").str[0])
    assert attd.loc["Rookie", "ATTD Value Gap"].endswith(" · no history")
    assert attd.loc["Unconfirmed", "ATTD Value Gap"].endswith(" · not eligible")
    assert "·" in attd.loc["Vet", "ATTD Value Gap"]
    assert not attd.loc["Vet", "ATTD Value Gap"].endswith(("no history", "not eligible"))
    assert not attd.loc["Rookie", "_candidate"]
    for frame, col in (
        (page._two_plus_display(priced), "2+ TD Value Gap"),
        (page._first_td_display(priced), "Expected Return"),
    ):
        by_name = frame.set_index(frame["Player"].str.split(" · ").str[0])
        assert by_name.loc["Rookie", col].endswith(" · no history")
        assert not by_name.loc["Vet", col].endswith(("no history", "not eligible"))
    assert page._with_tag("Pending", " · no history") == "Pending"


def test_candidate_style_uses_emerald_value_treatment():
    rows = pd.DataFrame({
        "player_display_name": ["Candidate", "Other"],
        "position": ["RB", "WR"],
        "team": ["KC", "SF"],
        "opponent_team": ["LV", "SEA"],
        "p_ge1": [0.40, 0.35],
        "p_ge2": [0.10, 0.02],
        "p_book": [0.30, 0.35],
        "fair_amer": [150, 186],
        "book_amer": [233, 186],
        "scored_anytime": [None, None],
    })
    display = page._display(page.priced_rows(rows))
    styles = page._style(display)(display[page.DESKTOP_COLS])

    assert styles.iloc[0]["Player"] == (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700; "
        "border-left: 3px solid #35D08A"
    )
    assert "background-color: #123229" in styles.iloc[0]["Pos"]
    assert "background-color: #1A4A3B" in styles.iloc[0]["ATTD Value Gap"]
    assert styles.iloc[0]["Model ATTD Odds"] == (
        "color: #FFFFFF; background-color: #123229"
    )
    assert styles.iloc[1]["Model ATTD Odds"] == "color: #FFFFFF"
    assert not any("rgba" in str(value) for value in styles.to_numpy().ravel())


def test_settled_candidate_miss_uses_muted_red_value_treatment():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Missed Candidate"],
        "position": ["RB"],
        "team": ["KC"],
        "opponent_team": ["LV"],
        "p_ge1": [0.40],
        "p_ge2": [0.10],
        "p_book": [0.30],
        "fair_amer": [150],
        "book_amer": [233],
        "scored_anytime": [0],
    })
    display = page._display(page.priced_rows(rows))
    styles = page._style(display)(display[page.DESKTOP_COLS])

    assert styles.iloc[0]["Player"] == (
        "background-color: #BA797A; color: #3F2024; font-weight: 700; "
        "border-left: 3px solid #8F525A"
    )
    assert styles.iloc[0]["ATTD Value Gap"] == (
        "background-color: #BA797A; color: #3F2024; font-weight: 700"
    )
    assert styles.iloc[0]["Model ATTD Odds"] == (
        "color: #FFFFFF; background-color: #BA797A"
    )
    assert styles.iloc[0]["Hit"] == (
        "background-color: #BA797A; color: #3F2024; font-weight: 700"
    )


def test_two_plus_candidate_uses_ratio_and_price_floor_highlight():
    """2+ TD candidate rule since 2026-09-19: model >= 1.25x DraftKings'
    price, with that price >= 2% (attd_tracker.qualifies_two_plus_ratio).
    Both rows share the same two_plus_amer (400 -> 20% implied), which
    clears the price floor for both; only Boundary's 1.5x ratio clears the
    ratio bar, Other's 1.0x does not."""
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Boundary", "Other"],
        "position": ["RB", "WR"],
        "team": ["KC", "SF"],
        "opponent_team": ["LV", "SEA"],
        "p_ge1": [0.40, 0.35],
        "p_ge2": [0.30, 0.20],
        "p_book": [0.30, 0.35],
        "fair_amer": [150, 186],
        "book_amer": [233, 186],
        "two_plus_amer": [400, 400],
        "scored_anytime": [None, None],
        "scored_two_plus": [None, None],
    })
    display = page._two_plus_display(page.priced_rows(rows))
    assert list(display["Player"]) == ["Boundary · KC", "Other · SF"]
    assert list(display["_candidate"]) == [True, False]
    styles = page._two_plus_style(display)(display[page.TWO_PLUS_DESKTOP_COLS])
    assert styles.iloc[0]["Player"] == (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700; "
        "border-left: 3px solid #35D08A"
    )
    assert styles.iloc[0]["2+ TD Value Gap"] == (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700"
    )


def test_two_plus_rows_sort_by_raw_value_gap_then_player():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Higher Probability", "Higher Value", "Tie Z", "Tie A"],
        "position": ["RB", "WR", "TE", "RB"],
        "team": ["KC", "SF", "PHI", "DAL"],
        "opponent_team": ["LV", "SEA", "NYG", "NYG"],
        "p_ge1": [0.40, 0.35, 0.25, 0.20],
        "p_ge2": [0.30, 0.20, 0.25, 0.20],
        "p_book": [0.30, 0.35, 0.30, 0.25],
        "fair_amer": [150, 400, 300, 400],
        "book_amer": [233, 186, 233, 300],
        "two_plus_amer": [100, 400, 300, 400],
        "scored_anytime": [None, None, None, None],
        "scored_two_plus": [None, None, None, None],
    })

    display = page._two_plus_display(page.priced_rows(rows))

    assert list(display["Player"]) == [
        "Higher Value · SF",
        "Tie A · DAL",
        "Tie Z · PHI",
        "Higher Probability · KC",
    ]


def test_phone_grid_pins_identity_columns_only():
    import page_anytime_td as page

    assert page.PHONE_COLS == [
        "#", "Player", "Model ATTD Odds", "Book ATTD Odds", "ATTD Value Gap", "Hit",
    ]
    assert page.PHONE_LABELS["Model ATTD Odds"] == "Model"
    assert page.PHONE_LABELS["Book ATTD Odds"] == "Book"
    assert page.PHONE_LABELS["ATTD Value Gap"] == "Value"
    assert page.PHONE_WIDTHS["#"] >= 50
    assert set(page.PHONE_COLS).issubset(page.DESKTOP_COLS)
    phone = page._phone_column_config()
    assert phone["#"]["pinned"] is True
    assert phone["Player"]["pinned"] is True
    assert all(phone[column].get("pinned") is None for column in page.PHONE_COLS[2:])

    two_plus_phone = page._two_plus_phone_column_config()
    assert two_plus_phone["#"]["pinned"] is True
    assert two_plus_phone["Player"]["pinned"] is True
    assert all(
        two_plus_phone[column].get("pinned") is None
        for column in page.TWO_PLUS_PHONE_COLS[2:]
    )


def test_week10_priced_board_is_larger_than_a_card():
    import page_anytime_td as page

    path = page.available_weeks()[10]
    priced = page.priced_rows(pd.read_csv(path))
    assert len(priced) > 8
    assert priced.p_book.notna().all()


def test_live_release_discovery_and_pending_hit_is_blank(tmp_path, monkeypatch):
    import page_anytime_td as page

    live = tmp_path / "anytime_td_2026_week01.csv"
    pd.DataFrame([{
        "season": 2026, "week": 1, "player_id": "p1", "player_display_name": "Player One",
        "position": "RB", "team": "SF", "opponent_team": "LA", "p_ge1": .4,
        "p_ge2": .1, "p_book": .375, "fair_amer": 150, "book_amer": 167,
        "scored_anytime": None,
    }]).to_csv(live, index=False)
    monkeypatch.setattr(page, "_DIR", tmp_path)
    assert page.available_releases()[(2026, 1)] == live
    display = page._display(page.priced_rows(pd.read_csv(live)))
    assert display.loc[0, "Hit"] == ""


def test_hit_labels_distinguish_settled_void_and_pending_rows():
    rows = pd.DataFrame({
        "scored_first": [1, 0, None, 0, None],
        "settlement_status_first": [
            "settled", "settled", "void", "awaiting_evidence", "open",
        ],
    })

    assert page._hit_labels(rows, "scored_first", "settlement_status_first").tolist() == [
        "Yes", "No", "Void", "Awaiting evidence", "",
    ]


def test_week_completion_uses_grade_stamp_not_every_player_settlement(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(page, "_DIR", tmp_path)
    (tmp_path / "grading_2026_week06.json").write_text(
        json.dumps({"final_games": 2}), encoding="utf-8",
    )
    rows = pd.DataFrame({
        "game_id": ["g1", "g1", "g2", "g2"],
        "settlement_status_first": ["settled", "awaiting_evidence", "void", "settled"],
    })

    assert page._week_is_complete(rows, 2026, 6)
    assert not page._week_is_complete(rows, 2026, 5)
    (tmp_path / "grading_2026_week06.json").write_text(
        json.dumps({"final_games": 1}), encoding="utf-8",
    )
    assert not page._week_is_complete(rows, 2026, 6)


def test_missing_scheduled_markets_names_uncovered_week7_game(tmp_path, monkeypatch):
    betting = tmp_path / "betting"
    betting.mkdir()
    pd.DataFrame([
        {"game_id": "2026_07_CIN_BAL", "season": 2026, "week": 7,
         "game_type": "REG", "away_team": "CIN", "home_team": "BAL"},
        {"game_id": "2026_07_SF_ATL", "season": 2026, "week": 7,
         "game_type": "REG", "away_team": "SF", "home_team": "ATL"},
    ]).to_csv(betting / "nfl_2026_schedule.csv", index=False)
    monkeypatch.setattr(page, "_HERE", tmp_path)

    missing = page._missing_scheduled_markets(
        pd.DataFrame({"game_id": ["2026_07_CIN_BAL"]}), 2026, 7
    )

    assert missing == ["SF at ATL"]


def test_completed_week_first_td_defaults_to_all_results(tmp_path):
    at = _render(tmp_path, week=6)
    at.segmented_control(key="atd_view_2026_6").set_value("First TD").run()

    matchup = next(w for w in at.selectbox if w.key == "atd_props_matchup_2026_6")
    assert matchup.value == page.ALL_RESULTS_LABEL
    assert page.ALL_RESULTS_LABEL in matchup.options
    assert page.RECOMMENDED_LABEL in matchup.options
    headings = " ".join(str(item.value) for item in at.markdown)
    assert page._week_is_complete(
        pd.read_csv(page.available_releases()[(2026, 6)]), 2026, 6,
    )
    assert "All First TD results across matchups" in headings
    assert len([item for item in at.markdown if " vs " in str(item.value)]) >= 10


def test_completed_week_can_still_select_recommended_and_matchup(tmp_path):
    at = _render(tmp_path, week=6)
    at.segmented_control(key="atd_view_2026_6").set_value("First TD").run()
    selector = at.selectbox(key="atd_props_matchup_2026_6")

    selector.set_value(page.RECOMMENDED_LABEL).run()
    assert at.selectbox(key="atd_props_matchup_2026_6").value == page.RECOMMENDED_LABEL
    matchup_label = next(label for label, _, _ in page._matchup_groups(
        page.priced_rows(pd.read_csv(page.available_releases()[(2026, 6)]))
    ))
    at.selectbox(key="atd_props_matchup_2026_6").set_value(matchup_label).run()
    assert at.selectbox(key="atd_props_matchup_2026_6").value == matchup_label


def test_verified_replacement_can_display_book_odds_while_model_is_pending():
    import page_anytime_td as page

    rows = pd.DataFrame([{
        "player_display_name": "Cooper Rush", "position": "QB",
        "team": "ATL", "opponent_team": "PIT", "p_ge1": None,
        "p_ge2": None, "p_book": 0.0625, "fair_amer": None,
        "book_amer": 1500, "two_plus_amer": 17000,
        "scored_anytime": None, "scored_two_plus": None,
    }])

    priced = page.priced_rows(rows)
    assert list(priced.player_display_name) == ["Cooper Rush"]
    display = page._display(priced)
    assert display.loc[0, "Model ATTD Odds"] == "Pending"
    assert display.loc[0, "Book ATTD Odds"] == "+1500 · 6.2%"
    assert display.loc[0, "ATTD Value Gap"] == "Pending"

    two_plus = page._two_plus_display(priced)
    assert two_plus.loc[0, "Model 2+ TD Odds"] == "Pending"
    assert two_plus.loc[0, "Book 2+ TD Odds"] == "+17.0k · 0.6%"
    assert two_plus.loc[0, "2+ TD Value Gap"] == "Pending"


def test_week1_reconstruction_preserves_atl_pit_prices_and_unsupported_row():
    release = page.available_releases()[(2026, 1)]
    retro = pd.read_csv(release)
    matchup = retro[retro.game_id.eq("2026_01_ATL_PIT")]

    assert retro.prediction_mode.eq("retrospective").all()
    assert retro.model_version.eq("td_product_ngs_44_frozen_2025_v1").all()
    assert not retro.player_display_name.eq("Tua Tagovailoa").any()
    cooper = matchup[matchup.player_id.eq("00-0033662")].iloc[0]
    assert cooper.player_display_name == "Cooper Rush"
    # Prices remain as recorded. Cooper Rush's exact Sunday context is
    # unavailable, so his model probability is not borrowed from another slate.
    assert (cooper.book_amer, cooper.first_amer, cooper.two_plus_amer) == (
        2200, 8000, 25000,
    )
    bijan = matchup[matchup.player_id.eq("00-0038542")].iloc[0]
    # Same 09-11-to-final drift as Cooper Rush above.
    assert (bijan.book_amer, bijan.first_amer, bijan.two_plus_amer) == (
        -125, 425, 500,
    )
    assert matchup.book.eq("DraftKings").all()


def test_latest_2026_week_is_default_release_when_present():
    import page_anytime_td as page

    assert page.default_release([(2025, 17), (2026, 1)]) == (2026, 1)
    assert page.default_release([(2026, 1), (2026, 2), (2026, 3)]) == (2026, 3)
    assert page.default_release([(2025, 10), (2025, 17)]) == (2025, 10)


def test_current_week1_keeps_published_past_game_results():
    release = page.available_releases()[(2026, 1)]
    expected = pd.read_csv(release)
    assert expected.prediction_mode.eq("retrospective").all()
    past = expected[expected.game_id.isin(["2026_01_NE_SEA", "2026_01_SF_LA"])]

    assert len(past) == 48
    # Efton Chism (NE_SEA) and Jordan James / CJ Daniels (SF_LA) took zero
    # snaps on any unit in the complete Week 1 snap-count table (see
    # td-settlement-proposal-v1, applied 2026-09-30, DATA_DEFECTS.md P15) and
    # are VOID, not a graded loss -- the same resolved-or-void distinction
    # already asserted for DEN_KC below.
    unresolved = past[past.settlement_status_anytime.astype(str).str.lower().eq("awaiting_evidence")]
    assert sorted(unresolved.player_display_name) == ["Max Klare", "Tory Horton"]
    assert pd.to_numeric(unresolved.scored_anytime, errors="coerce").eq(0).all()
    assert set(past.status) <= {"final", "void"}
    assert pd.isna(past.loc[past.status.eq("void"), "scored_anytime"]).all()
    assert list(past.loc[past.player_display_name.eq("Eli Raridon"), "scored_anytime"]) == [1]

    den_kc = expected[expected.game_id.eq("2026_01_DEN_KC")]
    assert len(den_kc) == 25
    # A quoted player with zero offensive snaps is VOID (no action), not a loss,
    # so "resolved" means graded OR void -- never silently blank.
    resolved = den_kc.settlement_status_anytime.astype(str).str.lower().isin({"settled", "void"})
    assert resolved.all()
    assert pd.to_numeric(den_kc.loc[den_kc.status.ne("void"), "scored_two_plus"], errors="coerce").notna().all()
    assert set(den_kc.status) <= {"final", "void"}
    assert pd.isna(den_kc.loc[den_kc.status.eq("void"), "scored_anytime"]).all()
    assert list(den_kc.loc[den_kc.player_display_name.eq("Kenneth Walker"), "scored_two_plus"]) == [1]


def test_matchups_are_grouped_then_split_by_team():
    import page_anytime_td as page

    rows = pd.DataFrame([
        {"game_id": "2026_01_NE_SEA", "team": "SEA", "opponent_team": "NE"},
        {"game_id": "2026_01_NE_SEA", "team": "NE", "opponent_team": "SEA"},
    ])
    groups = list(page._matchup_groups(rows))
    assert len(groups) == 1
    label, teams, grouped = groups[0]
    assert label == "NE vs SEA"
    assert teams == ["NE", "SEA"]
    assert set(grouped.team) == {"NE", "SEA"}

    later = rows.assign(
        game_id=["2026_01_ARI_LAC", "2026_01_ARI_LAC"],
        team=["ARI", "LAC"], opponent_team=["LAC", "ARI"],
        kickoff_et=["2026-09-13 16:25", "2026-09-13 16:25"],
    )
    ordered = list(page._matchup_groups(pd.concat([later, rows.assign(
        kickoff_et=["2026-09-10 20:20", "2026-09-10 20:20"]
    )], ignore_index=True)))
    assert [item[0] for item in ordered] == ["NE vs SEA", "ARI vs LAC"]


def test_default_matchup_skips_fully_graded_games():
    import page_anytime_td as page

    rows = pd.DataFrame([
        {
            "game_id": "2026_01_NE_SEA", "team": "NE", "opponent_team": "SEA",
            "kickoff_et": "2026-09-09 20:20", "scored_anytime": 0,
        },
        {
            "game_id": "2026_01_NE_SEA", "team": "SEA", "opponent_team": "NE",
            "kickoff_et": "2026-09-09 20:20", "scored_anytime": 1,
        },
        {
            "game_id": "2026_01_SF_LA", "team": "SF", "opponent_team": "LA",
            "kickoff_et": "2026-09-10 20:35", "scored_anytime": None,
        },
        {
            "game_id": "2026_01_SF_LA", "team": "LA", "opponent_team": "SF",
            "kickoff_et": "2026-09-10 20:35", "scored_anytime": None,
        },
    ])

    matchups = list(page._matchup_groups(rows))
    assert page.default_matchup_label(matchups) == "SF vs LAR"


def test_default_matchup_skips_started_games_before_grading():
    import page_anytime_td as page

    rows = pd.DataFrame([
        {
            "game_id": "2026_01_NE_SEA", "team": "NE", "opponent_team": "SEA",
            "kickoff_et": "2020-09-09 20:20", "scored_anytime": None,
        },
        {
            "game_id": "2026_01_ATL_PIT", "team": "ATL", "opponent_team": "PIT",
            "kickoff_et": "2099-09-13 13:00", "scored_anytime": None,
        },
    ])

    matchups = list(page._matchup_groups(rows))
    assert page.default_matchup_label(matchups) == "ATL vs PIT"


def test_live_tracker_uses_raw_inclusive_gap_and_separates_open_bets():
    import attd_tracker as tracker

    rows = pd.DataFrame({
        "season": [2026] * 4,
        "week": [1, 1, 2, 2],
        "game_id": ["g1", "g1", "g2", "g2"],
        "player_id": ["p1", "p2", "p3", "p3"],
        "p_ge1": [0.41, 0.31, 0.50, 0.50],
        "p_book": [0.40, 0.30, 0.40, 0.40],
        "book_amer": [150, 200, 150, 150],
        "scored_anytime": [1, None, 0, 0],
    })
    # The duplicate player-game row represents a later weekly release and
    # must not create a second paper bet.
    deduped = tracker.deduplicate_player_games([rows.iloc[:3], rows.iloc[3:]])
    result = tracker.season_tracker(deduped)
    summary = result["summary"]
    assert summary["bets"] == 3
    assert summary["settled_bets"] == 2
    assert summary["open_bets"] == 1
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["net_units"] == 0.5
    assert result["ci"]["available"] is False
    # Only 2 settled candidate bets -- below the same 20-bet floor the ROI
    # interval uses, so the selected-calibration disclosure stays hidden
    # rather than showing a percentage built on almost nothing.
    assert result["calibration"]["available"] is False


def test_published_tracker_preserves_legacy_rows_when_market_eligibility_is_added(tmp_path):
    import attd_tracker as tracker

    legacy = pd.DataFrame([{
        "season": 2026, "week": 1, "game_id": "g1", "player_id": "p1",
        "p_ge1": 0.50, "p_book": 0.40, "book_amer": 150,
        "scored_anytime": 1, "settlement_status_anytime": "settled",
        "p_ge2": 0.30, "two_plus_amer": 400,
        "scored_two_plus": 1, "settlement_status_two_plus": "settled",
        "p_first": 0.50, "book_first_p_devigged": 0.40, "first_amer": 150,
        "scored_first": 1, "settlement_status_first": "settled",
    }])
    current = legacy.copy()
    current["week"] = 4
    current["game_id"] = "g4"
    current["player_id"] = "p4"
    current["scored_anytime"] = None
    current["settlement_status_anytime"] = "open"
    current["scored_two_plus"] = None
    current["settlement_status_two_plus"] = "open"
    current["scored_first"] = None
    current["settlement_status_first"] = "open"
    current["bet_eligible_anytime"] = False
    current["bet_eligible_two_plus"] = False
    current["bet_eligible_first"] = False
    legacy_path = tmp_path / "week01.csv"
    current_path = tmp_path / "week04.csv"
    legacy.to_csv(legacy_path, index=False)
    current.to_csv(current_path, index=False)

    published = tracker.aggregate_published_csvs((legacy_path, current_path))
    summaries = (
        tracker.season_tracker(published),
        tracker.season_tracker(
            published, model_probability_col="p_ge2", book_probability_col=None,
            book_price_col="two_plus_amer", outcome_col="scored_two_plus",
            qualifies=lambda f: tracker.qualifies_two_plus_ratio(
                f["_model_probability"], f["_book_probability"],
            ),
        ),
        tracker.season_tracker(
            published, model_probability_col="p_first",
            book_probability_col="book_first_p_devigged", book_price_col="first_amer",
            outcome_col="scored_first",
            qualifies=lambda f: tracker.qualifies_first_td_ev(
                f["_model_probability"], f["_book_price"], f["_value_gap"],
            ),
        ),
    )
    for result in summaries:
        assert result["summary"]["bets"] == 1
        assert result["summary"]["settled_bets"] == 1
        assert result["summary"]["wins"] == 1


def test_tracker_accounts_for_void_separately_from_open_and_settled():
    import attd_tracker as tracker

    rows = pd.DataFrame({
        "season": [2026] * 3, "week": [1] * 3, "game_id": ["g1", "g2", "g3"],
        "player_id": ["p1", "p2", "p3"], "p_ge1": [0.5] * 3,
        "p_book": [0.4] * 3, "book_amer": [100] * 3,
        "scored_anytime": [1, None, None],
        "settlement_status_anytime": ["settled", "void", "awaiting_evidence"],
    })
    result = tracker.season_tracker(rows)
    summary = result["summary"]
    assert summary["bets"] == 3
    assert summary["settled_bets"] == 1
    assert summary["void_bets"] == 1
    assert summary["open_bets"] == 1
    assert summary["wins"] == 1 and summary["losses"] == 0
    assert summary["net_units"] == 1.0
    assert summary["accounting_invariant"] is True
    assert result["calibration"]["n"] == 1
    assert result["ci"]["settled_bets"] == 1


def test_selected_calibration_reports_mean_probabilities_and_hit_rate_on_settled_candidates():
    import attd_tracker as tracker

    # 20 settled candidate rows (the MIN_SETTLED_BETS_FOR_CI floor): 15 at
    # model_p=0.20/book_p=0.15 with 1 win (hit_rate 1/15), 5 at
    # model_p=0.40/book_p=0.30 with 3 wins (hit_rate 3/5). Hand-computed:
    # mean model_p = (15*0.20 + 5*0.40)/20 = 0.25, mean book_p =
    # (15*0.15 + 5*0.30)/20 = 0.1875, hit_rate = (1+3)/20 = 0.20.
    rows = pd.DataFrame({
        "season": [2026] * 20,
        "week": [1] * 20,
        "game_id": [f"g{i}" for i in range(20)],
        "player_id": [f"p{i}" for i in range(20)],
        "p_ge1": [0.20] * 15 + [0.40] * 5,
        "p_book": [0.15] * 15 + [0.30] * 5,
        "book_amer": [150] * 20,
        "scored_anytime": [1] + [0] * 14 + [1, 1, 1, 0, 0],
    })
    result = tracker.season_tracker(rows, threshold=0.01)
    calib = result["calibration"]
    assert calib["available"] is True
    assert calib["n"] == 20
    assert calib["mean_model_probability"] == pytest.approx(0.25)
    assert calib["mean_book_probability"] == pytest.approx(0.1875)
    assert calib["hit_rate"] == pytest.approx(0.20)


def test_two_plus_tracker_uses_two_plus_price_and_outcome_columns():
    import attd_tracker as tracker

    rows = pd.DataFrame({
        "season": [2026] * 3,
        "week": [1, 1, 1],
        "game_id": ["g1", "g2", "g3"],
        "player_id": ["p1", "p2", "p3"],
        "p_ge2": [0.205, 0.30, 0.21],
        "two_plus_amer": [400, 300, 400],
        "scored_two_plus": [1, 0, None],
    })
    result = tracker.season_tracker(
        rows,
        model_probability_col="p_ge2",
        book_probability_col=None,
        book_price_col="two_plus_amer",
        outcome_col="scored_two_plus",
        threshold=tracker.TWO_PLUS_VALUE_THRESHOLD,
    )
    summary = result["summary"]
    assert summary["bets"] == 3
    assert summary["settled_bets"] == 2
    assert summary["open_bets"] == 1
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["net_units"] == 3.0
    assert summary["roi"] == 1.5
    assert result["ci"]["available"] is False


def test_live_tracker_american_settlement_math_and_ci_is_deterministic():
    import attd_tracker as tracker

    assert tracker.american_to_decimal(-110) == 1 + 100 / 110
    assert tracker.american_to_decimal(150) == 2.5
    frame = pd.DataFrame({
        "season": [2026] * 20,
        "week": list(range(1, 21)),
        "game_id": [f"g{i}" for i in range(20)],
        "player_id": [f"p{i}" for i in range(20)],
        "p_ge1": [0.51] * 20,
        "p_book": [0.50] * 20,
        "book_amer": [150] * 20,
        "scored_anytime": [1, 0] * 10,
    })
    prepared = tracker.prepare_paper_bets(frame)
    first = tracker.block_bootstrap_roi(prepared)
    second = tracker.block_bootstrap_roi(prepared)
    assert first == second
    assert first["available"] is True
    assert first["resamples"] == 10_000


def test_each_market_uses_its_own_candidate_rule():
    """Anytime: flat +1.0pp gap. 2+ TD (since 2026-09-19): model >= 1.25x
    DraftKings' price AND that price >= 2%. First TD: +3.0pp gap AND positive
    expected return at DraftKings' real price (see test_first_td_ev_rule_*
    below for that market's own cases)."""
    import attd_tracker as tracker

    assert tracker.ATTD_VALUE_THRESHOLD == 0.01
    assert tracker.TWO_PLUS_VALUE_THRESHOLD == 0.005
    assert tracker.TWO_PLUS_RATIO_THRESHOLD == 1.25
    assert tracker.TWO_PLUS_PRICE_FLOOR == 0.02
    assert tracker.FIRST_TD_VALUE_THRESHOLD == 0.03

    # A 0.7pp gap is below the Anytime +1.0pp rule.
    frame = pd.DataFrame([{
        "player_display_name": "A Player", "team": "X", "position": "WR", "opponent_team": "Y",
        "p_ge1": 0.207, "p_book": 0.200, "fair_amer": 283, "book_amer": 400,
        "scored_anytime": None, "bet_eligible": True,
    }])
    assert not bool(page._display(frame)["_candidate"].iloc[0])
    # A 1.2pp Anytime gap clears the rule.
    frame.loc[0, "p_ge1"] = 0.212
    assert bool(page._display(frame)["_candidate"].iloc[0])

    # 2+ TD: three rows sharing the same base structure, each isolating one
    # side of the ratio-plus-floor rule.
    two_plus = pd.DataFrame([{
        "player_display_name": "Ratio Candidate", "team": "X", "position": "WR",
        "opponent_team": "Y", "p_ge2": 0.075, "two_plus_amer": 1900,  # implied 5%, ratio 1.5
        "scored_two_plus": None, "bet_eligible": True,
    }, {
        "player_display_name": "Ratio Too Low", "team": "X", "position": "WR",
        "opponent_team": "Y", "p_ge2": 0.06, "two_plus_amer": 1900,  # implied 5%, ratio 1.2
        "scored_two_plus": None, "bet_eligible": True,
    }, {
        "player_display_name": "Below Price Floor", "team": "X", "position": "WR",
        "opponent_team": "Y", "p_ge2": 0.02, "two_plus_amer": 9900,  # implied 1%, ratio 2.0
        "scored_two_plus": None, "bet_eligible": True,
    }])
    result = page._two_plus_display(two_plus).set_index("Player")
    assert bool(result.loc["Ratio Candidate · X", "_candidate"])
    assert not bool(result.loc["Ratio Too Low · X", "_candidate"])
    assert not bool(result.loc["Below Price Floor · X", "_candidate"])


def test_qualifies_two_plus_ratio_handles_nan_and_boundary():
    import attd_tracker as tracker

    model = pd.Series([0.075, 0.075, float("nan"), 0.02])
    book = pd.Series([0.05, float("nan"), 0.05, 0.01])
    result = tracker.qualifies_two_plus_ratio(model, book)
    assert list(result) == [True, False, False, False]
    # Exactly at the 1.25x ratio and exactly at the 2% price floor both qualify.
    boundary = tracker.qualifies_two_plus_ratio(pd.Series([0.025]), pd.Series([0.02]))
    assert bool(boundary.iloc[0])


def test_qualifies_first_td_ev_requires_both_gap_and_positive_ev():
    import attd_tracker as tracker

    # Row 0: 5.0pp gap and +10.5% EV at +750 -- clears both.
    # Row 1: 1.0pp gap -- fails the gap alone, regardless of EV.
    # Row 2: McCaffrey's confirmed 2026 Week 2 case -- 3.5pp gap clears the
    # gap rule, but +295's real price implies a -2.8% expected return.
    model = pd.Series([0.13, 0.09, 0.246])
    book_price = pd.Series([750, 750, 295])
    gap = pd.Series([0.05, 0.01, 0.035])
    result = tracker.qualifies_first_td_ev(model, book_price, gap)
    assert list(result) == [True, False, False]
    assert not tracker.qualifies_first_td_ev(
        pd.Series([float("nan")]), pd.Series([750.0]), pd.Series([0.05])
    ).iloc[0]
    assert not tracker.qualifies_first_td_ev(
        pd.Series([0.13]), pd.Series([float("nan")]), pd.Series([0.05])
    ).iloc[0]


def test_rule_description_for_each_market():
    import attd_tracker as tracker

    assert tracker.rule_description("anytime") == "+1.0pp value gap"
    two_plus_text = tracker.rule_description("two_plus")
    assert "1.25x" in two_plus_text and "2%" in two_plus_text
    first_text = tracker.rule_description("first")
    assert "one pick per game" in first_text and "highest expected return" in first_text
    assert "3.0pp" not in first_text
    legacy_text = tracker.rule_description("first_legacy")
    assert "3.0pp" in legacy_text and "expected return" in legacy_text


def test_v3_rule_text_and_qualifier_read_the_cap_from_the_frozen_params(tmp_path, monkeypatch):
    import attd_tracker as tracker

    monkeypatch.setattr(first_td_v3, "PARAMS_PATH", tmp_path / "absent.json")
    assert tracker.FIRST_TD_V3_PRICE_CAP is None
    assert "the frozen cap" in tracker.rule_description("first")
    # no cap available: fail closed
    assert not tracker.qualifies_first_td_best_value_v3(pd.Series([0.9]), pd.Series([300])).any()
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"k": 1.5, "p_offense_2026": 0.94, "price_cap_american": 2500}), encoding="utf-8")
    monkeypatch.setattr(first_td_v3, "PARAMS_PATH", params)
    assert tracker.FIRST_TD_V3_PRICE_CAP == 2500
    assert "+2500 or shorter" in tracker.rule_description("first")
    assert tracker.first_td_v3_cap_state() == (True, 2500)
    # params that set no cap: nothing is excluded for price and the rule text drops the clause
    params.write_text(json.dumps({"k": 1.1, "p_offense_2026": 0.94, "cap_american": None}), encoding="utf-8")
    assert tracker.first_td_v3_cap_state() == (True, None)
    assert "shorter" not in tracker.rule_description("first")
    assert tracker.qualifies_first_td_best_value_v3(pd.Series([0.30]), pd.Series([9000])).all()
    params.write_text(json.dumps({"k": 1.5, "p_offense_2026": 0.94, "price_cap_american": 2500}), encoding="utf-8")
    qualifies = tracker.qualifies_first_td_best_value_v3(
        pd.Series([0.30, 0.30, 0.04, 0.0401, float("nan")]),
        pd.Series([300, 300, 2500, 2600, 300]),
    )
    # row 2: exactly at the cap but 0.04 * 26 - 1 = +4%; row 3: positive return but past the cap
    assert list(qualifies) == [True, True, True, False, False]
    assert list(tracker.qualifies_first_td_best_value_v3(
        pd.Series([0.50, 0.50]), pd.Series([300, 200]), price_cap=250,
    )) == [False, True]


def test_first_td_display_candidate_requires_positive_ev_not_just_the_gap():
    """Mirrors the confirmed 2026 Week 2 McCaffrey case: clears the +3.0pp
    de-vigged gap but the real, vigged price implies a negative expected
    return, so it must not be highlighted as a candidate."""
    import page_anytime_td as page

    rows = pd.DataFrame([{
        "player_display_name": "Losing At Real Price", "team": "X", "position": "RB",
        "opponent_team": "Y", "p_first": 0.246, "book_first_p_devigged": 0.211,
        "first_amer": 295, "scored_first": None,
    }, {
        "player_display_name": "Real Candidate", "team": "X", "position": "WR",
        "opponent_team": "Y", "p_first": 0.13, "book_first_p_devigged": 0.08,
        "first_amer": 750, "scored_first": None,
    }])
    display = page._first_td_display(rows).set_index("Player")
    assert not bool(display.loc["Losing At Real Price · X", "_candidate"])
    assert bool(display.loc["Real Candidate · X", "_candidate"])


def test_first_td_display_shows_raw_price_when_full_market_is_unavailable():
    import page_anytime_td as page

    rows = pd.DataFrame([{
        "player_display_name": "Raw Price", "team": "X", "position": "WR",
        "opponent_team": "Y", "p_first": 0.20,
        "book_first_p_devigged": None, "first_amer": 400,
        "scored_first": None,
    }])
    display = page._first_td_display(rows)
    assert display.loc[0, "Book First TD Odds"] == "+400 · 20.0% implied"
    assert display.loc[0, "_book_phone"] == "+400 · 20.0% implied"
    assert display.loc[0, "Expected Return"] == "0%"
    assert "Full market unavailable" not in " ".join(display.astype(str).to_numpy().ravel())


def test_two_plus_season_tracker_uses_ratio_qualifier_not_flat_gap():
    """The season-tracker cards must narrow the same way the display does:
    both rows clear the legacy flat +0.5pp gap, but only the 1.5pp-gap row
    clears the 1.25x ratio rule (the 1pp-gap row is only a 1.2x ratio)."""
    import attd_tracker as tracker

    frame = pd.DataFrame({
        "season": [2026, 2026], "week": [1, 1],
        "game_id": ["g1", "g2"], "player_id": ["p1", "p2"],
        "p_ge2": [0.06, 0.065],
        "two_plus_amer": [1900, 1900],
        "scored_two_plus": [1, 1],
    })
    flat = tracker.season_tracker(
        frame, model_probability_col="p_ge2", book_probability_col=None,
        book_price_col="two_plus_amer", outcome_col="scored_two_plus",
        threshold=tracker.TWO_PLUS_VALUE_THRESHOLD,
    )
    ratio = tracker.season_tracker(
        frame, model_probability_col="p_ge2", book_probability_col=None,
        book_price_col="two_plus_amer", outcome_col="scored_two_plus",
        threshold=tracker.TWO_PLUS_RATIO_THRESHOLD,
        qualifies=lambda f: tracker.qualifies_two_plus_ratio(
            f["_model_probability"], f["_book_probability"],
        ),
    )
    assert flat["summary"]["bets"] == 2
    assert ratio["summary"]["bets"] == 1


# ---------------------------------------------------------------------------
# Weeks 1 to 6 are history: the First TD v3 work must not move them.
# Snapshots taken on 2026-10-20, before the v3 edits.
# ---------------------------------------------------------------------------

# Manifest hashes of the retrospective releases. Weeks 4 to 6 are re-graded in place by the
# grading job (it rewrites the settlement columns and refreshes the manifest hash, as it did for
# Weeks 4 and 5 in "Auto: grade published releases"), so those weeks are pinned by the hash of
# everything except the grading columns below instead.
LEGACY_RETROSPECTIVE_MANIFEST_SHA256 = {
    1: "dc3eada6dca75f089d73f6e0724d8e810db83ecb57b6e3730048b75a0e05195e",
    2: "278787fad6587a6714c598e3656c52b164b74323c0ffe543beb30edc1c633060",
    3: "dc121b8b3d5719cea4b39c33af7c6a42d3fe4064cb59f24eb00c6eab211b1cea",
}
LEGACY_CONTENT_SHA256 = {
    1: "cae46bbaade6b2f69c932c7b7eeaec17092ddfbd15ef95d212f0c408ffda7e62",
    2: "15874b9fb26e667ec29b6ee01dd00ae7298ed6d9f67f5b57ef1cc10ba4f0b227",
    3: "e87124e6d43ea725d40ca4f5fb2dd45ba478b0dfe9690c26bfef92cac1f2cf4c",
    4: "f8716d198565dea0384ebafc8080d2a559e2843b2538f7de9e6802b955bb887a",
    5: "57a6e08d47c8db3cc9273f656ac2c67c6380a708fb98eff9c8a97b542bbcd220",
    6: "961434ef11df93f725e5d1a2edbcec2d5ff9b607ce3170057317341fbc62647d",
}
_NO_BETS = {"bets": 0, "settled_bets": 0, "void_bets": 0, "open_bets": 0, "wins": 0, "losses": 0,
            "stake_units": 0.0, "net_units": 0.0, "roi": None}
_LOST_3 = {"bets": 3, "settled_bets": 3, "void_bets": 0, "open_bets": 0, "wins": 0, "losses": 3,
           "stake_units": 3.0, "net_units": -3.0, "roi": -1.0}
_LOST_6 = {"bets": 6, "settled_bets": 6, "void_bets": 0, "open_bets": 0, "wins": 0, "losses": 6,
           "stake_units": 6.0, "net_units": -6.0, "roi": -1.0}
LEGACY_FIRST_TD_WEEK_SUMMARY = {1: _NO_BETS, 2: _NO_BETS, 3: _NO_BETS, 4: _LOST_3, 5: _LOST_3, 6: _NO_BETS}
LEGACY_FIRST_TD_SEASON_SUMMARY = {5: _LOST_6, 6: _LOST_6}
_SUMMARY_KEYS = tuple(_NO_BETS)
_GRADING_COLUMN_PREFIXES = ("scored_", "settlement_status_")


def _content_sha256(path) -> str:
    frame = pd.read_csv(path)
    keep = [c for c in frame.columns if not c.startswith(_GRADING_COLUMN_PREFIXES) and c != "status"]
    return hashlib.sha256(frame[keep].to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def _legacy_summary(frame) -> dict:
    summary = page._tracker_for_market(frame, "first")["summary"]
    return {key: summary[key] for key in _SUMMARY_KEYS}


def test_week_1_to_6_releases_are_unchanged():
    from publishing.td_releases import canonical_td_releases

    releases = canonical_td_releases(page._DIR)
    for week in range(1, 7):
        entry = releases[(2026, week)]
        assert hashlib.sha256(entry["csv_path"].read_bytes()).hexdigest() == entry["csv_sha256"]
        assert _content_sha256(entry["csv_path"]) == LEGACY_CONTENT_SHA256[week], f"Week {week} prices or probabilities moved"
    for week, expected in LEGACY_RETROSPECTIVE_MANIFEST_SHA256.items():
        assert releases[(2026, week)]["csv_sha256"] == expected


def test_week_1_to_6_legacy_first_td_tracker_summaries_are_unchanged():
    from publishing.td_releases import canonical_td_releases

    releases = canonical_td_releases(page._DIR)
    for week, expected in LEGACY_FIRST_TD_WEEK_SUMMARY.items():
        frame = page.priced_rows(read_td_release(releases[(2026, week)]["csv_path"]))
        assert _legacy_summary(frame) == expected, f"Week {week} legacy First TD record moved"
    paths = tuple(str(releases[(2026, week)]["csv_path"]) for week in range(1, 7))
    for through, expected in LEGACY_FIRST_TD_SEASON_SUMMARY.items():
        frame = page.tracker.aggregate_published_csvs(paths)
        frame = frame[pd.to_numeric(frame["week"], errors="coerce").le(through)]
        assert _legacy_summary(frame) == expected


def test_legacy_cards_keep_their_old_rule_text(tmp_path):
    at = _render(tmp_path, week=4)
    at.segmented_control(key="atd_view_2026_4").set_value("First TD").run()
    at.selectbox(key="atd_props_matchup_2026_4").set_value(page.RECOMMENDED_LABEL).run()
    assert not at.exception, at.exception
    captions = " ".join(str(c.value) for c in at.caption)
    assert "fixed rule: +3.0pp value gap AND a positive expected return" in captions
    assert "#### Best-value picks" not in " ".join(str(item.value) for item in at.markdown)
