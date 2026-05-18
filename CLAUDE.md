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
- **`betting/predict_betting.ipynb`** — The prediction pipeline. Pulls live NFL data via `nflreadpy`, engineers features, loads all three models from `betting/models/`, computes predicted margin vs. Vegas spread to find edges, and commits results to `betting/predictions_tracker.csv`. Run via papermill; `MODE` is the papermill parameter.
- **`app.py`** — Streamlit dashboard with 3 tabs: Weekly Predictions, Season Performance, Help & Guide. Reads `betting/predictions_tracker.csv` and cached `betting/agent_analysis_2025_week{n}.json` files for LLM agent reasoning overlays. Fantasy tab shows per-week projections per position with projected and actual stat columns (pass yds, rush yds, receptions, rec yds) that populate automatically after the week is played (fetched live from nflreadpy, cached 1 hour). Players who didn't play show "DNP" in all actual columns.
- **`betting/models/`** — All trained model pkl files:
  - `ensemble_prod_model.pkl` — **Primary model.** Ensemble fixed75: 0.75 XGBoost + 0.25 Ridge, trained 2014–2024. Sets the edge threshold and output sort order. Includes `scaler`, `feature_cols`, `roof_surface_encoder`, `xgb_model`, `ridge_model`, `xgb_weight`.
  - `xgboost_prod_model.pkl` — XGBoost sklearn pipeline (preprocessor + regressor). One of three direction voters.
  - `lgbm_prod_model.pkl` — LightGBM regressor. Third direction voter; independent signal from XGBoost (leaf-wise growth). Saved as `{'model': LGBMRegressor, 'feature_cols': list}`.
  - (Ridge is extracted from `ensemble_prod_model.pkl["ridge_model"]` at runtime — no separate pkl needed.)
- **`betting/archive/`** — Old model files and retired notebooks: `betting_model.pkl` (original XGBoost pkl), `BettingEdge_v2.ipynb`, `BettingEdgeContinued.ipynb`.
- **`betting/predictions_tracker.csv`** — Master log of all predictions and outcomes. Auto-committed by GitHub Actions.
- **`betting/model_comparison.ipynb`** — Model comparison notebook (32 cells). Rebuilds the exact 77-feature production dataset from scratch, evaluates 5 model architectures + 3 ensemble variants + walk-forward CV. See dedicated section below.

### Feature Groups (betting/predict_betting.ipynb — helpers cell)
1. Schedule context: surface, playoff flag, final-week flag
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
`.github/workflows/weekly_predictions.yml` runs `betting/predict_betting.ipynb` via papermill on three cron schedules (Tue 9am ET, Thu 9pm ET, Sun 9am ET) and commits the updated tracker. Supports manual dispatch with mode selection.

## Model Comparison Notebook (`betting/model_comparison.ipynb`)

**Purpose:** Compare model architectures on the exact 77-feature dataset used by production pkl, with ensemble variants and walk-forward cross-validation.

### Cell Structure

| Cells | Section |
|-------|---------|
| 0–1 | Title, config (`TRAIN_SEASONS=2014-2022`, `TEST_SEASONS=[2023,2024]`) |
| 2 | Imports (xgboost, lightgbm, sklearn, nflreadpy) |
| 3–11 | Data loading + full feature engineering pipeline (mirrors BettingEdge_v2.ipynb) |
| 12 | Feature matrix assembly, 77 `FEATURE_COLS`, train/test split, `roof_raw`/`surface_raw` saved before encoding |
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

### Walk-Forward CV Results (2026-05-15, 6 folds 2020–2025)

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| LightGBM | 53.0% | 4.1% | **CV winner** — highest mean, but highest floor risk (44.2% in 2023). Direction voter. |
| Ridge | 52.1% | 2.9% | Best MAE (9.83), strongest single fold (56.5% in 2024). Direction voter. |
| Random Forest | 51.3% | 2.5% | Below break-even mean — not in production |
| XGBoost (cv) | 51.2% | 1.8% | CV-retrained standalone; prod pkl (in ensemble) adds more signal |

Break-even: 52.4% ATS. 2023 was a universally hard season (all models underperformed fold 4). MLP removed from production after walk-forward showed 50.1% mean ATS (below break-even). Ensemble fixed75 is not in the CV loop — it is the edge-setter, not a direction voter.

## Key Constraints
- The XGBoost model pipeline expects a `preprocessor` named step — don't change the pkl structure without retraining.
- `betting/nfl_allpro_1997_2025.csv` must be updated manually each January for the new season.
- Agent analysis JSON files are cached by week; regenerating them requires re-running the agent notebook and costs API calls.
- The dashboard reads the tracker CSV directly — column names and structure in `betting/predictions_tracker.csv` must stay consistent with `app.py` expectations.
- **Production model is Ensemble fixed75** — `ens_model_edge` drives the edge threshold and sort order. XGBoost, Ridge, and LightGBM are the three direction voters in `consensus_tier`. `consensus_tier` = HIGH when all 3 agree + `abs(ens_model_edge) ≥ 3pt`; MEDIUM when agree + `≥ 1pt`; PASS otherwise.
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
| 1 | Parameters | `TARGET_SEASON`, `TARGET_WEEK`, `POS_FILTER` (papermill-tagged) |
| 2 | Setup | Imports, `INJURY_MAP`, `PRACTICE_MAP`, path constants |
| 3 | Stat model names | Defines `QB/RB/WR/TE_STAT_NAMES` lists for per-stat prop models |
| 4 | Load Models | Loads main per-position `.pkl` files from `models/`; then loads all 8 per-stat models (e.g. `rb_rush_yards_model.pkl`) into `QB/RB/WR/TE_STAT_MODELS` dicts |
| 5 | Detect Week | Auto-detects next unplayed week if `TARGET_WEEK` is None |
| 6 | Upcoming Schedule | Pulls game context (spread, total, weather, home/away) for target week |
| 7 | Player History & Live Defensive Metrics | Takes each player's most recent row from `features_dataset.csv` as rolling form; filters to `season >= TARGET_SEASON - 1`. Also builds live `opp_def` from `nfl.load_pbp([TARGET_SEASON])`: last 4 completed games per team → rolling defensive means. Falls back to `features_dataset.csv` if PBP unavailable. |
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

## Next Session Plan (2026-05-16)

All steps complete as of 2026-05-16.

1. ~~**Fix `opp_def` join**~~ — **Done 2026-05-16.**
2. ~~**Regenerate data + retrain fantasy models**~~ — **Done 2026-05-16.** MAE: QB 6.99, RB 4.48, WR 3.91, TE 3.17.
3. ~~**Markdown + documentation cleanup**~~ — **Done 2026-05-16.**
4. ~~**Final code review**~~ — **Done 2026-05-16.** Three rounds of progressively deeper review completed. All confirmed bugs fixed (see Known Issues below for full list).


## Known Issues — Not Yet Fixed

These were identified in a full code review (2026-05-15) but require design decisions or significant refactoring. Address before next season.

### Betting Pipeline (`predict_betting.ipynb`)

- ~~**Injury features only count `Out` (train used `Out + Doubtful×0.75`) (High)**~~ — **Fixed 2026-05-18.** Cell 8 Group 9 now filters to both `Out` and `Doubtful`, maps each to `{'Out': 1.0, 'Doubtful': 0.75}`, and multiplies the allpro historical weight by the status weight before summing.

- ~~**`home_qb_switch` and `is_home_qb_new` are identical (High)**~~ — **Fixed 2026-05-18.** Added a comment in cell 8 Group 7 noting the two features are currently synonymous. Differentiating their semantics requires retraining and is deferred to next offseason.

- ~~**Push counted as away cover in rolling cover rate (Medium)**~~ — **Fixed 2026-05-18.** Cell 8 Group 5 now uses `np.where(result == spread_line, np.nan, ...)` so pushes are excluded from both teams' cover rates instead of being attributed to the away team.

- ~~**`build_numeric_features` crashes on unknown roof/surface values (Medium)**~~ — **Fixed 2026-05-18.** Cell 8 now checks `enc.categories_` and maps any unknown value to the first known category before calling `enc.transform()`.

- ~~**Missing-feature check only covered XGBoost features (Medium)**~~ — **Fixed 2026-05-18.** Cell 8 `build_features` now checks the union of `model_features + ens_feat_cols + lgbm_feat_cols` and zero-fills any missing column across all three models.

- ~~**No warning when Week 1 history is empty (Medium)**~~ — **Fixed 2026-05-18.** Cell 8 prints an info message when `history.empty` so users know SOS/scoring/cover features will be zero-filled.

- ~~**Prediction refresh wipes already-filled results (Medium)**~~ — **Fixed 2026-05-18.** `log_predictions` now preserves `actual_margin`, `home_covered`, `model_correct`, `home_score`, `away_score`, `ens_model_correct`, `ridge_model_correct`, `lgbm_model_correct` from the old row before replacing the week's entry.

- ~~**New coach imputed as 0% win rate (Low)**~~ — **Fixed 2026-05-18.** Cell 8 Group 10 now fills NaN with `latest_coach_wp['coach_win_pct_prior'].mean()` (~0.5) instead of 0.

- ~~**No warning when backfilling a playoff week (Low)**~~ — **Fixed 2026-05-18.** Cell 8 Group 1 now prints a warning if any upcoming game has `game_type != 'REG'`.

- ~~**Redundant season schedule API call (Low)**~~ — **Fixed 2026-05-18.** Cell 10 now loads all schedules (1999–present) in a single `nfl.load_schedules` call and derives `full_schedule`, `coach_hist_df`, and `week_margin_lkp` from the same DataFrame. The duplicate `nfl.load_schedules([TARGET_SEASON])` call and the separate historical load have been removed.

- ~~**`TEAM_MAP` missing pre-2002 abbreviations (Low)**~~ — **Fixed 2026-05-18.** Added `"ARZ": "ARI"`, `"BLT": "BAL"`, `"CLV": "CLE"`, `"HST": "HOU"`, `"JAC": "JAX"` to cell 6.

- ~~**`TARGET_SEASON` needed manual update each year (Low)**~~ — **Fixed 2026-05-18.** Cell 2 now defaults `TARGET_SEASON = None`; cell 10 auto-detects the season from the current date (`year if month >= 7 else year - 1`).

- ~~**Injury–AllPro name matching is fragile (High)**~~ — **Fixed 2026-05-16.** `predict_betting.ipynb` cell 8 now normalizes both sides before joining: strips Unicode accents (`NFD` decomposition), lowercases, removes suffixes (Jr./Sr./II/III/IV/V) and punctuation. Confirmed fix: "Odell Beckham Jr." (AllPro) now matches "Odell Beckham" (injury report).

- ~~**`league_rolling_avg_abs_margin_by_week` train/inference mismatch (Medium)**~~ — **Fixed 2026-05-16.** `predict_betting.ipynb` cell 10 now pre-computes `week_margin_lkp`: average absolute margin per week number across 2014–TARGET_SEASON-1, matching the cross-season groupby used in training. `build_features()` and `run_predictions()` accept `week_margin_lkp` and use the lookup for the target week (falls back to the stale `.iloc[-1]` method if unavailable).

### Fantasy Pipeline (`predict_fantasy.ipynb`)

- ~~**`opp_def` join key is semantically wrong (Medium)**~~ — **Fixed 2026-05-16.** `predict_fantasy.ipynb` cell 12 now loads PBP for `TARGET_SEASON`, filters to `week < TARGET_WEEK`, takes each team's last 4 completed games, and computes rolling defensive means live. Falls back to the old features_dataset lookup if PBP is unavailable.

- ~~**`coach_win_pct`, `is_new_coach`, `opp_season_win_pct` are stale at inference (Medium)**~~ — **Fixed 2026-05-16.** `predict_fantasy.ipynb` cell 12 now loads full schedule history (1999–TARGET_SEASON), builds each coach's career win% up to just before TARGET_WEEK, looks up the current week's coaches from the upcoming schedule, and computes each opponent's current-season win% from completed games. Falls back to `features_dataset.csv` values if schedule load fails.

- ~~**`starter_qb_availability` is always 1.0 (High)**~~ — **Already fixed (pre-2026-05-16).** `data_pipeline.ipynb` cells 22–28 use `nfl.load_depth_charts()` with `depth_team == "1"` to identify the starting QB, not season targets. Verified: `raw_dataset.csv` has 3,832 non-1.0 rows (e.g., 2018 BUF Week 7 = 0.0, 2018 GB Week 2 = 0.3). Cell 20's old `starter_proxy` approach is dead code.

- ~~**`snap_pct` rolling groupby may have cross-season leakage (Low)**~~ — **Confirmed already correct (2026-05-16).** `data_pipeline.ipynb` cell 46 uses `groupby(['player_id', 'season'])` for both `snap_pct_roll3` and `snap_pct_roll5`. No leakage. No fix needed.

### App (`app.py`)

- ~~**Sleeper API makes up to 180 serial HTTP calls on cache miss (Medium)**~~ — **Fixed 2026-05-16.** Weekly matchup fetches within each season are now parallelised with `concurrent.futures.ThreadPoolExecutor(max_workers=18)`.

- ~~**Sleeper week fetch `break` stops processing on first failed week (High)**~~ — **Fixed 2026-05-16.** Changed `break` → `continue` so a failed week fetch is skipped rather than halting all subsequent weeks.

- ~~**Season-level ATS denominators use `len()` instead of `.notna().sum()` (Medium)**~~ — **Fixed 2026-05-16.** `app.py` Season Performance tab now uses `.notna().sum()` for `total_games`, `he_total`, `me_total`, `le_total`, `_ch_t`, `_cm_t`, `_cp_t` — prevents un-predicted games from inflating the denominator.

- ~~**`load_agent_analysis()` missing try/except (Low)**~~ — **Fixed 2026-05-16.** JSON parse errors on corrupt cache files now return `None` instead of crashing.

- ~~**Player search `str.contains()` without `regex=False` (Low)**~~ — **Fixed 2026-05-16.** A search string like "." previously matched all players.

- ~~**Manager selectbox with empty list crashes (Low)**~~ — **Fixed 2026-05-16.** Report Cards tab now shows an info message when `_h2h_managers` is empty.

- ~~**GitHub Actions: no concurrency guard, commit runs on failure (Low)**~~ — **Fixed 2026-05-16.** Added `concurrency: group: predictions` and `if: success()` on the commit step.

- ~~**`predict_fantasy.ipynb` injury filter drops NaN players (High)**~~ — **Fixed 2026-05-16.** Cell 14 now uses `injury_status_score.fillna(1.0) > 0.0` so players not on the injury report are treated as healthy instead of being dropped.

- ~~**`model.ipynb` RB per-stat models have no early stopping (Medium)**~~ — **Fixed 2026-05-16.** Cell 9 now uses 85/15 val split with `early_stopping_rounds=25`, matching main models and `retrain_models.py`.

- ~~**`data_pipeline.ipynb` FFO merge may create duplicate rows (Low)**~~ — **Fixed 2026-05-16.** Added `drop_duplicates(subset=["player_id","season","week"])` after FFO merges in cells 29 and 34.

- **DK lineup upload CSV format may be wrong (Medium)** — `dfs_pipeline.ipynb` exports only a `Name` column. DraftKings' actual lineup import format requires position slots as separate columns (QB, RB, RB, WR, WR, WR, TE, FLEX, DST). Verify against DK's current template before using the export.

---

### Next Steps

1. **DST projection model** — train on defensive EPA allowed, implied team total, home/away, and surface. Replace the `dk_avg` fallback for DST so all 9 slots use our model.
2. **Multi-lineup GPP generator** — produce N distinct lineups for tournament play using ownership-diversity constraints (force variation in at least the FLEX pick and one anchor position across lineups).
3. **Game-stacking constraints** — add optional ILP constraints to co-select 2+ players from the same game (QB + WR1 + opponent pass-catcher), exploiting positive score correlation in high-total matchups.
4. **Ownership leverage weighting** — scale `proj_pts` by inverse projected ownership so the optimizer differentiates from the field in large-field GPPs.
5. **Salary movement signal** — compare current DK salary to prior-week salary; large drops may indicate recency information (injury, role change) the season average hasn't priced in yet.
6. **Automated salary fetching** — replace the manual CSV download with a scraper or third-party API so the pipeline runs fully programmatically.
7. **End-to-end automation** — chain `predict_fantasy.ipynb` → `dfs_pipeline.ipynb` in a single papermill call or GitHub Actions step so DFS lineups generate automatically after weekly projections update.
