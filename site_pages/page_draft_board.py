"""Draft Board page for the multipage site (site revamp Batch 2).

The flagship page: site orientation + page-purpose, the pre-season banner, then the board
itself rendered via draft_board_2026.render(). The board is the exact 180-player independent
v6 publication universe, with live Sleeper, ESPN, and Yahoo ADP and frozen Model Proj. All board
copy/logic lives in draft_board_2026; this module adds only the flagship strings.
"""
import streamlit as st

import dashboard_chrome as chrome
import draft_board_2026 as board
from seasonal_config import app_today, board_refresh_season_start

# Ratified 4d copy (verbatim).
ORIENTATION = ("I build machine-learning models for NFL betting and fantasy, run them "
               "live, and show my work — the numbers, the honest track record, and the "
               "code on my GitHub.")
PURPOSE = ("My pre-season draft board: the independent model's exact 180-player 2026 "
           "projection universe. Sleeper ADP (default), ESPN ADP, Yahoo ADP, or Model "
           "Draft Rank, Sleeper projections, "
           "and both rank gaps refresh through kickoff, then show the latest pre-kickoff "
           "snapshot; Model Proj points and ranks stay frozen by design.")


def render():
    # Lead with the title, then the byline + purpose, then (pre-season) the notice.
    st.title("2026 draft board")
    st.caption(ORIENTATION)
    st.markdown(f"**{PURPOSE}**")
    _ss = board_refresh_season_start()
    if app_today() < _ss:
        # No page_link here — this IS the Draft Board page, so the link would be circular.
        chrome.render_preseason_banner(None, _ss.year)
    else:
        _freeze_date = f"{_ss:%B} {_ss.day}, {_ss.year}"
        st.info(
            f"ADP refreshes are paused after {_freeze_date}. Sleeper, ESPN, and Yahoo ADP "
            "show the latest available pre-kickoff market snapshot; the 2026 Model Proj "
            "and its ranks remain frozen by design."
        )
    board.render()
