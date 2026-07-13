"""Shared site chrome for the multipage app (site revamp Batch 1): GA helpers,
the global CSS, and the footer that replaces the retired sidebar.

Import-safe: defines functions/constants only — no GA fire, no secrets read, no
st.* call at import time. The APP_OFFLINE guard lives here so every page imports
one consistent value.
"""
import os
import time
import uuid
from pathlib import Path

import requests as req
import streamlit as st

_HERE = Path(__file__).resolve().parent
# Hermetic-test switch: when "1" the app attempts NO network (GA off).
_OFFLINE = os.environ.get("APP_OFFLINE") == "1"
CANONICAL_URL = "https://joschoanalytics.streamlit.app"
_LOGO = _HERE / "assets" / "logo.svg"
_VENMO = "https://venmo.com/u/JoScho"
_REPO = "https://github.com/joscho11/BettingEdgeContinued"   # repo ROOT only (Q3)


def _ga_creds():
    # a missing/unreadable secrets.toml degrades to analytics-off, never a crash
    try:
        return (st.secrets.get("GOOGLE_ANALYTICS_ID", ""),
                st.secrets.get("GA_API_SECRET", ""))
    except Exception:
        return "", ""


def _utm_params():
    """utm_* query params from the URL (campaign attribution), passed to GA."""
    try:
        return {k: v for k, v in st.query_params.items() if k.startswith("utm_")}
    except Exception:
        return {}


def send_ga_event(name, extra_params=None):
    """Fire one GA4 measurement-protocol event. No-op when offline or creds absent."""
    if _OFFLINE:
        return
    mid, sec = _ga_creds()
    if not (mid and sec):
        return
    if 'ga_client_id' not in st.session_state:
        st.session_state.ga_client_id = str(uuid.uuid4())
    if 'ga_session_id' not in st.session_state:
        st.session_state.ga_session_id = str(int(time.time()))
    params = {
        "page_title": "JoScho Analytics | NFL Predictions",
        "page_location": CANONICAL_URL,
        "session_id": st.session_state.ga_session_id,
        "engagement_time_msec": "100",
    }
    params.update(_utm_params())
    if extra_params:
        params.update(extra_params)
    try:
        req.post(
            "https://www.google-analytics.com/mp/collect",
            params={"measurement_id": mid, "api_secret": sec},
            json={"client_id": st.session_state.ga_client_id,
                  "events": [{"name": name, "params": params}]},
            timeout=3,
        )
    except Exception:
        pass


def site_pageview_once():
    """A single per-session pageview (mirrors the current app.py behavior). Per-PAGE
    pageviews are a later batch (design 4f / Batch D)."""
    if 'ga_tracked' not in st.session_state:
        st.session_state.ga_tracked = True
        send_ga_event("page_view")


def inject_css():
    """The global CSS (moved verbatim from app.py) — expander/summary styling."""
    st.markdown("""
    <style>
    details {
        border: none !important;
        box-shadow: none !important;
    }
    details summary {
        font-size: 11px !important;
        color: var(--conf-color, #aaa) !important;
        background-color: var(--conf-bg, #2d3748) !important;
        border-radius: 6px !important;
        padding: 4px 10px !important;
        border: 1px solid var(--conf-border, #4a5568) !important;
        width: fit-content !important;
    }
    details summary:hover {
        color: white !important;
        background-color: #3d4f66 !important;
        border-color: #6b8aad !important;
        cursor: pointer !important;
    }
    details[open] summary {
        border-radius: 6px 6px 0 0 !important;
    }
    details > div {
        background-color: #1a2332 !important;
        border: 1px solid var(--conf-border, #4a5568) !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        padding: 10px !important;
        font-size: 13px !important;
        line-height: 1.6 !important;
        color: #ddd !important;
    }
    .st-expander {
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stExpander"] {
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stExpanderDetails"] {
        border: none !important;
    }
    </style>
""", unsafe_allow_html=True)


def render_preseason_banner(board_page=None, season_year=2026):
    """Pre-season banner variant (design 4d.ii, verbatim-ratified). Points to the live
    daily-refreshing board. `board_page` is the Draft Board st.Page for the page_link
    (skipped gracefully if not registered, e.g. in a test harness)."""
    st.info(
        f"🏈 The {season_year} season hasn't kicked off yet. My **2026 Draft Board** is "
        "live and refreshing daily from the latest draft data — jump in below. Weekly "
        "predictions return at Week 1.")
    if board_page is not None:
        st.page_link(board_page, label="Open the Draft Board", icon="📋")


def render_footer():
    """Rendered on every page AFTER nav.run(), in the page flow (mobile-visible) —
    replaces the retired sidebar. Tip jar (with a lightest-touch click count),
    small brand logo, and a public-repo link."""
    st.divider()
    _mid = st.columns([1, 2, 1])[1]
    with _mid:
        # Tip jar: st.button so the click reruns and fires a GA count server-side
        # (lightest outbound-click mechanism, no attribution plumbing — Q2). The
        # tip-jar COPY strings are byte-identical to the retired sidebar version.
        if st.button("💙 Tip Jar — Venmo @JoScho", key="tip_jar_btn",
                     width="stretch"):
            send_ga_event("tip_jar_click")
            st.markdown(f"[Open Venmo → @JoScho]({_VENMO})")
        st.caption("If you find this useful, buy me a coffee ☕")
        if _LOGO.exists():
            st.image(str(_LOGO), width=120)   # small brand furniture (Q4)
        # NEW footer line (Q3, repo ROOT). Wording from design 4e proposal — flagged
        # as a new non-4d string for ratification.
        st.caption("The models and code behind this are public → "
                   f"[github.com/joscho11/BettingEdgeContinued]({_REPO})")
