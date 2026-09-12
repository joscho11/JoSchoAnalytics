"""Searchable Help & Guide page."""
from __future__ import annotations

import streamlit as st

import help_content
import page_common


def _render_item(item: help_content.FAQItem) -> None:
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

    query = st.text_input(
        "Search Help & Guide",
        key="help_search",
        placeholder="Try: half-PPR, HIGH, EPA, ADP, break-even, or league history",
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
        _render_items(help_content.items_for_topic(topic))

    _render_footer()
