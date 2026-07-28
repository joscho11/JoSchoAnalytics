# U4 betting execution layer — Lens A (fallback main-context pass; subagent pending)

- U4A-1 - betting/odds_client.py:208 - "df.to_csv(TRACKER, index=False)" - the
  snapshot subcommand fills pick_line/closing_line/clv by REWRITING the ENTIRE
  predictions_tracker.csv in place: no tmp+rename atomicity (contrast
  refresh_board_adp.py:86 which writes tmp first), no pre-write row-count/schema
  assert, full dtype round-trip of all 33 columns - a crash mid-write truncates the
  forward log; a dtype coercion could silently mutate historical rows - HIGH - RISK -
  invariant-screened: T5 (the INTENT is compliant — same rows, reserved columns,
  first-write-wins for pick_line per l.195-196 preserves the CLV baseline; the
  MECHANISM is the risk) - action: atomic write (tmp + os.replace) + row-count and
  column-set asserts before replace. GATED: tracker-adjacent, and the module is
  deliberately unwired until 2026 Week 1 (PRODUCTION_WIRING.md) so there is time to
  fix before first live use.
- U4A-2 - kelly_staking.py kelly_fraction/wilson_lower - verified verbatim against
  the domain-reference formulas (max(0,(p(b+1)-1)/b); Wilson with z=1.96) - correct.
- U4A-3 - odds_client.py:94,97 MIN_BOOKS=3 consensus - de-vig doctrine honored.
- U4A-4 - odds_client.py:148-156 clv_points sign - home-positive when close more
  home-favored than pick; away mirrored - correct under the home-margin convention
  (T3 screened).

Coverage: 7 modules + write-site grep across all; kelly/odds/clv math read in full.
ONE finding of severity HIGH (U4A-1, gated).
