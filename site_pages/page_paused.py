"""Retained URLs for temporarily archived public products."""
import streamlit as st

import nav_registry


def render(slug: str) -> None:
    title = {
        "anytime-tds": "Touchdown Props",
        "college-basketball": "College Basketball predictions",
    }[slug]
    st.title(title)
    st.info("This product is paused")
    st.write("Predictions are currently unavailable. Historical records are preserved.")
    st.page_link(nav_registry.PAGES["home"], label="Back to Home", icon=":material/home:")
