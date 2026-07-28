# U3 betting core — Lens B

- Shares U3A-1 (env-drift verdict; the local suite's two known failures are this one
  item) and U3A-2 (silent fallback). Determinism: no unseeded RNG in features.py
  (pure deterministic transforms). CI coverage: test_features (15) + test_calibration
  (16) in both CI jobs.

Coverage: 3/3. NO FINDINGS of severity >= HIGH.
