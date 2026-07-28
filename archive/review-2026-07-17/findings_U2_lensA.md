# U2 seasonal_projections + draft_board — Lens A

- U2A-1 - draft_board_2026.py:213-214 - ternary inside an &-chain for qb_rookie -
  evaluates correctly (parenthesized) but fragile to edit - LOW - SMELL - screened
  T3/T4 (display negation + value-board guards untouched) - action: none now; note
  for the next deliberate board change.
- Roster/overlay re-verified: phase4_band is the only row source (l.104,113); the
  overlay maps exactly 3 price/rank columns (l.118-123); no row addition/removal —
  consistent with the static-roster ruling. SORT_KEYS all numeric (T-board honored).

Coverage: draft_board_2026.py fully read; seasonal build + closed H-scripts
taxonomy-grepped (ddof use is internally consistent z-scoring inside closed research
scripts, not product paths) + spot-read. NO FINDINGS of severity >= HIGH.
