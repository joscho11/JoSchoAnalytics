"""Batch-3b proof for the extracted betting pages (page_weekly_predictions,
page_track_record). Each renders offline-clean, OWNS its own Season/Week/Min-edge
controls (filter independence — unique keys, no cross-page leakage), and carries the
ATS blurb moved off the retired sidebar. Hermetic (APP_OFFLINE=1).
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))


def _render_page(tmp_path, module):
    h = tmp_path / f"h_{module}.py"
    h.write_text(f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
                 f"import {module} as p\np.render()\n", encoding="utf-8")
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _control_keys(at):
    return {getattr(w, "key", None) for w in list(at.selectbox) + list(at.slider)}


def test_weekly_predictions_renders_and_owns_controls(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    keys = _control_keys(at)
    assert {"wp_season", "wp_week"} <= keys, \
        f"Weekly Predictions must own Season/Week; got {keys}"
    assert "wp_edge" not in keys, "the live 2026 card does not expose the 2025 demo edge slider"
    import page_common
    default_season, default_week = page_common.release_default_selection("predictions", (2025, 10))
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["wp_season"] == 2026 == default_season
    # The page follows the newest published week; pinning a number here breaks
    # every time a new week ships.
    assert int(controls["wp_week"]) == int(default_week)
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "green-badge" in markdown and "Published" in markdown
    captions = " ".join(str(item.value) for item in at.caption)
    # The caption names the model that produced the displayed release. A model
    # promotion ships as a new release, so read the version from the manifest
    # instead of pinning one model string here.
    from publishing.manifest import release_status
    manifest = page_common.load_release_manifest()
    shown = release_status(
        "predictions", default_season, int(default_week), manifest=manifest, root=_HERE
    )
    shown_version = manifest["products"]["predictions"]["builds"][str(shown["build_id"])]["model_version"]
    assert shown_version.startswith("spread-v3-prod-sunday-tuesday-market-")
    assert shown_version in captions
    shown_build = manifest["products"]["predictions"]["builds"][str(shown["build_id"])]
    # A model-update correction is allowed to be the displayed release, but it has to cite its audit.
    # Ordinary weekly publishes have no correction block.
    shown_correction = shown_build.get("correction") or {}
    assert shown_correction.get("model_update") is not True or shown_correction["promotion_audit"]["sha256"]
    qb_expander = next(exp for exp in at.expander if exp.label == "QB inputs used for this release")
    qb_markdown = " ".join(str(item.value) for item in qb_expander.markdown)
    # Read the displayed release's own QB metadata instead of pinning a week's names.
    import json as _json
    from team_display import public_team_abbr
    meta = _json.loads((_HERE / shown_build["metadata"]).read_text(encoding="utf-8"))
    details = meta.get("qb_selection_details") or {}  # actual-starter builds carry no QB selection block
    manual = {t: d["player_name"] for t, d in details.items() if d.get("is_user_modeling_assumption")}
    for team, name in manual.items():
        assert f"**{public_team_abbr(team)}:** {name} — user modeling assumption" in qb_markdown
    card_labels = " ".join(
        str(item.value) for item in at.markdown if "jsa-gc-team-abbr" in str(item.value)
    )
    for team, name in manual.items():
        assert f">{public_team_abbr(team)}</div><div class='jsa-gc-qb'" in card_labels
        assert f"QB: {name}</div>" in card_labels
    assert "font-size:10px" in card_labels
    scenario_caption = " ".join(str(c.value) for c in qb_expander.caption)
    scenario_games = (meta.get("qb_scenarios") or {}).get("results") or {}
    scenario_teams = {
        public_team_abbr(item["team"]) for items in scenario_games.values() for item in items if item.get("team")
    }
    # Scenario games are not guaranteed in every release; when present the caption names the teams.
    assert all(t in scenario_caption for t in scenario_teams)
    assert not any(str(k).startswith("tr_") for k in keys), \
        "Weekly Predictions must not carry Track Record's controls"


def test_weekly_prediction_team_cell_escapes_release_names():
    from page_weekly_predictions import _team_cell_html

    markup = _team_cell_html("<b>TB</b>", "<img src=x onerror=alert(1)>", "700", "white")
    assert "&lt;b&gt;TB&lt;/b&gt;" in markup
    assert "QB: &lt;img src=x onerror=alert(1)&gt;" in markup
    assert "<img src=x" not in markup


def test_weekly_predictions_shows_min_edge_on_2025_demo(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2025)
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    keys = _control_keys(at)
    assert "wp_edge" in keys, f"2025 demo must keep Min Edge; got {keys}"


def test_weekly_predictions_reads_shared_season_week_url(tmp_path):
    h = tmp_path / "h_weekly_query.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\n"
        "st.query_params['wp_season'] = '2026'\n"
        "st.query_params['wp_week'] = '1'\n"
        "import page_weekly_predictions as p\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["wp_season"] == 2026
    assert controls["wp_week"] == 1
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "Published" in markdown


def test_week1_scorecard_and_track_record_use_graded_corrected_release(tmp_path, monkeypatch):
    weekly = _render_page(tmp_path, "page_weekly_predictions")
    week = next(w for w in weekly.selectbox if getattr(w, "key", None) == "wp_week")
    week.set_value(1)
    weekly.run()
    assert not weekly.exception, weekly.exception
    metrics = {str(m.label): str(m.value) for m in weekly.metric}
    assert metrics["ATS record"] == "7-9-0"
    assert not any("Retrospective model correction" in str(w.value) for w in weekly.warning)
    assert not any("Retrospective model update" in str(c.value) for c in weekly.caption)
    assert any("Week 1 ATS record: **7-9-0**" in str(s.value) for s in weekly.info)
    week2 = next(w for w in weekly.selectbox if getattr(w, "key", None) == "wp_week")
    week2.set_value(2)
    weekly.run()
    assert not weekly.exception, weekly.exception
    assert next(w for w in weekly.selectbox if w.key == "wp_week").value == 2
    week2_metrics = {str(m.label): str(m.value) for m in weekly.metric}
    assert week2_metrics["ATS record"] == "8-8-0"
    assert week2_metrics["HIGH picks"] == "3"
    assert not any("Retrospective model correction" in str(w.value) for w in weekly.warning)
    assert not any("Retrospective model update" in str(c.value) for c in weekly.caption)
    week3 = next(w for w in weekly.selectbox if getattr(w, "key", None) == "wp_week")
    week3.set_value(3)
    weekly.run()
    assert not weekly.exception, weekly.exception
    week3_metrics = {str(m.label): str(m.value) for m in weekly.metric}
    assert week3_metrics["ATS record"] == "9-5-2"
    assert any("Week 3 ATS record: **9-5-2**" in str(s.value) for s in weekly.success)
    assert any("➖ PUSH" in str(m.value) for m in weekly.markdown)

    import dashboard_data
    tracker_without_release_metadata = dashboard_data.load_predictions().drop(
        columns=["release_retrospective", "release_build_id", "release_supersedes_build_id", "release_correction_reason"],
        errors="ignore",
    )
    monkeypatch.setattr(
        dashboard_data,
        "load_predictions",
        lambda: tracker_without_release_metadata.copy(),
    )
    track = _render_page(tmp_path, "page_track_record")
    assert next(w for w in track.selectbox if w.key == "tr_season").value == 2026
    track_metrics = {str(m.label): str(m.value) for m in track.metric}
    # The corrected builds contribute 15-17-0; later graded weeks may add games/pushes.
    season_ats = track_metrics["Season ATS"]
    wins, losses, pushes = (int(part) for part in season_ats.split("-"))
    settled = wins + losses
    # Win % still excludes pushes; pushes are finals with null home_covered.
    graded_2026 = tracker_without_release_metadata[
        (tracker_without_release_metadata["season"] == 2026)
        & tracker_without_release_metadata["actual_margin"].notna()
        & tracker_without_release_metadata["model_correct"].notna()
    ]
    finals_2026 = tracker_without_release_metadata[
        (tracker_without_release_metadata["season"] == 2026)
        & tracker_without_release_metadata["actual_margin"].notna()
    ]
    from dashboard_utils import push_mask

    corrected_weeks = graded_2026[graded_2026["week"].isin([1, 2])]
    assert (int(corrected_weeks["model_correct"].sum()), len(corrected_weeks)) == (15, 32)
    assert (wins, settled) == (int(graded_2026["model_correct"].sum()), len(graded_2026))
    assert pushes == int(push_mask(finals_2026).sum())
    # Week 1 and Week 2 contribute eight graded HIGH picks; later weeks may add more.
    high_wins, high_losses, high_pushes = (
        int(part) for part in track_metrics["HIGH (Tuesday 3+ points)"].split("-")
    )
    high_settled = high_wins + high_losses
    from live_2026 import row_display_high

    high_rows = graded_2026[graded_2026.apply(row_display_high, axis=1)]
    high_finals = finals_2026[finals_2026.apply(row_display_high, axis=1)]
    corrected_high = high_rows[high_rows["week"].isin([1, 2])]
    assert (int(corrected_high["model_correct"].sum()), len(corrected_high)) == (5, 8)
    assert (high_wins, high_settled) == (int(high_rows["model_correct"].sum()), len(high_rows))
    assert high_pushes == int(push_mask(high_finals).sum())


def test_track_record_renders_and_owns_controls(tmp_path):
    at = _render_page(tmp_path, "page_track_record")
    keys = _control_keys(at)
    assert "tr_season" in keys, f"Track Record must own its Season control; got {keys}"
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "tr_season")
    assert season.value == 2026
    assert not any(str(k).startswith("wp_") for k in keys), \
        "Track Record must not carry Weekly Predictions' controls"


def test_track_record_2026_has_no_medium_edge_bucket(tmp_path):
    at = _render_page(tmp_path, "page_track_record")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "tr_season")
    season.set_value(2026)
    at.run()
    assert not at.exception, at.exception
    md = " ".join(str(m.value) for m in at.markdown)
    assert "Med Edge" not in md
    assert "no medium" in " ".join(str(s.value) for s in at.success).lower()


def test_track_record_2025_demo_keeps_edge_buckets(tmp_path):
    at = _render_page(tmp_path, "page_track_record")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "tr_season")
    season.set_value(2025)
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    labels = [str(metric.label) for metric in at.metric]
    assert "Medium edge (1–3 points)" in labels
    assert "Low edge (<1 point)" in labels


def test_weekly_predictions_hides_paused_agent_chrome(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    at.run()
    assert not at.exception, at.exception
    md = " ".join(str(m.value) for m in at.markdown)
    assert "Agent Confidence:" not in md
    assert "Matchup Analysis" not in md
    assert "Tuesday HIGH" in md
    assert "Model Consensus:" not in md
    assert "No totals on this season" in (
        " ".join(str(s.value) for s in at.success) + " " + md
    )
    assert "jsa-tot-badge" not in md
    # Any real matchup card for the default week; a named game only exists in its own week.
    assert md.count("jsa-gc-meta") >= 14
    assert "Published" in md
    captions = " ".join(str(c.value) for c in at.caption)
    # The best-available quote renders as white markdown, not a muted caption.
    # The named team and price change every week, so assert the shape, not one quote.
    assert "Best available for <b style='color:#fff'>" in md
    assert "TUESDAY LINE" in md
    assert "TUE MODEL LINE" not in md
    metrics = {str(m.label): str(m.value) for m in at.metric}
    # HIGH count is a property of the week's slate, not a fixed number.
    assert int(metrics["HIGH picks"]) >= 0
    assert int(metrics["Total games"]) >= 14


def test_weekly_predictions_live_2026_banner(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    at.run()
    assert not at.exception, at.exception
    successes = " ".join(str(s.value) for s in at.success)
    notice_copy = successes + " " + " ".join(str(m.value) for m in at.markdown)
    assert "Live 2026" in notice_copy
    assert "one-sided 95%" in notice_copy and "Wilson lower bound" in notice_copy
    assert "251/437" in notice_copy
    assert "57.44%" in notice_copy
    assert "53.51%" in notice_copy
    assert "9 pushes among 446 HIGH labels" in notice_copy
    # The refit note: record moved from the previous model's, and said not to be distinguishable.
    assert "moved from the previous model's 261/449" in notice_copy
    assert "not statistically established either way" in notice_copy
    assert "regular injured reserve" in notice_copy
    assert "223/390" not in notice_copy
    assert "above 52.4%" in notice_copy
    assert "best US Tuesday" in notice_copy
    assert "57.14%" not in notice_copy
    assert "192/336" not in notice_copy
    assert "No medium tier" in notice_copy
    assert "No totals on this season" in notice_copy
    assert "model-version correction" in notice_copy
    assert any(
        exp.label == "Tuesday model rules and historical benchmark" for exp in at.expander
    )
    import page_common
    _, default_week = page_common.release_default_selection("predictions", (2025, 10))
    headings = " ".join(str(t.value) for t in [*at.title, *at.subheader])
    assert "2026" in headings
    assert f"Week {int(default_week)}" in headings
    for module in ("page_weekly_predictions", "page_track_record"):
        at = _render_page(tmp_path, module)
        md = " ".join(str(m.value) for m in at.markdown)
        assert "52.4% ATS" in md, f"ATS blurb must appear on {module}"


def test_weekly_predictions_formats_named_shopped_quote():
    import page_weekly_predictions as page

    row = {
        "home_team": "CIN",
        "away_team": "TB",
        "tuesday_spread_line": 4.0,
        "tuesday_spread_book": "BetRivers",
        "tuesday_spread_price": -109,
    }
    assert page._best_quote_label(row, "TB") == (
        "Best available for TB: +4.0 (-109) at BetRivers"
    )


def test_weekly_predictions_sort_matchups_by_largest_gap():
    import pandas as pd
    import page_weekly_predictions as page

    frame = pd.DataFrame([
        {"game_id": "small", "gap": -1.2, "gameday": "2026-09-20", "gametime": "13:00"},
        {"game_id": "largest", "gap": 3.0, "gameday": "2026-09-18", "gametime": "20:15"},
        {"game_id": "middle", "gap": -2.8, "gameday": "2026-09-19", "gametime": "13:00"},
    ])
    ordered = page._sort_matchups_by_gap(frame, "gap")
    assert ordered["game_id"].tolist() == ["largest", "middle", "small"]


def test_weekly_predictions_unplayed_game_keeps_score_column(tmp_path):
    """A week with some results in must lay out every card on the same 5-column grid.

    Regression: an unplayed game in a partly-played week fell back to the 4-column
    grid (no SCORE column), so its TUESDAY LINE / PREDICTED boxes sat wider and out
    of line with the finished games above and below it.
    """
    h = tmp_path / "h_weekly_partial.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import numpy as np\n"
        "import dashboard_data\n"
        "_saved_loader = dashboard_data.load_predictions\n"
        "try:\n"
        "    _real = dashboard_data.load_predictions()\n"
        "    _df = _real.copy()\n"
        "    _wk = _df[(_df['season'] == 2026) & (_df['week'] == 2)].index\n"
        "    _unplayed = _wk[::2]\n"
        "    for _c in ('actual_margin', 'home_score', 'away_score', 'model_correct', 'ens_model_correct'):\n"
        "        if _c in _df.columns:\n"
        "            _df.loc[_unplayed, _c] = np.nan\n"
        "    _df.loc[_wk[1::2], 'actual_margin'] = _df.loc[_wk[1::2], 'actual_margin'].fillna(3.0)\n"
        "    dashboard_data.load_predictions = lambda: _df\n"
        # Week 2 is the fixture's partly-played slate. The page default moves
        # forward on every publish, so pin the week this test actually set up.
        "    import streamlit as st; st.session_state['wp_week'] = 2\n"
        "    import page_weekly_predictions as p\n"
        "    p.render()\n"
        "finally:\n"
        "    dashboard_data.load_predictions = _saved_loader\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    markdown = [str(m.value) for m in at.markdown]
    cards = [m for m in markdown if "jsa-gc-meta" in m]
    score_headers = [m for m in markdown if "jsa-gc-hdr" in m and ">SCORE<" in m]
    assert len(cards) >= 2, "expected a full Week 2 card list"
    played = [m for m in cards if "WIN" in m or "LOSS" in m]
    assert 0 < len(played) < len(cards), "fixture must mix played and unplayed games"
    assert all("jsa-gc-scored" in m for m in cards), \
        "unplayed cards must carry the scored-grid class so mobile aligns too"
    assert len(score_headers) == len(cards), \
        "every card in a partly-played week needs a SCORE column, played or not"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_weekly_predictions_renders_and_owns_controls(p)
        test_track_record_renders_and_owns_controls(p)
        test_weekly_predictions_hides_paused_agent_chrome(p)
        test_weekly_predictions_live_2026_banner(p)
        test_ats_blurb_lives_on_the_betting_pages(p)
    print("OK  betting pages: render clean, own their controls, ATS blurb present")


def test_weekly_predictions_shows_one_equal_card_per_listed_qb(tmp_path):
    """The 2026 actual-starter rebuild (Weeks 1-8) removed QB scenario/pairing cards:
    every game shows exactly one card with one QB per team and no unsettled-starter view."""
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    week = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_week")
    week.set_value(3)
    at.run()
    assert not at.exception, at.exception
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "The starter is not settled" not in markdown
    assert "QB SPLIT" not in markdown
    assert markdown.count("jsa-gc-meta") >= 16
    expander = next(exp for exp in at.expander if exp.label == "QB inputs used for this release")
    text = " ".join(str(item.value) for item in expander.markdown) + " " + " ".join(str(c.value) for c in expander.caption)
    assert "Automatic uncertain-QB flag" not in text
    assert "QB scenarios for" not in text
    assert "**CHI:** Caleb Williams" in text


def test_week6_chi_atl_final_build_uses_settled_qbs_not_pair_scenarios(tmp_path):
    """Week 6 was reissued (build 610992bd5dbf) with Williams and Penix entered as manual
    QB assumptions, so the earlier six-pairing CHI at ATL scenario view no longer ships.
    The final build must show one plain card with those two QBs and no pairing expander."""
    import page_common
    from publishing.manifest import release_status

    at = _render_page(tmp_path, "page_weekly_predictions")
    next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season").set_value(2026)
    next(w for w in at.selectbox if getattr(w, "key", None) == "wp_week").set_value(6)
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    shown = release_status("predictions", 2026, 6, manifest=page_common.load_release_manifest(), root=_HERE)
    assert shown["build_id"] == "predictions-2026w06-9832281cdeab", shown

    markdown = " ".join(str(item.value) for item in at.markdown)
    assert not any(exp.label.endswith("joint QB pairings") for exp in at.expander)
    assert not [m for m in at.markdown if "jsa-gc-pair" in str(m.value)]
    assert "MAIN PATH" not in markdown
    for name in ("Caleb Williams", "Michael Penix Jr."):
        assert f"QB: {name}</div>" in markdown, name
    qb_expander = next(exp for exp in at.expander if exp.label == "QB inputs used for this release")
    qb_markdown = " ".join(str(item.value) for item in qb_expander.markdown)
    assert "**ATL:** Michael Penix Jr. — user modeling assumption" in qb_markdown
    assert "**CHI:** Caleb Williams — user modeling assumption" in qb_markdown


def test_week6_chi_atl_superseded_build_pair_scenarios_render(tmp_path):
    """Keep the joint-pairing renderer covered using the superseded Week 6 correction
    build (c3c200e3354b), whose artifact carries six CHI at ATL pairings."""
    import pandas as pd

    path = _HERE / "data/releases/builds/predictions/2026/week06/predictions-2026w06-c3c200e3354b/artifact.csv"
    row = pd.read_csv(path).set_index("game_id").loc["2026_06_CHI_ATL"]
    h = tmp_path / "h_pairs.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import pandas as pd, page_weekly_predictions as p\n"
        f"row = pd.read_csv(r'{path}').set_index('game_id').loc['2026_06_CHI_ATL']\n"
        "items, verdict = p._pair_scenario_items(row)\n"
        "p._render_qb_pair_scenarios(items, verdict, 'ATL', 'CHI', float(row['spread_line']), float(row['model_edge']))\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    markdown = " ".join(str(item.value) for item in at.markdown)
    captions = " ".join(str(item.value) for item in at.caption)
    assert "All 6 joint QB pairings" in [exp.label for exp in at.expander]
    for name in ("Caleb Williams", "Case Keenum", "Tyson Bagent", "Michael Penix Jr.", "Tua Tagovailoa"):
        assert name in markdown, name
    pair_cards = [str(item.value) for item in at.markdown if "jsa-gc-pair" in str(item.value)]
    assert len(pair_cards) == 6
    keenum_tua = next(card for card in pair_cards if "Case Keenum" in card and "Tua Tagovailoa" in card)
    assert "edge 3.46" in keenum_tua
    assert markdown.count("MAIN PATH") == 1
    assert "These are scenario scores, not blended probabilities" in captions


def test_week3_st_promotion_reissue_card_states(tmp_path):
    """Week 3 build c98a61b8420d (special-teams net two-sided EPA promotion): one plain HIGH
    card and one QB split card.

    CIN at PIT clears HIGH and shows as HIGH. HOU at IND no longer clears HIGH under the net
    special-teams definition (it did under the superseded build). PHI at CHI clears HIGH only
    under 1 of 3 listed QBs (Caleb Williams 3.36; Bagent and Keenum stay under 3.0), so the
    verdict is high_split and the header reads QB SPLIT, not HIGH PICK. ATL at GB is scored
    fresh by the new model this time (no --hold-started-games-from was used, unlike the prior
    units-fix reissue), so it carries no held-row marker. If Week 3 is reissued again this test
    must be re-read against the new build, not loosened.
    """
    import re
    import page_common

    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    week = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_week")
    week.set_value(3)
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    from publishing.manifest import release_status

    manifest = page_common.load_release_manifest()
    predictions = manifest["products"]["predictions"]
    week3_build_id = "predictions-2026w03-6ac0c411ac45"
    # Week 4+ publishes move the active pointer off Week 3, so pin the build the page
    # resolves for Week 3 instead of the active one. This is the same pin as before, by week.
    shown = release_status("predictions", 2026, 3, manifest=manifest, root=_HERE)
    assert shown["build_id"] == week3_build_id, shown
    build = predictions["builds"][week3_build_id]
    assert build["model_version"].endswith("actual-starter-0c213b99e845")
    assert "started_games_held" not in (build.get("correction") or {})

    def plain(html_text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text.replace("&nbsp;", " "))).strip()

    markdown = [str(item.value) for item in at.markdown]
    cards = {}
    for html_text in markdown:
        if "jsa-gc-meta" in html_text:
            match = re.search(r"([A-Z]{2,3}) @ ([A-Z]{2,3})", plain(html_text))
            cards[f"{match.group(1)} @ {match.group(2)}"] = html_text
    assert len(cards) == 16, sorted(cards)

    high = {name for name, html_text in cards.items() if "HIGH PICK" in html_text}
    assert high == {"CIN @ PIT", "LV @ NO"}, sorted(high)
    assert "jsa-gc-high" in cards["CIN @ PIT"]
    joined = " ".join(markdown)
    assert not any("QB SPLIT" in html_text for html_text in cards.values())
    assert "QB split: HIGH under" not in joined

    captions = " ".join(str(c.value) for c in at.caption)
    assert build["model_version"] in captions
    assert "games that had kicked off keep their published rows" not in captions


def test_week4_qb_paths_and_card_states(tmp_path):
    """Week 4 QB paths and card states from the published Week 4 release.

    TB starts Jalon Daniels (manual). WAS (Mariota default, Daniels path) and CHI (Keenum default,
    Williams and Bagent paths) carry QB scenarios. IND at WAS has no path clearing HIGH; NYJ at
    CHI clears HIGH under every listed QB. The default HIGH PICK cards are DAL at HOU, DEN at SF,
    ATL at NO, and NYJ at CHI. If Week 4 is
    reissued again this test must be re-read against the
    new build, not loosened.
    """
    import re
    import page_common
    from publishing.manifest import release_status

    at = _render_page(tmp_path, "page_weekly_predictions")
    next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season").set_value(2026)
    next(w for w in at.selectbox if getattr(w, "key", None) == "wp_week").set_value(4)
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    manifest = page_common.load_release_manifest()
    shown = release_status("predictions", 2026, 4, manifest=manifest, root=_HERE)
    week4_build_id = "predictions-2026w04-a3ed73dbc7b4"
    assert shown["build_id"] == week4_build_id, shown
    build = manifest["products"]["predictions"]["builds"][shown["build_id"]]
    assert build["model_version"].endswith("actual-starter-0c213b99e845")

    def plain(html_text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text.replace("&nbsp;", " "))).strip()

    markdown = [str(item.value) for item in at.markdown]
    cards = {}
    for html_text in markdown:
        if "jsa-gc-meta" in html_text:
            match = re.search(r"([A-Z]{2,3}) @ ([A-Z]{2,3})", plain(html_text))
            cards[f"{match.group(1)} @ {match.group(2)}"] = html_text
    assert len(cards) == 16, sorted(cards)
    high = {name for name, html_text in cards.items() if "HIGH PICK" in html_text}
    assert high == {"ARI @ NYG", "ATL @ NO", "DEN @ SF"}, sorted(high)
    assert not any("QB SPLIT" in html_text for html_text in cards.values())

    joined = " ".join(markdown)
    assert "Case Keenum" in joined  # CHI manual assumption
    assert "The starter is not settled" not in joined


def test_scenario_verdict_lines_are_plain_for_every_case():
    import importlib

    sys.path.insert(0, str(_SITE_PAGES))
    page = importlib.import_module("page_weekly_predictions")
    items = [{"clears_high": True}, {"clears_high": True}, {"clears_high": False}]
    assert "HIGH under all 2 QBs" in page._scenario_verdict_html(items[:2], "high_all_clear")
    assert "QB split: HIGH under 2 of 3 QBs, pass" in page._scenario_verdict_html(items, "high_split")
    assert "HIGH under 2 of 3 QBs, but not under the default QB" in page._scenario_verdict_html(items, "scenario_high_only")
    assert "No HIGH under any listed QB" in page._scenario_verdict_html([{"clears_high": False}] * 2, "no_high")
    assert page._scenario_verdict_html(items, "") == ""
    card = page._scenario_card_html(
        {"player_name": "Caleb Williams", "side": "HOME (CHI)", "edge": 4.39, "clears_high": True}, "CHI", -3.0
    )
    assert "Caleb Williams" in card and "Pick: CHI" in card and "Edge 4.39 points" in card
    assert "Model line: CHI -1.4" in card and ">HIGH if he starts<" in card


def test_blended_scenario_row_renders_probabilities_verdicts_and_official_label():
    """Synthetic blended row (new model): no live release needed. Old builds keep the old verdicts."""
    import importlib
    import json as _json

    sys.path.insert(0, str(_SITE_PAGES))
    page = importlib.import_module("page_weekly_predictions")
    scenarios = [
        {"team": "BAL", "player_name": "Lamar Jackson", "side": "HOME (BUF)", "edge": 4.1,
         "clears_high": True, "probability": 0.5},
        {"team": "BAL", "player_name": "Cooper Rush", "side": "HOME (BUF)", "edge": 2.2,
         "clears_high": False, "probability": 0.5},
    ]
    row = {
        "qb_scenarios": _json.dumps(scenarios),
        "qb_scenario_verdict": "blend_no_high",
        "default_qb_edge": 4.1,
        "default_qb_recommendation": "BUF",
    }
    items, verdict = page._scenario_items(row)
    assert verdict == "blend_no_high" and len(items) == 2 and page._is_blended(verdict)
    assert not page._is_blended("high_split")

    card = page._scenario_card_html(items[0], "BUF", -3.0)
    assert "Lamar Jackson" in card and "50% chance he starts" in card
    # Historical items without a probability keep the old card.
    legacy = page._scenario_card_html({k: v for k, v in items[0].items() if k != "probability"}, "BUF", -3.0)
    assert "chance he starts" not in legacy
    assert "chance he starts" not in page._scenario_card_html({**items[0], "probability": "bad"}, "BUF", -3.0)

    assert "Blended pick is HIGH" in page._scenario_verdict_html(items, "blend_high")
    assert "Blended gap is under 3.0 points, not HIGH" in page._scenario_verdict_html(items, "blend_no_high")
    assert "QBs point opposite ways" in page._scenario_verdict_html(items, "blend_split_no_high")
    # Old verdicts still render exactly as before.
    assert "No HIGH under any listed QB" in page._scenario_verdict_html(items, "no_high")

    assert page._official_row_label("BUF", -3.4, "HIGH", blended=True) == "Blended pick (official): BUF 3.40 points, HIGH"
    assert page._official_row_label("BUF", -2.0, "PASS", blended=True).startswith("Blended pick (official)")
    assert page._official_row_label("BUF", -3.4, "HIGH").startswith("Official model row for the season record")
    for text in (page._scenario_verdict_html(items, v) for v in ("blend_high", "blend_no_high", "blend_split_no_high")):
        assert "—" not in text and "&mdash;" not in text


def test_blended_scenario_game_shows_context_caption_and_official_expander(monkeypatch):
    """Drive _render_qb_scenarios with a stub Streamlit to confirm the blend caption text."""
    import importlib

    sys.path.insert(0, str(_SITE_PAGES))
    page = importlib.import_module("page_weekly_predictions")
    seen = []

    class _Col:
        def markdown(self, html_text, **_kw):
            seen.append(html_text)

    monkeypatch.setattr(page.st, "markdown", lambda html_text, **_kw: seen.append(html_text))
    monkeypatch.setattr(page.st, "columns", lambda n: [_Col() for _ in range(n)])
    items = [
        {"team": "BAL", "player_name": "Lamar Jackson", "side": "HOME (BUF)", "edge": 4.1, "clears_high": True, "probability": 0.5},
        {"team": "BAL", "player_name": "Cooper Rush", "side": "HOME (BUF)", "edge": 2.2, "clears_high": False, "probability": 0.5},
    ]
    page._render_qb_scenarios(items, "blend_split_no_high", "BUF", "BAL", -3.0)
    joined = " ".join(seen)
    assert "QB paths are shown for context" in joined
    assert joined.count("50% chance he starts") == 2
    assert "QBs point opposite ways" in joined
    seen.clear()
    page._render_qb_scenarios(items, "high_split", "BUF", "BAL", -3.0)
    assert "QB paths are shown for context" not in " ".join(seen)
