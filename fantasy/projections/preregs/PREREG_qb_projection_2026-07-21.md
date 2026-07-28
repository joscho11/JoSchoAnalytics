# PRE-REGISTRATION — QB SEASON-TOTAL PROJECTION (2026-07-21)

**STATUS: DESIGN LOCKED, NOTHING FIT.** Light PRODUCT prereg — no one-shot fire, no accept/reject
claim, no ship gate. Its job is to PIN every choice that could otherwise be shopped BEFORE any real model
is fit or any accuracy/Sleeper number is computed. Sleeper is the market baseline and is **shown, not
gated** (§9). Blindness note: §11.

**AUTHOR / PROVENANCE.** Designed by the intermediary from a read-only recon (2026-07-21), mirroring the
committed RB/WR/TE preregs (HEAD `78bdee4`) and inheriting their carry-forward lessons — but **QB is NOT a
straight mirror**: its rookie feature block is genuinely different (§3, §4), and it is the thinnest,
most-bimodal position (§3B). Joseph reviews and commits to lock.

**CARRY-FORWARD LESSONS (honored):**
1. **`depth_rank` is EXCLUDED from the start** (nflreadpy depth charts end at 2024 → train-present /
   deploy-absent; it collapsed the RB trees). No depth-chart feature in either QB bucket. 2026 coverage of
   every feature below was checked in recon; the build runs the deploy-gap check.
2. **The shipped code is not modified.** The QB build writes a NEW `build_qb_projection.py` that IMPORTS
   the position-agnostic RB engine (`season_total_target`, `nested_select`, `walk_forward`,
   `fit_final_model`, `_prep`, `_grid`, metrics, `FAMILIES`) + a QB frozen-matrix twin (`position=='QB'` +
   the PFF **passing** block). No refactor of `build_rb_projection.py` / `build_wr_projection.py` /
   `build_te_projection.py`.

---

## 0. WHAT THIS IS / SCOPE

A from-scratch **QB season-total half-PPR projection for 2026**, built as **two models sharing one target**
(veteran = ≥1 prior NFL season; rookie = none), merged into one projection column, shown on the board
**beside Sleeper's projection** + a difference column. QB is the LAST position (RB/WR/TE shipped
2026-07-21). Once built and approved it fills the QB rows of the shared projection surface
(`page_rookie_board.py` `_load_proj()` concatenates the per-position board files; RB/WR/TE rows unchanged).
Per §3B the **rookie arm may not ship** — veteran-only ship is the expected default, confirmed on the
fitted number at the STOP-2 readout.

---

## 1. TARGET DEFINITION — CONFIRMED CORRECT FOR QB

- **Target = observed season-total half-PPR points**, summed directly from weekly stats
  (`fantasy_points + 0.5·receptions`, REG) — **not** `target_ppg × games`. Reuses `season_total_target()`.
- **QB scoring is captured correctly** (verified this session, structure only): `season_total_target()`
  sums nflreadpy `fantasy_points`, which for QBs INCLUDES passing (yards/TDs/INTs) and rushing. Sanity
  check on top QB seasons: Lamar Jackson 2024 = 430.4, Patrick Mahomes 2022 = 416.9, Josh Allen 2021 =
  402.6 — correct QB fantasy totals (receptions ≈ 0 for QBs, so half-PPR ≈ standard). No target change needed.
- Partial/injury seasons fold IN; rostered-never-played = 0.
- **Training universe = the QB rows of `season_dataset_2014_2026.csv`** (~68–82 veteran + ~6–13 rookie QB
  per season). Target for every row; deep-roster 0s kept (backups are real 0s).

---

## 2. THE TWO MODELS + ROUTING RULE

Routing by `is_rookie` (pinned, exhaustive): `==1` → ROOKIE, `==0` → VETERAN. Every QB row routes to
exactly one model; partitions mutually exclusive and cover the universe (harness-asserted). Merged
projection = concatenation, SUBJECT to the §3B rookie ship/hold decision.

---

## 3. QB IS DIFFERENT — the rookie feature block, and a real signal gap (read before §4)

**3A. The college feature block is genuinely new (passing, not receiving).** WR/TE reused the frozen
matrix's RECEIVING block; QB uses the **PASSING** block. Recon coverage (135 QB rookies):
- **PFF passing block (the primary QB college signal): 10 cols, ~93% present** —
  `pff_passing_grades_pass`, `pff_passing_grades_offense`, `pff_passing_btt_rate` (big-time-throw rate),
  `pff_passing_avg_time_to_throw`, `pff_passing_accuracy_percent`, `pff_passing_completion_percent`,
  `pff_passing_pressure_to_sack_rate`, `pff_passing_avg_depth_of_target`, `pff_passing_qb_rating`,
  `pff_passing_touchdowns`.
- **⚠ SIGNAL GAP (QB-only, flagged):** the frozen matrix's `cfb` (cfbfastR box-score) block is
  **scrimmage/rushing/receiving only — there is NO college PASSING box-score** (no college passing yards,
  pass TDs, completion %, INTs; cfbfastR passing was not built into the frozen features). So a QB's core
  college PASSING production reaches the model ONLY through the PFF passing GRADES above, never as raw
  box-score. The `cfb` scrimmage columns capture a QB's college RUSHING (useful for mobile QBs) but not his
  passing. This is a real limitation the receiving positions did not have; disclosed, not tuned around.

**3B. QB is the thinnest, most under-powered, most bimodal position — veteran-only ship is the expected
default.** Pre-committed caveat, not a defect to tune away:
- **Tiny rookie sample.** QB rookies are only ~6–13/season (frozen college-matched panel 7–15/class; the
  hit-model panel already flagged QB as UNDERPOWERED at n=101). The rookie walk-forward folds have only
  **~7–13 test rows each** (2021–2025: 10/8/12/7/13) — far thinner than TE (22–27), WR (42–53), RB (28–33).
- **Extreme bimodality.** Most rookie (and many veteran) QBs are backups scoring near zero; a rare rookie
  starts and scores 200–430. Season-total median ≈ 60 with a 430 max. Ranking is dominated by the
  backup-vs-starter split, and for rookies "will he start Week 1?" is the whole question — and it is NOT in
  the feature set (the landing-spot features are receiving-oriented; `prior_team_pass_rate` is 0% for rookies).
- **Weak QB-specific landing signal.** `vacated_target_share` (a receiving metric) is the wrong opportunity
  proxy for a QB; there is no "projected starter" feature. 2026 rookie ADP coverage is only ~6%.
- **Consequence pre-committed:** the QB **veteran** arm (good Sleeper coverage — 2025 = 88%, strong
  `prior_ppg`/`prior_half_ppr` production priors) is expected to be the solid, shippable contribution. The
  QB **rookie** arm is expected to be non-viable or marginal; **veteran-only ship (rookie shows "coming",
  like the earlier positions' unbuilt arms) is the EXPECTED DEFAULT**, to be confirmed by Joseph at the
  STOP-2 readout on the actual fitted rookie rank correlation. This is a judgment, NOT decided by tuning.

---

## 4. FEATURE SET — PINNED, BY BUCKET, PER MODEL (the anti-shopping core)

Frozen candidate pool; within-pool selection only inside inner CV (§7). **No depth-chart feature.**

### VETERAN model (`season_dataset`, prior-season / point-in-time) — 32 features
The same 32-col position-agnostic pool the RB/WR/TE veteran models used. For QB the signal rests on the
production and rushing/team priors; the receiving priors are near-empty and act as dead weight (native-NaN
/ median). Recon coverage (QB veterans, 2024/2025/2026):
- **Prior production (encodes QB passing fantasy output):** `prior_ppg` (88/93/85%), `prior_half_ppr`
  (95/99/85%), `prior_games`, `ppg_2yr`, `ppg_3yr`, `ppg_trend` (72/75/67%), `career_high_ppg`,
  `prior_snap_share_pg`, `prior_touches_pg`.
- **Prior rushing (mobile-QB signal):** `prior_carries_pg`, `prior_ypc`, `prior_rush_epa` (85–99%),
  `prior_td_rate`.
- **Prior receiving (near-empty for QB — ~7% non-zero — kept for pool-identity, harmless under native-NaN):**
  `prior_targets_pg`, `prior_receptions_pg`, `prior_target_share`, `prior_air_yards_share`, `prior_adot`,
  `prior_yptarget`, `prior_rec_epa`.
- **Bio / draft:** `age`, `years_exp`, `draft_round`, `draft_pick` (~86–90%).
- **Availability prior:** `prior_games_missed`, `missed_prior_season`.
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays`, `vacated_target_share`,
  `vacated_rush_share`, `coach_changed`, `qb_changed`.
- **NO depth-chart feature.** **⚠ Flagged gap:** `season_dataset` has no granular QB passing-efficiency
  prior (completion %, yards-per-attempt, passer rating); the veteran passing signal reaches the model only
  through aggregate fantasy production (`prior_ppg` / `prior_half_ppr`). Disclosed. **CONDITIONAL
  talent/PFF-facet bucket: DEFERRED** (no per-season history), as in RB/WR/TE.

### ROOKIE model (draft / point-in-time) — 39 features (NEW composition)
The frozen hit-model rookie matrix **QB slice** (passing PFF + the rushing/dominance cfb subset), plus
landing-spot. Recon coverage (135 QB rookies):
- **Draft capital:** `draft_round`, `draft_pick`, `log_pick`.  **Age:** `age`.
- **Combine / athletic:** `forty`, `vertical`, `broad_jump`, `cone`, `shuttle`, `bench`, `ht_in`, `wt`,
  `bmi`, `speed_score` (ht/wt/bmi ~90%; forty/agility 48–58%; **`bench` 0% for QB** — native-NaN).
- **College PFF PASSING (primary signal, 10 cols, ~93%):** the block listed in §3A.
- **College cfb — rushing/dominance subset (mobile-QB + overall production; the receiving cfb cols are ~0
  for QB and EXCLUDED):** `cfb_final_dom`, `cfb_best_dom`, `cfb_breakout_class`, `cfb_seasons`,
  `cfb_rush_ypg`, `cfb_scrim_ypg`, `cfb_scrim_td`, `cfb_career_scrim_yds`, `cfb_career_scrim_td` (9 cols,
  ~96%). **NO college passing box-score exists (§3A gap).**
- **Landing-spot / opportunity:** `prior_team_pass_rate`, `prior_team_plays` (0% for rookies — no prior NFL
  team — kept for bucket-identity), `vacated_target_share`, `vacated_rush_share`, `coach_changed`,
  `qb_changed`. (Weak QB opportunity proxy — §3B.)
- **NO depth-chart feature.** **CONDITIONAL college talent score** (`rookie_score_2026.csv`) covers RB/WR/TE
  only — **no QB instrument exists**, so nothing to join; the QB rookie arm has no talent-score column at all.

Joins reuse the FROZEN hit-model bridges (combine `pfr_id`→`gsis`; PFF by `norm_name`; 2026 placeholder-gsis
by name+position coalesce).

---

## 5. LEAKAGE GUARD (HARD RULE)

Every feature knowable BEFORE season Y (identical to RB/WR/TE): veteran = prior-season / draft-time; rookie
= draft-time or drafting-team landing-spot; target for Y never a feature for Y. Prior-join convention
(`prior["season"] += 1`, merge on `(player_id, season)`; missed season → NaN priors). Talent/efficiency
facets DEFERRED; the ≤Y−1 lag assert stands. Harness proves the general form (peek screams; shuffled
alignment destroys signal; walk-forward never trains on its test season).

---

## 6. MISSING-DATA RULE (RULED — same as RB/WR/TE)

Tree models: native NaN routing. ElasticNet baseline: within-QB median-impute + per-feature missing flag.
No row dropped for missingness. QB-specific: the receiving veteran priors, `bench`, and combine agility are
sparse/empty for QB — native-NaN handles them and the flag marks them "unknown."

---

## 7. MODEL SLATE + GRIDS — PINNED, NESTED-CV SELECTED (anti-peeking)

Identical frozen slate + grids to RB/WR/TE (per model, independently): CatBoost (RMSE; depth {4,6}, lr
{0.03,0.06}, l2 {3,6}, iters {400,800}); LightGBM (mae; num_leaves {15,31}, lr {0.03,0.06}, n_est
{400,800}); XGBoost (squarederror, native-NaN; max_depth {4,6}, eta {0.03,0.06}, n_est {400,800},
reg_lambda {1,5}); ElasticNet (alpha {0.001,0.01,0.1}, l1_ratio {0.2,0.5,0.8}, median+flag). RF omitted.
**ANTI-PEEKING:** family/hyperparameters/feature-pruning chosen SOLELY by inner LOSO CV (MAE primary, RMSE
reported) on training seasons; the outer test season is never consulted. Grid frozen here.

---

## 8. VALIDATION — WALK-FORWARD BY SEASON

Outer folds 2021–2025, train ≤ Y−1 (QB Sleeper begins 2021; recon 0% ≤2020, 47% 2021 → 88% 2025). Inner
nested LOSO CV selects model+hyperparameters within each fold's training seasons. Metrics per fold / per
model / pooled: MAE, RMSE, Spearman vs actual season-total, veteran and rookie split out — report card only,
does NOT gate the ship. **The rookie folds are extremely thin (§3B); their metrics carry that caveat, and a
fold too small to run is reported honestly, not forced.**

---

## 9. SLEEPER COMPARISON — SHOWN, NOT GATED

On the board, permanently: the merged projection, the Sleeper column (`sleeper_pts_half_ppr`, season-total,
joinable 2021–2026), and a difference column. An OPTIONAL accuracy-vs-Sleeper check on 2021–2025 is computed
and stored for interest — **it GATES NOTHING and is NOT a success criterion.** "Beating Sleeper" is never a
ship requirement (RB/WR/TE all shipped without beating it; QB the same).

---

## 10. WHAT SHIPS REGARDLESS

The QB **veteran** projection column, the Sleeper column, and the difference column — filling the QB
veteran rows of the shared surface — ship once built and approved. The QB **rookie** column ships ONLY if
Joseph approves it at STOP 2 on the fitted rookie rank correlation (§3B expected default = HOLD, rookie
shows "coming"). Honest labels: season-total projection; the 2026 landing-spot caveat; the QB
thinness/underpower + no-college-passing-box-score caveats; "backtested, not live-validated"; "no claim to
beat Sleeper". RB/WR/TE board behavior unchanged.

---

## 11. BLINDNESS NOTE

Written BEFORE any QB model is fit and BEFORE any real QB accuracy/Sleeper number is computed. Recon touched
only STRUCTURE (row counts, coverage, column names, Sleeper units, sample sizes, the target's marginal
scale, and a structural verification that the target captures QB scoring) — never a feature-vs-target
relationship, never a fitted metric. The pool, slate, grids, folds, and metrics are frozen here so the build
session cannot shop them against the outcome. Design mirrors the committed RB/WR/TE preregs; every
QB-specific choice is inherited from recon coverage and the frozen matrix's actual QB columns.

---

## 12. FENCES / WHAT THIS SESSION DID (AND DID NOT) DO

- Wrote this prereg + a synthetic-only harness proof (`qb_projection_harness.py`). Fit NO model; computed NO
  accuracy; ran NO Sleeper comparison; committed NOTHING.
- Did NOT touch `talent_score_2026.csv` / `rookie_score_2026.csv` / `fantasy/talent/`, the RB/WR/TE
  models/results/board behavior, `build_rb_projection.py` / `build_wr_projection.py` /
  `build_te_projection.py`, the RB/WR/TE harnesses, the frozen hit-model harness, or any spent fire artifact.
- No parquet / no raw-PFF season table in either repo (PFF-derived QB matrix regenerated in TEMP scratch).
- The build session writes `build_qb_projection.py` importing the RB engine, fits the pinned models, joins
  Sleeper, runs the walk-forward, and (subject to the §3B decision) fills the QB rows — nothing re-shopped there.
