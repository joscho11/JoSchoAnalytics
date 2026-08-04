# PHASE 1A — REQUIREMENT-TO-CODE MATRIX

Every row verified against **executable code**, not docstrings or comments. Where a comment and the
code disagree, the code is what is recorded and the discrepancy is called out.

Governing prereg: `preregs/PREREG_coach_quality_2026-07-28.md` (v3.1).
Audited files: `build_coach_features.py`, `build_arm3_effects.py`, `build_team_offense_panel.py`,
`build_allocation_panel.py`, `build_personnel_controls.py`, `build_playcaller_table.py`.

## Headline finding

**There are no test files anywhere in `coaching/`.** Every "covering assertion" cell below reads
NONE. The only assertions in the subproject are inline prints in the panel builders and the T0
coverage report. Arms 1–5 feature construction has zero automated coverage.

---

## Cross-cutting: play-caller segment grain

| Field | Finding |
|---|---|
| Prereg requirement | §4 ARM 1: aggregate "across the play-caller's prior seasons, **weighted by games called**". §1.5: midseason changes split by games. |
| Generating function | `build_coach_features.play_caller_ledger()` → `prior_history()` |
| Raw source columns | `actual_play_caller.csv`: `season, team, person_id, n_games_attributed` |
| Timing rule | `base[base.season < Y]` — **PASS**, strictly prior |
| Aggregation grain | **FAIL.** `play_caller_ledger()` groups to (season, team, person_id) and **discards `week_start`/`week_end`**. `prior_history()` then joins the offense panel on `["season","team"]` only (line 140), so **both callers in a split team-season receive the identical full-season offense row**. Games are used only as a *weight*, never to restrict *which games* the metrics come from. |
| Missing-value rule | metric NaN → coach dropped from that metric's mean; if no history at all → fixed league prior |
| Leakage prevention | season-level only; **no week-range validation exists** — `week_start`/`week_end` appear **0 times** in both builders |
| Covering assertion | **NONE** |
| Status | **FAIL — defect 1. Blocks Arms 1, 2, 4.** |

---

## ARM 1 — simple coach résumé

| Feature family | Requirement | Code | Timing | Grain | Missing | Assertion | Status |
|---|---|---|---|---|---|---|---|
| `hc_career_win_pct_shrunk`, `hc_roll3_win_pct_shrunk` | REG only, no playoffs, **tie = 0.5 win** | `head_coach_ledger()`; `np.where(margin>0,1,np.where(margin<0,0,0.5))`; `game_type=="REG"` | seasons `< Y` | game → coach-season | no history → 0.500, rel 0 | NONE | **PASS** (logic correct, untested) |
| `hc_prior_games`, `hc_prior_games_log`, `hc_reliability` | `g/(g+32)` on attributed games | `_shrink()`; `games` counts only games with a result | seasons `< Y` | game | fill 0 | NONE | **PASS** |
| `hc_no_prior_history` | flag, no penalty/bonus | `hc_prior_games.isna().astype(int)` before fill | — | — | — | NONE | **PASS** |
| `pc_career_off_rank_pct_shrunk`, `pc_roll3_*` | composite of 5 rank percentiles, `1-(r-1)/(n-1)`, **≥3 of 5**, weighted by games called | `team_offense_views()` computes `rankpct_*` per season; `off_rank_composite` requires `notna().sum()>=3` | seasons `< Y` | **team-season, NOT segment** | <3 components → NaN → league prior | NONE | **FAIL — inherits defect 1** |
| `pc_prior_games`, `pc_reliability`, `pc_no_prior_history` | `g/(g+32)` | `_shrink()` on `n_games_attributed` | seasons `< Y` | segment games (correct) | fill 0 | NONE | **PASS** |
| `pc_tenure_current_team`, `pc_changed` | change flag on the play-caller | computed on **primary caller only** (`pc_prim = ...drop_duplicates`) | prior row | team-season | NaN if unknown | NONE | **FAIL — a within-season caller change is invisible to `pc_changed`** |
| `pc_is_head_coach` | derived | `pc_person_id == hc_person_id` | — | primary vs primary | NaN if unknown | NONE | **PARTIAL — primary-only** |

**Points-per-game component note:** `off_points_per_game` is drive-derived (TD 7 / FG 3 / safety −2)
in `build_allocation_panel.py`, not actual team points. Defensible and documented, but it is a
*proxy* for the prereg's "offensive points per game" and should be stated as such.

---

## ARM 2 — continuous offensive effectiveness

| Feature family | Requirement | Code | Timing | Grain | Missing | Assertion | Status |
|---|---|---|---|---|---|---|---|
| `pc_*_z_{epa_play, success_rate, points_drive, yards_play, explosive_rate, redzone_td_rate}` career + roll3 | within-season z across teams, aggregate over prior games, shrink to 0.000, **keep dimensions separate** | `team_offense_views()`: `(m - g.transform("mean")) / g.transform("std")` per season; `prior_history(..., "z")` | seasons `< Y` | **team-season, NOT segment** | NaN → 0.000 | NONE | **FAIL — inherits defect 1** |
| Kneel/spike/2pt exclusion | frozen PBP filter | `offensive_plays()` in `build_team_offense_panel.py` | — | play | — | inline print only | **PASS** |
| `proe`, `team_adot` coverage | 2006+ only (`xpass` model start) | native NaN pre-2006 | — | — | NaN preserved | inline print | **PASS, disclosed** |

**Docstring vs code (resolved in favour of code).** `prior_history()`'s docstring says values are
"shrunk toward the **EXPANDING league mean** of seasons < Y", but the code shrinks toward a **fixed**
0.500 / 0.000. This is *correct*: because rank percentiles and z-scores are standardised **within
each source season**, their league means are 0.5 and 0.0 by construction, so the fixed constants
*are* the expanding league means. The docstring wording is imprecise and must be replaced with the
structural justification rather than left implying a recomputation that does not happen.

---

## ARM 3 — personnel-adjusted coach effect

| Requirement | Code | Status |
|---|---|---|
| Expanding expectation model, seasons `< S` only | `stage1_residuals()`: `tr = df[df.season < S]` | **PASS** |
| All §3.2 controls **plus season effects** | `CONTROLS` list omits **`prior_qb_id`** (present in `personnel_controls.csv`). Comment at line 64 claims "season fixed effect … applied as an intercept shift"; the code fits numeric controls with a plain ridge intercept and **no season indicators** | **FAIL — defect 4; comment overstates code** |
| No season-S performance in controls | all controls are lagged/preseason | **PASS** |
| Preprocessing learned from training only | `med = Xtr.median()` then applied to `Xte` | **PASS** (median only; no scaler, and `RidgeCV` is scale-sensitive) |
| Cross-classified HC + PC identity blocks | `stage2_effects()` builds 0/1 indicator columns | **PARTIAL** |
| **Exposure by games called** | **FAIL.** Uses `pc_person_id` from `coach_features.csv`, i.e. the **primary caller only**; all 18 splits' secondary callers are discarded, and every included identity gets weight **1.0** regardless of games | **FAIL — defect 2** |
| HC==PC collapse without duplication | `h["same"]` excludes the PC column when identical | **PASS in intent** — but untested, and interacts with the exposure defect |
| Regularisation selected inside training only | `RidgeCV(alphas=ALPHAS)` — **default row-level generalised CV, not season-blocked** | **FAIL — defect 5** |
| Tuning resolved | **9 of 10 target-season fits selected the grid maximum (1000)**; 1,194/1,292 rows = 92.4% row-weighted. Stage-1 alpha **never persisted** | **FAIL — unresolved boundary** |
| Reliability | `n_seasons / (n_seasons + 32/16)` at lines 110, 116 — frozen formula is `prior_games/(prior_games+32)` | **FAIL — defect 3** |

---

## ARM 4 — scheme and allocation

| Feature family | Requirement | Code | Status |
|---|---|---|---|
| plays/game, neutral pass rate, PROE, early-down + RZ pass rate, pace, RB/QB carry share, RB/WR/TE target share, RZ share by position, aDOT | strictly prior, shrunk, **position-relevant only** | `SCHEME_METRICS` list is complete and matches the prereg | **PASS on coverage** |
| Segment attribution | games called | joins on (season, team) | **FAIL — inherits defect 1** |
| Position-relevant subsetting | QB/RB/WR/TE each get only their block | **NOT IMPLEMENTED YET** — all 16 metrics are emitted for every team-season; the per-position subset happens at arm assembly, which does not exist | **PENDING (not a defect yet)** |
| Pace definition | inter-snap gap within drive, (0,60] s | `build_allocation_panel.py`, 77% of plays qualify | **PASS** |

---

## ARM 5 — adjusted quality plus scheme

| Requirement | Status |
|---|---|
| Continuity + tenure + Arm 3 effects + Arm 4 position features + reliability/no-history | **NOT BUILT** — arm assembly does not exist yet |
| **Excludes** Arm 1 win/rank and Arm 2 raw efficiency | to be enforced at assembly; no code yet |

---

## Summary

| Arm | Blocking defects | Status |
|---|---|---|
| 1 | segment attribution; `pc_changed` primary-only | **FAIL** |
| 2 | segment attribution | **FAIL** |
| 3 | segment attribution, exposure, reliability, controls, regularisation | **FAIL (5 defects)** |
| 4 | segment attribution | **FAIL** |
| 5 | not built | **N/A** |

Nothing in Arms 1–5 currently passes. The single highest-leverage repair is **segment attribution**,
which alone blocks Arms 1, 2, 3 and 4.

---

## Phase 1C completion status (v3.4 PREFIT, 2026-07-28)

Zero test files existed in `coaching/` when this matrix was first written. That is now closed:
**`tests/test_coaching_phase1c.py` — 18 registered tests, all passing**, discoverable by
`pytest fantasy/projections/coaching/tests/`.

| requirement | status | evidence |
|---|---|---|
| Deterministic rebuild (byte-identical) | **PASS** | `test_rebuild_is_byte_identical` |
| Bye-week game counts stay corrected | **PASS** | `test_bye_week_game_counts_stay_corrected` (GB 2015 = 13/3) |
| 2026 scheduled counts = 17 | **PASS** | `test_2026_scheduled_counts_are_17` (32x17=544) |
| No overlapping/duplicate segments | **PASS** | `test_no_overlapping_or_duplicate_segments` |
| Placeholder dates never eligible | **PASS** | `test_no_placeholder_date_is_ever_eligible` |
| Month precision uses upper bound | **PASS** | `test_month_precision_uses_conservative_upper_bound` |
| Audited dates match bylines | **PASS** | `test_audited_dates_match_their_bylines` |
| Ledger/table cannot diverge | **PASS** | `test_ledger_and_table_cannot_diverge` |
| Caller exposure == known share (HARD) | **PASS** | `test_caller_exposure_equals_known_share` |
| No person holds both roles in one game | **PASS** | `test_no_person_holds_both_roles_in_one_game` |
| Exposure never exceeds 1.0 | **PASS** | `test_exposure_never_exceeds_one` |
| McDaniel EXACT (68 games, exposure 1.0, 0 HC-ctx) | **PASS** | `test_mcdaniel_caller_games_and_exposure` |
| McVay EXACT (181 through 2025, 198 all-time, 0 HC-ctx) | **PASS** | `test_mcvay_unified_across_titles` |
| Harbaugh 2026 LAC HC-context exposure 1.0 | **PASS** | `test_harbaugh_2026_routing` |
| Rams 2026 caller-only, exposure 1.0 | **PASS** | `test_rams_2026_routing` |
| Snapshot carries no realized outcome | **PASS** | `test_preseason_snapshot_carries_no_realized_outcome` |
| Unknown identity emits NA, not 0 | **PASS** | `test_unavailable_identity_is_na_not_zero` |
| Post-cutoff source confers no eligibility | **PASS** | `test_post_cutoff_attributing_source_never_clears_a_cutoff` |

### Still FAILING / not migrated (unchanged from the original matrix)

- **`build_arm3_effects.py`** — still carries all five original defects (game-weighted reliability,
  midseason caller attribution, QB identity/season controls, time-blocked ridge selection, boundary
  alpha). NOT repaired. No Arm 3 result may be quoted.
- **`build_coach_features.py`** — still joins on season+team and still uses the PRE-v3.3 metric
  names `off_points_per_game` / `points_per_drive`. Not migrated to segment-level, caller-first
  inputs. Its header now records the correct v3.4 hash and the rename, but the code is unchanged.
- **Arms 1–5 feature families** — all still FAIL; none consume the caller-first exposure blocks or
  the point-in-time snapshot.

### Blocking finding

Point-in-time caller coverage on the outer window is **39.1% (100/256)**, with 2017/2020/2021/2022/
2025 at exactly **0%**. See prereg v3.4 §6. The play-caller channel may be underpowered or
unidentifiable on the available archive; a null coaching arm must not be read as evidence about
coaching.

---

## PHASE 1D — game-based reliability (2026-07-29): **PASSED**

Artifact `data/coach_reliability.csv` — 6,340 rows at (person_id, target_season, role) grain,
225 persons, target seasons 2000–2026. Lineage `data/coach_reliability_lineage.csv` traces every
count to game_ids. **`tests/test_reliability_phase1d.py` — 22 tests; suite total 55, all passing.**

| requirement | status | evidence |
|---|---|---|
| Three semantically separate counts | **PASS** | roles `caller` / `hc_resume` / `noncalling_hc_context` |
| hc_context uses the FROZEN exposure rule | **PASS** | delegates to `build_exposure.exposure_long`, not re-derived |
| reliability = g/(g+32) | **PASS** | `test_reliability_formula_is_exactly_g_over_g_plus_32` (1 ULP CSV tolerance) |
| Counts are GAMES not seasons | **PASS** | `test_counts_are_games_not_seasons`; 16- and 17-game test |
| Strict timing (max season < Y) | **PASS** | `_assert_timing` + `test_no_row_uses_games_from_its_own_or_a_future_season` |
| McDaniel 68, reliability 0.68 | **PASS** | exact |
| McVay 181, reliability 181/213 | **PASS** | exact; lineage shows LA 149 + WAS 32 unified |
| HC==caller: 1 caller, 1 resume, 0 context | **PASS** | McDaniel 68/68/0 |
| Delegating HC splits correctly | **PASS** | Reid 437 resume = 192 called + 245 context |
| ~~Unknown caller → HC context retained~~ | **WITHDRAWN v3.6** — see the v3.6 section below. This row asserted the defect, not a requirement. | superseded by `test_unknown_caller_games_activate_NEITHER_identity_block` |
| Identity portability across teams/titles | **PASS** | 2 tests |
| Midseason split across a bye | **PASS** | 8 + 8 = 16, not 9 + 8 |
| HC change / HC takes over calling | **PASS** | 2 tests |
| No playoff games | **PASS** | max team-season games ≤ 17 |
| No duplicate game_ids in a role block | **PASS** | `_assert_no_double_counting` + lineage test |
| Per-team-season reconciliation | **PASS** | `test_every_historical_team_season_reconciles` |
| unknown-identity vs known-no-history SEPARATE | **PASS** | `routing_flags()`; outer: 104 unknown-identity, 28 known-no-history, mutually exclusive |
| A/B routing NOT mixed into historical counts | **PASS** | module is person-level only; routing applied downstream |

### Finding recorded during 1D — left-censoring asymmetry

`actual_play_caller.csv` starts **2014**; `head_coach_games.csv` starts **1999**. Caller history is
therefore left-censored 15 years later than HC-résumé history. Andy Reid, who had called plays since
1999: entering 2015 → caller 16 vs hc_resume 256 (reliability 0.33 vs 0.89); entering 2026 →
caller 192. **His caller count grows with calendar time purely because the window widens**, so
`caller_reliability` is confounded with target season and early-window rows look unreliable
regardless of real experience.

Not an arithmetic error — a data-coverage property — but it must not reach a model silently. Rows
now carry `history_window_start`, `observable_prior_seasons` and `history_left_censored`.
**Detection is incomplete by construction:** a pre-2014 OC/play-caller who was never a head coach
cannot be detected at all, so absence of the flag is NOT proof a count is complete. Any use of
caller reliability should be within-target-season comparable (or explicitly censoring-aware).

---

## PHASE 1D — v3.6 CORRECTION (2026-07-29): unknown-caller contamination removed

**Phase 1D was reported PASSED prematurely.** The Reid example exposed that the frozen
`ctx_mask = ~same` rule credited every UNKNOWN-caller game to the head coach's "delegated offense"
block, because `same` is False both when a distinct known person called and when the caller is
unknown.

| Andy Reid entering 2026 | v3.5 reported | v3.6 actual |
|---|---|---|
| `hc_resume` | 437 | 437 |
| known self-called | 192 | 192 |
| **known delegated** | **245 (claimed)** | **5** (Matt Nagy, KC 2017) |
| **unknown caller** | folded into the 245 | **240** (all 1999–2013) |

The Phase 1D report's "437 = 192 called + 245 delegated" was **false**. Corrected rule:
`hc_context_mask = known & (hc != caller)`; unknown games activate **neither** identity block.

| requirement | status | evidence |
|---|---|---|
| Unknown activates neither block | **PASS** | `test_unknown_caller_games_activate_NEITHER_identity_block` |
| HC résumé unaffected by unknown | **PASS** | same test (17 résumé games retained) |
| 2-known/2-unknown → 0.5 / 0.5 / 0.5 | **PASS** | `test_four_games_two_known_two_unknown_shares` |
| All-unknown → 0 caller, 0 context, share 1 | **PASS** | `test_all_callers_unknown_gives_zero_to_both_blocks` |
| Shares reconcile per team-season | **PASS** | `test_exposure_shares_reconcile_per_team_season` |
| `hc_resume = self + delegated + unknown` | **PASS** | asserted in `_assert_reconciles` |
| Reid 192 / 5 / 240 | **PASS** | `test_reid_decomposition_is_192_plus_5_plus_240` |
| Reid's 5 route to Nagy 2017 | **PASS** | `test_reid_delegated_games_route_to_nagy_in_2017` |
| McDaniel 68/68/0/0, McVay 181/149/0/0 | **PASS** | `test_mcvay_and_mcdaniel_have_zero_context_and_zero_unknown` |
| Target-season unknown assumes neither | **PASS** | `test_target_season_unknown_caller_assumes_neither_delegation_nor_self_call` |
| Confirmatory feature policy enforced | **PASS** | `test_feature_policy_lists_are_disjoint` (`test_reliability_phase1d.py`) |

**Scale of the contamination.** Mean unknown-caller share across 893 team-seasons is **0.561** —
most historical games have no attributed caller, because the caller table starts in 2014 while
`head_coach_games` starts in 1999. Entering 2026 the HC-context block totals **3,549** person-games
while the newly separated unknown block totals **8,020**. Under the old rule those 8,020 games were
all being read as delegated offense.

**Reliability semantics (v3.6):** `observed_prior_games / (observed_prior_games + 32)` is confidence
in the OBSERVED sample, not career experience. Nothing is imputed and the caller table is not
extended. Fields renamed `observed_*`; `history_left_censored` / `observable_prior_seasons` /
`observed_history_start` are **audit-only and forbidden as model features** (calendar proxies).
Raw `observed_games_log` is excluded from confirmatory quality use. A **rolling-three-only** caller
-quality sensitivity is pre-registered.

**62 registered tests pass.** Phase 1D PASSES under the corrected rule.

---

## PHASE 1D.1 + 1E/1F PREFIT (v3.7, 2026-07-29)

### 1D.1 — requirement to code, with covering tests

| requirement | code | test | status |
|---|---|---|---|
| `observed_reliability` is PRECISION_ONLY, not a predictor | `build_reliability.PRECISION_ONLY` | `test_observed_reliability_is_precision_only_not_a_predictor` | **PASS** |
| Reliability leaks the forbidden count (demonstrated) | — | `test_reliability_is_a_bijection_of_the_forbidden_count` (recovers g = 32r/(1−r)) | **PASS** |
| Four disjoint policy lists | `MODEL_PREDICTORS` / `PRECISION_ONLY` / `ROUTING_ONLY` / `AUDIT_ONLY` | `test_feature_policy_lists_are_disjoint` | **PASS** |
| Guard inspects the ACTUAL matrix | `assert_design_matrix_is_clean` | `test_design_matrix_guard_rejects_forbidden_columns`, `test_stage2_design_matrix_passes_the_guard` | **PASS** |
| Canonical schema, no legacy aliases | `CANONICAL_SCHEMA`, `LEGACY_ALIASES_REMOVED` | `test_canonical_schema_has_no_legacy_aliases` | **PASS** |
| One writer per artifact | ownership block in `build_exposure.py` | `test_each_protected_artifact_has_exactly_one_writer` | **PASS** |
| `build_exposure` writes only 3 files | — | `test_build_exposure_writes_only_its_three_artifacts` | **PASS** |
| Print message matches what is written | — | `test_build_exposure_print_message_matches_what_it_writes` | **PASS** |
| Withdrawn unknown-caller rule purged from live docs | `PROPOSED_DESIGNS_A_B_C.md`, this file | manual + superseded-history blocks | **PASS** |
| Double rebuild byte-identical | — | verified: all 9 artifacts identical across two full rebuilds | **PASS** |

### 1E/1F — implemented, NOT executed on real outcomes

| requirement | code | test | status |
|---|---|---|---|
| Same-season centering, zero league mean | `relative_epa_play` | `test_same_season_centering_gives_zero_league_mean` | **PASS** |
| League mean is normalization, not a predictor | — | `test_league_mean_is_outcome_normalization_not_a_predictor` | **PASS** |
| No validation/outer season in training | `expanding_folds` | `test_no_validation_or_outer_season_reaches_training`, `test_folds_are_expanding_and_never_train_on_the_future` | **PASS** |
| Frozen minimums, no silent relaxation | `expanding_folds` | `test_frozen_minimums_return_no_folds_rather_than_shrinking` | **PASS** |
| Equal per-season tuning weight | `season_averaged_mse` | `test_each_validation_season_gets_equal_tuning_weight` | **PASS** |
| Preprocessing learns only from inner-training | `Stage1Preprocessor` | `test_preprocessing_learns_only_from_inner_training_rows` | **PASS** |
| MISSING_QB / UNSEEN_QB routing, zero prior | `Stage1Preprocessor.transform` | `test_missing_and_unseen_qb_routing` | **PASS** |
| Binary indicators not standardized | — | `test_binary_columns_are_not_standardized` | **PASS** |
| Exposure weights match game shares, in [0,1] | `stage2_design` | `test_exposure_weights_match_supplied_game_shares` | **PASS** |
| HC==caller → one caller contribution, no context | — | `test_hc_equal_caller_gives_one_caller_contribution_and_no_context` | **PASS** |
| Unknown → zero in both blocks | — | `test_unknown_caller_games_contribute_zero_to_both_blocks` | **PASS** |
| Stage 2 uses seasons < Y only | — | `test_stage2_design_excludes_outer_and_future_seasons` | **PASS** |
| Block ridge matches closed form | `block_ridge` | `test_block_ridge_matches_closed_form_small_example` | **PASS** |
| Intercept unpenalized | — | `test_intercept_is_unpenalized` | **PASS** |
| `alpha_caller` does not move the HC penalty | — | `test_changing_alpha_caller_does_not_alter_the_hc_penalty` | **PASS** |
| Separate penalties, not one shared | — | `test_a_single_shared_penalty_is_not_used` | **PASS** |
| Boundary extension + tie-breaking | `select_alpha` | 5 tests incl. `test_exact_ties_resolve_toward_the_larger_alpha`, `test_grid_keeps_half_decade_spacing_after_extension` | **PASS** |
| Candidates + fold losses persisted | — | `test_all_candidates_and_fold_losses_are_persisted` | **PASS** |
| Stage 1/Stage 2 penalties reported separately | — | `test_stage1_and_stage2_penalties_are_reported_separately` | **PASS** |
| Reliability/count/censoring barred from X | — | `test_reliability_count_and_censoring_fields_cannot_enter_X` | **PASS** |

**97 registered tests pass.**

### UNINTERPRETABLE — do not read

`data/arm3_residuals.csv` (`2ba6c51769f8dbb85c27c603b2dc93f2`) and `data/arm3_effects.csv`
(`56b47dab2c0e27689ee260deb9e29c4b`) are the PRELIMINARY artifacts fit before v3.2. They predate the
bye-week count fix, the caller-first collapse, the drive-category fix, the unknown-caller correction
and the entire Stage 1/Stage 2 redesign. They are retained untouched for provenance only and **no
value in them may be quoted**.

### Unresolved design points

1. **Stage 1 feature availability is unverified.** The 17 frozen predictors are named in the prereg
   but no builder has been confirmed to emit all of them (`ret_skill_fantasy_share`,
   `vacated_*_share`, `prior_ol_sack_rate` in particular). Must be checked before any real fit.
2. **Left-censoring remains uncorrected** (AUDIT_TODO 11), now contained by policy rather than fixed:
   caller history starts 2014, HC résumé 1999.
3. **Stage 2 identity coverage under Design A is 59.4%**, so the caller block is sparse on the outer
   window; the interaction between that sparsity and `alpha_caller` selection is not yet characterised.
4. **No decision on whether `no_prior_history` is retained** as a labelled indicator in the final
   confirmatory specification, or used only for routing.

---

## v3.8 — CORRECTIONS TO STALE MATRIX STATEMENTS (2026-07-29)

Superseding earlier rows in this file:

| stale statement | corrected |
|---|---|
| "The 17 Stage 1 predictors are NAMED but no builder confirmed to emit them" | **WRONG.** `build_personnel_controls.py` emits all 17 and `personnel_controls.csv` contains them. The defect was that several were computed incorrectly, not absent. |
| "Stage 2 caller block sparse at 59.4% coverage" | **WRONG FIGURE.** 59.4% is point-in-time Design A coverage. Stage 2 trains on RETROSPECTIVE actual-caller exposure: **244/256** outer, **116/128** prior-building. |
| "Phase 1E/1F implemented" | **OVERSTATED.** Helpers only until v3.8; the pipeline now lives in `run_arm3_v38.py`. |
| data-layer test count | **141** (was 97, then 119) |
| `no_prior_history` status | **ROUTING-ONLY** in Stage 1/Stage 2; cannot enter X; player-arm use deferred |
| old drive + returning-share definitions | **SUPERSEDED** — see v3.8 §1–§3 |

## v3.8 — STAGE 1 / STAGE 2 REQUIREMENT TO CODE

| # | requirement | generating function | input artifact / columns | timing rule | inner-CV | missing values | output | covering test | status |
|---|---|---|---|---|---|---|---|---|---|
| S1-1 | unique (season, team) keys | `load_stage1_inputs` | panel + controls | — | — | raises | — | `test_duplicate_season_team_keys_are_rejected` | PASS |
| S1-2 | exact 17-predictor allowlist | `load_stage1_inputs` | `STAGE1_PREDICTORS` | — | — | raises on missing | — | `test_artifact_has_all_17_canonical_predictors` | PASS |
| S1-3 | retired drive names absent | `load_stage1_inputs` | `DD.RETIRED_NAMES` | — | — | raises | — | `test_retired_drive_names_are_rejected_at_load` | PASS |
| S1-4 | same-season centering | `relative_epa_play` | `epa_play` by season | within completed season only | — | — | `relative_epa_play` | `test_same_season_centering_gives_zero_league_mean`, `test_stage1_residual_identity_holds` | PASS |
| S1-5 | train only on seasons < S | `run_stage1` | merged frame | strict `<` | expanding | — | residuals | `test_stage1_training_excludes_target_and_future_seasons` | PASS |
| S1-6 | frozen minimums 5/3 | `expanding_folds` | season list | — | skip if unmet | — | — | `test_frozen_stage1_minimums_skip_targets_without_enough_history` | PASS |
| S1-7 | preprocessing refit per inner fold | `_fit_predict` | train rows | per fold | per fold | train-only medians | — | `test_preprocessing_learns_only_from_inner_training_rows` | PASS |
| S1-8 | season-averaged validation MSE | `season_averaged_mse` | fold errors | — | equal season weight | — | fold losses | `test_each_validation_season_gets_equal_tuning_weight` | PASS |
| S1-9 | 1-D boundary protocol | `select_alpha` | grid | — | — | — | tuning | 5 alpha tests | PASS |
| S1-10 | final fit on all seasons < S | `run_stage1` | train frame | strict `<` | — | — | schema JSON | `test_final_preprocessing_uses_all_and_only_seasons_before_S` | PASS |
| S1-11 | target-season QB never in vocab | `Stage1Preprocessor` | `prior_qb_id` | — | train-only | UNSEEN_QB / MISSING_QB | schema | `test_target_season_qb_identities_never_enter_the_vocabulary`, `test_missing_and_unseen_qb_routing` | PASS |
| S1-12 | all candidates + fold losses persisted | `run_stage1` | — | — | — | — | tuning + fold artifacts | `test_every_candidate_and_fold_loss_reaches_the_tuning_artifacts` | PASS |
| S2-1 | residuals from seasons < Y | `run_stage2` | Stage 1 residuals | strict `<` | expanding | — | effects | `test_stage2_end_to_end_produces_effects_and_diagnostics` | PASS |
| S2-2 | row universe = residual panel | `stage2_design(row_universe=)` | residual panel | — | — | zero-identity rows KEPT | design | `test_stage2_retains_residual_rows_with_zero_identity_exposure` | PASS |
| S2-3 | vocabularies learned inner-train only | `run_stage2` cache | exposure | strict `<` | per fold | unseen -> zero | — | `test_stage2_vocabularies_use_inner_training_data_only`, `test_inner_validation_unseen_coach_routes_to_zero` | PASS |
| S2-4 | separate caller/context penalties | `block_ridge` | design blocks | — | — | — | effects | `test_changing_alpha_caller_does_not_alter_the_hc_penalty` | PASS |
| S2-5 | joint 2-D selection | `select_alpha_pair` | grid x grid | — | season-averaged | — | tuning | `test_joint_selection_finds_the_hand_calculated_best_pair` | PASS |
| S2-6 | frozen 3-step tie rule | `select_alpha_pair` | — | — | — | — | tuning | `test_joint_exact_ties_follow_the_frozen_three_step_rule` | PASS |
| S2-7 | independent per-block boundary expansion | `select_alpha_pair` | — | — | — | — | boundary status | `test_each_block_expands_its_boundary_independently`, `test_both_boundaries_can_expand_in_the_same_iteration`, `test_opposite_directions_expand_independently` | PASS |
| S2-8 | complete pooling marks one block only | `select_alpha_pair` | — | — | — | — | `block_boundary_status` | `test_persistent_upper_boundary_marks_only_the_affected_block` | PASS |
| S2-9 | forbidden fields barred from X | `assert_design_matrix_is_clean` | policy lists | — | — | — | — | `test_forbidden_fields_cannot_enter_stage1_or_stage2_X`, `test_no_prior_history_is_routing_only` | PASS |
| S2-10 | deterministic rebuild | `run_stage1`/`run_stage2` | — | — | — | — | all v38 artifacts | `test_two_identical_builds_are_byte_identical` | PASS |

**Orchestration rows are marked PASS only because the end-to-end synthetic tests call
`run_arm3_v38.run_stage1` / `run_stage2` — the same entry points the real build uses.**

---

## v3.9 — CORRECTIONS TO STALE MATRIX STATEMENTS (2026-07-29)

| stale statement | corrected |
|---|---|
| "Arms 1–5 feature families — all still FAIL; none consume the caller-first exposure blocks or the point-in-time snapshot" | **CLOSED.** `build_arm_features_v39.py` consumes the point-in-time snapshot (Design A) and the segment ledger, and emits every Arm HC/1–5 family. `build_coach_features.py` is NOT repaired and is NOT used by v3.9. |
| "Arm 4 position-relevant subsetting NOT IMPLEMENTED YET — the per-position subset happens at arm assembly, which does not exist" | **CLOSED.** Arm assembly exists; `arm_feature_manifest_v39.json` pins the ordered per-position lists. |
| "Arm 5 NOT BUILT — arm assembly does not exist yet" | **CLOSED** and its exclusion contract is asserted, not merely documented. |
| Arms 1/2/3/5 include `*_prior_games_log`, `*_reliability`, `*_no_prior_history` | **WITHDRAWN by v3.9 §1.** Those columns are forbidden as primary player features. Reliability survives only as the shrinkage weight inside a historical estimate. |
| "point-in-time caller coverage on the outer window is 39.1% (100/256)" | **SUPERSEDED.** That was the v3.4 figure. After the v3.5 as-of rule it is **152/256 = 59.4%**, reproduced by the v3.9 builder. |
| Stage 1/Stage 2 inner CV is leave-one-season-out | **WRONG for the player arms.** v3.9 uses EXPANDING forward chaining; LOSO would train a fold on seasons after its validation season. |
| test count | **236** (was 141) |

## PHASE 2A — POINT-IN-TIME REPRESENTATIONS (v3.9): REQUIREMENT TO CODE

Artifacts — **exactly five, and no more**: `team_coach_features_design_a_v39.csv` (416 rows),
`team_coach_features_design_b_oracle_v39.csv` (416), `arm_feature_manifest_v39.json`,
`arm_feature_coverage_v39.csv` (728 rows, (design, arm, season, identity_state) grain),
`arm_feature_lineage_v39.csv` (51 feature-definition + 832 identity-routing rows).
The head-coach win ledger is **derived in memory** on every build from the repo-owned frozen snapshot
`fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet`, and is **never cached** — not in
the repo and not in a scratch directory. (RETIRED: v3.9a's `COACH_V39_SCRATCH` cache — WITHDRAWN,
because a cache outside the repo made the build non-hermetic.)
Representation names are `ARM_0`, `ARM_HC`, `ARM_1`…`ARM_5`.
Tests: `tests/test_arm_features_v39.py` — **88**.

| # | requirement | generating function | input artifact / columns | timing rule | aggregation grain | missing-value rule | covering test | status |
|---|---|---|---|---|---|---|---|---|
| F-1 | forbidden metadata can never be a primary feature | `assert_no_forbidden_features` | emitted column list + every manifest arm | — | column | n/a | `test_no_manifest_arm_carries_forbidden_metadata`, `test_reliability_counts_and_censoring_can_never_be_features` | PASS |
| F-2 | reliability only as an internal shrinkage weight | `_shrink`, `_window_aggregate` | `pbp_games` | — | (person, window, metric) | 0 games -> exactly the prior | `test_synthetic_ties_count_half_a_win_and_stay_in_the_denominator` | PASS |
| F-3 | Arm 3 effects are never shrunk twice | `route_arm3` | `arm3_stage2_effects_v38.csv` | effects fit on residuals `< Y` | (person, role) | absent -> 0 prior | `test_lineage_covers_every_emitted_feature_exactly_once` | PASS |
| F-4 | ARM_HC: REG only, no playoffs, tie = 0.5 | `hc_game_results`, `hc_history` | nflverse schedules `result` | seasons `< Y` | game | unplayed games DROPPED, never 0 | `test_synthetic_ties_count_half_a_win_and_stay_in_the_denominator`, `test_synthetic_hc_change_and_win_pct_shrinkage` | PASS |
| F-5 | ARM 1 composite needs >=3 of 5 rank components | `off_rank_composite` (upstream) | `segment_offense.csv` | seasons `< Y` | segment | <3 -> NaN -> 0.500 prior | `test_manifest_pins_exact_ordered_features_by_position_and_arm` | PASS |
| F-6 | ARM 2 keeps six efficiency dimensions separate | `EFFICIENCY_STEMS` | `z_*` columns | seasons `< Y` | segment | 0 games -> 0.000 | `test_manifest_pins_exact_ordered_features_by_position_and_arm` | PASS |
| F-7 | ARM 3 routing (4 cases) | `route_arm3` | effects table | entering `Y` | team-season | 0 prior | 4 `test_route_arm3_*` tests | PASS |
| F-8 | ARM 4 is position-specific | `arm4_features` | `SCHEME_STEMS` | seasons `< Y` | segment | 0.000 | `test_arm4_is_position_specific_and_not_interchangeable` | PASS |
| F-9 | ARM 5 excludes Arm 1 win/rank + Arm 2 efficiency + sample-size metadata | `arm5_features` + `manifest` assertions | — | — | — | — | `test_arm5_excludes_arm1_win_rank_and_arm2_efficiency` | PASS |
| F-10 | rush tendency == exact negation of pass tendency | `DERIVED_NEGATION` | `z_neutral_pass_rate` | — | segment | inherited | `test_rush_tendency_is_the_exact_negation_of_pass_tendency` | PASS |
| F-11 | segment attribution uses only each caller's own games | `_window_aggregate` | `segment_offense.csv` + `pbp_games` | week range inside the sourced segment | segment | per-metric games | `test_synthetic_midseason_split_attributes_only_each_callers_own_games` | PASS |
| F-12 | `pbp_games` == canonical `n_games_attributed` | `caller_segments` | both columns | — | segment | raises | asserted at load | PASS |
| F-13 | strict timing: season-`Y` games never enter | `caller_history` | segments | strict `<` | segment | — | `test_synthetic_strict_timing_target_season_games_never_enter` | PASS |
| F-14 | ~~Design A evidence gate: source upper bound <= `Y` cutoff~~ | | | | | | | **WITHDRAWN v3.9b — replaced by F-14a/b/c below. This was never the primary history requirement after v3.9b and the row is retained only so the change is traceable.** |
| F-14a | the TARGET-season expected caller is evidence-gated at the frozen preseason cutoff | `target_identities` (Design A), `preseason_staff_snapshot.eligible_at_cutoff` | snapshot | pre-cutoff evidence only | team-season | unknown -> frozen neutral VALUE | `test_design_a_outer_caller_coverage_is_152_of_256`, `test_missing_or_inferred_dates_are_never_eligible` | PASS |
| F-14b | historical caller PERFORMANCE and prior-season caller CONTINUITY use source seasons `< Y` from the FULL retrospective ledger — **no source-date gate** | `caller_history(gated=False)`, `caller_openers_closers(cutoff=None)`, `PRIMARY_TIMING_RULE` | `segment_offense.csv` | strictly prior only | segment | 0 games -> exactly the prior | `test_the_primary_history_policy_is_ungated`, `test_a_late_published_source_no_longer_suppresses_earlier_history`, `test_history_remains_STRICTLY_PRIOR_under_the_ungated_policy`, `test_every_caller_history_lineage_row_carries_the_primary_timing_rule` | PASS |
| F-14c | the retired source-date-gated history rule is DIAGNOSTIC-ONLY, nonselectable, unpersisted, and cannot rescue the primary result | `strict_gate_sensitivity`, `SENSITIVITY_LABEL`, `strict_source_date_gate_would_exclude` | — | — | — | — | `test_the_strict_gate_survives_only_as_an_in_memory_sensitivity`, `test_the_sensitivity_is_never_written_to_a_repo_artifact`, `test_the_retired_gate_stays_present_as_a_labelled_diagnostic` | PASS |
| F-15 | unknown caller -> frozen neutral VALUE, not NaN | `build_features` | — | — | team-season | neutral table | `test_unknown_caller_rows_carry_the_frozen_neutral_values`, `test_unknown_is_a_VALUE_not_a_missingness_pattern` | PASS |
| F-16 | identified caller with no history also gets priors, but stays distinguishable from unknown | `build_features` | — | — | team-season | priors | `test_known_caller_with_no_prior_history_also_receives_league_priors` | PASS |
| F-17 | identity portable across teams and titles | `caller_history` | `person_id` | — | person | — | `test_caller_identity_is_portable_across_teams_and_titles`, `test_mcdaniel_carries_his_miami_head_coach_games_into_a_coordinator_role` | PASS |
| F-18 | tenure bridges a franchise relocation | `tenure` | canonicalised team codes | prior consecutive seasons | (team, person) | None -> 0.0 | `test_tenure_bridges_a_franchise_relocation`, `test_tenure_counts_only_consecutive_prior_seasons` | PASS |
| F-19 | Design A never reads a retrospective identity field | `target_identities` | snapshot only | — | — | — | `test_design_a_never_reads_a_retrospective_identity_field`, `test_only_the_design_b_branch_reads_the_retrospective_ledger`, `test_the_gated_snapshot_itself_carries_no_retrospective_answer` | PASS |
| F-20 | Design B labelled nondeployable; Design C unauthorized | `DESIGN_LABEL`, `target_identities` | — | — | — | — | `test_design_b_is_labelled_nondeployable`, `test_design_c_is_not_authorized` | PASS |
| F-21 | Arm 3 zero before target 2018, disclosed | `arm3_lookup` | effects table | — | team-season | 0 | `test_arm3_effects_are_zero_before_target_season_2018` | PASS |
| F-22 | coverage 152/256 (A) and 244/256 (B) on the outer window | `coverage` | — | — | (design, arm, season) | — | `test_design_a_outer_caller_coverage_is_152_of_256`, `test_design_b_outer_caller_coverage_is_the_retrospective_244_of_256` | PASS |
| F-23 | 2026 LAC / Rams / KC routing | `routing_report` | — | — | team-season | — | 3 routing tests + `test_arm3_does_not_support_a_chargers_upgrade` | PASS |
| F-24 | feature construction reads NO fantasy outcome | — | — | — | — | — | `test_feature_construction_never_touches_a_fantasy_outcome` | PASS |
| F-25 | deterministic rebuild; lineage covers every feature | `build_features`, `lineage` | — | — | — | — | `test_two_identical_builds_are_byte_identical`, `test_lineage_covers_every_emitted_feature_exactly_once` | PASS |
| F-26 | inherited Phase-1 artifacts untouched | — | — | — | — | — | `test_upstream_phase1_artifacts_are_unchanged` | PASS |
| F-27 | no split caller inherits full-season offense | `_window_aggregate` | `segment_offense.csv` | week range | segment | — | `test_no_split_caller_inherits_full_team_season_offense` (>=15 splits checked) | PASS |
| F-28 | segment game membership reconciles with the canonical ledger | `caller_segments` | `pbp_games` vs `n_games_attributed` | — | segment + team-season total | raises | `test_segment_game_membership_reconciles_with_the_canonical_ledger` | PASS |
| F-29 | row-level routing lineage proves timing, membership and fallback | `routing_lineage` | feature frames | strict `<` asserted per row | (design, season, team) | reason recorded | `test_routing_lineage_proves_strict_timing_and_membership`, `test_lineage_records_the_target_identity_gate_and_the_shared_history_rule` | PASS |
| F-30 | retired drive names rejected in features, manifests AND lineage | `assert_no_retired_drive_names` | `DD.RETIRED_NAMES` minus canonical | — | column / text | raises | covered by every manifest assertion + `lineage()` guard | PASS |
| F-31 | identity states decompose the aggregate; rates emitted | `coverage`, `identity_state` | — | — | (design, arm, season, state) | — | `test_identity_states_decompose_the_aggregate_exactly`, `test_coverage_reports_rates_as_well_as_counts` | PASS |
| F-32 | exactly five v3.9 artifacts; HC ledger derived in memory and never cached | `OWNED_ARTIFACTS`, `hc_game_results` | — | — | — | — | `test_no_unauthorized_v39_artifact_exists_on_disk`, `test_the_head_coach_win_ledger_is_derived_in_memory_not_cached`, `test_build_arm_features_v39_writes_only_the_five_authorized_artifacts` | PASS |

## PHASE 2B — EVALUATION HARNESS (v3.9): REQUIREMENT TO CODE

`run_coach_projection_experiment_v39.py`. Tests: `tests/test_coach_projection_harness_v39.py` — **246**.
**SYNTHETIC TARGETS ONLY.** The real-fit gate is default-closed and DOUBLE-LOCKED: both
`REAL_FIT_AUTHORIZED = True` and
`COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT` are required. Both are
shut. **The module writes nothing at all.**

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| H-1 | expanding folds, `inner training < validation < outer target` | `expanding_inner_folds` | `test_outer_2018_inner_folds_are_exactly_the_frozen_pair`, `test_folds_are_expanding_and_never_train_on_their_own_or_a_later_season` | PASS |
| H-2 | frozen minimums 2/2, skip rather than relax | `expanding_inner_folds` | `test_frozen_inner_minimums_skip_a_target_without_enough_history` | PASS |
| H-3 | outer fit never touches its own test season | `outer_predictions` | `test_outer_fit_never_touches_its_own_test_season` | PASS |
| H-4 | Arm 0 read from bundle + cross-checked against builder code | `arm0_definition`, `builder_pools` | `test_arm0_is_read_from_the_bundle_and_matches_the_builder_pool` | PASS |
| H-5 | production contract recorded (families, params, categorical, weights, NaN, target, PPG/season-total) | `audit_production` | `test_audit_records_the_full_production_contract` | PASS |
| H-6 | QB rookie path absent and recorded | `MISSING_BUNDLES` | `test_qb_rookie_path_is_absent_and_recorded` | PASS |
| H-7 | identical player rows across arms | `outer_predictions`, `inner_scores` | `test_identical_player_rows_across_every_arm`, `test_attach_coach_features_preserves_the_row_count`, `test_a_player_row_without_a_coaching_bundle_raises` | PASS |
| H-8 | cohorts defined by the Arm 0 prediction | `baseline_cohort_mask` | `test_cohorts_are_defined_by_the_arm0_prediction_only`, `test_cohort_sizes_are_the_frozen_draft_relevant_ones`, `test_cohort_is_computed_per_season_and_position` | PASS |
| H-9 | 0.25 full-panel eligibility tolerance | `select_arm` | `test_an_arm_that_regresses_the_full_panel_is_ineligible` | PASS |
| H-10 | below 1% improvement selects Arm 0 | `select_arm` | `test_improvement_below_one_percent_selects_arm0` | PASS |
| H-11 | 0.25 tie band -> fewer added features, then frozen arm order | `select_arm` | `test_tie_band_prefers_the_arm_with_fewer_added_features`, `test_a_final_tie_breaks_on_the_frozen_arm_order` | PASS |
| H-12 | ARM_HC is selectable | `select_arm` | `test_arm_hc_can_win_selection` | PASS |
| H-13 | oracle excluded from primary selection, labelled everywhere | `run_experiment` | `test_oracle_design_never_enters_selection`, `test_every_oracle_row_carries_the_nondeployable_label`, `test_selection_is_identical_whether_or_not_the_oracle_is_supplied` | PASS |
| H-14 | clustered resampling units are WHOLE clusters, both frozen units | `clustered_bootstrap` | `test_bootstrap_resamples_whole_clusters_not_rows`, `test_both_frozen_cluster_units_are_available` | PASS |
| H-15 | 20,000 draws, seed 20260728, reproducible | `clustered_bootstrap` | `test_bootstrap_is_reproducible_under_the_frozen_seed`, `test_frozen_bootstrap_constants` | PASS |
| H-16 | Holm across the six fixed arms | `holm` | `test_holm_is_monotone_and_never_reduces_a_p_value` | PASS |
| H-17 | within-season TEAM-LEVEL permutation of complete bundles | `permute_team_bundles` | `test_permutation_moves_COMPLETE_team_bundles`, `test_permutation_stays_strictly_within_season`, `test_permutation_actually_reassigns_something`, `test_permutation_never_touches_player_rows`, `test_frozen_placebo_constants`, `test_placebo_distribution_runs_and_is_seeded` | PASS |
| H-18 | position-specific manifests reach the design matrix, appended AFTER the baseline | `attach_coach_features` | `test_position_specific_arm4_columns_reach_the_design_matrix`, `test_selected_arm_features_are_appended_after_the_baseline` | PASS |
| H-19 | real fantasy fitting is BLOCKED | `REAL_FIT_AUTHORIZED`, `assemble_real_panel` | `test_real_fit_is_blocked_by_a_default_closed_double_lock`, `test_the_wrong_env_token_does_not_unlock` | PASS |
| H-20 | no production write, and the harness writes **NOTHING** — not two artifacts, not one (the "two outcome-free repo artifacts" contract is **RETIRED**; v3.9 authorises five artifacts and the BUILDER owns all five) | `assert_no_production_writes` | `test_no_production_artifact_changes`, `test_the_harness_writes_nothing_at_all`, `test_the_harness_writes_no_repo_artifact_at_all` | PASS |
| H-21 | deterministic artifacts and results | `audit_production`, `experiment_spec`, `run_experiment` | `test_audit_and_spec_artifacts_are_deterministic`, `test_experiment_is_deterministic_on_identical_inputs`, `test_spec_pins_every_frozen_constant` | PASS |
| H-22 | Arm 3 unavailable in the outer-2018 inner folds, stated | — | `test_arm3_is_structurally_unavailable_in_the_outer_2018_inner_folds` | PASS |
| H-23 | real fit blocked by a DEFAULT-CLOSED double lock; neither lock alone opens it | `real_fit_is_unlocked`, `require_real_fit_authorization` | `test_real_fit_is_blocked_by_a_default_closed_double_lock`, `test_the_wrong_env_token_does_not_unlock` | PASS |
| H-24 | neither v3.9 module has an executable path to a real fantasy outcome. The success detail is pinned verbatim: `both v3.9 modules satisfy the frozen structural no-outcome contract C1-C7 + C4b (scope, executable-only, no banned callee, no banned token in any executable string, no reading through an exemption, sealed entry point, single False lock, no environment write)`. C5/C6/C7 share ONE recursive binding-target walker covering Name, tuple/list/starred destructuring, Assign/AnnAssign/AugAssign/NamedExpr/Delete, For/AsyncFor, With/AsyncWith, ExceptHandler, match captures, comprehensions, def/class and import aliases. The contract is PRODUCTION logic in `no_real_outcome_access()`; the tests call it and no longer own a parallel AST walk. | `no_real_outcome_access` | `test_no_real_outcome_access_passes_on_the_real_modules`, `test_THE_EXACT_CODEX_CASE_composed_path_read_is_now_detected`, `test_every_boundary_evasion_form_is_rejected` (15 forms), `test_the_sources_mapping_must_be_exactly_the_two_modules`, `test_exactly_one_module_level_false_lock_exists`, `test_the_documentation_exemption_is_void_once_the_function_gains_a_call`, `test_the_module_owns_the_banned_sets_and_the_tests_do_not_copy_them`, `test_no_v39_module_ever_CALLS_a_real_outcome_source`, `test_no_real_outcome_token_is_used_as_a_FILE_READ_OR_COLUMN_ACCESS`, `test_documenting_the_new_contract_is_still_not_crossing_it`, `test_the_boundary_IS_documented_in_both_modules` | PASS |
| H-25 | the audit scopes its no-categorical/no-weight claims to the Arm 0 family | `audit_production` | `test_audit_scopes_its_no_categorical_no_weight_claims_to_the_arm0_family` | PASS |
| H-26 | the clipping asymmetry is recorded and verified against production source | `audit_production` | `test_audit_records_the_clipping_asymmetry` | PASS |
| H-27 | the cosmetic bundle-note mismatch is recorded, not "fixed" | `audit_production` | `test_audit_flags_the_cosmetic_bundle_note_mismatch` | PASS |
| H-28 | team-season features replicate to every player row with no fan-out or divergence | `attach_coach_features` | `test_all_players_on_a_team_season_receive_one_identical_bundle` | PASS |
| H-29 | audit/spec refuse to write a repo artifact | `audit_production`, `experiment_spec` | `test_audit_and_spec_refuse_to_write_a_repo_artifact`, `test_the_harness_writes_nothing_at_all` | PASS |

### Test counts

| scope | count |
|---|---|
| inherited baseline (reproduced by ignoring the 2 new v3.9 modules and deselecting **all six** new ownership tests) | **141** |
| new v3.9 + v3.9a + v3.9b + v3.9c + v3.9d + v3.9e + v3.9f + v3.9g + v3.9i + v3.9j + v3.9k + v3.9m tests | **695** |
| **full coaching suite** (offline, empty temp dir) | **836 collected / 835 mandatory** |

## v3.9c — REVIEW REPAIRS (2026-07-29)

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| C-1 | `coverage_reconciles` is a FULL-FRAME comparison against a fresh canonical derivation, not a spot-check | `AF.compare_coverage` (regenerates with `coverage()` itself) | `test_coverage_reconciles_is_a_full_frame_comparison`, `test_THE_EXACT_CODEX_CASE_corrupting_ARM_2_known_with_history_now_fails`, `test_compare_coverage_accepts_the_real_artifact` | PASS |
| C-2 | every coverage column class is checked (counts, rates, means, arm feature counts, caller-dependence flags, league-prior rows/rates) | `AF.compare_coverage` | `test_corrupting_any_coverage_column_fails_the_semantic_check` (8 params), `test_compare_coverage_catches_a_corruption_in_any_arm_or_state` | PASS |
| C-3 | schema / key-set / duplicate corruptions are caught | `AF.compare_coverage` | `test_coverage_schema_key_and_duplicate_corruptions_are_caught` | PASS |
| C-4 | builder and preflight share ONE coverage derivation | `coverage`, `compare_coverage`, `_cov_rec` | `test_the_builder_and_the_preflight_share_one_coverage_derivation` | PASS |
| C-5 | preflight always returns its structured record and never raises | `_load`, `_need`, `v39_artifacts_readable` | `test_THE_EXACT_CODEX_CASE_deleting_design_a_returns_instead_of_raising`, `test_preflight_never_raises_for_any_single_missing_artifact` | PASS |
| C-6 | missing / malformed / schema-invalid / empty CSV and malformed JSON fail closed with `blocked by <input>` | `_csv`, `_json`, `_need` | `test_a_missing_artifact_blocks_its_dependents_without_crashing` (5 params), `test_a_malformed_csv_fails_closed` (3), `test_malformed_manifest_json_fails_closed`, `test_a_schema_invalid_csv_fails_closed`, `test_an_empty_csv_fails_closed` | PASS |
| C-7 | every caller-history / continuity lineage row carries `PRIMARY_TIMING_RULE` | `lineage`, `PRIMARY_TIMING_RULE` | `test_every_caller_history_lineage_row_carries_the_primary_timing_rule`, `test_the_two_specific_rows_codex_flagged_are_now_correct` | PASS |
| C-8 | no live lineage row asserts a source-date gate on history or openers; preflight validates it semantically | `AF.validate_lineage_policy`, `lineage_states_the_primary_policy` | `test_no_live_lineage_row_asserts_a_source_date_gate_on_history`, `test_a_reintroduced_source_date_gate_in_lineage_fails_the_semantic_check`, `test_a_reintroduced_gated_openers_note_fails_the_semantic_check` | PASS |
| C-9 | the `contribution_lineage` docstring no longer claims gate exclusions | — | `test_the_contribution_lineage_docstring_no_longer_claims_gate_exclusions` | PASS |
| C-10 | the retired rule stays present, labelled nonprimary/nonselectable | `SENSITIVITY_LABEL`, `strict_source_date_gate_would_exclude` | `test_the_retired_gate_stays_present_as_a_labelled_diagnostic` | PASS |
| C-11 | the no-real-outcome boundary is PRODUCTION logic inside C10, and the tests call it | `no_real_outcome_access`, preflight check | `test_no_real_outcome_access_passes_on_the_real_modules`, `test_c10_includes_the_no_real_outcome_check`, `test_the_tests_and_c10_share_one_definition` | PASS |
| C-12 | an injected real-outcome path is detected, in PURE SOURCE (canon untouched) | `no_real_outcome_access(sources=)` | `test_an_injected_real_outcome_path_is_detected` (5 params) | PASS |
| C-13 | documenting the boundary is not mistaken for crossing it | `_executable_tree` (docstrings stripped) | `test_documenting_the_boundary_is_not_mistaken_for_crossing_it` | PASS |
| C-14 | `assemble_real_panel` stays authorization-FIRST and unimplemented; source-level lock-opening is detected | `no_real_outcome_access` | `test_assemble_real_panel_must_stay_authorization_first_and_unimplemented`, `test_an_attempt_to_open_the_lock_in_source_is_detected` | PASS |

## v3.9e/v3.9f — REAL-OUTCOME TRANSITION (prepared; activation BLOCKED)

`assemble_real_panel_v39.py`, contract **A1–A6**, enforced as the 21st preflight check. Tests:
`tests/test_assemble_real_panel_v39.py` — **200**.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| R-1 | the outcome path is hermetic: the target comes from the repo-owned pinned weekly snapshot, never a live loader | `authorized_outcome_reader`, `grouped_season_totals` | `test_the_weekly_snapshot_is_repo_owned_and_matches_its_pin`, `test_the_weekly_snapshot_provenance_matches_the_manifest` | PASS |
| R-2 | the target reproduces production exactly: REG-only, 2014–2025, `fantasy_points + 0.5*receptions` summed per (player_id, season) | `grouped_season_totals` | `test_the_target_formula_is_the_production_one`, `test_postseason_never_enters_the_target`, `test_grouped_totals_are_REG_only_and_windowed` | PASS |
| R-3 | production zero-fill semantics: an eligible player-season with no weekly row is RETAINED with y = 0.0 | `assemble_panel_core` | `test_PRODUCTION_EQUIVALENCE_a_rostered_player_with_no_stat_row_is_kept_with_zero`, `test_no_feature_row_is_ever_silently_dropped` | PASS |
| R-4 | the veteran feature reader loads only the frozen contract, filters to 2014–2025, and its OUTPUT passes its own validator | `authorized_feature_reader` | `test_GREEN_the_authorized_feature_reader_returns_only_2014_2025_and_no_forbidden_column`, `test_the_feature_reader_output_passes_its_own_validator`, `test_RED_a_naive_full_read_of_the_fixture_violates_the_validator` | PASS |
| R-5 | accounting states are a mutually exclusive, exhaustive partition summing to the feature-row count | `assemble_panel_core` | `test_the_accounting_states_partition_the_feature_rows`, `test_the_states_cannot_overlap`, `test_a_null_player_id_is_missing_identity_only` | PASS |
| R-6 | **all SEVEN** shipped Arm 0 bundles pinned INDEPENDENTLY — ordered `feature_cols`, target, count, pool sha256 — with the pin never derived from the bundle under test | `arm0_bucket_table`, `tests/arm0_bundle_pins.py` | `test_every_shipped_bundle_matches_its_independent_pin` (7 params), `test_mutating_any_bundle_pool_fails_the_pin` (28 params: reorder/replace/add/delete × 7), `test_the_pins_cover_exactly_the_seven_shipped_buckets`, `test_a_bucket_frame_must_carry_every_bundle_feature_in_order` | PASS |
| R-7 | the three ROOKIE buckets' missing-from-season-dataset counts are DERIVED from the real CSV header and the bundles' own `feature_cols`, then asserted (RB 32/41, WR 35/44, TE 35/44). **The "NO repo-owned feature source" half is SUPERSEDED (v3.9n): Option A froze the derived matrix**, so the season dataset still lacks those features but the declared source now supplies them. | `arm0_bucket_table`, `ROOKIE_MISSING_FROM_SEASON_DATASET` | `test_the_rookie_missing_counts_are_derived_not_asserted` (3 params) | PASS |
| R-7b | the two missingness concepts stay SEPARATE and the readiness message is internally consistent — held in BOTH states: on the real ready tree, and with an injected absent rookie source | `arm0_bucket_table`, `activation_readiness` | `test_the_two_missingness_concepts_are_separate_fields`, `test_the_two_concepts_STILL_stay_apart_when_the_rookie_source_is_absent`, `test_the_readiness_message_is_internally_consistent` | PASS |
| R-8 | activation readiness FAILS CLOSED, is a layer SEPARATE from prefit integrity (in BOTH directions), and is a MANDATORY authorized-real gate alongside preflight. Readiness is now `True`; the fail-closed path is kept live by injecting an absent rookie source. | `activation_readiness`, `authorized_real_gate` | `test_activation_readiness_FAILS_CLOSED_when_the_rookie_source_is_absent`, `test_activation_readiness_is_TRUE_on_all_seven_buckets`, `test_readiness_still_FAILS_CLOSED_on_a_malformed_bundle_spec`, `test_prefit_integrity_and_activation_readiness_are_DIFFERENT_layers`, `test_the_authorized_real_gate_needs_BOTH_and_currently_REFUSES`, `test_the_gate_still_refuses_on_gate_2_when_readiness_is_blocked`, `test_the_gate_refuses_when_only_gate_1_is_clear`, `test_the_gate_refuses_when_only_gate_2_is_clear` | PASS (gate returns False, by design) |
| R-8b | **gate 1 fails closed**: a preflight result must be a dict with `all_ok is True`, `run_mode == "authorized_real"`, the exact frozen check count, `n_failed` exactly integer 0, a `checks` dict with exactly the expected names each explicitly ok, and no contradictory `failures`. A `synthetic_prefit` result can NEVER authorize a real run. | `validate_authorized_preflight` | `test_RED_a_preflight_with_only_all_ok_is_refused`, `test_RED_a_synthetic_prefit_result_can_never_authorize_a_real_run`, `test_RED_every_malformed_or_contradictory_preflight_is_refused` (12 params), `test_RED_one_check_false_while_all_ok_is_true_is_refused`, `test_RED_a_non_dict_or_empty_preflight_is_refused` (7 params), `test_RED_a_partial_or_closed_lock_state_cannot_produce_an_authorizing_preflight` (3 params), `test_GREEN_an_authorized_shaped_preflight_plus_readiness_passes` | PASS |
| R-8c | the ACTIVATION MANIFEST states both required gates, the gate-before-reader order, and readiness failure as a §7 stop condition | `V39_ACTIVATION_MANIFEST.md` §6/§7 | `test_the_manifest_states_the_required_activation_gates`, `test_the_manifest_lists_readiness_failure_as_a_stop_condition`, `test_the_manifest_still_records_the_run_as_not_executed_and_not_authorized` | PASS |
| R-8d | a permanent hermeticity scanner over the 8 stated targets, with self-probes proving each retired form is detected | `_scan_hermetic` | `test_no_live_document_makes_an_unqualified_hermeticity_claim`, `test_the_hermeticity_scanner_detects_each_retired_form` (6 params), `test_the_scanner_covers_the_eight_stated_targets` | PASS |
| R-9 | A2 rejects network capability at the IMPORT, under any alias or from-form | `assembly_module_contract` | `test_every_network_evasion_is_rejected_by_banning_the_import` (8 params), `test_the_network_check_does_not_false_positive` (4 params), `test_the_a2_limits_are_stated_not_hidden` | PASS |
| R-10 | both locks stay closed and the harness door stays sealed through this pass | `real_fit_lock_state`, `_entry_point_is_sealed` | `test_the_entry_point_is_still_sealed_and_this_pass_did_not_weaken_it`, `test_every_partial_or_closed_lock_state_refuses` (3 params) | PASS |

## v3.9a — REVIEW-REPAIR REQUIREMENTS (2026-07-29)

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| R-1 | cutoffs + HC win history build with NO network and an empty temp dir | `snapshot_schedules`, `projection_cutoffs`, `hc_game_results` | `test_cutoffs_and_hc_history_build_with_NETWORK_BLOCKED`, `test_a_full_feature_build_runs_with_NETWORK_BLOCKED` | PASS |
| R-2 | no v3.9 module reaches a live nflverse loader or imports the networked snapshot builder | — | `test_no_v39_module_calls_a_live_nflverse_loader` | PASS |
| R-3 | snapshot-derived cutoffs == the persisted `projection_cutoff` column (13/13) | `projection_cutoffs` | `test_snapshot_derived_cutoffs_match_the_persisted_artifact` | PASS |
| R-4 | no external cache; the win ledger is in-memory only | — | `test_the_builder_writes_no_cache_outside_the_five_artifacts`, `test_the_head_coach_win_ledger_is_derived_in_memory_not_cached` | PASS |
| R-5 | manifest pins the FULL ordered X per (position, bucket, arm), incl. the Arm 0 baseline and the missing QB-rookie path | `arm0_baselines`, `full_model_x`, `manifest` | `test_manifest_full_model_x_is_exactly_what_reaches_fit`, `test_manifest_pins_baselines_per_bucket_and_arm0_equals_the_baseline` | PASS |
| R-6 | the ten-condition §7 verdict is computed on the nested-selected Design A pipeline only | `primary_verdict`, `_integrity_check` | `test_a_fixture_engineered_to_satisfy_all_ten_conditions_passes`, `test_every_condition_can_fail_independently`, 10 per-condition tests, `test_verdict_is_emitted_by_run_experiment` | PASS |
| R-7 | no fixed arm and no Design B can rescue or alter the verdict | `primary_verdict` | `test_a_fixed_arm_cannot_rescue_a_failed_nested_selected_result`, `test_design_b_cannot_affect_the_verdict` | PASS |
| R-8 | the improvement statistic is frozen POOLED and used identically for the 3% rule and the placebo | `top_cohort_improvement`, `experiment_spec` | `test_the_improvement_statistic_is_pooled_not_a_per_season_mean`, `test_observed_statistic_and_placebo_use_the_same_function`, `test_spec_pins_all_ten_pass_thresholds_and_the_improvement_statistic` | PASS |
| R-9 | the placebo reruns nested selection per draw AND per outer fold | `nested_selected_outer_frame`, `placebo_distribution` | `test_placebo_reruns_nested_selection_and_returns_fold_specific_picks`, `test_placebo_can_select_different_arms_in_different_folds`, `test_placebo_distribution_runs_and_is_seeded` | PASS |
| R-10 | ARM_0 and therefore the cohort are invariant under permutation | — | `test_arm0_and_therefore_the_cohort_are_invariant_under_permutation` | PASS |
| R-11 | lineage carries segment-level contribution records that RECONCILE with the feature table | `contribution_lineage` | `test_contribution_rows_reconcile_with_the_feature_table_game_counts` (416 rows × 2 designs), `test_contribution_rows_identify_the_segment_and_trace_the_games`, `test_every_contribution_row_is_strictly_prior` | PASS |
| R-12 | gate exclusions are recorded WITH a reason from a closed set | `contribution_lineage` | `test_contribution_rows_exclude_nothing_by_source_date_under_the_primary_policy`, `test_a_gate_excluded_segment_appears_but_contributes_zero` | PASS |
| R-13 | the A/B test name no longer overclaims | — | `test_design_a_and_b_share_rows_schema_and_the_entire_hc_block` | PASS |

## v3.9b — FINAL PREFIT CORRECTNESS PATCH (2026-07-29)

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| B-1 | C3/C4/C8 require the EXACT frozen denominators, not just counts | `_panel_completeness`, `primary_verdict` | `test_the_complete_eight_and_five_fixture_still_passes`, `test_six_improving_seasons_supplied_as_only_six_seasons_fails_c3`, `test_four_improving_recent_seasons_supplied_as_only_four_fails_c4`, `test_four_nonbaseline_selections_across_only_four_folds_fails_c8` | PASS |
| B-2 | missing / duplicate / unexpected season or fold keys cannot yield a candidate, and are named | `_panel_completeness` | `test_unexpected_seasons_cannot_yield_a_candidate`, `test_duplicate_player_season_cohort_rows_cannot_yield_a_candidate`, `test_missing_fold_selections_cannot_yield_a_candidate` | PASS |
| B-3 | the required season sets are the prereg windows | `REQUIRED_OUTER_SEASONS`, `REQUIRED_RECENT_SEASONS` | `test_the_frozen_required_season_sets_are_exactly_the_prereg_windows` | PASS |
| B-4 | C10 == a real 17-check runtime preflight, reading no outcome | `preflight`, `_integrity_check` | `test_preflight_passes_on_the_real_artifacts`, `test_c10_is_the_preflight_and_run_experiment_reports_it` | PASS |
| B-5 | each preflight contract fails independently, on a TEMP COPY (canon never mutated) | `preflight(data_dir=)` | 11 `test_preflight_fails_when_*` / `test_preflight_fails_on_*` tests | PASS |
| B-6 | the pinned v3.9 hashes cannot go stale | `V39_ARTIFACT_HASHES` | `test_pinned_v39_hashes_match_disk` | PASS |
| B-7 | pipeline timing/leakage assertions must have EXECUTED, counted not assumed | `_note_assertion`, `_PIPELINE_ASSERTIONS` | `test_preflight_requires_the_pipeline_assertions_to_have_RUN`, `test_the_pipeline_actually_increments_every_assertion_counter` | PASS |
| B-8 | run-mode state machine; both locks; fails closed | `validate_run_mode`, `real_fit_lock_state` | `test_run_mode_truth_table` (8 cases), `test_an_unknown_run_mode_fails_closed`, `test_run_experiment_rejects_an_invalid_mode` | PASS |
| B-9 | authorized_real is reachable, so a candidate verdict is possible | `validate_run_mode` | `test_authorized_real_is_reachable_so_a_candidate_verdict_is_possible` | PASS |
| B-10 | no run mode relaxes a non-lock check | `preflight` | `test_no_run_mode_relaxes_a_non_lock_check` | PASS |
| B-11 | the locks are not opened anywhere in this pass (AST-level) | — | `test_the_locks_are_not_opened_anywhere_in_this_pass`, `test_this_pass_is_synthetic_prefit_with_both_locks_shut` | PASS |
| B-12 | PRIMARY history = strictly prior, full retrospective ledger, NOT source-date gated | `PRIMARY_HISTORY_SOURCE_DATE_GATED`, `build_features(history_source_date_gated=)` | `test_the_primary_history_policy_is_ungated`, `test_a_late_published_source_no_longer_suppresses_earlier_history`, `test_synthetic_the_primary_policy_does_NOT_hide_a_late_published_source` | PASS |
| B-13 | history stays STRICTLY PRIOR under the ungated policy | `caller_history` | `test_history_remains_STRICTLY_PRIOR_under_the_ungated_policy` | PASS |
| B-14 | Design A vs B is SINGLE-AXIS (target identity only) | `build_features` | `test_design_a_and_b_now_differ_on_target_identity_ONLY` (all 51 features on 227 matched rows), `test_routing_lineage_states_the_single_axis` | PASS |
| B-15 | the measured effect is +0 rows / +358 games, and known-with-history <= known | — | `test_the_ungated_policy_adds_ZERO_outer_rows_and_358_games`, `test_the_28_known_no_history_rows_are_genuine_first_time_callers`, `test_design_a_known_with_history_cannot_exceed_known_identities` | PASS |
| B-16 | the strict gate survives only as an in-memory, unpersisted, labelled sensitivity | `strict_gate_sensitivity`, `SENSITIVITY_LABEL` | `test_the_strict_gate_survives_only_as_an_in_memory_sensitivity`, `test_the_sensitivity_is_never_written_to_a_repo_artifact`, `test_the_strict_gate_remains_auditable_from_the_lineage_artifact` | PASS |
| B-17 | the verified v3.6 routing history totals are preserved (Reid 192 / McVay 181 / McDaniel 68) | — | `test_2026_routing_history_totals_match_the_verified_v36_figures` | PASS |

## v3.9n — FROZEN ROOKIE FEATURE MATRIX (Option A, 2026-08-03)

All in `tests/test_rookie_matrix_v39.py` unless noted.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| M-1 | the frozen 2014-2025 RB/WR/TE rookie population is preserved in full — 1,263 rows, RB 387 / WR 584 / TE 292, all twelve seasons, unique non-null `(player_id, season)`, rookie-only | `build_rookie_arm0_features.build`, `validate_rookie_matrix` | `test_the_frozen_population_is_rookie_only_and_fully_present`, `test_row_loss_is_refused_at_the_file_level`, `test_row_loss_is_refused_at_the_frame_level`, `test_a_duplicate_key_is_refused`, `test_a_null_key_is_refused`, `test_a_missing_season_is_refused`, `test_an_out_of_range_season_is_refused`, `test_a_foreign_position_is_refused`, `test_a_non_rookie_row_is_refused` | PASS |
| M-2 | built by calling the REAL production `assemble_features.build_features()` with only the two nflverse loaders injected from pinned snapshots — no parallel implementation | `build_rookie_arm0_features` | `test_the_declared_generator_exists_and_is_the_file_that_built_it`; production-equivalence also exercised by `test_combine_snapshot_provenance.py::test_the_production_combine_transformation_consumes_the_local_snapshot_offline` | PASS |
| M-3 | 5 identity/routing keys + the complete 54-column union of the three rookie pools, in an INDEPENDENTLY pinned order | `ROOKIE_MATRIX_COLUMNS` | `test_the_pinned_schema_literal_matches_the_file_on_disk`, `test_a_reordered_schema_is_refused`, `test_a_renamed_column_is_refused`, `test_an_added_column_is_refused`, `test_a_dropped_column_is_refused`, `test_reordering_the_stored_schema_is_refused_by_the_schema_pin` | PASS |
| M-4 | production null semantics preserved — no proxy substitution, no imputation, no row dropped, no population amendment | `build_rookie_arm0_features.build` | `test_nulls_are_PRESERVED_not_imputed` | PASS |
| M-5 | NO fantasy outcome, target, label, sample weight, ADP, market projection or target-season realized statistic | `FORBIDDEN_IN_FEATURES`, `verify_rookie_matrix_provenance` | `test_no_forbidden_column_is_present`, `test_no_column_name_carries_an_outcome_or_market_token` (13 params), `test_every_forbidden_column_is_refused_at_the_file_level` (11 params), `test_the_generator_never_names_the_outcome`, `test_the_generator_scan_catches_an_injected_read` | PASS |
| M-6 | raw PFF stays private and untracked; only derived feature values are repo-owned | — | `test_raw_pff_is_untracked_while_derived_values_are_repo_owned` | PASS |
| M-7 | deterministic write — two rebuilds byte-identical | `build_rookie_arm0_features.build` | verified in-pass by two temp-directory rebuilds reproducing sha256 `4b4655ab…`; pinned by `test_the_file_hash_matches_the_pin_and_the_manifest` | PASS |
| M-8 | manifest provenance: sha256, schema, shape, seasons, keys, positions, source categories, generator path | `snapshots/manifest.json` | `test_the_file_hash_matches_the_pin_and_the_manifest`, `test_a_missing_manifest_entry_is_refused`, `test_a_manifest_field_disagreeing_with_the_pin_is_refused` (7 params), `test_a_missing_manifest_file_is_refused` | PASS |
| M-9 | integrated into the assembly module with hash / schema / key / season / forbidden-column validation, behind a default-closed reader | `verify_rookie_matrix_provenance`, `authorized_rookie_matrix_reader`, `validate_rookie_matrix` | `test_the_frozen_matrix_verifies_clean`, `test_a_flipped_byte_is_refused`, `test_an_absent_matrix_is_refused`, `test_the_default_rookie_reader_refuses`, `test_constructing_the_authorized_reader_reads_nothing`, `test_the_authorized_reader_returns_the_frozen_frame`, `test_the_reader_runs_its_own_output_through_its_own_validator`, `test_the_assembly_contract_still_holds_with_the_matrix_wired_in` | PASS |
| M-10 | all seven bundle FEATURE inputs complete. **The `activation_readiness() is True` half is SUPERSEDED by L-7 (v3.9o): readiness is False on the bundle-training blocker.** | `arm0_bucket_table`, `activation_readiness` | `test_all_seven_bundles_have_their_FEATURES`, `test_each_rookie_bundle_is_sourced_from_the_frozen_matrix` (3 params), `test_activation_readiness_is_TRUE_with_a_point_in_time_matrix`, `test_readiness_fails_CLOSED_when_the_matrix_cannot_be_verified`, `test_readiness_fails_CLOSED_on_a_hash_mismatch` | PASS |
| M-11 | preflight stays 21/21 and `authorized_real_gate()` stays False; the entry point stays sealed and both locks stay closed | `preflight`, `authorized_real_gate` | `test_a_clean_preflight_still_does_not_open_the_gate`, `test_the_locks_are_still_closed`, `test_the_activation_entry_point_is_still_sealed` | PASS |
| M-12 | bundle FEED order is enforced where it is real (the per-bucket frame), because one storage order cannot equal all three bundle orders | `rookie_bucket_frame`, `bucket_frame_satisfies_bundle` | `test_every_rookie_bundle_selects_in_bundle_order` (3 params), `test_a_bucket_frame_with_shuffled_features_is_refused`, `test_dropping_one_bundle_feature_is_refused` (3 params), `test_the_three_pools_CANNOT_share_one_storage_order`, `test_a_veteran_bucket_cannot_be_pulled_from_the_rookie_matrix` | PASS |
| M-13 | the matrix agrees with the INDEPENDENT bundle pins, not with the module's own constants | `tests/arm0_bundle_pins.py` | `test_the_bundle_pins_and_the_matrix_agree_on_every_rookie_pool` | PASS |
| M-15 | the PFF local-file count quoted in the live documents is MEASURED from disk, not asserted; a superseded figure without a same-line qualifier fails | — | `test_the_documented_pff_local_file_count_is_MEASURED_not_asserted` | PASS |
| M-14 | every NON-PFF build input is hash-pinned and verified before a value is read; the private PFF library is deliberately NOT pinned and that is stated, not hidden | `build_rookie_arm0_features.INPUT_PINS`, `verify_inputs` | `test_every_non_pff_input_is_pinned_and_currently_matches`, `test_a_drifted_input_is_refused`, `test_the_private_pff_library_is_deliberately_NOT_pinned` | PASS |


## v3.9o — PFF POINT-IN-TIME REPAIR (material leakage, 2026-08-03)

All in `tests/test_pff_point_in_time_v39.py` unless noted.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| L-1 | the leak is REPRODUCED before it is repaired: the retired `idxmax`-per-name rule selects a source season at or after the rookie season for each measured example | `retired_max_season_join` (test-only reproduction) | `test_RED_the_retired_rule_reproduces_each_measured_leak` (3 params) | PASS |
| L-2 | the shipped rule fixes each measured example | `_pff_point_in_time` | `test_GREEN_the_shipped_rule_fixes_each_measured_leak` (3 params), `test_each_measured_example_is_corrected_IN_THE_SHIPPED_ARTIFACT` (4 params) | PASS |
| L-3 | PFF source season is RETAINED and only seasons strictly before the reference season are eligible; the boundary is exact | `_pff_long`, `_pff_point_in_time` | `test_the_season_boundary_is_STRICTLY_LESS_THAN` (3 params), `test_no_eligible_prior_season_yields_NULL`, `test_multiple_eligible_seasons_take_the_LATEST_prior` | PASS |
| L-4 | a later same-name player can never match an earlier rookie; collisions resolve by position then by the immediately-prior season, and yield NULL when identity cannot be established | `_pff_point_in_time`, `PFF_POSITION_COMPAT` | `test_a_LATER_same_name_player_can_never_match_an_earlier_rookie`, `test_a_same_name_collision_is_resolved_by_POSITION_when_that_is_decisive`, `test_a_same_name_collision_is_resolved_by_the_IMMEDIATELY_PRIOR_season`, `test_an_UNRESOLVABLE_same_name_collision_yields_NULL_rather_than_a_guess`, `test_an_unambiguous_name_keeps_its_row_even_when_the_position_disagrees` | PASS |
| L-5 | selection is deterministic and there is ONE shared production implementation, not a generator copy | `_pff_point_in_time`, `build_rookie_arm0_features` | `test_selection_is_deterministic_under_input_reordering`, `test_the_retired_collapse_is_GONE_from_production`, `test_build_features_REFUSES_a_panel_with_no_reference_season`, `test_there_is_ONE_shared_production_join_not_a_generator_copy` | PASS |
| L-6 | the artifact CARRIES its point-in-time guarantee and it is checkable with no private data | `PROVENANCE_COLUMNS`, `validate_rookie_matrix` | `test_the_artifact_carries_its_point_in_time_provenance`, `test_NO_row_in_the_artifact_draws_from_its_own_season_or_later` (2 params), `test_a_block_is_present_exactly_when_its_source_season_is` (2 params) | PASS |
| L-7 | **SUPERSEDED by S-1..S-5 (v3.9p).** The historical fact stands (the bundles were fit on the contaminated join) but the activation blocker drawn from it is WITHDRAWN: the experiment refits from scratch. Nothing is retrained. | `CONTAMINATED_TRAINED_BUCKETS`, `ROOKIE_BUNDLE_TRAINING_BLOCKER`, `arm0_bucket_table`, `activation_readiness` | `test_the_rookie_features_are_now_COMPLETE_and_point_in_time`, `test_the_rookie_bundle_SPECS_are_complete_so_nothing_blocks_on_them`, `test_activation_readiness_is_TRUE_now_that_the_features_are_point_in_time`, `test_the_frozen_hyperparameter_limitation_is_disclosed_but_does_not_gate`, `test_the_bundles_themselves_were_not_touched`, `test_the_gate_still_refuses_and_the_locks_are_still_shut` | PASS |
| L-8 | the private PFF inputs are fingerprinted over exactly the CONSUMED files, verified before and after the build, and never exposed | `pff_provenance`, `verify_pff_inputs`, `expected_pff_files` | `test_the_private_pff_inputs_are_fingerprinted_not_exposed`, `test_the_superseded_leaked_artifact_is_recorded_as_INVALID` | PASS |


## v3.9p — ARM 0 REFITS FROM SCRATCH (the withdrawn bundle-training blocker, 2026-08-03)

All in `tests/test_arm0_refits_from_scratch_v39.py`.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| S-1 | `arm0_definition()` returns METADATA only; the serialized estimator is never placed in the spec, and `bundle["model"]` is touched only inside `type(...)` | `arm0_definition` | `test_arm0_definition_does_not_return_the_serialized_model_object`, `test_arm0_definition_touches_the_stored_model_only_to_read_its_TYPE`, `test_the_experiment_never_unpickles_a_bundle_into_a_prediction_path` | PASS |
| S-2 | `fit_predict()` constructs a FRESH estimator per call and fits it on the frame it is given | `fit_predict` | `test_fit_predict_constructs_a_fresh_estimator_each_call`, `test_fit_predict_fits_on_the_frame_it_is_GIVEN` | PASS |
| S-3 | replacing the stored estimator with an exploding sentinel cannot change a single prediction | — | `test_POISONING_the_stored_estimator_cannot_change_a_single_prediction`, `test_the_sentinel_really_does_explode`, `test_arm0_definition_survives_a_poisoned_estimator` | PASS |
| S-4 | every rookie fold fit receives the CORRECTED point-in-time matrix | `arm0_bucket_table`, `rookie_bucket_frame` | `test_the_rookie_feature_source_is_the_corrected_matrix`, `test_every_rookie_row_the_folds_would_train_on_is_point_in_time`, `test_a_rookie_fold_frame_carries_the_corrected_values` (3 params), `test_fold_training_frames_are_spied_and_carry_no_late_pff` | PASS |
| S-5 | the bundle SPECIFICATION (feature order, family, params, null handling, seed, target) is pinned by value and is what gates activation; the fitted weights are not | `BUNDLE_SPEC_PINS`, `bundle_spec_problems`, `arm0_bucket_table` | `test_every_bundle_spec_matches_its_INDEPENDENT_pin` (7 params), `test_the_spec_pins_cover_exactly_the_seven_shipped_buckets`, `test_mutating_a_pinned_spec_field_is_detected` (4 params), `test_the_spec_contract_is_what_gates_activation_not_the_fitted_weights`, `test_an_INCOMPLETE_spec_is_refused` (6 params) | PASS |
| S-6 | the frozen-hyperparameter limitation is DISCLOSED and does NOT gate | `FROZEN_HYPERPARAMETER_DISCLOSURE` | `test_the_frozen_hyperparameter_limitation_is_DISCLOSED_and_NOT_gated`, `test_the_disclosure_appears_in_the_activation_manifest` | PASS |
| S-7 | readiness is True on all seven buckets and the gate refuses SOLELY on run mode and the locks | `activation_readiness`, `authorized_real_gate` | `test_activation_readiness_is_TRUE_on_all_seven_buckets`, `test_the_gate_refuses_SOLELY_on_run_mode_and_the_locks`, `test_nothing_was_retrained_in_this_pass` | PASS |


## v3.9q — THE ACTIVATION WIRING (C5-A implemented door, 2026-08-03)

All in `tests/test_activation_wiring_v39.py` unless noted.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| W-1 | C5 is MODE-AWARE and the mode is a DECLARED constant, never inferred from the lock state | `_entry_point_is_sealed`, `ENTRY_POINT_CONTRACT_MODE` | `test_the_declared_contract_mode_is_authorized_real_and_is_not_a_lock`, `test_an_unknown_contract_mode_is_refused` | PASS |
| W-2 | the live door satisfies C5-A, and C5-S genuinely rejects it (the variants are not interchangeable) | `_entry_point_is_sealed` | `test_the_door_satisfies_C5_A`, `test_the_live_door_would_FAIL_C5_S_and_that_is_the_point`, `test_C5_S_still_ACCEPTS_the_sealed_shape` | PASS |
| W-3 | the door body is exactly authorization → clearance → `assemble_panel_core(...)`, with NO reader or banned outcome callee anywhere, and readers as parameters | `assemble_real_panel` | `test_the_door_body_is_exactly_three_statements_in_the_pinned_order`, `test_the_door_contains_NO_reader_callee_at_all`, `test_the_readers_are_parameters_not_module_globals` | PASS |
| W-4 | **in `synthetic_prefit` the prohibition on real readers is COMPLETE**: with the locks closed or partial, or the run mode synthetic, no injected reader is ever called | `assemble_real_panel`, `require_preflight_clearance` | `test_with_the_locks_CLOSED_the_door_refuses_and_no_reader_is_called`, `test_every_PARTIAL_lock_state_refuses_before_any_reader` (3 params), `test_a_synthetic_prefit_run_mode_refuses_even_with_BOTH_locks_open` | PASS |
| W-5 | clearance requires both locks, preflight 21/21 in authorized_real mode, readiness True and the gate True, and gates BEFORE the input pins are consulted | `require_preflight_clearance` | `test_clearance_refuses_when_readiness_is_blocked`, `test_clearance_refuses_a_gate_that_is_not_authorized_shaped`, `test_clearance_ORDER_gates_before_inputs` | PASS |
| W-6 | the pinned veteran, rookie and weekly-outcome inputs are verified before reading, each failing closed independently; coaching artifacts via preflight | `verify_pinned_activation_inputs` | `test_all_four_pinned_input_families_are_verified_before_reading`, `test_each_pinned_input_family_fails_closed_independently` (3 params), `test_clearance_reaches_and_ENFORCES_the_input_pins`, `test_a_drifted_input_stops_the_door_before_any_reader` | PASS (the veteran pin is currently RED by design — stop report §10.9.6) |
| W-7 | the door routes through `assemble_panel_core` and preserves production zero-fill and accounting exactly | `assemble_real_panel`, `assemble_panel_core` | `test_GREEN_the_door_opens_and_assembles_when_every_gate_clears`, `test_GREEN_production_zero_fill_and_accounting_survive_the_door`, `test_the_door_returns_exactly_what_assemble_panel_core_returns` | PASS |
| W-8 | Design B stays oracle and unselectable, and the door introduced no Design B path | `run_experiment`, `assemble_real_panel` | `test_design_b_remains_oracle_and_unselectable`, `test_the_door_did_not_introduce_a_design_b_path` | PASS |
| W-9 | the boundary corpus covers C5-A, and the historical arm is measured against the source shape its validator was written for | `boundary_corpus.historical_pure_sources`, `CATEGORIES` | `test_the_historical_validator_matches_the_recorded_result` (75 params), `test_the_red_green_totals_are_exactly_as_reported`, `test_every_declared_category_is_exercised_by_the_corpus` | PASS |
| W-10 | the stop state: readiness True, preflight 21/21, gate False on the LOCKS alone, no result artifact, no canonical outcome read | `preflight`, `activation_readiness`, `authorized_real_gate` | `test_the_stop_state_is_exactly_what_was_asked_for`, `test_no_result_artifact_was_written`, `test_this_module_never_opens_the_canonical_outcome_snapshot` | PASS |


## v3.9r — THE VETERAN INPUT RE-SCOPED (immutable feature-only snapshot, 2026-08-03)

All in `tests/test_veteran_snapshot_v39.py` unless noted.

| # | requirement | generating function | covering test | status |
|---|---|---|---|---|
| V-1 | exact seasons, keys, population and ordered schema, DERIVED from the live contracts rather than hand-copied | `build_veteran_arm0_snapshot.build`, `frozen_columns`, `frozen_seasons` | `test_exact_seasons_keys_and_population`, `test_the_ordered_schema_is_the_LIVE_consumed_contract`, `test_the_schema_covers_every_shipped_VETERAN_bundle_pool`, `test_the_manifest_entry_matches_the_file` | PASS |
| V-2 | feature-only: no target, outcome, label, weight, ADP or market field, with the exclusion proven non-vacuous | `build`, `_assert_contract` | `test_no_forbidden_field_is_present`, `test_no_column_name_carries_an_outcome_or_market_token` (9 params), `test_no_column_is_EXACTLY_an_outcome_or_market_field` (9 params), `test_the_legitimate_prior_season_features_ARE_kept`, `test_the_source_columns_the_snapshot_DROPPED_include_every_market_and_target_field` | PASS |
| V-3 | the snapshot equals the source's 2014-2025 consumed values, column by column, null-aware | `build` | `test_the_snapshot_equals_the_SOURCE_2014_2025_consumed_values` | PASS |
| V-4 | **changes to season 2026 cannot affect the snapshot or activation** | `build`, `verify_pinned_activation_inputs` | `test_building_from_the_PRE_REFRESH_source_reproduces_the_SAME_bytes`, `test_a_2026_only_mutation_of_the_source_cannot_change_the_snapshot`, `test_the_two_sources_DIFFER_only_in_2026_and_only_as_measured`, `test_NO_2014_2025_cell_differs_between_the_two_sources`, `test_activation_does_not_depend_on_the_live_production_csv` | PASS |
| V-5 | any 2014-2025 consumed-value mutation fails | `build` | `test_a_2014_2025_consumed_value_mutation_CHANGES_the_rebuild` (5 params) | PASS |
| V-6 | two fresh rebuilds are byte-identical, and a corrupted / short / extended / 2026-carrying snapshot is refused | `build`, `verify_veteran_snapshot_provenance` | `test_two_fresh_rebuilds_are_byte_identical`, `test_a_corrupted_snapshot_is_refused_by_the_reader`, `test_a_dropped_or_extra_column_is_refused`, `test_a_2026_row_smuggled_into_the_snapshot_is_refused` | PASS |
| V-7 | the corrected rookie matrix is UNCHANGED and was not rebuilt | — | `test_the_corrected_rookie_matrix_is_UNCHANGED_and_was_not_rebuilt` | PASS |
| V-8 | the generator may read the production CSV; the authorized experiment may not, and the whole-CSV md5 pin is DELETED | `authorized_feature_reader`, `verify_pinned_activation_inputs` | `test_the_authorized_reader_reads_the_snapshot_not_the_csv`, `test_the_generator_reads_the_csv_but_the_experiment_never_does`, `test_assemble_real_panel_v39.py::test_the_feature_source_matches_the_production_pin` | PASS |
| V-9 | the stop state is unchanged by the re-scope | `preflight`, `activation_readiness`, `authorized_real_gate` | `test_preflight_readiness_and_gate_after_the_rescope` | PASS |

Inherited per module: `test_arm3_orchestration` 22 · `test_coaching_phase1c` 33 ·
`test_reliability_phase1d` 34 · `test_stage_models_synthetic` 27 · `test_personnel_controls` 15 ·
`test_drive_definitions` 7 · `test_artifact_ownership` 3 = **141**.

### Phase 2 open items (carried, NOT closed)

1. **Design A caller power is thin in 2019-2022.** Team-seasons with ANY eligible prior caller
   history: 25 / **3** / 4 / 7 / 6 / 26 / 26 / 27 out of 32 for 2018-2025. A null caller arm on this
   panel cannot separate "no coaching signal" from "no retrievable identity".
2. **The neutral 0.5 level on the two binary caller indicators is season-correlated** under Design A.
   The team-level permutation placebo is the pre-registered control; it is not a proof of absence.
3. **HC identity is an assumption, not evidence-gated research** — taken from the week-1 head coach.
4. **`build_coach_features.py` remains unrepaired** and is not used by v3.9. It still joins on
   (season, team) and still carries the pre-v3.3 metric names.
5. **Arm 3 effects do not exist before target 2018** and are not backfilled.
