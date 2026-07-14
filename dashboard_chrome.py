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
    /* Tighten the top gap. With a position="top" nav Streamlit pads the main block
       container's top by 8rem — far more than the header needs — leaving a big empty
       band under the nav. Pull content up to start just below the header. Tunable:
       raise this if page content ever tucks under the nav bar. */
    [data-testid="stMainBlockContainer"] {
        padding-top: 4rem !important;
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
    """Brand + tip jar laid onto Streamlit's OWN top-nav strip — the Fantasy / Betting /
    More menu lives inside [data-testid=stHeader], so all three share one bar.

    That nav is framework chrome we cannot add DOM children to, so we overlay a
    full-width, click-THROUGH fixed bar over the same band: brand pinned far-left, tip
    jar far-right, and the nav links show through the transparent middle and stay
    clickable (pointer-events:none on the bar, auto on our two items). We also pad the
    header's left/right so the nav links don't tuck under the brand / tip jar. Fixed =>
    it rides the header on scroll and reserves no flow space, so nothing is hidden.
    Byte-identical brand / tip-jar strings; the 'buy me a coffee' line is the tip jar's
    hover title. The --jsa-h height and the header side-paddings are the knobs to nudge
    on-device if the theme shifts the nav band (see the revamp report for honesty on how
    close to the framework nav this actually sits)."""
    st.markdown(
        f'''<style>
:root{{--jsa-h:3.25rem;}}
[data-testid="stHeader"]{{padding-left:11rem;padding-right:13rem;}}
#jsa-topbar{{position:fixed;top:0;left:0;right:0;height:var(--jsa-h);
display:flex;align-items:center;justify-content:space-between;
padding:0 1rem 0 1.1rem;pointer-events:none;z-index:999992;}}
#jsa-topbar>*{{pointer-events:auto;}}
@media (max-width:640px){{[data-testid="stHeader"]{{padding-left:.5rem;padding-right:.5rem;}}
 #jsa-topbar .jsa-brand{{font-size:15px;}} #jsa-topbar a{{margin-right:2.6rem;}}}}
</style>
<div id="jsa-topbar">
<span class="jsa-brand" style="font-size:19px;font-weight:800;letter-spacing:.3px;
color:#fafafa;text-shadow:0 1px 3px #0e1117;">JoScho Analytics</span>
<a href="{_VENMO}" target="_blank" rel="noopener noreferrer"
title="If you find this useful, buy me a coffee ☕"
style="margin-right:2.5rem;background:#3D95CE;color:#fff;font-weight:600;font-size:13px;
padding:6px 13px;border-radius:8px;text-decoration:none;white-space:nowrap;">💙 Tip Jar — Venmo @JoScho</a>
</div>''',
        unsafe_allow_html=True)


def render_footer():
    """Rendered on every page AFTER nav.run(), in the page flow (mobile-visible) —
    replaces the retired sidebar. A single CENTERED public-repo line; the tip jar moved
    UP into the persistent header (render_header) and the brand logo was retired."""
    st.divider()
    # Centered repo line (Q3, repo ROOT). Copy byte-identical to the 4e footer wording.
    st.markdown(
        "<div style='text-align:center;font-size:.875rem;color:#808495;'>"
        "The models and code behind this are public → "
        f"<a href='{_REPO}' target='_blank' rel='noopener noreferrer' "
        "style='color:#6ea8d8;text-decoration:none;'>"
        "github.com/joscho11/BettingEdgeContinued</a></div>",
        unsafe_allow_html=True)
