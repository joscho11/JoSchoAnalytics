# PRE-REGISTRATION — CORRECTED-DATA RETRAIN EVALUATION, QB/RB/WR/TE (2026-07-26)

**STATUS: DESIGN LOCKED, NOTHING FITTED ON CORRECTED DATA.** One shot, four independent position
verdicts. Everything is fitted and scored in a scratch directory; no production pkl, result CSV,
dataset, board file or analyst-overlay file is written. Joseph approves before the fire.

---

## 0. QUESTION

The seven shipped projection pkls and all four stored walk-forward panels were produced from the
**pre-fix** `season_dataset_2014_2026.csv` (commit `3b4cde0`). The dataset was rebuilt on 2026-07-26
after 14 data-correctness fixes (commit `f394ca1`) and the models were never retrained.

**Should each position's model be rebuilt on the corrected dataset?** Answered position by position,
never as a bloc, and never on the grounds that a rebuild is newer or that particular 2026 players rise.

---

## 1. BLINDNESS DISCLOSURE — this is PARTIALLY BLIND and outcome-aware

The following corrected-data results are **already known to the author** and must be read as priors on
this design, not as independent confirmation of it:

1. **A corrected-data WR improvement is on record.** On the `season_dataset`-direct WR non-rookie panel
   (n=955), the July 26 fixes moved fixed-LightGBM MAE **32.213 → 31.972** and rank correlation
   **0.7480 → 0.7520**, better in 3 of 5 seasons, with a paired interval crossing zero. The
   production-shaped n=1,006 corrected baseline is MAE **31.071** / ρ **.75341**. These two panels are
   not mutually comparable.
2. **Corrected-data, fixed-config full-panel baselines exist for all four positions**, produced by
   `PREREG_position_projection_calibration_2026-07-26.md` §11 and recorded there: MAE **51.570 QB /
   37.705 RB / 30.139 WR / 21.486 TE** on the 2021–2025 panel, against the shipped nested-selected
   panels' **53.107 / 37.969 / 30.722 / 21.383**. Those pairs differ in *both* data version and
   selection procedure, which is precisely what §5 below decomposes — but the author has seen an
   indicative direction (corrected looks better at QB/RB/WR, marginally worse at TE) and that is
   disclosed rather than presented as a discovery.
3. **The `qb_changed` findings are known** (§7): pre-fix deploy was a hard 0 on all 923 rows against
   31.4% ones in training; post-fix it is honest NaN on all 923 against 1.8% NaN in training; and the
   shipped LightGBM models convert that NaN back to 0 (`MissingType::None`), so the fix is currently
   inert at deploy — max |Δ| 0.00 at every position.
4. The depth-chart parsing fix and the rejected affine-calibration test are both on record and both
   completed before this prereg was written.

**Consequence.** Gates are inherited from existing repo conventions (§6.1) rather than chosen against
these numbers, the attribution design was fixed before any corrected model was fitted, and no
corrected-data *nested-selection* result of any kind exists yet. This can justify or reject a
production retrain recommendation; it is not a sealed hold-out and establishes no market edge.

**Multiplicity.** Four positions, tested independently. Disclosed; positions are not pooled.

---

## 2. THREE FROZEN ARMS — the attribution design (requirement 7)

| Arm | Data | Learner selection | Isolates |
|---|---|---|---|
| **OLD** | pre-fix `season_dataset_2014_2026.csv`, extracted read-only from git `3b4cde0` into scratch | the inherited `nested_select` (§3) | the shipped system |
| **MID** | corrected dataset on disk | the **per-fold `(family, params)` frozen from OLD**, applied verbatim | **the data effect** |
| **NEW** | corrected dataset on disk | the inherited `nested_select`, re-run | **the total effect** |

**Attribution, pre-committed:** data effect = MID − OLD; model-selection effect = NEW − MID; total =
NEW − OLD. Reported per position, per panel, per season. There is no fourth arm and no variant.

**Reproduction gate (hard).** The OLD arm must reproduce the four stored
`*_walkforward_predictions.csv` files **exactly** — same `(player_id, season)` key set and predictions
equal to the stored values within 1e-9 after the stored rounding. If any position fails to reproduce,
that position is **STOPPED and reported**, not analysed: a non-reproducing OLD arm means the attribution
is not identified. The fire may continue for the positions that do reproduce.

---

## 3. INHERITED, UNMODIFIED PROCEDURE

Everything below is taken verbatim from the committed position preregs and the shipped builders. **No
element of the architecture is changed by this evaluation.**

- Universe, routing (`is_rookie`), target (`season_total_target()`: regular-season
  `fantasy_points + 0.5·receptions`, rostered-never-played = 0), and the frozen rookie-matrix joins:
  each position's own `build_*_projection.py::assemble()`.
- Feature pools verbatim: `VET_ALL` (32) / `ROOK_ALL` (41) for RB, `WR_VET_ALL` (32) / `WR_ROOK_ALL`
  (44), `TE_VET_ALL` / `TE_ROOK_ALL` (44), `QB_VET_ALL` / `QB_ROOK_ALL` (39).
- Model slate and grids verbatim: CatBoost (16), LightGBM (8), XGBoost (16), ElasticNet (9), selected
  **solely** by inner leave-one-season-out CV on training seasons, MAE primary — `nested_select()`,
  unmodified.
- Walk-forward: outer folds **2021–2025**, train strictly on seasons < Y; deploy fit on all seasons
  ≤ 2025. `walk_forward()` / `fit_final_model()`, unmodified.
- Missing-data rule: native NaN for trees; median + missing-flag for ElasticNet.
- Seed 42 throughout.

The frozen rookie harness under `fantasy/rookie/harness/` is executed **read-only in a temp directory**,
exactly as the shipped builders do; its locked manifest is not touched.

---

## 4. FROZEN PANELS, KEYS AND ROW-SET HANDLING

**Key:** `(player_id, season)`. Asserted unique within every arm × position; a duplicate stops that
position.

**Row-set change is expected and is handled explicitly, not silently.** The corrections moved 19
players between the rookie and non-rookie arms and changed target/feature availability, so the OLD and
NEW panels need not contain identical rows.

- **PRIMARY panel = the matched intersection** of the OLD and NEW key sets, per position, 2021–2025,
  veteran and rookie arms merged. All paired statistics are computed here and only here.
- **Row-set delta is reported, never hidden:** counts and player names for OLD-only and NEW-only rows,
  plus each excluded group's actual-outcome mean and baseline error, so a favourable intersection
  cannot be manufactured by attrition.
- **SECONDARY:** each arm's own full panel, reported side by side with its own n.

**Forecast-known top cohort** (requirement 5): top **24 for RB and WR**, top **12 for QB and TE**, by
prediction within `(position, season)`, ties by first occurrence — the convention frozen and used in
`PREREG_position_projection_calibration_2026-07-26.md` §5.3.

- **PRIMARY top cohort = defined by the OLD arm's ranking**, held byte-identical across all three arms,
  so the cohort comparison is paired.
- **SECONDARY top cohort = each arm's own ranking**, reported separately with cohort membership churn,
  because a retrain legitimately changes who is in the top cohort.

**Fences.** Seasons 2008–2015 sealed — asserted no season < 2016 is scored. 2020 is not an evaluation
season. Sleeper/ADP appear nowhere in any fit, gate, selection or cohort definition; Sleeper is reported
only as untouched context.

---

## 5. FROZEN METRICS

Per position, per arm, per panel, and per test season: **MAE, RMSE, Spearman, mean bias
(`actual − prediction`), median bias, prediction SD versus actual SD.**

Paired deltas (NEW−OLD, MID−OLD, NEW−MID) carry a **paired player-clustered bootstrap**, 2,000 draws,
seed 42, resampling `player_id` clusters — the convention from the WR PPG-architecture prereg.

Season-level: the per-season paired ΔMAE, the count of seasons in which the corrected arm is not worse
by more than the noise floor, and the season-clustered two-sided t(4) p-value (reported always, per
Joseph's standing instruction).

**Model-selection change (requirement 7)** is reported as a table: per position, arm and fold, the
`(family, params)` chosen by OLD versus NEW, with the count of folds whose family changed and whose
hyperparameters changed.

**2026 deploy movement (requirement 6)** is computed in scratch from the NEW deploy fit: per position,
the slate mean/median/SD move and the full per-player OLD→NEW table, sorted by absolute move. **This is
a scratch scoring run. `--refresh-deploy` is never invoked, and the corrected scratch matrices are
never scored with the pre-fix production pkls.**

---

## 6. DECISION GATES

### 6.1 Provenance of every bar

| Bar | Value | Source |
|---|---|---|
| Noise floor | **0.26 MAE** | The RB session's *measured* junk-column floor: adding any pure-noise 33rd column costs +0.26 MAE on average over 20 nulls. A data-version change may not cost more than a junk feature costs. |
| Bootstrap | 2,000 draws, seed 42, `player_id` clusters | WR PPG-architecture prereg |
| Season breadth | ≥ 4 of 5 | H4 (≥4 of 6), stricter than the WR architecture prereg's 3 of 5 |
| Rank tolerance | Δρ ≥ −0.005 | Half the 0.010 pooled-Δρ bar used by the A4 extension gate |

### 6.2 Framing — non-inferiority, deliberately

The corrected dataset is **independently established as more correct**: `target_share` now sums to
1.0000 per team-season instead of averaging 1.384, postseason games no longer inflate `prior_games`
(565 bad rows → 0), team codes are canonical across three feeds, 27 Arizona players no longer carry NaN
on their 4th and 5th most-split features, and draft capital is no longer joined from an unguarded
1980-onward name match. Requiring the retrain to *win* on accuracy would be the wrong test — a more
correct input can legitimately score neutrally. The gate is therefore **non-inferiority plus stability**,
and "newer" alone is explicitly not sufficient: a position that cannot demonstrate non-inferiority does
not ship.

### 6.3 Gates — per position, all must hold (evaluated on NEW versus OLD, PRIMARY panel)

| # | Gate |
|---|---|
| **R0** | The OLD arm reproduces that position's stored walk-forward predictions exactly |
| **R1** | Paired `MAE_NEW − MAE_OLD ≤ +0.26` |
| **R2** | Paired player-clustered bootstrap 95% **upper** bound on that ΔMAE `< +0.50` |
| **R3** | `ρ_NEW − ρ_OLD ≥ −0.005` |
| **R4** | Per-season ΔMAE ≤ +0.26 in **≥ 4 of 5** seasons |
| **R5** | Frozen top-cohort ΔMAE ≤ +0.26 **and** `abs(bias)` does not increase by more than 2.0 points |
| **R6** | RMSE: `RMSE_NEW − RMSE_OLD ≤ +0.010 × RMSE_OLD` |
| **R7** | `depth_rank` and `source_pos_rank` absent from **every** feature pool at all four positions (hard assert; requirement 10) |

**R8 — 2026 deploy sanity, REPORTED AND STOP-ON-BREACH, not silently gated.** If the position's 2026
slate mean moves by more than ±10%, or any player moves by more than 25 points without an identifiable
corrected-data cause, the fire **stops for that position and reports** rather than issuing a
recommendation. Single-player 2026 point estimates are unstable at roughly ±8 under trivial
perturbation, so no move under 10 points is interpreted at all.

### 6.4 The `qb_changed` blocking condition (requirements 8 and 9)

This is **not** a gate on the retrain's accuracy; it is a separate blocking condition on *shipping* one.

**Measured and reported for every position:** training versus 2026-deploy missingness for every pooled
feature; the retrained model's recorded LightGBM missing-type for `qb_changed`; its split count and gain
share; and the deploy prediction sensitivity to `qb_changed ∈ {NaN, 0, 1}` under the **NEW** scratch
model (the analogue of the measurement already made on the shipped pkls).

**Pre-committed rule:** if any pooled feature has **deploy missingness ≥ 50% while training missingness
≤ 5%**, then that position's retrain **may not ship until a separate pre-registered decision on that
feature is made.** On the corrected data `qb_changed` is 100% missing at deploy against 1.8% in
training, so this condition is expected to trigger at all four positions — and it triggers *by
construction*, which is exactly why it is a blocking condition and not a gate whose failure would make
the whole test decorative.

**Explicitly forbidden in this fire:** testing removal of `qb_changed`, imputing it, replacing it,
re-weighting it, or evaluating any pool that differs from the committed one. Feature removal is an
unregistered rescue variant and is fenced. This evaluation measures the consequence and stops.

### 6.5 What a pass licenses

A position passing R0–R7 earns a **recommendation** to retrain on corrected data — subject to a separate
explicit production authorisation, the pkl-baseline snapshot protocol, the full regression suite, the
Streamlit AppTest all-tabs render, and resolution of §6.4. **Nothing ships from this test.** No position
is promoted because another passed. A pass licenses no claim about ranking and no claim versus Sleeper.

---

## 7. WHAT THIS TEST DOES NOT DO

- No production pkl, result CSV, dataset, board file, `wr_projection_adjustments_2026.csv` or
  `wr_player_scenarios_2026.csv` is written. All output goes to `$RETRAIN_SCRATCH`.
- `--refresh-deploy` is never invoked, and the corrected scratch matrices are never scored with the
  pre-fix production pkls — that combination is the train/serve mismatch this design exists to avoid.
- No feature is added, removed, reordered or re-weighted; no grid is changed; no fold boundary moves.
- No rejected experiment is re-run: not PPG × 16.5, prorating, loss functions, college-talent decay,
  depth tier, cross-season role state, `net_tgt_room`, H8v, or the affine calibration rejected today.
- No player is targeted. 2026 movement is reported as a full table, not curated.

---

## 8. PROTECTED ARTIFACTS

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
| `season_dataset_2014_2025.csv` | `d9f06a2fd77adae6b5b58158650fc7ea` |
| `season_dataset_2014_2026.csv` | `8322a59e43251820cb393d40787f60e6` |
| all 17 CSVs in `fantasy/projections/results/` | recomputed and compared by the harness |
| `wr_player_scenarios_2026.csv` | recomputed and compared |

`fantasy/talent/*` and `C:/tmp/talent_build/` are not touched.

---

## 9. HARNESS

`fantasy/projections/corrected_data_retrain_harness.py`

- `--check` — **structural only.** Extracts the pre-fix dataset from git into scratch and verifies its
  blob hash; assembles all four positions on **both** data versions; asserts keys, uniqueness,
  intersections, row-set deltas, time boundaries, sealed-season fence, pool purity (R7) and the
  Sleeper/ADP fence; runs the synthetic probes; runs **one cheap reproduction probe** on the smallest
  arm; prints the measured runtime estimate and all protected hashes. It computes **no corrected-model
  nested selection, no corrected-model metric, and no rescored 2026 projection.**
- `--fire` — the one shot: OLD, MID and NEW arms, the reproduction gate, all metrics, the attribution
  decomposition, the 2026 deploy table, the §6.4 diagnostics and the mechanical gate arithmetic.

Required probes: synthetic noise, synthetic planted signal, deliberate future-peek, per-fold time
boundaries, identical-row assertion between arms, pool purity, and before/after hashes.

---

## 10. STRUCTURAL CHECK RECORD

`corrected_data_retrain_harness.py --check` run 2026-07-26, **before any corrected-data nested
selection, corrected-model metric or rescored 2026 projection existed.**

**SHA256 of the frozen script:**
`c3a34c5b1053f3b689deeda44bb29994462956bc1b7187c0d6c048546a1fec07`

**Result: PASS.**

- Protected artifacts: 28 files snapshotted, all 10 pinned hashes match, byte-identical before and after.
- Pre-fix dataset extracted read-only from git `3b4cde0` (blob `782c831d…`, md5 `8d301a19…`, 2,977,749
  bytes) into scratch; asserted different from the corrected file on disk (md5 `8322a59e…`).
- Synthetic probes all PASS: noise |ρ| 0.0136; planted signal ρ 0.9838; **future-peek walk-forward MAE
  44.67 versus peek 4.02.**
- **R7 pool purity holds:** neither `depth_rank` nor `source_pos_rank`, and no `depth_*` token, appears
  in any of the 8 feature pools across all four positions.
- Sealed fence and time boundaries asserted; Sleeper/ADP absent from every arm.

**Panels — the row sets are perfectly matched, which was not guaranteed:**

| Position | OLD n | NEW n | matched | OLD-only | NEW-only | arm-moved |
|---|---:|---:|---:|---:|---:|---:|
| QB | 430 | 430 | **430** | 0 | 0 | 0 |
| RB | 802 | 802 | **802** | 0 | 0 | 0 |
| WR | 1242 | 1242 | **1242** | 0 | 0 | 0 |
| TE | 677 | 677 | **677** | 0 | 0 | 0 |

The 19 players the corrections moved between the rookie and non-rookie arms are all 2026 deploy rows, so
the 2021–2025 evaluation panels are identical row sets. §4's row-set machinery therefore has nothing to
exclude, and the paired comparison is complete rather than an intersection of convenience.

**Reproduction probe: EXACT.** QB rookie 2021 (the cheapest arm) selected
`lightgbm{num_leaves:15, lr:0.03, n_estimators:400}`, matched 10/10 rows, and reproduced the stored
predictions with **max |delta| = 0** after the stored 1-decimal rounding (unrounded 0.0496784, bounded
by the 0.05 rounding half-step). This confirms three things at once: `3b4cde0` is the correct pre-fix
data version, the OLD arm reproduces the shipped pipeline exactly, and the attribution decomposition is
identified.

**Two harness defects were found and fixed by this check, both before any result existed:**

1. The future-peek probe originally could not fire. Its synthetic target was so learnable that the
   walk-forward arm already sat on the irreducible noise floor, leaving a peeking model nothing to win
   (44.67 → 4.50, failing a `< 0.7×` bar). Rebuilt with a **season-specific** effect — `f0`'s
   coefficient flips sign in the test season — so only a model that has seen the test season can get it
   right. It now reads 44.67 versus **4.02**. A probe that cannot detect leakage is worse than no probe.
2. The R0 reproduction comparison used a `< 1e-6` tolerance against the **rounded** stored values, while
   §2 of this prereg correctly specifies "after the stored rounding". The shipped builders write
   `np.round(pred, 1)`. Corrected to round before comparing. A three-run determinism measurement
   confirmed the pipeline is **bit-deterministic** (run-to-run delta exactly 0, multi- and
   single-threaded), so no tolerance is warranted beyond the rounding itself — the gate stays at exact
   equality rather than being loosened.

**Expected runtime: ~331 min (5.5 h)** for the two nested-selection passes — 96 `nested_select` calls
across 4 positions × 2 arms × (5 outer folds + 1 deploy fit) × 2 data versions. The MID arm and all
scoring add ~2 minutes; assembles are cached. The cost model is
`(18.7 + 0.0041 × train_rows)` seconds per inner season, calibrated on this machine and validated
against a directly measured 1.3-minute `nested_select` (481 rows, 4 inner seasons). The grid is
inherited and is not pruned to save time.

---

---

## 11. OUTCOMES

*(recorded after the fact on 2026-07-26; nothing above this line was edited)*

Fired exactly once with the frozen script, SHA256
`c3a34c5b1053f3b689deeda44bb29994462956bc1b7187c0d6c048546a1fec07`, wall clock **295 minutes**
(estimate was 331). Exit code 0. No harness defect surfaced during execution.

### VERDICT: NO POSITION EARNS A RETRAIN RECOMMENDATION. All four FAIL.

| Position | R0 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| QB | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | **FAIL** |
| RB | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | **FAIL** |
| WR | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | **FAIL** |
| TE | PASS | **FAIL** | **FAIL** | PASS | **FAIL** | **FAIL** | **FAIL** | PASS | **FAIL** |

**R0 reproduced exactly at every position** — 430/430, 802/802, 1242/1242, 677/677 keys aligned, max
|delta| **0** after the stored 1-decimal rounding. The OLD arm is a true baseline, so every delta below
is a real effect and not baseline error. Row sets matched perfectly (0 OLD-only, 0 NEW-only, 0
arm-moved) at all four positions, so the paired comparison is complete.

### Full panel — the corrected rebuild is neutral-to-positive at three positions

| Position | OLD MAE | MID MAE | NEW MAE | data (MID−OLD) | selection (NEW−MID) | total | boot95 of total | ρ OLD → NEW |
|---|---:|---:|---:|---:|---:|---:|---|---|
| QB | 53.109 | 51.896 | **51.191** | **−1.213** | −0.704 | **−1.917** | [−4.107, +0.053] | .69522 → .70740 |
| RB | 37.970 | 37.811 | **37.773** | −0.159 | −0.038 | −0.197 | [−0.933, +0.480] | .68896 → .69229 |
| WR | 30.720 | 30.748 | **30.062** | **+0.028** | **−0.686** | −0.658 | **[−1.251, −0.041]** | .73613 → .74640 |
| TE | 21.380 | 21.697 | 21.854 | **+0.317** | +0.156 | **+0.474** | [−0.096, +1.051] | .73353 → .73235 |

Season-clustered t(4): QB p=0.074, RB p=0.581, WR p=0.363, TE p=0.375. Per-season ΔMAE — QB
−2.01/−1.03/−4.06/−2.97/+0.54; RB −1.17/−0.26/−0.04/+0.72/−0.16; WR −1.09/−2.82/−0.06/+0.65/+0.16;
TE +1.42/−0.75/+1.01/+1.25/−0.59.

### Forecast-known top cohort — R5 is the binding gate everywhere

| Position | OLD MAE | NEW MAE | ΔMAE | OLD bias | NEW bias | Δ\|bias\| | ρ OLD → NEW | R5 fails on |
|---|---:|---:|---:|---:|---:|---:|---|---|
| QB top12 | 70.567 | **66.702** | **−3.865** | −10.839 | −13.167 | **+2.328** | **.21428 → .46674** | bias only |
| RB top24 | 69.204 | 69.961 | **+0.757** | +22.892 | +21.844 | −1.048 | .22130 → .20237 | MAE only |
| WR top24 | 50.047 | 51.323 | **+1.276** | −0.734 | −3.271 | **+2.537** | .25397 → .24400 | both |
| TE top12 | 37.703 | 38.524 | **+0.821** | −0.626 | +3.233 | **+2.607** | .30829 → .35150 | both |

**The single clearest result: the corrected data does not hurt the full panel — and sometimes helps it
— while consistently failing the draftable cohort.** R5 is the binding gate at all four positions, and
at QB it fails on bias alone while top-12 MAE improved by 3.865 and top-12 rank correlation **more than
doubled, .214 → .467**. Reported as FAIL mechanically; no gate is re-cut after the fact.

### Attribution — the two positions that improved did so through different channels

- **QB: a data story.** −1.213 of the −1.917 full-panel gain is the corrected data; selection adds
  −0.704. The top-12 ρ jump .214 → .464 is almost entirely MID, i.e. data.
- **WR: a selection story.** The data channel is **+0.028 — nothing.** The entire −0.658 gain arrives
  through selection, and the mechanism is visible in the fold table: OLD chose **ElasticNet** for the
  2021 and 2022 veteran folds; on corrected data the inner CV picks CatBoost and LightGBM. The
  corrections did not make WR predictions better, they changed which model the frozen procedure picks.
  A bare re-run of selection could have found that without any correction, so this is **not** evidence
  for the corrected data at WR.
- **RB and TE: neither channel does anything useful.** RB total −0.197 with an interval spanning zero;
  TE is worse on data (+0.317) *and* selection (+0.156).

Model-family changes were rare: 0 at RB, 1 (TE vet) and 2 each at QB rookie and WR vet. Most folds moved
hyperparameters only.

### 2026 deploy movement (R8, scratch scoring only)

| Position | n | slate mean OLD → NEW | move | movers >\|25\| | R8 |
|---|---:|---|---:|---:|---|
| QB | 87 | 88.4 → 77.6 | **−12.2%** | 23 | **BREACH — STOP AND REPORT** |
| RB | 215 | 47.1 → 45.5 | −3.2% | 14 | within |
| WR | 394 | 38.0 → 38.1 | +0.3% | 11 | within |
| TE | 195 | 30.9 → 30.0 | −2.9% | 0 | within |

QB breached and is reported, not recommended. Its movers are almost uniformly downward (Mayfield −81.2,
Darnold −67.9, Stroud −67.6, Caleb Williams −61.1, Stafford −58.5, Lawrence −56.9, Herbert −55.6), with
Lamar Jackson +54.4 the lone large riser.

**Two WR movers independently confirm a fixed bug.** Mario Williams 91.6 → **14.3** is the unguarded
draft-capital name join that had a 2026 WR inheriting the 2006 #1 overall pick; the pre-fire prediction
recorded in the bug list was "~15". Anthony Smith 94.6 → 9.4 is the same class. Also large: Puka Nacua
+46.3, Smith-Njigba +28.0, Olave +25.6; Diggs −48.0, Hill −45.2, Keenan Allen −37.2.

Full per-player tables preserved at `$RETRAIN_SCRATCH/deploy_move_{QB,RB,WR,TE}.csv`.

### §6.4 blocking condition — TRIGGERED at all four positions, and it is not cosmetic

| Position | `qb_changed` train missing | deploy missing | retrained deploy mean: NaN vs 0 |
|---|---:|---:|---|
| QB | 2.4% | **100.0%** | 72.87 vs 83.19 → **−10.32** |
| RB | 1.6% | 100.0% | 54.91 vs 55.55 → −0.64 |
| WR | 2.0% | 100.0% | 47.05 vs 47.12 → −0.07 |
| TE | 2.2% | 100.0% | 35.10 vs 35.08 → +0.02 |

**Retraining is what makes the honest NaN real, and at QB it costs about 10 points of slate.** The
shipped models recorded `MissingType::None` and routed NaN exactly as 0 (measured Δ 0.00 at every
position before this run). The retrained models route 100% of deploy rows down a NaN branch learned
from roughly 2% of training rows. That is the depth-rank failure mode, arriving through a different
feature, and it accounts for a large share of QB's −12.2% R8 breach.

Per §6.4 this is a **shipping blocker** at all four positions regardless of the gate outcomes. No
imputation, removal or replacement of `qb_changed` was attempted, tested, or scored during this run.

### Pre-committed reading, applied

No position passes, so **no retrain is recommended and nothing is promoted.** The production models,
datasets, boards, result CSVs and overlays are untouched. Specifically:

- **The corrected dataset is still the more correct dataset.** This result does not say otherwise. It
  says that rebuilding the *existing architecture* on it does not clear a non-inferiority bar on the
  cohort that matters, which is a statement about the architecture's sensitivity to these inputs, not
  about the inputs' quality.
- **The retrain question is not reopened by tweaking this test.** Rejection is final for this design:
  no alternate cohort size, no re-cut gate, no per-arm rescue, no partial adoption of "just the QB
  data effect".
- **`qb_changed` now has its own question**, and it is the more urgent one: a feature that is 100%
  missing at deploy against ~2% in training cannot be carried into any retrained model without a
  separate preregistered decision. That decision governs any future retrain attempt.

### Integrity

Protected artifacts asserted at entry and re-asserted at exit: **unchanged**. The 7 projection pkls,
`rookie_ppg_model.pkl`, both `season_dataset` CSVs, all 17 result CSVs and
`wr_player_scenarios_2026.csv` are byte-identical. `--refresh-deploy` was never invoked and no corrected
scratch matrix was ever scored with a pre-fix production pkl. All scratch artifacts and the full log are
preserved under `$RETRAIN_SCRATCH` (16 assembled panels, 4 deploy-move CSVs, `fire.log`).
