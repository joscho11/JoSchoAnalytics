"""Mobile/responsive layer (additive, fully revertible).

Injected LAST — after chrome.inject_css(), theme_redesign.inject() AND
chrome.render_header() — so it wins the cascade on plain specificity. That ordering is
deliberate and lives in app.py: render_header emits its own <style>, so an earlier
injection point (the original arrangement) lost to it and needed !important on every
header rule to claw the win back. The !important that remains in this file is beating
Streamlit's own emotion classes, never our header.

Everything here lives inside `@media (max-width:640px)` — exactly Streamlit's own
column-stacking breakpoint (`theme.breakpoints.columns`, verified in the shipped bundle).
Above 640px this file changes nothing.

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
  3. Metric tiles ran 4-deep down the page; they now sit 2-up.
  4. Chart annotations, the analyst-note grid, tap targets, table height and type scale
     (see the individual sections below).

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

/* ── 5. Tabs: 4-6 tabs overflow a phone. Let them scroll, quietly. ───────── */
.stTabs [data-baseweb="tab-list"]{
  overflow-x:auto !important;
  scrollbar-width:none;
  -webkit-overflow-scrolling:touch;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{ display:none; }
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

/* ── 9b. Film Room card header — the ONE fixed-height container we release ─
   film_room.py builds each card's title block with st.container(height=130) purely to
   line the video embeds up ACROSS a row of three. On a phone the cards stack one per
   row, so it aligns nothing and just leaves ~70px of dead space above every embed (and
   would clip a title that wrapped). Let it size to its content instead.
   SCOPED BY KEY, deliberately: this rule used to match ANY explicitly sized container
   on the site, which would silently release a future scroll box that wanted its height.
   film_room passes key="jsa-filmroom-card-<id>", which Streamlit renders as an
   `st-key-…` class — the officially supported hook.
   The height is carried by BOTH the layout wrapper and the vertical block inside it,
   so releasing only one changes nothing, and Streamlit pins the size with
   `flex: 0 0 130px` as well — in a flex column the basis IS the main size, so
   releasing `height` alone would do nothing at all. */
[class*="st-key-jsa-filmroom-card"],
[class*="st-key-jsa-filmroom-card"] [data-testid="stVerticalBlock"][height]{
  height:auto !important;
  max-height:none !important;
  overflow:visible !important;
  flex:0 0 auto !important;
}

/* ── 10. Metric tiles ─────────────────────────────────────────────────────
   min-height keeps a tile with a sub-line the same height as one without, so the
   two-up grid reads as a grid instead of a ragged pair. */
.jsa-mcard{ padding:10px 12px !important; min-height:4.9rem; }
.jsa-mcard .jsa-mcard-label{ font-size:9.5px !important; letter-spacing:.5px !important; }
.jsa-mcard .jsa-mcard-value{ font-size:18px !important; }
.jsa-mcard .jsa-mcard-sub{ font-size:11.5px !important; }

}  /* end phones */


/* ══════════════════════════════════════════════════════════════════════════
   :has()-SCOPED LAYOUT RULES — isolated on purpose.
   A browser without :has() drops these blocks whole and simply keeps today's
   stacked layout; it must never take a neighbouring rule down with it.
   ══════════════════════════════════════════════════════════════════════════ */

/* 8a. Only the game-card rows stay horizontal. Streamlit forces
   min-width:calc(100% - 2rem) on every column below 640px; these rows opt out. */
@media (max-width: 640px){
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-stat),
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-hdr),
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-bet){
    flex-wrap:nowrap !important;
    gap:.3rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-stat) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-hdr)  > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(.jsa-gc-bet)  > [data-testid="stColumn"]{
    min-width:0 !important;
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
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard),
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]):not(:has([data-testid="stDataFrame"])){
    flex-wrap:wrap !important;
    gap:.45rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .jsa-mcard) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]):not(:has([data-testid="stDataFrame"])) > [data-testid="stColumn"]{
    min-width:calc(50% - .225rem) !important;
    flex:1 1 calc(50% - .225rem) !important;
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


/* Narrow phones (<=400px) are handled entirely in render_header alongside the rest of
   the header contract — see the note at section 1. */


/* 641px-767px needs nothing from THIS file. Streamlit still serves the nav from the
   drawer there, but the header keeps its desktop 11rem left padding, so the `»` lands
   at x~194 — well clear of the brand — and columns do not stack until 640px. The two
   things that WERE broken in that band, the tip-jar/`⋮` overlap and the drawer
   swallowing taps, are both fixed in render_header (right inset + z-index) because they
   are equally broken on desktop; fixing them here would have left desktop untouched. */
</style>
"""


def inject():
    """Inject the mobile layer. Call once, LAST, so it wins over the other skins."""
    st.markdown(_CSS, unsafe_allow_html=True)
