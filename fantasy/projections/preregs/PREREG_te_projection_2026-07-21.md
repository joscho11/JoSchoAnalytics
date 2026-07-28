# PRE-REGISTRATION — TE SEASON-TOTAL PROJECTION (2026-07-21)

**STATUS: DESIGN LOCKED, NOTHING FIT.** Light PRODUCT prereg — no one-shot fire, no accept/reject
claim, no ship gate. Its job is to PIN every choice that could otherwise be shopped (features, models,
grids, target, routing, validation) BEFORE any real model is fit or any accuracy/Sleeper number is
computed. Sleeper is the market baseline and is **shown, not gated** (§9). Blindness note: §11.

**AUTHOR / PROVENANCE.** Designed by the intermediary from a read-only recon (2026-07-21), mirroring the
committed RB and WR preregs (`PREREG_rb_projection_2026-07-21.md`, `PREREG_wr_projection_2026-07-21.md`,
HEAD `37acb80`) and inheriting their two carry-forward lessons. Joseph reviews and commits to lock.

**CARRY-FORWARD FROM THE SHIPPED RB/WR BUILDS (both honored):**
1. **`depth_rank` is EXCLUDED from the start.** nflreadpy's `load_depth_charts` ends at 2024 — zero rows
   for 2025/2026 — so it is train-present / deploy-absent and it collapsed the RB tree models on the
   deploy season. No depth-chart feature is pinned in either TE bucket. 2026 coverage of every feature
   below was checked in recon before pinning; nothing ~absent-at-deploy is included. (The build session
   also runs the deploy-gap check that caught nothing hidden for WR.)
2. **The shipped code is not modified.** The TE build session writes a NEW `build_te_projection.py` that
   IMPORTS the position-agnostic RB engine (`season_total_target`, `nested_select`, `walk_forward`,
   `fit_final_model`, `_prep`, `_grid`, metrics, `FAMILIES`) + a ~15-line TE frozen-matrix twin
   (`position=='TE'` + `pff_receiving`). No refactor of `build_rb_projection.py` / `build_wr_projection.py`.

---

## 0. WHAT THIS IS / SCOPE

A from-scratch **TE season-total half-PPR projection for 2026**, built as **two models sharing one target**
and merged into one projection column, shown on the board **beside Sleeper's projection** (permanent) plus
a difference column. TE-only this build (RB + WR shipped 2026-07-21; QB is a later, separate build). Once
built and approved it fills the TE rows of the same shared projection surface the RB/WR builds introduced
(`page_rookie_board.py` `_load_proj()` concatenates the per-position board files; RB/WR rows unchanged).

The two models: **VETERAN** (TEs with ≥1 prior NFL season) and **ROOKIE** (no prior NFL season). Both
regress the SAME target (§1); a player is scored by exactly one model (§2).

---

## 1. TARGET DEFINITION

- **Target = observed season-total half-PPR points**, per player per NFL season, summed directly from
  weekly stats (`fantasy_points + 0.5·receptions`, REG) — **not** `target_ppg × games` (which filters
  games ≥ 11 and drops partial seasons). Identical to RB/WR; reuses `season_total_target()`.
- Partial/injury seasons fold IN (rostered-never-played = 0). The model projects EXPECTED season total.
- **Training universe = the TE rows of `season_dataset_2014_2026.csv`** (~101–116 veteran + ~21–29 rookie
  TE per season). Target computed for every row; deep-roster 0s kept.

---

## 2. THE TWO MODELS + ROUTING RULE

Routing by `is_rookie` (pinned, exhaustive): `==1` → ROOKIE, `==0` → VETERAN. Every TE row routes to
exactly one model; partitions mutually exclusive and cover the universe (harness-asserted). Merged
projection = concatenation of the two models' outputs.

---

## 3. TE THINNESS + TARGET BIMODALITY (disclosed UP FRONT — read before the feature buckets)

TE is the **thinnest skill position**, and this is a pinned, pre-committed caveat, not a defect to tune
away:

- **Small samples.** Veterans ~101–116/season; **rookies only ~21–29/season** (frozen college-matched
  panel thinner still, ~11–20/class). The rookie walk-forward folds have only **~22–27 test rows each**
  (2021–2025: 27/25/23/22/22) — the thinnest arm of the three positions (RB 28–33, WR 42–53). It is
  runnable (inner LOSO has ~24 rookies/season, above the ≥10 floor), but its metrics will be **noisy and
  its rank correlation is expected to be the weakest yet** — possibly below the WR rookie arm (+0.68) and
  even the RB rookie arm (+0.55).
- **Zero-heavy / bimodal target.** TE season totals are strongly right-skewed: a handful of every-down TEs
  score big while a long tail scores near zero (measured: veteran prior-season half-PPR median ≈ 27, 10th
  percentile ≈ 0, 90th ≈ 118, max ≈ 261). MAE is dominated by the low mass; ranking the few big scorers
  is the hard part.
- **Consequence pre-committed:** whether the TE **rookie** arm ships on the board or instead shows a
  "coming" placeholder (like QB) is a judgment for Joseph at the STOP-2 readout, informed by the fitted
  rookie rank correlation and sample sizes — it is NOT decided by tuning. The **veteran** TE arm (larger,
  better-covered) is expected to be the solid contribution.

---

## 4. FEATURE SET — PINNED, BY BUCKET, PER MODEL (the anti-shopping core)

Frozen candidate pool; within-pool selection (if any) happens only inside inner CV (§7). **No depth-chart
feature in either bucket** (lesson 1).

### VETERAN model (`season_dataset`, prior-season / point-in-time) — 32 features
The same 32-col position-agnostic pool the RB/WR veteran models used, receiving priors as the TE signal.
Recon coverage (TE veterans, 2024/2025/2026):
- **Prior production:** `prior_ppg` (89/92/95%), `prior_half_ppr` (98/99/95%), `prior_games`, `ppg_2yr`,
  `ppg_3yr`, `ppg_trend` (70/72/74%), `career_high_ppg`.
- **Prior receiving usage / efficiency:** `prior_targets_pg`, `prior_receptions_pg`, `prior_target_share`,
  `prior_air_yards_share`, `prior_adot` (88/87/88%), `prior_yptarget`, `prior_rec_epa`, `prior_td_rate`,
  `prior_snap_share_pg`, `prior_touches_pg` (all ~87–95%; TE 2026 coverage is actually the best of the
  three positions).
- **Prior rushing (near-empty for TE, kept for pool-identity, harmless under native-NaN):**
  `prior_carries_pg`, `prior_ypc`, `prior_rush_epa`.
- **Bio / draft:** `age`, `years_exp`, `draft_round`, `draft_pick` (~71–74%; many TEs UDFA; native-NaN).
- **Availability prior:** `prior_games_missed`, `missed_prior_season`.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays`, `vacated_target_share`
  (100/100/84%), `vacated_rush_share`, `coach_changed`, `qb_changed`.
- **NO depth-chart feature.** **CONDITIONAL talent/PFF-facet bucket: DEFERRED** (no per-season history),
  as in RB/WR.

### ROOKIE model (draft / point-in-time) — 44 features
The frozen hit-model rookie matrix **TE slice** (the receiving block — TEs are receivers, so this mirrors
the WR slice), plus landing-spot. Recon coverage (180 TE rookies):
- **Draft capital:** `draft_round`, `draft_pick`, `log_pick`.  **Age:** `age`.
- **Combine / athletic:** `forty`, `vertical`, `broad_jump`, `cone`, `shuttle`, `bench`, `ht_in`, `wt`,
  `bmi`, `speed_score` (combine any-present 86%; forty 68%, cone/shuttle/bench 44–52%).
- **College production (cfbfastR), receiving-oriented slice:** `cfb_final_dom`, `cfb_best_dom`,
  `cfb_scrim_ypg`, `cfb_rec_ypg`, `cfb_rec_pg`, `cfb_ypr`, `cfb_final_recshare`, `cfb_career_scrim_yds`,
  `cfb_career_scrim_td`, `cfb_seasons`, `cfb_breakout_class` (any-present 93%; excludes id/metadata + the
  rushing cfb cols, as in the WR slice).
- **College PFF facets (the receiving block):** `pff_receiving_grades_offense`,
  `pff_receiving_grades_pass_route`, `pff_receiving_yprr`, `pff_receiving_avg_depth_of_target`,
  `pff_receiving_contested_catch_rate`, `pff_receiving_drop_rate`,
  `pff_receiving_yards_after_catch_per_reception`, `pff_receiving_targeted_qb_rating`,
  `pff_receiving_routes`, `pff_receiving_receptions`, `pff_receiving_yards`, `pff_receiving_touchdowns`,
  `pff_receiving_avoided_tackles` (13 cols, any-present 91%). Same block as the WR rookie slice.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays` (0% for rookies — no prior
  NFL team — kept for bucket-identity, harmless), `vacated_target_share` (82% for 2026 rookies),
  `vacated_rush_share`, `coach_changed`, `qb_changed`.
- **NO depth-chart feature.** **CONDITIONAL college talent score** (`rookie_score_2026.csv`, RB/WR/TE,
  2026 only): DEFERRED for training folds; may be shown/joined for the 2026 deploy row only.

Joins reuse the FROZEN hit-model bridges (combine `pfr_id`→`gsis`; college/PFF by `norm_name`; 2026
placeholder-gsis handled by name+position coalesce), as in RB/WR.

---

## 5. LEAKAGE GUARD (HARD RULE)

Every feature knowable BEFORE season Y (identical to RB/WR): veteran = prior-season / draft-time; rookie =
draft-time or drafting-team landing-spot; target for Y never a feature for Y. Prior-join convention
(`prior["season"] += 1`, merge on `(player_id, season)`; missed season → NaN priors). Talent/efficiency
facets (DEFERRED) carry the ≤Y−1 lag assert. The harness proves the general form (peek screams; shuffled
alignment destroys signal; walk-forward never trains on its test season).

---

## 6. MISSING-DATA RULE (RULED — same as RB/WR)

Tree models (CatBoost/LightGBM/XGBoost): native NaN routing. ElasticNet baseline: within-TE median-impute
+ per-feature missing flag (not mean-impute). No row dropped for missingness (would gut the thin TE
rookie slice and the many UDFA TEs). Combine agility (`cone`/`shuttle`/`bench`) and rushing priors are
sparse for TE; native-NaN handles them and the flag marks them "unknown."

---

## 7. MODEL SLATE + GRIDS — PINNED, NESTED-CV SELECTED (anti-peeking)

Identical frozen slate + grids to RB/WR (per model, veteran and rookie independently): **CatBoost** (RMSE;
depth {4,6}, lr {0.03,0.06}, l2 {3,6}, iters {400,800}); **LightGBM** (mae; num_leaves {15,31}, lr
{0.03,0.06}, n_est {400,800}); **XGBoost** (squarederror, native-NaN; max_depth {4,6}, eta {0.03,0.06},
n_est {400,800}, reg_lambda {1,5}); **ElasticNet** (alpha {0.001,0.01,0.1}, l1_ratio {0.2,0.5,0.8},
median+flag). RF omitted. **ANTI-PEEKING:** family/hyperparameters/feature-pruning chosen SOLELY by inner
LOSO CV (MAE primary, RMSE reported) on training seasons; the outer test season is never consulted. Grid
frozen here, not expanded after any result.

---

## 8. VALIDATION — WALK-FORWARD BY SEASON

Outer folds 2021–2025, train ≤ Y−1 (Sleeper begins 2021; TE recon 0% ≤2020, 31% 2021 → 72% 2025). Inner
nested LOSO CV selects model+hyperparameters within each fold's training seasons. Metrics per fold / per
model / pooled: MAE, RMSE, Spearman of projection vs actual season-total, veteran and rookie split out —
report card only, does NOT gate the ship. The rookie folds are thin (§3); their metrics are reported with
that caveat. If a fold's rookie slice is too small to run, that is reported honestly, not forced.

---

## 9. SLEEPER COMPARISON — SHOWN, NOT GATED

On the board, permanently: the merged projection, the Sleeper column (`sleeper_pts_half_ppr`, season-total,
joinable 2021–2026), and a difference column. An OPTIONAL accuracy-vs-Sleeper check on 2021–2025 is
computed and stored for interest — **it GATES NOTHING and is NOT a success criterion.** "Beating Sleeper"
is never a ship requirement. (RB did not beat Sleeper and shipped; WR was competitive on MAE but not rank
and shipped; TE ships on the same doctrine regardless of where it lands.)

---

## 10. WHAT SHIPS REGARDLESS

The merged TE projection column (veteran + rookie, subject to the §3 rookie-arm judgment), the Sleeper
column, and the difference column — filling the TE rows of the shared projection surface — once built and
approved. Honest labels: season-total projection; 2026 landing-spot caveat; the TE thinness/bimodality
caveat; "backtested, not live-validated"; "no claim to beat Sleeper". RB/WR board behavior unchanged.

---

## 11. BLINDNESS NOTE

Written BEFORE any TE model is fit and BEFORE any real TE accuracy/Sleeper number is computed. Recon
touched only STRUCTURE (row counts, coverage, column names, Sleeper units, sample sizes, the target's
marginal skew) — never a feature-vs-target relationship, never a fitted metric. The pool, slate, grids,
folds, and metrics are frozen here so the build session cannot shop them against the outcome. Design
mirrors the committed RB/WR preregs; every TE-specific number is inherited from recon coverage.

---

## 12. FENCES / WHAT THIS SESSION DID (AND DID NOT) DO

- Wrote this prereg + a synthetic-only harness proof (`te_projection_harness.py`). Fit NO model; computed
  NO accuracy; ran NO Sleeper comparison; committed NOTHING.
- Did NOT touch `talent_score_2026.csv` / `rookie_score_2026.csv` / `fantasy/talent/`, the RB/WR
  models/results/board behavior, `build_rb_projection.py` / `build_wr_projection.py`, the RB/WR harnesses,
  the frozen hit-model harness, or any spent fire artifact.
- No parquet / no raw-PFF season table in either repo (PFF-derived TE matrix regenerated in TEMP scratch).
- The build session writes `build_te_projection.py` importing the RB engine, fits the pinned models, joins
  Sleeper, runs the walk-forward, and fills the TE rows of the shared surface — nothing here re-shopped there.
