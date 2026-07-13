"""Multipage entrypoint (site revamp — Batch 1 scaffolding).

NOT the live entrypoint yet: the tab-based app.py stays live and tested until the
final batch does the swap. This file proves the nav skeleton — st.navigation (top),
the ratified groups/labels/icons/url_paths, the SEASON_START-reused seasonal default,
the retired sidebar (empty), and the shared footer. Draft Board and Film Room are
already modular and wire in for real; the other six pages are TEMPORARY stubs (their
ratified one-line header + a rebuild note) replaced batch by batch.
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
import film_room
import nav_registry
import page_dfs
import page_draft_board
from refresh_board_adp import SEASON_START   # single source of truth (design 4c)

st.set_page_config(page_title="JoScho Analytics | NFL Predictions",
                   page_icon="🏈", layout="wide")
chrome.inject_css()
chrome.site_pageview_once()

# ── Seasonal default: Draft Board pre-season, Weekly Predictions on/after ──
_ss = date.fromisoformat(
    os.environ.get("BOARD_REFRESH_SEASON_START", SEASON_START.isoformat()))
_preseason = date.today() < _ss


# ── Temporary stub pages (ratified 4d one-liner + neutral rebuild note) ──
def _stub(title, icon, line):
    def _page():
        st.title(f"{icon} {title}")
        st.caption(line)
        st.info("This section is being rebuilt.")
    _page.__name__ = "stub_" + title.replace(" ", "_").replace("&", "and").lower()
    return _page


_wp = _stub("Weekly Predictions", "🏈",
            "My model's call against the Vegas spread for every game this week, with "
            "an honest confidence tier and the reasoning behind each one. "
            "Break-even is 52.4%.")
_tr = _stub("Track Record", "📈",
            "Every graded pick, by confidence tier and week — wins, losses, and profit "
            "at standard odds. Nothing hidden.")
_wf = _stub("Weekly Fantasy", "🏆",
            "My weekly half-PPR projections for every skill player — with the actual "
            "results filled in once games are played.")
_lh = _stub("League History", "🏅",
            "Load any Sleeper league to see its standings and season-by-season records.")
_help = _stub("Help & Guide", "❓",
              "What each part of the site is, how the models work, and how to read the "
              "numbers.")

# ── Pages (Draft Board + Film Room wired real; url_paths per design 4b) ──
board_pg = st.Page(page_draft_board.render, title="Draft Board", icon="📋",
                   url_path="draft-board", default=_preseason)
wp_pg = st.Page(_wp, title="Weekly Predictions", icon="🏈",
                url_path="weekly-predictions", default=not _preseason)
wf_pg = st.Page(_wf, title="Weekly Fantasy", icon="🏆", url_path="weekly-fantasy")
dfs_pg = st.Page(page_dfs.render, title="DFS Optimizer", icon="🎯", url_path="dfs-optimizer")
tr_pg = st.Page(_tr, title="Track Record", icon="📈", url_path="track-record")
film_pg = st.Page(film_room.render_film_room, title="Film Room", icon="📺",
                  url_path="film-room")
lh_pg = st.Page(_lh, title="League History", icon="🏅", url_path="league-history")
help_pg = st.Page(_help, title="Help & Guide", icon="❓", url_path="help")

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
