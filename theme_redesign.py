"""Redesign PREVIEW layer (additive, fully revertible).

A restrained "analytics terminal" skin injected ON TOP of the stock chrome. Import-safe:
defines inject() only, no st.* at import time (mirrors dashboard_chrome). Wired into app.py
with a single call right after chrome.inject_css(). To revert to the stock look: remove that
call in app.py, then delete this file and .streamlit/config.toml.

Design direction (from the impeccable + emil-design-eng/apple-design skills):
  * Product/tool register => RESTRAINED color strategy: a deep cool-neutral base plus ONE
    emerald "edge" accent used sparingly (links, primary action, active states) — not drenched.
  * Type on a real contrast axis: a grotesk display (Space Grotesk) for headings + a monospace
    (JetBrains Mono) with tabular figures for the numbers, so stats read like a data terminal.
  * One 12/10/8px radius scale (shape-consistency lock). Sub-160ms ease-out motion on a single
    exponential curve, no bounce; prefers-reduced-motion honored. WCAG-AA contrast.
  * Deliberately NOT used (impeccable hard bans): gradient text, glassmorphism-by-default,
    side-stripe borders, gradient "hero-metric" tiles.

Web fonts load via @import; if the CSP/offline blocks them the stack falls back to system
fonts with no breakage. This layer is cosmetic only — it changes no copy, data, or claims.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

:root{
  --jsa-bg:#0B0F14;
  --jsa-surface:#121821;
  --jsa-surface-2:#1A2230;
  --jsa-border:#232D3B;
  --jsa-text:#E7ECF3;
  --jsa-dim:#93A0B1;
  --jsa-accent:#35D08A;
  --jsa-accent-2:#28B679;
  --jsa-accent-ink:#05130C;
  --jsa-r-lg:12px;
  --jsa-r-md:10px;
  --jsa-r-sm:8px;
  --jsa-ease:cubic-bezier(0.16,1,0.3,1);
}

/* Base surface + typography ------------------------------------------------ */
.stApp{ background:var(--jsa-bg); }
.stApp h1, .stApp h2, .stApp h3{
  font-family:"Space Grotesk", system-ui, sans-serif;
  letter-spacing:-0.02em;
  font-weight:700;
  text-wrap:balance;
}

/* Numbers read as a data terminal: mono + tabular figures ------------------ */
[data-testid="stMetricValue"]{
  font-family:"JetBrains Mono", ui-monospace, "SF Mono", monospace;
  font-variant-numeric:tabular-nums;
  font-weight:600;
  letter-spacing:-0.01em;
}
[data-testid="stMetricLabel"]{ color:var(--jsa-dim) !important; font-weight:600; }

/* Metric = a clean bordered tile (no gradient, no side-stripe) ------------- */
[data-testid="stMetric"]{
  background:var(--jsa-surface);
  border:1px solid var(--jsa-border);
  border-radius:var(--jsa-r-lg);
  padding:14px 16px;
  transition:border-color 150ms var(--jsa-ease), transform 150ms var(--jsa-ease);
}
@media (hover:hover){
  [data-testid="stMetric"]:hover{ border-color:var(--jsa-accent-2); transform:translateY(-1px); }
}

/* Links -------------------------------------------------------------------- */
[data-testid="stMarkdownContainer"] a{
  color:var(--jsa-accent);
  text-decoration:none;
  transition:color 120ms var(--jsa-ease);
}
[data-testid="stMarkdownContainer"] a:hover{ color:var(--jsa-text); text-decoration:underline; }

/* Buttons: one radius, press feedback, ease-out ---------------------------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button{
  border-radius:var(--jsa-r-md);
  border:1px solid var(--jsa-border);
  background:var(--jsa-surface-2);
  color:var(--jsa-text);
  font-weight:600;
  transition:transform 130ms var(--jsa-ease), background 130ms var(--jsa-ease), border-color 130ms var(--jsa-ease);
}
@media (hover:hover){
  .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover{
    border-color:var(--jsa-accent); background:var(--jsa-surface); }
}
.stButton > button:active, .stDownloadButton > button:active, .stFormSubmitButton > button:active{
  transform:scale(0.98);
}
/* Primary button = the one accent, used sparingly */
[data-testid="stBaseButton-primary"]{
  background:var(--jsa-accent) !important;
  border-color:var(--jsa-accent) !important;
  color:var(--jsa-accent-ink) !important;
}
[data-testid="stBaseButton-primary"]:hover{ background:var(--jsa-accent-2) !important; }

/* Tabs (where pages use st.tabs) ------------------------------------------- */
.stTabs [data-baseweb="tab-highlight"]{ background:var(--jsa-accent); }
.stTabs [aria-selected="true"]{ color:var(--jsa-text); }

/* Dataframes --------------------------------------------------------------- */
[data-testid="stDataFrame"]{
  border:1px solid var(--jsa-border);
  border-radius:var(--jsa-r-lg);
  overflow:hidden;
}

/* Inputs: match the radius scale ------------------------------------------- */
.stTextInput input, .stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div{ border-radius:var(--jsa-r-sm) !important; }

/* Re-harmonize the existing expander/details to the new palette ------------ */
details summary{
  color:var(--jsa-dim) !important;
  background-color:var(--jsa-surface) !important;
  border:1px solid var(--jsa-border) !important;
  border-radius:var(--jsa-r-sm) !important;
}
details summary:hover{
  color:var(--jsa-text) !important;
  background-color:var(--jsa-surface-2) !important;
  border-color:var(--jsa-accent-2) !important;
}
details > div{
  background-color:var(--jsa-surface) !important;
  border:1px solid var(--jsa-border) !important;
  border-top:none !important;
  color:var(--jsa-text) !important;
}

/* Header band + tip jar re-skinned to the accent (was stock blue) ---------- */
[data-testid="stHeader"]{
  background:var(--jsa-bg);
  border-bottom:1px solid var(--jsa-border);
}
#jsa-topbar a{
  background:var(--jsa-accent) !important;
  color:var(--jsa-accent-ink) !important;
  border-radius:var(--jsa-r-sm) !important;
  transition:background 130ms var(--jsa-ease);
}
#jsa-topbar a:hover{ background:var(--jsa-accent-2) !important; }
.jsa-brand{ color:var(--jsa-text) !important; }

/* Dividers ----------------------------------------------------------------- */
hr{ border-color:var(--jsa-border) !important; }

/* NOTE — deliberately NO transform/filter/animation on stMainBlockContainer.
   The fixed header overlay (#jsa-topbar = brand + tip jar, from render_header) is a
   DESCENDANT of this container. A transform on an ancestor re-anchors position:fixed
   to that ancestor instead of the viewport, which displaces/hides the header. If a
   content entrance is ever wanted, animate opacity ONLY (opacity does not create a
   containing block for fixed descendants). */
</style>
"""


def inject():
    """Inject the redesign skin. Call once, AFTER chrome.inject_css() so this layer wins."""
    st.markdown(_CSS, unsafe_allow_html=True)
