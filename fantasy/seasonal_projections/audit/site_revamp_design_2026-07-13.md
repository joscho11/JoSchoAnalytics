# Site revamp — 8-tab monolith → multipage app (design, 2026-07-13)

**Design only. No code this session.** Goals: (1) a first-time mobile visitor understands the
site in one screen, (2) they stay (fast first paint, cross-links, mobile-first), (3) each page
obviously serves its job. **Mobile-first rule:** every decision below states its narrow-screen
behavior first; desktop is secondary. The funnel audience is mobile TikTok traffic hitting
`/draft-board`.

Automation constraint: the daily `board_refresh.yml` publish commits an overlay to `main`, which
triggers `test.yml`; a red suite would not stop the refresh job itself (it commits before CI runs)
but a broken `main` blocks the *next* deploy. So **every build STOP in this arc must leave the full
suite green** — the migration cannot land half-done on `main`.

---

## 0. Platform mechanics — VERIFIED under the deploy-parity venv (streamlit 1.59.1)

All prototyped against `C:\tmp\parity_venv` (py3.11.9, streamlit **1.59.1**), the cloud-parity
stack — NOT the local 1.58. Findings the build relies on:

- **(3a) `st.navigation` + `st.Page`.** `st.Page(page, title, icon, url_path, default, visibility)`
  and `st.navigation(pages, position, expanded)` both exist. A **grouped dict**
  `{"Fantasy":[...], "Betting":[...], "More":[...]}` with **`position="top"`** constructs and runs.
  `url_path` (kebab), `default=<bool>` (conditional default works — verified pre-season→board,
  in-season→predictions), per-page `title`/`icon` all honored. **Mobile:** `position="top"` renders
  a horizontal nav bar; on narrow widths Streamlit collapses the grouped items into an
  overflow/scrollable menu (the section labels become group headers in the overflow). This must be
  eyeballed on a real phone during build — AppTest can't render the CSS breakpoint. If the top bar
  is too cramped on mobile, the fallback is `position="sidebar"` (hamburger on mobile) — a one-line
  change, flagged as Open Question Q1.
- **(3b) AppTest driving nav.** `at.run()` renders the **default** page; the default is
  env-controllable (the seasonal-default pattern), so tests select a page by setting the default.
  `at.switch_page(path)` needs a **file path** (works for file-based `st.Page("pages/x.py")`, NOT
  function pages). Since our pages are `module.render` callables, the migrated tests use **two
  patterns**: (i) a tiny **per-page harness** script (`import page_x; page_x.render()`) driven by
  `AppTest.from_file(harness)` — the exact shape the current board test already uses; and (ii) an
  **app.py-level** AppTest with the seasonal default forced via env to assert the right landing page.
  Page-switching inside one AppTest is not needed with per-page harnesses.
- **(3c) `st.page_link`.** Exists with `page, label, icon, icon_position, help, use_container_width,
  width, query_params`. Renders fine; **no dedicated AppTest accessor** (`at.page_link` doesn't
  exist) — tests verify cross-links by clean render, not by asserting the element.
- **(3d) Empty sidebar.** With zero `st.sidebar.*` calls, the sidebar renders **no content**
  (`at.sidebar.markdown` count 0). With `position="top"` nav, nothing forces the sidebar open, so
  mobile gets full width — a real first-paint win.
- **(3e) Board via `st.table` + Styler — CONFIRMED VIABLE.** `disp.style.hide(axis="index")
  .format({...}, na_rep="–")` rendered under 1.59.1 with: 180×12, **display strings byte-identical**
  (`gap "–"` ×1, `p50_disp` = `"100 (39th %ile)"`, `eff` `Rookie` ×14 / `–` ×18), **index hidden**.
  So the st.table baseline (4m) works — the HTML-table fallback is NOT needed. **Length:** 180 rows
  render as one static block (~7,000+ px tall on a phone) with **no scroll box** — this is the
  mobile problem 4m must solve with a default row-cap.
- **(3f) Per-page `st.set_page_config`.** A page function calling `st.set_page_config(page_title=…,
  page_icon=…)` renders without error under nav — so each page can carry its own title/icon for
  clean link-preview on shared deep links. Entrypoint sets a site default; pages override.

---

## 4a. Page inventory & thin entrypoint

Current `app.py` is **2,777 lines**. Tab bodies (verified line ranges) → page modules, each a
`render()` module mirroring the existing `draft_board_2026.render()` / `film_room.render_film_room()`
pattern:

| Current tab (app.py lines) | New page module | render fn |
|---|---|---|
| Weekly Predictions (524–963) | `page_weekly_predictions.py` | `render()` |
| Track Record (964–1386) | `page_track_record.py` | `render()` |
| Weekly Fantasy (1387–1706) | `page_weekly_fantasy.py` | `render()` |
| DFS Optimizer (1707–1741) | `page_dfs.py` | `render()` |
| Draft Board (1745–1759) | **`draft_board_2026.py`** (exists) | `render()` |
| League History (1761–2337) | `page_league_history.py` | `render()` |
| Help & Guide (2338–2774) | `page_help.py` | `render()` |
| Film Room (2775–2777) | **`film_room.py`** (exists) | `render_film_room()` |

**Shared setup currently at module top (1–163, plus helpers):** imports; `_OFFLINE`;
`st.set_page_config`; the GA helper block (`_utm_params`, `_send_ga_event`, `track_pageview`,
secrets read, pageview fire 84–86); the global CSS `st.markdown` (88–134); the data loads
(`_load_tracker_cached`→`df`, `totals_df`, `_calib`, `_compute_hc_stats`); `_MODE_BADGE_COLORS`.
The **offseason banner (498–514)** and the **`st.tabs` line (519)** and **`st.sidebar` block
(425–461)** all go away.

**Thin `app.py` entrypoint spec (target ≈ 60–90 lines):**
1. imports + `_OFFLINE` + `sys.path` inserts.
2. `st.set_page_config` (site default title/icon, `layout="wide"`).
3. `import dashboard_chrome` (new shared module — GA helpers, CSS, footer) and
   `dashboard_data` (new shared module — cached loaders); call the CSS injector.
4. GA per-page pageview (4f).
5. Build the `st.Page(...)` list (4b) with the **seasonal conditional default** (4c).
6. `nav = st.navigation({...}, position="top"); nav.run()`.
7. `dashboard_chrome.render_footer()` **after** `nav.run()` so the footer is on every page (4e).
No tab bodies, no sidebar, no banner logic inline (banner moves into the two flagship pages, 4d.ii).

---

## 4b. Nav structure (groups, labels, icons, order, url_path)

`st.navigation({...}, position="top")`. Order chosen mobile-first: **Fantasy first** (the funnel
lands on the board), Betting second, More last. Group + page order:

| Group | Page (nav label) | icon | url_path | notes |
|---|---|---|---|---|
| **Fantasy** | Draft Board | 📋 | **`draft-board`** (FIXED — funnel deep link) | flagship; pre-season default |
| | Weekly Fantasy | 🏆 | `weekly-fantasy` | |
| | DFS Optimizer | 🎯 | `dfs-optimizer` | "coming soon" page today |
| **Betting** | Weekly Predictions | 🏈 | `weekly-predictions` | flagship; in-season default |
| | Track Record | 📈 | `track-record` | |
| **More** | Film Room | 📺 | `film-room` | |
| | League History | 🏅 | `league-history` | |
| | Help & Guide | ❓ | `help` | |

**Mobile nav behavior:** the top bar shows the 8 items grouped; on a phone the row overflows into a
scrollable/▾-menu (verified the API; exact collapse is a CSS breakpoint to eyeball on-device). Group
labels (Fantasy/Betting/More) give the overflow menu structure. Because there's no sidebar, the nav
is the only chrome — first paint is the nav + the landing page, full width.

---

## 4c. Seasonal default page (single source of truth)

Reuse `refresh_board_adp.SEASON_START` (default `date(2026,9,4)`, env `BOARD_REFRESH_SEASON_START`)
— do NOT define a second date. The entrypoint imports it:

```
from refresh_board_adp import SEASON_START           # single source of truth
import os; from datetime import date
_ss = date.fromisoformat(os.environ.get("BOARD_REFRESH_SEASON_START", SEASON_START.isoformat()))
_preseason = date.today() < _ss
board_page = st.Page(draft_board_2026.render, title="Draft Board", icon="📋",
                     url_path="draft-board", default=_preseason)
wp_page    = st.Page(page_weekly_predictions.render, title="Weekly Predictions", icon="🏈",
                     url_path="weekly-predictions", default=not _preseason)
```
Before SEASON_START the site lands on the **Draft Board** (the live, daily-refreshing funnel target);
on/after, it lands on **Weekly Predictions**. `default` is a plain bool per `st.Page`, verified.
A deep link to any `url_path` overrides the default (visitor lands where the link points). **Mobile:**
identical — the default only sets the landing page, nav is unchanged.

---

## 4d. NEW PUBLIC COPY (DRAFTS — ratify; first-person; fence-scanned)

All strings below are **drafts for Joseph's ratification**. Board/fantasy copy scanned against the
fantasy-board fence (no buy/sell/fade/steal/reach/target/tier/valued/accuracy/hit-rate/lock/
guaranteed/must-draft/sleeper-pick/player-level claims); betting copy uses its own honest ATS/tier
vocabulary (out of the fantasy fence).

**i. Site orientation (one line; shown small under the nav on the two flagships):**
> "I build machine-learning models for NFL betting and fantasy, run them live, and show my work —
> the numbers, the honest track record, and the code on my GitHub."

**Draft Board page-purpose (top of `/draft-board`):**
> "My pre-season draft board: the market's price for each player paired with a calibrated range I
> built around it — refreshed daily from live draft data."

**Weekly Predictions page-purpose (top of `/weekly-predictions`):**
> "My model's call against the Vegas spread for every game this week, with an honest confidence
> tier and the reasoning behind each one. Break-even is 52.4%."

**ii. Seasonal banner rework (keyed on SEASON_START; kills the "using the sidebar" line):**
- **Pre-season variant** (before SEASON_START), shown at the top of Weekly Predictions (and as a
  small pointer on the board):
  > "🏈 The {next_season} season hasn't kicked off yet. My **2026 Draft Board** is live and
  > refreshing daily from the latest draft data — jump in below. Weekly predictions return at Week 1."
  With a `st.page_link` to `/draft-board`.
- **In-season / concluded-season variant** (carries the current offseason message's job, minus the
  sidebar line):
  > "🏈 The {current_season} season has concluded.{demo_hint} Weekly predictions return when the
  > {next_season} season kicks off in September."

**iii. One-line purpose headers (top of each other page):**
- Weekly Fantasy: "My weekly half-PPR projections for every skill player — with the actual results
  filled in once games are played."
- DFS Optimizer: "A DraftKings lineup optimizer built on my weekly projections. Launching with the
  2026 season."
- Track Record: "Every graded pick, by confidence tier and week — wins, losses, and profit at
  standard odds. Nothing hidden."
- Film Room: "Short model-backed breakdowns, each with the full written analysis behind it."
- League History: "Load any Sleeper league to see its standings and season-by-season records."
- Help & Guide: "What each part of the site is, how the models work, and how to read the numbers."

---

## 4e. Sidebar retirement + shared footer

Remove all four `st.sidebar.*` calls (logo 426, divider 427, tip jar 429, ATS blurb 451). Replace
with a **shared footer** in `dashboard_chrome.render_footer()`, rendered on every page **after**
`nav.run()` so it sits in the normal page flow (mobile sees it by scrolling the page, not by opening
a drawer they never open on a phone):

- **Tip jar** — the Venmo button, moved into the footer flow (centered, same styling). **Mobile:**
  visible at the end of every page instead of buried in a collapsed sidebar. An outbound-click GA
  event fires on it (4f) so the relocation's effect is measurable.
- **ATS blurb** ("ML model since 2014 … 52.4% ATS break-even") — moves to the **Betting pages only**
  (Weekly Predictions + Track Record page bodies), not the global footer; it's betting-specific.
- **Logo** (`assets/logo.svg`) — disposition proposed: put a **small logo + wordmark in the footer**
  (and optionally a compact one above the nav on the entrypoint). It should not eat vertical space
  above the fold on mobile; the nav is the primary identity. Recommend footer-only.
- **"About the research" repo link (PROPOSAL — ratify, not a decision):** a one-line footer link to
  the public GitHub repo ("The models and code behind this are public → github.com/joscho11/…").
  Reinforces the credibility angle; only ship if Joseph wants the repo surfaced from the site.

---

## 4f. GA per-page spec

- **Pageview per page:** fire `page_view` once **per page per session** — key session_state on the
  page's `url_path` (`ga_pv_<url_path>`), so navigating between pages logs distinct pageviews (today
  the whole app is one pageview). `page_location = CANONICAL_URL + "/" + url_path`;
  `page_title = "<Page title> | JoScho Analytics"`. UTM forwarding via `_utm_params()` **preserved**
  (still read from the landing URL). Guarded by `not _OFFLINE and GA creds`.
- **`board_view` event — ABSORB into pageviews (recommended).** With real per-page pageviews, the
  `/draft-board` pageview already measures board visits far more accurately than today's
  `board_view` (which fired for anyone who loaded the app because `st.tabs` executed every tab body).
  Drop the bespoke `board_view` event; the `draft-board` pageview replaces it. (Alternative: keep it
  as a redundant funnel marker — not recommended, it double-counts.)
- **Outbound tip-jar click event:** wire a `tip_jar_click` GA event on the footer Venmo link so the
  sidebar→footer relocation is measurable. Because it's an external `<a>`, use a lightweight
  approach: render the link with a GA measurement-protocol beacon is not possible from pure HTML, so
  fire the event from a small `st.button`-backed "Copy my Venmo" or wrap with a query-param
  round-trip — **Open Question Q2** (see 4l) on the exact mechanism; recommend a button that both
  reveals the link and logs the event.
- **Per-page `page_title`/`page_icon`** via each page's `st.set_page_config` (3f) for clean shared-
  link previews.

---

## 4g. Cross-link map (`st.page_link`)

Minimum set (all `st.page_link(target_page, label=…, icon=…)`, targets are the `st.Page` objects
built in the entrypoint — pass them into pages or a shared registry):

| From | To | Where / label |
|---|---|---|
| Film Room archived BTJ card | Draft Board | in the archive note's card: "For what I publish today → Draft Board" (the note already says this; make it a link) |
| Draft Board | Track Record | footer of the board: "See my betting track record →" |
| Track Record | Draft Board | inline: "Pre-season? See the Draft Board →" |
| Weekly Predictions (flagship) | Help & Guide | "New here? How to read these →" |
| Draft Board (flagship) | Help & Guide | "How to read this board →" (complements the how-to expander) |
| Pre-season banner | Draft Board | the `page_link` in 4d.ii |

Mechanic: page objects live in the entrypoint; expose them via a small `nav_registry` module (or
pass into each `render(pages=…)`) so pages can link without importing the entrypoint (avoids a
circular import). No AppTest accessor for page_link — tests assert clean render only.

---

## 4h. COPY FREEZE LIST (must move byte-identical during extraction)

Extraction **never rewrites** these; any change to them outside 4d is a separate flagged decision.

- **Draft Board:** the whole `draft_board_2026.py` copy — the "How to read this board" expander,
  the worked-example block, the `_adp_caption()` strings, the sort-control caption, the "About these
  numbers" footer, every `column_config` **help tooltip string** (these relocate verbatim into the
  visible guide per 4m), the population/badge/plain-label strings, and the licensed `signal_status`
  wording (already frozen in the CSV; never re-authored).
- **Film Room:** the archive note (`video_content.py` `archive_note`), titles, subtitles, the intro
  `about` blurb, all `video_breakdowns/*.md`.
- **Help & Guide:** the entire tab7 body (2338–2774) — every expander's text.
- **Weekly Predictions / Track Record / Weekly Fantasy / DFS:** all existing captions, the DFS
  "coming soon" block (1714–1725), metric labels, the totals "tracking only — do not bet" banner,
  the calibration/"covered X%" card lines.
- **The betting ATS blurb** (455–457) moves verbatim to the betting pages.
- Rule: the ONLY user-facing strings that may change this arc are the **new** 4d copy and the
  **removal** of the stale "using the sidebar" line (498–514). Everything else is frozen.

---

## 4i. Shared-state extraction plan

Because pages load **independently** (function pages called by `nav.run()`, no shared entrypoint
locals passed in), all shared data must come from **cached shared helpers**:

- New **`dashboard_data.py`**: move the cached loaders here, each `@st.cache_data`:
  `load_predictions()` (wraps `dashboard_utils.load_tracker(_HERE)`, ttl 300),
  `load_totals()`, `load_calibration(df)`, `compute_hc_stats(...)`. Pages call these directly; the
  cache means loading in each page is cheap (one read per TTL, shared across pages/sessions).
- New **`dashboard_chrome.py`**: the GA helpers (`_send_ga_event`, per-page pageview), the CSS
  injector (the 88–134 `st.markdown` block — call once per run from the entrypoint), `render_footer()`.
- **Module-import side effects to fix:** today `app.py` runs data loads, the GA pageview, and
  `st.error/st.stop` **at import**. In the multipage app these must run **inside** `render()` /
  entrypoint flow, never at module import — a page module imported for its `render` symbol must not
  fire network/data work on import. Each page's `render()` calls the cached loader and handles the
  empty/missing-tracker `st.error`+`st.stop` locally (so one missing file degrades that page, not
  the whole site).
- **`APP_OFFLINE` guard carried into every page:** each page that would touch the network (Weekly
  Predictions/Track Record via nflreadpy live actuals, League History via Sleeper, GA) checks
  `_OFFLINE` exactly as today. Centralize `_OFFLINE = os.environ.get("APP_OFFLINE")=="1"` in
  `dashboard_chrome` and import it, so no page re-derives it inconsistently.

---

## 4j. Test migration map

| Existing test | Covers | Migrated form |
|---|---|---|
| `test_app_draft_board.py::test_draft_value_2026_tab_renders_and_filters` | full-app render, board columns, filters, caption, default Gap-desc | Re-point to a **board page harness** (`AppTest.from_file(_board_harness)` calling `draft_board_2026.render()`), OR keep app.py-level with the seasonal default forced to the board via env. Drop the `at.tabs` assertion (no tabs); keep column/filter/caption/default-order asserts. Update for st.table (4m): assert the rendered **table** element (not dataframe) and the relocated column-guide text. |
| `test_app_draft_board.py::test_board_sort_is_numeric_and_sentinels_sink` | `_sort_board` numeric sort + sentinels | **Unchanged** — imports `draft_board_2026` directly; carries over as-is. `_sort_board` stays the only sort. |
| `test_dashboard_utils.py` (10) | pure helpers | **Unchanged** (imports `dashboard_utils`, not app.py). |
| `test_draft_board.py` (15), `test_seasonal_projections.py` (7) | seasonal modules | **Unchanged** (no app.py dependency). |
| `betting/test_features.py` (15), `test_calibration.py` (16) | feature contract, calibration | **Unchanged**. |
| **NEW** filter-independence test | Season/Week controls are per-page & independent | New per-page harnesses for Weekly Predictions / Track Record / Weekly Fantasy: assert each renders its own `wp_/tr_/wf_` keys and no sidebar widgets. |
| **NEW** nav/landing test | seasonal default lands on the right page | app.py AppTest with `BOARD_REFRESH_SEASON_START` env set both sides of the boundary; assert the default page title. |
| **NEW** film room render | archived card + uniform layout + cross-link | `film_room` harness render, assert archive note present + page_link renders clean. |

`test.yml`: the `pytests` job's **explicit file list** must add the new page-harness test files and
the new nav/landing test (keep explicit-list discipline — never auto-discover). The `deploy-parity`
job (py3.12 + `requirements.txt`) picks them up automatically since it lists the same files. No new
deps (streamlit already pinned 1.59.1). **Hermetic/offline:** every new page harness sets
`APP_OFFLINE=1` and asserts zero network, exactly as the board test does today.

---

## 4k. Build plan (Sessions 2–3), STOPs, risks, rollback

**Batch order** (each batch = its own session-or-stop, suite GREEN before handing back):

- **Batch A — scaffolding, no page moves yet.** Create `dashboard_data.py` + `dashboard_chrome.py`
  (extract cached loaders, GA, CSS, footer). Build the thin entrypoint with `st.navigation` and
  **temporary thin pages that still call the existing tab code paths** (or wrap the current app as
  one page) to prove nav + default + footer + empty sidebar render green. STOP, suite green.
- **Batch B — extract the two already-modular pages + the simple ones.** Draft Board (4m rework:
  st.table + column guide) and Film Room are near-drop-in; add DFS (tiny) and Help (static). Wire
  the seasonal default and the new flagship copy (4d). STOP, suite green (board test migrated).
- **Batch C — extract the heavy tabs.** Weekly Predictions, Track Record, Weekly Fantasy, League
  History into their page modules; move the ATS blurb to betting pages; per-page filters already
  independent (done in the prior arc) so they lift cleanly. Delete the old tab scaffolding, sidebar,
  banner. STOP, suite green + full AppTest of every page.
- **Batch D — GA per-page + cross-links + polish.** Per-page pageviews, tip-jar event, page_link
  map, per-page set_page_config titles. STOP, suite green.

**Risks & mitigations:**
- **Copy drift** — enforce the 4h freeze list; extraction is move-only; diff each moved string.
- **Bot-commit interaction mid-arc** — `board_refresh.yml` commits `board_adp_live_2026.csv` daily
  to `main`. If a build batch is mid-flight on `main`, a bot commit could interleave. Mitigation:
  do the arc on a **branch**, merge each green batch; the refresh only touches the overlay CSV (no
  overlap with the page files), so conflicts are near-zero, but the branch keeps `main` deployable
  throughout. (Joseph commits/merges.)
- **GA regression** — per-page pageviews change the analytics shape; keep `CANONICAL_URL` + UTM
  forwarding identical; validate one event in the GA debug view before relying on it.
- **st.table mobile length** — mitigated by 4m's default row-cap; validate on-device.
- **Nav mobile cramping** — Q1 fallback to `position="sidebar"`.

**Rollback:** the whole arc lands as a branch merged in batches; the single-commit revert target is
the merge commit (or each batch's merge). Because the frozen data + `_sort_board` + refresh pipeline
are untouched, a revert restores the tab app with zero data risk. Keep the old `app.py` tab bodies
in git history (the extraction deletes them from tip only).

---

## 4l. Open questions (each with a recommendation)

- **Q1 — Nav position on mobile.** `position="top"` per the brief; if on-device it's cramped with 8
  items, fall back to `position="sidebar"` (hamburger). **Recommend:** ship `top`, eyeball on a
  phone in Batch A, switch only if it's bad.
- **Q2 — Tip-jar outbound-click tracking.** A plain `<a>` can't fire a GA measurement-protocol event
  on click. **Recommend:** a footer `st.button("💙 Tip jar — Venmo @JoScho")` that fires the
  `tip_jar_click` event and then reveals/links the Venmo URL (`st.link_button` beneath, or
  `st.markdown` link), so the click is measurable. If Joseph prefers a pure link (no event), keep the
  current `<a>` and drop the event.
- **Q3 — "About the research" repo link (4e).** Ship the public-repo footer link or not? **Recommend:**
  yes — it reinforces the credibility angle the channel leads with; one line, low risk.
- **Q4 — Logo placement (4e).** Footer-only vs a compact mark above the nav. **Recommend:** footer-only
  to protect mobile above-the-fold; revisit if the site feels unbranded.

---

## 4m. BOARD RENDERING (direction ruled — implementation design)

Header-click sorting is removed; the board's default view leaves `st.dataframe`. **Baseline
(confirmed viable in 3e): `st.table` + pandas Styler.** Implementation:

- Build `disp = view[cols]`; render `disp.style.hide(axis="index").format({adp_half_ppr:"{:.1f}",
  adp_pos_rank:"{:.0f}", proj_pos_rank:"{:.0f}", p10:"{:.0f}", p90:"{:.0f}", top12_pct:"{:.0f}%"},
  na_rep="–")` via `st.table`. Verified: display strings (`gap_disp`, `p50_disp`, `eff_disp`) pass
  through byte-identical, index hidden, no header-click sort exists on `st.table`.
- **The Sort-by + Order control stays the ONLY sort** (`_sort_board` + its regression test carry
  over unchanged). Remove the `db26_grid_*` remount key and the "clicking a column header…" caveat
  line from the caption (no headers to click anymore) — that caveat removal is the one sanctioned
  copy change here, tied to the ruled direction.
- **Column tooltips → visible guide (byte-identical relocation).** Every `column_config` help string
  moves into a single **"What each column means"** section merged with the existing "How to read this
  board" expander — one honesty surface, readable on mobile (hover tooltips never worked on touch).
  The strings move verbatim (4h freeze). Recommend rendering it as a definition list (bold column
  name → its former tooltip text) inside the same expander, expanded by default on first paint.

**180-row length answer (mobile-first) — RECOMMENDATION: default position filter + full via control.**
A single static 180-row st.table is ~7,000px on a phone. Options weighed: (a) top-N with "show all"
expander, (b) advanced-view split, (c) **default to a single position**. Recommend **(c) + a "Top 40
overall" default toggle**:
- On first paint (mobile), the board defaults to **one position** (RB — highest-interest, or the
  position with the most rows) OR a **"Top N by current sort" cap (default N=40)** with a "Show all
  180" toggle. Recommend the **Top-N cap** as the default (N=40 ≈ 3–4 rounds, the draftable core),
  because it's position-agnostic and respects the active sort, with an explicit "Show all 180"
  toggle for desktop/power users. The position multiselect stays as the primary filter above it.
- **Mobile:** first paint = 40 rows (~1,600px, a reasonable scroll) sorted Gap-desc; the visitor can
  expand or filter. **Desktop:** same default, one click to full.
- **CSV download unchanged:** always exports the **full 180-row** board regardless of the on-screen
  cap or filter (the download reads the full sorted `view`, not the capped display).

**Fallback (only if 3e had failed — it did not):** a custom static HTML table via `st.html` with a
CSS `max-height`+`overflow:auto` scroll box and no sorting. Not needed (st.table works); documented
cost if ever required: hand-rolled theme-aware CSS, manual cell formatting, no Styler — higher
maintenance. **Not** a revert to `st.dataframe`.

---

*End of design. Build begins at Batch A (4k) in a fresh session on a branch; Joseph ratifies the
4d copy and Q1–Q4 first.*
