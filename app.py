"""Live entrypoint — the multipage site (st.navigation, top nav).

The 8-tab monolith was migrated to page modules across site-revamp Batch 3 and swapped
in here (3e). This thin entrypoint wires the ratified nav groups/labels/icons/url_paths,
the fixed default landing page (Weekly Predictions, always — Joseph's ruling 2026-07-14
retired the seasonal Draft-Board-pre-season default), the cross-link registry, and the
shared footer; there is no sidebar. Page modules are imported only when selected so a
request does not initialize every page's dependencies. Shared data/chrome come from
dashboard_data / dashboard_chrome / page_common.
"""
import importlib
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "site_pages"))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))

import dashboard_chrome as chrome
import theme_redesign  # redesign preview skin (revertible) — delete this import + the call below to revert
import nav_registry


def _lazy_render(module_name: str):
    """Return a page callable that imports its implementation only when selected."""
    def render():
        importlib.import_module(module_name).render()

    render.__name__ = f"render_{module_name}"
    return render

st.set_page_config(page_title="JoScho Analytics | NFL Predictions",
                   page_icon="🏈", layout="wide")
chrome.inject_css()
theme_redesign.inject()  # redesign preview skin (revertible) — remove this line to restore the stock look
chrome.site_pageview_once()

# ── Pages — all real now (stubs retired in Batch 3d); url_paths per design 4b ──
board_pg = st.Page(_lazy_render("page_draft_board"), title="Draft Board", icon="📋",
                   url_path="draft-board")
wp_pg = st.Page(_lazy_render("page_weekly_predictions"), title="Weekly Predictions", icon="🏈",
                url_path="weekly-predictions", default=True)
wf_pg = st.Page(_lazy_render("page_weekly_fantasy"), title="Weekly Fantasy", icon="🏆",
                url_path="weekly-fantasy")
dfs_pg = st.Page(_lazy_render("page_dfs"), title="DFS Optimizer", icon="🎯",
                 url_path="dfs-optimizer")
tr_pg = st.Page(_lazy_render("page_track_record"), title="Track Record", icon="📈",
                url_path="track-record")
film_pg = st.Page(_lazy_render("page_film_room"), title="Film Room", icon="📺",
                  url_path="film-room")
lh_pg = st.Page(_lazy_render("page_league_history"), title="League History", icon="🏅",
                url_path="league-history")
help_pg = st.Page(_lazy_render("page_help"), title="Help & Guide", icon="❓",
                  url_path="help")
rb_pg = st.Page(_lazy_render("page_rookie_board"), title="Rookie Board", icon="🧬",
                url_path="rookie-board")

# cross-link registry (design 4g) — populated before nav.run() so pages can link
nav_registry.PAGES = {
    "draft-board": board_pg, "weekly-predictions": wp_pg, "weekly-fantasy": wf_pg,
    "dfs-optimizer": dfs_pg, "track-record": tr_pg, "film-room": film_pg,
    "league-history": lh_pg, "help": help_pg, "rookie-board": rb_pg,
}

# Persistent branded header ABOVE the top nav — rendered before st.navigation so the
# brand + tip jar strip sits on top of the page links, on every page.
chrome.render_header()

nav = st.navigation(
    {"Betting": [wp_pg, tr_pg],
     "Fantasy": [board_pg, rb_pg, wf_pg, dfs_pg],
     "More": [film_pg, lh_pg, help_pg]},
    position="top",
)
nav.run()
chrome.render_footer()
