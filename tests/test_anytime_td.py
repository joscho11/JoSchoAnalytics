"""Anytime TDs demo page. Hermetic APP_OFFLINE=1."""
import os
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))

import page_anytime_td as page


def _render(tmp_path):
    harness = tmp_path / "h_anytime_td.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_anytime_td as p\np.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def test_anytime_td_renders_and_owns_controls(tmp_path):
    at = _render(tmp_path)
    keys = {getattr(w, "key", None) for w in list(at.selectbox)}
    assert {"atd_year", "atd_week"}.issubset(keys), keys
    assert len(at.tabs) == 0
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["atd_year"] == 2026
    assert controls["atd_week"] == 1
    titles = " ".join(str(t.value) for t in at.title)
    assert "Anytime TDs" in titles
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
    assert any(getattr(w, "key", None) == "atd_matchup_2026_1" for w in at.selectbox)
    assert any(getattr(w, "key", None) == "atd_two_plus_2026_1" for w in at.toggle)
    assert any(getattr(w, "key", None) == "atd_search" for w in at.text_input)
    expected = pd.read_csv(_HERE / "betting" / "anytime_td" / "anytime_td_2026_week01.csv")
    expected_default = page.default_matchup_label(list(page._matchup_groups(expected)))
    assert expected_default in {str(w.value) for w in at.selectbox}
    selected = next(
        group for label, _, group in page._matchup_groups(expected)
        if label == expected_default
    )
    expected_counts = sorted(selected.groupby("team").size().tolist())
    rendered_counts = sorted(len(frame.value) for frame in at.dataframe)
    assert rendered_counts == sorted(expected_counts * 2)
    assert set(at.dataframe[0].value.columns) == set(
        ["#", "Player", "Pos", "Opp", "Model ATTD Odds", "Book ATTD Odds", "ATTD Value Gap"]
    )


def test_two_plus_toggle_shows_book_market_when_available(tmp_path):
    at = _render(tmp_path)
    at.toggle(key="atd_two_plus_2026_1").set_value(True).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("2+ TD view" in str(item.value) for item in at.caption)
    assert set(at.dataframe[0].value.columns) == set([
        "#", "Player", "Pos", "Opp", "Model 2+ TD Odds",
        "Book 2+ TD Odds", "2+ TD Value Gap",
    ])
    assert at.dataframe[0].value["Book 2+ TD Odds"].ne("Not implemented yet").any()
    assert at.dataframe[0].value["2+ TD Value Gap"].ne("Not implemented yet").any()


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


def test_anytime_td_files_cover_weeks_10_17():
    import page_anytime_td as page

    weeks = page.available_weeks()
    assert list(weeks) == list(range(10, 18)), weeks


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
    assert page._value_gap(144, 150, 0.411, 0.400) == "+6 · +1.1%"


def test_phone_grid_keeps_value_and_five_other_pinned_columns():
    import page_anytime_td as page

    assert page.PHONE_COLS == [
        "#", "Player", "Model ATTD Odds", "Book ATTD Odds", "ATTD Value Gap", "Hit",
    ]
    assert page.PHONE_LABELS["Model ATTD Odds"] == "Model"
    assert page.PHONE_LABELS["Book ATTD Odds"] == "Book"
    assert page.PHONE_LABELS["ATTD Value Gap"] == "Value"
    assert page.PHONE_WIDTHS["#"] >= 50
    assert set(page.PHONE_COLS).issubset(page.DESKTOP_COLS)


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


def test_2026_week1_is_default_release_when_present():
    import page_anytime_td as page

    assert page.default_release([(2025, 17), (2026, 1)]) == (2026, 1)
    assert page.default_release([(2026, 1), (2026, 2)]) == (2026, 1)
    assert page.default_release([(2025, 10), (2025, 17)]) == (2025, 10)


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
    assert page.default_matchup_label(matchups) == "SF vs LA"
