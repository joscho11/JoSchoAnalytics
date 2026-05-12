# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL Against-the-Spread (ATS) prediction system combining:
- A pre-trained XGBoost ML model for predicting game margins
- A Claude-powered LLM agent (via LlamaIndex) for qualitative game reasoning
- A Streamlit dashboard for visualization (deployed at joschobetting.streamlit.app)
- GitHub Actions for weekly automated predictions (Mon/Thu/Sun)

## Common Commands

**Run the dashboard locally:**
```bash
streamlit run app.py
```
Runs on port 8501. Requires `predictions_tracker.csv` and any cached `agent_analysis_2025_week*.json` files.

**Run the prediction pipeline:**
```bash
python predict.py monday    # Update last week's results, generate new week predictions
python predict.py thursday  # Refresh predictions with injury data
python predict.py sunday    # Final predictions before games
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Environment variables** (from `.env`): `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_ANALYTICS_ID`

## Architecture

### Core Files
- **`predict.py`** — The prediction pipeline. Pulls live NFL data via `nflreadpy`, engineers features, loads `fantasy_model.pkl`, computes predicted margin vs. Vegas spread to find edges, and commits results to `predictions_tracker.csv`.
- **`app.py`** — Streamlit dashboard with 3 tabs: Weekly Predictions, Season Performance, Help & Guide. Reads `predictions_tracker.csv` and cached `agent_analysis_2025_week{n}.json` files for LLM agent reasoning overlays.
- **`fantasy_model.pkl`** — Pre-trained XGBoost `sklearn` pipeline (includes `preprocessor` step with OneHotEncoder + StandardScaler). Not retrained in `predict.py`.
- **`predictions_tracker.csv`** — Master log of all predictions and outcomes. Auto-committed by GitHub Actions.

### Feature Groups (predict.py ~lines 77–423)
1. Schedule context: temperature, wind, surface, playoff flag, final-week flag
2. Rolling PBP stats: EPA, yards/play (5-game windows)
3. Strength of schedule: opponent win% (rolling 3-game and season-long)
4. All-Pro roster quality: weighted 3-year lookback, offense/defense split
5. Rolling performance: win%, points scored/allowed (5-game windows)

### LLM Agent
Developed in `DEV_sports_betting_agent.ipynb`. Uses LlamaIndex `ReActAgent` with 5 tools (predictions lookup, injury reports, line movement, matchup history, confidence analysis). Output is cached per week as `agent_analysis_2025_week{n}.json` and displayed in the dashboard as confidence overlays (HIGH/MEDIUM/SKIP).

### Data
- `fantasy/features_dataset.csv` — Engineered feature dataset (built by `fantasy/data_pipeline.ipynb`)
- `nfl_allpro_1997_2025.csv` — All-Pro roster data; updated manually each January
- Live schedule, PBP, and stats pulled from `nflreadpy` at prediction time

### Automation
`.github/workflows/weekly_predictions.yml` runs `predict.py` on three cron schedules (Mon 9am ET, Thu 9pm ET, Sun 7am ET) and commits the updated tracker. Supports manual dispatch with mode selection.

## Key Constraints
- The XGBoost model pipeline expects a `preprocessor` named step — don't change the pkl structure without retraining.
- `nfl_allpro_1997_2025.csv` must be updated manually each January for the new season.
- Agent analysis JSON files are cached by week; regenerating them requires re-running the agent notebook and costs API calls.
- The dashboard reads the tracker CSV directly — column names and structure in `predictions_tracker.csv` must stay consistent with `app.py` expectations.
