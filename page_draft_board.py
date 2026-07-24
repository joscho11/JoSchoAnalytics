"""Draft Board page for the multipage site (site revamp Batch 2).

The flagship page: site orientation + page-purpose (ratified 4d copy), the pre-season
banner (4d.ii), then the board itself rendered via draft_board_2026.render() — the
season-projection comparison table (2026-07-22 rebuild): every player with a 2026 Sleeper
ADP, the market's draft price and positional rank beside Sleeper's and my model's
projections with the rank gap for each, sorted via the control. All board copy/logic lives
in draft_board_2026; this module adds only the ratified flagship strings.
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
PURPOSE = ("My pre-season draft board: the market's draft price and positional rank for each "
           "player, beside two independent season-total projections — Sleeper's and my own "
           "model's — with the rank gap for each. Refreshed daily from live draft data.")


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
