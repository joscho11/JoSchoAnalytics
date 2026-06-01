# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL sports betting prediction system with two independent models:
- **Spread model**: Ensemble fixed75 as primary edge-setter (0.75 XGBoost + 0.25 Ridge), with XGBoost, Ridge, and LightGBM as three direction voters. HIGH/MEDIUM/PASS tiers.
- **Totals model**: XGBoost + Ridge predicting whether games go over/under the Vegas total. UNDER-only strategy (books shade totals high due to recreational OVER-bias). HIGH = both models predict UNDER.
- A Claude-powered LLM agent (via LlamaIndex) for qualitative game reasoning
- A Streamlit dashboard for visualization (deployed at joschobetting.streamlit.app)
- GitHub Actions for weekly automated predictions (Mon/Thu/Sun)

## Common Commands

**Run the dashboard locally:**
```bash
streamlit run app.py
```
Runs on port 8501. Requires `betting/predictions_tracker.csv` and any cached `betting/agent_analysis_2025_week*.json` files.

**Run the spread prediction pipeline:**
```bash
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE tuesday   # Update results + new predictions
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE thursday  # Refresh with injury data
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE sunday    # Final predictions
papermill betting/predict_betting.ipynb /tmp/out.ipynb -p MODE backfill -p TARGET_WEEK 14  # Backfill a specific week
```

**Run the totals prediction pipeline:**
```bash
papermill betting/predict_totals.ipynb /tmp/out.ipynb -p MODE tuesday    # New totals predictions
papermill betting/predict_totals.ipynb /tmp/out.ipynb -p MODE thursday   # Refresh with injury data
papermill betting/predict_totals.ipynb /tmp/out.ipynb -p MODE sunday     # Final totals predictions
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
- **`app.py`** — Streamlit dashboard with 3 tabs: Weekly Predictions, Season Performance, Help & Guide. Reads `betting/predictions_tracker.csv` and `betting/totals_tracker.csv`. Game cards show a **dashed amber EXPERIMENTAL UNDER badge** when the totals model has a HIGH pick — amber instead of green/purple because live 2025 is only at break-even and the model hasn't been confirmed profitable yet. Season Performance totals section is gated with a "tracking only — do not bet" warning banner. Game cards also show a **💰 stake chip** next to the tier badge (added 2026-05-28): HIGH tier = 2u if `abs(ens_model_edge) ≥ 5` else 1u, MEDIUM = 0.5u, PASS = none. Visual flat-tier guide only (not full Kelly); explained in the Help & Guide. Fantasy tab shows per-week projections per position with projected and actual stat columns.
- **`betting/models/`** — All trained model pkl files:
  - `ensemble_prod_model.pkl` — **Primary spread model.** Ensemble fixed75: 0.75 XGBoost + 0.25 Ridge, trained 2014–2024. Sets the edge threshold and output sort order. Includes `scaler`, `feature_cols`, `roof_surface_encoder`, `xgb_model`, `ridge_model`, `xgb_weight`.
  - `xgboost_prod_model.pkl` — XGBoost sklearn pipeline (preprocessor + regressor). One of three spread direction voters.
  - `lgbm_prod_model.pkl` — LightGBM regressor. Third spread direction voter. Saved as `{'model': LGBMRegressor, 'feature_cols': list}`.
  - (Ridge for spreads is extracted from `ensemble_prod_model.pkl["ridge_model"]` at runtime — no separate pkl needed.)
  - `totals_xgboost.pkl` — **Totals model XGBoost.** Saved as `{'model': XGBRegressor, 'feature_cols': list[49], 'target': 'total_diff', 'train_seasons': list}`.
  - `totals_ridge.pkl` — **Totals model Ridge.** Saved as `{'model': Ridge, 'scaler': StandardScaler, 'feature_cols': list[49], 'target': 'total_diff', 'train_seasons': list}`.
- **`betting/archive/`** — Old model files and retired notebooks: `betting_model.pkl` (original XGBoost pkl), `BettingEdge_v2.ipynb`, `BettingEdgeContinued.ipynb`.
- **`betting/predictions_tracker.csv`** — Master log of spread predictions and outcomes. Auto-committed by GitHub Actions. Includes `pick_line` / `closing_line` / `clv` columns (added 2026-05-28, currently empty) reserved for forward-collected Closing Line Value once the 2026 season pipeline runs.
- **`betting/totals_tracker.csv`** — Master log of totals (over/under) predictions and outcomes. Same structure as predictions_tracker but for the totals model. Columns: `game_id`, `home_team`, `away_team`, `gameday`, `season`, `week`, `total_line`, `xgb_predicted_total`, `ridge_predicted_total`, `xgb_diff`, `ridge_diff`, `consensus_tier` (HIGH/PASS), `recommendation` (UNDER/PASS), `mode`, `logged_at`, `actual_total`, `went_over`, `model_correct`.
- **`betting/totals_features.ipynb`** — **Single source of truth** for the 14 totals-specific features. 15 cells, markdown→code→test pattern. Public surface: `build_totals_features`, `TOTALS_FEATURE_COLS`, `totals_acc`. Loaded by consumer notebooks via json+exec with `RUN_TESTS=False`. **Key constraint:** `is_dome` re-merges the raw roof string from sched (not the ordinal-encoded int in `g`) — this is intentional and must be preserved.
- **`betting/totals_model.ipynb`** — Totals model training notebook (22 cells). Loads `features.ipynb` + `totals_features.ipynb`, builds 49-feature matrix (35 spread + 14 totals), runs walk-forward CV, retrains on full 2014-2024 data, saves `totals_xgboost.pkl` and `totals_ridge.pkl`.
- **`betting/predict_totals.ipynb`** — Weekly totals inference pipeline. Papermill-compatible (MODE parameter). Loads both `features.ipynb` (for `build_features`, `PROD_FEATURES_35`) and `totals_features.ipynb` (for `build_totals_features`, `TOTALS_FEATURE_COLS`). Hard-fails at load if pkl feature_cols don't match `TOTALS_ALL_COLS = PROD_FEATURES_35 + TOTALS_FEATURE_COLS`. Writes to `totals_tracker.csv`. **Critical:** `build_features` must be called with keyword args — positional args would bind `target_week` and `target_season` incorrectly. Grading (actual_total, model_correct) is computed from `full_schedule` at write time so re-running a past week doesn't wipe grades.
- **`betting/model_comparison.ipynb`** — Spread model comparison notebook (70 cells). Rebuilds the exact 85-feature production dataset from scratch, evaluates 5 model architectures + 3 ensemble variants + walk-forward CV. See dedicated section below.

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
Developed in `betting/sports_betting_agent.ipynb`. Uses LlamaIndex `ReActAgent` with 5 tools (predictions lookup, live injuries via nflreadpy, line movement mock data, historical matchups, confidence analysis). Output is cached per week as `betting/agent_analysis_2025_week{n}.json` and displayed in the dashboard as confidence overlays (HIGH/MEDIUM/PASS).

**Key constraints:**
- `llama-index==0.11.0` (pinned in requirements.txt) only recognises model IDs up to `claude-3-5-sonnet-20240620`. Newer models are patched into `CLAUDE_MODELS` at runtime in cell 5. pydantic v2 silently drops `_client`/`_aclient` set in `__init__` — cell 5 restores them via `object.__setattr__` after construction.
- Line movement data is hardcoded mock (Week 10 2025). Replace with a live sportsbook API (e.g. The Odds API) for production use.
- Run via papermill: `papermill betting/sports_betting_agent.ipynb /tmp/out.ipynb -p TARGET_WEEK 10 -p TARGET_SEASON 2025`

### Data
- `betting/nfl_allpro_1997_2025.csv` — All-Pro roster data; updated manually each January
- `fantasy/features_dataset.csv` — Engineered feature dataset (built by `fantasy/data_pipeline.ipynb`)
- Live schedule, PBP, and stats pulled from `nflreadpy` at prediction time

### Automation
`.github/workflows/weekly_predictions.yml` runs the prediction pipelines via papermill on three cron schedules (Tue 9am ET, Thu 9pm ET, Sun 9am ET) and commits the updated trackers. Supports manual dispatch with mode selection. Steps in order: (1) `predict_betting.ipynb` (spread), (2) `predict_totals.ipynb` (totals), (3) `sports_betting_agent.ipynb` — **Tuesday only** (gated on the Tuesday cron / `mode == tuesday` dispatch; `continue-on-error: true` so an agent/API failure never blocks the tracker commit). Commit stages `predictions_tracker.csv`, `totals_tracker.csv`, and `agent_analysis_*.json`. Job timeout is 60 min (agent adds ~10 min for a full slate). Each notebook uploads its own failed-notebook artifact on error.

`.github/workflows/test.yml` runs the inline test suite in `betting/features.ipynb` via papermill on every push and PR against `main`. Fast (~30s), offline (synth tests don't hit nflreadpy), uploads the failed notebook as an artifact on failure. The job fails if any inline assertion in features.ipynb breaks — including the order-hash check that catches `PROD_FEATURES_35` / `FEATURE_COLS_85` reorder bugs.

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
| 32–34 | Section 11 — Feature matrix assembly (85-feature `FEATURE_COLS`), train/test split, raw categoricals saved + test |
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
- **Production model is Ensemble fixed75** — `ens_model_edge` drives the edge threshold and sort order. XGBoost, Ridge, and LightGBM are the three direction voters in `consensus_tier`. `consensus_tier` = HIGH when all 3 agree + `abs(ens_model_edge) ≥ 3pt`; MEDIUM when agree + `≥ 1pt`; PASS otherwise. (A 2026-05-24 experiment to drop the voter-agreement filter and add an ULTRA tier was tried and **rejected** — see Completed Work entry for that date. Test-set evidence said the filter added zero accuracy; live 2025 evidence said it added ~3pp on MEDIUM. Conservative read on borderline evidence keeps the original tier rule.)
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

**2025 holdout results** (vs 3-week rolling average baseline; retrained 2026-05-28):

| Position | Train rows | Test rows | MAE | RMSE | Baseline MAE |
|----------|-----------|-----------|-----|------|--------------|
| QB | 2,781 | 571 | 6.81 | 8.43 | 7.49 |
| RB | 6,652 | 1,397 | 4.40 | 6.36 | 4.59 |
| WR | 10,643 | 2,215 | 3.96 | 5.28 | 4.06 |
| TE | 5,265 | 1,145 | 3.16 | 4.55 | 3.48 |

### Known Next Improvements

- **Include 2025 in training (still PENDING — intentionally deferred).** 2025 is kept as the **evaluation holdout** for now so the models can be improved against a real out-of-sample season. `TRAIN_SEASONS = [2020–2024]`, `TEST_SEASON = 2025` in both `model.ipynb` cell 3 and `retrain_models.py`. When ready to fold 2025 in, bump both to include 2025 and re-run `retrain_models.py` (the empty-holdout guards already handle the resulting empty 2026 holdout). This adds ~5,300 rows total when done.
- **Infra fixes applied 2026-05-28 (retained regardless of holdout choice):** (1) `early_stopping_rounds` moved from `fit()` into the `XGB_PARAMS` constructor — XGBoost 2.x+ rejects it in `fit()`, so the old code couldn't retrain at all; (2) eval cells in `model.ipynb` (7, 9, 15) and player-profile cells (17-19) guarded to skip gracefully on an empty holdout; (3) `retrain_models.py` is the canonical retrain path covering all 12 models (the notebook only covers the 4 main + 6 RB per-stat). All 12 models retrained 2026-05-28 on 2020-2024 with 2025 holdout MAE: QB 6.81, RB 4.40, WR 3.96, TE 3.16 (all beat the rolling-avg baseline of 7.49 / 4.59 / 4.06 / 3.48).
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

**Canonical retrain path is `fantasy/retrain_models.py`** — it trains all 12 production models (4 main + these 8 per-stat) in one run with identical config. `fantasy/model.ipynb` also trains the 4 main + the 2 RB per-stat models (rush_yards, rec_yards) for exploration; as of 2026-05-28 its RB-stat section is trimmed to exactly those 2 so it no longer writes orphan pkls (rush_tds / rec_tds / receptions / fumbles_lost) into `models/`. Both paths use `early_stopping_rounds=25` in the `XGBRegressor` constructor (XGBoost 2.x+ rejects it in `fit()`). `predict_fantasy.ipynb` loads exactly these 8.

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

## Seasonal Projections (`fantasy/seasonal_projections/`)

A **pre-season** fantasy projection / draft-board system, distinct from the in-season weekly model. Goal: project each player's upcoming season, rank into a draft board, and compare to the market (Sleeper ADP) to surface values and reaches — the fantasy analog of the betting side's "model vs the Vegas line" edge thesis (here the market line is ADP). **As of 2026-05-28 the data foundation is built and tested; the models are NOT built yet** (next session).

**Why a separate model from the weekly one:** the weekly model leans on in-season rolling features (recent EPA, recent target share) that don't exist before Week 1. This is a season-long projection built only from draft-time-available info (prior-season aggregates, multi-year trend, age, draft capital, team context).

### Files (pipeline runs in order)

| File | Output | Purpose |
|------|--------|---------|
| `_utils.py` | — | Shared `norm_name` (DRY, matches betting/features.ipynb convention; no early `break` so cached join keys stay identical) + constants (`ADP_SENTINEL=900`, `SKILL_POSITIONS`). |
| `fetch_adp.py` | `sleeper_adp_2020_2025.csv` | Caches Sleeper preseason ADP (`adp_half_ppr`) + Sleeper's own season projections, from the undocumented `api.sleeper.app/v1/projections/nfl/regular/{season}` endpoint. **ADP is a benchmark only, never a model feature.** |
| `build_season_dataset.py` | `season_dataset_2014_2025.csv` | One row per (player, season), 7,350 rows, prior-only features (no leakage), two targets, ADP joined for 2020+. |
| `test_seasonal_projections.py` | — | Hermetic test suite (7 tests, no network) for the transformation logic + an output-integrity check on the real CSV. |
| `README.md` | — | Pipeline order, design decisions, honest caveats. |

### Data-source facts (verified empirically)

- **Sleeper ADP**: undocumented projections endpoint carries `adp_half_ppr` etc. ADP exists **2020+** only (2019 is 100% the `999.0` "undrafted" sentinel; pre-2019 has no ADP). Sleeper point projections exist 2018+. It's a **live rolling aggregate** of real drafts that freezes at the final draft-season (late-Aug) consensus for completed seasons. No timestamp in the data. Join to our data by **normalized name + position** (Sleeper's `gsis_id` is too sparse to join on, even for stars).
- **Model features come from `nfl.load_player_stats` (1999+)**, which carries `target_share`, `air_yards_share`, `receiving_air_yards` populated back to 2011 — so the air-yards/aDOT "NGS-like" signal needs no NGS endpoint and no PBP load, and 2014 has zero missing-value problem.

### Two-model design (target columns)

- `target_ppg` — half-PPR points per game (**Model A, production**). NaN when the player played 0 games or `< MIN_GAMES_TARGET` (3) — a tiny sample is a noisy label.
- `target_games` — games played (**Model B, availability**). Present for every row, including reconstructed full-miss seasons.
- `sample_weight` — games played, so Model A trusts a 2-game season far less than a 16-game one.
- Final draft value = projected PPG × projected games, ranked vs ADP. (Models not built yet.)

### Key design decisions (intentional — do not "fix")

- **Full-miss seasons reconstructed**: a season a player skips entirely leaves no stats row, so Model B would never see a 0-game outcome. `reconstruct_missed` synthesizes a `games=0` row for every gap **between** a player's first and last active season (leans toward injury/IR since the player returned). 377 such rows.
- **`is_rookie` vs `missed_prior_season`**: both yield a NaN-ish prior but mean opposite things (no NFL history vs a veteran who sat out hurt). Both are flags.
- **Prior features via explicit season-(N-1) join, NOT `shift(1)`** — a missed season correctly yields NaN priors instead of pulling 2-year-stale data. Missing priors are **NaN, never 0** (zero is a real value to a tree; same lesson as the spread time-decay bug).
- **Low-snap player-seasons kept, not filtered** — usage drives points, so a 17-game/15%-snap line is real signal; `snap_share_pg` lets the model learn it. The ADP join means low-relevance players never reach the board.
- **Draft capital joins on `gsis_id`** (matches `player_id`), name-join only as fallback — avoids the father/son same-name collapse (Frank Gore vs Frank Gore Jr.).
- **Training window decoupled from ADP**: model trains 2014+ from nflreadpy; ADP (2020+) is left-joined where it exists. Pre-2020 rows simply have no ADP benchmark, which is fine.

### Caveats (documented, not bugs)

- `qb_changed` and `vacated_target_share`/`vacated_rush_share` use season-N primary-passer / roster info — ~known by a late-August draft but mild hindsight in a strict backtest. `coach_changed` is fully clean (coaches known at season start).
- Reconstructed gaps capture injury plus some non-injury cases (a backup who sat a year); the ADP join ignores them, so they only inform Model B's durability gradient.
- `games_played` is snap-based where snaps exist (2013+), else stat-line weeks.

### Next session — modeling (TODO)

The data foundation is done; this is the plan for the modeling step:
1. **Model A (production / PPG)** — per-position XGBoost regressors (QB/RB/WR/TE, mirroring the weekly model), target `target_ppg`, `sample_weight=sample_weight` (games-weighted), train 2014-2024, holdout 2025. Pass NaN priors through natively (don't impute/zero-fill). Report holdout MAE per position.
2. **Model B (availability / games)** — one regressor predicting `target_games`, trained on ALL rows including reconstructed 0-game seasons. Features that matter: `age`, `prior_games_missed`, `missed_prior_season`, `position`, prior workload (`prior_carries_pg`/`prior_touches_pg`), `years_exp`. Set honest expectations: it should separate durable/fragile tiers, not predict exact games.
3. **Combine → draft board** — `projected_value = PPG_pred × games_pred`, rank overall + per position, join ADP (`adp_pos_rank`), compute the value/reach gap (our rank vs ADP rank). Breakouts = biggest positive gaps among young/cheap (low-ADP, low-`years_exp`) players.
4. **Evaluate two ways**: (a) projection accuracy vs actual 2025 (PPG MAE, games MAE) and vs Sleeper's own `sleeper_pts_half_ppr` projection as a benchmark; (b) the edge thesis — do our "value" picks (we rank meaningfully above ADP) actually out-finish their ADP? Backtest on 2020-2024 where ADP exists.
5. **Watch for**: modest sample (~6k usable rows, one row per player-season) → lean on regularization, don't over-feature; rookies are a cold-start population (lean on `draft_pick`/`age`/`is_rookie`); be honest if the ADP edge is within noise (same discipline as the totals model — live/holdout evidence over backtest).
6. Output a board CSV (and later a dashboard view). Keep models in `fantasy/seasonal_projections/models/` separate from the weekly `fantasy/models/`.

### Editing / running

```bash
python fantasy/seasonal_projections/fetch_adp.py            # refresh ADP cache
python fantasy/seasonal_projections/build_season_dataset.py # rebuild dataset (~1-2 min)
python fantasy/seasonal_projections/test_seasonal_projections.py
```

## Active Experiments

### 2026-05-27/28: Totals model (over/under) — SHIPPED v1 (EXPERIMENTAL on dashboard)

**Goal:** Build a separate model for the totals (over/under) market, independent of the spread model. Spread architecture is at architectural ceiling (~57% CV), but the totals market is a separate edge stream — sharp UNDER bias is a known retail/professional inefficiency.

**Status:** Fully productized and shipped.

**Path so far:**
1. **v1 (spread features alone):** all 5 models BELOW 52.4% break-even. The 35 spread features answer "who's better" not "high or low scoring."
2. **v2 (+12 totals-specific features):** XGBoost 51.7%, Ridge 52.6% (just above break-even). Significant gain from weather + implied team totals + rolling points + league scoring environment. **Audit revealed `is_dome` bug** — was always 0 because `g['roof']` was already ordinal-encoded by mc cell 33.
3. **v3 (+8 derived features, dome bug fixed):** XGBoost +0.7pp but Ridge -0.9pp. Derived features (abs_spread, rest_diff, sum_pr_prev, sum_active_allpro, outdoor_wind_mph, team_total_combined) helped trees but hurt Ridge via multicollinearity with spread features.
4. **v3.5 (Ridge-friendly: drop multicollinear, keep only pace_5g + div_game on top of v2):** **Best result.** XGBoost 52.3% ± 1.9%, Ridge 52.1%, **RF 53.3% ± 2.1% — best single model.** Consensus UNDER (XGB + Ridge agree) at **55.7% on n=575** (~96 picks/season, 95% CI 51.6-59.7%). XGBoost std dropped from 2.8% → 1.9% — lean features = less overfitting.

**Critical finding: the edge is asymmetric.** OVERs are essentially noise (50.8-52.6% across configs). The actionable strategy is **UNDER-only** when 2 voters agree. This is consistent with the known retail OVER-bias in totals markets (recreational bettors love OVER → lines inflated → UNDERs sharper).

**Final v3.5 feature set (14 totals features on top of the 35 spread features):**
- Vegas inputs (3): `total_line`, `home_implied_pts`, `away_implied_pts`
- Weather (3): `temp_f`, `wind_mph`, `is_dome` (neutralizes weather for indoor games)
- Rolling scoring (5): `home_pts_scored_5g`, `home_pts_allowed_5g`, `away_pts_scored_5g`, `away_pts_allowed_5g`, `combined_pts_5g`
- Environment (1): `league_avg_total_4wk` (rolling 4-week league average total)
- Pace (1): `pace_5g` (PBP-derived plays per game, both teams averaged)
- Matchup type (1): `div_game` (binary, division games trend slightly lower)

**Artifacts on disk:**
- `betting/experiments/totals_baseline_v3_5.py` — canonical feature engineering + walk-forward CV
- `betting/experiments/totals_baseline_v3_5_results.json` — final CV results
- `betting/experiments/_totals_baseline_v3_5.log` — run log
- `betting/experiments/_totals_direction_check.py` — direction-conditioned analysis (OVER vs UNDER hit-rates per model)
- `betting/experiments/_totals_3voter_check.py` — 3-voter consensus comparison
- (v1/v2/v3 iterations deleted during cleanup; the path-through is documented above.)

**Stats to know before picking this up next session:**
- 95% CI on 2-voter consensus UNDER straddles break-even on the lower end (51.6%). Real but not slam-dunk edge.
- Picks volume: ~96 UNDER picks per season (vs 17 HIGH-tier spread picks/season). Higher volume = more variance reduction over time.
- Vegas total_line itself has near-zero correlation with the diff target (-0.007). Vegas is well-calibrated; the model is finding small residual signal.

**Productization status (all complete):**
1. ✓ `betting/totals_features.ipynb` — feature engineering source of truth (15 cells, all tests pass). Loaded by consumer notebooks via json+exec with `RUN_TESTS=False`.
2. ✓ `betting/totals_model.ipynb` — walk-forward CV + production retrain (22 cells, all section tests pass). CV reproduces 55.7% consensus UNDER.
3. ✓ `betting/predict_totals.ipynb` — papermill-compatible weekly inference (MODE parameter). Loads both `features.ipynb` and `totals_features.ipynb`. Validates feature order against pkls at load time.
4. ✓ `betting/models/totals_xgboost.pkl` — trained on 2014-2024, 49 features, target=total_diff
5. ✓ `betting/models/totals_ridge.pkl` — trained on 2014-2024, 49 features + scaler, target=total_diff
6. ✓ `betting/totals_tracker.csv` — backfilled for 2025 **weeks 10-17 only** (the model didn't exist earlier in the season). 121 rows, 46 HIGH picks, 52.2% correct, 95% CI ~37-67%. Weeks 1-9 are intentionally absent — don't compute "full season" totals stats off this file without accounting for the partial coverage.
7. ✓ `app.py` — game cards show purple UNDER badge for HIGH totals picks; Season Performance tab has totals section; Help & Guide updated.

**Tier logic:** HIGH = both XGBoost AND Ridge predict UNDER (both residuals < 0). PASS = everything else. No OVER bets — OVER hit-rate is 50.8%, below break-even.

**Live test (2025 weeks 10-17, n=46):** 52.2% correct — essentially at the 52.4% break-even. SE ≈ 7.4pp (95% CI ~37-67%), so the result is statistically consistent with both the 55.7% CV estimate AND "no edge" — the sample is too small to tell. A full live season (~96 picks) is needed for a clean read.

**Dashboard treatment (2026-05-28):** Because the live result hasn't yet cleared break-even, the totals model is presented as **EXPERIMENTAL** on the dashboard — amber/dashed badge styling instead of confident green/purple, plus a "tracking only — do not bet" warning banner in the Season Performance section, plus an honest disclosure in the Help & Guide. We reassess after a full 2026 season of picks (~96 graded HIGH picks).

**Note on the earlier live-test number:** an initial docs claim of "57.9% on 38 picks" was based on a `g_full` fallback code path that doesn't match production. The correct production-path number is 52.2% on 46 picks. See the 2026-05-28 code review fixes for what changed.

**Architecture note for future-me:** keep totals SEPARATE from spread features. `betting/features.ipynb` stays untouched (it's the spread source of truth). New file `betting/totals_features.ipynb` is the totals source of truth. They can share data prep (mc cells 1-37) but each owns its own feature list and pkl files. Both can be retrained independently.

## Completed Work

**2026-05-28 (5 quick wins + dual code review):**
- **Fantasy 2025 holdout retain + infra fixes:** kept `TRAIN_SEASONS=[2020-2024]` / `TEST_SEASON=2025` (2025 stays the holdout for now); fixed `early_stopping_rounds` (moved to `XGB_PARAMS` constructor in both `model.ipynb` and `retrain_models.py` — XGBoost 3.x rejects it in `fit()`, so retrain was previously broken); guarded empty-holdout eval/profile cells; retrained all 12 models via `retrain_models.py` (holdout MAE QB 6.81 / RB 4.40 / WR 3.96 / TE 3.16).
- **DFS export fixed** — `dfs_pipeline.ipynb` cell 19 now writes proper DK Classic columns (`QB,RB,RB,WR,WR,WR,TE,FLEX,DST`) via consume-from-slot; unit-tested.
- **CLV columns** added to `predictions_tracker.csv` (`pick_line`, `closing_line`, `clv`; empty, reserved for 2026).
- **Agent in CI** — `weekly_predictions.yml` runs `sports_betting_agent.ipynb` Tuesday-only with a Tuesday-only conditional install of agent deps (llama-index/anthropic are excluded from `requirements-ci.txt` to keep Thu/Sun lean); `continue-on-error` so an agent/API failure never blocks the tracker commit.
- **Kelly stake chip** on game cards (💰 2u / 1u / 0.5u by tier + edge; visual only).
- **Code-review fixes (this session, mine + independent agent):** (1) app.py totals badge now coerces predictions with `pd.to_numeric(errors='coerce')` so a corrupted CSV can't crash the dashboard; (2) app.py stops with a clear warning if `predictions_tracker.csv` loads empty (not just missing); (3) `predict_totals.ipynb` asserts all `PROD_FEATURES_35` survived `build_features` for a clear error; (4) `get_tier` got a docstring; (5) `retrain_models.py` asserts required columns exist in `features_dataset.csv`; (6) deleted 4 orphan RB per-stat pkls and trimmed `model.ipynb` cell 9 so they no longer regenerate (production per-stat set is the documented 8). Both reviewers confirmed no leakage, no crash bugs, all pct divisions guarded. Remaining `SKIP` strings in app.py (lines ~411/820/911) are intentional backward-compat detectors for pre-rename cached agent JSON — they map to `PASS`.

**2026-05-25 / 26 / 27 (time-decay weighting + extended training range — REJECTED, three passes + clean rerun):**

Tested whether (a) time-decay sample weighting and/or (b) extending TRAIN_SEASONS back beyond 2014 improves the ATS model. All three passes rejected; no production change. Pass 3 was re-run with verified-clean data coverage on 2026-05-27 after discovering the initial runs had silent mechanical zero-fill in pre-2009 training rows.

**Pass 1 — time-decay sweep at TRAIN_SEASONS=2014+** (`betting/experiments/time_decay_results.json`, `_pass1.log`):
- Sweep α ∈ {0, 0.05, 0.10, 0.15, 0.20} across 5 models via 6-fold walk-forward CV (test years 2020-2025), production-tuned hyperparameters, sample_weight = exp(-α × (max_train_year - season)).
- XGBoost (primary): α=0 baseline 57.2% ± 2.0%; best non-zero α=0.10 at 57.2% ± 2.5% (Δ -0.01pp mean, +0.5pp std worse). α=0.20 worst at 56.2% ± 2.7% (Δ -1.0pp).
- Ridge, LightGBM, Random Forest all flat or worse at every non-zero α.
- Only MLP showed a positive response (53.6% → 55.0% at α=0.15, +1.4pp) — but MLP isn't in production.
- **Ship criteria failed:** XGBoost ≥+0.5pp improvement (fail), ≥3 of 5 models improve (fail), std doesn't worsen >+0.3pp (fail).

**Pass 2 (real) — extended TRAIN_SEASONS at α=0** (`betting/experiments/time_decay_pass2_real.json`, `_pass2_real.log`):
- First attempt was methodologically flawed: `mc cell 2` only loads PBP for ALL_SEASONS=2014-2025, so filtering training data to earlier years was a no-op (identical results for train_starts 2014/2010/2005/1999). Documented and re-done.
- Real Pass 2: extended `tune_time_decay.py` with `--earliest YEAR` that overrides `ALL_SEASONS` after mc cell 2 runs and before cell 8 (data load). Also monkey-patched `nfl.load_injuries` to filter to 2009+ (nflreadpy's documented lower bound) with progressive-year fallback. Ran `--alphas 0 --train-starts 2014,2010,2005 --earliest 2005`.
- Verified extended load: 5,698 games (vs 3,295 baseline), 712k PBP plays, manual passer rating for 352 team-seasons (2005-2015), injuries 2009-2025, AllPro 2005-2025.
- XGBoost results within this run: 56.4% ± 2.0% (2014+) → 56.7% ± 2.5% (2010+) → 56.8% ± 3.0% (2005+). Best Δ +0.4pp at 2005+, but std worsens by +1.0pp. Other models: Ridge +0.4pp at 2005+, LightGBM -0.5pp at 2005+, Random Forest -0.4pp, MLP +1.2pp.
- Important caveat: the 2014+ baseline within this run (56.4%) is 0.8pp *below* Pass 1's baseline (57.2%) because extending the data load activates the manual passer-rating fallback for 2010-2015 (vs only 2014-2015 in Pass 1), changing feature values for 2014 training rows. So part of any "improvement" at train_start=2010+ is just recovering ground lost to the feature shift.
- **Ship criteria failed:** XGBoost +0.4pp (sub-threshold), std worsens by +1.0pp at 2005+ (fail), only 3 of 5 models improve and two of those (Ridge, MLP) by sub-threshold amounts.

**Pass 3 — synthesis: extended TRAIN_SEASONS × non-zero α** (`betting/experiments/time_decay_pass3.json`, `_pass3.log`):
- First version with `--earliest 2005` had silent coverage corruption: pre-2009 training rows had 100% zero injury features (nflreadpy injuries only exist from 2009), and 2005 rows had 100% zero AllPro (a hardcoded 2006 floor in mc cell 15's `build_weighted`). The "extra training data" was partly mechanical zeros, biasing the test against the more-data hypothesis. Documented and re-done.
- **Clean Pass 3** (`betting/experiments/time_decay_pass3_clean.json`, `_pass3_clean.log`): ran with `--earliest 2008, --train-starts 2014,2011,2009`. This avoids both coverage bugs: training never includes pre-2009 rows, the 2008 PBP load enables real 2008 prev-year features for 2009 training rows, AllPro CSV has the years needed (1997+). Added a `verify_coverage` gate in `tune_time_decay.py` that hard-fails if any feature shows a >25pp zero-rate shift between early and late periods — gate passed cleanly on this range.
- **Audit of historical coverage** (`betting/experiments/_audit_historical_coverage.py`) before running, verifying each data source's earliest reliable year: schedules + spread + coach + QB names back to 1999 (100% non-null), PBP+EPA back to 1999 (verified at 2005/2007/2009/2011), AllPro CSV 1997+, NGS hard floor 2016 (nflreadpy ValueError pre-2016), injuries hard floor 2009 (nflreadpy ValueError pre-2009).
- **XGBoost grid (clean Pass 3):**
  | α | 2014+ | 2011+ | 2009+ |
  |---|---|---|---|
  | 0.00 | 56.5% ± 1.6% | 56.1% ± 2.6% | **57.1% ± 2.6%** |
  | 0.05 | 56.8% ± 1.7% | 55.5% ± 2.8% | 56.9% ± 3.5% |
  | 0.10 | 56.2% ± 1.9% | 55.3% ± 2.9% | 56.1% ± 2.8% |
  | 0.15 | 56.0% ± 2.2% | 55.7% ± 3.1% | 55.8% ± 3.2% |
- Best cell: train=2009+, α=0 at **57.1% ± 2.6%**. Within-run baseline (2014+, α=0) is 56.5% ± 1.6%. **+0.6pp mean** (clears the +0.5pp ship threshold), **+1.0pp std worse** (fails the +0.3pp std cap).
- 4-of-5 models improve at the best cell (XGB +0.6, Ridge +0.2, LightGBM +0.3, MLP +0.7), 1-of-5 regresses (RF -0.5).
- **Key insight on the apparent gain:** the within-run 2014+ baseline (56.5%) is **0.7pp below** Pass 1's standalone 2014+ baseline (57.2%). The reason: extending the data load gives 2013 a real manual passer rating (instead of median fill), which changes `pr_prev_year` for 2014 training rows. So part of the +0.6pp "gain from extending data" is recovery from the feature-shift the extension itself causes. Net change vs current production CV (XGBoost 56.9%): +0.2pp mean / +0.7pp std worse.
- **Decay × extension synthesis: no synergy.** Every non-zero α at every train_start performs *worse* than α=0 within that train_start. Decay weighting consistently hurts when applied to the cleaned data.
- **Verdict: REJECT.** The cleanest finding of all three passes — but the ship criteria fail on the std cap, and the net improvement vs current production is essentially zero once the data-shift baseline drop is factored in. Stability loss (+0.7-1.0pp std worse) is a real business cost in a money-at-stake application.

**Verdict: all three passes rejected.** No production code changed; pkls verified byte-identical to baseline md5s (`ensemble=42a61911…`, `lgbm=c6fcf092…`, `xgboost=a0a209e5…`). Artifacts preserved on disk:
- `betting/experiments/tune_time_decay.py` (now supports `--earliest YEAR` + has `verify_coverage()` gate)
- `betting/experiments/_audit_historical_coverage.py` (live audit of nflreadpy's actual data coverage by source)
- `betting/experiments/time_decay_results.json` + `_pass1.log` (Pass 1)
- `betting/experiments/time_decay_pass2_real.json` + `_pass2_real.log` (Pass 2 real — partially-zeroed coverage)
- `betting/experiments/time_decay_pass2_results.json` + `_pass2.log` (Pass 2 flawed v1, kept as cautionary tale)
- `betting/experiments/time_decay_pass3.json` + `_pass3.log` (Pass 3 — partially-zeroed coverage)
- `betting/experiments/time_decay_pass3_clean.json` + `_pass3_clean.log` (**Pass 3 clean — methodologically correct test**)
- `betting/_pkl_baseline_time_decay.json` (md5 snapshot, used for verification)

**Lessons:**
1. The production XGBoost ensemble is at a stable ceiling around 57% CV ATS. Adding more historical data or down-weighting old samples does not move the mean meaningfully and degrades stability.
2. **Always audit data-source coverage BEFORE running an "extra data" experiment.** Pass 2/3 initially looked borderline because pre-2009 training rows had 100% zero injury features (nflreadpy hard floor) and pre-2006 had 100% zero AllPro (hardcoded code floor). The model was being fed mechanical zeros disguised as extra training rows. The `verify_coverage()` gate in `tune_time_decay.py` catches this automatically by comparing early-vs-late zero-rates per feature.
3. **Extending the data load also extends the manual passer-rating fallback,** which can change feature values for years that weren't strictly added (e.g. 2013 gets a real PR instead of median-fill, which then shifts 2014's prev-year-PR feature). This makes "extend the data" not a clean A/B knob — it shifts the baseline too.
4. **Decay weighting consistently hurts on the cleaned data** at every (train_start, α > 0) cell. No synergy. The hypothesis "decay unlocks the value of more data" was wrong here.
5. The MLP responds positively to both decay (+1.4pp Pass 1) and more data (+0.7pp clean Pass 3), but it isn't in production and adding it to the ensemble was tested in May 2026 (`[[bettingedge-model-experiments-2026-05]]`) without ship-worthy results.
6. **Stability matters more than the mean in real-money applications.** A model that's 57.1% with 2.6% std could swing 54-60% in any given year, vs 56.5% with 1.6% std that swings 55-58%. The wider band is a worse business outcome even though the mean is higher. The std-worsening cap exists for this reason and is the right call to enforce.
7. Per the rejection-criteria memory: when the cleanest possible test still fails the ship criteria, the prior on "this lever helps" is now strong enough that re-running is wasted effort. Memory updated.

Memory note: see `[[bettingedge-model-experiments-2026-05]]` for the running list of model-tuning experiments that have been tried and rejected.

**2026-05-23 (feature-engineering dedup, Phase 1):**
- Created `betting/features.ipynb` (initially 51 cells; now 53 after same-day code-review fixes added a cleanup cell pair, see entry below) with markdown → code → inline-test pattern as the **single source of truth** for the 85-feature engineering pipeline. Public surface: `build_features`, `build_numeric_features`, all 10 `_build_*` per-group helpers, `FEATURE_COLS_85`, `PROD_FEATURES_35`, `TEAM_MAP`, `norm_name`, `canonicalize_ngs_team`. Each per-group helper has its own test cell exercising synthetic schedule + PBP + AllPro fixtures (Andy Reid wins 4/4 → roll3 = 1.0, KC offense AllPro 2024 → weight 4 in 2025, etc.). All 14 test cells pass.
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
- Verified: `papermill betting/features.ipynb` runs all 15 inline tests (1 imports-smoke + 14 RUN_TESTS-gated, all pass, including the now-hermetic passer-rating test). `papermill betting/predict_betting.ipynb -p MODE thursday` still runs through to the "season is over" check. mc retrain still produces byte-identical pkls.

**2026-05-24 (CI safety net + order-hash regression check):**
- Added `.github/workflows/test.yml` — a 2nd GitHub Actions workflow that runs `papermill betting/features.ipynb` on every push and PR against `main`. Fast (~30s), fully offline (synth tests don't touch nflreadpy), uploads the failed notebook as an artifact on failure. Closes the gap where breakage on `main` was only caught by the Tuesday cron run.
- Tightened the constants test in `features.ipynb` cell 8 with an **order-hash check**: locks the canonical orders of `FEATURE_COLS_85` (md5 `c1822ba8…`) and `PROD_FEATURES_35` (md5 `ac880107…`). If either list is reordered, the assertion fails with a clear message ("If intentional, retrain pkls and update the expected hash"). This is the exact bug-class hit during Phase 2a (memory [[feature-list-order-is-contract]]) — now caught automatically before merge.
- Why this matters: Phase 1+2a+review-fixes added clean structure but increased the cost of a silent regression. Pkl byte-equivalence had been verified by hand twice this week. With CI in place, the verification runs on every push — no future contributor (including future-me) has to remember to do it.

**2026-05-24 (model-improvement experiments — REJECTED; production unchanged):**

Ran a series of model-improvement experiments. **None were shipped.** Saved as memory note `[[bettingedge-model-experiments-2026-05]]` to avoid re-running.

1. **Ensemble weight sweep** — tested XGB+Ridge weights 0.50→0.90, XGB+LGBM variants, three-way blends, Ridge meta-learner stack on 855-game test set. **All variants within statistical noise** of current 0.75 XGB + 0.25 Ridge (SE ~2.8pp on n=238 HIGH-tier). LightGBM in the BLEND hurts (it belongs in the consensus tier, not the predicted margin). **Conclusion: 0.75 weight is essentially optimal. Don't retune.**

2. **Consensus filter removal + ULTRA tier addition** — proposed switch from 3-of-3 voter agreement + edge threshold to pure edge-only with new ULTRA tier at ≥5pt.
   - Test-set evidence (n=855, 2023-2025): consensus filter added ~0pp on average across all edge cutoffs.
   - Live 2025 evidence (n=117): consensus filter looked helpful — removing it dropped MEDIUM from 59.5% (n=42) to 56.5% (n=62). Within standard error, but real direction.
   - ULTRA tier on live 2025: only **2 games hit ≥5pt edge across 7 weeks** (test set predicted ~8.5% rate / ~1.4 games/week; actual was 0.3 games/week — 4× lower). Tier label that fires this rarely isn't useful for staking or UX.
   - **Implemented end-to-end** (predict_betting cell 34 rewritten, tracker backfilled with new tier labels, app.py updated for 4 tiers including ULTRA badge / Season Performance / Help section, README updated, CLAUDE.md updated).
   - **User correctly pushed back:** "is this really worth doing after looking at the 2025 data". Live data > test set when they conflict for production decisions with real money. ULTRA fires too rarely to be actionable.
   - **Fully reverted same day.** Restored 3-tier consensus rule everywhere. Tracker re-backfilled. app.py / README / CLAUDE.md restored. No net change to production from this experiment.

3. **Weather feature addition** — built `betting/nfl_weather_2014_2025.csv` (Meteostat-sourced, 99.96% coverage, kickoff-hour accurate, verified vs known events). Tested adding `temp_f` + `wind_mph` to PROD_FEATURES_35. **All 5 models flat or worse** in walk-forward CV (XGBoost -0.7pp, RF -1.0pp). Vegas already prices weather in; rolling EPA / coach win% / AllPro indirectly capture weather effects; wind has spread signal but it's small and noisy. **Fully reverted** — pkls restored from backup (byte-identical to baseline md5s), features.ipynb reverted to 85/35. **Artifacts preserved:** the weather CSV + `betting/experiments/fetch_weather.py` remain on disk for potential future use in a totals model (where wind has clear signal).

**Net business-relevant lesson from these experiments:** the production model is approximately at the ceiling of what this architecture can deliver on ATS. Further gains come from **execution infrastructure**, not model tuning:
- **Closing Line Value (CLV) tracking** — leading indicator of long-term profit; currently not tracked
- **Multi-book line shopping** — 2-5% implied edge improvement per bet at zero model cost
- **Kelly fractional sizing** — currently absent; tier-based equal staking leaves money on the table
- **Totals model** — independent edge stream; weather data is already built for this
- **Player props model** — lower-efficiency market, higher edge potential

These items (none of them model-tuning) are what would actually grow the project from "interesting analysis" to "revenue generator." See memory `[[bettingedge-model-experiments-2026-05]]` for full context.

**2026-05-24 (weather-features experiment — NEGATIVE RESULT, reverted):**
- Question: does kickoff-hour weather (temp_f + wind_mph) improve ATS when added to PROD_FEATURES_35? Originally we'd dropped weather because nflreadpy's `temp`/`wind` columns had 48.7% missing in 2022 and 21.5% in 2023.
- Built `betting/experiments/fetch_weather.py` (260 lines) — uses Meteostat (NOAA-backed, free) to pull kickoff-hour temp + wind for every outdoor REG-season game. Robust 2-era station picker + per-game fallback to next-nearest station gets 99.96% coverage (2,268 / 2,269 games). Cross-validated vs nflreadpy where both have data: median 1.1°F / 2.0 mph diff — meteostat is more accurate to actual kickoff hour. Spot-checked vs known events (Buffalo Snow Game 2017-12-10 = 28.9°F / 15 mph wind; Bills Dec 22 2024 = 14°F / 0 mph; Miami early-Sept = 86–92°F).
- Result CSV: `betting/nfl_weather_2014_2025.csv` (225 KB). Indoor/dome games skipped on purpose — feature pipeline gives them neutral 70°F / 0 mph at training-time merge.
- **Integration test (walk-forward CV 2020-2025, 5 models, 37 features = PROD_FEATURES_35 + temp_f + wind_mph):**
  | Model | Baseline (35 feat) | With weather (37) | Δ ATS | Verdict |
  |-------|---------|---------|--------|---------|
  | XGBoost (cv) | 56.9% ± 1.9% | 56.2% ± 2.3% | -0.7pp | WORSE |
  | LightGBM | 56.5% ± 1.7% | 56.3% ± 2.4% | -0.2pp | flat (std worse) |
  | Ridge | 55.6% ± 2.0% | 55.3% ± 2.1% | -0.3pp | WORSE |
  | Random Forest | 57.1% ± 2.9% | 56.1% ± 2.1% | -1.0pp | WORSE |
  | MLP | 53.7% ± 2.5% | 53.7% ± 2.5% | +0.0pp | flat |
- All 5 models flat or worse. Verdict: weather features add **no signal** on top of the existing 35. The model already implicitly captures weather effects via rolling EPA (passing in wind), coach win% (home-field cold-weather adaptation), and AllPro (cold-weather team strength).
- **Reverted in same commit:** restored baseline pkls from backup (md5s match the snapshot), removed Group 11 from features.ipynb, removed `_build_weather` call from mc cell 33, restored original `==` size assertions in mc cells 6/33/34/37, restored original `FEATURE_COLS_85` (85 entries) and `PROD_FEATURES_35` (35 entries) with the original locked hashes (c1822ba8 / ac880107).
- **What was preserved:** `betting/nfl_weather_2014_2025.csv` and `betting/experiments/fetch_weather.py` remain on disk. They're useful for future experiments where weather might matter more directly — e.g., a totals model (wind has stronger signal on totals than spreads — see the original analysis: ~3pt under in 16+ mph wind games), or extreme-weather subset features (freezing-temp games specifically), or any future model architecture where weather might add value the current ensemble misses.
- **Lesson:** don't redo this experiment with the same feature framing. If weather is to be tried again, it should be in a different form (extreme buckets, weather × team interactions, or directly as a totals model).

### Editing the shared features notebook

- `betting/features.ipynb` is ~80 KB but well within Read/NotebookEdit tool limits. Edit cells via the notebook tools or `json.load/dump`, either is fine.
- After editing, run it standalone via `papermill betting/features.ipynb /tmp/_out.ipynb` to verify all 15 inline tests still pass (imports-smoke + 14 RUN_TESTS-gated tests for constants, helpers, each of the 10 feature groups, build_features integration, build_numeric_features). The papermill run takes ~5 seconds.
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

- **✓ FIXED (2026-05-28): DK lineup upload CSV format.** `dfs_pipeline.ipynb` cell 19 now exports the proper DraftKings Classic layout — one column per roster slot (`QB, RB, RB, WR, WR, WR, TE, FLEX, DST`), filled by consuming names from each `_assign_slots` label. Verify against DK's current template before a real contest, but the format now matches the documented Classic import spec.

---

### Next Steps

1. **DST projection model** — train on defensive EPA allowed, implied team total, home/away, and surface. Replace the `dk_avg` fallback for DST so all 9 slots use our model.
2. **Multi-lineup GPP generator** — produce N distinct lineups for tournament play using ownership-diversity constraints (force variation in at least the FLEX pick and one anchor position across lineups).
3. **Game-stacking constraints** — add optional ILP constraints to co-select 2+ players from the same game (QB + WR1 + opponent pass-catcher), exploiting positive score correlation in high-total matchups.
4. **Ownership leverage weighting** — scale `proj_pts` by inverse projected ownership so the optimizer differentiates from the field in large-field GPPs.
5. **Salary movement signal** — compare current DK salary to prior-week salary; large drops may indicate recency information (injury, role change) the season average hasn't priced in yet.
6. **Automated salary fetching** — replace the manual CSV download with a scraper or third-party API so the pipeline runs fully programmatically.
7. **End-to-end automation** — chain `predict_fantasy.ipynb` → `dfs_pipeline.ipynb` in a single papermill call or GitHub Actions step so DFS lineups generate automatically after weekly projections update.
