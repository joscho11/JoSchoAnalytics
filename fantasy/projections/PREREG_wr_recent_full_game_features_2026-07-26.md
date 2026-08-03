# PRE-REGISTRATION — WR RECENT FULL-PARTICIPATION-GAME ROLE FEATURES (2026-07-26)

**STATUS: DESIGN LOCKED. NO CHALLENGER MODEL HAS BEEN FITTED, NO CHALLENGER METRIC EXISTS.**
This is a **research-only** development experiment on the non-rookie seasonal WR model. It cannot
rewrite a model, a projection CSV, a board artifact, an overlay, a dataset, or a market claim.
Sleeper, ADP and player names are excluded from loading, fitting, selection, cohort definition and
every gate. Everything generated goes to `C:\tmp\wr_recent_full_game_features_2026-07-26`.

---

## 0. QUESTION

Does adding a **jointly frozen block of prior-season last-four and last-eight
full-participation-game role features** improve 2021–2025 walk-forward player projections for
non-rookie WRs?

The two elements that were **not** isolated in the already-rejected within-season trajectory family
are the only justification for a second look:

1. **Last-eight-game levels** — a longer, less volatile confirmation window. The rejected family
   tested last-four only.
2. **Filtering probable partial-game injury exits before computing recent form** — a snaps-only,
   outcome-independent early-exit proxy. The rejected family computed recent form over every active
   game, so a 10–20-snap injury exit entered the average as if it were a normal role observation.

---

## 1. REQUIRED DISCLOSURE — the rejected prior experiment

`memory/seasonal-wr-negative-gap-experiments-2026-07.md` §"Rejected — do not re-run", item 3
("Within-season role trajectory"), fired 2026-07-25/26 and is **REJECTED AND FINAL**. It tested four
variants: second-half versus first-half target share; a last-four-game share ramp; both plus
air-yard and scoring trends; and a `years_exp == 2` interaction.

| Variant | ΔMAE |
|---|---:|
| second-half vs first-half share | **+0.178** |
| last-four share ramp | **−0.017** |
| both + air-yards/scoring trends | **+0.127** |
| `years_exp == 2` interaction | **+0.204** |

Every confidence interval crossed zero, rank correlation declined in all four variants, only 2–3 of
5 seasons improved, and it failed the job it was built for (third-season cohort under-projection
went 17.47 → 19.67 / 16.67 / 18.31 and cohort MAE rose from 52.00 in every variant). Training/deploy
feature coverage was approximately **79% / 72%** — the same drift class that sank the rookie profile
matrix and `depth_rank`.

**This experiment may not retest those variants, rescue them with alternative thresholds, or claim
that a last-four trend alone is new.** Second-half-versus-first-half features, share *ramps* /
slopes / trends / EWMAs, rise thresholds and career-stage interactions are all fenced and appear
nowhere in the block below. No named player — Ricky Pearsall, Rome Odunze, Luther Burden, Terry
McLaurin or any other — is tuned for, scored in isolation, or admissible as evidence.

### 1.1 Recoverability of the prior implementation — searched, and the result stated exactly

The task requires locating the generating code and persisted output of that experiment rather than
declaring it unrecoverable from result CSVs. **It was searched for and it is not on this machine.**
Searched, all negative: the whole `JoSchoAnalytics` tree; `git log --all` including
`--diff-filter=D`, the reflog and the stash (no `PREREG_ppg_vs_total_2026-07-25.md`,
`PREREG_prorate_totals_2026-07-25.md` or any trajectory harness was ever committed); all 44 local
Claude session transcripts under
`~/.claude/projects/c--Users-josep-Desktop-random-stuff-cowork-OS/`, by feature-token
(`share_ramp`, `last4_*`, `second_half_share`, `tail(4)`), by result value (`0.178`) and by phrase
("within-season role trajectory") — every hit resolves to the memory node being *read*, never to the
code; every session scratchpad under that project root and under both alternate scratch roots
(`C--Users-josep-Desktop-random-stuff-JoSchoAnalytics`,
`C--Users-josep-iCloudDrive-Projects-JoSchoAnalytics`, which contain `tasks/` only); `C:\tmp\*`;
and the alternate checkout `C:\Users\josep\iCloudDrive\Projects\JoSchoAnalytics` (an empty
placeholder).

**What survives is the recorded summary**, which is the disclosure in §1 above plus
`memory/daily/2026-07-26.md`. The 2026-07-25 batch (families 1, 2, 3 and 4 and their two named
preregs) left no artifacts in this repo or in local scratch, which is consistent with those runs
having happened in a sandbox whose filesystem was not persisted here. This is recorded as a
provenance limitation of the prior result, not as an excuse: the ΔMAE values, CI behaviour, rank
direction, season counts and coverage figures in §1 are treated as binding fences regardless.

---

## 2. HYPOTHESIS AND MECHANISM

Whole-season averages can obscure a genuinely changed late-season role, while ordinary last-four
trends are contaminated by injury exits and too noisy on their own.

A **jointly added block** containing last-four and last-eight full-participation-game *levels* may
improve player discrimination because:

- four games captures the most recent role;
- eight games provides a less volatile confirmation window;
- excluding probable early exits prevents a 10–20-snap injury game from being treated as a normal
  role observation;
- the full-participation definition uses **snaps only, never fantasy production**, so the filter
  cannot select on the outcome it is meant to predict.

The mechanism is expected to help **opportunity allocation**, not merely inflate projections.

**Honest prior, recorded before the fire: expect REJECT.** The four-variant trajectory family failed;
cross-season role state failed; the measured junk-feature noise floor is +0.26 MAE per added column
and this block adds **16**; and the WR model's established deficiency is *within-cohort
discrimination*, which the team-allocation audit showed is an identification problem
(prediction SD 19.8 against actual SD 68.4 on the top cohort), not a shape problem. A block of
sixteen prior-season role levels is a plausible but not obviously sufficient answer to that.

---

## 3. PRIMARY DATA, MODEL AND RESEARCH-ONLY LABELLING

- **Position:** WR. **Arm:** non-rookies only (`is_rookie == 0`). Rookies untouched.
- **Evaluation seasons:** 2021–2025, walk-forward; for target season `Y` every arm trains strictly
  on rows with `season < Y`.
- **Target:** the existing `season_total_target()` — regular-season `fantasy_points + 0.5·receptions`
  summed by `(player_id, season)`; observed seasons ≤ 2025 with no weekly row are real zeros; 2026 is
  NaN.
- **Dataset:** the corrected `fantasy/seasonal_projections/season_dataset_2014_2026.csv`
  (md5 `8322a59e43251820cb393d40787f60e6`).
- **Weekly inputs:** the pinned snapshots `build_season_dataset.py` itself uses —
  `snapshots/player_stats_2011_2025.parquet`, `snapshots/snap_counts_2013_2025.parquet`,
  `snapshots/players.parquet` (the `pfr_id → gsis_id` crosswalk), `snapshots/schedules_2011_2025.parquet`.
  No live `nflreadpy` pull occurs anywhere in this harness.
- **Postseason is excluded** everywhere: `season_type == "REG"` on player stats and schedules,
  `game_type == "REG"` on snap counts. Asserted, not assumed.
- **Sleeper, ADP, current depth charts and player names** enter no fit, no selection, no gate and no
  cohort definition.
- **Baseline feature pool:** `WR_VET_ALL` — the exact ordered 32 columns — **unchanged**.
- **Learner slate, grids, nested selection, walk-forward and missing-data handling:** inherited
  verbatim from `build_rb_projection.py` (`nested_select`, `_grid`, `_prep`, `_make_model`,
  `_fit_predict`; CatBoost 16 / LightGBM 8 / XGBoost 16 / ElasticNet 9; inner leave-one-season-out CV
  on training seasons, MAE primary; seed 42). **No new learner, objective, grid, loss function or
  target architecture is introduced.**
- **Interpreter:** `JoSchoAnalytics/.venv-test/Scripts/python.exe` — the interpreter that
  produced the completed corrected-data retrain, so the G0 reproduction is like-for-like.

**RESEARCH-ONLY LABEL (required).** The corrected-data retrain
(`PREREG_corrected_data_retrain_2026-07-26.md`) **FAILED at all four positions** and is additionally
blocked from production by its §6.4 `qb_changed` condition. The corrected-data baseline used here is
therefore **explicitly research-only**; it is not a shipping baseline and a pass here would not
change that. This experiment tests a feature block against a research baseline, and nothing more.

---

## 4. PREREQUISITE TASKS — both confirmed terminal before this file was written

| Task | State | Evidence |
|---|---|---|
| Corrected-data retrain `bt4gpx818` | **TERMINAL 2026-07-26 20:47 ET** | `PREREG_corrected_data_retrain_2026-07-26.md` §11: fired once, SHA256 `c3a34c5b…`, 295 min, exit 0, verdict **FAIL at all four positions**, protected artifacts unchanged. |
| WR team-allocation audit | **TERMINAL 2026-07-26 20:49 ET** | `PREREG_wr_team_allocation_audit_2026-07-26.md` §11: fired once, SHA256 `de1b09bd…`, verdict **NO GENERIC CONCENTRATION DEFECT**, all four gates fail, primary statistic sign-inverted. |

Neither is active. Nothing runs concurrently with either.

**Consequence for §8's optional reporting block.** The audit did **not** confirm generic
under-concentration — it inverted: the model's own top two were projected 59.89% of team WR points
and realized 58.67% (allocation error **+0.0122** against a −0.050 bar), and prediction-rank 7+
receivers were **under**-given (+0.0076, interval excluding zero). The allocation statistics named
in the task specification are therefore reported **as descriptive movement only**, explicitly
against the audit's measured inverted baseline, and they are **not** a gate and not evidence in
either direction.

---

## 5. FULL-PARTICIPATION DEFINITION — FROZEN

For every player and every **prior** season (the source season `S = Y − 1`), over regular-season
weeks only:

1. **Active week:** `offense_snaps > 0`.
2. **Normal snap share:** the **75th percentile** of that player's `offense_pct` across his active
   regular-season weeks in `S`. Requires **at least three active weeks** to estimate.
3. **Full-participation proxy:** a week qualifies when
   - `offense_snaps >= 20`, **and**
   - `offense_pct >= max(0.35, 0.70 × normal_snap_share)`.

`20`, `0.35`, `0.70`, the 75th percentile and the three-active-week minimum are **frozen** and are
not altered after results are seen. No alternate threshold, no alternate percentile, no alternate
minimum-week rule, and no second definition is created.

This is a deliberately conservative, **outcome-independent early-exit proxy**. It is not a claim of
known health. Snap columns only; no fantasy production, no targets, no yards, no touchdowns enter
the qualification test.

**Frozen resolution of the one ambiguity, decided now, before any result exists.** When a player has
**fewer than three active weeks** in `S`, `normal_snap_share` is not estimable, so **no week
qualifies**: `prior_full_participation_games = 0`, `prior_active_games_excluded = ` his active-week
count, both window flags are `0`, and all ten window features are NaN. The alternative (treating
every active week as qualifying) would let a one- or two-game season define a "recent role", which is
the exact contamination this filter exists to remove.

**Important caveat, preserved in the features themselves.** A low-snap game may be a genuine
demotion rather than an injury exit. The count of active games excluded by the proxy is therefore
carried as its own feature (`prior_active_games_excluded`) so negative role information is not
silently erased, and the audit in §9 reports the excluded games in full.

---

## 6. RECENT WINDOWS AND THE FROZEN FEATURE BLOCK

Qualifying games are sorted chronologically within `(player_id, source_season)` by regular-season
week. The **last K** qualifying games form the K-window. **A window is populated only when the player
has at least K qualifying games**; otherwise all of that window's features are NaN and its flag is 0.

For each window `K ∈ {4, 8}`, exactly five quantities:

| Feature | Definition |
|---|---|
| `last{K}_half_ppr_pg` | mean half-PPR (`fantasy_points + 0.5·receptions`) per qualifying game in the window |
| `last{K}_targets_pg` | mean targets per qualifying game in the window |
| `last{K}_target_share` | **volume-weighted**: Σ player targets over the window ÷ Σ his team's skill-position targets in those same weeks |
| `last{K}_air_yards_share` | **volume-weighted**: Σ player `receiving_air_yards` over the window ÷ Σ his team's skill-position receiving air yards in those same weeks |
| `last{K}_snap_share_mean` | mean `offense_pct` over the qualifying games in the window |

Plus six:

| Feature | Definition |
|---|---|
| `prior_full_participation_games` | count of qualifying games in `S` |
| `prior_active_games_excluded` | active weeks in `S` minus qualifying games in `S` |
| `last4_calendar_span` | days between the first and last gameday of the 4-window (NaN when unpopulated) |
| `last8_calendar_span` | days between the first and last gameday of the 8-window (NaN when unpopulated) |
| `has_last4_full` | 1 when the 4-window is populated, else 0 |
| `has_last8_full` | 1 when the 8-window is populated, else 0 |

**16 columns. This is one frozen feature family.** Appended to `WR_VET_ALL` in exactly the order
listed, giving a 48-column challenger pool.

**Frozen mechanics.** Team weekly denominators are computed exactly as the corrected
`build_season_dataset.build_season_aggregates()` does — REG rows, skill positions
(`QB/RB/WR/TE`) only, grouped by `(team, season, week)`, using the player's **own team that week**, so
a traded player's window is priced against the right room. `TEAM_CANON` is applied to every feed.
Gamedays come from the pinned schedules snapshot keyed on `(season, week, canonical team)`; if a key
misses, that week's earliest REG gameday in the season is used. Snap rows are joined to `player_id`
by the `pfr_id → gsis_id` crosswalk first, with a name fallback used **only** where the normalized
name maps to exactly one `pfr_player_id` in that season — the same rule, at weekly grain, that
`add_snaps()` uses.

**Frozen resolution of the second ambiguity, decided now, before the harness exists and before any
value has been computed.** Qualification is decided by the **snap row alone**. If a qualifying week
has no corresponding weekly *stat* row, the player was on the field and recorded nothing, so his
targets, receiving air yards and half-PPR for that week are **0**, while the week still contributes
its team denominator and its snap share. The incidence of such weeks is counted and reported. The
alternative — dropping those weeks — would silently delete the lowest-production qualifying games
from a window and bias every level feature upward.

**Explicitly excluded from the block** (each would reopen a fenced family): touchdown rate; yards per
target; catch rate; receiving yards per target; any efficiency trend; any separate first-half /
second-half feature; any slope, ramp, delta or EWMA; any player-specific interaction; any
position-age or experience interaction.

**No ablation after the fire.** Last-four-only, last-eight-only, flag-only, drop-the-spans and every
other single-feature or subset variant of this block are fenced by this document. The block passes or
fails whole.

---

## 7. THREE FROZEN ARMS

Inherited from the corrected-data retrain's attribution structure.

| Arm | Features | Selection | Isolates |
|---|---|---|---|
| **BASE** | `WR_VET_ALL` (32) | inherited `nested_select`, per fold | the corrected-data research baseline |
| **FIXED-FEATURE** | 32 + the 16-column block (48) | **BASE's per-fold `(family, params)`, verbatim** | **the feature effect — this is the PRIMARY comparison** |
| **RESELECTED-FEATURE** | 48 | inherited `nested_select`, re-run | secondary, **report-only** |

Deploy (2026) follows the same rule: BASE fits its own `nested_select` on `season <= 2025`;
FIXED-FEATURE reuses that deploy `(family, params)` with the 48-column pool; RESELECTED-FEATURE
re-runs selection.

**A RESELECTED-FEATURE improvement is report-only and cannot promote the family if FIXED-FEATURE
fails.** No fourth arm, no variant.

---

## 8. PRIMARY PANEL AND METRICS

Primary panel = the matched **`(player_id, season)` intersection of BASE and FIXED-FEATURE**, 2021–2025.
Keys asserted unique in every arm; a duplicate stops the task. Because the block adds columns and
removes no rows, the arms are expected to be row-identical, and that identity is **asserted**, not
assumed.

Reported for every arm:

- MAE, RMSE, Spearman, mean bias (`actual − prediction`), median bias, prediction SD versus actual SD.
- Per-season metrics and per-season paired ΔMAE.
- **Top-24 cohort defined by BASE prediction rank within season, frozen byte-identically across all
  three arms** (ties by first occurrence).
- **Player-clustered paired bootstrap, 2,000 draws, seed 42**, resampling `player_id` clusters
  (all of a drawn player's rows travel together), for ΔMAE.
- **Season-clustered two-sided t(4) test** on the five per-season ΔMAE values (reported always).
- Feature coverage by season, and training versus 2026 deploy, for all 16 new columns.
- Feature gain / split usage for tree models (`feature_usage.csv`).
- The complete 2026 BASE→challenger movement table, in scratch, all rows, uncurated.
- Cohort results by prior-season games played (`prior_games` bucketed), **report-only**.

**Team-allocation statistics — reported, explicitly NOT a gate.** Because the audit found the
opposite of generic under-concentration, these are recorded only as descriptive movement against its
measured baseline: prediction-selected team top-two allocation error, and rank-1/2 versus rank-7+
pooled share residuals, under BASE and under FIXED-FEATURE, with the direction of any movement stated
relative to the audit's `+0.0122` / `−0.006076` / `+0.007638`. They cannot promote or block anything.

---

## 9. NON-GATED DIAGNOSTICS

1. `full_game_exclusion_audit.csv` — every `(player_id, source_season)` with at least one excluded
   active game: active weeks, qualifying games, excluded games, `normal_snap_share`, and each excluded
   week's `offense_snaps` / `offense_pct`.
2. **Injury-exit versus demotion classification, outcome-free.** An excluded week is labelled
   `ISOLATED` when the player has at least one *later* qualifying week in that season, and
   `TERMINAL_RUN` when every later week is also excluded. Reported as counts and as a share, together
   with the association between excluded-game count and the already-existing `prior_games_missed`
   column. This uses snaps and availability only; no outcome enters it.
3. Coverage of both flags per season and at deploy (`coverage.csv`).
4. Cohort results by `prior_games`.

None of these can move a gate.

---

## 10. FROZEN DECISION GATES — one shot

The block **passes only if every one of G0–G8 holds on FIXED-FEATURE versus BASE**, on the primary
panel.

| # | Gate |
|---|---|
| **G0** | Every fold is strictly walk-forward (`train.season.max() < Y`, asserted per fold, per arm) **and** the baseline reproduces the completed corrected-data baseline within numerical tolerance (§10.1). |
| **G1** | Pooled `MAE_FIXED − MAE_BASE ≤ −0.26`. The 0.26 is the existing **measured** junk-feature noise floor (RB session, 20 pure-noise columns). |
| **G2** | Player-clustered bootstrap **95% upper bound** on that ΔMAE is **< 0**. |
| **G3** | `rho_FIXED − rho_BASE >= 0`. |
| **G4** | MAE improves in **at least 3 of 5** evaluation seasons. |
| **G5** | Frozen top-24 MAE does not worsen by more than **0.26**, **and** `abs(mean bias)` does not worsen by more than **2.0** points. |
| **G6** | `RMSE_FIXED − RMSE_BASE <= 0.010 × RMSE_BASE`. |
| **G7** | Deploy coverage: `has_last4_full` ≥ **60%** and `has_last8_full` ≥ **40%** on the 2026 deploy rows, **and** neither coverage rate falls more than **10 percentage points** from the 2021–2025 evaluation panel to 2026 deploy. |
| **G8** | Deploy sanity: 2026 slate mean movement within **±10%**; any player movement exceeding **25** points requires an identifiable **generic, feature-based** cause. A named-player lift is never itself evidence. |

### 10.1 What G0's reproduction means, fixed now

Three checks, all required:

1. **Panel identity.** The non-rookie WR panel rebuilt deterministically from the corrected dataset
   plus the pinned weekly snapshot must equal the corrected-data retrain's cached
   `assembled_WR_new.parquet` on the `(player_id, season)` key set, on `y`, and on all 32 baseline
   features, to `max |delta| = 0`.
2. **Selection identity.** BASE's per-fold `(family, params)` must equal the corrected-data retrain's
   recorded NEW WR non-rookie selections — 2021 `catboost{depth 4, lr 0.03, l2_leaf_reg 3,
   iterations 400}` and 2022 `lightgbm{num_leaves 15, lr 0.03, n_estimators 400}` from its `fire.log`,
   with 2023–2025 equal to the shipped OLD selections that same log certifies as unchanged.
3. **Metric identity.** BASE's non-rookie predictions, merged with the retrain's cached rookie-arm
   panel re-run under the same inherited procedure, must reproduce the retrain's recorded WR NEW
   full-panel **MAE 30.062** and **Spearman 0.74640** to three decimal places on n = 1,242.

The rookie arm is read **read-only** from the retrain scratch (`assembled_WR_new_rook.parquet`) and
exists in this experiment **solely** to make check 3 possible. No rookie feature is added, no rookie
model is shipped, and the rookie arm appears in no gate other than G0.

### 10.2 Rejection is final

No threshold change, no window change, no partial-feature or ablation variant, no alternate player
cohort, no season removal, no full-participation redefinition, no alternate percentile, and no
player-specific rescue attempt. A REJECT closes this block. A revisit requires a fresh
pre-registration that opens by acknowledging it is a second look at an answered question
(Amendment 4, standing).

**Even a PASS licenses nothing but a later, separate, explicit production decision and validation
session.** It licenses no model change, no projection change, no board change, no overlay, no claim
about ranking and no claim versus Sleeper.

---

## 11. POWER AND HARNESS PROOF — all before the fire

1. This preregistration is written and frozen first.
2. The harness `fantasy/projections/wr_recent_full_game_features_harness.py` is built in
   **structural-only** `--check` mode.
3. `--check` runs, and must pass:
   - **noise probe** — a random 16-column block carries no rank signal;
   - **planted-signal probe** — a block containing a deterministic function of the target is detected;
   - **future-peek probe** — a season-specific synthetic effect where a peeking model must scream;
   - **fold-boundary assertions** — `train.season.max() < Y` for every fold and arm;
   - **postseason exclusion assertion** — every weekly source is REG-only, asserted on the raw frames;
   - **feature-timing assertion** — every prediction-season-`Y` block value derives only from
     regular-season `Y − 1` rows, proved by rebuilding the block from a frame truncated at `Y − 1` and
     comparing, and by asserting the source-season join is exactly `season − 1`;
   - **duplicate-key checks** on every arm and on the block itself;
   - **row-identity check** between BASE and FIXED-FEATURE;
   - **feature-pool purity** — the 32 baseline columns are untouched and in order, the challenger is
     exactly those 32 followed by the 16 named columns, and no pool contains a `sleeper`, `adp`,
     `depth_rank`, `depth_chart`, `depth_team`, `talent` or `y` token.
4. An **outcome-free power approximation** is computed from panel counts (rows, player clusters,
   seasons) and **simulated** effects only, across a frozen grid of assumed per-row paired
   absolute-error-difference SDs and intra-player correlations. No observed ΔMAE enters it.
5. The harness SHA256 is printed and frozen.
6. `--fire` runs **exactly once**.

`--check` computes **no challenger metric of any kind**. Coverage counts, panel counts and the BASE
selection reproduction are structural and are printed; no MAE, RMSE, Spearman, bias or bootstrap for
any arm is computed in `--check`.

---

## 12. ARTIFACTS

**Created in the repo — these two files only:**

- `fantasy/projections/PREREG_wr_recent_full_game_features_2026-07-26.md` (this file)
- `fantasy/projections/wr_recent_full_game_features_harness.py`

**All generated output goes outside the repo**, to
`C:\tmp\wr_recent_full_game_features_2026-07-26`: `summary.json`, `per_season.csv`, `coverage.csv`,
`feature_usage.csv`, `deploy_move_WR.csv`, `full_game_exclusion_audit.csv`, `fire.log`.

---

## 13. PROTECTED ARTIFACTS

Hashed **before and after** both `--check` and `--fire`. **Any drift stops the task and is reported.
Nothing is repaired or overwritten.**

| Group | Files |
|---|---|
| Position models | `fantasy/projections/models/{qb_veteran, rb_rookie, rb_veteran, te_rookie, te_veteran, wr_rookie, wr_veteran}_model.pkl` |
| Rookie PPG model | `fantasy/seasonal_projections/models/rookie_ppg_model.pkl` |
| Result CSVs | every existing CSV in `fantasy/projections/results/` |
| Season datasets | `season_dataset_2014_2025.csv`, `season_dataset_2014_2026.csv` |
| Board + WR overlays | `draft_board_2026.py`, `fantasy/projections/results/wr_projection_adjustments_2026.csv`, `fantasy/projections/wr_player_scenarios_2026.csv` |

Pinned expectations carried forward:
`wr_veteran_model.pkl = 17dfbcf01054bdd5ce032f2b55df9ad2`,
`wr_rookie_model.pkl = 6c9a3f3ed02ce32c53594f383aade882`,
`rookie_ppg_model.pkl = 872467b2295fce27761f9e04da01b6e8`,
`season_dataset_2014_2026.csv = 8322a59e43251820cb393d40787f60e6`,
`season_dataset_2014_2025.csv = d9f06a2fd77adae6b5b58158650fc7ea`.

Nothing in the corrected-retrain scratch or the team-allocation-audit scratch is written or edited;
the retrain's rookie panel is read read-only. The working tree's existing state is preserved exactly:
nothing is staged, committed, reverted, cleaned or absorbed.

---

## 14. BLINDNESS DISCLOSURE

**PARTIALLY BLIND.** Known to the author before this file was frozen, and therefore priors on the
design rather than findings of it:

- the four rejected trajectory ΔMAE values and their 79%/72% coverage drift (§1);
- the corrected-data retrain outcome (FAIL 4/4) and the WR NEW arm's recorded numbers — full-panel
  MAE 30.062, ρ 0.74640, top-24 ΔMAE +1.276, per-fold selections;
- the team-allocation audit outcome (inverted, NOT CONFIRMED) and its exact statistics;
- the corrected fixed-config WR non-rookie baseline MAE 31.071 / ρ 0.75341 (n = 1,006), and the
  n=1,006-versus-n=955 non-comparability rule;
- the measured +0.26 junk-column noise floor;
- that a structural probe run while sizing this experiment reproduced the corrected panel exactly and
  selected `catboost{4, 0.03, 3, 400}` on the 2021 BASE fold — a **baseline** selection, matching the
  retrain's own record. No challenger feature existed at that time and no challenger quantity was
  computed.

**Not inspected, and constituting the actual test:** every last-four and last-eight
full-participation feature value, the block's coverage, any FIXED-FEATURE or RESELECTED-FEATURE
prediction, and every metric of either challenger arm. None of these existed anywhere when this file
was written.

**Provenance of every bar** — none invented against an unseen number: the −0.26 MAE floor, the 2,000
draw / seed 42 / `player_id`-cluster bootstrap, the 1% RMSE tolerance, the top-24 cohort convention
and the ±10% / 25-point deploy sanity rules are all inherited from
`PREREG_corrected_data_retrain_2026-07-26.md` §6.1 / §6.3. The 3-of-5 season bar is the WR
architecture prereg's. The 60% / 40% / 10pp coverage bars and the 20-snap / 0.35 / 0.70 / p75
full-participation constants are specified in the task instruction and used unchanged.

**Multiplicity.** One position, one arm, one panel, one primary comparison, one shot.

*Locked 2026-07-26 (executed 2026-07-28) before `wr_recent_full_game_features_harness.py` existed.*

---

## 15. STRUCTURAL CHECK RECORD

*(appended by `--check`, before any challenger metric of any kind existed; nothing above this line is
edited)*

`wr_recent_full_game_features_harness.py --check`, run 2026-07-28 under
`.venv-test/Scripts/python.exe` (Python 3.11.9, numpy 1.26.4, pandas 2.3.3, scikit-learn 1.6.1,
LightGBM 4.6.0, CatBoost 1.2.10, XGBoost 3.1.2 — the same interpreter that produced the completed
corrected-data retrain).

**FROZEN SHA256 of the harness:**
`0a4c71c3bbd8ac190432490214ca0ab4f475350850b572bbfff25b7b008ea312`

**Result: PASS.**

### 15.1 The one fact that already decides the verdict — G7 fails structurally

**Recorded before the fire, from coverage counts alone, with no challenger model fitted:**

| | 2021–2025 eval | 2026 deploy | G7 bar | drop | G7 |
|---|---:|---:|---|---:|---|
| `has_last4_full` | **0.6123** | **0.5469** | ≥ 0.60 | +0.065 | **FAIL** |
| `has_last8_full` | **0.4602** | **0.3878** | ≥ 0.40 | +0.072 | **FAIL** |

Both *drop* limits hold comfortably (+6.5pp and +7.2pp against a 10pp cap) — the block does **not**
have the train/deploy drift that sank the rejected trajectory family (79%→72%) or `depth_rank`. It
fails the **absolute deploy floors**: only 54.7% of 2026 non-rookie WRs have four qualifying
full-participation games in 2025, and only 38.8% have eight.

**G7 is a conjunctive gate, so the family cannot pass, and this was known before any challenger
metric existed.** The gate is **not** re-cut, relaxed, or re-scoped, and the definition is not
changed to raise coverage. The fire proceeds exactly once as pre-registered so that the complete
G0–G8 arithmetic, the three arms' metrics, the per-season table, the top-24 effects, the deploy
movement table and the diagnostics required by the task specification are produced on the record.
**Everything the fire reports about accuracy is therefore a diagnostic, not a live promotion path.**

Per-season coverage: 2021 .586/.405 · 2022 .594/.448 · 2023 .617/.461 · 2024 .628/.492 ·
2025 .641/.500 · 2026 .547/.388. Mean qualifying games per row 6.45 → 7.48 across 2021–2025 and
**5.97** at deploy; mean excluded active games is flat at 3.88–4.60 throughout.

### 15.2 G0 reproduction, established before the fire

- **G0.1 panel identity: EXACT.** The non-rookie WR panel rebuilt deterministically from the
  corrected dataset (md5 `8322a59e…`) plus the pinned `player_stats_2011_2025.parquet` matches the
  corrected-data retrain's cached `assembled_WR_new.parquet` with **identical key sets,
  max |y delta| = 0 and max |feature delta| = 0** across all 32 baseline columns. n = 2,511 rows;
  1,006 evaluation rows over 2021–2025; 363 player clusters; 245 2026 deploy rows. No live
  `nflreadpy` pull occurs.
- **G0.2 selection identity (2021 fold, the cheap probe): MATCH.** BASE's inner LOSO CV selected
  `catboost{depth 4, learning_rate 0.03, l2_leaf_reg 3, iterations 400}` (inner MAE 36.560), exactly
  the corrected-data retrain's recorded WR non-rookie 2021 NEW selection.
- **G0.3 metric identity** is computed at fire time.

### 15.3 Probes — all PASS

| Probe | Result |
|---|---|
| noise block carries nothing | base 9.960 → +16 random cols 9.908 (Δ **−0.052**, correctly fails to clear the −0.26 floor); max abs ρ(z, y) = 0.0538 |
| planted signal detected **through the FIXED-FEATURE code path** | base 8.437 → planted 2.820 (Δ **−5.617**, clears −0.26). A harness that cannot detect a real feature cannot report the absence of one. |
| future-peek screams | walk-forward **47.34** vs future-peek **4.05** |
| feature timing | the `source_season = 2023` block, rebuilt from every weekly source truncated at 2023, is identical to the full build over 958 rows, **max abs delta 0**; the join is asserted to be exactly `season − 1` |
| feature-pool purity | BASE's 32 columns untouched and in order; challenger = those 32 followed by exactly the 16 named columns; no `sleeper` / `adp` / `depth_*` / `talent` / `y` token in either pool |

Also asserted: fold boundaries (`train.season.max() < Y`) for all five folds; postseason exclusion
inside every weekly loader (`season_type == "REG"`, `game_type == "REG"`); no duplicate
`(player_id, season)` in the panel or `(player_id, source_season)` in the block; row identity between
BASE and FIXED-FEATURE; minimum season touched = 2014, so the sealed 2008–2015 slice is never read.

### 15.4 Block construction diagnostics

12,343 `(player_id, source_season)` block rows. Of the WR-panel weekly snap rows (31,672, of which
19,118 qualify), **3,052 (9.64%) have no weekly stat row, but only 243 (1.27%) of qualifying weeks
do** — and 2,607 WR weeks carry a stat row with zero targets, so a zero-production WR week is an
ordinary, well-attested event. §6's frozen resolution (no stat row on a played week ⇒ zeros) is
therefore operating on 1.27% of qualifying weeks, not on a large hidden population. Zero weeks lack a
gameday; zero duplicate weekly keys by either id or name; the unambiguous-name fallback supplied
**35** rows. The raw snap frame's much larger global no-stat count is an artifact of it carrying
offensive linemen, who never join the WR panel.

### 15.5 Outcome-free power approximation

Computed from **structure only** — 1,006 rows, 363 player clusters, m = 2.77 rows per cluster — with
a frozen grid of *assumed* per-row paired absolute-error-difference SDs and intra-player
correlations, using the design effect `1 + (m − 1)ρ`. **No observed ΔMAE enters this calculation.**

| assumed SD | ICC 0.0 | ICC 0.3 | ICC 0.6 |
|---|---|---|---|
| 5 | MDE 0.442 / power 0.378 | 0.547 / 0.265 | 0.634 / 0.208 |
| 10 | 0.883 / 0.128 | 1.093 / 0.098 | 1.269 / 0.083 |
| 15 | 1.325 / 0.079 | 1.640 / 0.065 | 1.903 / 0.057 |
| 20 | 1.767 / 0.061 | 2.187 / 0.052 | 2.538 / 0.047 |

**Disclosed honestly and before the shot: this design is badly underpowered to certify a −0.26
effect.** On a panel whose MAE is around 30 points, the per-row paired absolute-error difference is
far more likely to sit in the 10–20 range than at 5, which puts power at the material effect between
**0.05 and 0.13** and the 80%-power detectable effect at **0.9 to 2.5 MAE points** — three to ten
times the bar. Read the consequence the way §5.1 of the allocation-audit prereg reads it: a **PASS**
would be meaningful at any of these, while a **FAIL** carries an inflated false-negative risk and
will be stated as a weak negative rather than dressed up as a clean null. G2's requirement that the
bootstrap upper bound sit below zero is, on this panel, the binding statistical constraint, and it is
a demanding one.

### 15.6 Integrity

29 protected artifacts snapshotted; all 10 pinned hashes verified; **byte-identical before and after
`--check`**. No challenger metric — no MAE, RMSE, Spearman, bias or bootstrap for any arm — was
computed or printed by `--check`.

---

## 16. OUTCOMES

*(appended after the fire; nothing above this line is edited)*

**FIRED 2026-07-28, once, wall clock 79 minutes, exit code 0. Harness SHA256
`0a4c71c3bbd8ac190432490214ca0ab4f475350850b572bbfff25b7b008ea312`, verified unchanged immediately
before the shot and unchanged after. No harness defect surfaced during execution.**

# VERDICT: REJECT — RECENT FULL-PARTICIPATION FEATURES

**Six of nine gates fail. The block makes the model worse on every primary axis.**

### 16.1 Exact G0–G8 arithmetic

| Gate | Required | Measured | Result |
|---|---|---|---|
| **G0** | walk-forward + baseline reproduces the corrected-data baseline | selections match; **n 1,242, MAE 30.06241 vs target 30.062, ρ 0.746405 vs target 0.74640** | **PASS** |
| **G1** | ΔMAE ≤ **−0.26** | **+0.1338** | **FAIL** — wrong sign; misses by 0.394 |
| **G2** | bootstrap 95% **upper** bound < 0 | **[−0.3056, +0.5722]** | **FAIL** — upper +0.5722 |
| **G3** | Δρ ≥ 0 | **−0.00275** | **FAIL** |
| **G4** | MAE better in ≥ **3 of 5** seasons | **1 of 5** (2023 only) | **FAIL** |
| **G5** | top-24 ΔMAE ≤ +0.26 **and** Δ\|bias\| ≤ 2.0 | ΔMAE **+0.6140**, Δ\|bias\| +0.4921 | **FAIL** on MAE; bias limb passes |
| **G6** | ΔRMSE ≤ +1.0% | +0.0827 (**+0.19%**) | **PASS** |
| **G7** | deploy L4 ≥ .60, L8 ≥ .40, drops ≤ 10pp | **L4 0.5469, L8 0.3878**; drops +0.0654 / +0.0725 | **FAIL** on both floors |
| **G8** | slate within ±10%; >25-pt movers explained | **−0.27%**, 2 movers | **PASS** |

**G7 was already failing at `--check`, before any challenger model was fitted** (§15.1). No gate was
re-cut, and the shot was taken as pre-registered to put the full arithmetic on the record.

### 16.2 Arm metrics — primary panel, n = 1,006, 363 player clusters

| Arm | MAE | RMSE | ρ | bias | median bias | pred SD (actual 69.89) |
|---|---:|---:|---:|---:|---:|---:|
| **BASE** | **30.9757** | 43.5112 | **0.75615** | +1.315 | −3.929 | 58.32 |
| **FIXED-FEATURE** | 31.1095 | 43.5939 | 0.75339 | +1.151 | −4.018 | 58.76 |
| **RESELECTED-FEATURE** | 31.0851 | 43.7286 | 0.74854 | +0.761 | −4.506 | 58.91 |

RESELECTED−BASE ΔMAE **+0.1094**, bootstrap [−0.4971, +0.7144], ρ **0.74854 vs 0.75615**.
**The report-only arm is also worse, and worse on rank than FIXED-FEATURE**, so re-running selection
rescues nothing. Season-clustered t(4) on ΔMAE: **p = 0.2499**.

Note on comparability: BASE here is the **nested-selected** corrected baseline (30.9757). It is not
the 31.071 fixed-config LightGBM figure recorded in
`memory/seasonal-wr-negative-gap-experiments-2026-07.md`; different selection procedure, same panel.

### 16.3 Per-season

| Season | n | MAE BASE | MAE FIXED | ΔMAE | ρ BASE | ρ FIXED |
|---|---:|---:|---:|---:|---:|---:|
| 2021 | 210 | 36.0768 | 36.4515 | **+0.3747** | 0.67331 | 0.67100 |
| 2022 | 212 | 29.8402 | 30.0149 | **+0.1747** | 0.70337 | 0.69851 |
| 2023 | 193 | 27.9230 | 27.7432 | **−0.1798** | 0.81364 | 0.81299 |
| 2024 | 199 | 31.9855 | 32.0070 | **+0.0215** | 0.77024 | 0.77862 |
| 2025 | 192 | 28.6724 | 28.9291 | **+0.2567** | 0.81991 | 0.80775 |

The single improving season, 2023, improves by less than the noise floor, and its ρ still falls.

### 16.4 Frozen top-24 cohort (BASE rank, byte-identical rows in all arms), n = 120

| Arm | MAE | ρ | bias |
|---|---:|---:|---:|
| BASE | 51.6880 | **0.27799** | −5.696 |
| FIXED-FEATURE | 52.3020 | **0.22003** | −6.188 |
| RESELECTED-FEATURE | 52.7062 | 0.23219 | −5.631 |

**The draftable cohort is where the block does most damage**: ΔMAE +0.6140, and within-cohort rank
correlation falls **0.278 → 0.220**. The established WR deficiency is within-cohort discrimination;
this block moves it the wrong way.

### 16.5 The mechanism did not do what the hypothesis said

**The exclusion proxy is not principally catching injury exits.** On the 12,154 excluded active WR
weeks:

- median `offense_pct` **0.180**, median `offense_snaps` **12** — these are low-usage rotational
  weeks, not "played most of the game and left";
- **72.5%** fail both floors, 24.4% fail the share floor alone, only **2.5%** fail the 20-snap floor
  alone;
- **ρ(excluded active games, `prior_games_missed`) = −0.0857** over n = 2,427 — essentially zero and
  slightly *negative*. Players with more excluded games are **not** the players who missed more games;
- classification splits **57.5% ISOLATED / 42.5% TERMINAL_RUN** (all positions: 53.7% / 46.3%).

So the second of the two elements that justified this second look — *filtering probable partial-game
injury exits* — is in practice **removing genuine low-role games**, which is the failure mode §5's
caveat anticipated. `prior_active_games_excluded` was carried precisely to preserve that negative role
information, and it lands at gain rank **36 of 48**.

**The block is used and is still useless.** It takes **15.52%** of total gain in the FIXED deploy
LightGBM, spread thinly: best block column is `last4_half_ppr_pg` at rank **16 of 48** (1.96% gain),
and both flags `has_last4_full` / `has_last8_full` take **zero splits**. This is not the
`talent_score` pattern of a feature the model ignores — the trees spend real capacity on it and
predict slightly worse.

### 16.6 Coverage and 2026 deploy

Coverage rises monotonically through the panel (L4 .586→.641, L8 .405→.500 across 2021–2025) and then
**falls at deploy to .547 / .388** — the 2026 non-rookie WR slate simply contains more players without
four or eight qualifying 2025 games. Slate mean **47.04 → 46.92 (−0.27%)**; only **2** movers beyond
±25 points, both with fully populated windows and a generic cause visible in the block columns:
Puka Nacua −33.5 (12 qualifying games, 4 excluded) and Jaylen Waddle +26.9 (15 qualifying, 1
excluded). **Neither is evidence of anything** and no named-player movement was used in any gate.

### 16.7 Team-allocation movement — report-only, and it moves the wrong way

On the non-rookie-only panel (160 admissible team-seasons; **not** comparable in level to the audit's
1,242-row panel — only the movement is meaningful): allocation error **+0.026639 → +0.028478**
(+0.001838), rank 1–2 share residual **−0.013320 → −0.014239**, rank 7+ **+0.003998 → +0.007531**.
Every one of the three moves **away** from zero. Consistent with the audit's finding that there is no
allocation defect to fix, and this block does not improve the statistics anyway.

### 16.8 Cohort by prior-season games played (report-only)

`0` games n=65 −0.048 · `1–8` n=218 −0.001 · `9–12` n=168 **+0.417** · `13–16` n=363 +0.043 ·
`17+` n=176 **+0.340**. The block is worst on the 9–12-game cohort — exactly the interrupted-season
players it was designed to describe.

### 16.9 Pre-committed reading, applied

**REJECT is final.** No threshold change, no window change, no last-four-only or last-eight-only or
flag-only ablation, no alternate cohort, no season removal, no redefinition of full participation, no
alternate percentile, no player-specific rescue. Per §10.2 this closes the block whole.

Read honestly against §15.5: this design was **underpowered** to certify a −0.26 effect
(power ≈ 0.05–0.13 at plausible SDs). That caveat protects a *small negative*; it does not apply
here. The point estimate is **+0.1338 — the wrong side of zero** — rank correlation falls, 4 of 5
seasons worsen, the draftable cohort worsens by more than twice the noise floor with ρ dropping
0.278 → 0.220, the report-only reselected arm is also worse, and G7 failed on coverage before a model
was fitted. Low power does not rescue a result that is negative on every axis at once.

**Within-season recent-role information for non-rookie WRs is now closed across two independent
families**: the rejected trajectory family (slopes, ramps, halves) and this levels-plus-exclusion
family. Combined with the rejected cross-season role state, role *timing* has been tested three ways
and has produced nothing.

**No production change is implemented or recommended.** No model, projection, board file, overlay or
dataset was touched.

### 16.10 Integrity

**29 protected artifacts byte-identical before and after both `--check` and `--fire`; drift 0.** All
10 pins verified, including `wr_veteran_model.pkl 17dfbcf01054bdd5ce032f2b55df9ad2`,
`wr_rookie_model.pkl 6c9a3f3ed02ce32c53594f383aade882`,
`rookie_ppg_model.pkl 872467b2295fce27761f9e04da01b6e8` and both `season_dataset` CSVs. Every
generated file is outside the repo, in `C:\tmp\wr_recent_full_game_features_2026-07-26`
(`summary.json`, `per_season.csv`, `coverage.csv`, `feature_usage.csv`, `deploy_move_WR.csv`,
`full_game_exclusion_audit.csv`, `fire.log`). The retrain scratch was read read-only for the rookie
panel and nothing there was edited. The two repo files created are this prereg and the harness.

**Concurrent-modification disclosure.** The working tree was clean at session start; `.git/index` was
rewritten at **12:03:50 ET on 2026-07-28 by a process other than this task**, staging a large
repository reorganization (preregs → `fantasy/projections/preregs/`, pages → `site_pages/`, tests →
`tests/`, plus modified `app.py`, `CLAUDE.md`, `README.md`). None of the fire's inputs were among the
changed paths and every protected artifact survived byte-identical. Nothing was staged, committed,
reverted, cleaned or absorbed by this task. **Note for the record:** this prereg and its harness were
written to the paths named in the task specification, which is one directory above where that
reorganization has since moved the other preregs.
