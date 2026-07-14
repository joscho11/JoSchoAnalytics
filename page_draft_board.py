"""Draft Board page for the multipage site (site revamp Batch 2).

The flagship page: site orientation + page-purpose (ratified 4d copy), the pre-season
banner (4d.ii), then the board itself rendered via draft_board_2026.render(use_table=True)
— the st.table view with the sort control as the only sort, the column tooltips relocated
into the visible guide, and the Top-40 default. All board copy/logic lives in
draft_board_2026 (single source, byte-identical); this module adds only the ratified
flagship strings.
"""
import os
from datetime import date

import streamlit as st

import dashboard_chrome as chrome
import draft_board_2026 as board
from refresh_board_adp import SEASON_START

# Ratified 4d copy (verbatim).
ORIENTATION = ("I build machine-learning models for NFL betting and fantasy, run them "
               "live, and show my work — the numbers, the honest track record, and the "
               "code on my GitHub.")
PURPOSE = ("My pre-season draft board: the market's price for each player paired with a "
           "calibrated range I built around it — refreshed daily from live draft data.")


def render():
    # Lead with the title, then the byline + purpose, then (pre-season) the notice.
    st.title("📋 2026 Draft Board")
    st.caption(ORIENTATION)
    st.markdown(f"**{PURPOSE}**")
    _ss = date.fromisoformat(
        os.environ.get("BOARD_REFRESH_SEASON_START", SEASON_START.isoformat()))
    if date.today() < _ss:
        # No page_link here — this IS the Draft Board page, so the link would be circular.
        chrome.render_preseason_banner(None, _ss.year)
    board.render()
