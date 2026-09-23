"""Batch-3d proof for the extracted Help & Guide page. Renders offline-clean, and the
live model stats its prose interpolates come from dashboard_data.accuracy_stats (3a) —
so the rendered copy is byte-identical to what app.py's Help tab shows. Hermetic.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))


def _render(tmp_path, *, topic=None, search=None, fail_tracker=False, open_question=None):
    h = tmp_path / "h_help.py"
    setup = (
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\n"
    )
    if topic:
        setup += f"st.query_params['help_topic'] = {topic!r}\n"
    if search:
        setup += f"st.session_state['help_search'] = {search!r}\n"
    if fail_tracker:
        setup += (
            "import dashboard_data\n"
            "dashboard_data.load_predictions = lambda: (_ for _ in ()).throw(FileNotFoundError())\n"
        )
    h.write_text(setup + "import page_help as p\np.render()\n", encoding="utf-8")
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    if open_question:
        expander = next(e for e in at.expander if open_question in str(e.label))
        expander.proto.expanded = True
        at.run()
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]
    return at


def test_help_renders_offline_clean(tmp_path):
    at = _render(tmp_path)
    assert any("Help & guide" in str(t.value) for t in at.title), "Help title missing"
    assert len(list(at.markdown)) > 10, "Help body (expanders/markdown) did not render"
    assert any("Site Guide" in str(s.value) for s in at.subheader)
    assert any("Search Help & Guide" == str(w.label) for w in at.text_input)
    assert not any("Start here" in str(s.value) for s in at.subheader)
    assert not any("Start here" in str(c.value) for c in at.caption)
    assert any("Which page should I use?" in str(e.label) for e in at.expander)
    assert not any("How do the product-specific models work?" in str(e.label) for e in at.expander)


def test_help_league_history_covers_yahoo(tmp_path):
    at = _render(tmp_path, open_question="How does League History work?")
    md = " ".join(str(m.value) for m in at.markdown)
    all_copy = md + " " + " ".join(str(c.value) for c in at.caption)
    assert "Choose Sleeper, ESPN, Yahoo, or CBS" in md
    assert "Y and T cookie" in md
    assert "number after `/f1/`" in md
    assert "CBS IDs are the subdomain" in md
    source = (_HERE / "site_pages" / "help_content.py").read_text(encoding="utf-8")
    assert "CBS leagues always need the signed-in access" in source
    assert "token" in source
    assert "Yahoo ADP" in md
    assert "Yahoo does not price every one of the 180 players" in all_copy
    assert "empty" in source and "scored" in source and "weeks" in source
    assert "Yahoo and CBS are on the live page and are not in that video" in source


def test_league_history_help_deep_links_to_current_walkthrough(tmp_path):
    harness = tmp_path / "h_help_navigation.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\n"
        "import nav_registry\n"
        "import page_help\n"
        "film = st.Page(lambda: st.write('Film Room'), title='Film Room', "
        "url_path='film-room')\n"
        "help_page = st.Page(page_help.render, title='Help & Guide', "
        "url_path='help', default=True)\n"
        "nav_registry.PAGES = {'film-room': film}\n"
        "st.navigation([help_page, film], position='hidden').run()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    links = [
        link
        for link in at.get("page_link")
        if link.label == "Watch the League History walkthrough"
    ]
    assert len(links) == 1
    assert links[0].query_string == "video=league-history-guide"


def test_help_site_org_and_paused_copy(tmp_path):
    at = _render(tmp_path)
    md = " ".join(str(m.value) for m in at.markdown)
    assert "Season Totals" in md
    assert "Season Totals (Beta)" not in md
    assert "Draft Board" in md
    assert "opens on **Home**" in md
    assert any("Which page should I use?" in str(e.label) for e in at.expander)
    assert not any("Season Totals (Beta)" in str(e.label) for e in at.expander)
    assert "DFS Optimizer" in md
    assert "currently uses mock data" not in md
    assert "roadmap for the 2026 season" not in md
    assert "same automated pipeline that runs the betting predictions" not in md


def test_help_states_live_high_wilson_claim(tmp_path):
    at = _render(tmp_path, topic="Betting", open_question="What win rate is needed")
    md = " ".join(str(m.value) for m in at.markdown)
    assert "246/423" in md
    assert "58.16%" in md
    assert "54.17%" in md
    assert "11 pushes among 434 HIGH labels" in md
    assert "44 core features and 47 fitted inputs" in md
    assert "non-QB" in md and "regular injured reserve" in md
    assert "223/390" not in md
    assert "the Sunday 11:20 p.m. ET and Tuesday snapshots" in md
    assert "above 52.4%" in md
    assert "best US Tuesday" in md
    assert "192/336" not in md
    assert "57.14%" not in md
    assert "201/349" not in md


def test_help_does_not_disclose_sleeper_mix(tmp_path):
    at = _render(tmp_path)
    blob = " ".join(
        [str(m.value) for m in at.markdown]
        + [str(c.value) for c in at.caption]
    )
    for phrase in ("25% Sleeper", "75/25", "mixed in at 25%",
                   "75% independent v6 plus 25%", "no Sleeper mix"):
        assert phrase not in blob, f"Sleeper mix leaked onto Help: {phrase}"


def test_help_interpolates_shared_stats_byte_identical(tmp_path):
    import dashboard_data
    df = dashboard_data.load_predictions()
    demo = df[df["season"] == 2025] if "season" in df.columns else df
    s = dashboard_data.accuracy_stats(demo if not demo.empty else df)
    at = _render(tmp_path, topic="Betting", open_question="What win rate is needed")
    md = " ".join(str(m.value) for m in at.markdown)
    assert f"{s['overall_pct']}% ATS" in md, \
        "2025 demo ATS% (from accuracy_stats) must appear verbatim in the Help copy"
    assert "2025 demo" in md.lower()
    assert "currently at" not in md.lower()
    assert "When an approved agent artifact" not in md
    if s["hc_pct"] is not None:
        assert f"{s['hc_pct']}%" in md, "high-confidence % must appear verbatim in the Help copy"


def test_help_covers_live_model_rundowns(tmp_path):
    at = _render(tmp_path, topic="Models & Data")
    labels = [str(e.label) for e in at.expander]
    for needed in (
        "How does a published model become a page?",
        "How should I read the evaluation metrics?",
        "What data does the site use, and what are the limits?",
        "How do the product-specific models work?",
        "How the 2026 spread model works",
        "How weekly fantasy projections are built",
    ):
        assert any(needed in lab for lab in labels), f"missing rundown: {needed}"
    assert not any("How does the 2026 Tuesday model work?" in lab for lab in labels)
    assert not any("How does the prediction model work?" in lab for lab in labels)
    assert not any("How accurate is the model?" in lab for lab in labels)
    md = " ".join(str(m.value) for m in at.markdown)
    assert "mean absolute Tree SHAP" in md or "XGBoost gain" in md
    assert "absolute ridge coefficient" in md
    assert "4.999" in md
    assert "0.395" in md
    assert "prior season" in md
    assert "not an input" in md
    assert "not a claim it beats Sleeper" in md


def test_help_topics_and_search_cover_all_sections(tmp_path):
    at = _render(tmp_path)
    selector = next(w for w in at.segmented_control if w.key == "help_topic")
    assert selector.options == ["Site Guide", "Football", "Fantasy", "Betting", "Models & Data"]

    at = _render(tmp_path, search="half-PPR")
    assert any("Fantasy" == str(s.value) for s in at.subheader)
    assert any("What is half-PPR scoring?" in str(e.label) for e in at.expander)
    assert not any("What is EPA?" in str(e.label) for e in at.expander)


def test_help_search_empty_state(tmp_path):
    at = _render(tmp_path, search="not-a-real-help-term")
    assert any("No matching answers" in str(i.value) for i in at.info)


def test_help_static_content_survives_missing_tracker(tmp_path):
    at = _render(tmp_path, topic="Site Guide", fail_tracker=True)
    assert not at.exception, at.exception
    assert any("Which page should I use?" in str(e.label) for e in at.expander)

    at = _render(tmp_path, topic="Betting", fail_tracker=True)
    assert not at.exception, at.exception
    assert any("tracker statistics are unavailable" in str(i.value) for i in at.info)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_help_renders_offline_clean(Path(d))
        test_help_site_org_and_paused_copy(Path(d))
        test_help_does_not_disclose_sleeper_mix(Path(d))
        test_help_interpolates_shared_stats_byte_identical(Path(d))
        test_help_covers_live_model_rundowns(Path(d))
    print("OK  Help page renders clean; shared stats interpolate byte-identical")
