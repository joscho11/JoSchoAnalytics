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

# Shared fixed height for every long, scrolling st.dataframe on the site (~20 data
# rows visible; the rest scroll inside). One source of truth — the Draft Board and
# the long per-position / all-time tables all import this. Trivially tunable after
# on-device eyeballing.
TABLE_HEIGHT = 735


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


def render_header():
    """Persistent branded header strip. Rendered by the entrypoint BEFORE nav.run() so
    it sits above the top nav and shows on every page (tab-independent, always present).
    Brand far-left; the tip jar — moved byte-identical from the old footer — pinned
    far-right. A flex bar that wraps on narrow screens, so on a phone the brand and the
    tip jar stack instead of overflowing, staying legible. The 'buy me a coffee' line
    travels byte-identical as the tip jar's hover title; the direct Venmo link replaces
    the old two-click GA button (see render_footer history)."""
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:6px 16px;'
        'justify-content:space-between;align-items:center;padding:12px 18px;'
        'margin-bottom:8px;background:#0e1117;border:1px solid #262730;'
        'border-radius:10px;">'
        '<span style="font-size:22px;font-weight:800;letter-spacing:.3px;'
        'color:#fafafa;">JoScho Analytics</span>'
        f'<a href="{_VENMO}" target="_blank" rel="noopener noreferrer" '
        'title="If you find this useful, buy me a coffee ☕" '
        'style="background:#3D95CE;color:#fff;font-weight:600;font-size:13px;'
        'padding:7px 15px;border-radius:8px;text-decoration:none;'
        'white-space:nowrap;">💙 Tip Jar — Venmo @JoScho</a></div>',
        unsafe_allow_html=True)


def render_footer():
    """Rendered on every page AFTER nav.run(), in the page flow (mobile-visible) —
    replaces the retired sidebar. Small brand logo and a public-repo link only; the
    tip jar moved UP into the persistent header (render_header), so it is not duplicated."""
    st.divider()
    _mid = st.columns([1, 2, 1])[1]
    with _mid:
        if _LOGO.exists():
            st.image(str(_LOGO), width=120)   # small brand furniture (Q4)
        # NEW footer line (Q3, repo ROOT). Wording from design 4e proposal — flagged
        # as a new non-4d string for ratification.
        st.caption("The models and code behind this are public → "
                   f"[github.com/joscho11/BettingEdgeContinued]({_REPO})")
