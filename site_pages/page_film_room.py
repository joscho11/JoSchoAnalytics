"""Film Room page wrapper for the shared analysis and site-walkthrough library."""
import importlib

import streamlit as st

import page_common
import film_room as _film_room
import video_content as _video_content

# Analysis shorts and product walkthroughs share one canonical video library.
HEADER = "Short analysis and site walkthroughs, each with the context behind it."


def _fresh_film_room():
    """Return film_room bound to the current video_content.

    Adding a video only edits video_content.py. film_room copies its names at
    import time, so reloading film_room alone (its own file never changed) keeps
    serving the old list after Streamlit Cloud syncs a new registry into a live
    process. Reload video_content first, then film_room if the registry moved.
    """
    stamp = getattr(_video_content, "__joscho_source_mtime_ns__", None)
    page_common.reload_if_stale(_video_content)
    if getattr(_video_content, "__joscho_source_mtime_ns__", None) != stamp:
        return importlib.reload(_film_room)
    return page_common.reload_if_stale(_film_room)


def render():
    st.title("Film room")
    st.caption(HEADER)
    _fresh_film_room().render_film_room(show_header=False)
