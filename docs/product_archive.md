# Product route pause

`anytime-tds` (Touchdown Props) and `college-basketball` (Daily predictions) are temporarily paused on the public site. The routes show a pause notice with a link Home; they do not render archived predictions. Their page code, artifacts, odds history, grading, and internal tests remain in place.

## Restore

`nav_registry.ARCHIVED_PAGES` is the central set of paused slugs. Removing either slug restores its normal route, navigation entry, and gated Home, This Week, and Help promotions. Before restoring a route, verify its data, model inputs, prices, season/week context, and public-facing copy are fresh and ready. The pause is not evidence that a product is ready to resume.

## TD odds logging and publication boundary

Weekly TD odds logging continues privately through the existing `td_count_model_beta/live/2026_weekNN_<slate>.csv` contract. Preserve the original pasted sportsbook captures and actual capture timestamps. Keep the existing `season`, `week`, `kickoff_et`, `snapped_at_et`, `book`, `player`, `team`, `opponent`, and `yes_amer` columns, plus supplied `first_amer` and `two_plus_amer` prices. For another capture of the same slate, use a distinct capture suffix within `<slate>`; never overwrite an earlier paste or replace its actual `snapped_at_et`. Preserve the original pasted text or screenshot alongside the normalized input in the existing private capture locations. Flag ambiguous, missing, or conflicting player/market prices in the handoff; do not guess or silently normalize them. Route pausing does not change historical grading.

Logging stops before `publish_live_week.py`, release activation, or `freeze-first-td-v3`. A separate request to resume predictions is required to cross that boundary. Do not create new predictions, picks, or public releases as part of maintaining the odds log.

## Validation and rollback

Validate locally with `APP_OFFLINE=1`: run navigation/AppTest coverage, the TD and CBB module tests, and the visual regression suite. Confirm both old URLs show only the pause notice and Home link at phone, tablet, and desktop sizes, while unaffected navigation and Home still work. Keep weekly TD odds logging and grading tests passing. A human reviews and pushes repository changes. To undo this change completely, revert its scoped commit. To resume one product later, remove its slug from `nav_registry.ARCHIVED_PAGES`; the route and gated promotions restore together. Repeat local validation and freshness checks before any public release.
