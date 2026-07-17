# U7 infra — Lens B

- U7B-1 = U1B-2 (talent tests absent from every CI job) - HIGH - TEST-GAP - GATED
  (CI file list). Deduplicated in the ledger.
- U7B-2 - test.yml runs pytests on py3.11+requirements-test AND a deploy-parity job
  on py3.12+requirements.txt (added by the 2026-07-12 audit) - deliberate and
  healthy - INFO.
- U7B-3 - CLAUDE.md dead claims: "deployed at joschobetting.streamlit.app" (live app
  is joschoanalytics.streamlit.app per app config); monolithic-app description;
  "GitHub Actions (Mon/Thu/Sun)" cron claim (actual crons Tue/Thu/Sun; the bot has
  never committed) - LOW-MED - DOCS-DRIFT - the URL is a dead-claim correction
  (safe-fix-eligible per cowork-docs-and-writing); the larger rewrite is owner scope.
- U7B-4 - fantasy/talent/tests/golden/golden_ruled.json is committed but read by no
  test (pre-split orphan; live goldens are golden_facets/golden_weighted) - LOW -
  SMELL - removal is an owner call (committed artifact).

Coverage: full. ONE finding of severity HIGH (dedup of U1B-2).
