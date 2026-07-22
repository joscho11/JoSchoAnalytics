# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL sports betting prediction system with two independent models:
- **Spread model**: Ensemble fixed75 as primary edge-setter (0.75 XGBoost + 0.25 Ridge), with XGBoost, Ridge, and LightGBM as three direction voters. HIGH/MEDIUM/PASS tiers.
- **Totals model**: XGBoost + Ridge predicting whether games go over/under the Vegas total. UNDER-only strategy (books shade totals high due to recreational OVER-bias). HIGH = both models predict UNDER.
- A Claude-powered LLM agent (via LlamaIndex) for qualitative game reasoning
- A Streamlit dashboard for visualization (deployed at joschoanalytics.streamlit.app)
- GitHub Actions for weekly automated predictions (Mon/Thu/Sun)
- A pre-season fantasy **2026 Draft Board** (`fantasy/seasonal_projections/`), surfaced as the Draft Board dashboard tab (`draft_board_2026.py`) — the market point estimate plus a calibrated uncertainty band, from a closed pre-registered research campaign. See that directory's `GUIDE.md` / `ARTIFACTS.md` / `PREREGISTRATION.md` and the `bettingedge-seasonal-h5-campaign` skill.

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
  | 27–29 | `build_features` — imported from `betting/features.py` (cell 28 loader; was json-exec of features.ipynb until 2026-06-15) |
  | 30–32 | `build_numeric_features` — also from `features.py` (acknowledged in cell 31; tested inline in cell 32) |
  | 33–34 | `run_predictions` — model inference (no test cell — needs live models) |
  | 35–37 | `update_results` — fill outcomes from completed games |
  | 38–40 | `log_predictions` — write to tracker CSV |
  | 41–42 | Run Pipeline — execution cell |
- **`betting/features.py`** — **Single source of truth** for the 85-feature engineering pipeline (Groups 1–10), shared by `predict_betting.ipynb`, `model_comparison.ipynb`, `predict_totals.ipynb`, and `totals_model.ipynb`. Plain importable Python (extracted verbatim from the former `features.ipynb` on 2026-06-15 — see Completed Work). Public surface: `build_features`, `build_numeric_features`, the per-group `_build_*` helpers, `FEATURE_COLS_85`, `PROD_FEATURES_35`, `TEAM_MAP`, `norm_name`, `canonicalize_ngs_team`. **Loading pattern** (all 4 consumers): add `betting/` to `sys.path`, `import features as _features`, then `globals().update({k:v for k,v in vars(_features).items() if not k.startswith("__")})` — this mirrors the old `exec(globals())` namespace population (including the `_build_*` helpers). Tests live in **`betting/test_features.py`** (hermetic synthetic-data tests, run in CI — see below); the `PROD_FEATURES_35`/`FEATURE_COLS_85` order-hash check is `test_constants_and_order_hashes`.
- **`betting/features.ipynb`** — Now a **thin documentation notebook** (one import cell + the design-rationale markdown for each feature group). It is NO LONGER the source of truth and defines no production code — edit `features.py` instead. (Was the 53-cell source-of-truth notebook before 2026-06-15.)
- **`app.py`** — Streamlit dashboard, **8 tabs** (built on a single `st.tabs` call, so one AppTest render exercises all of them): Weekly Predictions, Track Record, **📋 Draft Board** (`tab5` → `import draft_board_2026; draft_board_2026.render()`), Film Room, Weekly Fantasy, DFS Optimizer, League History, Help & Guide. The pure, Streamlit-free helpers (`metric_card`, `get_confidence`, `_md_to_html`, `load_tracker`, `load_totals_tracker`) live in **`dashboard_utils.py`** (unit-tested by `test_dashboard_utils.py`, in CI); tab-rendering stays in app.py (`st.*`-procedural, covered by `test_app_draft_board.py`'s AppTest). Game cards use the sportsbook-style display negation (see Key Constraints) and show a **dashed amber EXPERIMENTAL UNDER badge** when the totals model has a HIGH pick (amber because live 2025 is only at break-even). The Track Record totals section carries a "tracking only — do not bet" banner. **`APP_OFFLINE=1`** disables every network path (GA, nflreadpy, Sleeper) for hermetic AppTest runs. The Draft Board tab renders the FROZEN 2026 artifacts under the license discipline described in the Seasonal Projections section — no BUY/FADE/tier/verdict language anywhere. (The old inline Draft Value Finder tab and its `value_board_*.csv` were retired 2026-07-12; `build_value_board.py`/`build_draft_board.py`/`board_view.py` stay on disk but no tab renders them.)
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
- **`betting/totals_model.ipynb`** — Totals model training notebook (22 cells). Imports `features.py` + loads `totals_features.ipynb`, builds 49-feature matrix (35 spread + 14 totals), runs walk-forward CV, retrains on full 2014-2024 data, saves `totals_xgboost.pkl` and `totals_ridge.pkl`.
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

`.github/workflows/test.yml` runs on every push and PR against `main`, with two jobs (both fast + offline): (1) **`features`** — `pytest betting/test_features.py` (the feature-pipeline contract tests, including the order-hash check that catches `PROD_FEATURES_35` / `FEATURE_COLS_85` reorder bugs); (2) **`pytests`** — the seasonal + dashboard suites (`test_seasonal_projections.py`, `test_draft_board.py`, `test_app_draft_board.py`) via `requirements-test.txt`.

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

**⚠️ These CV win-rates are optimistic development estimates, not unbiased out-of-sample numbers.** Hyperparameters AND the 35-feature set were *selected* on these same walk-forward folds (the tuning is NOT nested), so the reported %s are inflated by selection — the classic "tune-then-report-on-the-same-folds" bias. They're fine for *comparing* models/configs against each other (the bias is shared), but the honest read on the real edge is the **forward live tracking** (`predictions_tracker.csv`), not CV. A research-only nested walk-forward (`betting/experiments/nested_cv_xgb.py`, 2026-06-04) sized the optimism for XGBoost: the pooled-best/production config reports **57.2% ± 2.0%**, but tuning inside each fold (train `< N` only) gives a leak-free **56.4% ± 2.1%** — i.e. **~0.9pp of selection optimism**, edge still well above the 52.4% break-even. The inner tuning picked a different config nearly every fold (no robust single best), which is exactly why the optimism is small. The data splits themselves are clean (no target/feature leakage; walk-forward training only uses prior seasons) — this is selection optimism, not data leakage.

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

A pre-season fantasy draft system, distinct from the in-season weekly model. It projects
each player's upcoming season and compares to the market (Sleeper ADP) — the fantasy analog
of the betting side's "model vs the Vegas line" thesis (here the line is ADP). This area ran
a long, pre-registered research campaign; that campaign is **closed**, and what ships today is
the **2026 Draft Board**.

**Full detail lives in these places — read them before touching anything here:**
- `PREREGISTRATION.md` — the campaign constitution and the OUTCOMES ledger (every fired test).
- `GUIDE.md` — plain-language tour of the board and the campaign.
- `ARTIFACTS.md` — every file in this directory tagged frozen / regenerable / retired.
- The `bettingedge-seasonal-h5-campaign` skill — the executable runbook and the one-shot-test rules.

### What ships today: the 2026 Draft Board

`draft_board_2026.py` (a Streamlit tab in `app.py`, license-frozen copy) renders two FROZEN
artifacts: `phase4_band_2026.csv` (the board — market point estimate + a calibrated Floor/
Expected/Ceiling band, P(top-12/24), bust prob, and a descriptive `value_gap`) and
`talent_index_2026.csv` (a separate, descriptive 2025-efficiency context column, never blended
into anything). The band engine is `phase4_band.py` (walk-forward isotonic + residual quantiles;
leave-one-season-out coverage 79.4% at nominal 80% and 49.8% at 50% — beats a constant-width
baseline); `apply_board_labels.py` adds the population flags and the licensed `signal_status`
wording.

**License discipline.** Board *copy* states disagreements descriptively and validation
*in aggregate* only — never player-level calls, hit-rate claims, named tiers, or buy/sell/fade/
steal/reach language. The verbatim licensed labels ship in-schema; plain-language translations must
not strengthen or weaken them. The talent column is descriptive only and is never combined with the
value signal. **Color coding is permitted (Joseph-ratified 2026-07-13):** a red→green heat on the
Gap and on the descriptive magnitude columns (Top-12 chance, NFL Efficiency %ile) plus a bold,
enlarged Gap headline — uniform with the Weekly Fantasy table. Color conveys magnitude/direction
only and the copy stays aggregate-only; the *wording* restrictions above are unchanged. See
`draft_board_2026.py`'s module docstring and `apply_board_labels.py`.

### The campaign, settled (do not re-fight — see PREREGISTRATION.md OUTCOMES)

The question was "can anything beat ADP at ranking drafted players?" Answers, all pre-registered:
- **Prior-stats features do NOT beat ADP** (H4 residual model FAILED; λ=0 in 28/30 folds).
- **Sleeper-vs-ADP disagreement carries real aggregate information** — H6 PASS (pooled r +0.300),
  and it survives a freshness control (H11 PASS) and holds for volatile RB/WR vs a dated market
  (H12 PASS). Validated **in aggregate only**; threshold tiers and QB/TE-volatile rows are unvalidated.
- **Efficiency-over-expectation does NOT predict market error** (H7 FAIL) — hence the talent column
  is descriptive-only. **Offseason room-competition is priced by the market** (H8v FAIL).
- The band product (Phase 4) validated and shipped either way — the band is the contribution.
- **Sealed forever:** seasons 2008–2015 (never touched by any model-vs-ADP metric). **Void:**
  Sleeper's 2020 projections (near-actuals; every Sleeper metric is ex-2020).

**One-shot rule:** the H-series tests are pre-registered and fire exactly once; their results are
frozen in `*_results.json`. Never re-fire one to "regenerate" a number — read the JSON.

### Current phase: content sourcing (no research contact)

The shipped board is now raw material for TikTok content (see `nfl_tiktok` + the video skills).
That work is descriptive-only extraction from the frozen artifacts: no outcomes exist for 2026 and
none get computed. `fantasy/seasonal_projections/content/` holds those sourcing sheets (gitignored).

### Retired engine (kept for history)

`build_value_board.py` + the old BUY/FADE `value_board_*.csv` served the retired Draft Value Finder
tab. The engine files stay on disk; the CSVs were removed from git on 2026-07-12 (history preserves
them). The earlier Model A/B + three-way-blend arc (`build_draft_board.py`, `train_model_a.py`, etc.)
is also retained, not shipped. The blind decision rules, sealed slices, and data-provenance facts all
live in `PREREGISTRATION.md` and the campaign skill.

## RB, WR, TE & QB Season Projection (`fantasy/projections/`)

From-scratch **season-total half-PPR projections for 2026** (all four skill positions built + shipped
2026-07-21), separate from the seasonal Draft Board and the weekly fantasy model. Per position, **two models
share one target** — veteran (≥1 prior NFL season) and rookie (none) — merged into one projection column,
shown on the **Rookie Board page beside Sleeper's projection + a difference column**. They replace the
starved per-game `rookie_ppg` surface on display (that pkl is untouched; md5 `872467b2…` asserted). The
Rookie Board's `_load_proj()` concatenates the per-position board-projection files
(`{rb,wr,te,qb}_rookie_board_projection.csv`) — **position is in the join key, so each position's rows draw
its own model and the others' rows are byte-identical**; the board displays ROOKIES (veteran projections
live only in `results/{pos}_projection_2026.csv`, not displayed anywhere yet). Every build IMPORTS the RB
engine from `build_rb_projection.py` (never modifies it) + a ~15-line per-position frozen-matrix twin;
`depth_rank` is excluded from every bucket (nflreadpy depth charts end at 2024 → train-present/deploy-absent),
enforced by a deploy-gap check each build. Honest walk-forward (2021–2025) pooled Spearman: RB +0.689, WR
+0.736, TE +0.734, QB +0.695 — **none beat Sleeper** (Sleeper shown, not gated; it's strongest at QB, 0.849).

**TE (2026-07-21):** `build_te_projection.py` (WR's receiving block). Rookie ρ +0.636 (above RB's +0.55) →
rookie arm shipped; less elite-conservative than RB/WR (projects Pitts & Kittle above Sleeper). `TE_SHIP_ROOKIE`
env toggle honors a ship/hold call.

**QB (2026-07-21) — VETERAN-ONLY:** `build_qb_projection.py` uses the PFF **passing** block (there is NO
college passing box-score in the frozen matrix — the `cfb_*` block is scrimmage-only — and no QB talent
instrument). Veteran ρ +0.697 ships. The **rookie arm was HELD** (`QB_SHIP_ROOKIE=0` default): its ρ +0.627
is near-meaningless (50 rows / 7–13 per fold), and a draft-order diagnostic showed it just re-ranks by draft
capital and projects starter seasons for QBs the market expects to sit (Ty Simpson proj 135.9 vs Sleeper 13.6)
— it has no "will he start" signal. So `qb_rookie_board_projection.csv` is empty and QB rookies show no
projection. GUIDE broadened to "RB, WR, TE & QB".

**TE (2026-07-21):** `build_te_projection.py` (WR's receiving block — TEs are receivers). Walk-forward
(n=677) pooled Spearman **+0.734** (veteran +0.742, **rookie +0.636** — above the shipped RB rookie arm's
+0.55, so the rookie arm ships; TE is the thinnest position with a zero-heavy target, disclosed). vs
Sleeper ρ +0.741 vs +0.798 (does not beat). Notably **less elite-conservative** than RB/WR (projects Pitts
& Kittle above Sleeper). Models `models/te_{veteran,rookie}_model.pkl` (LightGBM); a `TE_SHIP_ROOKIE` env
toggle honors a rookie ship/hold decision. GUIDE broadened to "RB, WR & TE".

**WR (2026-07-21):** `build_wr_projection.py` **imports the RB engine** (`season_total_target`,
`nested_select`, `walk_forward`, `fit_final_model`, `_prep`, `_grid`, metrics) + a ~15-line WR
frozen-matrix twin (`position=='WR'` + `pff_receiving`) — **`build_rb_projection.py` is NOT modified**.
Governing prereg `PREREG_wr_projection_2026-07-21.md`; **`depth_rank` excluded from the start** (the RB
lesson) with an explicit deploy-gap check confirming no other feature is train-present/2026-absent.
Walk-forward (n=1242) pooled Spearman **+0.736** (stronger than RB); vs Sleeper ρ +0.738 vs +0.799 — does
not beat on ranking, though MAE is even (38.5 vs 39.2). Models `models/wr_{veteran,rookie}_model.pkl`
(LightGBM); results `results/wr_*.csv`. The Rookie Board's `_load_proj()` concatenates the RB + WR
board-projection files (position is in the join key, so RB rows are byte-identical); WR rows now carry the
projection/Sleeper/Diff columns. GUIDE broadened to "RB & WR".

- **Governing prereg:** `fantasy/projections/PREREG_rb_projection_2026-07-21.md` (design frozen before
  fitting; **Amendment 1 dropped `depth_rank`** — nflreadpy `load_depth_charts` ends at 2024, so the
  feature was absent for the 2025 fold + 2026 deploy and collapsed the native-NaN tree models; kept the
  drop as a data-validity fix). Target = **observed season-total half-PPR summed from weekly stats**
  (NOT `target_ppg×games`, which filters games≥11 and drops partial/injury seasons).
- **Pipeline:** `build_rb_projection.py` — `--assemble` (feature matrices + pre-registered asserts),
  `--walk-forward` (registered nested-CV walk-forward 2021–2025 + gates-nothing Sleeper reference),
  `--ship` (fit final models, write derived artifacts). Interpreter = the AI_hedge_fund venv (repo .venv
  broken). PFF-derived rookie matrix regenerated in a TEMP scratch dir — **no parquet / no raw-PFF season
  tables in the repo**; only derived projections land in `results/`. Synthetic proof: `rb_projection_harness.py --build`.
- **Models:** `models/rb_veteran_model.pkl`, `models/rb_rookie_model.pkl` (both LightGBM, inner-CV-chosen).
  **Results:** `results/rb_projection_2026.csv` (full veteran+rookie surface), `rb_rookie_board_projection.csv`
  (the board join file), `walkforward_predictions.csv`, `sleeper_comparison.csv`.
- **Honest numbers:** walk-forward 2021–2025 (n=802) pooled Spearman **+0.689**; **does NOT beat Sleeper**
  (Sleeper ρ +0.799 vs +0.671 on the 486 covered rows) — Sleeper is **shown, not a gate**, and this is
  **backtested, not live-validated** (first live test = end of 2026). Board display retires `proj_ppg` and
  shows *Proj (season ½-PPR) / Sleeper Proj / Diff vs Sleeper* (RB rows only). Guide: `fantasy/projections/GUIDE.md`.
  AppTest: `test_page_rookie_board.py` (not yet in CI).

## Active Experiments

### Seasonal value-signal campaign — CLOSED (2026-07-12)

The pre-registered "beat ADP" campaign in `fantasy/seasonal_projections/` is complete: H6/H11/H12
PASS (Sleeper-vs-ADP disagreement carries aggregate, freshness-controlled information), H4/H7/H8v
FAIL. The 2026 Draft Board shipped from the validated band. Full ledger in that directory's
`PREREGISTRATION.md`; runbook in the `bettingedge-seasonal-h5-campaign` skill. Do not re-fire any
H-series test — they are one-shot and their results are frozen in `*_results.json`.

### Totals model (over/under) — SHIPPED, EXPERIMENTAL on the dashboard

A separate over/under model, independent of the spread model, exploiting the known retail
OVER-bias (books shade totals high). **UNDER-only** when both voters agree; OVER is noise
(~50.8%, below break-even). Full development path and the README's totals section carry the
rest of the story; the load-bearing facts for working here:

- **Strategy / tier logic:** HIGH = both XGBoost AND Ridge predict UNDER (both residuals < 0);
  PASS otherwise. No OVER bets.
- **Numbers:** consensus UNDER 55.7% CV (n=575, ~96 picks/season, 95% CI 51.6–59.7%); live 2025
  weeks 10–17 **52.2% on n=46** — at break-even, sample too small to separate the CV estimate
  from no edge. Stays labeled EXPERIMENTAL (amber/dashed badge, "tracking only — do not bet"
  banner) until a full 2026 season (~96 graded picks) is in.
- **Feature set:** 49 features = the 35 spread features + 14 totals-specific (`total_line`,
  implied team totals, `temp_f`/`wind_mph`/`is_dome`, rolling points 5g, `league_avg_total_4wk`,
  `pace_5g`, `div_game`).
- **INVARIANT — keep totals SEPARATE from spread.** `betting/features.py` is the spread source
  of truth and stays untouched; `betting/totals_features.ipynb` is the totals source of truth
  (`is_dome` re-merges the raw roof string, not the ordinal int — do not "fix"). Pipeline:
  `totals_model.ipynb` (CV + retrain) → `totals_xgboost.pkl` / `totals_ridge.pkl` (2014–2024,
  target `total_diff`) → `predict_totals.ipynb` (weekly, validates feature order at load).
- **Caveat:** `totals_tracker.csv` is backfilled for 2025 **weeks 10–17 only** — don't compute
  "full season" stats off it without accounting for the partial coverage.

## Completed Work

The dated implementation history moved to [`memory/completed-work-log.md`](memory/completed-work-log.md)
on 2026-07-12 to keep this file lean. See it for the full log — the feature-module extraction
(`features.ipynb` → `features.py`), the rejected time-decay / extended-range and weather / ensemble-
reweighting experiments, the notebook restructures and corruption recovery, and the CI wiring.

### Editing the shared features module

- The feature logic lives in **`betting/features.py`** (plain Python — edit with normal tools, no notebook json hacks). `betting/features.ipynb` is now thin documentation only.
- After editing, run `pytest betting/test_features.py` to verify all 15 hermetic tests pass (imports-smoke, constants + order-hash, the 2 pure helpers, each of the 10 feature groups, `build_features` integration, `build_numeric_features`). Runs in ~2 seconds, offline. This is the same suite CI runs.
- **If you change feature order** (`FEATURE_COLS_85` / `PROD_FEATURES_35`), the order-hash test fails by design — retrain the pkls and update the expected hash in `test_features.py` in the same commit.
- If you change any name in the public surface, no consumer-notebook loader edit is needed (they `globals().update(vars(features))`), but update the cell-structure tables / file descriptions in this CLAUDE.md.


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
