# PRE-REGISTRATION — RB SEASON-TOTAL PROJECTION (2026-07-21)

**STATUS: DESIGN LOCKED, NOTHING FIT.** Light PRODUCT prereg — no one-shot fire, no accept/reject
claim, no ship gate. Its job is to PIN every choice that could otherwise be shopped (features, models,
grids, target, routing, validation) BEFORE any real model is fit or any accuracy/Sleeper number is
computed. Sleeper is the market baseline and is **shown, not gated** (§9). Blindness note: §11.

**AUTHOR / PROVENANCE.** Designed by the intermediary from a read-only recon (2026-07-21); Joseph
reviews and commits this file to lock the design. Missing-data rule (§5) is Joseph's to confirm.

---

## 0. WHAT THIS IS / SCOPE

A from-scratch **RB season-total half-PPR projection for 2026**, built as **two models sharing one
target** and merged into one projection column, shown on the board **beside Sleeper's projection**
(permanent) plus a difference column. RB-only this build; WR/TE/QB are later, separate builds under
their own prereg. Once built and approved in a LATER session it replaces the current starved
`rookie_ppg` surface (which is draft+combine+landing only, no college signal, and per-game not total).

The two models:
- **VETERAN model** — for players with ≥1 prior NFL season (prior production exists).
- **ROOKIE model** — for players with no prior NFL season (college + draft + landing-spot only).

Both regress the SAME target (§1) and their outputs are concatenated into one projection column (a
player is scored by exactly one model per §2).

---

## 1. TARGET DEFINITION

- **Target = observed season-total half-PPR points**, per player per NFL season (the row = one
  `(player, season)`). Half-PPR = `fantasy_points + 0.5·receptions` (repo formula), **summed over the
  regular season**, computed directly from weekly stats — **not** `target_ppg × games` (that column
  filters games ≥ 11 and would drop partial seasons).
- **Partial seasons / injuries fold INTO the target, not out of it.** A player who plays 6 games and
  scores 55 total is a 55 data point; a player who was rostered but never played is 0. The model
  therefore projects EXPECTED season total (rate × availability jointly) — which is what a fantasy
  manager drafts on. Injuries are not filtered and not separately modeled (beyond the prior-injury
  feature in §3). This is disclosed: high-variance, injury-driven seasons are inherent noise in this
  target.
- **Training universe = the RB rows of `season_dataset_2014_2026.csv`** (the drafted / prior-relevant
  pool; ~120 veteran + ~30 rookie RB per season). Target computed for every row; deep-roster 0s are
  kept (they are real outcomes).

---

## 2. THE TWO MODELS + ROUTING RULE

**Routing is by the `is_rookie` flag, pinned and exhaustive:**
- `is_rookie == 1` (no prior NFL season) → **ROOKIE model**.
- `is_rookie == 0` (≥1 prior NFL season) → **VETERAN model**.

Every RB row routes to **exactly one** model; the two partitions are mutually exclusive and cover the
universe. (Harness asserts this — §STOP-3.) No player is scored by both; no player is unscored. The
final projection column = the concatenation of the two models' outputs.

---

## 3. FEATURE SET — PINNED, BY BUCKET, PER MODEL (the anti-shopping core)

All features below are the FROZEN candidate pool. Feature SELECTION within this pool (if any) happens
only inside inner CV (§7); the pool itself is fixed here and not expanded after seeing any result.

### VETERAN model (all from `season_dataset`, all prior-season / point-in-time)
- **Prior production:** `prior_ppg`, `prior_half_ppr`, `prior_games`, `ppg_2yr`, `ppg_3yr`,
  `ppg_trend`, `career_high_ppg`.
- **Prior usage / efficiency:** `prior_snap_share_pg`, `prior_targets_pg`, `prior_carries_pg`,
  `prior_receptions_pg`, `prior_touches_pg`, `prior_target_share`, `prior_air_yards_share`,
  `prior_adot`, `prior_td_rate`, `prior_yptarget`, `prior_ypc`, `prior_rec_epa`, `prior_rush_epa`.
- **Bio / draft:** `age`, `years_exp`, `draft_round`, `draft_pick`.
- **Availability prior:** `prior_games_missed`, `missed_prior_season`. (KEPT here — unlike the existing
  per-game Model A which dropped them — because the SEASON-TOTAL target depends on games played, and
  prior missed time is a legitimate availability prior.)
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays`, `vacated_target_share`,
  `vacated_rush_share`, `coach_changed`, `qb_changed`, **projected depth-chart position/rank
  (preseason, `load_depth_charts`, point-in-time) where available — provisional/noisier for 2026 (§6)**.
- **CONDITIONAL — prior-season talent / PFF-efficiency facets:** included ONLY if a per-season
  historical artifact exists for the training seasons. Today only `talent_score_2026.csv` (2026,
  veteran R30) and the season's EPA efficiency (`prior_rec_epa`/`prior_rush_epa`, already listed)
  exist; a historical per-season veteran talent/PFF-facet table does NOT exist. So this bucket is
  **DEFERRED** (omitted) unless such history is built in a separate session. Declared here so it is
  never quietly added mid-build.

### ROOKIE model (all knowable at draft / point-in-time)
- **Draft capital:** `draft_round`, `draft_pick`, `draft_ovr`/`log_pick`.
- **Age:** `age`.
- **Combine / athletic:** `forty`, `vertical`, `broad_jump`, `cone`, `shuttle`, `bench`, `ht_in`,
  `wt`, `bmi`, `speed_score`.
- **College production (cfbfastR):** the `cfb_*` bucket — `cfb_final_dom`, `cfb_best_dom`,
  `cfb_scrim_ypg`, `cfb_rush_ypg`, `cfb_rec_ypg`, `cfb_ypc`, `cfb_ypr`, `cfb_career_scrim_yds`,
  `cfb_career_scrim_td`, `cfb_seasons`, `cfb_breakout_class`.
- **College PFF facets (RB):** `pff_rushing_grades_run`, `pff_rushing_grades_offense`,
  `elusive_rating`, `breakaway_percent`, `elu_yco`, `avoided_tackles`, `pff_rushing_first_downs`,
  `pff_rushing_touchdowns` (+ the RB receiving facets `pff_receiving_yprr`, `pff_receiving_routes`).
  (This is the hit-model's frozen 63-col rookie matrix, RB slice — reused verbatim.)
- **CONDITIONAL — college talent score:** read-only from `rookie_score_2026.csv` (RB PBP instrument),
  2026 only. Historical per-class rookie talent scores do not exist → **DEFERRED** for training folds
  unless built; may still be shown/joined for the 2026 deploy row. Declared so it is not quietly added.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays`, `vacated_target_share`,
  `vacated_rush_share`, `coach_changed`, `qb_changed` (the DRAFTING team's context), **projected
  depth-chart position/rank (preseason, `load_depth_charts`, point-in-time) where available —
  provisional/noisier for 2026 (§6)**.
- **Team context:** as captured by the landing-spot bucket above.

The college↔NFL and combine joins reuse the FROZEN hit-model bridges (combine `pfr_id`→`gsis`;
college/PFF by `norm_name`; the placeholder-gsis seam on 2026 handled by name+position coalesce).

---

## 4. LEAKAGE GUARD (HARD RULE)

**Every feature must be knowable BEFORE the projected season Y.** No same-season feature may enter the
projection of its own season. Concretely:
- All veteran features are PRIOR-season (`prior_*`) or draft-time (bio/draft); talent scores and every
  efficiency facet use PRIOR-season data only.
- All rookie features are draft-time (draft/combine/college/age) or drafting-team landing-spot — all
  set before Y kicks off.
- The target for season Y is NEVER a feature for Y (and no leakage of Y's within-season stats).
- Prior-join convention (repo standard, `build_season_dataset.py`): `prior["season"] += 1` then merge
  on `(player_id, season)` — a player who missed a season gets NaN priors, never carried-forward stats.
- **TALENT-SCORE / EFFICIENCY-FACET LAG (explicit):** any talent-score feature (and every PFF /
  efficiency facet) is LAGGED to PRIOR-season data only — a talent-score feature used to project
  season Y must be derived from information available at or before Y−1, never Y or later. **The build
  ASSERTS this lag:** for each such column the build verifies its source season ≤ Y−1 for every row
  (e.g. `talent_score` joined for projection-season Y carries the Y−1 construction), and fails the
  build if any talent/efficiency feature is same-season or future-dated. (These buckets are DEFERRED
  per §3 until a per-season history exists; the assert is a standing requirement for when they are added.)
This is a hard rule; the harness proves the general form (peek probe must scream; shuffled-alignment
probe must destroy signal — §STOP-3), and the build adds the talent-lag assert above.

---

## 5. MISSING-DATA RULE (RULED — Joseph, 2026-07-21)

Joseph's standing OMIT-not-fabricate rule, confirmed for this build:
- **Tree models (CatBoost / LightGBM / XGBoost):** native NaN routing — a missing value stays NaN and
  the model learns an "unknown" branch. Nothing invented.
- **Regularized linear baseline (ElasticNet):** cannot accept NaN → within-position median-impute + a
  per-feature missing-indicator flag (value 0 after centering); NOT naive mean-imputation. The flag
  marks "unknown."
- No row is dropped for missingness (would gut the thin 2026 landing-spot).

---

## 6. LANDING-SPOT / 2026 DEPTH-CHART HANDLING (disclosed up front)

For the historical TEST seasons (2021–2025) landing-spot features are well-populated. For the UNPLAYED
2026 season they are the **thinnest, noisiest input** — measured this session (RB 2026):
`vacated_rush_share` 84% / `vacated_target_share` 84%, `prior_team_pass_rate` 60%, `coach_changed`
100% (22% non-zero), **`qb_changed` 100% present but ALL ZERO (undeterminable pre-season)**, ADP
pos-rank only 35% present (still filling over the summer).

Projected 2026 opportunity is sourced from three inputs, all point-in-time (knowable before the season)
and all firming through the offseason:
- (a) **Projected depth-chart position/rank** (`load_depth_charts`) — used as an actual FEATURE where
  available (a role signal: RB1 vs RB2 vs committee), not merely a firming reference. For the
  historical test folds (2021–2025) the preseason depth chart of season Y is used point-in-time.
- (b) **ADP-as-role proxy** (`adp_pos_rank` / `sleeper_adp_2020_2026`), which grows toward late August.
- (c) **Vacated-touches** from off-season departures (`vacated_rush_share` / `vacated_target_share`,
  already in the dataset).

**Pinned disclosure:** for the UNPLAYED 2026 season all three are PROVISIONAL and NOISIER than in the
historical folds — depth charts are unsettled, ADP is still filling (RB pos-rank ~35% as of this
writing), `qb_changed` is undeterminable pre-season (all zero), and the drafting-team context for
rookies is thin. 2026 projections should be RE-RUN as depth charts and ADP firm. This noise is inherent
to projecting an unplayed season and is NOT a defect to tune away.

---

## 7. MODEL SLATE + HYPERPARAMETER GRIDS — PINNED, NESTED-CV SELECTED (anti-peeking)

Candidate models (per model, veteran and rookie independently):
- **CatBoost** (regressor, RMSE/MAE loss) — depth {4,6}, learning_rate {0.03,0.06}, l2_leaf_reg {3,6},
  iterations {400,800}.
- **LightGBM** (objective mae) — num_leaves {15,31}, learning_rate {0.03,0.06}, n_estimators {400,800}.
- **XGBoost** (reg:squarederror) — max_depth {4,6}, eta {0.03,0.06}, n_estimators {400,800},
  reg_lambda {1,5}.
- **Regularized linear baseline** — ElasticNet, alpha {0.001,0.01,0.1}, l1_ratio {0.2,0.5,0.8}
  (median-impute+flag inputs).
- **Optional RandomForest** — n_estimators {400}, max_depth {None,12} (comparison only).

**ANTI-PEEKING RULE (hard):** the model family, its hyperparameters, and any within-pool feature
selection are chosen SOLELY by the INNER cross-validation score on the training seasons. The OUTER
test season is NEVER consulted for any selection decision — not model choice, not tuning, not feature
pruning. Selection metric = inner-CV MAE (primary) with RMSE reported. The whole grid above is frozen
here; it is not expanded after seeing any fold's result.

---

## 8. VALIDATION STRUCTURE — WALK-FORWARD BY SEASON

- **Outer walk-forward folds:** project each of **2021, 2022, 2023, 2024, 2025** using models trained
  ONLY on seasons ≤ Y−1 (2021 trains on 2014–2020, …, 2025 trains on 2014–2024). Deploy row = 2026
  (unplayed, no outcome — not a fold). (2021–2025 chosen because Sleeper coverage begins 2021.)
- **Inner tuning:** within each outer fold's training seasons, a nested leave-one-season-out CV selects
  the model+hyperparameters (§7). The outer test season is untouched during tuning.
- **Metrics (per fold, per model, pooled):** MAE, RMSE, and Spearman rank-correlation of projection vs
  actual season-total. Reported per position-model and merged. These are the model's own report card —
  they do NOT gate the ship (§10).
- Leakage: train strictly on prior seasons; the harness asserts no fold trains on its own test season.

---

## 9. SLEEPER COMPARISON — SHOWN, NOT GATED

- On the board, **permanently and unconditionally**: the merged **projection** column, the **Sleeper**
  column (`sleeper_pts_half_ppr`, season-total, joinable 2021–2026), and a **difference** column
  (`projection − Sleeper`).
- An OPTIONAL accuracy-vs-Sleeper check on the past seasons where outcomes are known (2021–2025) —
  MAE/RMSE/rank of projection vs Sleeper vs actual — is **computed and stored for interest only. It
  GATES NOTHING and is NOT a success criterion.** "Beating Sleeper" is explicitly **not** a ship
  requirement; no future session may treat it as one. (Doctrine: Sleeper is the market, shown for the
  user's context, not a bar our model must clear to ship — cf. the closed seasonal H4/H6 campaign,
  where beating ADP was hard and the honest product shipped regardless.)

---

## 10. WHAT SHIPS REGARDLESS

The **merged projection column** (veteran + rookie), the **Sleeper column**, and the **difference
column** — replacing the current `rookie_ppg` projection surface — once built and approved in a later
session. It ships with honest labels (a season-total projection; the 2026 landing-spot caveat of §6;
"projection, not a guarantee"). No accuracy claim beyond the walk-forward report is made; Sleeper is
context, not a scoreboard we must win.

---

## 11. BLINDNESS NOTE

This prereg is written BEFORE any final model is fit and BEFORE any real accuracy or Sleeper-comparison
number is computed. The recon this session touched only data STRUCTURE (row counts, coverage rates,
column names, Sleeper units, sample sizes) — never a feature-vs-target relationship, never a fitted
metric. The feature pool, model slate, grids, folds, and metrics above are frozen here so that the
build session cannot shop them against the outcome.

---

## 12. FENCES / WHAT THIS SESSION DID (AND DID NOT) DO

- Wrote this prereg + a synthetic-only harness proof (`rb_projection_harness.py`). Fit NO real model;
  computed NO real accuracy; ran NO Sleeper comparison; committed NOTHING.
- Did NOT touch `talent_score_2026.csv` / `rookie_score_2026.csv` / `fantasy/talent/` (read-only if at
  all), the frozen hit-model harness, or the deployed rookie board.
- Reuses the FROZEN hit-model feature bridges and the `season_dataset` verbatim; builds no new data
  artifact into the repo this session.
- The build session (next) fits the pinned models under this prereg, joins Sleeper, runs the
  walk-forward, and builds the board column — nothing here may be re-shopped there.

---

## AMENDMENT 1 (2026-07-21, build session) — `depth_rank` DROPPED (data-validity; STRICTLY NARROWS the pool)

**Hardness assertion:** this amendment only REMOVES a feature from the frozen §3 pool. It adds no
feature, relaxes no gate (there is no gate — this is a product prereg), and cannot be used to fish for
a Sleeper win. It makes the design strictly more honest.

**What changed.** The pinned "projected depth-chart position/rank (preseason, `load_depth_charts`,
point-in-time)" feature (listed in §3 for BOTH the veteran and rookie buckets, and as §6(a)) is
**removed from both feature pools.** No other feature, model, grid, fold, or metric changes.

**Why (measured, not shopped).** `nflreadpy.load_depth_charts` has **zero rows for 2025 and 2026** —
the source table ends at 2024. So `depth_rank` is well-populated in veteran TRAINING (82–84% for
2014–2024) but **entirely absent at inference for the 2025 fold and the 2026 deploy**. That
train-present / deploy-absent asymmetry breaks the native-NaN tree models: an all-NaN-at-inference
column routes every 2025 veteran down LightGBM's learned NaN-default branch, collapsing the 2025
veteran fold (MAE 65.4 / ρ +0.322, Bijan Robinson predicted 4 vs actual 331) and flipping the 2026
veteran deploy selection to ElasticNet. Confirmed by an ablation on the 2025 veteran fold (fixed
LightGBM): WITH depth MAE 74.0 / ρ +0.271; WITHOUT depth MAE 40.1 / ρ +0.758 — the latter in line
with the healthy 2021–2024 folds. This is a data-availability defect for the deploy target, not a
metric shopped after the fact; §3 already pinned the feature "where available," and it is not
available for the seasons that ship. `depth_rank` is still COMPUTED for coverage/disclosure and may be
shown as descriptive board context, but it is NOT a model feature. Approved by Joseph 2026-07-21.
