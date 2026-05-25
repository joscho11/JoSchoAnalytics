---
name: bettingedge-model-experiments-2026-05
description: Rejected model-improvement experiments (weather, ensemble re-weighting, consensus filter removal, ULTRA tier) — all proven not worth shipping
metadata:
  type: project
---

In late May 2026 we ran a series of model-improvement experiments on BettingEdge.
**All of them were rejected** after empirical testing. Future contributors (including future-me) should not re-run these without strong reason — the negative findings are documented in CLAUDE.md's Completed Work entries dated 2026-05-24.

## What did NOT work

### 1. Weather features (temp_f / wind_mph from Meteostat)
- Built a complete kickoff-hour weather CSV (`betting/nfl_weather_2014_2025.csv`, 99.96% coverage)
- Tested adding `temp_f` + `wind_mph` to PROD_FEATURES_35
- **Result:** all 5 models flat or worse in walk-forward CV (XGBoost -0.7pp, RF -1.0pp)
- **Why it failed:** Vegas already prices weather into spreads; rolling EPA / coach win% / AllPro features already implicitly capture weather effects; wind affects totals not spreads
- **Artifacts preserved:** the weather CSV + `betting/experiments/fetch_weather.py` remain on disk for potential future use (a totals model, where wind has real signal)

### 2. Ensemble weight retuning (XGB+Ridge sweep, XGB+LGBM, 3-way blends)
- Tested sweep of 7 XGB+Ridge weights (0.50 → 0.90), 4 XGB+LGBM variants, 5 three-way blends, plus Ridge meta-learner stack
- **Result:** all variants within statistical noise (~0.3-0.5pp on n=855) of current 0.75 XGB + 0.25 Ridge production. The "best" variants were not distinguishable from baseline at the High-tier sample size (SE ~2.8pp on n=238)
- **LightGBM in the blend HURTS** — every XGB+LGBM variant underperformed XGB+Ridge by 1-2pp. LightGBM's role belongs in the consensus tier (direction voting), not in the predicted-margin blend
- **The 0.75 weight is essentially optimal** within noise. Don't retune it.

### 3. Dropping the consensus filter from tiering
- Test set (855 games) showed consensus filter adds ~0pp average across edge cutoffs (verified empirically)
- Removed it → re-evaluated on live 2025 (117 games) → MEDIUM tier dropped from 59.5% to 56.5% (~3pp, within SE but real direction)
- **Conclusion:** for production with real money implications, the live data signal trumps the test set's null result. The consensus filter stays. The 855-game test set is statistically more reliable in theory, but live 2025 is the only truly OOS sample for production-trained pkls (mc test set has 2024 in-sample).

### 4. ULTRA tier (|edge| ≥ 5pt)
- Test set showed 82% ATS on n=73 (8.5% of games) at ≥5pt cutoff — looked promising
- Live 2025 reality: only **2 games** hit the threshold across 7 weeks. Most weeks have zero ULTRA picks.
- **Tier labels that fire 0.3 times/week aren't useful for staking decisions or UX.** Drop.

## What is established about this codebase

- **The model is ~at ceiling.** ATS gains from retuning XGB+Ridge weights, adding weather, or restructuring tiers are all within statistical noise on available samples. Spend effort elsewhere.
- **Vegas already prices in the obvious factors.** Any feature with strong univariate correlation to home_margin is likely already in the spread.
- **What ACTUALLY moves the business needle is execution, not model tuning:**
  - Closing line value (CLV) tracking — leading indicator of long-term profit
  - Multi-book line shopping — 2-5% implied edge improvement per bet
  - Kelly fractional sizing — concentrates bankroll on highest-edge picks
  - Totals model — independent edge stream from spread model
  - Player props model — lower-efficiency market, higher edge potential
- The "Model is 10% / Execution is 90%" lesson applies. The 56.4% live ATS is approximately what this model architecture can deliver; further gains come from infrastructure around the model, not the model itself.

## How to apply

- **Don't re-run ensemble weight tuning** unless you have a meaningfully different model architecture to mix in. The current 0.75 XGB + 0.25 Ridge is empirically optimal within noise.
- **Don't add weather features to spread prediction.** It doesn't help. If building a totals model in the future, the weather data is ready to use.
- **Don't remove the consensus filter** from tiering. Live data weakly favors keeping it; conservative production read.
- **Don't add an ULTRA tier** at ≥5pt. Fires too rarely to be useful.
- **DO consider** building: CLV tracking column, multi-book line scraper, totals model, props model, Kelly sizing layer — these are where actual edge gains live.

Related: [[feature-list-order-is-contract]] (the column-order safety net that lets us safely run experiments like these).
