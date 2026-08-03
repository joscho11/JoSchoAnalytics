---
name: joschoanalytics-model-experiments-2026-05
description: Rejected model-improvement experiments (weather, ensemble re-weighting, consensus filter removal, ULTRA tier, time-decay weighting, extended training range) — all proven not worth shipping
metadata:
  type: project
---

In late May 2026 we ran a series of model-improvement experiments on JoSchoAnalytics.
**All of them were rejected** after empirical testing. Future contributors (including future-me) should not re-run these without strong reason — the negative findings are documented in CLAUDE.md's Completed Work entries dated 2026-05-24 / 25 / 26.

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

### 5. Time-decay sample weighting (Pass 1, 2026-05-25)
- Tested `sample_weight = exp(-α × (max_train_year - season))` with α ∈ {0, 0.05, 0.10, 0.15, 0.20} on 6-fold walk-forward CV with TRAIN_SEASONS=2014+
- **Result:** XGBoost α=0 baseline 57.2% ± 2.0%; best non-zero α=0.10 at 57.2% ± 2.5% (Δ -0.01pp mean, +0.5pp std worse). Ridge/LightGBM/Random Forest flat or worse at every α. Only MLP improved (+1.4pp at α=0.15), but MLP isn't in production.
- **Why it failed:** the production-relevant tree-based models don't suffer from "too much old data" — they're already weighting recent samples implicitly through the rolling-feature structure. Adding explicit decay only adds noise.

### 7. Synthesis: decay weighting × extended TRAIN_SEASONS together (Pass 3, 2026-05-26)
- Initial run with `--earliest 2005` had silent **data coverage corruption** — pre-2009 training rows had 100% zero injury features (nflreadpy injuries hard-floor at 2009), and 2005 rows had 100% zero AllPro (hardcoded 2006 floor in mc cell 15). The "extra training data" was partly mechanical zeros, biasing the experiment.
- **Clean rerun** (`--earliest 2008, --train-starts 2014,2011,2009`): explicit `verify_coverage()` gate ensures no feature has >25pp zero-rate shift between early and late periods. Audit script also verified each nflreadpy source's actual lower bound (schedules/PBP 1999, AllPro 1997, NGS 2016, injuries 2009).
- **Best cell for XGBoost:** train=2009+, α=0 (no decay) → 57.1% ± 2.6%. Within-run baseline (2014+, α=0) is 56.5% ± 1.6%. That's +0.6pp mean (clears ship threshold) but +1.0pp std worse (fails std cap).
- **4-of-5 models improve at the best cell** (XGB +0.6, Ridge +0.2, LightGBM +0.3, MLP +0.7). RF regresses (-0.5).
- **Critical context:** the within-run 2014+ baseline (56.5%) is 0.7pp BELOW Pass 1's standalone baseline (57.2%). Why: extending the data load gives 2013 a real manual passer rating instead of median fill, which then shifts 2014's prev-year-PR feature. Part of the apparent +0.6pp "gain from extending data" is recovery from the feature-shift the extension itself causes. **Net vs current production CV (XGBoost 56.9%): +0.2pp mean, +0.7pp std worse.**
- **Decay × extension synthesis: NO synergy.** Every non-zero α at every train_start performs WORSE than α=0 within that train_start. The hypothesis that decay unlocks the value of more data is empirically wrong on this codebase.
- **Why it failed:** stability loss is real and consequential. A model with 1.6% std swings 55-58% in any given year; 2.6% std swings 54-60%. For a money-at-stake application, narrower band > slightly higher mean.

### 6. Extended TRAIN_SEASONS back beyond 2014 (Pass 2, 2026-05-26)
- Tested `train_starts ∈ {2014, 2010, 2005}` with α=0, after extending mc's ALL_SEASONS data load to 2005-2025 (5,698 games vs baseline 3,295)
- **Result:** XGBoost 56.4% (2014+) → 56.7% (2010+) → 56.8% (2005+). Best Δ +0.4pp at 2005+, sub-threshold. Std worsens by +1.0pp at 2005+. Mixed across other models (Ridge +0.4, LightGBM -0.5, RF -0.4, MLP +1.2).
- **Important nuance:** the 2014+ baseline within the extended-data run (56.4%) is 0.8pp *below* Pass 1's 2014+ baseline (57.2%) because extending the data load activates the manual passer-rating fallback for 2010-2015 (vs only 2014-2015 in Pass 1). This changes feature values for 2014 training rows, so part of any "improvement" at earlier train_starts is just recovering ground lost to the feature shift.
- **Engineering done that future experiments can reuse:** `tune_time_decay.py` now supports `--earliest YEAR` for extended data loads, with monkey-patched `nfl.load_injuries` (filters to 2009+ with progressive-year fallback). Schedule pulls 1999+, PBP back as far as nflreadpy supports, manual passer-rating fallback extends to any pre-2016 year automatically.
- **Why it failed:** older NFL games have meaningfully different rules (catch rule, kickoff rules, defenseless receiver expansions, two-point conversion changes circa 2015), and the model's tree splits don't generalize across the rule-shift boundary as cleanly as expected. The newer 2014+ window is more uniform.

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
- **Don't re-add time-decay sample weighting to production models.** Tested across the full α grid (Pass 1 + 3); decay weighting consistently hurts when combined with any train_start on cleaned data. Production-relevant models don't respond.
- **Don't extend TRAIN_SEASONS back beyond 2014** for ATS spread prediction. Tested cleanly down to 2009+ with verified-clean data coverage (Pass 3 clean). XGBoost mean +0.6pp but std +1.0pp worse; net vs current production is essentially zero once data-shift baseline drop is factored in. Stability loss > mean gain for money-at-stake applications.
- **ALWAYS audit data-source coverage before running an "extend the data" experiment.** Use `betting/experiments/_audit_historical_coverage.py` to verify each nflreadpy source's actual lower bound. Use `verify_coverage()` in `tune_time_decay.py` as a pre-flight gate. Mechanical zero-fill from missing data sources will make a bad experiment look like a borderline good one.
- **DO consider** building: CLV tracking column, multi-book line scraper, totals model, props model, Kelly sizing layer — these are where actual edge gains live.

Related: [[feature-list-order-is-contract]] (the column-order safety net that lets us safely run experiments like these), [[experiment-rejection-criteria]] (the ship/reject thresholds applied to each of these).
