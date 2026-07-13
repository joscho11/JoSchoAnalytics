"""Film Room page wrapper (site revamp Batch 3e). Carries the ratified 4d Film Room
header, then renders film_room.render_film_room() byte-identical (its own header/caption
and cards, plus the archived-card → Draft Board cross-link that can only render in the
nav context). The 4d header is the only new copy.
"""
import streamlit as st

import film_room

# Ratified 4d.iii Film Room header (verbatim).
HEADER = "Short model-backed breakdowns, each with the full written analysis behind it."


def render():
    st.caption(HEADER)
    film_room.render_film_room()
