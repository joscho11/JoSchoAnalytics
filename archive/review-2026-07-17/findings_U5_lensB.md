# U5 dashboard — Lens B

- U5B-1 - CLAUDE.md vs reality - the app is now an st.Page MULTIPAGE app (app.py 70
  lines; page_*.py files; test_site_nav/test_board_page/test_betting_pages/
  test_fantasy_league_pages/test_help_page in CI) while CLAUDE.md still describes a
  monolithic ~167KB 8-tab app.py and the old joschoanalytics.streamlit.app URL - MED -
  DOCS-DRIFT - screened vs the architecture skill's own staleness ledger - action:
  dead-claim URL correction is safe-fix-eligible; the full dashboard-section rewrite
  is owner scope (GATED-docs).
- U5B-2 - 59 unsafe_allow_html sites (page_weekly_predictions 28, page_track_record
  17, others few) - representative audit: all render self-built constant/style
  strings or formatted numbers; only external HTML is TikTok's oEmbed payload
  (film_room, from TikTok's API, cached, pre-existing accepted pattern) - LOW -
  RISK - no action.

Coverage: as Lens A. NO FINDINGS of severity >= HIGH.
