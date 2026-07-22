# PRE-REGISTRATION — WR SEASON-TOTAL PROJECTION (2026-07-21)

**STATUS: DESIGN LOCKED, NOTHING FIT.** Light PRODUCT prereg — no one-shot fire, no accept/reject
claim, no ship gate. Its job is to PIN every choice that could otherwise be shopped (features, models,
grids, target, routing, validation) BEFORE any real model is fit or any accuracy/Sleeper number is
computed. Sleeper is the market baseline and is **shown, not gated** (§9). Blindness note: §11.

**AUTHOR / PROVENANCE.** Designed by the intermediary from a read-only recon (2026-07-21), mirroring the
committed RB prereg (`PREREG_rb_projection_2026-07-21.md`, HEAD `9a78f94`) and inheriting its two
carry-forward lessons. Joseph reviews and commits this file to lock the design.

**CARRY-FORWARD FROM THE SHIPPED RB BUILD (both honored here):**
1. **`depth_rank` is EXCLUDED from the start** (not "provisional"). nflreadpy's `load_depth_charts` table
   ends at 2024 — zero rows for 2025 or 2026. It is a train-present / deploy-absent feature that poisoned
   the RB tree models on exactly the deploy season (Bijan projected 4 vs actual 331), and RB dropped it by
   Amendment 1. This prereg pins NO depth-chart feature in either bucket. 2026-coverage of every feature
   below was checked in recon before pinning; nothing ~absent-at-deploy is included.
2. **The shipped RB code is not modified.** The WR build session (later) writes a NEW
   `build_wr_projection.py` that IMPORTS the position-agnostic RB engine (`season_total_target`,
   `nested_select`, `walk_forward`, `fit_final_model`, `_prep`, `_grid`, metrics) and defines only
   WR-specific assembly + a WR frozen-matrix slice. No refactor of `build_rb_projection.py` unless
   pkl/prediction-identity of the shipped RB models/results/board is proven first (cowork-change-control).

---

## 0. WHAT THIS IS / SCOPE

A from-scratch **WR season-total half-PPR projection for 2026**, built as **two models sharing one target**
and merged into one projection column, shown on the board **beside Sleeper's projection** (permanent) plus
a difference column. WR-only this build (RB shipped 2026-07-21; TE/QB are later, separate builds under
their own prereg). Once built and approved in a LATER session it adds a WR projection surface (the rookie
board's projection column already sources the RB model for RB rows; the WR model fills the WR rows the same
way — RB behavior unchanged).

The two models:
- **VETERAN model** — WRs with ≥1 prior NFL season (prior receiving production exists).
- **ROOKIE model** — WRs with no prior NFL season (college + draft + landing-spot only).

Both regress the SAME target (§1); their outputs are concatenated into one projection column (a player is
scored by exactly one model per §2).

---

## 1. TARGET DEFINITION

- **Target = observed season-total half-PPR points**, per player per NFL season (row = one
  `(player, season)`). Half-PPR = `fantasy_points + 0.5·receptions` (repo formula), **summed over the
  regular season**, computed directly from weekly stats — **not** `target_ppg × games` (that column
  filters games ≥ 11 and would drop partial seasons). Identical to the RB build; reuses the same
  `season_total_target()` function.
- **Partial seasons / injuries fold INTO the target, not out of it.** A player who plays 6 games and scores
  55 total is a 55; a player rostered but who never played is 0. The model projects EXPECTED season total
  (rate × availability jointly) — what a fantasy manager drafts on. Disclosed: high-variance injury seasons
  are inherent noise in this target.
- **Training universe = the WR rows of `season_dataset_2014_2026.csv`** (~170–212 veteran + ~41–59 rookie
  WR per season). Target computed for every row; deep-roster 0s are kept (real outcomes).

---

## 2. THE TWO MODELS + ROUTING RULE

**Routing is by the `is_rookie` flag, pinned and exhaustive:**
- `is_rookie == 1` (no prior NFL season) → **ROOKIE model**.
- `is_rookie == 0` (≥1 prior NFL season) → **VETERAN model**.

Every WR row routes to **exactly one** model; the two partitions are mutually exclusive and cover the
universe (harness-asserted, §STOP-4). The final projection column = the concatenation of the two models'
outputs. Identical routing rule to the RB build.

---

## 3. FEATURE SET — PINNED, BY BUCKET, PER MODEL (the anti-shopping core)

All features below are the FROZEN candidate pool. Feature SELECTION within this pool (if any) happens only
inside inner CV (§7); the pool itself is fixed here and not expanded after seeing any result.
**`depth_rank` / any depth-chart feature is NOT in either bucket (carry-forward lesson 1).**

### VETERAN model (all from `season_dataset`, all prior-season / point-in-time) — 32 features
The same position-agnostic `season_dataset` pool the RB veteran model used, with the receiving priors as
the prominent WR signal. Recon coverage (WR veterans, 2024/2025/2026) in parentheses:
- **Prior production:** `prior_ppg` (91/92/88%), `prior_half_ppr` (99/98/88%), `prior_games`, `ppg_2yr`,
  `ppg_3yr`, `ppg_trend` (69/69/63%), `career_high_ppg`.
- **Prior receiving usage / efficiency (WR signal):** `prior_targets_pg`, `prior_receptions_pg`,
  `prior_target_share`, `prior_air_yards_share`, `prior_adot`, `prior_yptarget`, `prior_rec_epa`,
  `prior_td_rate`, `prior_snap_share_pg`, `prior_touches_pg` (all ~88–92%).
- **Prior rushing (near-empty for WR, kept for pool-identity, harmless under native-NaN):**
  `prior_carries_pg`, `prior_ypc` (33–46%), `prior_rush_epa`.
- **Bio / draft:** `age`, `years_exp`, `draft_round`, `draft_pick` (draft cols ~73–74% — many veteran WRs
  are UDFA/undrafted; native-NaN).
- **Availability prior:** `prior_games_missed`, `missed_prior_season`.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays`, `vacated_target_share`
  (98/100/82% — the prominent WR opportunity signal), `vacated_rush_share`, `coach_changed`, `qb_changed`.
- **NO depth-chart feature** (lesson 1).
- **CONDITIONAL — prior-season talent / PFF-efficiency facets:** DEFERRED (no per-season historical
  veteran talent/PFF table exists), exactly as in the RB prereg. Declared so it is never quietly added.

### ROOKIE model (all knowable at draft / point-in-time) — 44 features
The frozen hit-model rookie matrix, **WR slice** (the receiving-oriented columns), reused verbatim from the
frozen assemble scripts, plus landing-spot. Recon coverage (388 WR rookies) in parentheses:
- **Draft capital:** `draft_round`, `draft_pick`, `log_pick`.
- **Age:** `age`.
- **Combine / athletic:** `forty`, `vertical`, `broad_jump`, `cone`, `shuttle`, `bench`, `ht_in`, `wt`,
  `bmi`, `speed_score` (combine any-present 84%; forty 73%, ht/wt 84%, cone/shuttle/bench ~41–43%).
- **College production (cfbfastR), receiving-oriented slice:** `cfb_final_dom`, `cfb_best_dom`,
  `cfb_scrim_ypg`, `cfb_rec_ypg`, `cfb_rec_pg`, `cfb_ypr`, `cfb_final_recshare`, `cfb_career_scrim_yds`,
  `cfb_career_scrim_td`, `cfb_seasons`, `cfb_breakout_class` (box any-present 94%; excludes the id/metadata
  cols `cfb_pid`/`cfb_last_season`/`cfb_final_class` and the rushing `cfb_rush_ypg`/`cfb_ypc`, mirroring how
  the RB slice excluded id/metadata).
- **College PFF facets (WR = the receiving block):** `pff_receiving_grades_offense`,
  `pff_receiving_grades_pass_route`, `pff_receiving_yprr`, `pff_receiving_avg_depth_of_target`,
  `pff_receiving_contested_catch_rate`, `pff_receiving_drop_rate`,
  `pff_receiving_yards_after_catch_per_reception`, `pff_receiving_targeted_qb_rating`,
  `pff_receiving_routes`, `pff_receiving_receptions`, `pff_receiving_yards`, `pff_receiving_touchdowns`,
  `pff_receiving_avoided_tackles` (13 cols, any-present 94%). This is the WR analog of the RB slice's
  `pff_rushing_*` block.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays` (0% for rookies — no prior NFL
  team — kept for bucket-identity, harmless under native-NaN, same as RB), `vacated_target_share` (84% for
  2026 rookies — the prominent WR opportunity signal), `vacated_rush_share`, `coach_changed`, `qb_changed`
  (the DRAFTING team's context).
- **NO depth-chart feature** (lesson 1).
- **CONDITIONAL — college talent score:** `rookie_score_2026.csv` covers RB/WR/TE (2026 only). Historical
  per-class rookie talent scores do not exist → **DEFERRED** for training folds; may be shown/joined for the
  2026 deploy row only. Declared so it is not quietly added.

The college↔NFL and combine joins reuse the FROZEN hit-model bridges (combine `pfr_id`→`gsis`; college/PFF
by `norm_name`; the placeholder-gsis seam on 2026 handled by name+position coalesce), exactly as the RB
build did.

---

## 4. LEAKAGE GUARD (HARD RULE)

**Every feature must be knowable BEFORE the projected season Y** (identical rule to the RB build):
- All veteran features are PRIOR-season (`prior_*`) or draft-time (bio/draft).
- All rookie features are draft-time (draft/combine/college/age) or drafting-team landing-spot.
- The target for season Y is NEVER a feature for Y; no within-season-Y stats leak.
- Prior-join convention (`build_season_dataset.py`): `prior["season"] += 1` then merge on
  `(player_id, season)` — a player who missed a season gets NaN priors, never carried-forward stats.
- **TALENT-SCORE / EFFICIENCY-FACET LAG (explicit):** any talent-score / PFF-efficiency facet is LAGGED to
  ≤ Y−1; the build ASSERTS this. (Those buckets are DEFERRED per §3; the assert is a standing requirement.)
The harness proves the general form (peek probe must scream; shuffled-alignment probe must destroy signal;
walk-forward never trains on its test season — §STOP-4).

---

## 5. MISSING-DATA RULE (RULED — same as RB, Joseph 2026-07-21)

- **Tree models (CatBoost / LightGBM / XGBoost):** native NaN routing — a missing value stays NaN and the
  model learns an "unknown" branch. Nothing invented.
- **Regularized linear baseline (ElasticNet):** within-WR median-impute + a per-feature missing-indicator
  flag; NOT naive mean-imputation.
- No row is dropped for missingness (would gut the thin 2026 landing-spot and the many UDFA/undrafted WRs).
- WR-specific note: the rushing priors (`prior_ypc` etc.) and combine agility (`cone`/`shuttle`/`bench`) are
  sparsely populated for WR; native-NaN handles them, and the ElasticNet flag marks them "unknown."

---

## 6. LANDING-SPOT / 2026 HANDLING (disclosed up front)

For the historical TEST seasons (2021–2025) landing-spot features are well-populated. For the UNPLAYED 2026
season they are the thinnest, noisiest input — measured this session (WR 2026):
`vacated_target_share` / `vacated_rush_share` 84% (the prominent WR opportunity signal — decent),
`prior_team_pass_rate` 88% for veterans but **0% for rookies** (no prior NFL team), **`qb_changed` 100%
present but ALL ZERO** (undeterminable pre-season), `coach_changed` 100% (21% non-zero), **ADP pos-rank only
10% present for 2026 WR rookies** (still filling over the summer — thinner than RB's 35%).

**Pinned disclosure:** for the UNPLAYED 2026 season these opportunity inputs are PROVISIONAL and NOISIER
than in the historical folds; 2026 projections should be RE-RUN as ADP and rosters firm through August.
This noise is inherent to projecting an unplayed season and is NOT a defect to tune away. **No depth-chart
feature is used** (lesson 1), so there is no depth-chart-availability gap to disclose.

---

## 7. MODEL SLATE + HYPERPARAMETER GRIDS — PINNED, NESTED-CV SELECTED (anti-peeking)

Identical frozen slate + grids to the RB build (per model, veteran and rookie independently):
- **CatBoost** (loss RMSE) — depth {4,6}, learning_rate {0.03,0.06}, l2_leaf_reg {3,6}, iterations {400,800}.
- **LightGBM** (objective mae) — num_leaves {15,31}, learning_rate {0.03,0.06}, n_estimators {400,800}.
- **XGBoost** (reg:squarederror, native-NaN) — max_depth {4,6}, eta {0.03,0.06}, n_estimators {400,800},
  reg_lambda {1,5}.
- **Regularized linear baseline** — ElasticNet, alpha {0.001,0.01,0.1}, l1_ratio {0.2,0.5,0.8}
  (median-impute+flag inputs).
- (Optional RandomForest omitted, as in the RB build, to keep one clean missing-data regime per family.)

**ANTI-PEEKING RULE (hard):** model family, hyperparameters, and any within-pool feature selection are
chosen SOLELY by the INNER leave-one-season-out CV score (MAE primary, RMSE reported) on the training
seasons. The OUTER test season is NEVER consulted for any selection decision. The whole grid is frozen
here; it is not expanded after seeing any fold's result.

---

## 8. VALIDATION STRUCTURE — WALK-FORWARD BY SEASON

- **Outer walk-forward folds:** project each of **2021, 2022, 2023, 2024, 2025** using models trained ONLY
  on seasons ≤ Y−1. Deploy row = 2026 (unplayed, not a fold). 2021–2025 chosen because WR Sleeper coverage
  begins 2021 (recon: 0% ≤2020, 39% 2021 → 75% 2025), identical to the RB window.
- **Inner tuning:** nested leave-one-season-out CV within each outer fold's training seasons selects the
  model+hyperparameters (§7). The outer test season is untouched during tuning.
- **Metrics (per fold, per model, pooled):** MAE, RMSE, Spearman of projection vs actual season-total,
  reported per position-model and merged. They do NOT gate the ship (§10).
- Leakage: train strictly on prior seasons; the harness asserts no fold trains on its own test season.

---

## 9. SLEEPER COMPARISON — SHOWN, NOT GATED

- On the board, **permanently and unconditionally**: the merged **projection**, the **Sleeper** column
  (`sleeper_pts_half_ppr`, season-total, joinable 2021–2026), and a **difference** column
  (`projection − Sleeper`).
- An OPTIONAL accuracy-vs-Sleeper check on 2021–2025 (MAE/RMSE/Spearman of projection vs Sleeper vs actual)
  is **computed and stored for interest only. It GATES NOTHING and is NOT a success criterion.** "Beating
  Sleeper" is explicitly not a ship requirement; no future session may treat it as one. (The RB build did
  not beat Sleeper — ρ 0.67 vs 0.80 — and shipped regardless; the WR build ships on the same doctrine.)

---

## 10. WHAT SHIPS REGARDLESS

The **merged WR projection column** (veteran + rookie), the **Sleeper column**, and the **difference
column** — filling the WR rows of the projection surface the RB build introduced — once built and approved
in a later session. It ships with honest labels (a season-total projection; the 2026 landing-spot caveat of
§6; "backtested, not live-validated"; "no claim to beat Sleeper"). RB behavior on the board is unchanged.

---

## 11. BLINDNESS NOTE

This prereg is written BEFORE any WR model is fit and BEFORE any real WR accuracy or Sleeper-comparison
number is computed. The recon this session touched only data STRUCTURE (row counts, coverage rates, column
names, Sleeper units, sample sizes) — never a feature-vs-target relationship, never a fitted metric. The
feature pool, model slate, grids, folds, and metrics above are frozen here so the build session cannot shop
them against the outcome. The design mirrors the already-committed RB prereg; every WR-specific number was
inherited from recon coverage, none invented to fit an outcome.

---

## 12. FENCES / WHAT THIS SESSION DID (AND DID NOT) DO

- Wrote this prereg + a synthetic-only harness proof (`wr_projection_harness.py`). Fit NO real model;
  computed NO real accuracy; ran NO Sleeper comparison; committed NOTHING.
- Did NOT touch `talent_score_2026.csv` / `rookie_score_2026.csv` / `fantasy/talent/`, the RB models /
  results / board, `page_rookie_board.py` behavior, the frozen hit-model harness, or any spent fire artifact.
- Did NOT modify `build_rb_projection.py` or `rb_projection_harness.py` (the shipped RB code).
- Reuses the FROZEN hit-model feature bridges and the `season_dataset` verbatim; builds no new data artifact
  into the repo this session; no parquet / no raw-PFF season table in either repo.
- The build session (next) writes `build_wr_projection.py` importing the RB engine, fits the pinned models,
  joins Sleeper, runs the walk-forward, and fills the WR projection surface — nothing here may be re-shopped
  there.
