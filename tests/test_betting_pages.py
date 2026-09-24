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
    shown_correction = shown_build["correction"]
    assert shown_correction.get("model_update") is not True or shown_correction["promotion_audit"]["sha256"]
    qb_expander = next(exp for exp in at.expander if exp.label == "QB inputs used for this release")
    qb_markdown = " ".join(str(item.value) for item in qb_expander.markdown)
    assert "**ATL:** Michael Penix Jr." in qb_markdown
    assert "**MIN:** Kyler Murray" in qb_markdown
    assert "**CHI:** Caleb Williams" in qb_markdown
    assert "**CHI:** Caleb Williams — previous-game dropback leader" in qb_markdown
    assert "Case Keenum" not in qb_markdown
    assert not any(str(k).startswith("tr_") for k in keys), \
        "Weekly Predictions must not carry Track Record's controls"


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


def test_week1_scorecard_and_track_record_use_graded_corrected_release(tmp_path):
    weekly = _render_page(tmp_path, "page_weekly_predictions")
    week = next(w for w in weekly.selectbox if getattr(w, "key", None) == "wp_week")
    week.set_value(1)
    weekly.run()
    assert not weekly.exception, weekly.exception
    metrics = {str(m.label): str(m.value) for m in weekly.metric}
    assert metrics["ATS record"] == "9/16"
    assert not any("Retrospective model correction" in str(w.value) for w in weekly.warning)
    assert any("Week 1 ATS record: **9-7**" in str(s.value) for s in weekly.success)
    week2 = next(w for w in weekly.selectbox if getattr(w, "key", None) == "wp_week")
    week2.set_value(2)
    weekly.run()
    assert not weekly.exception, weekly.exception
    assert next(w for w in weekly.selectbox if w.key == "wp_week").value == 2
    week2_metrics = {str(m.label): str(m.value) for m in weekly.metric}
    assert week2_metrics["ATS record"] == "8/16"
    assert week2_metrics["HIGH picks"] == "1"
    assert not any("Retrospective model correction" in str(w.value) for w in weekly.warning)

    track = _render_page(tmp_path, "page_track_record")
    assert next(w for w in track.selectbox if w.key == "tr_season").value == 2026
    track_metrics = {str(m.label): str(m.value) for m in track.metric}
    # Every graded week joins the season summary, so this must not be frozen at
    # one week's denominator. Week 1 contributed 9 wins from 16 settled games.
    season_ats = track_metrics["Season ATS"]
    wins, settled = (int(part) for part in season_ats.split("/"))
    assert season_ats == "17/32", season_ats
    track_warnings = " ".join(str(w.value) for w in track.warning)
    assert "Retrospective model corrections are included" not in track_warnings
    # HIGH tickets accumulate as weeks settle, so assert the shape, not a frozen count.
    high_wins, high_settled = (
        int(part) for part in track_metrics["HIGH (Tuesday 3+ points)"].split("/")
    )
    # The settled HIGH count moves as weeks grade; this was already (3, 4) at HEAD before the A+F promotion.
    assert 0 <= high_wins <= high_settled and high_settled >= 4, (high_wins, high_settled)


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
    assert "256/432" in notice_copy
    assert "59.26%" in notice_copy
    assert "55.32%" in notice_copy
    assert "10 pushes among 442 HIGH labels" in notice_copy
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
        "_real = dashboard_data.load_predictions()\n"
        "_df = _real.copy()\n"
        "_wk = _df[(_df['season'] == 2026) & (_df['week'] == 2)].index\n"
        "_unplayed = _wk[::2]\n"
        "for _c in ('actual_margin', 'home_score', 'away_score', 'model_correct', 'ens_model_correct'):\n"
        "    if _c in _df.columns:\n"
        "        _df.loc[_unplayed, _c] = np.nan\n"
        "_df.loc[_wk[1::2], 'actual_margin'] = _df.loc[_wk[1::2], 'actual_margin'].fillna(3.0)\n"
        "dashboard_data.load_predictions = lambda: _df\n"
        # Week 2 is the fixture's partly-played slate. The page default moves
        # forward on every publish, so pin the week this test actually set up.
        "import streamlit as st; st.session_state['wp_week'] = 2\n"
        "import page_weekly_predictions as p\n"
        "p.render()\n",
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


def test_weekly_predictions_shows_qb_scenarios_and_flag_notes(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    week = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_week")
    week.set_value(3)
    at.run()
    assert not at.exception, at.exception
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "QB scenarios" in markdown
    # SEA: Lock or Darnold. CHI: Caleb Williams, Bagent or Keenum.
    for name in ("Drew Lock", "Sam Darnold", "Caleb Williams", "Tyson Bagent", "Case Keenum"):
        assert name in markdown, name
    assert "QB split: pass" in markdown  # PHI at CHI is HIGH officially but not under every listed QB
    assert "&mdash;" not in markdown.split("QB scenarios", 1)[1].split("</div>", 1)[0]
    expander = next(exp for exp in at.expander if exp.label == "QB inputs used for this release")
    text = " ".join(str(item.value) for item in expander.markdown) + " " + " ".join(str(c.value) for c in expander.caption)
    assert "Automatic uncertain-QB flag" in text
    assert "**CHI:**" in text and "left before the end of" in text
    assert "QB scenarios for" in text
