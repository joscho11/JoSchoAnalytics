# U3 betting core — Lens A

- U3A-1 - betting/features.py:681 - _build_coach_win_pct .groupby("coach") raises
  KeyError 'coach' under the LOCAL venv (pandas 3.0.3) only; CI pins pandas==2.3.3
  and CI is green on HEAD; pandas-3 groupby/nth semantics changed - VERDICT: ENV
  DRIFT locally (INFO) + FORWARD RISK (MED) when the pins eventually bump to
  pandas 3.x - RISK - screened T1/T2 (feature list order + trailing space untouched)
  - action: version-stable rewrite AT the next pinned bump WITH pkl md5
  byte-equivalence proof (GATED: model feature path).
- U3A-2 - betting/features.py:466-471 - except Exception -> empty prior-schedule
  frame - a failed schedules load silently degrades coach features (silent-NaN
  class) - LOW - SMELL - screened T1 - action: warning log, GATED (papermill output
  is part of the cron contract).
- calibration.py checked against betting-domain-reference formulas (Wilson,
  BREAKEVEN=0.524, lower-bound-beats-breakeven): correct. dashboard_utils loaders
  are path-injected and tmp-path tested. No tracker/pkl write path outside notebooks.

Coverage: 3/3 files fully read. NO findings >= HIGH (forward pandas-3 risk is MED, gated).
