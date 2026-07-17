# U1 fantasy/talent — Lens B (robustness/ops)

- U1B-1 - config.py:57 WORK="C:/tmp/talent_build"; archive_rho.py:27-34 hardcoded
  user/scratchpad paths - machine-specific; checkpoint-dependent tests pytest.skip on
  a fresh clone - MED - RISK - screened T9 - action: env-var override for WORK
  (GATED: build behavior path).
- U1B-2 - .github/workflows/test.yml: zero hits for "talent" - fantasy/talent/tests/
  (26 tests incl. golden regressions) + test_app_talent_columns.py (4, incl. the H7
  fence + all-tabs AppTest) run in NO CI job - HIGH - TEST-GAP - screened T6 (explicit
  lists are deliberate; that is exactly why an explicit ADD is needed, not discovery) -
  action: add both to the pytests job and deploy-parity lists; note: checkpoint-
  dependent tests will skip in CI, static/schema/lint/fence tests still run. GATED
  (CI file list is a must-not-mutate this session).
- U1B-3 - build_rookie_score.py load_college(): network fetch of 2025 college data on
  cache miss - non-hermetic build dependency, documented in code - LOW - RISK - T9.

Coverage: 11/11. ONE finding of severity HIGH (U1B-2, gated).
