# BettingEdge — NFL Prediction System

Live dashboard: [joschobetting.streamlit.app](https://joschobetting.streamlit.app)

---

## What This Is

I built this because I wanted to know if a data-driven model could actually find an edge against the spread. Not just predict winners — anyone can do that — but consistently beat the number Vegas sets.

The answer so far: yes. The ATS model sits at **57.85% overall** with **high-confidence picks at 55.71%+**. Not retire-off-this numbers, but enough to be interesting.

This repo is the full system — ATS predictions, fantasy football projections, a DFS lineup optimizer, and an LLM agent that explains *why* it likes or fades each game.

---

## What's Inside

### ATS Prediction Model

A three-voter ensemble trained on 4,300+ NFL games across 15+ seasons.

- **Ensemble fixed75** (primary) — 75% XGBoost + 25% Ridge, trained 2014–2024. Sets the edge threshold and game ranking.
- **XGBoost, Ridge, LightGBM** — three independent direction voters. When all three agree on a side and the Ensemble edge is ≥ 3pts → **HIGH** confidence. ≥ 1pt → **MEDIUM**. Otherwise → **PASS**.
- **79 features** covering rolling EPA, yards/play, strength of schedule, All-Pro roster quality, injury impact, coaching win%, surface, and weather.

Walk-forward CV results (6 folds, test years 2020–2025):

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| LightGBM | 53.0% | 4.1% | CV winner — direction voter |
| Ridge | 52.1% | 2.9% | Best MAE; direction voter |
| Random Forest | 51.3% | 2.5% | Not in production |
| XGBoost (cv) | 51.2% | 1.8% | CV-retrained; prod pkl adds more signal |

Break-even is 52.4% ATS.

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
| Monday 9am ET | Previous week results filled in; new week predictions generated |
| Thursday 9pm ET | Predictions refreshed with injury report data |
| Sunday 9am ET | Final predictions locked |

The only manual step each season is updating the All-Pro CSV in January.

---

## Results (2025 Season)

| Metric | Value |
|--------|-------|
| Overall ATS | 57.85% (70/121) |
| Best week | 11/16 (Week 13) |

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
  predict_betting.ipynb                # Weekly ATS prediction pipeline (run via papermill)
  model_comparison.ipynb               # Model architecture comparison + walk-forward CV
  sports_betting_agent.ipynb           # Agent development notebook
  models/
    ensemble_prod_model.pkl            # Primary model: Ensemble fixed75 (0.75 XGB + 0.25 Ridge)
    xgboost_prod_model.pkl             # XGBoost direction voter
    lgbm_prod_model.pkl                # LightGBM direction voter
  predictions_tracker.csv              # All predictions + results (auto-committed)
  nfl_allpro_1997_2025.csv             # All-Pro roster data (updated manually each January)
  agent_analysis_2025_week{n}.json     # Cached agent output per week
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
    optimizer.ipynb                    # ILP formulation + helper functions reference
    dfs_pipeline.ipynb                 # Weekly DFS workflow (papermill-compatible)
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
