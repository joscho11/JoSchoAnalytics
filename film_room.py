"""Compatibility for old Film Room links; the video library is retired."""
from pathlib import Path
from datetime import date

import streamlit as st

import nav_registry
import page_common
from video_content import VIDEOS

_BREAKDOWN_DIR = Path(__file__).resolve().parent / "video_breakdowns"
_WALKTHROUGHS = {"league-history-guide", "site-walkthrough"}


def _fmt_published(iso: str) -> str:
    try:
        published = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"Published {published:%b} {published.day}, {published.year}"


def _load_breakdown(fname: str) -> str:
    try:
        return (_BREAKDOWN_DIR / fname).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "_Full breakdown coming soon._"


def _open_help(guide: str | None = None) -> None:
    params = {"help_topic": "Site Guide"}
    if guide:
        params["guide"] = guide
    page = nav_registry.PAGES.get("help")
    if page is not None:
        st.switch_page(page, query_params=params)
    else:
        # Standalone page previews have no navigation registry.
        st.info("Walkthroughs are available in Help & Guide under Site Guide.")


def render_film_room(*, show_header: bool = True) -> None:
    """Resolve a bookmarked episode without restoring the retired catalogue."""
    slug = str(page_common.query_value("video") or "")
    item = next((episode for episode in VIDEOS if episode["slug"] == slug), None)
    if item is None or slug in _WALKTHROUGHS:
        _open_help(slug if slug in _WALKTHROUGHS else None)
        return

    if show_header:
        st.title(item["title"])
    else:
        st.subheader(item["title"])
    published = _fmt_published(item.get("date", ""))
    if published:
        st.caption(published)
    st.caption(
        "This archived analysis reflects its publication date. "
        "Its forecasts, player situations, and model claims may have changed."
    )
    st.link_button("Watch on TikTok", item["tiktok_url"], icon=":material/play_arrow:")
    if item.get("breakdown_file") or item.get("about") or item.get("archive_note"):
        with st.expander("Archived written breakdown", expanded=False):
            if item.get("archive_note"):
                st.markdown(item["archive_note"])
            if item.get("breakdown_file"):
                st.markdown(_load_breakdown(item["breakdown_file"]))
            elif item.get("about"):
                st.markdown(item["about"])
