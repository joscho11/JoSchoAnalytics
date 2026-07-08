"""Film Room tab: embedded TikTok videos in a tidy grid + click-to-open breakdowns.

Kept out of app.py so adding a video is a data-only change (see video_content.py).
Videos fill left-to-right and wrap to the next row as more are added.
"""
import os

import streamlit as st
import streamlit.components.v1 as components

from video_content import INTRO_VIDEO, VIDEOS

_HERE = os.path.dirname(os.path.abspath(__file__))
_BREAKDOWN_DIR = os.path.join(_HERE, "video_breakdowns")

_PER_ROW = 3          # videos per row; they wrap to a new line when full
_EMBED_HEIGHT = 800   # tall enough to show the full TikTok card (video + caption + sound)


def _tiktok_embed(video_id: str, url: str) -> None:
    html = f"""
    <div style="display:flex;justify-content:center;">
      <blockquote class="tiktok-embed" cite="{url}" data-video-id="{video_id}"
                  style="max-width:325px;min-width:280px;margin:0;">
        <a href="{url}" target="_blank" rel="noopener">Watch on TikTok</a>
      </blockquote>
    </div>
    <script async src="https://www.tiktok.com/embed.js"></script>
    """
    components.html(html, height=_EMBED_HEIGHT, scrolling=False)


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


def render_film_room() -> None:
    st.header("📺 Film Room")
    st.caption("Model-backed breakdowns. Watch the short, then open the full analysis.")

    open_breakdown = _make_dialog()

    intro = {**INTRO_VIDEO, "short_caption": "Start here — what the channel is about."}
    items = [intro] + list(VIDEOS)

    for i in range(0, len(items), _PER_ROW):
        for col, item in zip(st.columns(_PER_ROW), items[i:i + _PER_ROW]):
            with col:
                st.markdown(f"**{item['title']}**")
                caption = item.get("subtitle") or item.get("short_caption")
                if caption:
                    st.caption(caption)
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
                            if st.button(label, key=key, use_container_width=True):
                                open_breakdown(content)
                    else:
                        with st.expander(label):
                            st.markdown(content)
        st.divider()
