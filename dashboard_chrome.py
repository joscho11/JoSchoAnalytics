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

import email_signup

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
ROW_PX = 35          # st.dataframe row height
HEADER_PX = 38       # header row plus the 3px border


def exact_table_height(n_rows: int) -> int:
    """Height that fits n_rows with no trailing blank rows.

    TABLE_HEIGHT is sized for long scrolling boards. A fixed-length table (a
    9-slot DFS lineup, say) rendered at that height pads a dozen empty rows
    under the data and reads like the table failed to load.
    """
    return HEADER_PX + ROW_PX * max(int(n_rows), 1)


def dataframe_phone_desktop(desktop_data, phone_data, *, slug: str,
                            phone_column_config=None, **kwargs) -> None:
    """Show desktop_data above 640px and phone_data at phone width.

    Same pattern as the labeled-scatter swap: both copies render, CSS shows one.
    phone_column_config, when given, is the phone grid's own config (shorter
    labels, pinned widths). Otherwise the desktop config is filtered to the
    phone columns.
    """
    desktop_kwargs = dict(kwargs)
    phone_kwargs = dict(kwargs)
    if "key" in kwargs:
        desktop_kwargs["key"] = f"{kwargs['key']}-desktop"
        phone_kwargs["key"] = f"{kwargs['key']}-phone"
    if phone_column_config is not None:
        phone_kwargs["column_config"] = phone_column_config
    else:
        cfg = kwargs.get("column_config")
        if cfg:
            phone_cols = set(_dataframe_columns(phone_data))
            phone_kwargs["column_config"] = {
                name: spec for name, spec in cfg.items() if name in phone_cols
            }
    with st.container(key=f"jsa-table-desktop-{slug}"):
        st.dataframe(desktop_data, **desktop_kwargs)
    with st.container(key=f"jsa-table-phone-{slug}"):
        st.dataframe(phone_data, **phone_kwargs)


def _dataframe_columns(data):
    if hasattr(data, "data") and hasattr(data.data, "columns"):
        return list(data.data.columns)
    return list(getattr(data, "columns", []))


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


def site_pageview(page_title: str, url_path: str = "") -> None:
    """Send one page view per route per browser session.

    The route is public app state. Query parameters are deliberately excluded so a
    shared filter URL—or a Sleeper league ID—never reaches analytics.
    """
    path = str(url_path or "").strip("/")
    route = f"/{path}" if path else "/"
    tracked = st.session_state.setdefault("ga_tracked_pages", [])
    if route in tracked:
        return
    tracked.append(route)
    send_ga_event(
        "page_view",
        {
            "page_title": f"{page_title} | JoScho Analytics",
            "page_location": f"{CANONICAL_URL}{route if route != '/' else ''}",
            "page_path": route,
        },
    )


def site_pageview_once():
    """Backward-compatible wrapper for older harnesses."""
    site_pageview("JoScho Analytics", "")


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
    frozen independent-model projections and live Sleeper market board. `board_page` is the Draft Board st.Page for the page_link
    (skipped gracefully if not registered, e.g. in a test harness)."""
    st.info(
        f"🏈 The {season_year} season hasn't kicked off yet. My **2026 Draft Board** is "
        "live with frozen Model Proj and daily Sleeper market data; the next model "
        "update is the planned early-September pre-kickoff snapshot. Week 1 matchups "
        "are already on Weekly Predictions. The public spread card uses the first valid Tuesday capture from 09:00–15:30 ET.")
    if board_page is not None:
        st.page_link(board_page, label="Open the Draft Board", icon="📋")


def render_header():
    """Place the brand and Venmo support link in Streamlit's top navigation band."""
    st.markdown(
        f'''<style>
:root{{--jsa-h:3.25rem;}}
/* Keep Streamlit's own controls in their native header positions. The support pill is
   independently inset below, so padding the header cannot pull the menu underneath it. */
[data-testid="stHeader"]{{padding-left:11rem;padding-right:3.5rem;}}
@media (min-width:920px){{
  /* Streamlit Cloud's toolbar occupies the top-right. Move the pill left of that area
     without moving the toolbar or main menu themselves. */
 .jsa-tip{{margin-right:15rem;}}
}}
@media (min-width:920px) and (max-width:1100px){{
 .jsa-tip{{width:2.25rem;height:2.25rem;min-width:2.25rem;padding:0;
  flex:0 0 2.25rem;margin-right:10.5rem;}}
 .jsa-tip-label{{display:none;}}
}}
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
.jsa-brand{{font-size:19px;font-weight:800;letter-spacing:.3px;
color:#fafafa;text-shadow:0 1px 3px #0e1117;}}
.jsa-tip{{background:#3D95CE;color:#fff;font-weight:600;font-size:13px;
padding:6px 13px;border-radius:8px;text-decoration:none;white-space:nowrap;
display:flex;align-items:center;justify-content:center;gap:.35rem;}}
/* Below 920px a full 197px pill cannot avoid both toolbar variants: local Streamlit
   keeps Deploy/menu at the right edge while Streamlit Cloud moves Fork/GitHub/menu much
   farther left. Keep the same accessible Venmo link as a compact heart in the safe lane
   between them; the title and aria-label retain the full purpose for hover/screen readers. */
@media (max-width:919px){{
 .jsa-tip{{width:2.25rem;height:2.25rem;min-width:2.25rem;padding:0;
  flex:0 0 2.25rem;}}
 .jsa-tip-label{{display:none;}}
}}
@media (min-width:641px) and (max-width:919px){{
 .jsa-tip{{margin-right:9.5rem;}}
}}
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
 visibility:visible;}}
 /* Streamlit's drawer controls are double chevrons (`»` / `«`). Those do not read
    as a menu on a phone. Hide the glyph and draw three bars, the same mark YouTube
    uses for its menu. Open and close share the mark. The button, tap target, and
    label stay. */
 [data-testid="stExpandSidebarButton"],
 [data-testid="stSidebarCollapseButton"],
 [data-testid="stSidebarCollapseButton"] button{{
  position:relative;}}
 [data-testid="stExpandSidebarButton"] *,
 [data-testid="stSidebarCollapseButton"] *{{
  opacity:0;}}
 [data-testid="stExpandSidebarButton"]::after,
 [data-testid="stSidebarCollapseButton"]::after{{
  content:"";position:absolute;left:50%;top:50%;
  width:1.05rem;height:2px;margin:-1px 0 0 -.525rem;
  background:#fafafa;
  box-shadow:0 -.35rem 0 #fafafa, 0 .35rem 0 #fafafa;
  pointer-events:none;}}}}
/* ── Phone header, owned HERE and complete on its own ──────────────────────────────
   This block is the whole phone header contract, not a partial one: mobile.py is the
   page-CONTENT layer and deliberately carries no header rules, so deleting it leaves
   this correct rather than half-applied. Verified standalone down to 320px.
   Below 640px Streamlit collapses the top nav into a drawer. The overlay reserves the
   drawer trigger on the left and Streamlit's main menu on the right. */
@media (max-width:640px){{
 [data-testid="stHeader"]{{padding-left:.25rem;padding-right:.25rem;}}
 #jsa-topbar{{padding-left:3.9rem;padding-right:3.4rem;gap:.4rem;}}
 .jsa-brand{{font-size:13px;letter-spacing:.2px;white-space:nowrap;flex:0 0 auto;}}
 .jsa-tip{{margin-right:5.375rem;}}
 /* The drawer trigger is the only way to change page here — give it a real tap target
    and a surface so the three-bar menu reads as a control. */
 [data-testid="stExpandSidebarButton"]{{min-width:2.25rem;min-height:2.25rem;
  border:1px solid var(--jsa-border, #232D3B);border-radius:var(--jsa-r-sm, 8px);
  background:var(--jsa-surface, #121821);}}
 [data-testid="stSidebarNavLink"]{{min-height:2.6rem;align-items:center;}}
 [data-testid="stSidebarNav"] a span{{font-size:15px;}}}}
@media (max-width:400px){{
 .jsa-brand{{font-size:12px;}}
 .jsa-tip{{width:1.875rem;height:2rem;min-width:1.875rem;margin-right:5.125rem;
  flex-basis:1.875rem;}}}}
</style>
<div id="jsa-topbar">
<span class="jsa-brand">JoScho Analytics</span>
<a class="jsa-tip" href="{_VENMO}" target="_blank" rel="noopener noreferrer"
aria-label="Support JoScho Analytics via Venmo"
title="If you find this useful, buy me a coffee"><span class="jsa-tip-icon"
aria-hidden="true">💙</span><span class="jsa-tip-label">Tip Jar — Venmo @JoScho</span></a>
</div>''',
        unsafe_allow_html=True)


def render_footer():
    """Render public-code and Venmo support actions in normal page flow."""
    st.divider()
    st.caption("This site publishes checked release artifacts. The website code is public.", text_alignment="center")
    with st.container(horizontal=True, horizontal_alignment="center"):
        email_signup.render_button(on_click=send_ga_event, type="tertiary")
        st.link_button(
            "View public code",
            _REPO,
            icon=":material/code:",
            type="tertiary",
            on_click=send_ga_event,
            args=("outbound_github",),
        )
        st.link_button(
            "Support via Venmo",
            _VENMO,
            icon=":material/favorite:",
            type="tertiary",
            on_click=send_ga_event,
            args=("outbound_venmo",),
            help="If you find the site useful, buy me a coffee.",
        )
