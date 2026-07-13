"""Live entrypoint — the multipage site (st.navigation, top nav).

The 8-tab monolith was migrated to page modules across site-revamp Batch 3 and swapped
in here (3e). This thin entrypoint wires the ratified nav groups/labels/icons/url_paths,
the SEASON_START-reused seasonal default (Draft Board pre-season, Weekly Predictions
on/after), the cross-link registry, and the shared footer; there is no sidebar. Each
page is its own module (page_*.py / draft_board_2026.py / film_room via page_film_room);
shared data/chrome come from dashboard_data / dashboard_chrome / page_common.
"""
import os
import sys
from datetime import date
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))

import dashboard_chrome as chrome
import nav_registry
import page_dfs
import page_film_room
import page_draft_board
import page_help
import page_league_history
import page_track_record
import page_weekly_fantasy
import page_weekly_predictions
from refresh_board_adp import SEASON_START   # single source of truth (design 4c)

st.set_page_config(page_title="JoScho Analytics | NFL Predictions",
                   page_icon="🏈", layout="wide")
chrome.inject_css()
chrome.site_pageview_once()

# ── Seasonal default: Draft Board pre-season, Weekly Predictions on/after ──
_ss = date.fromisoformat(
    os.environ.get("BOARD_REFRESH_SEASON_START", SEASON_START.isoformat()))
_preseason = date.today() < _ss


# ── Pages — all real now (stubs retired in Batch 3d); url_paths per design 4b ──
board_pg = st.Page(page_draft_board.render, title="Draft Board", icon="📋",
                   url_path="draft-board", default=_preseason)
wp_pg = st.Page(page_weekly_predictions.render, title="Weekly Predictions", icon="🏈",
                url_path="weekly-predictions", default=not _preseason)
wf_pg = st.Page(page_weekly_fantasy.render, title="Weekly Fantasy", icon="🏆", url_path="weekly-fantasy")
dfs_pg = st.Page(page_dfs.render, title="DFS Optimizer", icon="🎯", url_path="dfs-optimizer")
tr_pg = st.Page(page_track_record.render, title="Track Record", icon="📈", url_path="track-record")
film_pg = st.Page(page_film_room.render, title="Film Room", icon="📺",
                  url_path="film-room")
lh_pg = st.Page(page_league_history.render, title="League History", icon="🏅", url_path="league-history")
help_pg = st.Page(page_help.render, title="Help & Guide", icon="❓", url_path="help")

# cross-link registry (design 4g) — populated before nav.run() so pages can link
nav_registry.PAGES = {
    "draft-board": board_pg, "weekly-predictions": wp_pg, "weekly-fantasy": wf_pg,
    "dfs-optimizer": dfs_pg, "track-record": tr_pg, "film-room": film_pg,
    "league-history": lh_pg, "help": help_pg,
}

nav = st.navigation(
    {"Fantasy": [board_pg, wf_pg, dfs_pg],
     "Betting": [wp_pg, tr_pg],
     "More": [film_pg, lh_pg, help_pg]},
    position="top",
)
nav.run()
chrome.render_footer()
