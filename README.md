# JoSchoAnalytics: NFL Prediction System

Live dashboard: [joschoanalytics.streamlit.app](https://joschoanalytics.streamlit.app) - May need to be woken up

---

## What This Is

I built this to find out if a data-driven model can actually find an edge against the spread. Anyone can pick winners. The harder question is whether you can consistently beat the number Vegas sets.

> ### ⚠️ RETRACTED 2026-08-03 — the 64.2% ATS edge does not survive a leak fix
>
> I previously published: *"HIGH-confidence picks hit 64.2% against the opening spread,
> 380 of 592 games, 2018–2025, 95% Wilson lower bound 60.2%."* **That number was produced
> through a leaking feature and I am withdrawing it.**
>
> **The defect.** The sack history was built only from sack-positive game/team rows, so a
> defense that recorded zero sacks in a game had *no row at all*. Row presence therefore
> encoded that game's own outcome, and a downstream `fillna(0)` wrote 0 onto exactly those
> rows — contemporaneous information inside a pregame feature. `sack_diff` and
> `sack_diff_reverse` are the #2 and #3 of the 35 features the model trains on.
>
> **The regenerated numbers** (walk-forward out-of-sample, 2018–2025, 2,138 predictions,
> pushes excluded via `won_open.notna()`, tiers over games with |edge| ≥ 1):
>
> All numbers below come from ONE declared pinned environment
> (`requirements-backtest.txt`, pandas 2.3.3, Python 3.11.9). Full provenance and the
> controlled 2×2:
> [`betting/experiments/audit_2026-08-03c_final/PROVENANCE.md`](betting/experiments/audit_2026-08-03c_final/PROVENANCE.md).
>
> Two defects were found, and they are separated rather than conflated. **(1)** the sack
> leak above; **(2)** an All-Pro **identity collision** — the roster file has no player ID
> and two distinct players named C.J. Mosley were merged under a name key, with the
> survivor decided by an unstable sort.
>
> | Arm | sack | identity | HIGH | win% | 95% Wilson lower | Clears 52.4%? |
> |---|---|---|---|---|---|---|
> | A | leaking | legacy | 380/592 | 64.1892% | 60.2469% | yes |
> | B | dense | legacy | 133/240 | 55.4167% | 49.0918% | no |
> | C | leaking | fixed | 378/589 | 64.1766% | 60.2239% | yes |
> | **D (published)** | **dense** | **fixed** | **129/238** | **54.2017%** | **47.8551%** | **no** |
>
> Arm A reproduces the originally published figure **exactly**, which licenses the causal
> claim: the collapse is the leak, not drift. The sack repair is the dominant effect (mean
> margin change 1.77 pts, HIGH 592→240); the identity repair is small but real (mean 0.09,
> HIGH 240→238). Arm D was run twice and is byte-identical.
>
> **Published: HIGH 129/238 = 54.2017%, Wilson lower 47.8551% — below break-even.**
> MEDIUM 382/718 = 53.2033%, lower 49.5462% — also below. **No tier clears break-even.**
>
> **What I now claim: nothing.** 54.2% on 238 picks is a point estimate whose 95% interval
> contains break-even. This system has **no demonstrated ATS edge**; the 2026 forward
> record is the first real test.
>
> Reproduce (the pinned env is required — `requirements-ci.txt` alone lacks openpyxl):
> ```
> python -m venv C:/tmp/jsa-bt
> C:/tmp/jsa-bt/Scripts/python.exe -m pip install -r requirements-backtest.txt
> C:/tmp/jsa-bt/Scripts/python.exe betting/experiments/walkforward_oos_preds.py --line open --out <path>.csv
> cd betting && C:/tmp/jsa-bt/Scripts/python.exe kelly_staking.py --preds <path>.csv
> ```
> Fix: `betting/features.py::_build_situational_pbp` + `model_comparison.ipynb` §7 build a
> dense sack table. Guard: `betting/test_sack_leak.py` mutates the target game's sack count
> and asserts every pregame feature is unchanged, with a red proof that the pre-fix builder
> fails that test.

The model does **not** beat the closing line, and I do not claim it does — an earlier "beats the close" reading turned out to be an artifact of the closing line being one of the model's own inputs.

The 2025 live sample (weeks 10 through 17, 117 graded games) reads 56.4% overall, HIGH 64.7% and MEDIUM 59.5% — but HIGH is only 11 of 17 graded picks there, far too few to separate from luck. Cite the walk-forward figure, not that one.

The repo is the full system: ATS predictions, an experimental over/under model, weekly fantasy projections, a DFS lineup optimizer, an LLM agent that explains the model's read on each game, and a pre-season Draft Board and Rookie Board built on from-scratch season projections and descriptive talent scores.

---

## Guides

Each subsystem has a plain-language guide — what it is trying to do, how it works end to end, the key files, and the honest results:

- [betting/GUIDE.md](betting/GUIDE.md) — the ATS spread model, the experimental totals model, and the LLM agent.
- [fantasy/GUIDE.md](fantasy/GUIDE.md) — the weekly fantasy projection system (per-position and per-stat models).
- [fantasy/projections/GUIDE.md](fantasy/projections/GUIDE.md) — the from-scratch 2026 season-total half-PPR projections (RB, WR, TE and veteran QB) behind the Draft Board's Model Proj column.
- [fantasy/seasonal_projections/GUIDE.md](fantasy/seasonal_projections/GUIDE.md) — the closed value-signal research campaign behind the pre-season board (the band it validated was retired from the page on 2026-07-22).
- [fantasy/talent/GUIDE.md](fantasy/talent/GUIDE.md) — the NFL Talent Score and College Talent Score columns: the eight per-position builds behind them, what they measure, and where they fail (no strength-of-schedule adjustment; FBS only on the college side).
- [fantasy/rookie/GUIDE.md](fantasy/rookie/GUIDE.md) — the Rookie Board's hit-probability score.
- [fantasy/dfs/GUIDE.md](fantasy/dfs/GUIDE.md) — the DraftKings lineup optimizer.

`fantasy/breakout/` is a one-off research notebook (a breakout-probability experiment with saved charts); it is not wired into the dashboard or any pipeline, so it has no guide.

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

Half-PPR points for QB, RB, WR, and TE the night before each slate, plus per-stat prop projections for passing, rushing, and receiving yards and receptions. Three notebooks build the models and a fourth runs weekly inference.

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

> **Corrected 2026-08-03.** The previous table was measured on a `features_dataset.csv` whose 2025 season had **16 of 16 depth/availability columns constant** — nflverse changed the depth-chart schema and the legacy filter silently dropped 100% of 2025, so defaults filled in. Rebuilt via `fantasy/depth_adapter.py`; 0 of 16 constant now. Holdout n falls because per-season rolling windows drop each player's week-1 row (3,072 of 3,185 removed rows; 0 unexplained). **Every MAE got slightly worse — the corrupted data made the holdout easier — and the "all four beat the baseline" claim does NOT survive: only QB and TE are statistically distinguishable from the rolling average.** Provenance: `fantasy/staging/manifest_primary.json`, `gate_report.json`.

| Position | Holdout n | MAE | RMSE | Rolling baseline MAE | Paired gain vs baseline | t |
|---|---|---|---|---|---|---|
| QB | 508 | **6.859** | 8.502 | 7.378 | +0.519 | **3.13** |
| RB | 1,284 | **4.489** | 6.331 | 4.578 | +0.089 | 1.15 |
| WR | 2,030 | **4.015** | 5.293 | 4.027 | +0.012 | 0.23 |
| TE | 1,022 | **3.200** | 4.646 | 3.485 | +0.284 | **4.16** |

**Read plainly: QB and TE beat the rolling-average baseline; RB (t=1.15) and WR (t=0.23) do
not.** WR is essentially indistinguishable from just averaging a player's last three games.


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

A Streamlit multipage site with a top nav in three groups — **Betting**: Weekly Predictions, Track Record · **Fantasy**: Draft Board, Rookie Board, Weekly Fantasy, DFS Optimizer · **More**: Film Room, League History, Help & Guide.

- **Draft Board**: my pre-season board for QB, RB, WR, and TE — every player with a 2026 Sleeper ADP, 245 of them. For each it puts the market's draft price and positional rank next to two independent season-total half-PPR projections — Sleeper's and a from-scratch model I built — with the positional-rank gap for each, plus two descriptive talent columns (NFL Talent Score, College Talent Score). Thirteen columns; a "Show projection and talent detail" toggle (on by default) drops the four raw-estimate and talent columns for a compact nine-column comparison, and the CSV download always contains all thirteen. My model is backtested on 2021–2025 and **not** live-validated — the first live test is the 2026 season — and it does not beat Sleeper on ranking. Selected named 2026 players carry a disclosed analyst scenario in place of the model's point estimate; the raw model output is preserved unchanged underneath. The gaps are neutral rank differences shown for context, not calls about any player. (This replaced the Phase-4 band spine on 2026-07-22, which had itself replaced the retired Draft Value Finder tab on 2026-07-12; see `fantasy/projections/GUIDE.md` for the projection engine and `fantasy/seasonal_projections/GUIDE.md` for the closed band campaign.)

- **Rookie Board**: a per-position hit-probability score for drafted rookies, beside the rookie season-total projections (RB, WR and TE — the QB rookie arm was built and held as too thin), a College Talent score, and college/athletic percentiles. Backtested, not live-validated: at this sample college production and athletic testing added no measured edge beyond draft capital.

- **Weekly Predictions**: game cards with edge, confidence tier, and expandable agent reasoning. Games where the experimental totals model says UNDER show a dashed amber badge below the spread card.
- **Track Record**: ATS record by tier and week, profit at standard odds, longest streaks, and a separate over/under section flagged as tracking-only.
- **Weekly Fantasy**: per-position projections with both projected and actual stat columns that fill in after games are played.

- **Film Room**: embedded TikToks from the [@joschoanalytics](https://www.tiktok.com/@joschoanalytics) channel (the analytics content arm), each paired with a click-to-open written breakdown that digs into the data the short couldn't fit. The channel intro is featured at the top; player and matchup breakdowns land here as they're posted. Add one by appending to `video_content.py` and dropping a markdown file in `video_breakdowns/`.

### Automation

Two GitHub Actions workflows.

**`weekly_predictions.yml`** runs on three schedules and auto-commits the updated trackers:

| Time | Action |
|------|--------|
| Tuesday 9am ET | Previous week graded, new week predicted (spread, totals, and the LLM agent) |
| Thursday 9pm ET | Predictions refreshed with injury reports |
| Sunday 9am ET | Final predictions locked |

The agent only runs on Tuesday (it costs API calls) and is allowed to fail without blocking the tracker commit.

**`test.yml`** runs on every push and PR to `main`, in three jobs: a `features` job runs the `features.py` contract tests (including an order-hash check that catches feature-list changes which would silently alter the trained models) plus the calibration tests; a `pytests` job runs the seasonal, dashboard and talent suites plus the betting execution layer; and a `deploy-parity` job re-runs everything on Python 3.12 against the exact package set Streamlit Cloud installs, so a resolver conflict fails here instead of on the live site. Catches regressions in seconds instead of on the next cron.

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
app.py                                 # Multipage entry point (st.navigation, 9 pages, top nav)
site_pages/                            # One module per page (draft_board, rookie_board, weekly_predictions,
  page_*.py                            #   weekly_fantasy, dfs, track_record, film_room, league_history, help)
  page_common.py                       # Shared page scaffolding
tests/                                 # Dashboard + board suites; conftest.py puts the repo root on sys.path
nav_registry.py                        # Cross-link registry, populated before nav.run()
dashboard_chrome.py / dashboard_data.py   # Shared chrome and data loaders
dashboard_utils.py                     # Streamlit-free dashboard helpers (testable; metric_card, loaders, etc.)
draft_board_2026.py                    # Draft Board renderer (license-frozen copy; reads season_dataset ADP +
                                       #   fantasy/projections/results + fantasy/talent scores)
film_room.py                           # Film Room renderer (embedded TikToks + breakdown popups)
video_content.py                       # Registry of published videos (embed ids + breakdown files)
video_breakdowns/                      # Long-form written breakdowns (markdown), one per video
docs/                                  # Long-form specs kept out of the root
archive/                               # Retired material, on no live path (closed code review, design audits)
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
  projections/                         # From-scratch season-total half-PPR builds (the Model Proj column)
    build_{rb,wr,te,qb}_projection.py  # One per position; each imports the RB engine, never modifies it
    results/                           # {pos}_projection_2026.csv, *_rookie_board_projection.csv, and
                                       #   analyst_projection_adjustments_2026.csv (45-row display overlay)
    preregs/PREREG_*.md                # Frozen pre-registrations
    GUIDE.md                           # Plain-language guide
  talent/                              # Descriptive talent scores (SPEC R34-R41, shipped 2026-07-27)
    build_nfl_{qb,rb,wr,te}_score.py   # -> nfl_{pos}_score_2026.csv    (+ .provenance.json)
    build_college_{qb,rb,wr,te}_score.py  # -> college_{pos}_score_2026.csv (+ .provenance.json)
    talent_score_2026.csv              # R29, SUPERSEDED: feeds no rendered column; hash-pinned on disk
    rookie_score_2026.csv              # Fallback only, where a college build has no coverage
    SPEC.md, GUIDE.md, tests/          # Formulas of record, plain-language guide, build tests
    preregs/PREREG_*.md                # Frozen pre-registrations for the fired talent instruments
  rookie/                              # Rookie Board hit-probability score + its frozen (spent) harness
  seasonal_projections/                # The closed value-signal research campaign
    phase4_band_2026.csv               # FROZEN, RETIRED FROM THE PAGE (2026-07-22): kept for the closed
                                       #   campaign and as a fixed input to the daily ADP refresh
    talent_index_2026.csv              # FROZEN, RETIRED: superseded by fantasy/talent/ per-position builds
    refresh_board_adp.py               # Daily Sleeper ADP refresh -> board_adp_live_2026.csv (245 rows)
    phase4_band.py                     # Band engine (walk-forward isotonic + residual quantiles)
    apply_board_labels.py              # Post-process: population flags + licensed signal_status wording
    build_talent_index.py              # Regenerates talent_index_2026.csv (descriptive only, never blended)
    PREREGISTRATION.md                 # The campaign constitution (blind decision rules, OUTCOMES ledger)
    h6/h7/h8v/h11/h12_*.py, *_results.json  # Fired pre-registered tests + their frozen results
    build_value_board.py               # RETIRED engine for the old Draft Value Finder (kept for history)
    ARTIFACTS.md                       # Every file in this dir: frozen / regenerable / retired
    GUIDE.md                           # Plain-language guide to the board and the campaign
    README.md                          # Design decisions, results, and the honest verdict
memory/                                # Repo-specific engineering notes, the dated changelog
                                       #   (completed-work-log.md), and dated session logs
.github/workflows/
  weekly_predictions.yml               # Tue/Thu/Sun automation (spread, totals, agent)
  test.yml                             # Push/PR CI: features + calibration; seasonal/dashboard/talent +
                                       #   betting execution layer; deploy-parity on py3.12
  board_refresh.yml                    # Daily Sleeper ADP refresh for the Draft Board
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

## License

The code in this repository is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE): you're free to read it, learn from it, and use it for any **noncommercial** purpose. Using it commercially (including running it as a paid product or service) requires a separate license. Copyright © 2026 Joseph Schoenbaum.

---

*Not financial advice. Sports betting involves real risk. Bet responsibly.*
