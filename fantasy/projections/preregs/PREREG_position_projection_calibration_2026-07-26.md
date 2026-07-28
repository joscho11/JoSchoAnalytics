# PRE-REGISTRATION — GENERIC POSITION-LEVEL PROJECTION CALIBRATION (2026-07-26)

**STATUS: DESIGN LOCKED, NOTHING FITTED.** One-shot, four independent position verdicts. Written after
a read-only Phase-0 audit whose numbers are recorded in §2 and §3; **no calibrated (challenger)
prediction, metric, or player value of any kind has been computed.** Joseph approves before the fire.

---

## 0. QUESTION AND MECHANISM

**Question.** Does a generic, market-independent, rank-preserving affine calibration of a position's raw
season-total half-PPR predictions correct the *drafted-player* level/dispersion compression without
damaging overall out-of-fold accuracy?

**Mechanism claimed.** The models are fitted with an MAE objective on a deep-roster universe in which a
large share of rows are near-zero outcomes. An MAE learner estimates a conditional **median**. The target
is strongly right-skewed, so the conditional median sits below the conditional mean, and prediction
dispersion is compressed relative to outcome dispersion (measured: predSD/actSD = 0.834 QB, 0.685 RB,
0.815 WR, 0.763 TE on the full out-of-fold panel). If the resulting error is a *level and scale* error,
one positive affine map per position fitted on strictly earlier out-of-fold predictions should reduce
error on the forecast-known draftable cohort. If the error is instead *missing information* — the model
cannot tell which player will get the role — an affine map cannot help, because it changes no ordering.

**What this test can and cannot settle.** A positive affine map preserves within-position ordering
exactly (up to clipping ties). It therefore **cannot** address the model's ranking deficit versus Sleeper
and makes no claim to. It is the minimal instrument that separates "point-calibration defect" from
"missing-information defect", which is precisely the open question.

**Honest prior, stated before firing.** Phase 0 (§3.4) already shows the forecast-known top-cohort mean
bias is ≈0 for WR and TE and *negative* (over-projection) for QB, and materially positive only for RB.
The author's expectation is therefore **FAIL at QB/WR/TE and at best a marginal pass at RB.** This
expectation is recorded so that a pass cannot be claimed as confirmation of a prior, and a fail cannot be
retro-fitted into "we knew it".

---

## 1. BLINDNESS DISCLOSURE (required reading before accepting this prereg)

This test is **PARTIALLY BLIND and explicitly outcome-aware.** Everything in §2–§3 was computed
read-only before this document was written, including:

- the 2026 cross-position Sleeper gap table and its top-cohort decomposition;
- the full-panel and Sleeper-covered historical out-of-fold level/accuracy tables;
- actual-outcome-decile bias and prediction-versus-actual SD ratios for every position and arm;
- **the forecast-known top-cohort baseline bias, MAE, RMSE, Spearman, per-season signs, and
  player-clustered bootstrap SDs** — i.e. the baseline arm of the primary panel is fully known;
- deploy model families and hyperparameters read out of the protected pkls;
- an exact reproduction of the shipped 2026 veteran projections from the pre-fix dataset.

What has **not** been computed and does not exist anywhere: any calibrated prediction, any calibration
coefficient, any challenger metric, any calibrated 2026 player value.

**Consequence.** The gates in §7 are set against a baseline that is already known. They are therefore
inherited from pre-existing repo conventions wherever possible (§7.1) rather than chosen to be
clearable, and the primary-panel definition, its sizes, and the metric were fixed before any calibration
was fitted. This is outcome-aware method development. It can justify or reject a production calibration
layer; it cannot establish market edge, and it is not a sealed hold-out.

**Multiplicity.** Four positions are tested independently. Under the null, the chance that at least one
of four clears a p ≤ 0.05 gate is ≈18.5%. Any single-position pass must carry that sentence. The four
positions are not pooled and are not required to move together.

---

## 2. PROVENANCE MAP (Phase 0, verified 2026-07-26)

| Artifact | Produced by | From which data | Verified how |
|---|---|---|---|
| `models/{qb,rb,wr,te}_{veteran,rookie}_model.pkl` (7 files; no QB rookie model exists) | `build_*_projection.py --ship`, 2026-07-21/22 | `season_dataset_2014_2026.csv` **as of commit `3b4cde0`** (pre-fix) | mtimes + MD5s below |
| `results/*_walkforward_predictions.csv` (4 files) | same `--ship` runs, 2026-07-21/22 | same pre-fix dataset | mtimes; seasons 2021–2025 only |
| `results/{qb,rb,wr,te}_projection_2026.csv` | `build_*_projection.py --refresh-deploy`, **2026-07-24 18:24** — existing pkls, no retrain | same pre-fix dataset | **Exactly reproduced**: scoring the protected pkls on the pre-fix 2026 non-rookie rows returns the shipped values with max abs delta **0.0** and 100% exact matches at all four positions (QB 87/87, RB 144/144, WR 240/240, TE 129/129) |
| `season_dataset_2014_{2025,2026}.csv` on disk now | `build_season_dataset.py` after the 14 correctness fixes | rebuilt 2026-07-26 09:34 | committed in `f394ca1` |

**Train/serve state.** The shipped models and every shipped result CSV are internally consistent: both
sides are pre-fix. They are **not** consistent with the corrected dataset now on disk. Rescoring the
protected pkls on the corrected 2026 rows moves the veteran means by only −0.50 to −1.28, but individual
players move by up to 13.7 (WR), 23.7 (TE), 33.9 (RB) and 40.7 (QB). The largest single driver is
`vacated_target_share`, whose training mean moved 0.392 → 0.267 and 2026 deploy mean 0.342 → 0.233 when
the share bug was fixed.

**Deploy model families** (read from the pkl bundles): all seven are LightGBM, `objective="mae"`,
`random_state=42`, `n_estimators=400`. Params — QB vet `num_leaves=31, lr=0.03`; RB vet, WR vet, TE vet,
TE rook `num_leaves=15, lr=0.03`; RB rook `num_leaves=15, lr=0.06`; WR rook `num_leaves=31, lr=0.06`.
The stored walk-forward folds were nested-CV selected per fold and are **not** uniformly LightGBM: WR
veteran folds 2021 and 2022 selected **ElasticNet**, and QB rookie folds 2022/2023 selected XGBoost. The
shipped WR/QB out-of-fold panels are therefore heterogeneous in model family across seasons. This is a
material reason the primary analysis (§5) does not use them.

**Scoring units are not mismatched.** On the 67 out-of-fold QB seasons with realized ≥ 250 half-PPR
points, mean Sleeper 316.3 versus mean actual 315.3, mean ratio 1.012, median 0.989. Sleeper's QB column
is on the same scale as the target. The QB gap is not a units bug.

---

## 3. PHASE-0 FINDINGS THAT THIS TEST IS BUILT ON

### 3.1 Confirmed correctness defect — depth-chart schema (reported, not fixed here)

`build_rb_projection.py:122` filters `dc[dc["position"].astype(str) == "RB"]`. Verified against
`nflreadpy.load_depth_charts(seasons=2014..2026)`: the combined frame has 1,328,109 rows, but only
2014–2024 rows carry `season` and `position`. 2025 (554,215 rows) and 2026 (372,120 rows) use the ESPN
daily-snapshot schema (`dt, team, player_name, espn_id, gsis_id, pos_grp, pos_abb, pos_slot, pos_rank`)
and carry NaN in both columns, so `.astype(str)` yields `"nan"` and **100% of 2025 and 2026 rows are
silently dropped**. Surviving RB rows per season: 2,431 … 3,017 for 2014–2024, **0 for 2025 and 2026**.

`build_season_dataset.py::_load_qb1_week1` (lines 341–372) already handles both schemas correctly.

**Blast radius: zero for any shipped number.** `depth_rank` was removed from both feature pools by
RB prereg Amendment 1 and is absent from `VET_ALL`/`ROOK_ALL` and from every WR/TE/QB pool. The bug
silences a disclosure-only column. **Amendment 1's stated premise — "nflreadpy depth charts end at
2024" — is factually false and should be corrected on the record**; the correct premise is a provider
schema change. Fixing the filter and revisiting the amendment is a separate change, not part of this
test, and is not folded into it.

### 3.2 Confirmed defect — the corrected `qb_changed` NaN does not reach the trained models as "unknown"

Pre-fix, `qb_changed` was 0% NaN in training (mean 0.314) and **hard 0 for all 923 2026 deploy rows** —
a definite "the quarterback did not change" claim for every team, false for roughly a third of them. The
2026-07-26 fix makes it honest NaN on all 923 rows (training 1.8% NaN).

Scoring the protected pkls on the 2026 non-rookie rows with `qb_changed` set to 0 versus NaN gives
**max absolute change 0.00 at every position.** LightGBM records `MissingType::None` for a feature with
no missing values in training and routes NaN exactly as zero. So the corrected "honest unknown" is
silently converted back to a hard "no change" by every shipped model. Setting `qb_changed = 1` instead
moves the QB veteran mean by −5.76 and the RB mean by −1.37, so the feature is not inert — the *fix* is,
until a model is retrained on data that contains the NaN. `qb_changed` carries 1.47% of QB veteran split
gain over 139 splits.

This is recorded as a finding. It is not fixed here and is not calibrated over.

### 3.3 The models are prior-production extrapolators at **all four** positions

On the 2026 non-rookie slate, Pearson correlation of the shipped projection with `prior_half_ppr`:
**QB 0.940 (n=74), RB 0.930 (n=130), WR 0.936 (n=211), TE 0.950 (n=122)**. No non-rookie in the
bottom half of prior production projects above 97.8 (QB), 67.7 (RB), 81.1 (WR), 33.9 (TE), against
slate maxima of 325.5 / 237.2 / 227.1 / 158.8. `prior_half_ppr` is the top gain feature at every
position (17.6–27.6%). The RB-session diagnosis generalises across the board.

The named 2026 QB outliers are all short-prior-season availability cases, not defects: Jayden Daniels
7 prior games / 114.28 prior points → 102.4; Kyler Murray 5 / 77.78 → 97.8; Malik Willis 4 / 51.18 →
23.0; Brock Purdy 9 / 177.38 → 160.8; Tyler Shough 11 / 157.96 → 115.6. `prior_games +
prior_games_missed = 17` for every one of them; no arithmetic defect was found.

### 3.4 The premise "the models suppress draftable players" is FALSE at three of four positions

Defining the draftable cohort the only way a forecast can — **by the raw model's own within-position
rank** — and measuring bias as `actual − prediction` on the shipped out-of-fold panel:

| Position | Full panel bias | Sleeper-covered bias | Top-cohort bias (mean) | Top-cohort bias (median) | Seasons under-projected |
|---|---:|---:|---:|---:|---:|
| QB (top 12) | +8.73 | +15.52 | **−10.84** | +8.24 | 1 / 5 |
| RB (top 24) | +7.14 | +18.91 | **+22.89** | +27.15 | **5 / 5** |
| WR (top 24) | +0.15 | +6.14 | **−0.73** | +6.50 | 2 / 5 |
| TE (top 12) | +3.35 | +10.00 | **−0.62** | −8.95 | 2 / 5 |

Per-season top-cohort bias: QB +29.0 / −10.1 / −25.2 / −21.8 / −26.1; RB +6.5 / +26.0 / +1.2 / +46.6 /
+34.1; WR −5.3 / +22.7 / +19.5 / −14.9 / −25.6; TE +23.0 / −12.8 / +5.6 / −14.1 / −4.8.

**Only RB shows a real, season-consistent level deficit on the forecast-known cohort.** The
actual-outcome-decile picture that motivated this investigation (top-decile bias −57.9 WR, −102.6 RB,
−117.9 QB, −51.2 TE) is an outcome-conditioned diagnostic and does not survive translation to a cohort
definable at forecast time. The Sleeper-covered column is the market's cohort, not ours, and Sleeper's
own bias explains most of the 2026 gap (§8).

**The real top-cohort defect is discrimination, not level.** Within the top cohort, prediction SD
collapses to 24.7 (QB), 25.3 (RB), 19.8 (WR), 24.8 (TE) against actual SDs of 93.1 / 85.1 / 68.4 / 49.7,
and Spearman inside the cohort is 0.214 / 0.221 / 0.254 / 0.308. **No rank-preserving map can repair
that.** This is pre-committed as the expected reading of a failure.

### 3.5 Baseline arm of the primary panel, shipped out-of-fold predictions (hash-pinned)

| Panel | n | clusters | MAE | boot SD | RMSE | bias | predSD | actSD | ρ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QB full | 430 | 138 | 53.107 | 3.405 | 78.134 | +8.732 | 96.717 | 115.984 | .695 |
| QB top12 | 60 | 28 | 70.563 | 7.854 | 90.449 | −10.841 | 24.715 | 93.116 | .214 |
| RB full | 802 | 300 | 37.969 | 1.914 | 54.768 | +7.144 | 54.764 | 79.935 | .689 |
| RB top24 | 120 | 50 | 69.202 | 5.770 | 85.793 | +22.891 | 25.265 | 85.053 | .221 |
| WR full | 1242 | 457 | 30.722 | 1.045 | 43.126 | +0.146 | 55.484 | 68.082 | .736 |
| WR top24 | 120 | 51 | 50.045 | 4.008 | 65.136 | −0.734 | 19.844 | 68.427 | .254 |
| TE full | 677 | 235 | 21.383 | 1.185 | 31.049 | +3.352 | 36.484 | 47.845 | .733 |
| TE top12 | 60 | 28 | 37.706 | 3.570 | 46.229 | −0.623 | 24.799 | 49.739 | .308 |

(bias = `actual − prediction`; boot SD = one-sample player-clustered bootstrap SD of MAE, 2,000 draws,
seed 42.)

---

## 4. FROZEN CHALLENGER — exactly one

For each position independently:

```
calibrated = max(0, a_pos + b_pos * raw_prediction)
```

`(a_pos, b_pos)` = ordinary least squares of `actual` on `raw_prediction`, intercept included, fitted on
the pooled **out-of-fold** rows (veteran and rookie arms together) of that position from **strictly
earlier seasons only** (§6). One fit per (position, test season). No weights, no robust loss, no
winsorising, no cohort selection, no per-arm split, no per-season-band split.

**There is no second candidate.** Not isotonic regression, not splines, not quantile mapping, not
separate rookie/veteran fits, not rank buckets, not caps, not a shrinkage parameter, not a grid over any
of these. Rejection is final for the positive affine map; a different post-processor would require a new
prereg opening with the admission that it is a second look.

**Why the positive affine map and nothing else.** It preserves within-position ordering exactly, so any
Spearman change is a pure clipping artifact and is asserted as such; it is the *only* two-parameter
family that can move level and dispersion simultaneously; it cannot encode Sleeper or ADP because
neither enters its fit; and it is the minimal instrument that distinguishes a point-calibration defect
from a missing-information defect. Choosing among several post-processors after seeing results would be
gate-shopping.

**Degenerate-fit rule, pre-committed.** If the fitted `b_pos ≤ 0` for any test season at a position, the
challenger is undefined there and **that position is recorded FAIL by construction.** It is not rescued
by refitting, by dropping the intercept, or by constraining `b`.

---

## 5. FROZEN PANELS

### 5.1 ANALYSIS A — PRIMARY: corrected-data, fixed-configuration scratch panel

The stored walk-forward CSVs cannot serve as the primary base layer for two reasons recorded in §2:
their model family changes across seasons at WR and QB, and they contain no out-of-fold prediction for
any season before 2021, so a strictly-time-respecting calibration could not be fitted for the 2021 fold.
A feasibility probe measured that regenerating the nested-CV selection is not viable — a single
`nested_select` call on the smallest RB veteran training set (2014–2017) did not complete in 600 s, so
the 64 calls the full series would need are a multi-hour job with no scientific benefit here.

Analysis A therefore fixes the learner:

- **Data:** the corrected `season_dataset_2014_2026.csv` now on disk, assembled through each position's
  own `build_*_projection.py::assemble()` (identical target, joins, routing and frozen rookie matrix).
  The frozen rookie harness under `fantasy/rookie/harness/` is executed **read-only in a temp directory,
  exactly as the shipped builders do, and is not modified** — its locked manifest is untouched.
- **Learner (frozen, inherited not chosen):** LightGBM, `objective="mae"`, `random_state=42`,
  `n_estimators=400`, at each position-arm's **shipped deploy hyperparameters** read from the pkl
  bundles in §2. QB has no shipped rookie model; its rookie arm is pinned to the **QB veteran** deploy
  config (`num_leaves=31, lr=0.03`) — declared here, not selected.
- **Out-of-fold series:** seasons **2018–2025**, each trained strictly on seasons < S. 2018 is the first
  because 2014–2017 is the shortest training history that still spans four seasons; 2016/2017 folds
  would train on two or three seasons and are excluded for that reason, decided here and not after any
  result.
- **Evaluation seasons: 2021, 2022, 2023, 2024, 2025** — identical to every shipped prereg.
- **Calibration-fit seasons for test season Y: all of 2018 … Y−1.** 2021 is therefore evaluated and is
  **not dropped**.

Analysis A's baseline arm is an exact corrected-data scratch refit of each position's existing
architecture, so it also answers secondary question 2 directly.

### 5.2 ANALYSIS B — SECONDARY, REPORT-ONLY: the shipped out-of-fold predictions

Base layer = the four stored `*_walkforward_predictions.csv` files, taken verbatim, hash-pinned:

| File | MD5 |
|---|---|
| `qb_walkforward_predictions.csv` | `fff920ee50f6fa022ae6a81f0b042091` |
| `walkforward_predictions.csv` (RB) | `eb2a810153ee17084beb284be70e3787` |
| `wr_walkforward_predictions.csv` | `f78723f0fc3d45ca1bca5af3a82cd721` |
| `te_walkforward_predictions.csv` | `ff696393b529a21c4cea480ccbbf8c0c` |

(The harness recomputes and prints all four and compares them against the live files; the table is
documentation, the recomputation is the contract.)

Calibration for test season Y is fitted on stored out-of-fold rows from 2021 … Y−1. **Test seasons
2022–2025 only.** 2021 is not evaluated in Analysis B because no strictly-earlier out-of-fold prediction
exists in the shipped artifacts; this is stated, not silent, and is the reason Analysis B is secondary.
Analysis B **cannot promote anything**; it exists to show whether the conclusion transfers to the
artifacts actually on the board.

### 5.3 The forecast-known top cohort (frozen)

Within each `(position, season)` of the evaluation panel, rank rows by **raw model prediction**,
descending, ties broken by first occurrence, and keep the top **24 for RB and WR, 12 for QB and TE**.

Justification, fixed before firing: these are the startable counts in the repo's own 12-team half-PPR
convention (two RB and two WR starters, one QB and one TE), they match the top-N slices already used in
the handoff's gap tables, and they are computable at forecast time from the model alone. Sizes: 120 rows
/ 5 seasons at RB and WR, 60 at QB and TE. On the shipped panel these carry 50, 51, 28 and 28 player
clusters — **QB and TE are thin and their intervals will be wide; that is disclosed now, not used as an
excuse later.**

The cohort is defined from the **baseline** ranking and is held byte-identical for both arms, so the two
arms are compared on exactly the same rows. (Under `b > 0` the challenger's ranking is identical anyway;
the assert is belt-and-braces.)

### 5.4 Report-only panels

- Full out-of-fold panel, same seasons — carries the guardrail gates G5/G6 but is not primary.
- Sleeper-covered rows — **secondary, report-only, gates nothing.**
- Actual-outcome deciles — **explanatory only**, may never define or promote a rule.

---

## 6. LEAKAGE DISCIPLINE (hard rules)

1. A base prediction for season S is used only if its model was trained strictly on seasons < S. No
   in-sample base prediction may enter any calibration fit or any evaluation.
2. The calibration parameters applied to test season Y are fitted **only** on out-of-fold rows from
   seasons ≤ Y−1. No leave-one-season-out, no pooled-across-all-seasons fit, no refit on Y.
3. Every fold asserts `max(train season) < S` for the base model and
   `max(calibration-fit season) < Y` for the calibration layer.
4. **Seasons 2008–2015 are sealed.** The harness asserts no season < 2016 is ever scored or
   calibration-fitted. (2014–2015 remain training-only inputs, exactly as in every shipped build.)
5. **Sleeper and ADP never enter a fit.** The harness asserts the calibration design matrix contains
   exactly two columns (intercept, raw prediction) and that no Sleeper/ADP column is read on the fit
   path. Sleeper appears only in the §5.4 report-only block. Sleeper 2020 is void and 2020 is not an
   evaluation season in either analysis.
6. The target is the same `season_total_target()` used by every shipped build: regular-season
   `fantasy_points + 0.5 × receptions`, summed from weekly stats; a rostered-never-played row is 0.

---

## 7. FROZEN METRICS AND DECISION GATES

### 7.1 Provenance of every threshold

| Bar | Value | Where it comes from |
|---|---|---|
| Effect size | ≥ 3.0% relative MAE improvement on the primary panel | The repo's absolute bars are −0.25 (WR sensitivity, WR cross-season role) and −0.50 (WR PPG architecture switch) against full-panel MAEs near 31, i.e. 0.8% and 1.6%. The primary panel here is a small, high-variance cohort (MAE 37.7–70.6, 28–51 clusters), so the bar is set at roughly double the strictest existing production-switch bar in relative terms. Frozen as a percentage so it is computed mechanically from the baseline arm and cannot be tuned. |
| Full-panel damage cap | ΔMAE ≤ +0.26 | The RB session's **measured** noise floor: adding any pure-noise 33rd column costs +0.26 MAE on average (20 nulls). A calibration may not cost more on the full panel than a junk feature costs. |
| Season breadth | ≥ 4 of 5 | H4 (≥4 of 6) and H1 (≥5 of 8); stricter than the WR architecture prereg's 3 of 5 because a deterministic post-processor should be far more season-stable than a feature change. |
| Season-clustered p | ≤ 0.05, two-sided t(4) | Joseph's standing instruction from the RB session: with five folds this is the binding constraint, and it is what killed depth rank after player clustering had passed it. |
| Bootstrap | 2,000 draws, seed 42, resample `player_id` clusters | The WR PPG architecture prereg's exact convention. |

### 7.2 Metrics computed and reported (both arms, all panels)

MAE; RMSE; mean bias `actual − prediction`; median bias; prediction SD versus actual SD; Spearman;
every one of these per test season; the paired player-clustered bootstrap 95% interval of the MAE delta;
count of rows clipped at zero; the fitted `(a, b)` per position and test season.

### 7.3 Decision gates — evaluated per position, independently

A position earns a **production-calibration recommendation** only if **all seven** hold on
**Analysis A**:

| # | Gate |
|---|---|
| **G1** | Primary-panel (top-cohort) `MAE_cal − MAE_base ≤ −0.030 × MAE_base` |
| **G2** | Paired player-clustered bootstrap 95% interval for that MAE delta has **upper bound < 0** |
| **G3** | Challenger primary-panel MAE lower in **≥ 4 of 5** test seasons |
| **G4** | Two-sided paired t on the five per-season MAE deltas: **p ≤ 0.05** |
| **G5** | Full-panel `MAE_cal − MAE_base ≤ +0.26` |
| **G6** | Full-panel `RMSE_cal − RMSE_base ≤ +0.010 × RMSE_base` |
| **G7** | `b_pos > 0` for every test season, and Spearman is unchanged to within 1e-9 on the rows not clipped to zero |

Analysis B's gates are computed and printed identically **for information only**. Analysis B can never
promote a position; a divergence between A and B is reported as a train/serve transfer finding.

**Power, disclosed honestly.** The minimum detectable effect for G4 cannot be computed blind, because
the per-season delta variance of a fitted affine map is unknown until it is fitted, and simulating it
with a plausible `(a, b)` would be a preview of the challenger. What is known: five folds give t(4), so
G4 needs `|mean Δ| ≥ 2.776 × SE`. **A FAIL must therefore be headlined with a power caveat**, and a
PASS remains meaningful regardless of power. This asymmetry is the H5/P2 lesson and is accepted in
advance.

### 7.4 Pre-committed reading of every outcome

| Outcome | Reading | What it licenses |
|---|---|---|
| A position passes all seven gates | The defect at that position is **point calibration** | A recommendation to add a calibration layer for that position — **subject to a separate, explicit production authorisation**, full artifact protection, the regression suites, and the Streamlit AppTest all-tabs render. Nothing ships from this test. It licenses **no** claim about ranking and **no** claim versus Sleeper. |
| A position fails | The defect at that position is **not** point calibration | Combined with §3.4's within-cohort Spearman of 0.21–0.31, the remaining explanation is **missing point-in-time forward-looking role information**. That closes global inflation as a remedy at that position and points the next frontier at role/context features. It does **not** license starting that work — that needs its own prereg and Joseph's approval. |
| Full panel already calibrated but the top cohort stays low | **Conditional calibration / universe mismatch**, reported as such — not a universal model bias | Nothing beyond the description |
| A passes, B fails (or vice versa) | A train/serve transfer finding about the pre-fix artifacts on the board | Feeds the open "retrain on corrected data" decision; decides nothing by itself |
| Any outcome | Sleeper's rank advantage (ρ .849/.799/.797/.798 versus .730/.671/.738/.741) is **untouched** by this test and must be restated plainly in the readout | — |

**One shot. Rejection is final** — no alternative post-processor, no alternate cohort size, no threshold
change, no panel swap, no per-arm or per-band rescue, no re-fire on a different data version.

---

## 8. WHAT THIS TEST EXPLICITLY DOES NOT DO

- It does not move toward Sleeper and does not treat closeness to Sleeper as success. For context and
  never as a gate: on the shipped out-of-fold Sleeper-covered rows Sleeper is **high** by +30.9 (QB),
  +15.0 (RB), +20.1 (WR), +5.0 (TE) while the model is **low** by 15.5 / 18.9 / 6.1 / 10.0, so most of
  the 2026 board gap is Sleeper's level, not ours.
- It does not tune to Pearsall, Odunze, Burden, Worthy, McConkey or any named player, and computes no
  2026 player value at all.
- It does not re-run any rejected experiment: not PPG × 16.5 or any multiplier, not prior-total
  prorating, not a loss-function change, not college-talent decay, not depth tier, not cross-season role
  state, not `net_tgt_room`, not H8v.
- It does not touch coordinator/scheme/play-caller features. That work is fenced behind this
  diagnosis and Joseph's separate authorisation.
- It does not fix the §3.1 depth-chart bug or the §3.2 `qb_changed` routing defect. Both are reported
  for a separate decision so that no bug fix is folded into a calibration result.

---

## 9. PROTECTED ARTIFACTS AND INTEGRITY

The harness writes **nothing** into `fantasy/projections/models/`, `fantasy/projections/results/`,
`fantasy/seasonal_projections/`, `fantasy/talent/`, `fantasy/rookie/harness/`, or any board file, and
does not modify `wr_projection_adjustments_2026.csv` or `wr_player_scenarios_2026.csv`. All scratch
output goes to `$CALIB_SCRATCH` (default: a session temp directory outside the repo). `C:/tmp/talent_build/`
is not touched.

Asserted byte-identical **before and after** both `--check` and `--fire`:

| File | MD5 |
|---|---|
| `models/qb_veteran_model.pkl` | `7632549f95995b9702baefdf016d7271` |
| `models/rb_rookie_model.pkl` | `da230ee66575ca574f02cbc2139e1a80` |
| `models/rb_veteran_model.pkl` | `167aca71a8511afcced37c0abc846004` |
| `models/te_rookie_model.pkl` | `f79dad0ab26af5cb4e06a9f1723328cd` |
| `models/te_veteran_model.pkl` | `5a2f0b504d4cc6fc9a2e04453fd76a44` |
| `models/wr_rookie_model.pkl` | `6c9a3f3ed02ce32c53594f383aade882` |
| `models/wr_veteran_model.pkl` | `17dfbcf01054bdd5ce032f2b55df9ad2` |
| `fantasy/seasonal_projections/models/rookie_ppg_model.pkl` | `872467b2295fce27761f9e04da01b6e8` |
| every file in `fantasy/projections/results/` (17 CSVs) | recomputed and compared by the harness |

---

## 10. HARNESS AND STRUCTURAL CHECK

`fantasy/projections/position_projection_calibration_harness.py`

- `--check` — structural only. Builds both panels, runs every assert in §6, runs the three synthetic
  probes, prints row/cluster/season counts and the protected-artifact hashes. It **refuses to fit or
  score any calibration**: no `(a, b)`, no calibrated prediction, no challenger metric is computed or
  printed in this mode. Baseline-arm statistics may be printed because §3.5 already discloses them.
- `--fire` — the one shot. Runs `--check` first, then fits and evaluates the single frozen challenger,
  prints the full metric block and the mechanical gate arithmetic for both analyses.

Required probes (all on synthetic data, none on the real challenger):

1. **Noise probe** — a pure-noise "prediction" column must produce a calibration whose out-of-fold MAE
   is no better than the noise column's own; the harness must not manufacture signal.
2. **Planted-signal probe** — a synthetic panel where `actual = 2 × pred + 30 + ε` must recover
   `b ≈ 2`, `a ≈ 30` and show a large MAE gain; the harness must detect a real calibration error.
3. **Future-peek probe** — deliberately fitting the calibration on the *test* season must show a
   materially larger gain than the honest strictly-prior fit; the metric must scream when leaked.
4. **Time-boundary asserts** — §6 rules 1–4, per fold, per position.
5. **Identical-row assert** — baseline and challenger evaluated on byte-identical `(player_id, season)`
   keys, per panel, per position.
6. **Hash asserts** — §9, before and after.

The `--check` output and the script's SHA256 are recorded in §11 before the fire, and the fire runs
that exact code once.

---

## 11. STRUCTURAL CHECK RECORD

`position_projection_calibration_harness.py --check` was run on 2026-07-26 **before any calibration was
fitted**. It printed no calibration coefficient, no calibrated prediction and no challenger metric.

**SHA256 of the frozen script:**
`8256da3e3a32143b4b221c8212cb7f703d921db5640eac1c90e247235b88a3c1`

**Result: PASS.**

- Protected artifacts: all 7 projection pkls and `rookie_ppg_model.pkl` matched their pins; 28 artifacts
  snapshotted; byte-identical before and after the check.
- Synthetic probes, all PASS: (i) noise probe — a pure-noise predictor yields `b = +0.048` and Spearman
  is unchanged to `0.00e+00`, so the map manufactures no ranking; (ii) planted-signal probe — a known
  `y = 2·pred + 30 + ε` is recovered as `a = 28.08, b = 2.023` with a −88.7% MAE change; (iii)
  future-peek probe — base MAE 187.94, honest strictly-prior fit 115.55, deliberate test-season fit
  **8.06**, so the metric screams under leakage.
- Leakage asserts pass at every position for both analyses: no scored season below 2016, and every
  calibration-fit pool for test season Y ends at Y−1.
- Sleeper/ADP fence: no market column exists on any calibration panel.
- Identical-row contract: all 8 panels carry unique `(player_id, season)` keys; every top cohort is
  exactly `k × n_seasons`.

**Frozen panel structure.**

| Position | Analysis A OOF rows (2018–2025) | pre-2021 calibration pool | A eval full n / clusters | A top-cohort n / clusters (rookies) | B eval full n | B top-cohort n / clusters |
|---|---:|---:|---:|---:|---:|---:|
| QB | 648 | 218 | 430 / 138 | 60 / 26 (0) | 339 | 48 / 26 |
| RB | 1273 | 471 | 802 / 300 | 120 / 52 (11) | 633 | 96 / 43 |
| WR | 1971 | 729 | 1242 / 457 | 120 / 51 (0) | 979 | 96 / 44 |
| TE | 1087 | 410 | 677 / 235 | 60 / 27 (0) | 540 | 48 / 27 |

Analysis A's evaluation row counts are **identical** to the shipped panels (430 / 802 / 1242 / 677),
confirming the same universe, target and routing.

**Two structural facts discovered by the check, recorded before the fire:**

1. The QB **rookie** arm cannot produce out-of-fold folds for 2018–2020: training rows are 35 / 43 / 55,
   below the shipped engine's `len(train) < 60` guard. The QB 2021 calibration is therefore fitted on
   **veteran rows only** (218 rows, seasons 2018–2020). Disclosed here; not changed, because relaxing the
   guard would depart from the shipped engine.
2. Analysis B evaluates **2022–2025** by construction (§5.2), so its baseline numbers differ from the
   2021–2025 figures in §3.5. Both are baseline-arm statistics; neither is a challenger metric.

**Baseline arm on the frozen panels** (already disclosed in §3.5 for the shipped 2021–2025 panel; here on
the exact evaluation panels the fire will use). Note the primary-panel bias signs, which are what the
gates will be judged against:

| Pos | Analysis | Panel | n | MAE | RMSE | bias | med bias | predSD | actSD | ρ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| QB | A | full | 430 | 51.570 | 75.582 | +9.761 | −1.899 | 98.446 | 115.984 | .703 |
| QB | A | top12 | 60 | 69.483 | 86.817 | **−17.182** | −4.466 | 28.284 | 92.701 | .402 |
| RB | A | full | 802 | 37.705 | 54.540 | +7.316 | −3.226 | 55.413 | 79.935 | .692 |
| RB | A | top24 | 120 | 65.498 | 80.241 | **+17.497** | +18.631 | 26.203 | 82.536 | .293 |
| WR | A | full | 1242 | 30.139 | 43.205 | +1.700 | −3.680 | 56.791 | 68.082 | .743 |
| WR | A | top24 | 120 | 52.942 | 65.489 | **−8.011** | −9.285 | 18.848 | 69.614 | .303 |
| TE | A | full | 677 | 21.486 | 31.325 | +4.292 | −1.631 | 35.814 | 47.845 | .737 |
| TE | A | top12 | 60 | 39.376 | 46.838 | **+1.783** | −9.178 | 24.633 | 51.529 | .376 |
| QB | B | full | 339 | 53.415 | 78.681 | +9.204 | −1.400 | 96.152 | 114.759 | .706 |
| QB | B | top12 | 48 | 73.224 | 94.920 | −20.797 | −1.680 | 25.767 | 96.413 | .196 |
| RB | B | full | 633 | 38.408 | 55.527 | +7.112 | −3.700 | 55.132 | 81.391 | .696 |
| RB | B | top24 | 96 | 71.525 | 87.949 | +26.980 | +37.650 | 25.248 | 85.204 | .194 |
| WR | B | full | 979 | 29.406 | 41.330 | +1.077 | −3.300 | 55.656 | 67.754 | .755 |
| WR | B | top24 | 96 | 48.568 | 62.087 | +0.416 | +5.850 | 19.580 | 64.032 | .183 |
| TE | B | full | 540 | 21.638 | 30.955 | +2.636 | −2.700 | 36.725 | 47.587 | .735 |
| TE | B | top12 | 48 | 38.168 | 45.825 | −6.526 | −17.450 | 23.965 | 49.902 | .338 |

**The corrected-data refit does not change the §3.4 conclusion.** On Analysis A's primary panels the
top-cohort mean bias is **−17.2 (QB), +17.5 (RB), −8.0 (WR), +1.8 (TE)**. RB remains the only position
whose forecast-known draftable cohort is materially under-projected; QB and WR are *over*-projected
there. Secondary question 2 is therefore already answered: **the apparent suppression does not survive a
corrected-data scratch refit at three of four positions.**

Resulting mechanical G1 bars (3.0% of each Analysis-A primary baseline MAE), computed now so they cannot
be tuned later: **QB ≤ −2.084, RB ≤ −1.965, WR ≤ −1.588, TE ≤ −1.181.**

---

---

## 12. OUTCOMES

*(recorded after the fact on 2026-07-26; nothing above this line was edited)*

Fired exactly once with the frozen script, SHA256
`8256da3e3a32143b4b221c8212cb7f703d921db5640eac1c90e247235b88a3c1`. Joseph authorised the shot after
reading the §11 structural-check record.

### VERDICT: REJECT AT ALL FOUR POSITIONS.

No position clears any of G1–G5 on Analysis A. The positive affine calibration is not merely
ineffective; on the full out-of-fold panel it is a **statistically significant degradation at every
position**.

### Fitted coefficients — Analysis A

| Position | b by test season (2021→2025) | a by test season |
|---|---|---|
| QB | 0.8786 / 0.8956 / 0.9013 / 0.8778 / 0.8938 | 16.80 / 15.35 / 15.18 / 18.35 / 17.52 |
| RB | 0.8838 / 0.9124 / 0.9340 / 0.9401 / 0.9741 | 12.92 / 11.23 / 9.30 / 8.82 / 7.61 |
| WR | 0.9403 / 0.9130 / 0.9298 / 0.9492 / 0.9424 | 7.77 / 7.73 / 6.50 / 5.88 / 6.29 |
| TE | 0.8664 / 0.9156 / 0.9335 / 0.9503 / 0.9461 | 8.23 / 7.17 / 6.40 / 5.46 / 5.67 |

**`b < 1` in 20 of 20 fits.** The least-squares calibration wants to **shrink** predictions toward the
mean, not stretch them. This is the single most important number in the result and it is the exact
opposite of what the compression hypothesis predicts.

### Analysis A — primary results

| Position | Panel | MAE base → cal (Δ) | boot95 of Δ | seasons won | t(4) p | bias base → cal | median bias base → cal | predSD base → cal (actual) |
|---|---|---|---|---|---:|---|---|---|
| QB | full | 51.570 → 54.049 (**+2.478**) | [+1.220, +3.817] | 0/5 | **0.0068** | +9.761 → +3.544 | −1.899 → **−14.777** | 98.45 → 87.61 (115.98) |
| QB | top12 | 69.483 → 70.020 (+0.537) | [−3.255, +4.393] | 2/5 | 0.8119 | −17.182 → −2.684 | −4.466 → +9.739 | 28.28 → 25.44 (92.70) |
| RB | full | 37.705 → 39.634 (**+1.930**) | [+1.417, +2.453] | 0/5 | **0.0012** | +7.316 → +1.607 | −3.226 → **−11.375** | 55.41 → 51.51 (79.93) |
| RB | top24 | 65.498 → 65.768 (+0.269) | [−0.449, +0.967] | 2/5 | 0.4183 | +17.497 → +19.496 | +18.631 → +24.763 | 26.20 → 24.58 (82.54) |
| WR | full | 30.139 → 31.240 (**+1.101**) | [+0.782, +1.417] | 0/5 | **0.0053** | +1.700 → −1.425 | −3.680 → **−8.365** | 56.79 → 53.15 (68.08) |
| WR | top24 | 52.942 → 52.889 (−0.053) | [−1.148, +0.896] | 3/5 | 0.9517 | −8.011 → −2.853 | −9.285 → −3.995 | 18.85 → 17.80 (69.61) |
| TE | full | 21.486 → 22.524 (**+1.038**) | [+0.682, +1.408] | 0/5 | **0.0009** | +4.292 → +0.448 | −1.631 → **−7.155** | 35.81 → 33.10 (47.85) |
| TE | top12 | 39.376 → 39.328 (−0.049) | [−1.083, +0.803] | 4/5 | 0.9404 | +1.783 → +4.665 | −9.178 → −7.144 | 24.63 → 23.11 (51.53) |

### Frozen gate arithmetic — Analysis A

| Position | G1 (ΔMAE ≤ bar) | G2 (boot hi < 0) | G3 (≥4/5) | G4 (p ≤ .05) | G5 (full ΔMAE ≤ +0.26) | G6 (ΔRMSE) | G7 (rank) | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| QB | FAIL (+0.537 vs ≤ −2.084) | FAIL (+4.393) | FAIL (2/5) | FAIL (0.812) | FAIL (+2.478) | PASS | FAIL* | **FAIL** |
| RB | FAIL (+0.269 vs ≤ −1.965) | FAIL (+0.967) | FAIL (2/5) | FAIL (0.418) | FAIL (+1.930) | PASS | FAIL* | **FAIL** |
| WR | FAIL (−0.053 vs ≤ −1.588) | FAIL (+0.896) | FAIL (3/5) | FAIL (0.952) | FAIL (+1.101) | PASS | FAIL* | **FAIL** |
| TE | FAIL (−0.049 vs ≤ −1.181) | FAIL (+0.803) | PASS (4/5) | FAIL (0.940) | FAIL (+1.038) | PASS | FAIL* | **FAIL** |

\* **G7 was mis-specified and its failure is immaterial.** `b > 0` held in all 20 fits, and a post-hoc
mechanical check confirms Spearman is invariant **exactly** — |Δρ| = 0.00e+00 — within all 20
position-seasons, with zero rows clipped at zero in Analysis A. G7 as frozen measured the *pooled*
five-season Spearman, which a season-varying `(a, b)` does not preserve; the pooled shift is 6.2e-4 to
1.3e-3. Rank invariance within a draft board (one position, one season) is therefore intact as designed.
The gate text is left unedited per §7.3; the verdict is unaffected because G1–G5 fail independently at
every position.

### Analysis B — shipped out-of-fold artifacts, report-only

| Position | full ΔMAE | full t(4) p | top-cohort ΔMAE | top boot95 | top seasons won | Verdict |
|---|---|---:|---|---|---|---|
| QB | +2.054 | 0.0281 | +0.867 | [−1.986, +3.590] | 2/4 | FAIL |
| RB | +1.039 | 0.0841 | **−1.371** | [−2.811, **+0.166**] | 3/4 | FAIL |
| WR | −0.071 | 0.4913 | +1.941 | [+0.099, +3.483] | 2/4 | FAIL |
| TE | +0.921 | 0.0306 | +2.498 | [+0.457, +4.682] | 0/4 | FAIL |

RB on the shipped artifacts is the only cell anywhere that moves in the intended direction on the
primary panel (−1.371). It fails G1 (bar −2.146), G2 (interval includes zero), G3 (3/4), G4 (p = 0.165)
and G5 (+1.039 full-panel damage), and Analysis B promotes nothing by construction. Under the §7.3
one-shot rule it is **not** rescued, re-sliced or re-fired.

### Mechanism — why it fails, in one paragraph

The compression hypothesis predicts `b > 1`. The data returns `b < 1` in 20 of 20 fits, because ordinary
least squares regresses the *conditional mean* of a right-skewed outcome on a *median-like* prediction,
and that relationship is flatter than the identity. The map therefore does exactly the wrong two things
at once: it **reduces** prediction dispersion further (predSD falls at every position, moving *away*
from the actual SD in all four cases) while trading a small mean-bias improvement for a large median-bias
deterioration (QB −1.9 → −14.8; RB −3.2 → −11.4; WR −3.7 → −8.4; TE −1.6 → −7.2). MAE is a
median-aligned loss, so full-panel MAE worsens significantly at every position. On the forecast-known
top cohort the effect is close to nil in both directions (−0.05 to +0.54), which is what §3.4 predicted:
that cohort's error is not a level error.

### Pre-committed reading, applied verbatim (§7.4)

**"A position fails ⇒ the defect at that position is not point calibration."** That reading now applies
to all four. Combined with the within-cohort Spearman of 0.21–0.31 recorded in §3.4, the remaining
explanation is **missing point-in-time forward-looking role information**. Concretely, this result
closes:

- rank-preserving level/scale correction as a generic remedy, at every position;
- global inflation of the projections in any form — the honest fit points the other way;
- and, together with the already-rejected PPG × 16.5, prorating, loss-function and feature-family
  experiments, "make the point estimates bigger" as a research direction.

It licenses **nothing** about ranking. Sleeper's rank advantage on the Sleeper-covered out-of-fold rows
(ρ .849 / .799 / .797 / .798 versus our .730 / .671 / .738 / .741) is untouched by this test and is
restated here plainly, as required.

**Power caveat, carried as pre-committed.** With five folds, G4 rests on t(4). A FAIL cannot exclude a
small true effect. In this instance the caveat is close to academic on the primary panel — the observed
top-cohort deltas are −0.05 to +0.54 against bars of −1.18 to −2.08 — and it is irrelevant on the full
panel, where the degradation is significant at p ≤ 0.0068 at every position with all four bootstrap
intervals strictly above zero.

**Rejection is final.** No alternative post-processor, no isotonic or quantile variant, no alternate
cohort size, no per-arm or per-band fit, no threshold change, no re-fire on a different data version.
A future revisit requires a fresh pre-registration that opens by acknowledging it is a second look at an
answered question.

### Integrity

All 28 protected artifacts — the 7 projection pkls, `rookie_ppg_model.pkl`, all 17 result CSVs, both
`season_dataset` CSVs and `wr_player_scenarios_2026.csv` — were byte-identical before and after the
fire. No model, dataset, result CSV, board file or overlay was written.

### FACTUAL CORRECTION (2026-07-26, after the fire) — §5.1's runtime claim was wrong

§5.1 states: *"a single `nested_select` call on the smallest RB veteran training set (2014–2017) did
not complete in 600 s, so the 64 calls the full series would need are a multi-hour job."*

**That is false.** The observation was an artifact of the author's own shell pipeline — output was
buffered by a PowerShell `Select-String` filter and never reached the terminal — not of the code. The
call had almost certainly completed. Measured directly on 2026-07-26 with an in-process timer:

| Arm | Train rows | Inner seasons | Measured `nested_select` |
|---|---:|---:|---:|
| RB veteran, 2018 fold | 481 | 4 | **1.3 min** |
| WR veteran, 2025 fold (largest) | 1,875 | 10 | **~4.4 min** (full-grid timing) |

A full nested-selection pass over all four positions and both arms is therefore roughly **75–90
minutes**, not "multi-hour-with-no-benefit". §5.1's *conclusion* — fix the learner for the calibration
panel — remains defensible on its other stated grounds (the shipped folds are family-heterogeneous at
WR and QB, and fixing the learner isolates the calibration effect from selection variance), but it was
argued partly from a wrong number and that is recorded here rather than quietly dropped.

**Does this change the verdict? No.** The rejection does not rest on the base learner. Analysis B used
the *actual shipped nested-selected* out-of-fold predictions and failed at every position on the same
gates and in the same direction, and the decisive mechanism — `b < 1` in 20 of 20 fits — is a property
of regressing a right-skewed outcome on a median-like prediction, not of any hyperparameter choice.
The rules and outcomes above stand unedited.
