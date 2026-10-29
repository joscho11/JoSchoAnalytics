"""Offline regression coverage for retired Film Room bookmark compatibility."""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path[:0] = [str(_HERE), str(_SITE_PAGES)]

from video_content import VIDEOS


def _harness(tmp_path, source):
    path = tmp_path / "film_compatibility.py"
    path.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import streamlit as st\n"
        "import nav_registry\n"
        + source,
        encoding="utf-8",
    )
    at = AppTest.from_file(str(path), default_timeout=90).run()
    assert not at.exception, at.exception
    assert not at.error, [error.value for error in at.error]
    return at


@pytest.mark.parametrize("slug", [None, "unknown-episode", "league-history-guide", "site-walkthrough"])
def test_legacy_walkthrough_and_empty_links_switch_to_help(tmp_path, slug):
    at = _harness(
        tmp_path,
        "import film_room\n"
        "if not st.session_state.get('seeded'):\n"
        "    st.session_state['seeded'] = True\n"
        + (f"    st.query_params['video'] = {slug!r}\n" if slug else "")
        + "def help_render():\n"
        "    st.title('Help destination')\n"
        "    st.json(dict(st.query_params))\n"
        "help_page = st.Page(help_render, title='Help', url_path='help')\n"
        "film_page = st.Page(film_room.render_film_room, title='Archive', default=True)\n"
        "nav_registry.PAGES = {'help': help_page}\n"
        "st.navigation([film_page, help_page], position='hidden').run()\n",
    )
    assert [title.value for title in at.title] == ["Help destination"]
    expected = {"help_topic": "Site Guide"}
    if slug in {"league-history-guide", "site-walkthrough"}:
        expected["guide"] = slug
    assert json.loads(at.json[0].value) == expected
    assert not at.get("iframe")


@pytest.mark.parametrize("slug", ["makai-lemon", "week-5-model-gaps-2026", "graphs-of-the-week-02"])
def test_analysis_bookmark_preserves_only_selected_context(tmp_path, slug):
    item = next(episode for episode in VIDEOS if episode["slug"] == slug)
    at = _harness(
        tmp_path,
        f"st.query_params['video'] = {slug!r}\n"
        "import film_room\n"
        "film_room.render_film_room()\n",
    )
    assert [title.value for title in at.title] == [item["title"]]
    captions = " ".join(str(caption.value) for caption in at.caption)
    assert "Published" in captions and "publication date" in captions
    assert "may have changed" in captions
    links = list(at.get("link_button"))
    assert len(links) == 1 and links[0].url == item["tiktok_url"]
    assert not at.get("iframe")
    assert not at.selectbox and not at.segmented_control
    assert len(at.expander) == 1
    assert at.expander[0].label == "Archived written breakdown"
    assert not at.expander[0].proto.expanded
    expected = (_HERE / "video_breakdowns" / item["breakdown_file"]).read_text(encoding="utf-8")
    assert expected.strip() in [markdown.value for markdown in at.markdown]


def test_registry_preserves_unique_bookmarks_and_breakdown_files():
    slugs = [item["slug"] for item in VIDEOS]
    assert len(slugs) == len(set(slugs))
    assert {"league-history-guide", "site-walkthrough"} <= set(slugs)
    for item in VIDEOS:
        assert item["video_id"] in item["tiktok_url"]
        if item.get("breakdown_file"):
            assert (_HERE / "video_breakdowns" / item["breakdown_file"]).is_file()
