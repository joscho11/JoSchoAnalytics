"""Shared site chrome for the multipage app (site revamp Batch 1): GA helpers,
the global CSS, and the footer that replaces the retired sidebar.

Import-safe: defines functions/constants only — no GA fire, no secrets read, no
st.* call at import time. The APP_OFFLINE guard lives here so every page imports
one consistent value.
"""
import os
import threading
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
_REPO = "https://github.com/joscho11/JoSchoAnalytics"   # repo ROOT only (Q3)

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
    """Fire one GA4 measurement-protocol event. No-op when offline or creds absent.

    The POST is dispatched on a short-lived daemon thread rather than awaited inline.
    Measured 2026-07-29: the round trip to google-analytics.com/mp/collect is ~224 ms
    typical and the timeout allows 3 s, and it sat on the critical path of the FIRST
    render of every session (site_pageview_once runs before st.navigation). GA is a
    fire-and-forget beacon — nothing on the page depends on its response — so the wait
    bought nothing. Payload, endpoint, params and timeout are unchanged; only the wait
    is gone. This is not a persistent worker: the thread exists for one request.
    """
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
    # Snapshot every session_state read on THIS thread; the worker touches no Streamlit
    # state (a background thread has no ScriptRunContext).
    payload = {"client_id": st.session_state.ga_client_id,
               "events": [{"name": name, "params": params}]}
    query = {"measurement_id": mid, "api_secret": sec}

    def _post():
        try:
            req.post("https://www.google-analytics.com/mp/collect",
                     params=query, json=payload, timeout=3)
        except Exception:
            pass

    try:
        threading.Thread(target=_post, name="ga-beacon", daemon=True).start()
    except Exception:
        _post()   # thread creation refused: fall back to the old inline behavior


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
/* Right inset reserves the tip jar's own width (~194px) plus a gap, so neither the nav
   links nor Streamlit's `⋮` main menu — both laid out inside this padding box — can end
   up underneath it. It was 13rem, which is NARROWER than the pill, and the `⋮` sat 24px
   under the pill at every width from 641px up (hit-tested: elementFromPoint at the menu
   centre returned the Venmo anchor). Keep this >= the .jsa-tip width + 1rem. */
[data-testid="stHeader"]{{padding-left:11rem;padding-right:14rem;}}
/* z-index MUST be 999990 — the same layer as stHeader, NOT above it.
     stHeader/stToolbar 999990  <  stSidebar 999991
   At 999992 this bar painted above BOTH, so while the mobile nav drawer was open the
   fixed overlay swallowed taps meant for the drawer's close control. At 999990 the bar
   still paints over the header band (equal z-index resolves by document order and this
   div comes later), while the drawer at 999991 correctly paints over the bar. */
#jsa-topbar{{position:fixed;top:0;left:0;right:0;height:var(--jsa-h);
display:flex;align-items:center;justify-content:space-between;
padding:0 1rem 0 1.1rem;pointer-events:none;z-index:999990;}}
#jsa-topbar>*{{pointer-events:auto;}}
/* Presentation lives in classes, not style="" attributes, so the narrow-width blocks
   below can override it with ordinary specificity instead of !important. Markup and
   copy unchanged. */
.jsa-brand{{font-size:19px;font-weight:800;letter-spacing:.3px;
color:#fafafa;text-shadow:0 1px 3px #0e1117;}}
.jsa-tip{{background:#3D95CE;color:#fff;font-weight:600;font-size:13px;
padding:6px 13px;border-radius:8px;text-decoration:none;white-space:nowrap;}}
/* Belt and braces with the z-index fix: while the drawer is open the branded overlay is
   both irrelevant and in the way, so it stands down entirely. A browser without :has()
   still gets the correct hit-testing from the z-index above. */
body:has(section[data-testid="stSidebar"][aria-expanded="true"]) #jsa-topbar{{
visibility:hidden;pointer-events:none;}}
/* Streamlit hides the drawer's own collapse control (visibility:hidden) above its 576px
   `sm` breakpoint and reveals it only on sidebar HOVER. A touch device has no hover, so
   from 577px to 767px — large phones and small tablets, exactly the band where the nav
   is drawer-only — the drawer could be opened and then not closed from its own control.
   Hover-only is not an acceptable affordance on touch, so force it visible for as long
   as the drawer is open. Above 767px the nav is inline and no drawer exists. */
@media (max-width:767px){{
 section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"],
 section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] button{{
 visibility:visible;}}}}
/* ── Phone header, owned HERE and complete on its own ──────────────────────────────
   This block is the whole phone header contract, not a partial one: mobile.py is the
   page-CONTENT layer and deliberately carries no header rules, so deleting it leaves
   this correct rather than half-applied. Verified standalone down to 320px.
   Below 640px Streamlit collapses the top nav into a drawer whose `»` trigger renders
   at the header's left inset (x=22..58) and its `⋮` in the rightmost ~50px, so the bar
   reserves both and brand + tip jar share only the middle. */
@media (max-width:640px){{
 [data-testid="stHeader"]{{padding-left:.25rem;padding-right:.25rem;}}
 #jsa-topbar{{padding-left:3.9rem;padding-right:3.4rem;gap:.4rem;}}
 .jsa-brand{{font-size:13px;letter-spacing:.2px;white-space:nowrap;flex:0 0 auto;}}
 .jsa-tip{{font-size:10.5px;font-weight:700;padding:5px 8px;flex:0 1 auto;min-width:0;
  min-height:2rem;display:flex;align-items:center;justify-content:center;}}
 /* The drawer trigger is the only way to change page here — give it a real tap target
    and a surface so it reads as a menu rather than a stray glyph. */
 [data-testid="stExpandSidebarButton"]{{min-width:2.25rem;min-height:2.25rem;
  border:1px solid var(--jsa-border, #232D3B);border-radius:var(--jsa-r-sm, 8px);
  background:var(--jsa-surface, #121821);}}
 [data-testid="stExpandSidebarButton"] span{{font-size:22px;}}
 [data-testid="stSidebarNavLink"]{{min-height:2.6rem;align-items:center;}}
 [data-testid="stSidebarNav"] a span{{font-size:15px;}}}}
/* Narrow phones. Fixed overhead is ~117px (62px reserving the `»`, 55px reserving the
   `⋮`), leaving ~200px at 320px — too little for brand AND a one-line pill at legible
   sizes. The pill's label wraps inside itself instead of shrinking to unreadable; every
   word is still there and it still fits the 52px bar. Without this the brand wrapped to
   two lines and the pill sat 28px under the `⋮` at 320px. */
@media (max-width:400px){{
 .jsa-brand{{font-size:12px;}}
 .jsa-tip{{white-space:normal;line-height:1.2;text-align:center;padding:4px 7px;}}}}
</style>
<div id="jsa-topbar">
<span class="jsa-brand">JoScho Analytics</span>
<a class="jsa-tip" href="{_VENMO}" target="_blank" rel="noopener noreferrer"
title="If you find this useful, buy me a coffee ☕">💙 Tip Jar — Venmo @JoScho</a>
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
        "github.com/joscho11/JoSchoAnalytics</a></div>",
        unsafe_allow_html=True)
