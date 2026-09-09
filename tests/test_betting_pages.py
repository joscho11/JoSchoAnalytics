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
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["wp_season"] == 2026
    assert controls["wp_week"] == 1
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "green-badge" in markdown and "Published" in markdown
    assert "Published" in markdown
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


def test_track_record_renders_and_owns_controls(tmp_path):
    at = _render_page(tmp_path, "page_track_record")
    keys = _control_keys(at)
    assert "tr_season" in keys, f"Track Record must own its Season control; got {keys}"
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "tr_season")
    assert season.value == 2025
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
    assert "No totals on this season" in " ".join(str(s.value) for s in at.success)
    assert "jsa-tot-badge" not in md
    assert "NE @ SEA" in md
    assert "Published" in md
    captions = " ".join(str(c.value) for c in at.caption)
    # The best-available quote renders as white markdown, not a muted caption.
    assert "Best available for <b style='color:#fff'>TB</b>" in md
    assert "+4.0" in md and "(-109)" in md and "BetRivers" in md
    metrics = {str(m.label): str(m.value) for m in at.metric}
    # WAS clears 2.5 against the shopped line (2.61). All 2026 public decisions
    # use that quote, so it is the fifth HIGH card.
    assert metrics["HIGH picks"] == "5"


def test_weekly_predictions_live_2026_banner(tmp_path):
    at = _render_page(tmp_path, "page_weekly_predictions")
    season = next(w for w in at.selectbox if getattr(w, "key", None) == "wp_season")
    season.set_value(2026)
    at.run()
    assert not at.exception, at.exception
    successes = " ".join(str(s.value) for s in at.success)
    assert "Live 2026" in successes
    assert "one-sided 95% Wilson" in successes
    assert "302/535" in successes
    assert "56.45%" in successes
    assert "52.90%" in successes
    assert "above 52.4%" in successes
    assert "best US Tuesday" in successes
    assert "57.14%" not in successes
    assert "192/336" not in successes
    assert "No medium tier" in successes
    assert "No totals on this season" in successes
    headings = " ".join(str(t.value) for t in [*at.title, *at.subheader])
    assert "2026" in headings
    assert "Week 1" in headings
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
