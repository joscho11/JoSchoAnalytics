# BettingEdge: NFL Prediction System

Live dashboard: [joschobetting.streamlit.app](https://joschobetting.streamlit.app)

---

## What This Is

I built this to find out if a data-driven model can actually find an edge against the spread. Anyone can pick winners. The harder question is whether you can consistently beat the number Vegas sets.

The answer so far is yes. Across the 2025 live test (weeks 10 through 17, 121 games), the ATS model sits at **56.4% overall**, with **HIGH-confidence picks at 64.7%** (11/17) and **MEDIUM-confidence picks at 59.5%** (25/42). Break-even after vig is 52.4%.

The repo is the full system: ATS predictions, fantasy football projections, a DFS lineup optimizer, and an LLM agent that explains *why* the model likes or fades each game.

---

## What's Inside

### ATS Prediction Model

A three-voter ensemble trained on 4,300+ NFL games across 15+ seasons.

- **Ensemble fixed75** is the primary model. 75% XGBoost + 25% Ridge, trained 2014 through 2024. It sets the edge threshold and game ranking.
- **XGBoost, Ridge, LightGBM** are three independent direction voters. When all three agree on a side and the Ensemble edge is at least 3 points the tier is **HIGH**. At least 1 point is **MEDIUM**. Otherwise it's **PASS**.
- **35 production features** selected from 85 engineered (rolling EPA, yards/play, strength of schedule, All-Pro roster quality, injury impact, coach win%, QB passer rating, sack/turnover/3rd-down rates). I trimmed the feature set in May 2026 via a walk-forward ablation. Dropping the 50 lowest-importance features improved XGBoost CV mean ATS by +1.6pp.
- **Tuned hyperparameters** (May 2026): Ridge α=50, XGBoost reg_alpha=2 / reg_lambda=5. Confirmed across 3 seeds.

Walk-forward CV results (6 folds, test years 2020 through 2025, 35-feature subset, tuned hyperparameters):

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| Random Forest | 57.1% | 2.9% | Highest mean. Also highest variance, so not in production. |
| XGBoost (cv) | 56.9% | 1.9% | **CV winner on risk-adjusted basis**. Direction voter. |
| LightGBM | 56.5% | 1.7% | Most consistent. Direction voter. |
| Ridge | 55.6% | 2.0% | Direction voter + linear component of the ensemble. |

![Walk-forward CV results across 5 models, 2020 through 2025](betting/images/model_cv_results.png)

Break-even is 52.4% ATS. The full ablation, hyperparameter sweep, and seed-stability check live in `betting/experiments/`.

![Head-to-head model comparison on the 2023 through 2025 test set](betting/images/model_comparison_results.png)

The most important features by combined XGBoost gain + Ridge |coef| + LightGBM gain:

![Feature importance ranking across all three voter models](betting/images/model_comparison_importance.png)

### Fantasy Football Projections

Half-PPR points for QB, RB, WR, and TE the night before each slate, plus per-stat prop projections for pass/rush/rec yards and receptions. The pipeline is three notebooks run in order.

| Notebook | Role |
|----------|------|
| `data_pipeline.ipynb` | Pulls and joins `player_stats`, `ff_opportunity`, `schedules`, `injuries`, and `depth_charts` from nflreadpy into `raw_dataset.csv` (about 35k rows by 84 columns) |
| `features.ipynb` | Builds rolling 3 and 5 week averages plus their trend, points-allowed-vs-position for matchup difficulty, opponent SOS, coach win%, Vegas implied team total, weather, depth-chart starter availability. Output is `features_dataset.csv` (about 40k rows by 97 columns) |
| `model.ipynb` | Trains per-position XGBoost regressors on `target_half_ppr` (next week's score), saves to `models/{position}_model.pkl` |
| `predict_fantasy.ipynb` | Weekly inference. Loads the pkls, pulls upcoming week, generates projections plus per-stat props, writes `fantasy_projections/projections_{season}_week{n}.csv` |

**Feature pattern:** every rolling window uses `shift(1).rolling(N, min_periods=1)` so a player's own current-week stats never leak into their current-week prediction. Features include rolling usage (snaps, targets, carries), rolling production (yards, TDs, receptions), the 3 vs 5 week trend, matchup difficulty (opponent points allowed to that position), Vegas implied team total, weather and surface, depth-chart starter availability, and injury status of teammates and opponents.

**2025 holdout results** (vs a 3 week rolling average baseline):

| Position | Train rows | Test rows | MAE | RMSE | Baseline MAE |
|----------|-----------|-----------|-----|------|--------------|
| QB | 2,781 | 571 | **6.99** | 8.60 | 7.49 |
| RB | 6,652 | 1,397 | **4.48** | 6.45 | 4.59 |
| WR | 10,643 | 2,215 | **3.91** | 5.37 | 4.06 |
| TE | 5,265 | 1,145 | **3.17** | 4.64 | 3.48 |

Beats the rolling-average baseline at every position. TE has the lowest MAE since TE scoring is more concentrated and the model picks up on it.

**Per-stat prop models** (8 separate XGBoost regressors, same train/test split):

| Position | Stat | Model file |
|----------|------|-----------|
| QB | Pass yards | `qb_pass_yards_model.pkl` |
| QB | Rush yards | `qb_rush_yards_model.pkl` |
| RB | Rush yards | `rb_rush_yards_model.pkl` |
| RB | Rec yards | `rb_rec_yards_model.pkl` |
| WR | Receptions | `wr_receptions_model.pkl` |
| WR | Rec yards | `wr_rec_yards_model.pkl` |
| TE | Receptions | `te_receptions_model.pkl` |
| TE | Rec yards | `te_rec_yards_model.pkl` |

Each prop model uses the same feature set as the main position model but with a different `target_*` column. The per-stat projections are independent, so their values won't sum exactly to the main `Proj Pts` figure. They're meant as a reference for prop bets where the question is whether the projected stat clears the sportsbook's line.

**Live integration:** the Streamlit dashboard's Fantasy tab shows per-position weekly projections with both projected and **actual** stat columns. Actuals come from nflreadpy and cache for an hour. Players who didn't play show "DNP" in all actual columns so missed-game noise doesn't fake-deflate the model's accuracy.

### DFS Lineup Optimizer

ILP-based DraftKings NFL Classic lineup optimizer using the weekly fantasy projections as the value signal. It fuzzy-matches DK salary CSVs to player names and solves a salary-capped roster selection as a binary integer program.

- Constraints: 1 QB / 2+ RB / 3+ WR / 1+ TE / 1 DST / 9 total / $50k cap / max 8 from one team
- FLEX is filled implicitly by the solver
- Unmatched players fall back to DK's season `AvgPointsPerGame`

### LLM Agent

A LlamaIndex `ReActAgent` with 5 tools (predictions lookup, injury reports, line movement, matchup history, confidence analysis). It writes a short qualitative read per game and flags when sharp money conflicts with the model or when injuries change the picture. Output is cached per week and displayed as confidence overlays in the dashboard.

### Dashboard

Streamlit app with three main tabs.

- **Weekly Predictions**: game cards with edge, consensus tier, and expandable agent reasoning.
- **Season Performance**: ATS record by confidence tier and week, plus profit-at-110-odds and longest streaks.
- **Fantasy**: per-position player projections with projected and actual stat columns.

### Automation

Two GitHub Actions workflows.

**`weekly_predictions.yml`** runs the prediction pipeline on three schedules:

| Time | Action |
|------|--------|
| Tuesday 9am ET | Previous week results filled in. New week predictions generated. |
| Thursday 9pm ET | Predictions refreshed with injury report data. |
| Sunday 9am ET | Final predictions locked. |

**`test.yml`** runs on every push and PR to `main`. It executes `features.ipynb` end-to-end via papermill, validating all 15 inline tests (constants order-hashes, per-group feature builders, build_features integration). Catches regressions in seconds instead of on the next Tuesday cron.

The only manual step each season is updating the All-Pro CSV in January.

---

## Results (2025 Season, Weeks 10 through 17, 117 graded games)

| Tier | Games | Correct | Win % |
|------|-------|---------|-------|
| **HIGH** (all 3 voters agree + ensemble edge ≥ 3pt) | 17 | 11 | **64.7%** |
| **MEDIUM** (all 3 voters agree + ensemble edge ≥ 1pt) | 42 | 25 | **59.5%** |
| PASS | 58 | 30 | 51.7% |
| **Overall (Ensemble)** | **117** | **66** | **56.4%** |

Best week: 9/14 (Week 14, 64.3%).

---

## Stack

| Component | Tech |
|-----------|------|
| ATS models | XGBoost, LightGBM, Scikit-learn (Ridge, Ensemble) |
| Fantasy models | XGBoost (per-position + per-stat prop models) |
| DFS optimizer | PuLP (ILP), fuzzy name matching |
| Feature engineering | nflreadpy, pandas, NumPy |
| LLM agent | LlamaIndex, Anthropic Claude API |
| Dashboard | Streamlit |
| Automation | GitHub Actions (papermill) |
| Data | nflreadpy, custom All-Pro CSV |

---

## Repo Structure

```
app.py                                 # Streamlit dashboard (entry point)
betting/
  features.ipynb                       # Shared 85-feature engineering (single source of truth)
  predict_betting.ipynb                # Weekly ATS prediction pipeline (run via papermill; loads features.ipynb)
  model_comparison.ipynb               # Model architecture comparison + walk-forward CV (loads features.ipynb)
  sports_betting_agent.ipynb           # Agent development notebook
  models/
    ensemble_prod_model.pkl            # Primary model: Ensemble fixed75 (0.75 XGB + 0.25 Ridge)
    xgboost_prod_model.pkl             # XGBoost direction voter
    lgbm_prod_model.pkl                # LightGBM direction voter
  predictions_tracker.csv              # All predictions + results (auto-committed)
  nfl_allpro_1997_2025.csv             # All-Pro roster data (updated manually each January)
  nfl_weather_2014_2025.csv            # Kickoff-hour temp/wind per outdoor game (Meteostat-sourced)
  agent_analysis_2025_week{n}.json     # Cached agent output per week
  experiments/                         # Reusable analysis scripts + result snapshots
    tune_hyperparams.py                # Walk-forward hyperparameter sweep across 5 models
    tune_xgb_seeds.py                  # Multi-seed XGBoost stability check
    feature_ablation.py                # Importance-ranked feature subset CV study
    fetch_weather.py                   # Pulls kickoff-hour weather, writes nfl_weather_*.csv (annual refresh)
    *.json / feature_importance_ranking.csv  # Result snapshots
  archive/                             # Retired notebooks and model files
fantasy/
  data_pipeline.ipynb                  # Pull & join player stats from nflreadpy
  features.ipynb                       # Feature engineering, writes features_dataset.csv
  model.ipynb                          # Train per-position + per-stat prop models
  predict_fantasy.ipynb                # Weekly half-PPR projections (run via papermill)
  features_dataset.csv                 # Engineered feature dataset
  raw_dataset.csv                      # Raw joined player stats
  models/                              # Per-position + per-stat XGBoost pkl files
  fantasy_projections/                 # Weekly projection CSVs (projections_{season}_week{n}.csv)
  dfs/
    optimizer.ipynb                    # TBD. ILP formulation + helper functions reference.
    dfs_pipeline.ipynb                 # TBD. Weekly DFS workflow (papermill-compatible).
memory/                                # Persistent notes for future contributors (preferences + project context)
.github/workflows/
  weekly_predictions.yml               # Tuesday/Thursday/Sunday automation (runs predict_betting.ipynb)
  test.yml                             # Push/PR CI. Runs features.ipynb inline tests on every change.
```

---

## What's Next

After an extended series of May 2026 experiments — weather features, ensemble re-weighting, consensus-tier changes, time-decay sample weighting, and extending the training window back to 2009 — all rejected the ATS spread model is at the ceiling of what this architecture can deliver. The biggest gains from here are in execution infrastructure or in opening new edge streams, not more spread-model tuning. See `CLAUDE.md` Completed Work for the full rolling log.

1. **Totals model.** Independent edge stream using the same data infrastructure. Wind features (which don't help spreads) have clear signal on totals. The weather CSV (`betting/nfl_weather_2014_2025.csv`) is already built and ready. Estimated 5-10 hours to a working v1; same XGB + Ridge architecture as the spread model.
2. **Closing Line Value (CLV) tracking.** Leading indicator of long-term profitability, more predictive than ATS% over short samples. Two paths: (a) pay The Odds API ~$30 for one month to dump historical opening + closing lines for 2020-2025, then cancel; (b) modify the predictions tracker to start recording multi-day line snapshots forward-only. Path (a) gives a real CLV answer immediately; (b) is free but requires waiting through a season.
3. **Multi-book line shopping.** Same pick at DraftKings -3.5 (-110) vs FanDuel -3.5 (-105) is about a 2% implied-edge improvement. Across hundreds of bets this moves the needle more than further model tuning.
4. **Kelly fractional sizing.** Stop equal-staking within tiers. Let bet size scale with edge magnitude.
5. **Player props model.** Lower-efficiency market, higher edge potential. Per-stat fantasy projection models already exist. The leap to "is the prop line over/under our predicted stat" is small.

DFS optimizer follow-ups (lower priority, already functional):

6. **DST projection model.** Replace the `dk_avg` fallback for DST in the DFS optimizer with a trained model.
7. **Multi-lineup GPP generator.** Produce N distinct lineups with ownership-diversity constraints for tournament play.
8. **Game-stacking constraints.** ILP constraints to co-select QB + WR + opponent pass-catcher in high-total games.
9. **Automated salary fetching.** Replace the manual DK CSV download with a scraper or API.
10. **End-to-end automation.** Chain `predict_fantasy.ipynb` and `dfs_pipeline.ipynb` in GitHub Actions so DFS lineups generate automatically.
