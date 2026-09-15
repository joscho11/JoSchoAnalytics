"""Anytime TDs demo page. Hermetic APP_OFFLINE=1."""
import os
import re
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))

import page_anytime_td as page


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


def test_anytime_td_renders_and_owns_controls(tmp_path):
    at = _render(tmp_path)
    keys = {getattr(w, "key", None) for w in list(at.selectbox)}
    assert {"atd_year", "atd_week"}.issubset(keys), keys
    assert len(at.tabs) == 0
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["atd_year"] == 2026
    assert controls["atd_week"] == 2
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
    assert any(getattr(w, "key", None) == "atd_matchup_2026_2" for w in at.selectbox)
    assert any(getattr(w, "key", None) == "atd_view_2026_2" for w in at.segmented_control)
    assert any(getattr(w, "key", None) == "atd_search" for w in at.text_input)
    metric_labels = {str(metric.label) for metric in at.metric}
    assert {"Net units", "ROI", "Record", "Approx. 95% ROI range"} <= metric_labels
    expected = pd.read_csv(_HERE / "betting" / "anytime_td" / "anytime_td_2026_week02.csv")
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


def test_two_plus_toggle_preserves_market_or_placeholder(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    at.toggle(key="atd_rec_2026_1_2+ TD").set_value(False).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("2+ TD view" in str(item.value) for item in at.caption)
    assert set(at.dataframe[0].value.columns) == set([
        "#", "Player", "Pos", "Opp", "Model 2+ TD Odds",
        "Book 2+ TD Odds", "2+ TD Value Gap",
    ])
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


def test_ne_sea_display_only_two_plus_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.selectbox(key="atd_matchup_2026_1").set_value("NE vs SEA").run()
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    at.toggle(key="atd_rec_2026_1_2+ TD").set_value(False).run()
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
    at.selectbox(key="atd_matchup_2026_1").set_value("SF vs LA").run()
    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    at.toggle(key="atd_rec_2026_1_2+ TD").set_value(False).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical 2+ TD model view for SF vs LA" in info
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
    at.toggle(key="atd_rec_2026_1_First TD").set_value(False).run()
    at.selectbox(key="atd_matchup_2026_1").set_value("NO vs DET").run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("First TD" in str(item.value) for item in at.info)
    columns = set(at.dataframe[0].value.columns)
    assert {
        "#", "Player", "Pos", "Opp", "Model First TD Odds",
        "Book First TD Odds", "First TD Value Gap",
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
    at.toggle(key="atd_rec_2026_1_2+ TD").set_value(False).run()
    assert not at.exception, at.exception
    assert "Model 2+ TD Odds" in set(at.dataframe[0].value.columns)

    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    at.toggle(key="atd_rec_2026_1_First TD").set_value(False).run()
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
    at.toggle(key="atd_rec_2026_1_First TD").set_value(False).run()
    at.selectbox(key="atd_matchup_2026_1").set_value("NO vs DET").run()
    md = " ".join(str(item.value) for item in at.markdown)
    assert "First TDs**" in md
    assert "Anytime TDs**" not in md

    at.segmented_control(key="atd_view_2026_1").set_value("2+ TD").run()
    at.toggle(key="atd_rec_2026_1_2+ TD").set_value(False).run()
    md = " ".join(str(item.value) for item in at.markdown)
    assert "2+ TDs**" in md


def test_ne_sea_display_only_first_td_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    at.toggle(key="atd_rec_2026_1_First TD").set_value(False).run()
    at.selectbox(key="atd_matchup_2026_1").set_value("NE vs SEA").run()
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
        "Results-only First TD tally" in str(item.value)
        for item in at.caption
    )


def test_sf_la_display_only_first_td_model_view_is_shown(tmp_path):
    at = _render(tmp_path, week=1)
    at.segmented_control(key="atd_view_2026_1").set_value("First TD").run()
    at.toggle(key="atd_rec_2026_1_First TD").set_value(False).run()
    at.selectbox(key="atd_matchup_2026_1").set_value("SF vs LA").run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    info = " ".join(str(item.value) for item in at.info)
    assert "Display-only historical First TD model view for SF vs LA" in info
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
    assert list(table["Player"]) == ["Alpha · AAA", "Gamma · BBB", "Beta · AAA"]
    assert table.loc[0, "_value"] > table.loc[1, "_value"] > table.loc[2, "_value"]
    assert table.loc[0, "_candidate"]


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
    rec_toggle = next(w for w in at.toggle if w.key.startswith("atd_rec"))
    at.toggle(key=rec_toggle.key).set_value(False).run()
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
    rec_toggle = next(w for w in at.toggle if w.key.startswith("atd_rec"))
    at.toggle(key=rec_toggle.key).set_value(False).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(list(at.dataframe)) > 0


def test_qualifies_probability_gap_never_returns_na():
    import attd_tracker as tracker

    gap = pd.Series([0.01, float("nan"), 0.06], dtype="Float64")
    result = tracker.qualifies_probability_gap(gap)
    assert result.dtype == bool
    assert list(result) == [True, False, True]


def test_pending_replacement_caption_pluralizes_the_verb(tmp_path):
    # "1 quoted replacement row await model inputs" is a subject-verb
    # mismatch. Requires exactly one pending row on the live board.
    at = _render(tmp_path, week=1)
    raw = pd.read_csv(_HERE / "betting" / "anytime_td" / "anytime_td_2026_week01.csv")
    pending_count = int(page.priced_rows(raw).p_ge1.isna().sum())
    captions = " ".join(str(c.value) for c in at.caption)
    if pending_count == 1:
        assert "1 quoted replacement row awaits model inputs" in captions
        assert "row await model" not in captions
    elif pending_count > 1:
        assert f"{pending_count} quoted replacement rows await model inputs" in captions


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


def test_two_plus_candidate_uses_same_gap_highlight():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Boundary", "Other"],
        "position": ["RB", "WR"],
        "team": ["KC", "SF"],
        "opponent_team": ["LV", "SEA"],
        "p_ge1": [0.40, 0.35],
        "p_ge2": [0.205, 0.20],
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


def test_live_week1_reconciles_tua_out_and_updated_atl_pit_prices():
    live = pd.read_csv(
        _HERE / "betting" / "anytime_td" / "anytime_td_2026_week01.csv"
    )
    matchup = live[live.game_id.eq("2026_01_ATL_PIT")]

    assert not live.player_display_name.eq("Tua Tagovailoa").any()
    cooper = matchup[matchup.player_id.eq("00-0033662")].iloc[0]
    assert cooper.player_display_name == "Cooper Rush"
    # Price moved between the 09-11 pregame capture (1500/6000/17000, see
    # anytime_td_2026_week01.csv.bak_before_first_td) and the final graded
    # board. Cooper Rush stays model_pending (no slp_proj feature): lambda,
    # p_ge1, p_ge2, fair_amer, p_first are NaN in the live file.
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
    assert page.default_release([(2026, 1), (2026, 2)]) == (2026, 2)
    assert page.default_release([(2025, 10), (2025, 17)]) == (2025, 10)


def test_current_week1_keeps_published_past_game_results():
    expected = pd.read_csv(_HERE / "betting" / "anytime_td" / "anytime_td_2026_week01.csv")
    past = expected[expected.game_id.isin(["2026_01_NE_SEA", "2026_01_SF_LA"])]

    assert len(past) == 48
    assert pd.to_numeric(past.scored_anytime, errors="coerce").notna().all()
    assert set(past.status) == {"final"}
    assert list(past.loc[past.player_display_name.eq("Eli Raridon"), "scored_anytime"]) == [1]

    den_kc = expected[expected.game_id.eq("2026_01_DEN_KC")]
    assert len(den_kc) == 25
    assert pd.to_numeric(den_kc.scored_anytime, errors="coerce").notna().all()
    assert pd.to_numeric(den_kc.scored_two_plus, errors="coerce").notna().all()
    assert set(den_kc.status) == {"final"}
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
    assert page.default_matchup_label(matchups) == "SF vs LA"


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
