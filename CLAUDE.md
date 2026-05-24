# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL Against-the-Spread (ATS) prediction system combining:
- Ensemble fixed75 as primary model (edge-setter), with XGBoost, Ridge, and LightGBM as the three direction voters
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
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE tuesday   # Update results + new predictions
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
- **`betting/predict_betting.ipynb`** — The prediction pipeline. 43 cells using a markdown → code → inline-test pattern for each section. Pulls live NFL data via `nflreadpy`, loads the shared feature-engineering pipeline from `betting/features.ipynb`, loads all three models from `betting/models/`, computes predicted margin vs. Vegas spread to find edges, and commits results to `betting/predictions_tracker.csv`. Run via papermill; `MODE` is the papermill parameter. (`betting/test_predict_betting.py` was deleted 2026-05-18 — replaced by the inline test cells.)

  | Cells | Section |
  |-------|---------|
  | 0–2 | Title, parameters |
  | 3–5 | Imports |
  | 6–8 | Paths, `FinalCfg`, model-path constants |
  | 9–11 | XGBoost model load |
  | 12–14 | Ensemble model load |
  | 15–17 | LightGBM model load |
  | 18–20 | Static data: AllPro CSV, `TEAM_MAP` |
  | 21–23 | `_norm_name` helper |
  | 24–26 | `get_week_info` helper |
  | 27–29 | `build_features` — loaded from `features.ipynb` via json-exec (Phase 1, 2026-05-23) |
  | 30–32 | `build_numeric_features` — also loaded from `features.ipynb` (acknowledged in cell 31; tested inline in cell 32) |
  | 33–34 | `run_predictions` — model inference (no test cell — needs live models) |
  | 35–37 | `update_results` — fill outcomes from completed games |
  | 38–40 | `log_predictions` — write to tracker CSV |
  | 41–42 | Run Pipeline — execution cell |
- **`betting/features.ipynb`** — **Single source of truth** for the 85-feature engineering pipeline (Groups 1–10) shared by both `predict_betting.ipynb` and `model_comparison.ipynb`. 53 cells using the markdown → code → inline-test pattern, with synthetic-data tests per group (all hermetic — no live nflreadpy calls in tests). Public names exposed after load: `build_features`, `build_numeric_features`, the per-group `_build_*` helpers, `FEATURE_COLS_85`, `PROD_FEATURES_35`, `TEAM_MAP`, `norm_name`, `canonicalize_ngs_team`. **Loading pattern** (used by `predict_betting.ipynb` cell 28 and `model_comparison.ipynb` cell 5): set `RUN_TESTS = False` then exec every code cell from the notebook json — see [editing notebooks](#editing-the-shared-features-notebook) below. The synthetic-data tests inside run when the notebook is opened standalone (RUN_TESTS=True by default) and are skipped during production runs; a closing cleanup cell removes the synth fixtures from consumer globals.
- **`app.py`** — Streamlit dashboard with 3 tabs: Weekly Predictions, Season Performance, Help & Guide. Reads `betting/predictions_tracker.csv` and cached `betting/agent_analysis_2025_week{n}.json` files for LLM agent reasoning overlays. Fantasy tab shows per-week projections per position with projected and actual stat columns (pass yds, rush yds, receptions, rec yds) that populate automatically after the week is played (fetched live from nflreadpy, cached 1 hour). Players who didn't play show "DNP" in all actual columns.
- **`betting/models/`** — All trained model pkl files:
  - `ensemble_prod_model.pkl` — **Primary model.** Ensemble fixed75: 0.75 XGBoost + 0.25 Ridge, trained 2014–2024. Sets the edge threshold and output sort order. Includes `scaler`, `feature_cols`, `roof_surface_encoder`, `xgb_model`, `ridge_model`, `xgb_weight`.
  - `xgboost_prod_model.pkl` — XGBoost sklearn pipeline (preprocessor + regressor). One of three direction voters.
  - `lgbm_prod_model.pkl` — LightGBM regressor. Third direction voter; independent signal from XGBoost (leaf-wise growth). Saved as `{'model': LGBMRegressor, 'feature_cols': list}`.
  - (Ridge is extracted from `ensemble_prod_model.pkl["ridge_model"]` at runtime — no separate pkl needed.)
- **`betting/archive/`** — Old model files and retired notebooks: `betting_model.pkl` (original XGBoost pkl), `BettingEdge_v2.ipynb`, `BettingEdgeContinued.ipynb`.
- **`betting/predictions_tracker.csv`** — Master log of all predictions and outcomes. Auto-committed by GitHub Actions.
- **`betting/model_comparison.ipynb`** — Model comparison notebook (32 cells). Rebuilds the exact 85-feature production dataset from scratch, evaluates 5 model architectures + 3 ensemble variants + walk-forward CV. See dedicated section below.

### Feature Groups (betting/predict_betting.ipynb — helpers cell)
1. Schedule context: surface, playoff flag, final-week flag
2. Rolling PBP stats: EPA, yards/play (5-game windows)
3. Strength of schedule: opponent win% (rolling 3-game and season-long)
4. All-Pro roster quality: weighted 3-year lookback, offense/defense split
5. Rolling performance: win%, points scored/allowed (5-game windows)
6. Situational PBP: sacks, turnovers, third-down rate (5-game windows)
7. QB switch flags
8. QB NGS features (NGS 2016+, manual PBP fallback for 2014–2015): prior-season passer rating (`home/away_pr_prev_year`, `diff_pr_prev_year`), completion % above expectation (`home/away_cpae_prev_year`, `diff_cpae_prev_year`), avg time to throw (`home/away_time_to_throw_prev_year`, `diff_time_to_throw_prev_year`)
9. Injuries: out-player count, All-Pro-weighted injury impact
10. Coach win%: career win% + rolling 3-season win% for home/away coach

### LLM Agent
Developed in `betting/sports_betting_agent.ipynb`. Uses LlamaIndex `ReActAgent` with 5 tools (predictions lookup, injury reports, line movement, matchup history, confidence analysis). Output is cached per week as `betting/agent_analysis_2025_week{n}.json` and displayed in the dashboard as confidence overlays (HIGH/MEDIUM/SKIP).

### Data
- `betting/nfl_allpro_1997_2025.csv` — All-Pro roster data; updated manually each January
- `fantasy/features_dataset.csv` — Engineered feature dataset (built by `fantasy/data_pipeline.ipynb`)
- Live schedule, PBP, and stats pulled from `nflreadpy` at prediction time

### Automation
`.github/workflows/weekly_predictions.yml` runs `betting/predict_betting.ipynb` via papermill on three cron schedules (Tue 9am ET, Thu 9pm ET, Sun 9am ET) and commits the updated tracker. Supports manual dispatch with mode selection.

## Model Comparison Notebook (`betting/model_comparison.ipynb`)

**Purpose:** Compare model architectures on the exact 85-feature dataset used by production pkl, with ensemble variants and walk-forward cross-validation.

### Cell Structure

70 cells, restructured 2026-05-20 into a **markdown → code → inline-test** pattern per section. Each section's test cell asserts shape/null/range invariants on the artifacts produced by that section, so plumbing regressions fail at the section boundary instead of leaking downstream. Test cells print `✓ Section N tests passed | ...`.

| Cells | Section |
|-------|---------|
| 0 | Title + notebook conventions |
| 1–3 | Section 1 — Configuration (`TRAIN_SEASONS=2014-2022`, `TEST_SEASONS=[2023,2024,2025]`, `ALLPRO_CSV` path) + test |
| 4–6 | Section 2 — Imports (xgb, lgb, sklearn, nflreadpy, matplotlib) + test |
| 7–9 | Section 3 — Data loading: schedules & PBP + test |
| 10–13 | Section 4 — Rolling off/def stats + long-format pivot + SOS (2 code cells) + test |
| 14–16 | Section 5 — All-Pro roster features (weighted 4/2/1, prev-year split off/def) + test |
| 17–19 | Section 6 — Prior-year passer rating from NGS (2016+) with manual fallback (2014–2015) + test |
| 20–22 | Section 7 — Rolling sacks / turnovers / 3rd-down rate + test |
| 23–25 | Section 8 — Coach win % (career-prior + roll3) + test |
| 26–28 | Section 9 — QB switch flag + test |
| 29–31 | Section 10 — Pivot to home_/away_ layout (`games` DataFrame) + test |
| 32–34 | Section 11 — Feature matrix assembly, 79 `FEATURE_COLS`, train/test split, raw categoricals saved + test |
| 35–37 | Section 12 — Real injury data from `nfl.load_injuries()` (Out=1.0, Doubtful=0.75) + test |
| 38–40 | Section 13 — Model 1: XGBoost prod pkl (`FinalCfg` defined here) + test |
| 41–43 | Section 14 — Model 2: Random Forest + test |
| 44–46 | Section 15 — Model 3: Ridge regression + test |
| 47–49 | Section 16 — Model 4: LightGBM (chronological 15% early-stop holdout) + test |
| 50–53 | Section 17 — Model 5: MLP (PyTorch, 3-layer feedforward) + test |
| 54–56 | Section 18 — Ensemble variants: avg, weighted (tuned on 2022 holdout), Ridge meta-learner stack + test |
| 57–60 | Section 19 — Head-to-head comparison (cmp table) + feature importance charts (XGBoost + RF) + test |
| 61–64 | Section 20 — Walk-forward CV: 6 folds (2020–2025), 5 models (includes MLP) + CV analysis markdown + test |
| 65–68 | Section 21 — Production retrain: ensemble fixed75 + standalone XGBoost pipeline + LightGBM + test (loads pkls back, checks keys) |
| 69 | Section 22 — 2025 live-test note + production setup summary |

### Key Constraints

- **FinalCfg dataclass** must be defined before `joblib.load("xgboost_prod_model.pkl")` — it's embedded in the pkl. Definition is in the Section 13 code cell (cell 39).
- **`roof_raw` / `surface_raw`** — raw categorical strings saved before local OrdinalEncoding in the Section 11 code cell (cell 33). The production pipeline has its own encoder; pass raw strings to it, not locally-encoded integers.
- **Trailing space** in `"allpro_diff_home_def_away_off_3_years "` is intentional — matches the production pkl's column name exactly. Do not remove it. (Section 11 test asserts this.)
- **ALLPRO_CSV** path tries both `nfl_allpro_1997_2025.csv` (CWD=`betting/`) and `betting/nfl_allpro_1997_2025.csv` (CWD=project root) — handled in the Section 1 code cell (cell 2). The Section 1 test asserts the CSV is reachable.
- **LightGBM early stopping** uses a 15% held-out slice of training data, not the test set — to avoid test label leakage.
- **XGBoost (cv)** in walk-forward CV is retrained from scratch each fold. It is NOT the pre-trained pkl — that would be in-sample for all folds.
- **Editing:** Use Python + `json.load/dump`. The notebook is too large for the Read/NotebookEdit tools.

### Walk-Forward CV Results (2026-05-20, 6 folds 2020–2025, **35-feature production subset**, tuned hyperparameters)

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| **Random Forest** | **57.1%** | 2.9% | Highest mean but still highest variance. Not in production. |
| **XGBoost (cv) (α=2, λ=5)** | **56.9%** | **1.9%** | **CV winner on risk-adjusted basis.** Was 55.3% at 85 features — biggest gain from ablation. Direction voter. |
| LightGBM | 56.5% | 1.7% | Was 55.5% at 85 features. Direction voter. |
| Ridge (α=50) | 55.6% | 2.0% | Was 56.2% at 85 features. Ridge prefers more features — its L2 reg already handles noise. Direction voter. |
| MLP | 53.7% | 2.5% | Comparison only. Performance held roughly flat with feature reduction. |

Break-even: 52.4% ATS. **Feature set reduced from 85 → 35** on 2026-05-20 after an ablation study (`betting/experiments/feature_ablation.py`) showed dropping low-importance features improved AVG CV score by +1.3pp. Engineering still builds all 85 features for analysis; only the top 35 (ranked by combined XGB gain + Ridge |coef| + LGB gain) are passed to model training via `PROD_FEATURES_35` in `model_comparison.ipynb` cell 33. Hyperparameter tuning sweep (2026-05-20) confirmed Ridge α=10→50 and XGBoost reg_alpha 1→2 / reg_lambda 3→5. Ensemble fixed75 is not in the CV loop — it is the edge-setter, not a direction voter.

## Key Constraints
- The XGBoost model pipeline expects a `preprocessor` named step — don't change the pkl structure without retraining.
- `betting/nfl_allpro_1997_2025.csv` must be updated manually each January for the new season.
- Agent analysis JSON files are cached by week; regenerating them requires re-running the agent notebook and costs API calls.
- The dashboard reads the tracker CSV directly — column names and structure in `betting/predictions_tracker.csv` must stay consistent with `app.py` expectations.
- **Prediction display convention (sportsbook style)** — In `app.py` game cards (around line 666), the PREDICTED column shows the favored team with a **negative** number and the underdog with a **positive** number, mirroring how sportsbooks display spreads. Internally `predicted_margin` / `ens_predicted_margin` are still the model's home_margin estimate (positive = home wins by that much), so the display logic negates for the home team and passes through for the away team:
  ```python
  top_predicted = fmt(-predicted)   # home team display (favored when predicted > 0)
  bot_predicted = fmt(predicted)    # away team display
  ```
  **Do NOT flip these back to the "natural" model orientation.** Users expect sportsbook-style display. The underlying model output, `model_edge` columns, `consensus_tier` logic, and all correctness/backtesting math operate on the unmodified home_margin convention — only the per-team display is flipped. The same pattern applies to SPREAD (`top_spread = fmt(-spread)`, `bot_spread = fmt(spread)`) since `spread_line` in the tracker is the Vegas-predicted home margin, not the sportsbook line.
- **Production model is Ensemble fixed75** — `ens_model_edge` drives the edge threshold and sort order. XGBoost, Ridge, and LightGBM are the three direction voters in `consensus_tier`. `consensus_tier` = HIGH when all 3 agree + `abs(ens_model_edge) ≥ 3pt`; MEDIUM when agree + `≥ 1pt`; PASS otherwise.
- **MLP is comparison-only** — present in `model_comparison.ipynb` Section 17 for benchmarking. Not in `betting/models/` and not used by `predict_betting.ipynb`. Walk-forward CV with 85 features shows 53.9% mean ATS (above 52.4% break-even), but its edge filter adds minimal signal vs. the ensemble (53.8% high vs 53.6% all). Do not add it to production.
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
- `features_dataset.csv` — 39,607 rows × 97 columns (output of `features.ipynb`; drops last week of each season + week-1 players with no rolling history)

Target: `target_half_ppr` (half-PPR points in week W+1).

**Model:** One XGBoost regressor per position (QB, RB, WR, TE). Train on 2020–2024, holdout 2025. Saved to `models/{position}_model.pkl` as `{'model': XGBRegressor, 'feature_cols': list}`.

**2025 holdout results** (vs 3-week rolling average baseline):

| Position | Train rows | Test rows | MAE | RMSE | Baseline MAE |
|----------|-----------|-----------|-----|------|--------------|
| QB | 2,781 | 571 | 6.99 | 8.60 | 7.49 |
| RB | 6,652 | 1,397 | 4.48 | 6.45 | 4.59 |
| WR | 10,643 | 2,215 | 3.91 | 5.37 | 4.06 |
| TE | 5,265 | 1,145 | 3.17 | 4.64 | 3.48 |

### Known Next Improvements

- **Include 2025 in training** — currently `TRAIN_SEASONS = [2020–2024]` with 2025 as the holdout. Once the 2025 season is complete, move it into training and use 2026 (or a rolling holdout) for evaluation. Update `TRAIN_SEASONS` in `model.ipynb` cell 3, retrain with `retrain_models.py`, and update the holdout results table above. This is the highest-ROI change remaining — it adds ~3,000 rows per model.
- **Rebuild raw_dataset.csv annually** — re-run `data_pipeline.ipynb` each offseason to pull fresh nflreadpy data (new season stats, updated injury history, depth charts). Then re-run `features.ipynb` and retrain.

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
| 1–2 | Parameters | `TARGET_SEASON`, `TARGET_WEEK`, `POS_FILTER` (papermill-tagged) |
| 3–4 | Setup | Imports, `INJURY_MAP`, `PRACTICE_MAP`, path constants |
| 5–6 | Load Models | Loads main per-position `.pkl` files from `models/`; then loads all 8 per-stat models (e.g. `rb_rush_yards_model.pkl`) into `QB/RB/WR/TE_STAT_MODELS` dicts |
| 7–8 | Detect Week | Auto-detects next unplayed week if `TARGET_WEEK` is None |
| 9–10 | Upcoming Schedule | Pulls game context (spread, total, weather, home/away) for target week |
| 11–12 | Player History & Live Defensive Metrics | Takes each player's most recent row from `features_dataset.csv` as rolling form; filters to `season >= TARGET_SEASON - 1`. Builds live `opp_def` from `nfl.load_pbp([TARGET_SEASON])`: last 4 completed games per team → rolling defensive means. Computes live coach win%, `opp_season_win_pct`. Joins display names, merges feature rows, fills missing cols with 0. Falls back to `features_dataset.csv` if PBP unavailable. |
| 13–14 | Injury & Depth Chart | Maps `injury_status` / `practice_status` strings to numeric scores via `INJURY_MAP` / `PRACTICE_MAP`. Loads `nfl.load_depth_charts()`; caps snapshot to before target week's first game to avoid retroactive promotions. Removes players with `injury_status_score == 0` (ruled Out). |
| 15–16 | Generate Projections | Runs main per-position models for `pred_pts`; runs per-stat models appending `pred_qb_pass_yards`, `pred_qb_rush_yards`, `pred_rush_yards`, `pred_rec_yards`, `pred_wr_receptions`, `pred_wr_rec_yards`, `pred_te_receptions`, `pred_te_rec_yards` columns. Assembles display DataFrame with `Proj Pts`. Writes `fantasy/fantasy_projections/projections_{season}_week{week:02d}.csv`. |
| 17–18 | Projection Analysis | Distribution of projected pts by position; prop stat leaders (top 5 per stat); top-10 position scorecards with inline prop stats |
| 19 | Model Performance Summary | 2025 weeks 10–17 MAE, bias, correlation, and top-12 hit rate by position; prop stat model accuracy table with betting usability notes |

**Key fixes (2026-05-13):**
- `PRACTICE_MAP` keys updated to match nflreadpy's actual values (`"Did Not Participate In Practice"` etc.)
- Injury column renamed from `practice_primary_status` → `practice_status` to match nflreadpy schema
- Stale player filter: `latest["season"] >= TARGET_SEASON - 1` (drops anyone last seen 2+ seasons ago)
- Out player filter: drops players with `injury_status_score == 0` before projecting

**Key fixes (2026-05-16):**
- `opp_def` defensive metrics now built live from `nfl.load_pbp([TARGET_SEASON])` — last 4 completed games per team, `week < TARGET_WEEK`. Replaces stale `features_dataset.csv` lookup. Falls back to old method if PBP unavailable (cell 12).
- `coach_win_pct`, `is_new_coach`, `opp_coach_win_pct`, `opp_is_new_coach` — now computed live from full schedule history (1999–TARGET_SEASON), looking up the current week's coaches from the upcoming schedule (cell 12).
- `opp_season_win_pct` — now computed live from TARGET_SEASON completed games, giving the opponent's actual current-season win% going into TARGET_WEEK (cell 12).
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
| 1–2 | Setup | Imports, load `raw_dataset.csv` |
| 3–5 | Target Variable | Computes `fantasy_points_half_ppr`; shifts to create `target_half_ppr` (next week's score) |
| 6–8 | Rolling Features | 3/5-game rolling averages + trend (3-week avg minus 5-week avg) for usage/production cols |
| 9–10 | Pts Allowed vs Position | Weekly pts allowed per team per position (matchup difficulty) |
| 11–12 | Coach Features | Imputes `coach_win_pct` / `opp_coach_win_pct` nulls; adds `is_new_coach` binary flag |
| 13–17 | SOS & Team Rankings | `opp_season_win_pct`, `opp_win_pct_roll4`; Vegas spread features; per-week `off_epa_rank`, `sos_rank`; drops null-target rows |
| 18–19 | Cleanup & Save | Saves `features_dataset.csv` |
| 20–21 | Inspection | Display shape and sample rows |

**Key constraints:**
- Never shuffle train/test split across seasons — always split on season boundaries to avoid leakage.
- Drop identity columns (`player_id`, `player_display_name`, `position`, `team`, `opponent_team`, `season`, `week`) before fitting.
- Always use `features_dataset.csv` as model input, not `raw_dataset.csv` (raw contains current-week stats that leak the target).
- `betting/nfl_allpro_1997_2025.csv` must be updated each January before re-running `data_pipeline.ipynb`.
- All rolling features in `data_pipeline.ipynb` use `shift(1).rolling(n, min_periods=1)` — never `shift(fill_value=0)` which leaks across group boundaries.

## DFS Lineup Optimizer (`fantasy/dfs/`)

ILP-based DraftKings NFL Classic lineup optimizer. Uses our weekly fantasy `projected_pts` as the value signal and solves salary-capped roster selection as a binary integer program. Requires `pulp` (added to `requirements.txt`).

### Notebooks

| Notebook | Purpose |
|----------|---------|
| `optimizer.ipynb` | Documents the ILP formulation, all helper functions, and fuzzy name-matching logic. Reference / library notebook. |
| `dfs_pipeline.ipynb` | Weekly workflow: load DK salary CSV → merge projections → analyze player pool → optimize lineup → export. Papermill-compatible with `CSV_PATH`, `SEASON`, `WEEK`, `BUDGET`, `LOCKED`, `EXCLUDED` parameters. |

**To run each week:**
```bash
papermill fantasy/dfs/dfs_pipeline.ipynb /tmp/dfs_out.ipynb -p CSV_PATH dk_salaries.csv
```
Download the salary CSV from any DK NFL Classic contest lobby → *Export to CSV*.

### How It Works

- `merge_projections()` fuzzy-matches DK player names to our `projected_pts` (cutoff 0.72 on normalised strings). Unmatched players fall back to DK's season `AvgPointsPerGame`, flagged as `dk_avg` in the pool table.
- **DST always uses DK's season average** — no team-defense model yet.
- ILP maximises total projected points subject to: 1 QB / 2+ RB / 3+ WR / 1+ TE / 1 DST / 9 total / $50k cap / max 8 from one team. The FLEX slot is filled implicitly by the solver.

### Key Constraints

- **Run `predict_fantasy.ipynb` first** — the pipeline reads `fantasy/fantasy_projections/projections_{season}_week{week:02d}.csv`. No projection file = no optimizer input.
- **Name matching is fuzzy** — review `dk_avg`-flagged players in the pipeline output before finalising the lineup.
- **Edit notebooks via Python `json.load/dump`** — same constraint as all other notebooks in this repo.

## Completed Work

**2026-05-23 (feature-engineering dedup, Phase 1):**
- Created `betting/features.ipynb` (51 cells, markdown → code → inline-test pattern) as the **single source of truth** for the 85-feature engineering pipeline. Public surface: `build_features`, `build_numeric_features`, all 10 `_build_*` per-group helpers, `FEATURE_COLS_85`, `PROD_FEATURES_35`, `TEAM_MAP`, `norm_name`, `canonicalize_ngs_team`. Each per-group helper has its own test cell exercising synthetic schedule + PBP + AllPro fixtures (Andy Reid wins 4/4 → roll3 = 1.0, KC offense AllPro 2024 → weight 4 in 2025, etc.). All 14 test cells pass.
- **Slimmed `predict_betting.ipynb` cell 28 from 36 KB → 1.2 KB** — replaced the giant `build_features` definition with a json-load + exec loop that pulls every code cell from `features.ipynb` into the kernel's namespace. Set `RUN_TESTS = False` before the load so the synth tests inside `features.ipynb` skip during production runs. Cell 31 (`build_numeric_features`) became a one-line acknowledgement; cell 34 (`run_predictions`) gained a `required_features=list(dict.fromkeys(model_features + ens_feat_cols + lgbm_feat_cols))` arg to preserve the prior missing-column warning behaviour exactly.
- Verified end-to-end: `papermill betting/predict_betting.ipynb -p MODE thursday` runs cleanly through all imports, the new loader, every inline test, model loads, schedule loading (285 current-season games), and only stops at the "season is over" check (correct in May 2026). The existing test cells inside `predict_betting.ipynb` still pass against the loaded-from-features functions: `✓ build_features: 1 game row, 119 columns, key features present`.
- **Phase 2a (same day) — dedup constants + pure helpers in `model_comparison.ipynb`.** Added a json+exec loader block at the end of Section 2 (cell 5) that pulls every code cell of `features.ipynb` into the kernel namespace, plus a verification assertion in Section 2's test (cell 6). Removed three local duplicates: cell 15's `TEAM_MAP` (was 12 entries; the shared version has 17, with 5 extra pre-2002 abbrevs absent from the AllPro CSV — verified no-op on training data); cell 18's `_canonicalize_ngs_team` (replaced by the shared `canonicalize_ngs_team`, aliased back to the underscore name in the loader); cell 33's `FEATURE_COLS` and `PROD_FEATURES_35` lists. Net diff: `-372 lines` from mc. **Verified pkl byte-equivalence** by snapshotting current md5s, running mc end-to-end (full retrain), and confirming all 3 pkls (`ensemble_prod_model.pkl`, `xgboost_prod_model.pkl`, `lgbm_prod_model.pkl`) hash to the exact baseline values (`+0` size delta on each). First retrain showed pkl drift; root-caused to having reordered `PROD_FEATURES_35` in `features.ipynb` for "readability" — list order determines `X_tr` column order which determines pkl bytes. Restored canonical ablation-study order (memory `[[feature-list-order-is-contract]]`). Second retrain matched md5s exactly.
- **Phase 2b (deferred / pending decision)** — the per-group `_build_*` function logic still differs in shape between the two notebooks (mc uses `shift(1).rolling(5)` over all games; predict_betting uses `rolling(5).nth(-1)` on the latest team-game — equivalent values, different code shape). Dedup'ing those would require adding training-mode variants to `features.ipynb` and re-running the pkl byte-equivalence check. Lower-priority than Phase 2a because the constants and pure helpers were the highest-drift surface; per-group logic changes already require retraining and tend to be caught by reviewers grepping both notebooks.
- Why this matters: previously the 85-feature build existed in two places (`predict_betting.ipynb` cell 28 and `model_comparison.ipynb` Sections 4–11) that had to stay hand-synced. Drift had caused corrupt-cell incidents, stale comments, and ongoing risk. With features.ipynb as source of truth, edits land in one place and a 14-cell test suite catches plumbing breakage immediately.

**2026-05-23 (Phase 1+2a code-review fixes):**
- After landing Phase 1+2a, did a structured code review and shipped 5 fixes (all behaviour-preserving — pkls still byte-identical):
  - **Cell 5 (features.ipynb)**: gated the "✓ Imports loaded." print behind `RUN_TESTS`; the import asserts still run always (cheap, catches missing nflreadpy). Removes noise from consumer-notebook CI logs.
  - **Cell 36 (`_build_passer_rating`)**: added optional `ngs_data` parameter. Default `None` keeps the live `nfl.load_nextgen_stats` behaviour for production callers; tests now pass a pre-fab dataframe instead.
  - **Cell 37 (passer-rating test)**: now hermetic — uses a synthetic NGS stub (KC=102.5 / BUF=88.3 ratings, etc.), no network call, deterministic in any CI environment.
  - **Cells 50–51 (new)**: closing markdown + code cell that `globals().pop()`s `_synth_schedule`, `_synth_pbp`, `_synth_allpro` when loaded with `RUN_TESTS=False`. Keeps consumer namespaces from accumulating test scaffolding. Total cell count: 51 → 53.
  - **Both consumer loaders** (`predict_betting.ipynb` cell 28 + `model_comparison.ipynb` cell 5): unified the path-resolution to use a `_FEATURE_NB_CANDIDATES` list with `next(p for p if p.exists())`. Same pattern in both files. Works whether CWD is project root or `betting/`. Cleanup switched from fragile `del` to idempotent `globals().pop(name, None)`. Error message now lists every path tried.
- Verified: `papermill betting/features.ipynb` runs all 14 inline tests (all pass, including the now-hermetic passer-rating test). `papermill betting/predict_betting.ipynb -p MODE thursday` still runs through to the "season is over" check. mc retrain still produces byte-identical pkls.

### Editing the shared features notebook

- `betting/features.ipynb` is ~80 KB but well within Read/NotebookEdit tool limits. Edit cells via the notebook tools or `json.load/dump`, either is fine.
- After editing, run it standalone via `papermill betting/features.ipynb /tmp/_out.ipynb` to verify all 14 inline tests still pass. The papermill run takes ~5 seconds.
- If you change any name in the public surface (`build_features`, `FEATURE_COLS_85`, etc.), update the loader in `predict_betting.ipynb` cell 28 and the cell-structure tables in this CLAUDE.md.

**2026-05-20 (continued, feature ablation):**
- Ran feature ablation study (`betting/experiments/feature_ablation.py` / `betting/experiments/feature_ablation_results.json` / `betting/experiments/feature_importance_ranking.csv`): ranked all 85 features by combined importance (XGB gain + Ridge |coef| + LGB gain), then tested walk-forward CV at 85, 75, 65, 55, 45, 35, 25 feature subsets. Best AVG score at 35 features (+1.3pp over full 85). XGBoost gained the most (+1.6pp mean ATS); Ridge slightly regressed (its L2 reg already handles noise). LightGBM and Random Forest also improved.
- **Reduced production feature set from 85 → 35** via new `PROD_FEATURES_35` list in `model_comparison.ipynb` cell 33. Engineering still computes all 85 features into `g`; only the top 35 are passed to model training (`avail` is filtered). All 3 production pkls retrained. New CV: XGBoost (cv) 55.3% → **56.9%** mean ATS, LightGBM 55.5% → 56.5%, Ridge 56.2% → 55.6%. Hold-out 2023-2025: XGBoost prod 60.9% → 61.4% ATS overall, high-confidence 74.3% → 75.2%.
- Notable features dropped: all 3 new NGS CPAE/TTT features (added earlier today — ranked bottom 15), `roof`/`surface`, `home_rest`/`away_rest`, `is_final_week`, `is_away_qb_new`, several individual-team allpro features (the diff versions ranked higher).
- Stale comments fixed: `model_comparison.ipynb` cell 33 ("Exact 79 production feature columns" → "All 85 engineered feature columns"); `predict_betting.ipynb` cell 28 docstring ("Builds all 79 features" → "Builds all 85 features").

**2026-05-20 (continued, hyperparameter tuning):**
- Ran walk-forward CV hyperparameter sweep on all 5 models (30 configs × 6 folds, see `betting/experiments/tune_hyperparams.py` / `betting/experiments/hyperparam_sweep_results.json`). Optimized for Mean ATS − Std (risk-adjusted score). Best per family: Ridge α=50 (was α=10), XGBoost α=2/λ=5 (was α=1/λ=3), RF max_features=0.3 (not in production), LightGBM unchanged (baseline already optimal), MLP smaller (128/64/32 — not in production).
- 3-seed stability check on XGBoost (`betting/experiments/tune_xgb_seeds.py`) confirmed the α=2/λ=5 std reduction is robust across seeds (Δscore +0.35pp averaged); the mean improvement was within seed noise. Applied anyway for the std gain.
- **Updated production hyperparameters:** Ridge α 10→50, XGBoost reg_alpha 1→2, reg_lambda 3→5. Updated in both `betting/predict_betting.ipynb` (FinalCfg) and `betting/model_comparison.ipynb` (cells 40, 46, 62, 66, 67). Retrained all 3 production pkls. New CV (above): Ridge 55.4→56.2% mean ATS, XGBoost std 1.7→1.4%.

**2026-05-20 (continued):**
- Added 6 new QB NGS features (Group 8): `home/away/diff_cpae_prev_year` (completion % above expectation) and `home/away/diff_time_to_throw_prev_year` — feature count 79 → 85. Source: `nfl.load_nextgen_stats(stat_type="passing")` same as passer rating; CPAE and TTT unavailable pre-2016 (filled with NGS median). Extended `_build_passer_rating` helper in `predict_betting.ipynb` (cell 28) and Section 6 (cells 17–19) in `model_comparison.ipynb`. All 3 production pkls retrained.
- Renamed `home/away_qbr_prev_year` → `home/away_pr_prev_year` (completing the 2026-05-18 rename that only updated the diff column). All notebooks, pkls, and CLAUDE.md updated.
- Applied 11 code-review fixes to `model_comparison.ipynb`: OrdinalEncoder fit on train only; `fillna(0)` for sacks/turnovers/third-down after left-join; stale "77" comment; orphaned comment; 2022 "holdout" label; missing-2025 warning; `len(avail)==85` assert in cells 34 and 37; archive pkl fallback removed; `len(tr_stack)==len(y_tr)` guard; NGS dedup assert.
- Re-enabled MLP in `model_comparison.ipynb` (Section 17, cell 52 raw→code + Section 17 test cell inserted). Added MLP to walk-forward CV loop (Section 20) with per-fold `StandardScaler` and 150-epoch `BettingMLP` training. CV result: 53.9% mean ATS ± 1.7% (was 50.1% at 79 features) — above break-even with 85 features, but edge filter barely discriminates. Notebook now 70 cells. Updated CV results table above.

**2026-05-20:**
- Restructured `betting/model_comparison.ipynb` from 45 cells to 68 cells (markdown → code → inline-test pattern, matching `predict_betting.ipynb`)
- Added 20 inline test cells (one per section) asserting shape/null/range invariants — features = 85, FEATURE_COLS trailing-space preserved, ATS/MAE in plausible ranges, pkl keys present, etc.
- Standardised section markdown headers with Purpose / Inputs / Outputs / Tests
- Updated CLAUDE.md cell-structure table to reflect the 22 numbered sections
- **Recovered 3 corrupt cells in `predict_betting.ipynb`** (cells 27, 28, 36) — each character had been stored as a separate list item with a trailing `\n`, making the notebook fail to compile. Reconstruction: `''.join(item[0] for item in source_list)`. Corruption was introduced by commit `84cbcb2` (May 19 "updates"); not noticed until 2026-05-20.
- **Switched passer-rating source to NFL Next Gen Stats** in both `predict_betting.ipynb` (`_build_passer_rating` helper) and `model_comparison.ipynb` (Section 6). `nfl.load_nextgen_stats(stat_type="passing")` is now primary for 2016+; the manual NFL-passer-rating formula on PBP remains as the fallback for 2014–2015 (NGS does not cover pre-2016) and for any year where the NGS load fails. NGS team abbreviations are canonicalised (`LAR`→`LA`; `LV`→`OAK` for 2016–2019; `LAC`→`SD` for 2016) so the per-season team merge succeeds. After switch: 313 NGS team-seasons + 64 manual = 377 total team-seasons; median passer rating 90.4. All 3 production pkls retrained against the NGS-sourced feature.

**2026-05-18:**
- Renamed all three passer-rating features: `home_qbr_prev_year` → `home_pr_prev_year`, `away_qbr_prev_year` → `away_pr_prev_year`, `diff_qbr_prev_year` → `diff_pr_prev_year` in `predict_betting.ipynb` and `model_comparison.ipynb`
- Added `home_coach_win_pct_roll3` / `away_coach_win_pct_roll3` (rolling 3-season window) — feature count now 79 (later expanded to 85)
- Restructured `predict_betting.ipynb` from 11 cells to 43 cells (markdown → code → inline-test pattern)
- Deleted `betting/test_predict_betting.py` — replaced by inline test cells in the notebook
- Fixed all known issues from 2026-05-15 code review (see Known Issues below for full list)

**2026-05-16:**
- Fixed `opp_def` live defensive metrics join in `predict_fantasy.ipynb`
- Regenerated `raw_dataset.csv` + `features_dataset.csv`; retrained all fantasy models (MAE: QB 6.99, RB 4.48, WR 3.91, TE 3.17)
- Full code review — all confirmed bugs fixed


## Known Issues

- **DK lineup upload CSV format may be wrong (Medium)** — `dfs_pipeline.ipynb` exports only a `Name` column. DraftKings' actual lineup import format requires position slots as separate columns (QB, RB, RB, WR, WW, WR, TE, FLEX, DST). Verify against DK's current template before using the export.

---

### Next Steps

1. **DST projection model** — train on defensive EPA allowed, implied team total, home/away, and surface. Replace the `dk_avg` fallback for DST so all 9 slots use our model.
2. **Multi-lineup GPP generator** — produce N distinct lineups for tournament play using ownership-diversity constraints (force variation in at least the FLEX pick and one anchor position across lineups).
3. **Game-stacking constraints** — add optional ILP constraints to co-select 2+ players from the same game (QB + WR1 + opponent pass-catcher), exploiting positive score correlation in high-total matchups.
4. **Ownership leverage weighting** — scale `proj_pts` by inverse projected ownership so the optimizer differentiates from the field in large-field GPPs.
5. **Salary movement signal** — compare current DK salary to prior-week salary; large drops may indicate recency information (injury, role change) the season average hasn't priced in yet.
6. **Automated salary fetching** — replace the manual CSV download with a scraper or third-party API so the pipeline runs fully programmatically.
7. **End-to-end automation** — chain `predict_fantasy.ipynb` → `dfs_pipeline.ipynb` in a single papermill call or GitHub Actions step so DFS lineups generate automatically after weekly projections update.
