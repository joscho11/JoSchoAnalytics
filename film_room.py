"""Film Room tab: embedded TikTok videos in a tidy grid + click-to-open breakdowns.

Kept out of app.py so adding a video is a data-only change (see video_content.py).
Videos fill left-to-right and wrap to the next row as more are added.

ORDER IS COMPUTED HERE, NOT STORED. The channel intro is pinned to the first slot as the
"start here" card, and every other video sorts by publish date, newest first (top-left) to
oldest (bottom-right). So VIDEOS in video_content.py can stay append-only and a new entry
lands in the right slot on its own. The intro is deliberately exempt from the sort: it is a
standing explainer, not part of the chronology, which is why its own date can read older
than the cards after it.
"""
import os
from datetime import date as _date

import streamlit as st

import nav_registry
from video_content import INTRO_VIDEO, VIDEOS

_HERE = os.path.dirname(os.path.abspath(__file__))
_BREAKDOWN_DIR = os.path.join(_HERE, "video_breakdowns")

_PER_ROW = 3          # videos per row; they wrap to a new line when full
_EMBED_HEIGHT = 800   # tall enough to show the full TikTok card (video + caption + sound)
# Fixed height for the publish date + title + short-caption region, so every card's video
# starts at the same vertical position and the cards align in a uniform grid. The archived-
# video note does not live here: it moved to a compact pop-out (see _render_archive_popout),
# so this region holds a date line, a title and one short caption.
# Raised 130 -> 150 when the publish-date line was added; a date line plus its margin is
# about 20px. Tunable: raise it if a longer title/subtitle ever wraps past this height.
_HEADER_HEIGHT = 150


def _tiktok_embed(video_id: str, url: str) -> None:
    # TikTok's official iframe player endpoint: no oEmbed fetch, no embed.js
    # hydration, works offline-gracefully (the iframe simply shows TikTok's
    # own unavailable state). st.iframe replaces the removed components.html.
    st.iframe(f"https://www.tiktok.com/embed/v2/{video_id}",
              height=_EMBED_HEIGHT)


def _fmt_published(iso: str) -> str:
    """'2026-08-06' -> 'Published Aug 6, 2026'. Empty string if the date is missing or
    unparseable, so a card without one simply renders no date line rather than breaking.
    The day is taken off the date object because %-d is not portable to Windows."""
    try:
        d = _date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"Published {d.strftime('%b')} {d.day}, {d.year}"


def _render_published(item: dict) -> None:
    """Small muted publish-date line above the title. Uses opacity rather than a fixed
    colour so it reads correctly against both the light and dark themes."""
    label = _fmt_published(item.get("date", ""))
    if not label:
        return
    st.markdown(
        f"<div style='font-size:11.5px;line-height:1.4;opacity:.65;margin-bottom:1px'>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _ordered_items() -> list:
    """The intro pinned first, then every other video newest-first. ISO dates sort
    lexicographically, so a plain string sort is correct; an undated entry sorts to the
    end rather than crashing or jumping to the front."""
    intro = {**INTRO_VIDEO, "short_caption": "Start here: what the channel is about."}
    rest = sorted(VIDEOS, key=lambda v: v.get("date") or "", reverse=True)
    return [intro] + rest


def _load_breakdown(fname: str) -> str:
    try:
        with open(os.path.join(_BREAKDOWN_DIR, fname), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "_Full breakdown coming soon._"


def _make_dialog():
    """Define the breakdown popup ONCE per run (outside any column) so the trigger
    button renders in place under its video. Returns a callable or None (fallback)."""
    if not hasattr(st, "dialog"):
        return None
    try:
        @st.dialog("📺 Film Room", width="large")
        def _open(md: str) -> None:
            st.markdown(md)
    except TypeError:  # older Streamlit without the width kwarg
        @st.dialog("📺 Film Room")
        def _open(md: str) -> None:
            st.markdown(md)
    return _open


def _render_archive_popout(item: dict) -> None:
    """The archived-video note as a compact pop-out button (it was an always-visible
    st.info that forced the whole card grid ~170px taller). The Draft Board cross-link
    (design 4g) moves inside the pop-out so an archived card is the same height as the rest.
    The note copy is rendered verbatim from video_content; layout change only."""
    note = item["archive_note"]
    board_pg = nav_registry.PAGES.get("draft-board")

    def _body() -> None:
        st.markdown(note)
        if board_pg is not None:
            st.page_link(board_pg, label="Open the Draft Board", icon="📋")

    if hasattr(st, "popover"):
        with st.popover("📼 Archived: why?"):
            _body()
    else:  # very old Streamlit without popover: fall back to an inline expander
        with st.expander("📼 Archived: why?"):
            _body()


def render_film_room() -> None:
    st.header("📺 Film Room")
    st.caption("Model-backed breakdowns. Watch the short, then open the full analysis.")

    open_breakdown = _make_dialog()

    items = _ordered_items()

    for i in range(0, len(items), _PER_ROW):
        for col, item in zip(st.columns(_PER_ROW), items[i:i + _PER_ROW]):
            with col:
                # Uniform-height header so every card's video starts at the same Y and the
                # embeds line up. EVERYTHING above the embed lives inside this fixed region
                # (publish date, title, one short caption, and for archived cards the pop-out
                # trigger), so an archived card is exactly as tall as its neighbours.
                #
                # The key is inert here (Streamlit only turns it into an `st-key-…` CSS class)
                # and exists so mobile.py can release THIS container's fixed height on a phone
                # (where the cards stack one per row and the height aligns nothing) without
                # a blanket rule that would release every explicitly sized container on the
                # site. Keys must be unique per element, hence the slug/id suffix.
                _card_key = f"jsa-filmroom-card-{item.get('slug') or item['video_id']}"
                with st.container(height=_HEADER_HEIGHT, border=False, key=_card_key):
                    _render_published(item)
                    st.markdown(f"**{item['title']}**")
                    caption = item.get("subtitle") or item.get("short_caption")
                    if caption:
                        st.caption(caption)
                    if item.get("archived") and item.get("archive_note"):
                        _render_archive_popout(item)
                _tiktok_embed(item["video_id"], item["tiktok_url"])
                st.markdown(
                    f"<div style='text-align:center;margin-top:-6px'>"
                    f"<a href='{item['tiktok_url']}' target='_blank' rel='noopener' "
                    f"style='font-size:13px;color:#3D95CE;text-decoration:none'>▶ Watch on TikTok</a></div>",
                    unsafe_allow_html=True,
                )
                # every card gets a button in the same slot so the columns stay uniform height
                if item.get("breakdown_file"):
                    label, content = "📖 Full breakdown", _load_breakdown(item["breakdown_file"])
                elif item.get("about"):
                    label, content = "ℹ️ What is this?", item["about"]
                else:
                    label = content = None

                if content is not None:
                    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)  # space above button
                    key = f"btn_{item.get('slug', item['video_id'])}"
                    if open_breakdown is not None:
                        _, _bc, _ = st.columns([1, 2, 1])  # center under the video
                        with _bc:
                            if st.button(label, key=key, width="stretch"):
                                open_breakdown(content)
                    else:
                        with st.expander(label):
                            st.markdown(content)
        st.divider()
