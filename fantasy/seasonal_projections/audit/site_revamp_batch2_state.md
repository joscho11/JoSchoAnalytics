# Site revamp — Batch 2 state-of-work (2026-07-13)

Batch 2 (design Batch B) landed the board rework + DFS; two items are **deferred to a
continuation on budget grounds**, tree left GREEN (72 passed). app.py + its tests untouched.

## Done this session (green)
- **Board rework (4m):** `draft_board_2026.render(use_table=True)` renders the default view via
  `st.table` + pandas Styler (no header-click sort at all); the Sort-by control is the ONLY sort;
  `_sort_board` + its regression test carry over unchanged. Column tooltips relocated **byte-identical**
  into a visible "What each column means" guide via a shared `COLUMN_META` constant (one Python
  string, used by both the legacy `column_config` and the guide). Top-40 default + "Show all"
  expand; full-board CSV export unchanged. app.py's `render()` (default `use_table=False`) is
  byte-behavior-identical — verified by `test_app_draft_board.py` staying green.
- **`page_draft_board.py`:** flagship page (ratified 4d orientation + purpose + pre-season banner
  with `st.page_link`) wrapping the st.table board. `nav_registry.py` added for cross-links.
- **`page_dfs.py`:** DFS "coming soon" body moved byte-identical (stub → real).
- **`dashboard_chrome.render_preseason_banner()`** (ratified 4d.ii, verbatim).
- Tests: `test_board_page.py` (st.table, Top-40/Show-all, sentinels sink, strings intact) added to
  both CI jobs; `test_site_nav.py` still green.

## Deferred to the next session (both need a fresh go)
1. **Help & Guide page (stub → real).** The `app.py` tab7 body is ~436 lines of expanders — a large
   byte-identical extraction. Deferred to avoid a rushed, error-prone copy under low budget. Plan:
   mechanically slice `app.py` lines 2338–2774 into `page_help.py::render()` (strip the `with tab7:`
   indent, verify no shared-local deps), byte-identical; wire `help_pg → page_help.render`; add a
   render harness test. It's currently a clean green STUB, so nothing is broken.
2. **Film Room polish (4d header + archived-card → Draft Board cross-link).** Entangled with the
   app.py-still-live constraint: `film_room.render_film_room` is shared with app.py's tab8, and an
   `st.page_link` to a nav Page can't render in the tab app. So the cross-link + the 4d one-line
   header belong in a `page_film_room` wrapper (like `page_draft_board`) built when app.py is
   retired (Batch 3) or as part of the cross-link pass (design Batch D). Film Room is already wired
   real (Batch 1) with the uniform cards + archive note — no regression, just not yet cross-linked.

## Flags carried forward
- `page_dfs.py` keeps "the Weekly Fantasy **tab**" and "this **tab** will let you" byte-identical —
  stale "tab" wording in a multipage site; a `tab`→`page` copy pass is a separate flagged decision.
- Footer "about the research" line ratified (Batch 1). Board `COLUMN_META` strings are byte-identical
  to the previously-shipped `column_config` help (already fence-cleared).

## Remaining batches (unchanged from design 4k)
- **Batch 3:** Help page (above) + extract the heavy tabs (Weekly Predictions, Track Record, Weekly
  Fantasy, League History) + `compute_hc_stats` extraction + ATS blurb → betting pages + **remove the
  old tab layer/sidebar/banner and swap the entrypoint to `app.py`**.
- **Batch 4:** per-page GA pageviews + `board_view` absorb + cross-links (incl. Film Room) + per-page
  `set_page_config` titles.
