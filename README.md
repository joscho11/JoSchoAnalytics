# BettingEdge — NFL Prediction System

Live dashboard: [joschobetting.streamlit.app](https://joschobetting.streamlit.app)

---

## What This Is

I built this because I wanted to know if a data-driven model could actually find an edge against the spread. Not just predict winners — anyone can do that — but consistently beat the number Vegas sets.

The answer so far: yes. Across the 2025 live test (weeks 10–17, 121 games), the ATS model sits at **56.4% overall**, with **HIGH-confidence picks at 64.7%** (11/17) and **MEDIUM-confidence picks at 59.5%** (25/42). Break-even after vig is 52.4%.

This repo is the full system — ATS predictions, fantasy football projections, a DFS lineup optimizer, and an LLM agent that explains *why* it likes or fades each game.

---

## What's Inside

### ATS Prediction Model

A three-voter ensemble trained on 4,300+ NFL games across 15+ seasons.

- **Ensemble fixed75** (primary) — 75% XGBoost + 25% Ridge, trained 2014–2024. Sets the edge threshold and game ranking.
- **XGBoost, Ridge, LightGBM** — three independent direction voters. When all three agree on a side and the Ensemble edge is ≥ 3pts → **HIGH** confidence. ≥ 1pt → **MEDIUM**. Otherwise → **PASS**.
- **35 production features** selected from 85 engineered (rolling EPA, yards/play, strength of schedule, All-Pro roster quality, injury impact, coach win%, QB passer rating, sack/turnover/3rd-down rates). The feature set was trimmed in May 2026 via a walk-forward ablation — dropping the 50 lowest-importance features improved XGBoost CV mean ATS by +1.6pp.
- **Tuned hyperparameters** (May 2026): Ridge α=50, XGBoost reg_alpha=2 / reg_lambda=5. Confirmed across 3 seeds.

Walk-forward CV results (6 folds, test years 2020–2025, 35-feature subset, tuned hyperparameters):

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| Random Forest | 57.1% | 2.9% | Highest mean — but highest variance; not in production |
| XGBoost (cv) | 56.9% | 1.9% | **CV winner on risk-adjusted basis** — direction voter |
| LightGBM | 56.5% | 1.7% | Most consistent — direction voter |
| Ridge | 55.6% | 2.0% | Direction voter + linear component of the ensemble |

Break-even is 52.4% ATS. The full ablation, hyperparameter sweep, and seed-stability check live in `betting/experiments/`.

### Fantasy Football Projections

Half-PPR player projections for QB, RB, WR, and TE. One XGBoost regressor per position, trained on 2020–2024 data with 2025 as holdout.

| Position | MAE | Baseline MAE |
|----------|-----|--------------|
| QB | 6.99 | 7.49 |
| RB | 4.48 | 4.59 |
| WR | 3.91 | 4.06 |
| TE | 3.17 | 3.48 |

Eight additional per-stat prop models (pass yards, rush yards, receptions, rec yards by position) generate individual stat projections for prop betting reference.

### DFS Lineup Optimizer

ILP-based DraftKings NFL Classic lineup optimizer using our weekly fantasy projections as the value signal. Fuzzy-matches DK salary CSVs to player names and solves a salary-capped roster selection as a binary integer program.

- Constraints: 1 QB / 2+ RB / 3+ WR / 1+ TE / 1 DST / 9 total / $50k cap / max 8 from one team
- FLEX filled implicitly by the solver
- Unmatched players fall back to DK's season `AvgPointsPerGame`

### LLM Agent

A LlamaIndex `ReActAgent` with 5 tools (predictions lookup, injury reports, line movement, matchup history, confidence analysis). Synthesizes qualitative reasoning per game — flags when sharp money conflicts with the model or when injuries change the picture. Output cached per week, displayed as confidence overlays in the dashboard.

### Dashboard

Streamlit app with three tabs:
- **Weekly Predictions** — game cards with edge, consensus tier, and expandable agent reasoning
- **Season Performance** — ATS record by confidence tier and week
- **Fantasy** — per-position player projections with projected and actual stat columns

### Automation

GitHub Actions runs the prediction pipeline on three schedules:

| Time | Action |
|------|--------|
| Tuesday 9am ET | Previous week results filled in; new week predictions generated |
| Thursday 9pm ET | Predictions refreshed with injury report data |
| Sunday 9am ET | Final predictions locked |

The only manual step each season is updating the All-Pro CSV in January.

---

## Results (2025 Season, Weeks 10–17, 121 games)

| Tier | Games | Correct | Win % |
|------|-------|---------|-------|
| **HIGH** (all 3 voters agree + ensemble edge ≥ 3pt) | 17 | 11 | **64.7%** |
| **MEDIUM** (all 3 voters agree + ensemble edge ≥ 1pt) | 42 | 25 | **59.5%** |
| PASS | 62 | 30 | 48.4% |
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
  agent_analysis_2025_week{n}.json     # Cached agent output per week
  experiments/                         # Reusable analysis scripts + result snapshots
    tune_hyperparams.py                # Walk-forward hyperparameter sweep across 5 models
    tune_xgb_seeds.py                  # Multi-seed XGBoost stability check
    feature_ablation.py                # Importance-ranked feature subset CV study
    *.json / feature_importance_ranking.csv  # Result snapshots
  archive/                             # Retired notebooks and model files
fantasy/
  data_pipeline.ipynb                  # Pull & join player stats from nflreadpy
  features.ipynb                       # Feature engineering → features_dataset.csv
  model.ipynb                          # Train per-position + per-stat prop models
  predict_fantasy.ipynb                # Weekly half-PPR projections (run via papermill)
  features_dataset.csv                 # Engineered feature dataset
  raw_dataset.csv                      # Raw joined player stats
  models/                              # Per-position + per-stat XGBoost pkl files
  fantasy_projections/                 # Weekly projection CSVs (projections_{season}_week{n}.csv)
  dfs/
    optimizer.ipynb                    # TBD - ILP formulation + helper functions reference
    dfs_pipeline.ipynb                 # TBD - Weekly DFS workflow (papermill-compatible)
.github/workflows/
  weekly_predictions.yml               # Monday/Thursday/Sunday automation
```

---

## What's Next

1. **DST projection model** — replace the `dk_avg` fallback for DST in the DFS optimizer with a trained model
2. **Multi-lineup GPP generator** — produce N distinct lineups with ownership-diversity constraints for tournament play
3. **Game-stacking constraints** — ILP constraints to co-select QB + WR + opponent pass-catcher in high-total games
4. **Automated salary fetching** — replace the manual DK CSV download with a scraper or API
5. **End-to-end automation** — chain `predict_fantasy.ipynb` → `dfs_pipeline.ipynb` in GitHub Actions so DFS lineups generate automatically
