"""Film Room: one TikTok player plus a section/episode picker, with click-to-open breakdowns.

Kept out of app.py so adding a video is a data-only change (see video_content.py).

Only the selected video mounts a TikTok iframe. Opening the page defaults to
DEFAULT_VIDEO_SLUG (League History walkthrough). An optional INTRO_VIDEO in
video_content.py (currently None) would reappear as a Start here control.
"""
import os
from datetime import date as _date

import streamlit as st

import page_common
import nav_registry
from video_content import DEFAULT_VIDEO_SLUG, INTRO_VIDEO, VIDEO_SECTIONS, VIDEOS

_HERE = os.path.dirname(os.path.abspath(__file__))
_BREAKDOWN_DIR = os.path.join(_HERE, "video_breakdowns")

# 9:16 player. embed/v2 is the white TikTok post card; player/v1 is the dark video.
_EMBED_HEIGHT = 720
_SEL_KEY = "film_room_sel"
_INTRO_KEY = "__intro__"
_PICK_KEY_PREFIX = "fr_pick_"
_SITE_BG = "#0B0F14"

_SEC_KEY = "film_room_section"
_EP_KEY_PREFIX = "fr_ep_"
_SECTION_SHORT = {
    "site-walkthroughs": "Walkthroughs",
    "predictions": "Predictions",
    "draft-strategy": "Draft",
    "player-breakdowns": "Players",
}

# Iframe chrome is painted to the site background so leftover space is not white.
_PICKER_CSS = f"""
<style>
[data-testid="stIFrame"] {{
  background: {_SITE_BG} !important;
  display: flex !important;
  justify-content: center !important;
}}
[data-testid="stIFrame"] iframe {{
  background: {_SITE_BG} !important;
  border: 0 !important;
  border-radius: 12px;
  color-scheme: dark;
  width: min(100%, 405px) !important;
}}
</style>
"""


def _embed_src(video_id: str) -> str:
    return f"https://www.tiktok.com/player/v1/{video_id}"


def _tiktok_embed(video_id: str, url: str) -> None:
    # Official player kit, not the oEmbed card. No oEmbed fetch, no embed.js.
    # Offline, TikTok's own unavailable state shows inside the dark frame.
    st.iframe(_embed_src(video_id), height=_EMBED_HEIGHT)


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


def _intro_item() -> dict | None:
    if not INTRO_VIDEO:
        return None
    return {
        **INTRO_VIDEO,
        "slug": _INTRO_KEY,
        "short_caption": INTRO_VIDEO.get(
            "short_caption", "Start here: what the channel is about."
        ),
    }


def _episodes() -> list:
    """Newest first. ISO dates sort lexicographically; an undated entry sorts last."""
    return sorted(VIDEOS, key=lambda v: v.get("date") or "", reverse=True)


def _grouped_episodes(episodes: list) -> dict[str, list]:
    grouped = {key: [] for key, _label in VIDEO_SECTIONS}
    for item in episodes:
        key = item.get("section")
        if key not in grouped:
            key = "player-breakdowns"
        grouped[key].append(item)
    return grouped


def _sectioned_episodes(episodes: list) -> list[tuple[str, list]]:
    """Return configured sections, omitting empty ones and preserving episode order."""
    grouped = _grouped_episodes(episodes)
    return [
        (label, grouped[key])
        for key, label in VIDEO_SECTIONS
        if grouped[key]
    ]


def _section_of(slug: str, episodes: list, intro: dict | None) -> str:
    if intro is not None and slug == _INTRO_KEY:
        return VIDEO_SECTIONS[0][0]
    known = {key for key, _label in VIDEO_SECTIONS}
    for item in episodes:
        if item.get("slug") == slug:
            key = item.get("section")
            return key if key in known else "player-breakdowns"
    return VIDEO_SECTIONS[0][0]


def _item_for(sel: str, intro: dict | None, episodes: list) -> dict | None:
    if intro is not None and sel == _INTRO_KEY:
        return intro
    for item in episodes:
        if item.get("slug") == sel:
            return item
    for item in episodes:
        if item.get("slug") == DEFAULT_VIDEO_SLUG:
            return item
    if episodes:
        return episodes[0]
    return intro


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
    """Render an archive explanation and its optional replacement/current destination."""
    note = item["archive_note"]
    link = item.get("archive_link") or {}
    page = nav_registry.PAGES.get(link.get("page"))

    def _body() -> None:
        st.markdown(note)
        if page is not None:
            st.page_link(
                page,
                label=link["label"],
                icon=link.get("icon"),
                query_params=link.get("query_params"),
            )

    if hasattr(st, "popover"):
        with st.popover("📼 Archived: why?"):
            _body()
    else:
        with st.expander("📼 Archived: why?"):
            _body()


def _set_sel(slug: str) -> None:
    # on_click runs before the next script body, so the player column (which
    # renders first) already sees the new selection on that rerun.
    st.session_state[_SEL_KEY] = slug


def _pick_button(label: str, slug: str, selected: str) -> None:
    st.button(
        label,
        key=f"{_PICK_KEY_PREFIX}{slug}",
        type="primary" if selected == slug else "secondary",
        width="stretch",
        on_click=_set_sel,
        args=(slug,),
    )


def _render_player(item: dict | None, open_breakdown) -> None:
    if item is None:
        st.caption("No videos in the Film Room yet.")
        return
    _render_published(item)
    st.markdown(f"**{item['title']}**")
    caption = item.get("subtitle") or item.get("short_caption")
    if caption:
        st.caption(caption)
    if item.get("archived") and item.get("archive_note"):
        _render_archive_popout(item)
    _tiktok_embed(item["video_id"], item["tiktok_url"])
    with st.container(horizontal=True, horizontal_alignment="center"):
        st.link_button(
            "Watch on TikTok",
            item["tiktok_url"],
            icon=":material/play_arrow:",
            type="tertiary",
        )
    if item.get("breakdown_file"):
        label, content = "📖 Full breakdown", _load_breakdown(item["breakdown_file"])
    elif item.get("about"):
        label, content = "ℹ️ What is this?", item["about"]
    else:
        label = content = None
    if content is None:
        return
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    key = f"btn_{item.get('slug', item['video_id'])}"
    if open_breakdown is not None:
        _, _bc, _ = st.columns([1, 2, 1])
        with _bc:
            if st.button(label, key=key, width="stretch"):
                open_breakdown(content)
    else:
        with st.expander(label):
            st.markdown(content)


def render_film_room(*, show_header: bool = True) -> None:
    if show_header:
        st.header("Film room")
        st.caption("Analysis and site walkthroughs. Watch the short, then open the full context.")
    st.markdown(_PICKER_CSS, unsafe_allow_html=True)

    intro = _intro_item()
    episodes = _episodes()
    default = (
        DEFAULT_VIDEO_SLUG
        if DEFAULT_VIDEO_SLUG in {item["slug"] for item in episodes}
        else (episodes[0]["slug"] if episodes else (_INTRO_KEY if intro else ""))
    )
    valid = {item["slug"] for item in episodes}
    if intro is not None:
        valid.add(_INTRO_KEY)
    if _SEL_KEY not in st.session_state:
        shared = str(page_common.query_value("video") or "")
        st.session_state[_SEL_KEY] = shared if shared in valid else default
    selected = st.session_state[_SEL_KEY]
    if selected not in valid:
        selected = default
        st.session_state[_SEL_KEY] = selected
    open_breakdown = _make_dialog()

    # Catalog is two widgets, so it sits above the player. Phones no longer
    # scroll a title list, and desktop no longer has an empty right column.
    with st.container(key="jsa-filmroom-picker"):
        if intro is not None:
            st.caption("Start here")
            _pick_button(
                intro["short_caption"],
                _INTRO_KEY,
                selected,
            )
        grouped = _grouped_episodes(episodes)
        if _SEC_KEY not in st.session_state:
            st.session_state[_SEC_KEY] = _section_of(selected, episodes, intro)
        if st.session_state[_SEC_KEY] not in grouped or not grouped[st.session_state[_SEC_KEY]]:
            st.session_state[_SEC_KEY] = _section_of(selected, episodes, intro)
        section_keys = [key for key, _label in VIDEO_SECTIONS if grouped[key]]
        sec_col, ep_col = st.columns([1, 1.25], vertical_alignment="bottom")
        with sec_col:
            st.segmented_control(
                "Section",
                options=section_keys,
                format_func=lambda key: _SECTION_SHORT.get(key, key),
                key=_SEC_KEY,
                required=True,
                width="stretch",
            )
        section = st.session_state[_SEC_KEY]
        section_items = grouped[section]
        slugs = [item["slug"] for item in section_items]
        titles = {item["slug"]: item["title"] for item in section_items}
        ep_key = f"{_EP_KEY_PREFIX}{section}"
        if ep_key not in st.session_state or st.session_state[ep_key] not in slugs:
            st.session_state[ep_key] = selected if selected in slugs else slugs[0]
        with ep_col:
            picked = st.selectbox(
                "Episode",
                slugs,
                format_func=lambda slug: titles[slug],
                key=ep_key,
                width="stretch",
            )
        selected = picked
        st.session_state[_SEL_KEY] = selected
        page_common.sync_query_value("video", selected)

    _render_player(_item_for(selected, intro, episodes), open_breakdown)
