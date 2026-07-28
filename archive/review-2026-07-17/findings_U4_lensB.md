# U4 betting execution layer — Lens B (fallback main-context pass; subagent pending)

- U4B-1 - the 26 execution-layer tests are NOT in CI (known gap) - risk assessment:
  moderate-low TODAY because the layer is unwired (nothing calls it in the weekly
  cron); becomes HIGH the day PRODUCTION_WIRING.md executes - MED - TEST-GAP -
  action: add the 5 test files to CI in the same change that wires the layer
  (GATED, CI list).
- U4B-2 - documented sys.path import fragility (modules must run from betting/) -
  LOW - RISK - known, documented in COUNCIL_REVIEW_HANDOFF §7 - no action now.
- U4B-3 - odds_client snapshot path: non-atomic tracker rewrite = the ops half of
  U4A-1 (same finding, robustness face) - see lens A.

Coverage: as Lens A. NO NEW findings >= HIGH beyond U4A-1.
