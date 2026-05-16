# BettingEdge — NFL ATS Prediction System

Live dashboard: [joschobetting.streamlit.app](https://joschobetting.streamlit.app)

---

## What This Is

I built this because I wanted to know if a data-driven model could actually find an edge against the spread. Not just predict winners — anyone can do that — but consistently beat the number Vegas sets.

The short answer: yes, at least on the 2025 season. The model finished **11/14 on Week 10** and sits at **53.85% ATS overall**, with **55.71%** on high-confidence picks. Not retire-off-this numbers, but enough to be interesting.

This repo is the full system — the model, the automation, the dashboard, and an LLM agent that explains *why* it likes or fades each game.

---

## How It Works

**The Model**
A four-model system trained on 4,300+ NFL games across 15+ seasons. The primary model is **Ensemble fixed75** — a fixed-weight blend of 75% XGBoost and 25% Ridge — which sets the edge threshold and game ranking. XGBoost, Ridge, and LightGBM serve as the three direction voters: when all three agree on a side and the Ensemble edge is large enough, the game is rated HIGH or MEDIUM confidence. I engineered 79 features covering rolling EPA, strength of schedule, All-Pro roster quality, injury impact, QB changes, and coaching history. Each model predicts the margin of victory and compares it against the Vegas spread to find edge.

**The Agent**
On top of the raw predictions, I built a ReActAgent using LlamaIndex and the Anthropic Claude API. It has 5 tools: model predictions, injury reports, line movement, historical matchups, and model confidence analysis. Each week it synthesizes all of that into per-game reasoning — flagging when sharp money conflicts with the model, when injuries change the picture, or when historical trends back up the prediction.

**The Dashboard**
Streamlit app showing weekly predictions, per-game agent analysis (click any game card to expand), ATS record, and season-wide performance. Updated automatically on Monday, Thursday, and Sunday via GitHub Actions.

**The Automation**
Monday 9am   → Predictions generated with early lines
Thursday 9pm → Refreshed with injury report data
Sunday 7am   → Final predictions locked in
Monday 9am   → Previous week results filled in, new week starts

The only manual step each season is updating the All-Pro CSV in January.

---

## Stack

| Component | Tech |
|-----------|------|
| Prediction models | XGBoost, LightGBM, Scikit-learn (Ridge) |
| Feature engineering | nflreadpy, pandas, NumPy |
| LLM agent | LlamaIndex, Anthropic Claude API |
| Dashboard | Streamlit |
| Automation | GitHub Actions |
| Data | nflreadpy, custom All-Pro CSV |

---

## Repo Structure

```
app.py                               # Streamlit dashboard (entry point)
betting/
  predict_betting.ipynb              # Weekly ATS prediction pipeline (run via papermill)
  model_comparison.ipynb             # Model architecture comparison + walk-forward CV
  models/
    ensemble_prod_model.pkl          # Primary model: Ensemble fixed75 (0.75 XGB + 0.25 Ridge)
    xgboost_prod_model.pkl           # XGBoost direction voter
    lgbm_prod_model.pkl              # LightGBM direction voter
  predictions_tracker.csv            # All predictions + results
  nfl_allpro_1997_2025.csv           # All-Pro roster data
  sports_betting_agent.ipynb         # Agent development notebook
  agent_analysis_2025_week{n}.json   # Cached agent output per week
  archive/                           # Retired notebooks and model files
fantasy/
  data_pipeline.ipynb                # Pull & join player stats
  features.ipynb                     # Feature engineering
  model.ipynb                        # Train per-position models
  predict_fantasy.ipynb              # Weekly half-PPR player projections (run via papermill)
  features_dataset.csv               # Engineered feature dataset
.github/workflows/                   # GitHub Actions automation
```

---

## Results (2025 Season)

| Metric | Value |
|--------|-------|
| Overall ATS | 57.85% (70/121) |
| Best week | 11/16 (Week 13) |

---

## What's Next

- Replace mock injury/line data with live ESPN and sportsbook APIs
- Wire agent notebook into GitHub Actions for full end-to-end automation
- Track agent vs model accuracy over multiple seasons to measure if the reasoning layer adds value