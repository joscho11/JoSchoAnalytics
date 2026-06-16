# BettingEdge: NFL Prediction System

Live dashboard: [joschobetting.streamlit.app](https://joschobetting.streamlit.app)

---

## What This Is

I built this to find out if a data-driven model can actually find an edge against the spread. Anyone can pick winners. The harder question is whether you can consistently beat the number Vegas sets.

The answer so far is yes. Across the 2025 live test (weeks 10 through 17, 117 graded games) the ATS model sits at **56.4% overall**, with **HIGH-confidence picks at 64.7%** (11/17) and **MEDIUM-confidence picks at 59.5%** (25/42). Break-even after the bookmaker's cut is 52.4%.

The repo is the full system: ATS predictions, an experimental over/under model, fantasy football projections, a DFS lineup optimizer, and an LLM agent that explains why the model likes or fades each game.

---

## The Thinking Behind It

This section is the part I care about most, because the modeling choices only make sense once you understand the problem.

### You are not predicting who wins. You are beating a number.

When a book posts "Chiefs by 7," that line is not their honest guess at the final margin. It is the number that splits betting money close to evenly so they collect their cut no matter who wins. At standard odds you risk 110 to win 100, which means you have to win **52.4%** of your bets just to break even. That number is the bar everything in this project is measured against.

So the goal is narrow and hard: figure out which side of an already-sharp line is mispriced, often enough to clear 52.4%. The market is efficient, the edge is thin (high-50s percent at best), and most of the engineering is about finding that edge without fooling myself into seeing one that is not there.

### Why these features

The model builds 85 features per game and uses the top 35 in production. The ones that carry the most signal:

- **Rolling EPA (Expected Points Added).** The single most important input. EPA measures how much each play moved a team toward scoring, accounting for down, distance, and field position. A 5-yard gain on 3rd-and-4 is worth far more than the same gain on 1st-and-10. It is a much better read on team quality than raw yards or points. I use a 5-game rolling window for both offense and defense.
- **Strength of schedule.** A team's stats mean nothing without knowing who they played. I track opponents' win percentage so dominant numbers against weak teams get discounted.
- **All-Pro roster quality.** Talent is predictive but hard to quantify. All-Pro selections are a clean public talent signal. I weight them over a 3-year lookback (4/2/1, since recent selections matter most and talent decays), split by offense and defense.
- **Injuries.** Instead of a standalone flag, injured stars (Out or Doubtful) get subtracted from a team's weighted All-Pro score. So a starting QB being ruled out automatically deflates that team's talent rating. Injuries feed straight into the talent feature.
- The rest: rolling points and win percentage, situational stats (sacks, turnovers, 3rd-down rate), QB-change flags, prior-year passer rating from Next Gen Stats, and coach win percentage.

I trimmed 85 features down to 35 after an ablation study showed that dropping the lowest-importance features actually improved the cross-validation score. Fewer features means less room to overfit noise. The pipeline still computes all 85 for analysis, but only the top 35 (ranked by combined model importance) train the production models.

### Why no data leakage, ever

Every rolling feature uses `shift(1).rolling(N)`, which guarantees a game's own result never sneaks into its own prediction. This sounds obvious but it is the easiest way to build a model that looks brilliant in backtest and loses money live. The whole pipeline only ever uses information that existed before a given game kicked off.

### Why an ensemble, and why three voters

There are two jobs being done.

**Setting the edge.** The primary model, "Ensemble fixed75," is a fixed blend of 75% XGBoost and 25% Ridge. It predicts the home margin, which gets compared to the Vegas spread to find the edge. The two are blended on purpose:

- **XGBoost** (gradient-boosted trees) captures nonlinear interactions, the "this matters only when that is also true" patterns. Powerful, but it can overfit.
- **Ridge** (linear regression with L2 regularization) is a stable, regularized baseline. It cannot model interactions but it does not chase noise.

Blending them dampens XGBoost's variance with Ridge's stability. I swept the 75/25 weight and it is near optimal. Retuning it was tested and rejected as noise.

**Voting on direction.** Three independent models (XGBoost, Ridge, LightGBM) each pick a side. LightGBM grows its trees leaf-first rather than level-first, so it makes genuinely different mistakes than XGBoost. The idea: different algorithms err differently, so when all three independently agree on a side, that agreement filters out noise. That agreement plus the size of the ensemble edge is what drives the confidence tiers.

### Why I measure ATS, not prediction error

Being off by 3 points on the margin does not matter if I got the side right. A model can have mediocre point-accuracy and still be profitable as long as it lands on the correct side of the spread often enough. So every result is reported as ATS hit-rate against the 52.4% bar, not as mean error.

### Why walk-forward validation and a live holdout

You cannot use 2024 games to predict 2023, that is leakage. So validation trains on everything up to year N and tests on year N, stepping forward through 2020 to 2025 (6 folds). That mimics how the model would actually have been used week to week. On top of that, the production models train through 2024 and **2025 is held out as a true live test**, the only data the model has genuinely never seen. That holdout is the honest read on whether the edge is real.

One caveat I am upfront about: the cross-validation win rate (around 57%) is an *optimistic* number, because the hyperparameters and the feature set were chosen by looking at those same folds. That is not data leakage (nothing trains on the test set), it is selection bias from tuning, and it inflates the point estimate a little. The unbiased read is the forward live tracking, not the backtest. A research-only nested re-tune (tuning inside each fold on prior seasons only) put a number on it: the headline drops from about 57.2% to about 56.4%, roughly 0.9 points of optimism, with the edge still well clear of the 52.4% break-even.

### Why so many experiments got rejected

Through 2026 I ran a long list of "make it better" experiments: weather features, re-weighting the ensemble, an ULTRA confidence tier, time-decay sample weighting, extending training data back to 2009. Almost all were rejected against a strict bar (the primary model has to improve at least 0.5pp, most models have to improve, and stability cannot get meaningfully worse).

Two things came out of that:

1. **The spread model is near its ceiling, around 57% on cross-validation.** Adding data or down-weighting old data does not move the mean and tends to hurt stability. Once the cleanest version of an experiment still fails the bar, re-running it is wasted effort.
2. **The real gains are in execution, not the model.** Tracking closing line value, shopping lines across books, sizing bets by edge, and opening new markets (totals, props) matter more than squeezing another fraction of a percent out of the spread model.

One rule I hold to: when a backtest and the live data disagree, the live data wins for production decisions. The ULTRA tier looked great in backtest, fired about twice in seven live weeks, and got cut.

---

## What's Inside

### ATS Prediction Model

A three-voter ensemble trained on 4,300+ NFL games across 15+ seasons.

- **Ensemble fixed75** is the primary model. 75% XGBoost + 25% Ridge, trained 2014 through 2024. It sets the edge and ranks the games.
- **XGBoost, Ridge, LightGBM** are three independent direction voters. When all three agree on a side and the ensemble edge is at least 3 points the tier is **HIGH**. At least 1 point is **MEDIUM**. Otherwise it is **PASS**. Agreement alone is not enough (the edge still has to be meaningful), and a big edge alone is not enough (the voters still have to agree).
- **35 production features** selected from 85 engineered. I trimmed the set via a walk-forward ablation, which improved XGBoost cross-validation ATS by about 1.6pp.
- **Tuned hyperparameters**: Ridge alpha 50, XGBoost reg_alpha 2 and reg_lambda 5, confirmed stable across 3 seeds.

Walk-forward CV (6 folds, test years 2020 through 2025, 35-feature subset, tuned hyperparameters):

| Model | Mean ATS | Std | Notes |
|-------|----------|-----|-------|
| Random Forest | 57.1% | 2.9% | Highest mean but highest variance, so not in production. |
| XGBoost (cv) | 56.9% | 1.9% | Best on a risk-adjusted basis. Direction voter. |
| LightGBM | 56.5% | 1.7% | Most consistent. Direction voter. |
| Ridge | 55.6% | 2.0% | Direction voter plus the linear half of the ensemble. |

![Walk-forward CV results across 5 models, 2020 through 2025](betting/images/model_cv_results.png)

![Head-to-head model comparison on the 2023 through 2025 test set](betting/images/model_comparison_results.png)

The most important features by combined XGBoost gain, Ridge coefficient, and LightGBM gain:

![Feature importance ranking across all three voter models](betting/images/model_comparison_importance.png)

### Over/Under (Totals) Model (Experimental)

A separate two-model system predicting whether the combined final score goes over or under the Vegas total. It is flagged experimental on the dashboard because the cross-validation result looks real but the live 2025 sample has not confirmed it yet.

The thesis is a known market quirk: recreational bettors love betting the OVER (everyone wants a shootout), so books shade total lines slightly high. That leaves a systematic edge on the UNDER side. The model is built to find it.

- **XGBoost + Ridge** trained on the same 2014 through 2024 data, predicting the residual from Vegas (`actual_total - vegas_line`) rather than the raw total. They only have to learn small adjustments on top of an already well-calibrated number.
- **49 features**: the 35 spread features plus 14 totals-specific ones (the Vegas total, implied team totals, weather including wind which suppresses scoring, dome flag, rolling points scored and allowed, league scoring environment, pace, and a division-game flag). Wind does nothing for spreads but matters for totals, which is exactly why the two models keep separate feature sets.
- **UNDER only.** A game gets an UNDER pick only when both XGBoost and Ridge agree the score comes in low. OVER picks showed no edge (50.8% in CV, below break-even), which is what the retail-bias thesis predicts.

Walk-forward CV (6 folds, 2020 through 2025, 49 features):

| Strategy | Hit rate | Picks per season | Notes |
|---|---|---|---|
| Always UNDER (naive baseline) | 51.2% | every game | Free, just the market bias |
| **Consensus UNDER (XGB + Ridge agree)** | **55.7%** | **~96** | 95% CI 51.6 to 59.7% |
| Consensus OVER | 50.8% | ~100 | Below break-even, not bet |

Live test (2025 weeks 10 through 17, 46 picks): **52.2%**, essentially at break-even. The sample is too small to separate a real 55.7% edge from no edge at all (the confidence interval spans both). That is why the dashboard tags these picks experimental: track, do not bet. A full live season of about 96 picks will be enough to either promote the model or pull it.

### Fantasy Football Projections

Half-PPR points for QB, RB, WR, and TE the night before each slate, plus per-stat prop projections for passing, rushing, and receiving yards and receptions. Three notebooks run in order.

| Notebook | Role |
|----------|------|
| `data_pipeline.ipynb` | Pulls and joins player stats, expected points, schedules, injuries, and depth charts from nflreadpy into `raw_dataset.csv` (about 35k rows by 84 columns) |
| `features.ipynb` | Builds rolling 3 and 5 week averages and their trend, points allowed to each position for matchup difficulty, opponent strength of schedule, coach win percentage, Vegas implied team total, weather, and depth-chart availability into `features_dataset.csv` (about 40k rows by 97 columns) |
| `model.ipynb` | Trains per-position XGBoost regressors on next week's score, saves to `models/{position}_model.pkl` |
| `predict_fantasy.ipynb` | Weekly inference. Loads the models, pulls the upcoming week, writes `fantasy_projections/projections_{season}_week{n}.csv` |

Same leakage discipline as the betting side: every rolling window uses `shift(1).rolling(N)` so a player's current-week stats never leak into their current-week prediction.

**2025 holdout results** (against a 3-week rolling-average baseline):

| Position | Train rows | Test rows | MAE | RMSE | Baseline MAE |
|----------|-----------|-----------|-----|------|--------------|
| QB | 2,781 | 571 | **6.81** | 8.43 | 7.49 |
| RB | 6,652 | 1,397 | **4.40** | 6.36 | 4.59 |
| WR | 10,643 | 2,215 | **3.96** | 5.28 | 4.06 |
| TE | 5,265 | 1,145 | **3.16** | 4.55 | 3.48 |

Beats the rolling-average baseline at every position. TE has the lowest error because TE scoring is the most concentrated and predictable week to week.

**Per-stat prop models** are 8 separate XGBoost regressors (QB pass and rush yards, RB rush and rec yards, WR receptions and rec yards, TE receptions and rec yards). Each uses the same features as its position model but a different target. The values are independent, so they will not sum exactly to the main projected points. They exist as a reference for prop bets, where the question is whether the projected stat clears the sportsbook line.

The canonical retrain path is `fantasy/retrain_models.py`, which trains all 12 models in one consistent run. 2025 is currently the holdout, which keeps a clean out-of-sample season to improve against.

### DFS Lineup Optimizer

An integer-linear-program optimizer for DraftKings NFL Classic, using the weekly fantasy projections as the value signal. It fuzzy-matches DraftKings salary CSVs to player names and solves a salary-capped roster as a binary integer program.

- Constraints: 1 QB, 2 or more RB, 3 or more WR, 1 or more TE, 1 DST, 9 total, 50k cap, max 8 from one team
- The FLEX slot is filled implicitly by the solver
- Export is a proper DraftKings Classic upload (one column per roster slot)

### LLM Agent

A LlamaIndex ReActAgent with 5 tools (predictions, live injuries, line movement, head-to-head history, confidence analysis). The model gives a number, the agent gives the narrative: it reasons through each game and flags when sharp money or an injury cuts against the model's pick. It is not there to override the model, it is the qualitative sanity check a raw number cannot give you. Output is cached per week and shown as confidence overlays in the dashboard.

### Dashboard

A Streamlit app with tabs for Weekly Predictions, Track Record, Weekly Fantasy, DFS Optimizer, a pre-season Draft Value Finder, League History, and a Help guide.

- **Draft Value Finder**: our own season projection ranked against the market's ADP to flag who the draft room is mispricing. It leads with a **🔥 Consensus values** box, the players our model and Sleeper both rank above their ADP, which is the strongest signal (about 78% have beaten their draft cost). BUY means we rank a player above their ADP and FADE means below, and we only show fades when there's a real decline reason. On our confident calls alone it beats the casual ADP line about 68% of the time, season to season. It does not beat the sharpest public projections, so Sleeper sits next to our ranks purely for comparison. Treat it as an honest draft day second opinion, not a market beating edge. For a finished season it shows where each player actually landed and whether the call hit, and anyone who lost a big chunk of the year to injury just shows 🏥 instead of a hit or miss, since injuries are not something the model can predict.

- **Weekly Predictions**: game cards with edge, confidence tier, and expandable agent reasoning. Games where the experimental totals model says UNDER show a dashed amber badge below the spread card.
- **Track Record**: ATS record by tier and week, profit at standard odds, longest streaks, and a separate over/under section flagged as tracking-only.
- **Weekly Fantasy**: per-position projections with both projected and actual stat columns that fill in after games are played.

### Automation

Two GitHub Actions workflows.

**`weekly_predictions.yml`** runs on three schedules and auto-commits the updated trackers:

| Time | Action |
|------|--------|
| Tuesday 9am ET | Previous week graded, new week predicted (spread, totals, and the LLM agent) |
| Thursday 9pm ET | Predictions refreshed with injury reports |
| Sunday 9am ET | Final predictions locked |

The agent only runs on Tuesday (it costs API calls) and is allowed to fail without blocking the tracker commit.

**`test.yml`** runs on every push and PR to `main`: a `features` job runs the `features.py` contract tests (including an order-hash check that catches feature-list changes which would silently alter the trained models) and a `pytests` job runs the seasonal + dashboard suites. Catches regressions in seconds instead of on the next cron.

The only manual step each season is updating the All-Pro CSV in January.

---

## Results (2025 Season, Weeks 10 through 17, 117 graded games)

| Tier | Games | Correct | Win % |
|------|-------|---------|-------|
| **HIGH** (all 3 voters agree, ensemble edge 3pt or more) | 17 | 11 | **64.7%** |
| **MEDIUM** (all 3 voters agree, ensemble edge 1pt or more) | 42 | 25 | **59.5%** |
| PASS | 58 | 30 | 51.7% |
| **Overall (Ensemble)** | **117** | **66** | **56.4%** |

Best week: 9 of 14 (Week 14, 64.3%). These are encouraging but it is a small live sample, and there will be bad weeks. The point is to track this honestly over multiple seasons and see if the edge holds.

---

## Stack

| Component | Tech |
|-----------|------|
| ATS and totals models | XGBoost, LightGBM, Scikit-learn (Ridge, Ensemble) |
| Fantasy models | XGBoost (per-position plus per-stat prop models) |
| DFS optimizer | PuLP (integer linear program), fuzzy name matching |
| Feature engineering | nflreadpy, pandas, NumPy |
| LLM agent | LlamaIndex, Anthropic Claude API |
| Dashboard | Streamlit |
| Automation | GitHub Actions (papermill) |
| Data | nflreadpy, custom All-Pro CSV, Meteostat weather |

---

## Repo Structure

```
app.py                                 # Streamlit dashboard (entry point)
dashboard_utils.py                     # Streamlit-free dashboard helpers (testable; metric_card, loaders, etc.)
test_dashboard_utils.py                # Unit tests for dashboard_utils.py (run in CI)
betting/
  features.py                          # Shared 85-feature engineering (single source of truth, importable)
  test_features.py                     # Hermetic synthetic-data tests for features.py (run in CI)
  features.ipynb                       # Thin documentation notebook (design rationale; imports features.py)
  predict_betting.ipynb                # Weekly ATS prediction pipeline (papermill; imports features.py)
  predict_totals.ipynb                 # Weekly over/under pipeline (imports features.py + totals_features)
  totals_features.ipynb                # 14 totals-specific features (single source of truth)
  totals_model.ipynb                   # Totals walk-forward CV + production retrain
  model_comparison.ipynb               # Spread model architecture comparison + walk-forward CV
  sports_betting_agent.ipynb           # LLM agent (weekly qualitative analysis)
  models/
    ensemble_prod_model.pkl            # Primary spread model: Ensemble fixed75
    xgboost_prod_model.pkl             # XGBoost direction voter
    lgbm_prod_model.pkl                # LightGBM direction voter
    totals_xgboost.pkl, totals_ridge.pkl  # Totals model
  predictions_tracker.csv              # Spread predictions and results (auto-committed)
  totals_tracker.csv                   # Totals predictions and results (auto-committed)
  nfl_allpro_1997_2025.csv             # All-Pro roster data (updated manually each January)
  nfl_weather_2014_2025.csv            # Kickoff-hour temp and wind (Meteostat)
  agent_analysis_2025_week{n}.json     # Cached agent output per week
  experiments/                         # Reusable analysis scripts and result snapshots
  archive/                             # Retired notebooks and model files
fantasy/
  data_pipeline.ipynb                  # Pull and join player stats from nflreadpy
  features.ipynb                       # Feature engineering, writes features_dataset.csv
  model.ipynb                          # Train per-position and per-stat models
  retrain_models.py                    # Canonical retrain of all 12 fantasy models
  predict_fantasy.ipynb                # Weekly half-PPR projections (papermill)
  models/                              # Per-position and per-stat XGBoost pkl files
  fantasy_projections/                 # Weekly projection CSVs
  dfs/
    optimizer.ipynb                    # ILP formulation and helper reference
    dfs_pipeline.ipynb                 # Weekly DFS workflow (papermill)
  seasonal_projections/                # Pre-season Draft Value Finder tab + value-edge research
    train_model_a.py                   # Per-position season PPG models (LightGBM, injury features removed)
    build_value_board.py               # Builds the live tab data: our calls vs ADP (+ Sleeper comparison)
    surprise_eval.py                   # Canonical eval: ADP-mispricing skill (can we spot over/undervalued players, injury-filtered)
    model_bakeoff.py                   # Algorithm + hyperparameter bakeoff on the projection (LightGBM wins)
    fade_deep_dive.py                  # Why fades struggle + the decline-catalyst gate that fixes them
    build_draft_board.py               # Older three-way blend board (retained for reference)
    README.md                          # Design decisions, results, and the honest verdict
memory/                                # Persistent notes for future work
.github/workflows/
  weekly_predictions.yml               # Tue/Thu/Sun automation (spread, totals, agent)
  test.yml                             # Push/PR CI: features.py contract tests + seasonal/dashboard suites
```

---

## What's Next

The spread model is at the ceiling of what this architecture delivers, confirmed by a long run of rejected experiments (the full log is in `CLAUDE.md`). The gains from here are in execution and in opening new markets, not in more spread-model tuning.

1. **Closing Line Value tracking.** The leading indicator of long-term profit, more predictive than win rate over short samples. The tracker already has empty columns reserved for it. The plan is to record the line at pick time and again near kickoff once the 2026 season starts.
2. **Multi-book line shopping.** The same pick at one book's price versus another's is a couple percent of implied edge per bet, which compounds across a season more than model tuning would.
3. **Kelly fractional sizing.** Real fractional Kelly sizing by edge magnitude, surfaced once it's validated (an earlier flat-tier unit chip was removed as premature).
4. **Player props model.** A lower-efficiency market with higher edge potential. The per-stat fantasy models already exist, so the leap to "is the prop line over or under our projection" is small.

DFS follow-ups (lower priority, already functional):

5. **DST projection model** to replace the season-average fallback.
6. **Multi-lineup GPP generator** with ownership-diversity constraints.
7. **Game-stacking constraints** to co-select correlated players in high-total games.
8. **Automated salary fetching** to replace the manual DraftKings CSV download.
9. **End-to-end automation** chaining the fantasy and DFS pipelines in GitHub Actions.

---

*Not financial advice. Sports betting involves real risk. Bet responsibly.*
