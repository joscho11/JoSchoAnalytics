"""Mobile/responsive layer (additive, fully revertible).

Injected LAST — after chrome.inject_css(), theme_redesign.inject() AND
chrome.render_header() — so it wins the cascade on plain specificity. That ordering is
deliberate and lives in app.py: render_header emits its own <style>, so an earlier
injection point (the original arrangement) lost to it and needed !important on every
header rule to claw the win back. The !important that remains in this file is beating
Streamlit's own emotion classes, never our header.

Everything here lives inside `@media (max-width:640px)` except the labeled-scatter
swap: a `min-width:641px` rule hides the unlabeled phone copy so desktop never
shows two charts. Above 640px that is the only rule that fires.

SCOPE: page CONTENT only. Every header/nav rule — bar insets, brand and tip-jar sizing
and wrapping, the drawer trigger's tap target, drawer row heights, the collapse control,
and the tablet/desktop `⋮` clearance — belongs to render_header in dashboard_chrome.py.
That split is why the revert below is safe: there is exactly one owner per surface, so
removing this file cannot leave the header half-styled.

To revert: delete the `mobile.inject()` call in app.py, then delete this file. The marker
classes it keys on (`jsa-*`) are inert everywhere else, and the header stays correct —
verified by rendering with this stylesheet removed from the DOM down to 320px.

What it fixes, measured on a 390x844 phone viewport before the change:

  1. NAVIGATION WAS UNREACHABLE. Below 768px Streamlit collapses the top nav into a
     drawer behind the `»` button, which renders at x=26..54 inside the header. The
     fixed `#jsa-topbar` brand span sat at x=18..140 with pointer-events:auto and
     covered it, so no nav link could be tapped and the brand wrapped onto two lines
     across the button. The bar is now indented past both the `»` and Streamlit's `⋮`.
  2. GAME CARDS FELL APART. st.columns stacks below 640px, so each card became
     "SPREAD / PREDICTED / SCORE" as three orphan header rows followed by unlabeled
     full-width boxes. The card rows are pinned back to a real row via :has() scoping —
     only those rows, so every other stacked layout keeps stacking.
  3. Metric tiles ran 4-deep down the page; they now sit 2-up. Native metric
     values wrap on phones so player and manager names are not ellipsized.
     League History All-Time Leaderboard cards stay paired and equal-height.
  4. Chart annotations, the analyst-note grid, tap targets, table height and type scale
     (see the individual sections below).
  5. League History: rivalry cards stacked, tabs show a drag bar, radios wrap,
     Plotly does not steal vertical scroll, the Load button is full-width.
     Labeled scatters drop on-chart names on phones (tap the point). Desktop keeps names.

`:has()` rules are kept in their own blocks on purpose: one unsupported selector
invalidates an entire selector list, so a browser without :has() must degrade to
today's layout rather than dropping a neighbouring rule with it.
"""
import streamlit as st

_CSS = """
<style>
/* ══════════════════════════════════════════════════════════════════════════
   PHONES  (<= 640px — Streamlit's own column-stacking breakpoint)
   ══════════════════════════════════════════════════════════════════════════ */
@media (max-width: 640px){

/* ── 1. Header — deliberately NOT here ────────────────────────────────────
   The whole phone header contract (bar insets, brand/pill sizing and wrapping, the
   drawer trigger's tap target, drawer row heights) lives in dashboard_chrome's
   render_header, so that header is correct standing alone and deleting this file
   leaves it whole rather than half-applied. This file is the page-CONTENT layer. */

/* ── 2. Page frame ────────────────────────────────────────────────────────
   4rem of top padding is tuned to the desktop nav band; the mobile header is
   60px and the content only needs to clear it. Side padding buys usable width. */
[data-testid="stMainBlockContainer"]{
  padding-top:4.25rem !important;
  padding-left:.85rem !important;
  padding-right:.85rem !important;
  padding-bottom:2rem !important;
}

/* ── 3. Type scale — 2.75rem headings burn three lines on a 390px screen ── */
.stApp h1{ font-size:1.65rem !important; line-height:1.2 !important; }
.stApp h2{ font-size:1.3rem  !important; line-height:1.25 !important; }
.stApp h3{ font-size:1.1rem  !important; line-height:1.3 !important; }
.stApp h4{ font-size:1rem    !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{
  font-size:.78rem !important; line-height:1.55 !important;
}
[data-testid="stAlertContainer"] p{ font-size:.88rem !important; line-height:1.5 !important; }

/* ── 4. Tap targets ───────────────────────────────────────────────────────
   The <details> "Matchup Analysis" trigger and the dataframe toolbar buttons
   are 28px / 22px tall by default. */
details summary{
  min-height:2.25rem !important;
  display:flex !important;
  align-items:center !important;
  font-size:12px !important;
  padding:6px 12px !important;
}
[data-testid="stBaseButton-elementToolbar"]{ min-width:2rem !important; min-height:2rem !important; }
/* Streamlit's own `⋮` is deliberately left at its native 28px: growing it pushes its
   box under the tip jar, and it is app chrome rather than site navigation. */

/* ── 5. Tabs: 4-6 tabs overflow a phone. Show a drag bar so swipe is obvious. */
.stTabs [data-baseweb="tab-list"]{
  overflow-x:auto !important;
  scrollbar-width:thin;
  scrollbar-color:rgba(231,236,243,.55) rgba(255,255,255,.14);
  -webkit-overflow-scrolling:touch;
  touch-action:pan-x;
  padding-bottom:.55rem !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{
  display:block !important;
  height:6px !important;
  background:transparent;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-track{
  background:rgba(255,255,255,.14);
  border-radius:99px;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-thumb{
  background:rgba(231,236,243,.55);
  border-radius:99px;
}
.stTabs [data-baseweb="tab"]{ padding-left:.7rem !important; padding-right:.7rem !important; }

/* ── 6. Charts ────────────────────────────────────────────────────────────
   The Plotly modebar is hover-only on a mouse but permanently visible on touch,
   where it lands on top of the plot and none of its tools are usable. */
.js-plotly-plot .modebar{ display:none !important; }

/* ── 7. Tables — see the :has() section below (needs sibling scoping) ───── */

/* ── 8. Game cards (Weekly Predictions) — pinned back to real rows ──────── */
.jsa-gc-hdr{ font-size:8.5px !important; letter-spacing:.3px !important; white-space:nowrap; }
.jsa-gc-stat{ font-size:13px !important; }
.jsa-gc-team{ font-size:13px !important; }
.jsa-gc-bet{
  font-size:11px !important;
  letter-spacing:0 !important;
  padding:0 4px !important;
}
.jsa-gc-meta{ font-size:11.5px !important; line-height:1.5 !important; }
/* The totals badge is a flex row of five spans; let it wrap instead of squeezing. */
.jsa-tot-badge{ flex-wrap:wrap; gap:4px !important; font-size:11.5px !important; padding:6px 9px !important; }

/* Legend chips + the historical-cover-rate line */
.jsa-legend{ gap:6px !important; }
.jsa-legend span{ font-size:10.5px !important; }
.jsa-calib{ font-size:10.5px !important; line-height:1.6 !important; }

/* ── 9. Agent-analysis pairs (Weekly Fantasy) ───────────────────────────── */
.jsa-ff-pair{ gap:6px !important; }
/* The cards are equal-height flex boxes with space-between, which on a narrow column
   opens a big void between the player's name and the reason. Pack them to the top. */
.jsa-ff-pair > div{ padding:8px 10px !important; justify-content:flex-start !important; }
/* The <br> between the name and the reason is its own flex item in a column card, so
   it contributes a whole empty line box. A margin says the same thing in less space. */
.jsa-ff-pair > div > br{ display:none !important; }
.jsa-ff-pair > div > span:last-child{ margin-top:6px; }
.jsa-ff-pair b{ font-size:12.5px; }
.jsa-ff-head{ padding:7px 9px !important; }
.jsa-ff-head span{ font-size:10px !important; letter-spacing:.2px !important; }

/* ── 9b. Film Room ───────────────────────────────────────────────────────
   Section pills and an episode select sit above one player. Widget chrome
   lives in film_room.py (`jsa-filmroom-picker`). */

/* ── 10. Metric tiles ─────────────────────────────────────────────────────
   min-height keeps a tile with a sub-line the same height as one without, so the
   two-up grid reads as a grid instead of a ragged pair.
   Streamlit renders metric text with truncate:true (nowrap + ellipsis). Combined
   with JetBrains Mono on a 2-up phone tile, "Joshua Palmer" becomes "josh…".
   Kill truncate, drop mono, wrap the full name. Leaderboard cards also wrap on
   desktop so a long manager name or a two-name tie stays inside the tile. */
.jsa-mcard{ padding:10px 12px !important; min-height:4.9rem; }
.jsa-mcard .jsa-mcard-label{ font-size:9.5px !important; letter-spacing:.5px !important; }
.jsa-mcard .jsa-mcard-value{ font-size:18px !important; }
.jsa-mcard .jsa-mcard-sub{ font-size:11.5px !important; }
[data-testid="stMetric"]{
  min-width:0 !important;
  height:auto !important;
  overflow:visible !important;
  padding:10px 10px !important;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] *,
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] *,
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] *{
  white-space:normal !important;
  overflow:visible !important;
  text-overflow:unset !important;
  word-break:break-word !important;
  overflow-wrap:anywhere !important;
  max-width:100% !important;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] *{
  line-height:1.25 !important;
}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] *{
  font-family:"Space Grotesk", system-ui, sans-serif !important;
  font-size:1rem !important;
  line-height:1.2 !important;
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] *{
  font-size:.72rem !important;
  line-height:1.35 !important;
}

/* Hall of Fame matchup line sits in Streamlit's capsule delta. Wrapping the
   text without growing the capsule left names hanging off the grey oval. */
[class*="st-key-jsa-lh-hof-cards"] [data-testid="stMetricDelta"]{
  display:block !important;
  width:100% !important;
  max-width:100% !important;
  box-sizing:border-box !important;
  height:auto !important;
  flex-shrink:1 !important;
  white-space:normal !important;
  overflow:hidden !important;
  border-radius:8px !important;
  padding:.35rem .5rem !important;
}
[class*="st-key-jsa-lh-hof-cards"] [data-testid="stMetricDelta"] *{
  display:block !important;
  width:100% !important;
  max-width:100% !important;
  box-sizing:border-box !important;
  white-space:normal !important;
  overflow:hidden !important;
  word-break:break-word !important;
  overflow-wrap:anywhere !important;
}

/* ── 12. League History ───────────────────────────────────────────────────
   Custom HTML cards, long inner tabs, horizontal radios, and Plotly heatmaps
   are the pieces the shared metric/table rules do not cover. */
.jsa-lh-card{ padding:12px !important; }
.jsa-lh-card-row{
  flex-direction:column !important;
  gap:8px !important;
}
.jsa-lh-score{ text-align:left !important; }
.jsa-lh-score > div:last-child{ font-size:24px !important; }
.jsa-lh-card-copy > div:first-child{ font-size:16px !important; }
.jsa-lh-legend{ gap:6px !important; }
.jsa-lh-legend span{ font-size:10.5px !important; padding:6px 9px !important; }
.jsa-lh-series{ font-size:1.15rem !important; }

[data-testid="stRadio"] [role="radiogroup"]{
  flex-wrap:wrap !important;
  row-gap:.4rem !important;
}
[data-testid="stButtonGroup"]{
  flex-wrap:wrap !important;
  max-width:100% !important;
  row-gap:.35rem !important;
}
[data-testid="stSelectbox"],
[data-testid="stSelectbox"] > div{
  max-width:100% !important;
}
[data-testid="stFormSubmitButton"] button{
  min-height:2.75rem !important;
}
[class*="st-key-jsa-scatter-desktop"],
[class*="st-key-jsa-table-desktop"],
[class*="st-key-jsa-st-high-desktop"]{
  display:none !important;
}
[class*="st-key-db26_detail"]{
  display:none !important;
}
[data-testid="stPlotlyChart"]{
  max-width:100% !important;
  overflow-x:auto !important;
  -webkit-overflow-scrolling:touch;
}
/* League Matrix: keep the page at phone width and pan the grid. Plotly
   stretch was packing 12 teams into ~360px; the phone figure is ~60px/cell. */
[class*="st-key-jsa-scatter-phone-league-matrix"]{
  max-width:100% !important;
  overflow-x:auto !important;
  -webkit-overflow-scrolling:touch;
  overscroll-behavior-x:contain;
}
[class*="st-key-jsa-scatter-phone-league-matrix"] [data-testid="stVerticalBlock"],
[class*="st-key-jsa-scatter-phone-league-matrix"] [data-testid="stElementContainer"],
[class*="st-key-jsa-scatter-phone-league-matrix"] [data-testid="stFullScreenFrame"]{
  max-width:100% !important;
  overflow-x:auto !important;
}
[class*="st-key-jsa-scatter-phone-league-matrix"] [data-testid="stPlotlyChart"],
[class*="st-key-jsa-scatter-phone-league-matrix"] .js-plotly-plot,
[class*="st-key-jsa-scatter-phone-league-matrix"] .plot-container,
[class*="st-key-jsa-scatter-phone-league-matrix"] .svg-container{
  min-width:56rem !important;
  max-width:none !important;
  width:max-content !important;
}
.stTabs [data-baseweb="tab-list"]{
  flex-wrap:nowrap !important;
}
.stTabs [data-baseweb="tab"]{
  white-space:nowrap !important;
  flex:0 0 auto !important;
}

/* Home start-here cards stay 2-up on a phone and clip the CTA ("Open the Draft E…").
   Stack them so the full page_link label is tappable. Explore links wrap instead
   of squeezing six items into one row. */
[class*="st-key-jsa-home-start"] [data-testid="stHorizontalBlock"]{
  flex-direction:column !important;
  flex-wrap:nowrap !important;
  gap:.7rem !important;
}
[class*="st-key-jsa-home-start"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
[class*="st-key-jsa-home-start"] [data-testid="stHorizontalBlock"] > [data-testid="stElementContainer"]{
  width:100% !important;
  max-width:100% !important;
  min-width:0 !important;
}
[class*="st-key-jsa-home-explore"],
[class*="st-key-jsa-help-start"]{
  flex-wrap:wrap !important;
  row-gap:.4rem !important;
}
[class*="st-key-jsa-home-explore"] [data-testid="stPageLink-NavLink"],
[class*="st-key-jsa-home-explore"] a,
[class*="st-key-jsa-help-start"] [data-testid="stPageLink-NavLink"],
[class*="st-key-jsa-help-start"] a{
  white-space:nowrap !important;
}

}  /* end phones */


/* ══════════════════════════════════════════════════════════════════════════
   :has()-SCOPED LAYOUT RULES — isolated on purpose.
   A browser without :has() drops these blocks whole and simply keeps today's
   stacked layout; it must never take a neighbouring rule down with it.
   ══════════════════════════════════════════════════════════════════════════ */

/* 8a. Game-card rows stay one row, on a shared grid so headers sit on the
   numbers. Streamlit forces min-width:calc(100% - 2rem) below 640px, which
   used to stack SPREAD / PREDICTED / SCORE into unlabeled full-width boxes.
   The pick pill is hidden on phones: the recommended team is already bold. */
@media (max-width: 640px){
  [class*="st-key-jsa-gc"]{
    --jsa-gc-cols: minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr);
  }
  [class*="st-key-jsa-gc"]:has(.jsa-gc-scored){
    --jsa-gc-cols: minmax(0,1.35fr) repeat(3,minmax(0,.85fr));
  }
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-stat),
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-hdr){
    display:grid !important;
    flex-wrap:unset !important;
    align-items:center !important;
    gap:.35rem !important;
    grid-template-columns: var(--jsa-gc-cols) !important;
  }
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-stat) [data-testid="stColumn"],
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-hdr) [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    overflow:visible !important;
    padding:0 !important;
    box-sizing:border-box !important;
  }
  [class*="st-key-jsa-gc"] [data-testid="stColumn"]:has(.jsa-gc-pick){
    display:none !important;
  }
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-hdr) [data-testid="stMarkdownContainer"] p,
  [class*="st-key-jsa-gc"] [data-testid="stHorizontalBlock"]:has(.jsa-gc-stat) [data-testid="stMarkdownContainer"] p{
    margin:0 !important;
  }
  .jsa-gc-hdr{
    letter-spacing:0 !important;
    overflow:visible !important;
    white-space:normal !important;
  }
  .jsa-gc-stat{
    box-sizing:border-box !important;
    width:100% !important;
    min-width:0 !important;
    overflow:visible !important;
  }
  .jsa-gc-team{
    white-space:normal !important;
    overflow:visible !important;
    height:auto !important;
    min-height:32px !important;
    display:flex !important;
    align-items:center !important;
    padding-top:0 !important;
    overflow-wrap:anywhere !important;
  }
  .jsa-gc-meta{
    overflow:visible !important;
    white-space:normal !important;
    overflow-wrap:anywhere !important;
  }
}

/* 9a. Keep the OUTPERFORM / UNDERPERFORM headers paired with the two-column
   card grid underneath them, which is raw CSS grid and does not stack. */
@media (max-width: 640px){
  [data-testid="stHorizontalBlock"]:has(.jsa-ff-head){
    flex-wrap:nowrap !important;
    gap:.375rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(.jsa-ff-head) > [data-testid="stColumn"]{
    min-width:0 !important;
  }
}

/* 10a. Metric tiles two-up instead of a four-deep stack. Rows that also carry a
   dataframe are excluded — those columns need the full width. */
@media (max-width: 640px){
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard){
    display:grid !important;
    flex-wrap:unset !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    grid-auto-rows:1fr !important;
    align-items:stretch !important;
    gap:.45rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    padding:0 !important;
    display:flex !important;
    flex-direction:column !important;
    overflow:visible !important;
    box-sizing:border-box !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) [data-testid="stVerticalBlock"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) [data-testid="stElementContainer"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) [data-testid="stMarkdownContainer"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) [data-testid="stMarkdownContainer"] p{
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
    height:auto !important;
    overflow:visible !important;
    width:100% !important;
    max-width:100% !important;
    margin:0 !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) .jsa-mcard{
    flex:1 1 auto !important;
    min-height:100% !important;
    height:auto !important;
    overflow:visible !important;
    display:flex !important;
    flex-direction:column !important;
    box-sizing:border-box !important;
    margin-bottom:0 !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) .jsa-mcard-label,
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) .jsa-mcard-value,
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) .jsa-mcard-sub{
    overflow:visible !important;
    white-space:normal !important;
    overflow-wrap:anywhere !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) .jsa-mcard-sub{
    margin-top:auto !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]):not(:has([data-testid="stDataFrame"])){
    flex-wrap:wrap !important;
    gap:.45rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]):not(:has([data-testid="stDataFrame"])) > [data-testid="stColumn"]{
    min-width:calc(50% - .225rem) !important;
    flex:1 1 calc(50% - .225rem) !important;
    overflow:visible !important;
  }
}

/* Season Totals hero: those three metric labels wrap into unreadability in a
   2-up tile ("One-sided 95% Wilson lower"). Stack them full-width on a phone.
   Desktop keeps the three-across row. */
@media (max-width: 640px){
  [class*="st-key-jsa-st-hero"] [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]){
    display:flex !important;
    flex-direction:column !important;
    flex-wrap:nowrap !important;
    gap:.45rem !important;
  }
  [class*="st-key-jsa-st-hero"] [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"]{
    min-width:100% !important;
    flex:1 1 auto !important;
    max-width:100% !important;
    overflow:visible !important;
  }
  [class*="st-key-jsa-st-high-phone"] [data-testid="stMarkdownContainer"] p{
    margin:0 0 .4rem 0 !important;
    font-size:.92rem !important;
    line-height:1.35 !important;
  }
  [class*="st-key-jsa-st-ladder"] [data-testid="stDataFrame"],
  [class*="st-key-jsa-st-ladder"] [data-testid="stFullScreenFrame"]{
    max-width:100% !important;
    overflow-x:auto !important;
  }
}

/* 10b-desktop. Leaderboard is 4-up. Streamlit columns default min-width:auto,
   so a long name or a two-name tie runs off the tile. Grid + minmax(0,1fr)
   lets the value wrap inside the card. pre-line keeps a stacked two-name tie.
   Stretch wrappers to 1fr so a longer label does not drop that card's bottom
   border below the rest of the row. */
@media (min-width: 641px){
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){
    display:grid !important;
    grid-template-columns:repeat(4, minmax(0, 1fr)) !important;
    grid-auto-rows:1fr !important;
    gap:.45rem !important;
    align-items:stretch !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    flex:none !important;
    display:flex !important;
    padding:0 !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stElementContainer"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stFullScreenFrame"]{
    width:100% !important;
    height:100% !important;
    min-height:0 !important;
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"]{
    flex:1 1 auto !important;
    height:100% !important;
    min-height:8.25rem !important;
    display:flex !important;
    flex-direction:column !important;
    box-sizing:border-box !important;
    overflow:visible !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"] > div{
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
    height:100% !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"] > div > div:has([data-testid="stMetricDelta"]){
    margin-top:auto !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricValue"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricValue"] *{
    white-space:pre-line !important;
    overflow:visible !important;
    text-overflow:unset !important;
    overflow-wrap:anywhere !important;
    word-break:break-word !important;
    max-width:100% !important;
    width:100% !important;
    font-family:"Space Grotesk", system-ui, sans-serif !important;
    font-size:clamp(0.75rem, 1.1vw, 1rem) !important;
    line-height:1.15 !important;
  }
}

[class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"],
[class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"] p,
[class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"] li{
  font-size:.85rem !important;
  color:var(--jsa-dim, #93A0B1) !important;
  line-height:1.45 !important;
}
[class*="st-key-jsa-lh-leaderboard-ties"] ul{
  margin:.2rem 0 0 1.15rem !important;
  padding:0 !important;
}

/* 10b. Leaderboard + Report Cards scorecards: even 2-up pairs, reserved
   label band, delta at the bottom. Leaderboard is eight cards in two rows
   of four, so mobile 2-up wrapping stays even. */
@media (max-width: 640px){
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){
    align-items:stretch !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"]{
    flex:0 0 calc(50% - .225rem) !important;
    max-width:calc(50% - .225rem) !important;
    min-width:0 !important;
    display:flex !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricValue"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricValue"] *{
    white-space:pre-line !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stColumn"] > [data-testid="stVerticalBlock"]{
    width:100% !important;
    height:100% !important;
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stMetric"]{
    flex:1 1 auto !important;
    height:100% !important;
    min-height:8.25rem !important;
    display:flex !important;
    flex-direction:column !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stMetric"] > div{
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
    height:100% !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stMetricLabel"]{
    min-height:2.6rem !important;
  }
  :is(
    [class*="st-key-jsa-lh-leaderboard-cards"],
    [class*="st-key-jsa-lh-report-cards"]
  ) [data-testid="stMetric"] > div > div:has([data-testid="stMetricDelta"]){
    margin-top:auto !important;
  }
}

/* 10b-phone. Leaderboard 2-up: same wrapper-stretch as Report Cards. The
   consolation-finals label is three lines on a ~160px tile; flex 50% let
   that one card's bottom drop. Grid 1fr plus a reserved label band keeps
   pairs even. Wrap labels at spaces, not mid-word. */
@media (max-width: 640px){
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){
    display:grid !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    grid-auto-rows:1fr !important;
    align-items:stretch !important;
    gap:.45rem !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    flex:none !important;
    display:flex !important;
    padding:0 !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stElementContainer"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stFullScreenFrame"]{
    width:100% !important;
    height:100% !important;
    min-height:0 !important;
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"]{
    flex:1 1 auto !important;
    height:100% !important;
    min-height:11.25rem !important;
    display:flex !important;
    flex-direction:column !important;
    box-sizing:border-box !important;
    overflow:visible !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"] > div{
    display:grid !important;
    grid-template-rows:3.9rem minmax(1.7rem,auto) 1fr !important;
    flex:1 1 auto !important;
    height:100% !important;
    min-height:0 !important;
    width:100% !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricLabel"],
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricLabel"] *{
    min-height:3.9rem !important;
    align-content:start !important;
    font-size:.7rem !important;
    line-height:1.2 !important;
    overflow-wrap:break-word !important;
    word-break:normal !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricValue"]{
    min-height:1.7rem !important;
    display:flex !important;
    align-items:flex-end !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetric"] > div > div:has([data-testid="stMetricDelta"]){
    width:100% !important;
    max-width:100% !important;
    min-height:2.6rem !important;
    margin-top:auto !important;
    display:flex !important;
    align-items:stretch !important;
    align-self:end !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricDelta"]{
    display:flex !important;
    align-items:center !important;
    width:100% !important;
    max-width:100% !important;
    min-height:2.6rem !important;
    box-sizing:border-box !important;
    border-radius:8px !important;
    flex-shrink:1 !important;
    white-space:normal !important;
    overflow:hidden !important;
  }
  [class*="st-key-jsa-lh-leaderboard-cards"] [data-testid="stMetricDelta"] *{
    white-space:normal !important;
    overflow-wrap:anywhere !important;
  }
  [class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"],
  [class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"] p,
  [class*="st-key-jsa-lh-leaderboard-ties"] [data-testid="stMarkdownContainer"] li{
    font-size:.78rem !important;
    overflow-wrap:anywhere !important;
    word-break:break-word !important;
  }
  [class*="st-key-jsa-lh-leaderboard-ties"] ul{
    margin:.1rem 0 0 1rem !important;
    padding:0 !important;
  }
}

/* 10d. Report Cards: 2x2 equal cells. Streamlit wraps each metric in
   stElementContainer, so height:100% on stMetric never saw a stretched
   parent and label/value/delta stacked to their own text. Grid the row,
   stretch the wrappers, pin the three metric bands. */
@media (max-width: 640px){
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){
    display:grid !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    grid-auto-rows:1fr !important;
    align-items:stretch !important;
    gap:.45rem !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    flex:none !important;
    display:flex !important;
    padding:0 !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stElementContainer"],
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stFullScreenFrame"]{
    width:100% !important;
    height:100% !important;
    min-height:0 !important;
    display:flex !important;
    flex-direction:column !important;
    flex:1 1 auto !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetric"]{
    flex:1 1 auto !important;
    height:100% !important;
    min-height:10.75rem !important;
    display:flex !important;
    flex-direction:column !important;
    box-sizing:border-box !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetric"] > div{
    display:grid !important;
    grid-template-rows:3.1rem minmax(1.7rem,auto) 1fr !important;
    flex:1 1 auto !important;
    height:100% !important;
    min-height:0 !important;
    width:100% !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetricLabel"]{
    min-height:3.1rem !important;
    align-content:start !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetricValue"]{
    min-height:1.7rem !important;
    display:flex !important;
    align-items:flex-end !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetric"] > div > div:has([data-testid="stMetricDelta"]){
    width:100% !important;
    max-width:100% !important;
    min-height:3rem !important;
    margin-top:auto !important;
    display:flex !important;
    align-items:stretch !important;
    align-self:end !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetricDelta"]{
    display:flex !important;
    align-items:center !important;
    width:100% !important;
    max-width:100% !important;
    min-height:3rem !important;
    box-sizing:border-box !important;
    border-radius:8px !important;
    flex-shrink:1 !important;
    white-space:normal !important;
    overflow:hidden !important;
  }
  [class*="st-key-jsa-lh-report-cards"] [data-testid="stMetricDelta"] *{
    white-space:normal !important;
    overflow-wrap:anywhere !important;
  }
}

/* 10c. Hall of Fame matchup pill: the parent row is inline-flex and will not
   stretch the grey box unless it is a full-width block. */
@media (max-width: 640px){
  [class*="st-key-jsa-lh-hof-cards"] [data-testid="stMetric"] > div > div:has([data-testid="stMetricDelta"]){
    display:block !important;
    width:100% !important;
    max-width:100% !important;
    overflow:hidden !important;
    flex-shrink:1 !important;
  }
}

/* 10e. Filter toolbars: two-up instead of a four-deep stack. */
@media (max-width: 640px){
  [class*="st-key-jsa-filter-bar"] [data-testid="stHorizontalBlock"]{
    display:grid !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    gap:.45rem !important;
  }
  [class*="st-key-jsa-filter-bar"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    padding:0 !important;
  }
  [class*="st-key-jsa-metric-even"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]),
  [class*="st-key-jsa-metric-even"] [data-testid="stHorizontalBlock"]:has(.jsa-mcard){
    display:grid !important;
    flex-wrap:unset !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    grid-auto-rows:1fr !important;
    align-items:stretch !important;
    gap:.45rem !important;
  }
  /* Keyed horizontal containers ARE the flex row (Anytime TDs, Weekly Predictions,
     DFS). The descendant rule above only fires when metrics sit in nested columns. */
  [class*="st-key-jsa-metric-even"]:has(> [data-testid="stElementContainer"] [data-testid="stMetric"]){
    display:grid !important;
    flex-wrap:unset !important;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
    grid-auto-rows:1fr !important;
    align-items:stretch !important;
    gap:.45rem !important;
  }
  [class*="st-key-jsa-metric-even"] [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"],
  [class*="st-key-jsa-metric-even"] [data-testid="stHorizontalBlock"]:has(.jsa-mcard) > [data-testid="stColumn"]{
    min-width:0 !important;
    max-width:none !important;
    width:auto !important;
    flex:none !important;
    padding:0 !important;
    display:flex !important;
    flex-direction:column !important;
    align-items:stretch !important;
    overflow:visible !important;
    box-sizing:border-box !important;
  }
  [class*="st-key-jsa-metric-even"]:has(> [data-testid="stElementContainer"] [data-testid="stMetric"]) > [data-testid="stElementContainer"]{
    min-width:0 !important;
    width:auto !important;
    max-width:none !important;
    flex:none !important;
  }
  [class*="st-key-jsa-metric-even"] [data-testid="stElementContainer"],
  [class*="st-key-jsa-metric-even"] [data-testid="stMarkdownContainer"]{
    min-width:0 !important;
    width:100% !important;
    max-width:100% !important;
    height:auto !important;
    overflow:visible !important;
  }
  [class*="st-key-jsa-metric-even"] .jsa-mcard{
    height:auto !important;
    min-height:100% !important;
    width:100% !important;
    box-sizing:border-box !important;
    margin-bottom:0 !important;
    overflow:visible !important;
  }
}

/* 7a. Long tables. The shared TABLE_HEIGHT is 735px — 87% of an 844px phone screen,
   so a table became a full-screen scroll trap you had to fight past to reach the rest
   of the page. max-height (not height) caps the tall ones at ~26rem while leaving the
   short auto-height tables untouched; the grid re-measures off its container box, so
   it renders the right number of rows and keeps scrolling internally.
   The height is carried by three nested boxes — grid, full-screen frame and element
   container — and all three have to be capped or the page keeps the old 735px gap.
   Fullscreen is excluded: that frame is position:fixed and must fill the screen. */
@media (max-width: 640px){
  [data-testid="stElementContainer"]:has(> [data-testid="stFullScreenFrame"] > [data-testid="stDataFrame"]),
  [data-testid="stFullScreenFrame"]:has(> [data-testid="stDataFrame"]),
  [data-testid="stFullScreenFrame"]:has(> [data-testid="stDataFrame"]) > [data-testid="stDataFrame"]{
    max-height:26rem !important;
  }
  /* Fullscreen escape. Streamlit only swaps an emotion-hash class when a frame goes
     fullscreen, which is not something CSS can rely on, but its toolbar button's
     aria-label flips "Fullscreen" -> "Close fullscreen". That is the stable signal. */
  [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"]),
  [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"]) > [data-testid="stDataFrame"]{
    max-height:none !important;
  }
}

/* 11. Spacer columns (the [1,3] and [1,2,1] centering wrappers) each become a
   full-width empty row once stacked. Collapse them. */
@media (max-width: 640px){
  [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"]:empty){ display:none !important; }
}


/* Labeled scatters: hide the unlabeled phone copy on desktop. Paired with the
   max-width 640 hide of the named copy inside the phones block above. */
@media (min-width: 641px){
  [class*="st-key-jsa-scatter-phone"],
  [class*="st-key-jsa-table-phone"],
  [class*="st-key-jsa-st-high-phone"]{ display:none !important; }
}

/* Narrow phones (<=400px) are handled entirely in render_header alongside the rest of
   the header contract — see the note at section 1. */


/* 641px-767px: the unlabeled scatter copy stays hidden (rule above). Nothing else
   in this file applies there. Streamlit still serves the nav from the drawer, but
   the header keeps its desktop 11rem left padding, so the `»` lands at x~194. */
</style>
"""


def inject():
    """Inject the mobile layer. Call once, LAST, so it wins over the other skins."""
    st.markdown(_CSS, unsafe_allow_html=True)
