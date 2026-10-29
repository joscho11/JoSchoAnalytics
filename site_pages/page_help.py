"""Searchable Help & Guide page."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

import video_content

import help_content
import page_common


_GUIDE_SLUGS = ("site-walkthrough", "league-history-guide")
_GUIDE_DIR = Path(__file__).resolve().parents[1] / "video_breakdowns"


def _select_guide(slug: str) -> None:
    st.session_state["help_guide"] = slug
    page_common.sync_query_value("guide", slug)


def _render_guides() -> None:
    guides = {item["slug"]: item for item in video_content.VIDEOS if item["slug"] in _GUIDE_SLUGS}
    selected = st.session_state.get("help_guide")
    st.subheader("Video guides")
    for col, slug in zip(st.columns(2), _GUIDE_SLUGS):
        item = guides[slug]
        with col, st.container(border=True):
            st.markdown("**Website walkthrough**" if slug == "site-walkthrough" else "**How to use League History**")
            st.caption(f"Recorded {item['date']}")
            st.caption("Page-by-page site tour." if slug == "site-walkthrough" else "Explore Sleeper, ESPN, Yahoo, and CBS leagues. The recording shows Sleeper and ESPN.")
            st.button("Watch site tour" if slug == "site-walkthrough" else "Watch League History guide",
                      key=f"help_watch_{slug}", type="primary" if selected == slug else "secondary",
                      width="stretch", on_click=_select_guide, args=(slug,))
    if selected not in guides:
        return
    item = guides[selected]
    st.markdown(f"**{item['title']}**")
    st.caption(f"Recorded {item['date']}. The site has changed since this recording; current steps are below.")
    st.link_button("Open walkthrough on TikTok", item["tiktok_url"], icon=":material/open_in_new:")
    st.caption("If the player is blank or blocked, use the TikTok link above.")
    with st.container(horizontal_alignment="center"):
        with st.container(width=405):
            st.iframe(f"https://www.tiktok.com/player/v1/{item['video_id']}?autoplay=0", width="stretch", height=720)
    with st.expander("Current written guide"):
        st.markdown((_GUIDE_DIR / item["breakdown_file"]).read_text(encoding="utf-8"))


def _render_item(item: help_content.FAQItem) -> None:
    if item.inline:
        # The model rundowns hold their own expanders; nesting them hid every explanation.
        item.render()
        return
    with st.expander(item.question):
        item.render()


def _render_items(items: tuple[help_content.FAQItem, ...]) -> None:
    for item in items:
        _render_item(item)


def _topic_selector() -> str:
    options = list(help_content.TOPICS)
    seeded = page_common.seed_widget_from_query("help_topic", "help_topic", options)
    kwargs = {
        "label": "Topic",
        "options": options,
        "key": "help_topic",
        "required": True,
        "width": "stretch",
        "help": "Choose a topic, or search all topics above.",
    }
    if not seeded and "help_topic" not in st.session_state:
        kwargs["default"] = options[0]
    selected = st.segmented_control(**kwargs) or options[0]
    page_common.sync_query_value("help_topic", selected)
    return selected


def _render_footer() -> None:
    with st.container(border=True, horizontal_alignment="center"):
        st.caption(
            "Not financial advice. Sports betting involves real risk. Bet responsibly.",
            text_alignment="center",
        )
        st.markdown("Built by **Joseph Schoenbaum**", text_alignment="center")
        st.link_button(
            "View methodology and code",
            "https://github.com/joscho11/JoSchoAnalytics",
            icon=":material/code:",
            type="tertiary",
        )


def render() -> None:
    st.title("Help & guide")
    st.caption(
        "Plain-language answers about the site, NFL football, fantasy, betting, "
        "and the models behind the numbers."
    )

    requested = page_common.query_value("guide")
    if requested in _GUIDE_SLUGS:
        if st.session_state.get("help_guide_url") != requested:
            st.session_state["help_guide"] = requested
            st.session_state["help_guide_url"] = requested
            st.session_state["help_topic"] = "Site Guide"
            st.session_state["help_search"] = ""
    else:
        if requested is not None:
            page_common.sync_query_value("guide", "")
        st.session_state.pop("help_guide", None)
        st.session_state.pop("help_guide_url", None)

    query = st.text_input(
        "Search Help & Guide",
        key="help_search",
        placeholder="Try: half-PPR, HIGH, EPA, ADP",
        help="Search questions, topic names, and keywords.",
    ).strip()
    topic = _topic_selector()

    if query:
        matches = help_content.search_items(query)
        st.caption(f"{len(matches)} matching answer{'s' if len(matches) != 1 else ''}")
        if not matches:
            st.info("No matching answers. Try a broader term such as spread, fantasy, model, or league.")
        else:
            for group in help_content.TOPICS:
                grouped = tuple(item for item in matches if item.topic == group)
                if grouped:
                    st.subheader(group)
                    _render_items(grouped)
    else:
        st.subheader(topic)
        if topic == "Site Guide":
            _render_guides()
        _render_items(help_content.items_for_topic(topic))

    _render_footer()
