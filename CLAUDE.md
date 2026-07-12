# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BettingEdge is an NFL sports betting prediction system with two independent models:
- **Spread model**: Ensemble fixed75 as primary edge-setter (0.75 XGBoost + 0.25 Ridge), with XGBoost, Ridge, and LightGBM as three direction voters. HIGH/MEDIUM/PASS tiers.
- **Totals model**: XGBoost + Ridge predicting whether games go over/under the Vegas total. UNDER-only strategy (books shade totals high due to recreational OVER-bias). HIGH = both models predict UNDER.
- A Claude-powered LLM agent (via LlamaIndex) for qualitative game reasoning
- A Streamlit dashboard for visualization (deployed at joschobetting.streamlit.app)
- GitHub Actions for weekly automated predictions (Mon/Thu/Sun)
- A pre-season fantasy **seasonal draft board** (`fantasy/seasonal_projections/`), surfaced as the Draft Value Finder dashboard tab — our model's calls vs ADP (the standalone model beats casual ADP on confident calls but not Sleeper). Includes a built 2026 pre-draft board.

## Next Session TODO (as of 2026-06-06)

**Seasonal status (2026-06-06):** the draft-board arc is built (Model A + B + rookie model + three-way blend + 2026 pre-draft board) but its **dashboard tab is currently DISABLED** (commented out via `if False:` in `app.py` — see the app.py entry in Core Files; user turned it off while deciding whether to ship). A 2026-06-06 **value-edge research dig** (reframe to the Sleeper-residual target) found a real-but-marginal opportunity-driven signal that beats casual ADP but not Sleeper, and confirmed we're noise-limited on ~6 seasons of ADP — full detail in the "Value-edge research" subsection below + memory `[[seasonal-projections-no-adp-edge]]`. **Open decision (deferred by user):** ship a modest ADP-flag overlay (re-enabling a reframed tab) / try Vegas win totals / pivot to player props. Nothing seasonal is on the live site right now.

The earlier **seasonal draft-board arc is built** (kept, just off the live site): Model A + Model B + rookie model, a **three-way blend** (our 0.2 / ADP 0.3 / Sleeper-projection 0.5) as the recommended draft order, a **2026 pre-draft board** (`build_2026_board.py` seeds 2026 rosters/rookies + 2025 priors; 2026 Sleeper ADP already exists), and the (now-disabled) dashboard Draft Board (Beta) tab with a season selector (2026 + 2025). All documented + tested. Remaining seasonal work is light:
- **2026 board freshness (through Aug 2026)** — 2026 ADP grows from ~245 players now toward ~1,800 by late-August drafts. Periodically re-run `fetch_adp.py` (refreshes the 2026 cache) then `build_2026_board.py` + `BOARD_SEASON=2026 build_draft_board.py` to firm up the board as ADP matures.
- **After the 2025 season is final / new data** — re-run `build_season_dataset.py` (rebuilds 2014-2025; note nflreadpy data drifts) and optionally fold 2025 into Model A/B/rookie training, then rebuild the board. `build_2026_board.py` keeps the trained 2014-2025 rows verbatim and only appends fresh 2026 rows, so it does NOT silently retrain the board on drifted data.

**The real next priorities are the betting-side execution items** (from the README "What's Next" — this is where the leverage is, the models are at their ceiling). Good offseason work, ready before Week 1:
1. **Closing Line Value (CLV) tracking** — columns already reserved in `predictions_tracker.csv`; needs a line source at pick time + near kickoff. Best long-term-profit signal and a prerequisite for judging everything else.
2. **Player props model** — new, less-efficient market; reuse the 8 per-stat fantasy models to grade prop lines (over/under our projection).
3. **Multi-book line shopping** + **Kelly fractional sizing** — execution wins that compound.

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
- **`app.py`** — Streamlit dashboard, 7 tabs: Weekly Predictions, Track Record, Weekly Fantasy, DFS Optimizer, **📋 Draft Value Finder** (`tab5`), League History, Help & Guide. The pure, Streamlit-free helpers (`metric_card`, `get_confidence`, `_md_to_html`, `load_tracker`, `load_totals_tracker`) were extracted to **`dashboard_utils.py`** (2026-06-15) so they're unit-testable without a Streamlit runtime (`test_dashboard_utils.py`, in CI); `load_tracker` keeps its `@st.cache_data` behavior via a cached shim in app.py. The tab-rendering code stays in app.py (it's `st.*`-procedural and covered by `test_app_draft_board.py`'s AppTest). (Display labels renamed 2026-06-12 for first-time-visitor clarity: "Season Performance"→"Track Record", "Fantasy"→"Weekly Fantasy", "DFS"→"DFS Optimizer", "Seasonal Value"→"Draft Value Finder"; internal file/code names like `value_board_*.csv` / `build_value_board.py` unchanged.) **The seasonal tab was reframed + re-enabled 2026-06-08 as the value finder** — it renders `fantasy/seasonal_projections/value_board_{season}.csv` (built by `build_value_board.py`), which is **our model's calls vs ADP**, NOT the old three-way blend board. Headline = our independent LightGBM projection (no Sleeper) ranked vs ADP within position → `value = adp_rank − our_rank` → **BUY** (undervalued) / **FADE** (overvalued, gated to decline-catalyst + not-young). Confidence tiers (HIGH = gap ≥8). **Sleeper's projected rank is shown as a comparison column only** (with a "Sleeper agrees" flag) — explicitly NOT part of our call (the edge is ours-vs-ADP, ~68% on HIGH buys; we do NOT beat Sleeper, and shipping Sleeper-as-our-edge was rejected as bad practice). Dashed-amber honest-scope banner (BETA label/badge removed 2026-06-12 — tab promoted out of beta). **Headline "🔥 Consensus values" box (2026-06-12):** leads the tab with the players our model AND Sleeper BOTH rank above ADP (call==BUY & sleeper_agrees) — the strongest signal (~78% beat their ADP vs ~68% our-model-alone), ranked by combined gap, with ✅/❌ for completed seasons. **Injury handling (2026-06-12):** players who missed >6 games (`injured` col, `target_games < 11`) show **🏥** instead of a graded ✅/❌ in both the consensus box and the Result column — they're not scored either way, consistent with `surprise_eval.py`'s injury filter (injury timing is unpredictable; our BUYs aren't more injury-prone than the field, ~14% vs ~18%). Season selector (2025 completed w/ actuals, 2026 upcoming), position filter. `test_app_draft_board.py` (renamed test `test_seasonal_value_tab_*`) drives it. The OLD draft-board code (`build_draft_board.py` three-way blend, `board_view.py`) is retained on disk but is NO LONGER what the tab renders. Reads `betting/predictions_tracker.csv` and `betting/totals_tracker.csv`. Game cards show a **dashed amber EXPERIMENTAL UNDER badge** when the totals model has a HIGH pick — amber instead of green/purple because live 2025 is only at break-even and the model hasn't been confirmed profitable yet. Season Performance totals section is gated with a "tracking only — do not bet" warning banner. (A 💰 unit stake chip was on the game cards 2026-05-28 to 2026-06-03, then removed at the user's request — the units weren't wanted.) Fantasy tab shows per-week projections per position with projected and actual stat columns. **Draft Board tab (built 2026-06-03, currently disabled per above)** reads `fantasy/seasonal_projections/draft_board_{season}.csv` with a **season selector** (shows 2026 + 2025), rendering the **three-way blend** ranking (our 0.2 / ADP 0.3 / Sleeper-projection 0.5, `blend_rank`) under a **dashed amber BETA banner** (same honest-disclosure styling as totals) — because the standalone model loses to the market and the blend, while a real gain, is a consensus not a secret edge; shows value/reach call-outs and a position filter. Help & Guide has a matching "What is the Draft Board tab? (Beta)" entry.
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

A **pre-season** fantasy projection / draft-board system, distinct from the in-season weekly model. Goal: project each player's upcoming season, rank into a draft board, and compare to the market (Sleeper ADP) to surface values and reaches — the fantasy analog of the betting side's "model vs the Vegas line" edge thesis (here the market line is ADP). **As of 2026-06-02 both models are built (CatBoost) and evaluated; the honest verdict is that the system does NOT beat ADP** — it's a fine projection/cross-check tool but not a draft-board edge (see the Modeling section below).

**Why a separate model from the weekly one:** the weekly model leans on in-season rolling features (recent EPA, recent target share) that don't exist before Week 1. This is a season-long projection built only from draft-time-available info (prior-season aggregates, multi-year trend, age, draft capital, team context).

### Files (pipeline runs in order)

| File | Output | Purpose |
|------|--------|---------|
| `_utils.py` | — | Shared `norm_name` (DRY, matches betting/features.ipynb convention; no early `break` so cached join keys stay identical) + constants (`ADP_SENTINEL=900`, `SKILL_POSITIONS`). |
| `fetch_adp.py` | `sleeper_adp_2020_2026.csv` | Caches Sleeper preseason ADP (`adp_half_ppr`) + Sleeper's own season projection (`sleeper_pts_half_ppr`), from the undocumented `api.sleeper.app/v1/projections/nfl/regular/{season}` endpoint. **2026 already has ADP (~245 players, growing).** ADP is never an input to the per-position models; Sleeper's projection IS used as a ranker in the board blend (not in the CatBoost models). |
| `build_season_dataset.py` | `season_dataset_2014_2025.csv` | One row per (player, season), 7,350 rows, prior-only features (no leakage), two targets, ADP joined for 2020+. |
| `test_seasonal_projections.py` | — | Hermetic test suite (7 tests, no network) for the dataset transformation logic + an output-integrity check on the real CSV. |
| `test_draft_board.py` | — | Hermetic tests (10) for the board logic: locks `BLEND_WEIGHTS` (our 0.2/ADP 0.3/Sleeper 0.5, sum=1), checks VOR math, the three-way blend ranking / value-gap / NaN+fallback handling, `parse_ht`, and that the output CSV has every column `app.py`'s Draft Board tab reads. |
| `model_a_compare.ipynb` | `model_a_compare_results.json` | 3-way bakeoff (CatBoost vs XGBoost vs LightGBM) per position, tuned via walk-forward CV, with a fair matched-subset baseline check. **CatBoost won at all 4 positions.** Kept as a notebook for future re-testing. |
| `train_model_a.py` | `models/{pos}_ppg_model.pkl` + `model_a_metrics.json` | Production Model A. One CatBoost per position, games-weighted, tuned params from the bakeoff JSON, train 2014-2024 / holdout 2025. |
| `train_model_b.py` | `models/availability_model.pkl` + `model_b_metrics.json` | Production Model B. One pooled CatBoost predicting `target_games`, trained on ALL rows incl. the 377 reconstructed 0-game seasons, `position` as native categorical, no sample weighting. |
| `build_draft_board.py` | `draft_board_{season}.csv` | Combines A×B → VOR, then a **three-way blend** (our 0.2 / ADP 0.3 / Sleeper-projection 0.5, `BLEND_WEIGHTS`) for the **recommended draft order** (`blend_rank`); also runs the walk-forward edge backtest. Globs the newest `season_dataset_*.csv`; season-parameterized via `BOARD_SEASON`; degrades gracefully for future / no-ADP seasons. |
| `build_2026_board.py` | `season_dataset_2014_2026.csv` | Seeds upcoming-season (2026) feature rows from `load_rosters([2026])` + 2026 rookies (draft/combine) + 2025-derived priors, reusing `build_season_dataset.build_feature_rows`. Keeps the trained 2014-2025 rows verbatim; appends fresh 2026 rows. Then `BOARD_SEASON=2026 build_draft_board.py` builds the pre-draft board. |
| `three_way_blend_test.py` | — | Sweeps the our/ADP/Sleeper blend weights (simplex grid + leave-one-season-out). Confirmed 0.2/0.3/0.5 beats the old 2-way 5/5 seasons OOS (+0.063 ρ); our model keeps weight. |
| `diagnose_vet_rookie.py` | — | Splits the walk-forward backtest into veterans vs rookies (the diagnostic that scoped the rookie model). |
| `rookie_features.py` | — | **Single source of truth** for rookie-model features: `COMBINE_COLS`, `ROOKIE_FEATS`, `parse_ht`, `load_combine_features` (cached), `add_rookie_features`. Imported by the trainer, the board, and the experiments. |
| `train_rookie_model.py` | `models/rookie_ppg_model.pkl` + `rookie_metrics.json` | Production rookie PPG model (CatBoost), games-weighted, tuned, train 2014-2024 / holdout 2025. |
| `rookie_model_experiment.py` | — | Original rookie bakeoff vs ADP on the rookie subset (standalone it loses to ADP). Kept as reference. |
| `rookie_blend_test.py` | — | A/B/C test of rookie handling inside the blend (veteran model / rookie model / pure ADP). **Showed the rookie model wins the rookie slice** → shipped. |
| `blend_experiment.py` | — | The original our/ADP two-way weight sweep (fine grid + LOSO); found w=0.30. **Superseded by the three-way blend** (`three_way_blend_test.py`) but kept for reference. |
| `README.md` | — | Pipeline order, design decisions, honest caveats + the verdict. |

### Data-source facts (verified empirically)

- **Sleeper ADP**: undocumented projections endpoint carries `adp_half_ppr` etc. ADP exists **2020+** only (2019 is 100% the `999.0` "undrafted" sentinel; pre-2019 has no ADP). Sleeper point projections exist 2018+. It's a **live rolling aggregate** of real drafts that freezes at the final draft-season (late-Aug) consensus for completed seasons. No timestamp in the data. Join to our data by **normalized name + position** (Sleeper's `gsis_id` is too sparse to join on, even for stars).
- **Model features come from `nfl.load_player_stats` (1999+)**, which carries `target_share`, `air_yards_share`, `receiving_air_yards` populated back to 2011 — so the air-yards/aDOT "NGS-like" signal needs no NGS endpoint and no PBP load, and 2014 has zero missing-value problem.

### Two-model design (target columns)

- `target_ppg` — half-PPR points per game (**Model A, production**). NaN when the player played 0 games or `< MIN_GAMES_TARGET` (3) — a tiny sample is a noisy label.
- `target_games` — games played (**Model B, availability**). Present for every row, including reconstructed full-miss seasons.
- `sample_weight` — games played, so Model A trusts a 2-game season far less than a 16-game one.
- Final draft value = projected PPG × projected games → value-over-replacement (VOR), ranked vs ADP. **Both models built 2026-06-02 (CatBoost).**

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

### Modeling — BUILT 2026-06-02 (CatBoost), with an honest negative verdict on the edge

**Model A (PPG, production).** Ran a 3-way bakeoff (CatBoost / XGBoost / LightGBM) per position, each tuned via walk-forward CV (val seasons 2021-2024), scored on the 2025 holdout with games-weighted MAE. **CatBoost won at all four positions** and was the only algo to beat the naive 3-year-average baseline everywhere — bakeoff kept as `model_a_compare.ipynb`. Production trainer `train_model_a.py` reconstructs each position's tuned params from `model_a_compare_results.json` and fits `dict(iterations=500, loss_function="MAE", random_seed=42, verbose=0, allow_writing_files=False, **best_params)` (best_params = depth / learning_rate / l2_leaf_reg). 2025 holdout matched-row wMAE (rookies excluded so the baseline can compete): **QB 2.78, RB 2.41, WR 1.84, TE 1.36**; ρ 0.75-0.83.

**Model B (availability / games).** One pooled CatBoost (`train_model_b.py`) predicting `target_games`, trained on ALL 6,740 rows incl. the 377 reconstructed 0-game seasons, `position` as native categorical, NO sample weighting (each player-season is one equal availability vote). Tuned grid → depth 6 / lr 0.03 / l2 3.0. 2025 holdout MAE **3.73 games**, beating "repeat prior games" (4.11) and "predict the mean" (5.34); ρ 0.57. Honest framing baked into the docstring: it separates durable/fragile tiers, it does not nail exact games (most injury variance is a freak hit).

**Draft board (`build_draft_board.py`).** value = PPG_pred × games_pred → **VOR** (value over replacement, baselines QB14/RB30/WR36/TE14) so the overall board isn't all-QBs. The headline ranking is the **three-way blend** of within-pool ranks (our VOR 0.2 / ADP 0.3 / Sleeper-projection 0.5, `BLEND_WEIGHTS`, see below); the raw VOR ranking drives the value/reach gap = `adp_pos_rank − our_pos_rank`. Writes `draft_board_{season}.csv`.

**THE EDGE THESIS FAILS — we do NOT beat ADP.** The first pass looked like a +0.12 ρ edge, but that was **leakage** (production pkls are trained through 2024, so backtesting 2020-2024 was in-sample). The corrected backtest **retrains both models walk-forward** (train on seasons `< N`, predict `N`), drafted pool only (ADP top 180), judged on actual VOR:

| | our VOR ρ | ADP ρ | edge |
|---|---|---|---|
| mean 2020-2024 | 0.488 | 0.552 | **−0.063** (ADP wins every year) |

Value-vs-reach buckets confirm it: players we'd "value pick" (gap ≥ +6) finished at **125** mean pts vs **160** for neutral and **157** for players we'd fade. When our model disagrees with the market, the market is usually right. 2025 season-total projection MAE: ours 38.8 vs Sleeper's own projection 36.8 (we're close but behind). **Same lesson as spread + totals: a market consensus prices in offseason/camp/depth-chart info a prior-season-stats model can't see.** As a standalone ranking the board is NOT draft-board alpha. See memory `[[seasonal-projections-no-adp-edge]]`.

**The positives: a THREE-way blend SHIPPED into the board (2026-06-03).** Two blend results, in order of impact:
- **Our + ADP (small, `blend_experiment.py`):** our standalone projection loses to ADP, but it carries a little *independent* signal, so 0.30·our + 0.70·adp beats pure ADP in 5/5 seasons — but only by +0.012-0.015 ρ (within pooled noise; real direction, marginal size). This was the first shipped blend.
- **Our + ADP + Sleeper's projection (the big one, `three_way_blend_test.py`):** Sleeper publishes its own season point projection (`sleeper_pts_half_ppr`), which alone (ρ 0.569) already beats ADP (0.555). Adding it as a third ranker is a **much bigger, robust gain**. Pooled best weights **our 0.20 / ADP 0.30 / Sleeper 0.50** lift the board to **ρ 0.637 vs 0.567 for the old 2-way (+0.07, ~2 SE)**. Confirmed by leave-one-season-out: held-out 3-way beats the 2-way in **5/5 seasons, mean +0.063**, with LOSO weights clustering tight (median 0.2/0.3/0.5). Crucially **our model still earns weight 0.2** — the full 3-way (0.637) beats ADP+Sleeper-without-us (0.628), so our independent projection isn't redundant. Sleeper's projection is a genuine *forward* projection (MAE vs actual ~37, not ~0), so it's clean to use at draft time, exists 2018+.

**Shipped:** `build_draft_board.make_board` now blends three within-pool ranks via `BLEND_WEIGHTS = {"our":0.20,"adp":0.30,"sleeper":0.50}` (missing Sleeper defers to ADP; ~99% pool coverage). `blend_rank`/`blend_pos_rank` are the headline recommended draft order; the standalone VOR ranking is retained for the value/reach view. **This is the real positive of the seasonal project** — a market-blend that out-ranks any single source, with our model contributing a small independent slice. Framing for the dashboard: still "a blended consensus, not a secret edge." **Surfaced in the dashboard** (2026-06-03) as the **Draft Board (Beta)** tab in `app.py` (tab5), with a season selector (2026 + 2025), reading `draft_board_{season}.csv` under a dashed-amber BETA banner and the honest "Sleeper 50% / ADP 30% / our model 20%" disclosure.

**Two leakage traps caught during this build (lessons):** (1) raw PPG×games stacks all QBs at the top of an overall board — use VOR; (2) any backtest of a model whose training window covers the backtest years is in-sample — retrain walk-forward or the edge is fiction. Both bit the first pass before correction.

**Vet-vs-rookie diagnostic (2026-06-03, `diagnose_vet_rookie.py`).** Split the same walk-forward backtest by `is_rookie` to see whether the ADP shortfall is all rookies or across the board. Pooled 2020-2024 (drafted pool, n=869): **veterans** (750, 86%) ours ρ 0.506 vs ADP 0.544 (edge **−0.038**, we edged ADP in 2022 and 2024); **rookies** (119, 14%) ours ρ 0.172 vs ADP 0.462 (edge **−0.290**). Our rookie ρ is noise (−0.095 in 2024) — the model dumps every rookie into one low VOR clump (range −144 to +24) because it has no prior-season data to separate them. So: **rookies are the dominant drag, but we only *match* (don't beat) ADP on veterans either.**

**Rookie model — BUILT and SHIPPED into the board blend (2026-06-03).** A dedicated rookie CatBoost on info the veteran model never sees: draft capital + **combine measurables** (`nfl.load_combine`: forty/bench/vertical/broad_jump/cone/shuttle/ht/wt, joined to our gsis `player_id` via the `load_draft_picks` pfr-id bridge, ~93% coverage on drafted rookies, 51% across all rookies) + landing-spot features. (College production is NOT in nflreadpy.) Feature engineering lives in `rookie_features.py` (single source of truth: `COMBINE_COLS`, `ROOKIE_FEATS`, `add_rookie_features`); trained by `train_rookie_model.py` → `models/rookie_ppg_model.pkl` (2025 holdout PPG wMAE **2.06** vs 2.89 position-mean baseline; depth 6 / lr 0.03 / l2 3.0).
  - **Standalone it does NOT beat ADP** (rookie ranking ρ 0.26 vs ADP 0.46) — confirming the earlier "no angle" call. But **inside the blend it does**: `rookie_blend_test.py` compared three ways to handle rookies in the 70/30 blend (A=veteran model [shipped status quo], B=rookie model, C=pure ADP). Walk-forward mean rookie-slice ρ: **A 0.457, B 0.488, C 0.457** — the rookie model (B) is the only option that clears pure ADP on rookies (ensemble effect: its errors are independent of ADP's), +0.031 over status quo in 4/5 seasons, with **no overall-board regression** (overall ρ A 0.561 / B 0.564 / C 0.566, all within noise). So B was shipped.
  - **Wiring:** `build_draft_board.predict(df, model_a, model_b, rookie_model)` overrides rookies' `ppg_pred` with the rookie model when the pkl is present (graceful fallback to the veteran model if absent). This flows into `vor` → the blend → `value_gap`. **The standalone-vs-ADP edge backtest (`eval_edge_thesis`) deliberately calls `predict` WITHOUT the rookie model**, so that documented thesis (we lose to ADP standalone) is unchanged. Shipping the rookie model improved the board's 2025 PPG MAE 2.064 → 2.008 and season-total MAE 38.8 → 38.3.

**Building / refreshing the upcoming-season board.** A true *pre-draft* board (season with zero games played) IS built — `build_2026_board.py` seeds the upcoming player population from `load_rosters` + that draft's rookies (draft/combine) and attaches prior-year priors via the same `build_feature_rows` prior-join the training data uses, so no reimplementation. It keeps the trained 2014-2025 rows verbatim (nflreadpy drifts; the models trained on the existing dataset) and only appends fresh upcoming-season rows → `season_dataset_2014_2026.csv`. `build_draft_board.py` globs the newest dataset, so `BOARD_SEASON=2026 python build_draft_board.py` then produces `draft_board_2026.csv`, and the dashboard season selector shows it. To refresh as 2026 ADP matures (it grows from ~245 players now toward ~1,800 by late-Aug drafts): re-run `fetch_adp.py` → `build_2026_board.py` → `BOARD_SEASON=2026 build_draft_board.py`. For a future year (2027), generalize `build_2026_board.py`'s `UPCOMING` constant. `build_draft_board.py` also still degrades gracefully for a season with no rows / no ADP.

### Value-edge research → ADP-MISPRICING SKILL (canonical eval `surprise_eval.py`, 2026-06-08)

A long dig (2026-06-06/08) for an actual over/under-valued-vs-ADP edge. **Full detail + numbers live in memory `[[seasonal-projections-no-adp-edge]]`.** Bottom line evolved:

- **The evaluation was the problem.** MAE / rank-ρ are dominated by easy calls (Chase top-5 = zero edge); they hid a real signal. **The canonical seasonal eval is now `surprise_eval.py`**, which grades CONDITIONAL ON ADP: `edge = corr(our_dev, actual_dev)` where `our_dev = adp_pos_rank − our_pos_rank` and `actual_dev = adp_pos_rank − actual_pos_rank`. Mid-season-injury seasons (missed >6 games, `MIN_GAMES_PLAYED=11`) are EXCLUDED — injuries are unpredictable noise. Result: pooled 2021-2025 **ADP-mispricing skill +0.20 (placebo ~0, positive every season)**; bold calls +8pp; surprise-catch 59%. We catch OPPORTUNITY/role surprises, miss INJURY ones. **The board is reframed around this** (see `build_draft_board.py` docstring): its job is identifying value vs ADP, not winning the overall ranking (it loses that to ADP — wrong lens). **Honest boundary: edge is vs ADP [cleared]; Sleeper also beats ADP, and vs Sleeper it stays marginal.**
- **Earlier (2026-06-06) marginal-signal arc** (Sleeper-residual reframe, +0.10-0.15 ρ; opportunity features / QB context / broader-training all OVERFIT the ~700-row sample; FFC historical ADP 2014-19 added via `fetch_historical_adp.py` → 11 seasons but the edge stayed unstable/fading vs Sleeper). We are noise-limited vs Sleeper, but the conditional-on-ADP skill is real.

**Model findings (eval = `eval_projection.py` MAE panel + `model_bakeoff.py`):** LightGBM/RF/XGBoost all beat production CatBoost by ~0.15-0.17 PPG MAE at every position (CatBoost *hyperparam* tuning does nothing — it's the algorithm); drop injury features from the PPG model (slightly helps — rate is injury-independent); on TOTALS the availability/games model HURTS (`ppg×predicted-games` 66.5 vs `ppg×const-16.5` 52.6) so use constant games — **injuries are a totals problem, not a rate problem**; best total method = blend(0.4·our-const + 0.6·Sleeper) MAE 50.2 < Sleeper 53.6. Contingent-opportunity feature (`contingent_features.py`, teammate-injury-risk-weighted, leak-safe) = sound idea, no usable signal (injury timing unpredictable).

New research files (all on disk, NOT wired into the dashboard, tab still disabled):
- `surprise_eval.py` — **CANONICAL EVAL**: ADP-mispricing skill (corr of deviations), bold-call + surprise-catch hit-rates w/ placebo, 2025 scorecard, injury filter. **Refactored 2026-06-08 to use the exact SHIPPED config** (per-position LightGBM, base-minus-injury) so it measures what the tab serves (was a pooled+college config; numbers unchanged: +0.20 skill, +10pp bold, 69% buys).
- `build_value_board.py` — **SHIPPED tab data**: loads Model A pkls, ranks the drafted pool vs ADP, emits BUY/FADE + tiers (fades gated to decline-catalyst, not young), Sleeper rank as comparison only → `value_board_{season}.csv`. **Incoming-competition guard (2026-06-08, `incoming_competition.py`):** our prior-stats model can't see touches ARRIVING, so it over-likes incumbents whose room just got more competition (the James Conner / Trey Benson problem). The guard SUPPRESSES a BUY → **⚠️ Contested** when a real new threat joined the player's position room: a round≤2 rookie, a free-agent/trade arrival (roster-change by gsis_id, bell-cow prior usage), a returning-from-injury starter (missed ≥6 g, high career PPG), or a 4-deep crowded RB backfield. Conservative + **elite-gated** (top-12-at-position incumbents are never flagged) so it doesn't fade clear starters; QBs excluded. Suppressed ~14 buys (2025) / ~8 (2026). The board CSV gains a `contested` column; the app shows "⚠️ Contested (reason)" in the Verdict. **Rookie projections (2026-06-08):** rookies have no prior NFL stats, so Model A can't see them — `build_value_board` now overrides rookie (`is_rookie==1`) projections with the dedicated **rookie model** (`models/rookie_ppg_model.pkl`, draft capital + combine + landing spot via `rookie_features.add_rookie_features`). Result: rookies are projected sensibly (PPG 1.5-12.9, differentiated) and visible, but get **no buy/fade call** (young → fades blocked; our rookie ranking loses to ADP so we don't pretend a rookie edge). **Rookie SEEDING BUG fixed (2026-06-08):** `build_2026_board.seed_upcoming_rows` seeded the 2026 population from `load_rosters([2026])` only, but the **roster feed lags the draft** — so drafted rookies (even Jeremiyah Love, #3 overall, who HAS Sleeper ADP rank 18) weren't seeded and never reached the board. It now also adds every drafted UPCOMING skill rookie from `load_draft_picks`, normalizing the pfr draft-team abbrev to the roster convention via `DRAFT_TEAM_MAP` (ARI→AZ, GNB→GB, etc.) so they group with their real teammates (id = gsis else `pfr_<id>`). Added 80 rookies (90→170); Love now appears (drafted RB11, our RB18, "—"), and the competition guard correctly reads Conner as "⚠️ Contested (rookie)". Still a timing reality: only top-pick rookies have ADP by June, so the rest enter as ADP fills over the summer (re-run `fetch_adp.py` → `build_2026_board.py` → `build_value_board.py`). **Pre-ship code review (independent agent + self):** no leakage / no crash bugs; fixes applied — `const_games(df)` from the building dataset (not a hardcoded path), feature-drift assertion (`feature_cols ⊆ dataset`), ≥50%-graded guard before computing actuals, NaN-safe call-outs. **Table is human-readable:** ranks are numeric (so they sort 1,2,..,10,11) but displayed `RB12`-style via `column_config` NumberColumn format when a position is filtered; a single plain-English **Verdict** column (🟢 Strong buy / 🔴 Fade / ⚠️ Contested / —) + a ✅/❌ **Result** for completed seasons (the board CSV also gains an `injured` column = `target_games < 11`; those rows render **🏥 injured** instead of a graded hit/miss, matching the eval's injury exclusion).
- `eval_projection.py` — PPG MAE panel (MAE/RMSE/bias/medAE/r/R²/hit<3) ours vs Sleeper vs naive vs blend.
- `model_bakeoff.py` (+ `_validate_models.py`) — algorithm + hyperparameter bakeoff on PPG; LightGBM/tree-ensemble win.
- `eval_totals.py` / `totals_board_2025.py` — season-total eval (availability model hurts; constant games + Sleeper blend best) + 2025 totals board.
- `rankings_2025.py` — 2025 rankings from the best standalone model, best position.
- `contingent_features.py` / `eval_contingent.py` — teammate-injury-risk opportunity (no signal).
- `fetch_historical_adp.py` → `ffc_adp_2014_2019.csv`, `value_eval.py`, `value_eval_extended.py`, `adp_value_model.py`, `fetch_college.py` → `college_features.csv`/`college_production_2014_2024.csv`, `college_rookie_test.py`, `opportunity_features.py`, `qb_context_features.py` → `qb_context_features.csv` — earlier-arc research (see memory).
- transient run logs (`_*.log`): safe to delete / not commit.
- **Scratch cleanup (2026-06-12):** removed 8 undocumented one-off scratch scripts from `fantasy/seasonal_projections/` (`deep_dive.py`, `show_2025_table.py`, `adp_calls_2025.py`, `ppg_eval.py`, `value_board_2025.py`, `compare_call_methods.py`, `improve_calls.py`, `leakage_check.py`) — pure digging-session scratch, nothing imported them, recoverable from git history. `fade_deep_dive.py` was kept (it's cited by `build_value_board.py`'s docstring and the README as the justification for the fade gate). The documented research arc (bakeoffs, evals, blend tests, old three-way-blend board) was retained.

### Editing / running

```bash
python fantasy/seasonal_projections/fetch_adp.py            # refresh ADP cache
python fantasy/seasonal_projections/build_season_dataset.py # rebuild dataset (~1-2 min)
python fantasy/seasonal_projections/test_seasonal_projections.py
python fantasy/seasonal_projections/train_model_a.py        # production Model A (4 CatBoost pkls)
python fantasy/seasonal_projections/train_model_b.py        # production Model B (availability pkl)
python fantasy/seasonal_projections/build_value_board.py    # SHIPPED tab data: value_board_{season}.csv (our calls vs ADP + Sleeper + incoming-competition guard)
python fantasy/seasonal_projections/incoming_competition.py # preview which incumbents face a new rookie/signing/return/crowded room
python fantasy/seasonal_projections/build_draft_board.py    # OLD three-way-blend board (retained, not what the tab renders)
python fantasy/seasonal_projections/surprise_eval.py        # CANONICAL eval: ADP-mispricing skill (2026-06-08)
python fantasy/seasonal_projections/eval_projection.py      # PPG MAE metric panel (ours/Sleeper/naive/blend)
python fantasy/seasonal_projections/model_bakeoff.py        # algorithm + hyperparameter bakeoff (LightGBM wins)
python fantasy/seasonal_projections/value_eval.py           # earlier value-edge research eval suite (2026-06-06)
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
3. ✓ `betting/predict_totals.ipynb` — papermill-compatible weekly inference (MODE parameter). Imports `features.py` and loads `totals_features.ipynb`. Validates feature order against pkls at load time.
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

**2026-07-12 (Board integration — Draft Board moved into main-app tabs; Draft Value Finder RETIRED):**
- Joseph's ruling after localhost preview: the pages/ multipage sidebar didn't fit the single-page convention, and the board is redundant with the legacy finder. **`pages/` deleted**; the board now renders as main-app tab **"📋 Draft Value 2026"** in the retired tab's slot (`app.py` line 486 label + tab5 body → `import draft_board_2026; draft_board_2026.render()`). New module **`draft_board_2026.py`** carries the Piece 5 content unchanged (filters keyed `db26_*`, licensed labels, separate talent column, methodology footer; page-level `set_page_config`/GA chrome dropped — the app-wide GA pageview is the tab convention).
- **Draft Value Finder retired, not merged**: the ~218-line inline tab5 block removed from app.py (git history preserves it); engine files (`build_value_board.py`, `value_board_*.csv`, guards) all kept; its 5 inline helpers had zero external references. NOTHING ported (BUY/FADE verdicts, Consensus box, tiers are unlicensed surfaces).
- **Known follow-ups needing Joseph's ruling**: (1) `test_app_draft_board.py` (CI `pytests` job) drives the retired tab and will fail until retargeted or dropped; (2) Help & Guide still contains "What is the Draft Value Finder tab?" — stale copy, left untouched (no-copy-edits scope); (3) legacy candidates NOT ported: 2025 completed-season board w/ ✅/❌/🏥 grading, season selector.
- AppTest: full app renders (18 tab labels incl. "📋 Draft Value 2026", 0 exceptions/errors); board filters/search flip clean inside the main app; pages/ sidebar gone.

**2026-07-12 (Piece 5 — 2026 Draft Board page + band regen + dataset population fix; SHIPPED pending Joseph's commit):**
- **New Streamlit page `pages/1_📋_2026_Draft_Board.py`** (first use of the multipage convention; existing `app.py` untouched — pages/ auto-registers in the sidebar). Renders `fantasy/seasonal_projections/phase4_band_2026.csv` joined with `talent_index_2026.csv`: sortable board with position/ADP/name/validation filters, P10–P90 bands, P(top-12/24), bust prob, a descriptive `value_gap` column (no tiers, no buy/sell language anywhere), a visually-separate descriptive talent column (per-row metric naming; rookie rows show college-share context + draft capital as display facts), per-row licensed validation labels, and an always-visible methodology footer. GA measurement-protocol pattern mirrored from app.py with a page-specific title. AppTest: new page renders clean incl. filter/search flips; `apptest_all_tabs.py app.py` PASS (18 tabs, 0 exceptions/errors).
- **`build_2026_board.py` fixes (dataset population):** (1) added the missing `bsd.add_context_team(full)` call — the script predated the 2026-07-09 leakage-fix refactor and had been crashing (`KeyError: context_team`); (2) new third seeding source: ADP-holding unsigned veterans absent from both the roster feed and the draft class (the Diggs/Hill/Deebo gap — same class as the 2026-06-08 rookie seeding fix), seeded from the Sleeper ADP cache with ids/names from their most recent prior dataset rows, `team=NaN`. Rebuilt `season_dataset_2014_2026.csv` (923 2026 rows; 2014–2025 verbatim).
- **`phase4_band.py` re-run UNMODIFIED** (LOSO 80% = 79.4%, 50% = 49.8% — reproduces the recorded v2 validation exactly; artifact regen byte-equivalent on all 180 rows/numbers). New `apply_board_labels.py` post-process adds in-schema population flags (`stable_role` 102 / `volatile_rb_wr` 60 / `volatile_qb_te` 18) + the H11/H12-licensed `signal_status` wording + `value_gap`. `build_talent_index.py` rebuilt against the repaired dataset (desync flag eliminated).
- Known environmental: `test_app_draft_board.py` fails locally under pandas 3.0.3 (StringDtype vs object assert) — passes under the CI pin (pandas 2.3.3); pre-existing, unrelated to this change.

**2026-06-15 (feature code extracted from notebook → `betting/features.py`; deps pinned; tests in CI):**
- **`betting/features.ipynb` → `betting/features.py` (the deepest refactor).** Extracted the 85-feature pipeline VERBATIM from the notebook's code cells into a plain importable module (the production code cells concatenated in order with section headers). Notebook storage was the weakest link (a char-by-char-corrupted cell and inconsistent `ensure_ascii` were both hit the same week). Now the source of truth is ordinary, diffable, testable Python.
  - **`betting/test_features.py`** — the former inline `if RUN_TESTS:` cells ported to 15 pytest functions (synthetic fixtures + per-group tests + the order-hash contract test). Runs offline in ~2s.
  - **All 4 consumers rewired** off the json+exec loader to `import features` + `globals().update(vars(features))` (mirrors the old `exec(globals())` namespace exactly, including `_build_*` helpers): `predict_betting.ipynb` cell 28, `model_comparison.ipynb` cell 5 (keeps the `FEATURE_COLS`/`_canonicalize_ngs_team` back-compat aliases), `predict_totals.ipynb` cell 4, `totals_model.ipynb` cell 5. **predict_totals/totals_model were easy to miss — they also json+exec'd features.ipynb.**
  - **`features.ipynb` is now a thin documentation notebook** (one import cell + the design-rationale markdown), defining no production code.
  - **Equivalence proven WITHOUT retraining** (pkls unchanged — only code *location* moved): order-hashes still `c1822ba8…` / `ac880107…`; `pd.testing.assert_frame_equal` confirms `features.py`'s `build_features` output is byte-identical (1×119, dtypes match) to the old notebook version; `predict_betting` + `predict_totals` papermill-run on LIVE data through all inline tests, stopping only at the offseason guard.
  - **CI:** `test.yml` `features` job now runs `pytest betting/test_features.py` (was `papermill features.ipynb`). Full local sweep: 38 tests green (15 features + 7 seasonal + 15 draft-board + 1 app).
- **Dependencies pinned + completeness fixes.** `requirements-ci.txt` (drives the unattended weekly cron) pinned EXACTLY to known-good versions incl. `polars`/`pyarrow` (nflreadpy's transitive drift vector). `requirements.txt` got bounds on every previously-unpinned dep, **added missing `catboost`** (imported by `build_draft_board.py` but absent → broke fresh installs) and **`scipy`**, and bumped `plotly` ceiling `<6.0`→`<7.0` (the old cap excluded the 6.7.0 actually in use). New `requirements-test.txt` for the test job.
- **Python test suites wired into CI** (new `pytests` job): `test_dashboard_utils.py`, `test_seasonal_projections.py`, `test_draft_board.py`, `test_app_draft_board.py` — previously manual-only (or nonexistent), now run on every push/PR (explicit file list so the network/training `*_test.py` research scripts aren't collected).
- **`app.py` → pure helpers extracted to `dashboard_utils.py`.** `metric_card` / `get_confidence` / `_md_to_html` / `load_tracker` / `load_totals_tracker` moved to a Streamlit-free module (unit-tested by `test_dashboard_utils.py`, 10 tests); app.py imports them (call sites unchanged except the two loaders now take `_HERE`; `load_tracker` keeps caching via a `@st.cache_data` shim). app.py 2934→2891 lines; AppTest confirms the dashboard still renders. Tab-rendering left in app.py (st-procedural, not unit-testable in isolation). Full local sweep after both #4+#5: **48 tests green**.

**2026-05-28 (5 quick wins + dual code review):**
- **Fantasy 2025 holdout retain + infra fixes:** kept `TRAIN_SEASONS=[2020-2024]` / `TEST_SEASON=2025` (2025 stays the holdout for now); fixed `early_stopping_rounds` (moved to `XGB_PARAMS` constructor in both `model.ipynb` and `retrain_models.py` — XGBoost 3.x rejects it in `fit()`, so retrain was previously broken); guarded empty-holdout eval/profile cells; retrained all 12 models via `retrain_models.py` (holdout MAE QB 6.81 / RB 4.40 / WR 3.96 / TE 3.16).
- **DFS export fixed** — `dfs_pipeline.ipynb` cell 19 now writes proper DK Classic columns (`QB,RB,RB,WR,WR,WR,TE,FLEX,DST`) via consume-from-slot; unit-tested.
- **CLV columns** added to `predictions_tracker.csv` (`pick_line`, `closing_line`, `clv`; empty, reserved for 2026).
- **Agent in CI** — `weekly_predictions.yml` runs `sports_betting_agent.ipynb` Tuesday-only with a Tuesday-only conditional install of agent deps (llama-index/anthropic are excluded from `requirements-ci.txt` to keep Thu/Sun lean); `continue-on-error` so an agent/API failure never blocks the tracker commit.
- **Kelly stake chip** on game cards (💰 2u / 1u / 0.5u by tier + edge; visual only). *(Removed 2026-06-03 at the user's request — units weren't wanted.)*
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

### Editing the shared features module

- The feature logic lives in **`betting/features.py`** (plain Python — edit with normal tools, no notebook json hacks). `betting/features.ipynb` is now thin documentation only.
- After editing, run `pytest betting/test_features.py` to verify all 15 hermetic tests pass (imports-smoke, constants + order-hash, the 2 pure helpers, each of the 10 feature groups, `build_features` integration, `build_numeric_features`). Runs in ~2 seconds, offline. This is the same suite CI runs.
- **If you change feature order** (`FEATURE_COLS_85` / `PROD_FEATURES_35`), the order-hash test fails by design — retrain the pkls and update the expected hash in `test_features.py` in the same commit.
- If you change any name in the public surface, no consumer-notebook loader edit is needed (they `globals().update(vars(features))`), but update the cell-structure tables / file descriptions in this CLAUDE.md.

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
