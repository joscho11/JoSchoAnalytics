"""Batch-3d proof for the extracted Help & Guide page. Renders offline-clean, and the
live model stats its prose interpolates come from dashboard_data.accuracy_stats (3a) —
so the rendered copy is byte-identical to what app.py's Help tab shows. Hermetic.
"""
import os
import sys
from unittest.mock import patch
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))


def _render(tmp_path, *, topic=None, search=None, guide=None, fail_tracker=False, open_question=None):
    h = tmp_path / "h_help.py"
    setup = (
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\n"
    )
    if topic:
        setup += f"st.query_params['help_topic'] = {topic!r}\n"
    if guide:
        setup += f"st.query_params['guide'] = {guide!r}\n"
    if search:
        setup += f"st.session_state['help_search'] = {search!r}\n"
    h.write_text(setup + "import page_help as p\np.render()\n", encoding="utf-8")
    if fail_tracker:
        import dashboard_data

        with patch.object(dashboard_data, "load_predictions", side_effect=FileNotFoundError):
            at = AppTest.from_file(str(h), default_timeout=180).run()
    else:
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
    assert len(list(at.markdown)) >= 10, "Help body (expanders/markdown) did not render"
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
    assert "Yahoo IDs are the number after `/f1/` and also need" in md
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
        "nav_registry.PAGES = {'help': help_page}\n"
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
    from urllib.parse import parse_qs
    assert parse_qs(links[0].query_string) == {"help_topic": ["Site Guide"], "guide": ["league-history-guide"]}


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
    assert "251/437" in md
    assert "57.44%" in md
    assert "53.51%" in md
    assert "9 pushes among 446 HIGH labels" in md
    assert "moved from the previous model's 261/449" in md
    assert "not statistically established either way" in md
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


def test_league_history_context_links_to_selected_guide(tmp_path):
    from urllib.parse import parse_qs
    harness = tmp_path / "h_league_guide_link.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\nimport nav_registry\nimport page_league_history\n"
        "help_page = st.Page(lambda: None, title='Help & Guide', url_path='help')\n"
        "league = st.Page(page_league_history.render, title='League History', default=True)\n"
        "nav_registry.PAGES = {'help': help_page}\n"
        "st.navigation([league, help_page], position='hidden').run()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception
    links = [link for link in at.get("page_link") if link.label == "Watch the League History guide"]
    assert len(links) == 1
    assert parse_qs(links[0].query_string) == {"help_topic": ["Site Guide"], "guide": ["league-history-guide"]}



def test_guides_are_opt_in_and_switch_one_player(tmp_path):
    at = _render(tmp_path)
    assert not at.get("iframe")
    at = next(b for b in at.button if b.label == "Watch site tour").click().run()
    frames = at.get("iframe")
    assert len(frames) == 1
    assert frames[0].proto.src == "https://www.tiktok.com/player/v1/7676601401342037279?autoplay=0"
    at = next(b for b in at.button if b.label == "Watch League History guide").click().run()
    frames = at.get("iframe")
    assert len(frames) == 1
    assert "7676271983297940766?autoplay=0" in frames[0].proto.src
    assert not at.exception
    links = [link for link in at.get("link_button") if link.label == "Open walkthrough on TikTok"]
    assert len(links) == 1 and links[0].url.endswith("7676271983297940766")


def test_guide_deep_links_override_stale_search_and_topic(tmp_path):
    for slug, video_id in (("site-walkthrough", "7676601401342037279"),
                           ("league-history-guide", "7676271983297940766")):
        at = _render(tmp_path, topic="Football", search="half-PPR", guide=slug)
        assert at.session_state["help_topic"] == "Site Guide"
        assert at.session_state["help_search"] == ""
        assert len(at.get("iframe")) == 1
        assert video_id in at.get("iframe")[0].proto.src
        assert any("Current written guide" == str(e.label) for e in at.expander)


def test_removing_guide_query_unmounts_player(tmp_path):
    at = _render(tmp_path)
    at.query_params["guide"] = "site-walkthrough"
    at.run()
    assert len(at.get("iframe")) == 1
    del at.query_params["guide"]
    at.run()
    assert not at.get("iframe")
    assert not at.exception



def test_invalid_guide_cannot_mount_arbitrary_player(tmp_path):
    at = _render(tmp_path, guide="../../unknown")
    assert not at.get("iframe")
    assert "guide" not in at.query_params



if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_help_renders_offline_clean(Path(d))
        test_help_site_org_and_paused_copy(Path(d))
        test_help_does_not_disclose_sleeper_mix(Path(d))
        test_help_interpolates_shared_stats_byte_identical(Path(d))
        test_help_covers_live_model_rundowns(Path(d))
    print("OK  Help page renders clean; shared stats interpolate byte-identical")
