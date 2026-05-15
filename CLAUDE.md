# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL Against-the-Spread (ATS) prediction system combining:
- A three-model ensemble: Ensemble fixed75 (primary), XGBoost, and Ridge as confidence voters
- A Claude-powered LLM agent (via LlamaIndex) for qualitative game reasoning
- A Streamlit dashboard for visualization (deployed at joschobetting.streamlit.app)
- GitHub Actions for weekly automated predictions (Mon/Thu/Sun)

## Common Commands

**Run the dashboard locally:**
```bash
streamlit run app.py
```
Runs on port 8501. Requires `betting/predictions_tracker.csv` and any cached `betting/agent_analysis_2025_week*.json` files.

**Run the prediction pipeline:**
```bash
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE monday    # Update results + new predictions
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE thursday  # Refresh with injury data
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE sunday    # Final predictions
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE backfill -p TARGET_WEEK 14  # Backfill a specific week
```

**Run fantasy projections:**
```bash
papermill fantasy/predict_fantasy.ipynb /tmp/out.ipynb                                      # auto-detect week
papermill fantasy/predict_fantasy.ipynb /tmp/out.ipynb -p TARGET_SEASON 2025 -p TARGET_WEEK 14
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Environment variables** (from `.env`): `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_ANALYTICS_ID`

## Architecture

### Core Files
- **`betting/predict_betting.ipynb`** — The prediction pipeline. Pulls live NFL data via `nflreadpy`, engineers features, loads all three models from `betting/models/`, computes predicted margin vs. Vegas spread to find edges, and commits results to `betting/predictions_tracker.csv`. Run via papermill; `MODE` is the papermill parameter.
- **`app.py`** — Streamlit dashboard with 3 tabs: Weekly Predictions, Season Performance, Help & Guide. Reads `betting/predictions_tracker.csv` and cached `betting/agent_analysis_2025_week{n}.json` files for LLM agent reasoning overlays. Fantasy tab shows per-week projections per position with projected and actual stat columns (pass yds, rush yds, receptions, rec yds) that populate automatically after the week is played (fetched live from nflreadpy, cached 1 hour). Players who didn't play show "DNP" in all actual columns.
- **`betting/models/`** — All trained model pkl files:
  - `ensemble_prod_model.pkl` — **Primary model.** Ensemble fixed75: 0.75 XGBoost + 0.25 Ridge, trained 2014–2024. Sets the edge threshold and output sort order. Includes `scaler`, `feature_cols`, `roof_surface_encoder`, `xgb_model`, `ridge_model`, `xgb_weight`.
  - `xgboost_prod_model.pkl` — XGBoost sklearn pipeline (preprocessor + regressor). Acts as one of three confidence voters.
  - (Ridge is extracted from `ensemble_prod_model.pkl["ridge_model"]` at runtime — no separate pkl needed.)
- **`betting/archive/`** — Old model files and retired notebooks: `betting_model.pkl` (original XGBoost pkl), `BettingEdge_v2.ipynb`, `BettingEdgeContinued.ipynb`.
- **`betting/predictions_tracker.csv`** — Master log of all predictions and outcomes. Auto-committed by GitHub Actions.
- **`betting/model_comparison.ipynb`** — Model comparison notebook (32 cells). Rebuilds the exact 79-feature production dataset from scratch, evaluates 5 model architectures + 3 ensemble variants + walk-forward CV. See dedicated section below.

### Feature Groups (betting/predict_betting.ipynb — helpers cell)
1. Schedule context: temperature, wind, surface, playoff flag, final-week flag
2. Rolling PBP stats: EPA, yards/play (5-game windows)
3. Strength of schedule: opponent win% (rolling 3-game and season-long)
4. All-Pro roster quality: weighted 3-year lookback, offense/defense split
5. Rolling performance: win%, points scored/allowed (5-game windows)

### LLM Agent
Developed in `betting/sports_betting_agent.ipynb`. Uses LlamaIndex `ReActAgent` with 5 tools (predictions lookup, injury reports, line movement, matchup history, confidence analysis). Output is cached per week as `betting/agent_analysis_2025_week{n}.json` and displayed in the dashboard as confidence overlays (HIGH/MEDIUM/SKIP).

### Data
- `betting/nfl_allpro_1997_2025.csv` — All-Pro roster data; updated manually each January
- `fantasy/features_dataset.csv` — Engineered feature dataset (built by `fantasy/data_pipeline.ipynb`)
- Live schedule, PBP, and stats pulled from `nflreadpy` at prediction time

### Automation
`.github/workflows/weekly_predictions.yml` runs `betting/predict_betting.ipynb` via papermill on three cron schedules (Mon 9am ET, Thu 9pm ET, Sun 7am ET) and commits the updated tracker. Supports manual dispatch with mode selection.

## Model Comparison Notebook (`betting/model_comparison.ipynb`)

**Purpose:** Compare model architectures on the exact 79-feature dataset used by production pkl, with ensemble variants and walk-forward cross-validation.

### Cell Structure

| Cells | Section |
|-------|---------|
| 0–1 | Title, config (`TRAIN_SEASONS=2014-2022`, `TEST_SEASONS=[2023,2024]`) |
| 2 | Imports (xgboost, lightgbm, sklearn, nflreadpy) |
| 3–11 | Data loading + full feature engineering pipeline (mirrors BettingEdge_v2.ipynb) |
| 12 | Feature matrix assembly, 79 `FEATURE_COLS`, train/test split, `roof_raw`/`surface_raw` saved before encoding |
| 13–14 | Real injury data from `nfl.load_injuries()` — Out=1.0, Doubtful=0.75 weighting |
| 15–24 | 4 models: XGBoost (prod pkl), Random Forest, Ridge, LightGBM |
| 25–26 | Ensemble: avg, weighted blend (tuned on 2022 holdout), Ridge meta-learner stack |
| 27 | Comparison table with 3 confidence tiers: all bets, medium (≥1pt edge), high (≥3pt edge) |
| 28 | Feature importance charts (XGBoost prod + Random Forest) |
| 29–35 | Walk-forward CV: 6 folds (test years 2020–2025), all models + Ensemble fixed75 |
| 39–42 | Production retrain section — Ensemble fixed75 only |

### Key Constraints

- **FinalCfg dataclass** must be defined before `joblib.load("xgboost_prod_model.pkl")` — it's embedded in the pkl. Definition is in cell 20.
- **`roof_raw` / `surface_raw`** — raw categorical strings saved before local OrdinalEncoding in cell 12. The production pipeline has its own encoder; pass raw strings to it, not locally-encoded integers.
- **Trailing space** in `"allpro_diff_home_def_away_off_3_years "` is intentional — matches the production pkl's column name exactly. Do not remove it.
- **ALLPRO_CSV** path tries both `nfl_allpro_1997_2025.csv` (CWD=`betting/`) and `betting/nfl_allpro_1997_2025.csv` (CWD=project root) — handled in cell 1.
- **LightGBM early stopping** uses a 15% held-out slice of training data, not the test set — to avoid test label leakage.
- **XGBoost (cv)** in walk-forward CV is retrained from scratch each fold. It is NOT the pre-trained pkl — that would be in-sample for all folds.
- **Editing:** Use Python + `json.load/dump`. The notebook is too large for the Read/NotebookEdit tools.

### Walk-Forward CV Results (2026-05-14, 6 folds 2020–2025)

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| Ensemble fixed75 | 52.8% | 3.1% | **Production model** — best mean, 0.75 XGB + 0.25 Ridge |
| LightGBM | 52.4% | 3.9% | Highest ceiling (55.4%), worst floor (44.9% in 2023) |
| Ridge | 52.0% | 3.6% | Best MAE (9.87), strongest single fold (57.5% in 2024) |
| XGBoost (cv) | 51.5% | 2.3% | Confirms production edge comes from injury features |
| Random Forest | 49.4% | 2.1% | Below 50% mean — not competitive |

Break-even: 52.4% ATS. 2023 was a universally hard season (all models underperformed fold 4). MLP removed from production after walk-forward showed 50.1% mean ATS (below break-even).

## Key Constraints
- The XGBoost model pipeline expects a `preprocessor` named step — don't change the pkl structure without retraining.
- `betting/nfl_allpro_1997_2025.csv` must be updated manually each January for the new season.
- Agent analysis JSON files are cached by week; regenerating them requires re-running the agent notebook and costs API calls.
- The dashboard reads the tracker CSV directly — column names and structure in `betting/predictions_tracker.csv` must stay consistent with `app.py` expectations.
- **Production model is Ensemble fixed75** — `ens_model_edge` drives the edge threshold and sort order. XGBoost and Ridge are the two other votes in `consensus_tier`. `consensus_tier` = HIGH when all 3 agree + `abs(ens_model_edge) ≥ 3pt`; MEDIUM when agree + `≥ 1pt`; PASS otherwise.
- **MLP has been removed** — deleted from `betting/models/`, stripped from `predict_betting.ipynb`. Walk-forward CV showed 50.1% mean ATS (below 52.4% break-even). Do not re-add it.
- **Fantasy projection CSVs MUST live in `fantasy/fantasy_projections/`** — never move them to `fantasy/` or any other location. `app.py` reads from `fantasy/fantasy_projections/projections_*.csv` and `predict_fantasy.ipynb` writes there via `_DIR / "fantasy_projections"`. Do not reorganize this path.

## Fantasy Model (`fantasy/`)

A half-PPR fantasy football points prediction system for NFL skill position players (QB, RB, WR, TE). Standalone ML pipeline with three notebooks run in order:

| Notebook | Input | Output | Purpose |
|----------|-------|--------|---------|
| `data_pipeline.ipynb` | nflreadpy (live) | `raw_dataset.csv` | Pulls and joins player stats, schedules, injury reports, depth charts, team metrics |
| `features.ipynb` | `raw_dataset.csv` | `features_dataset.csv` | Engineers rolling windows, trends, weather, injury/availability features |
| `model.ipynb` | `features_dataset.csv` | `models/*.pkl` | Trains and evaluates per-position XGBoost models |

**Datasets:**
- `raw_dataset.csv` — 34,907 rows × 84 columns (output of `data_pipeline.ipynb`)
- `features_dataset.csv` — 30,213 rows × 88 columns (output of `features.ipynb`; drops last week of each season + week-1 players with no rolling history)

Target: `target_half_ppr` (half-PPR points in week W+1).

**Model:** One XGBoost regressor per position (QB, RB, WR, TE). Train on 2020–2024, holdout 2025. Saved to `models/{position}_model.pkl` as `{'model': XGBRegressor, 'feature_cols': list}`.

**2025 holdout results** (vs 3-week rolling average baseline):

| Position | Train rows | Test rows | MAE | RMSE | Baseline MAE |
|----------|-----------|-----------|-----|------|--------------|
| QB | 2,723 | 571 | 7.11 | 8.77 | 7.49 |
| RB | 6,536 | 1,397 | 4.49 | 6.57 | 4.59 |
| WR | 10,464 | 2,215 | 3.92 | 5.39 | 4.06 |
| TE | 5,162 | 1,145 | 3.26 | 4.74 | 3.48 |

### data_pipeline.ipynb — Feature Groups

The notebook is structured in 4 parts + a master rebuild cell. Run cells top-to-bottom, or run the **Master Rebuild** cell (Part 3 → Part 4 boundary) to reconstruct `df` cleanly before running Part 4 steps.

**Part 1 — Raw Data Loading**
- `nfl.load_player_stats(SEASONS)` → filtered to REG, QB/RB/WR/TE
- `nfl.load_ff_opportunity(SEASONS)` → expected points (ffo_expected_pts, ffo_pts_diff)
- `nfl.load_schedules(SEASONS)` → Vegas lines, weather, home/away, rest days

**Part 2 — Base DataFrame Assembly**
- Merges player stats + FFO + Vegas/weather into base `df`
- Key columns: `spread_line`, `total_line`, `implied_team_total`, `wind`, `temp`, `is_home`

**Part 3 — Injury, Depth Chart & Surface Features**
- Player's own injury status: `injury_status_score`, `practice_status_score`
- Teammate availability: `starter_qb/rb/wr/te_availability`
- Opponent defensive starters: `opp_cb1/de1/lb1_availability` etc.
- Offensive line starters: `starter_tackle/guard/center_availability`
- Depth chart position: `depth_chart_position` (1 = starter)
- Surface: `is_turf` (binary)

**Part 4 — New Feature Groups** (added 2026-05-12)

| Step | Columns | Source | Notes |
|------|---------|--------|-------|
| Step 1 — Coach Win % | `coach_win_pct`, `opp_coach_win_pct` | `nfl.load_schedules(1999–2025)` | ~9.9% null for new coaches (<10 career games) — impute in features.ipynb |
| Step 2 — Offensive Metrics | `off_epa_roll4`, `off_yards_per_play_roll4`, `off_pass_rate_roll4`, `off_red_zone_rate_roll4` | `nfl.load_pbp(SEASONS)` | Rolling 4-game window, shift(1) to avoid leakage; ~1% null (week 1) |
| Step 3 — Defensive Metrics | `def_epa_allowed_roll4`, `def_yards_allowed_roll4`, `def_pass_rate_faced_roll4`, `def_red_zone_allowed_roll4` | same PBP | Joined on `opponent_team`; same null pattern as Step 2 |
| Step 4 — All-Pro Counts | `team_allpro_weighted`, `team_offense_allpro`, `team_defense_allpro`, `opp_allpro_weighted`, `opp_offense_allpro`, `opp_defense_allpro` | `betting/nfl_allpro_1997_2025.csv` | Weighted 3-year lookback (4/2/1); 0 nulls |

### Editing data_pipeline.ipynb
The notebook file exceeds the Read tool's token limit. **Always edit it via `python << 'PYEOF'` here-doc with `json.load/dump`** — do not use the NotebookEdit or Read tools. Use forward-slash paths (not `r"C:\..."`) inside here-docs to avoid unicode escape errors on Windows.

### predict_fantasy.ipynb — Pipeline Structure

| Cell | Section | What it does |
|------|---------|--------------|
| 0 | Title / usage | Markdown — papermill run instructions |
| 1 | Parameters | `TARGET_SEASON`, `TARGET_WEEK`, `POS_FILTER` (papermill-tagged) |
| 2 | Setup | Imports, `INJURY_MAP`, `PRACTICE_MAP`, path constants |
| 3 | Stat model names | Defines `QB/RB/WR/TE_STAT_NAMES` lists for per-stat prop models |
| 4 | Load Models | Loads main per-position `.pkl` files from `models/`; then loads all 8 per-stat models (e.g. `rb_rush_yards_model.pkl`) into `QB/RB/WR/TE_STAT_MODELS` dicts |
| 5 | Detect Week | Auto-detects next unplayed week if `TARGET_WEEK` is None |
| 6 | Upcoming Schedule | Pulls game context (spread, total, weather, home/away) for target week |
| 7 | Player History | Takes each player's most recent row from `features_dataset.csv` as rolling form; filters to `season >= TARGET_SEASON - 1` to drop retired/stale players |
| 8 | Helper — display names | Joins `player_display_name` from nflreadpy for readable output |
| 9 | Build feature rows | Merges player history with schedule context; handles missing cols with 0 fill |
| 10 | Injury status | Maps `injury_status` / `practice_status` strings to numeric scores via `INJURY_MAP` / `PRACTICE_MAP` |
| 11 | Depth chart | Loads `nfl.load_depth_charts()`; caps snapshot to before target week's first game to avoid retroactive promotions |
| 12 | Drop Out players | Removes players with `injury_status_score == 0` (ruled Out) |
| 13 | Generate Projections | Runs main per-position models for `pred_pts`; runs per-stat models appending `pred_qb_pass_yards`, `pred_qb_rush_yards`, `pred_rush_yards`, `pred_rec_yards`, `pred_wr_receptions`, `pred_wr_rec_yards`, `pred_te_receptions`, `pred_te_rec_yards` columns |
| 14 | Assemble output | Builds display DataFrame with `Proj Pts` + position-specific stat projection columns |
| 15 | Save Output | Writes `fantasy/fantasy_projections/projections_{season}_week{week:02d}.csv` |
| 16 | Projection Analysis | Distribution of projected pts by position; prop stat leaders (top 5 per stat); top-10 position scorecards with inline prop stats |
| 17 | Model Performance Summary | 2025 weeks 10–17 MAE, bias, correlation, and top-12 hit rate by position; prop stat model accuracy table with betting usability notes |

**Key fixes (2026-05-13):**
- `PRACTICE_MAP` keys updated to match nflreadpy's actual values (`"Did Not Participate In Practice"` etc.)
- Injury column renamed from `practice_primary_status` → `practice_status` to match nflreadpy schema
- Stale player filter: `latest["season"] >= TARGET_SEASON - 1` (drops anyone last seen 2+ seasons ago)
- Out player filter: drops players with `injury_status_score == 0` before projecting
- Depth chart snapshot capped to before `players["gameday"].min()` — prevents retroactive runs from using post-promotion depth charts (e.g. Shedeur Sanders appearing as CLE starter before his first game)

### Per-Stat Prop Models (`fantasy/models/`)

Output projections are saved to `fantasy/fantasy_projections/projections_{season}_week{week:02d}.csv`.

Eight additional XGBoost regressors trained to predict individual stats for prop betting reference. Trained with same train/test split as main models (2020–2024 train, 2025 holdout). Target for each is the stat in week W+1 (same shift-by-one pattern as `target_half_ppr`).

| Model file | Position | Stat predicted | Notes |
|-----------|---------|----------------|-------|
| `qb_pass_yards_model.pkl` | QB | passing yards | |
| `qb_rush_yards_model.pkl` | QB | rushing yards | |
| `rb_rush_yards_model.pkl` | RB | rushing yards | |
| `rb_rec_yards_model.pkl` | RB | receiving yards | |
| `wr_receptions_model.pkl` | WR | receptions | |
| `wr_rec_yards_model.pkl` | WR | receiving yards | |
| `te_receptions_model.pkl` | TE | receptions | |
| `te_rec_yards_model.pkl` | TE | receiving yards | |

Each pkl is `{'model': XGBRegressor, 'feature_cols': list}` — same structure as main models. Note: per-stat projections are independent models; their values will not sum exactly to the main `Proj Pts` prediction.

Trained and saved in `fantasy/model.ipynb` Step 2b (RB), 2c (WR), 2d (TE), 2e (QB).

### features.ipynb — Structure

| Cell | Section | What it does |
|------|---------|--------------|
| 0 | Title | Markdown header |
| 1 | Setup | Imports, load `raw_dataset.csv` |
| 2–3 | Target Variable | Computes `fantasy_points_half_ppr`; shifts to create `target_half_ppr` (next week's score) |
| 4–5 | Rolling Features | 3/5-game rolling averages + trend (3-week avg minus 5-week avg) for usage/production cols |
| 6 | Pts Allowed vs Position | Weekly pts allowed per team per position (matchup difficulty) |
| 7 | Coach Features | Imputes `coach_win_pct` / `opp_coach_win_pct` nulls; adds `is_new_coach` binary flag |
| 8–9 | SOS & Team Rankings | `opp_season_win_pct`, `opp_win_pct_roll4`; per-week `off_epa_rank`, `sos_rank` |
| 10–11 | Cleanup & Save | Drops null-target rows and week-1 rookies; saves `features_dataset.csv` |
| 12 | Inspection | Display shape and sample rows |

**Key constraints:**
- Never shuffle train/test split across seasons — always split on season boundaries to avoid leakage.
- Drop identity columns (`player_id`, `player_display_name`, `position`, `team`, `opponent_team`, `season`, `week`) before fitting.
- Always use `features_dataset.csv` as model input, not `raw_dataset.csv` (raw contains current-week stats that leak the target).
- `betting/nfl_allpro_1997_2025.csv` must be updated each January before re-running `data_pipeline.ipynb`.
- All rolling features in `data_pipeline.ipynb` use `shift(1).rolling(n, min_periods=1)` — never `shift(fill_value=0)` which leaks across group boundaries.
