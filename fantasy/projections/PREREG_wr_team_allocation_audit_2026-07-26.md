# PRE-REGISTRATION — WR TEAM-LEVEL ALLOCATION / CONCENTRATION AUDIT (2026-07-26)

**STATUS: DESIGN LOCKED. NO HISTORICAL OOF ALLOCATION STATISTIC HAS BEEN COMPUTED.** This is a
**read-only audit**, not an experiment on the model. Nothing is fitted, retrained, rescored or
written into the repo. Every generated output goes to `C:\tmp\wr_team_allocation_audit_2026-07-26`.
A positive finding **licenses a separately pre-registered architecture experiment later**; it does
not license a fix, an overlay, a board change, or a model edit in this task.

---

## 0. QUESTION

Does the shipped 2026 seasonal WR model spread each team's plausible WR production **too thinly
across the offseason roster** — suppressing the receivers it itself ranks first and second, and
assigning nonzero production to mutually exclusive camp/depth candidates?

Five things are deliberately separated and must not be conflated:

1. **Team-level WR point error** (is the whole room too big/small?).
2. **Within-team allocation error** (given the room, is it split correctly?).
3. **Draft Board visibility**, an artifact of the board's ADP-filtered universe.
4. **Historical-versus-deploy roster-universe mismatch** (who gets a row at all).
5. **Stale current-roster inputs** (is the 2026 WR list even right today?).

Only **(2)** is the pre-registered primary test. (1) is the mechanism classifier. (3), (4) and (5)
are reported as descriptive diagnostics with no gate.

---

## 1. HYPOTHESIS AND MECHANISM

**Hypothesis.** The shipped WR model is *not* principally suppressing entire team WR totals. It
**under-concentrates** each team's projected WR production among the receivers it ranks first and
second.

**Mechanism (stated before the test).** The learner is a season-total point regressor whose
predictions correlate ≈0.94 with `prior_half_ppr` (recorded in `memory/daily/2026-07-26.md`). It has
no within-team competitive-exclusion channel: nothing in the 32-feature veteran pool or the 44-feature
rookie pool forces a team's receivers to compete for one finite target pool. Each row is scored
independently. Conditional-mean regression of a right-skewed outcome is also flatter than the
identity — the fired affine-calibration test measured `b < 1` in 20/20 folds — so individual
predictions are median-like and compressed. Compressed independent predictions summed over a roster
produce a flatter within-team distribution than reality, where one or two receivers absorb most of a
team's targets.

**Why this bites harder at deploy than in training.** `build_2026_board.py::seed_upcoming_rows()`
seeds a row for **every** 2026-rostered skill player from `load_rosters([2026])` — a 90-man July camp
roster — plus every drafted rookie and every ADP-holding unsigned veteran. Historical rows are
produced by `build_season_aggregates()` from `load_player_stats`, i.e. primarily players who actually
recorded regular-season statistics. So the deploy denominator contains mutually exclusive camp bodies
that the historical denominator largely does not.

---

## 2. BLINDNESS DISCLOSURE — REQUIRED READING

This prereg is **PARTIALLY BLIND and outcome-aware on the 2026 side.** The following were seen
before this design was written and are **priors on the design, not discoveries of this test**:

| Seen | Value |
|---|---|
| Historical 2021–2025 **actual** median team top-two WR share | **67.1%** |
| Historical 2021–2025 **actual** 10th percentile | **54.5%** |
| Shipped 2026 **projection** median top-two share | **53.4%** |
| 2026 teams below the historical 10th percentile | **17 of 32** |
| Washington full modeled WR room | **415.5** |
| Washington model-selected top two | Terry McLaurin **127.9** + Jaylin Lane **55.7** = **183.6** (**44.2%**) |
| Washington board-visible receivers | McLaurin **127.9** + Antonio Williams **52.0** = **179.9** (**43.3%** of the modeled room) |
| Tennessee full modeled WR room | **526.6** |
| Tennessee model-selected top two | Wan'Dale Robinson **146.9** + Carnell Tate **117.0** = **263.9** (**50.1%**) |
| Tennessee board-visible receivers | five totalling **451.5** = **85.7%** of its room |

Also already inspected: the historical **actual** concentration distribution, and the 2026 **deploy
projection** concentration distribution.

**What has NOT been inspected — and is the primary statistic of this test:** the historical
**out-of-fold predicted** allocation versus the **realized** allocation *for the same
prediction-selected leaders*. No such number exists anywhere in this repo or in any prior session.
Seeing the actual distribution and seeing the deploy distribution tells you nothing about whether the
model's own out-of-fold predictions were mis-allocated relative to the outcomes of the players it
picked — that is exactly the paired quantity being fired here.

**Consequence.** The 2026 numbers above may not be cited as evidence for the primary finding. They
are the motivation. The primary verdict rests solely on the 2021–2025 shipped OOF panel.

**Provenance of every threshold** (none invented against an unseen number):

| Bar | Value | Where it comes from |
|---|---|---|
| Material allocation effect | **5 percentage points** | Named in the task specification and used unchanged. It is roughly one third of the gap between the seen historical actual median (67.1%) and the seen 2026 projection median (53.4%) — i.e. deliberately far below the motivating anomaly, so passing is not automatic. |
| Bootstrap | **2,000 draws, seed 42, team clusters** | The workspace convention (WR PPG-architecture prereg; `PREREG_corrected_data_retrain_2026-07-26.md` §6.1). Cluster unit changed from `player_id` to `team` because the unit of analysis here is the team-season. |
| Season breadth | **≥ 4 of 5** | Inherited from `PREREG_corrected_data_retrain_2026-07-26.md` §6.1 (stricter than the WR architecture prereg's 3 of 5). |
| Level/allocation split | **±5% of pooled actual team WR points** | Task specification, used unchanged. |
| Allocation-error SD for the power calc | **0.15** | Task specification, used unchanged, and **not** estimated from the panel being tested. |

**Multiplicity.** One position (WR), one panel, one primary statistic, four conjunctive gates. No
subgroup search. The corrected-data panel is a labelled **secondary confirmation** that cannot change
the verdict (§6).

---

## 3. FROZEN DEFINITIONS

Computed per **team-season** on the primary panel. `pred` and `y` are taken **verbatim from the
stored OOF file**; targets are never substituted from the corrected dataset.

```
clip(p)               = max(p, 0)
team_pred_total       = Σ clip(pred)        over the team-season's WR rows
team_actual_total     = Σ y                 over the same rows
top-K selection       = the K rows with the largest RAW pred, descending,
                        ties broken by ascending player_id (deterministic)
pred_topK_share       = Σ clip(pred) over the K selected rows / team_pred_total
actual_sameK_share    = Σ y          over those SAME K rows / team_actual_total
allocation_error      = pred_top2_share − actual_same2_share      # PRIMARY
```

**Frozen resolution of one ambiguity, decided now, before any result exists:** the numerator of
`pred_topK_share` uses the same `clip()` as the denominator. The top-K rows are by construction the
largest raw predictions, so this differs from raw only in the degenerate all-negative case; using the
same transform on both sides keeps the share in [0, 1] by construction.

- Selection uses **prediction only**. Realized outcomes never select identities for the primary test.
- **K ∈ {1, 2, 3, 6}** is reported; **K = 2 is the primary** and the only K that can decide anything.
- **Oracle / outcome-selected** top-two shares are computed and printed as **clearly labelled
  descriptive context only.** They are inadmissible to any gate.

Also computed, all reported, none gating:

- Full-team signed point error `team_pred_total − team_actual_total` and its absolute value.
- Within-team **HHI** (Σ share²) and **normalized entropy** (`−Σ s·ln s / ln n`) for the predicted
  and the actual share vectors. Actual shares use `clip(y,0)` renormalised, so entropy is defined.
- Row counts per team-season: WR rows, rows with `pred > 0`, rows with `y > 0`.
- **Player-level residuals** by within-team prediction rank, in buckets **1 / 2 / 3 / 4–6 / 7+**:
  point residual `y − clip(pred)` and share residual `actual_share − pred_share`, where
  `pred_share = clip(pred)/team_pred_total` and `actual_share = y/team_actual_total`.

**Team canonicalisation.** `build_season_dataset.TEAM_CANON` — the production mapping — applied to
the `team` column, imported from the module rather than re-typed. Any code the mapping actually
changes is reported.

**Team identity.** The `team` column of the pre-fix dataset — the exact identity the shipped system
carries. Verified in source rather than assumed: `build_season_dataset.py:567` sets
`rows["team"] = rows["context_team"].fillna(rows["team"])`, and `add_context_team()` (line 375) defines
`context_team` as the player's **week-1 roster team**, falling back to the season stats team
(`team=("team","last")`, the season-final stats team) only for players absent from the week-1 roster
feed. So historical identity is the **preseason-knowable** team. The 2026 rows carry the 2026 roster
team seeded by `build_2026_board.py`. Prediction and outcome therefore share one identity by
construction; the residual season-final fallback is disclosed, not corrected, and its incidence is
reported.

*Amendment note (written while still blind — no allocation statistic computed): this paragraph
replaces an earlier draft that described the identity as simply "season-final team". The correction
was made by reading the source. It sharpens a provenance description and **loosens no gate, changes no
threshold, and alters no panel** — the identity used is the dataset's `team` column either way.*

**Handling of degenerate team-seasons — reported, never silently dropped:**

| Condition | Treatment |
|---|---|
| `team` missing / NaN | Excluded from team-level statistics; count and player names reported. |
| Fewer than 2 WR rows | Cannot form a top-two; excluded from the top-2 statistic only; counted and reported. |
| `team_pred_total == 0` | Predicted shares undefined; excluded; reported. |
| `team_actual_total == 0` | Actual shares undefined; excluded; reported. |
| Any other "unusual-looking" team-season | **Kept.** No team-season is excluded for looking odd. |

---

## 4. PANELS

### 4.1 PRIMARY (the only panel that can decide anything)

`fantasy/projections/results/wr_walkforward_predictions.csv` — the **frozen shipped OOF file**,
1,242 rows, columns `season, grp, player_id, player, y, pred, sleeper, model`. Evaluation seasons
**2021–2025**. Veteran and rookie arms merged, exactly as shipped.

It carries no team column, so season/team identity is attached from the **pre-fix**
`fantasy/seasonal_projections/season_dataset_2014_2026.csv`, extracted **read-only from git commit
`3b4cde0` into scratch** — the data version that produced the shipped system (established byte-exactly
in `PREREG_corrected_data_retrain_2026-07-26.md` §10). The repo copy on disk is the corrected version
and is **never overwritten**; the extracted blob's SHA is verified and printed.

- Key **`(player_id, season)`**, asserted unique on both sides. Unmatched OOF rows are reported by
  count and by name and excluded from team-level statistics.
- Join restricted to `position == "WR"` rows of the dataset.

### 4.2 SECONDARY (report-only confirmation)

Run **if and only if** the corrected-data retrain (`corrected_data_retrain_harness.py --fire`,
frozen SHA256 `c3a34c5b1053f3b689deeda44bb29994462956bc1b7187c0d6c048546a1fec07`) reached a terminal
state **and** emitted a complete NEW corrected WR OOF panel covering 2021–2025. The identical audit is
then repeated on it.

**The shipped OOF panel remains primary. The corrected panel cannot rescue a primary failure and
cannot reverse the primary verdict.** If the corrected panel is absent, partial, or the retrain
stopped, that is reported as "secondary unavailable" and changes nothing.

---

## 5. PRE-REGISTERED DECISION RULE — ONE SHOT

Primary finding is **`GENERIC UNDER-CONCENTRATION CONFIRMED`** only if **all four** hold.

| # | Gate |
|---|---|
| **A** | Pooled mean `allocation_error` **≤ −0.050**. Pooled mean = the unweighted mean over admissible team-seasons, each team-season one observation. |
| **B** | Team-clustered bootstrap of that pooled mean — **2,000 draws, seed 42**, resampling the 32 team clusters with replacement and taking all seasons of each drawn team — has a **95% upper bound < 0** (percentile interval, 2.5/97.5). |
| **C** | Mean `allocation_error` is **negative in ≥ 4 of the 5 seasons**. |
| **D** | Prediction-selected **ranks 1–2 combined** have a **positive** pooled share residual (`actual_share − pred_share`) **and** ranks **7+** have a **negative** pooled share residual. Team-clustered bootstrap intervals are reported for both; the **rank-1/2 combined interval must exclude zero**. The ranks-7+ interval is reported but is not required to exclude zero. |

**Mechanism classification** (applies only if A–D pass). Let
`level_bias = Σ(team_pred_total − team_actual_total) / Σ team_actual_total` over admissible
team-seasons:

- **`ALLOCATION-ONLY`** — A–D pass and `|level_bias| ≤ 0.05`.
- **`MIXED ALLOCATION + LEVEL`** — A–D pass and `|level_bias| > 0.05`.
- **`NO GENERIC CONCENTRATION DEFECT`** — any of A–D fails.

**One shot. Rejection is FINAL for this exact mechanism and panel.** No alternate top-K definition,
no threshold change, no team subset, no season removal, no outcome-selected identity, no
re-fire on another data version, after the shot is taken. A future revisit needs a fresh
pre-registration that opens by acknowledging it is a second look at an answered question
(Amendment 4, standing).

### 5.1 Structural power calculation — run BEFORE the fire, in `--check`

Computed from **structure only**: 32 team clusters × 5 seasons = 160 team-seasons, a material effect
of **−0.05**, and an assumed allocation-error SD of **0.15**. **No observed historical OOF allocation
error enters this calculation.** Because the within-team correlation of allocation error is unknown
before the shot, power is reported across a frozen grid of intra-cluster correlations
**ρ ∈ {0.0, 0.3, 0.6, 1.0}** using the standard design effect `1 + (m−1)ρ` with `m = 5`:

```
SE(ρ)  = 0.15 / sqrt(160 / (1 + 4ρ))
MDE    = 2.802 × SE(ρ)          # two-sided 5%, 80% power
power  = Φ(|−0.05|/SE(ρ) − 1.96)
```

Both the approximate detectable effect and the expected power at the −0.05 material effect are
**recorded in §10 before the fire**. If power is low at high ρ, that is disclosed and read as an
inflated **false-negative** risk only: a pass remains meaningful regardless of power; a fail at low
power is a weaker negative and will be stated as such rather than dressed up.

### 5.2 Pre-committed reading of both outcomes

**If CONFIRMED —** the finding is that the shipped WR architecture allocates a team's projected
receiving production too diffusely among the receivers it itself ranks first and second. It
**licenses exactly one thing: writing a separate pre-registered architecture experiment** on
within-team competitive exclusion. It licenses **no** immediate change to the model, the projections,
the board, the overlays, or any dataset; **no** claim about ranking skill; **no** claim against
Sleeper or ADP; and **no** per-player adjustment. Global level/scale correction is already closed
(affine calibration fired and rejected at all four positions, `b < 1` in 20/20 fits) — a confirmation
here is a statement about *shape within a team*, which no rank-preserving map can touch.

**If NOT CONFIRMED —** the 2026 diffusion is then attributable to the **deploy roster universe** (the
90-man camp seeding of §1), to the **board's ADP-filtered visibility**, or to **stale roster inputs** —
not to a generic learned mis-allocation. The question "does the WR model generically
under-concentrate" is **CLOSED** for this mechanism and this panel. The diagnostics in §7 remain
valid descriptive findings either way.

---

## 6. WHAT THIS AUDIT DOES NOT DO

- No model is fitted, retrained, rescored, or selected. No pkl is written or loaded for scoring.
- No dataset, result CSV, board file, page/app file, or analyst overlay is modified.
- No repo file outside the two artifacts named in §8 is created or edited.
- Nothing in the corrected-retrain scratch directory is written or edited; its outputs are read only
  after that task is terminal.
- No fix is designed, recommended, or implemented in this task.
- Sleeper and ADP are used **only** to explain board visibility. Neither is evidence that a point
  projection is correct, and neither enters any gate.
- No rejected experiment is re-run: not PPG × 16.5, prorating, loss functions, college talent,
  depth tier, cross-season role state, affine calibration.

---

## 7. NON-GATED DIAGNOSTICS (reported in full, no decision rides on them)

1. **2026 concentration, all 32 teams** — full modeled WR room, top-1/2/3/6 shares, HHI, entropy,
   row counts; full tables sorted by top-two share and by board-visible share.
2. **Draft Board visibility, 2026** — board-visible WR count, visible projection sum, and visible
   share of the complete modeled WR-room points, per team. The board universe is
   `draft_board_2026.py`'s: 2026 dataset rows with a non-null `adp_half_ppr` (~245 players, all
   positions), deduped by `player_id`.
3. **Historical-versus-deploy universe** — WR rows per team-season 2021–2025 versus 2026, and the
   share of historical rows with `y > 0`, quantifying the mismatch of §1.
4. **Washington / Tennessee case study** — the full modeled room, model-selected top two, and
   board-visible set for each, reproduced mechanically from the shipped CSVs.
5. **Current-roster audit** — the projection-file WR list for WAS and TEN compared against each club's
   current official camp roster; stale, missing and extra projection rows named; source URLs and
   access dates recorded. Specifically: the apparent **Nick Nash vs Ja'Corey Brooks** mismatch at
   Washington, and Tennessee's stated **13-receiver camp room competing for roughly six spots**.
   Written to `roster_audit.md`.

---

## 8. ARTIFACTS AND OUTPUTS

**Created in the repo (these two files only):**

- `fantasy/projections/PREREG_wr_team_allocation_audit_2026-07-26.md` (this file)
- `fantasy/projections/wr_team_allocation_audit_harness.py`

**All generated output goes outside the repo**, to `C:\tmp\wr_team_allocation_audit_2026-07-26`:
`summary.json`, `team_season_primary.csv`, `rank_bucket_primary.csv`, `team_2026.csv`,
`washington_tennessee_case_study.csv`, `roster_audit.md`, `fire.log`, plus
`team_season_corrected_secondary.csv` and `rank_bucket_corrected_secondary.csv` **only if** the
corrected NEW panel is complete.

**Harness modes:**

- `--check` — structural only: extraction and provenance verification, key/uniqueness checks,
  time boundaries (no season outside 2021–2025 scored; sealed 2008–2015 never touched), the
  synthetic test, the §5.1 power calculation, and all protected hashes. It prints **no historical OOF
  allocation result** of any kind.
- `--fire` — the single frozen evaluation and the complete report.

The harness SHA256 is frozen and printed **before** `--fire`. It fires exactly once.

**Synthetic test (`--check`).** A hand-built panel of 4 synthetic teams × 3 seasons with known truth:
one team-season constructed so the prediction is perfectly concentrated and the outcome perfectly
uniform (allocation error must read strongly positive), one the mirror image (strongly negative), and
one where prediction equals outcome (must read exactly 0.0). The harness must recover all three, and
the rank-bucket residuals must carry the matching signs. A harness that cannot detect a planted
mis-allocation cannot report the absence of one.

---

## 9. PROTECTED ARTIFACTS

Hashed **before and after** both `--check` and `--fire`; any drift **stops the task and is reported**.
Nothing is repaired or overwritten.

| Group | Files |
|---|---|
| Position models | `fantasy/projections/models/{qb_veteran, rb_rookie, rb_veteran, te_rookie, te_veteran, wr_rookie, wr_veteran}_model.pkl` (7) |
| Rookie PPG model | `fantasy/seasonal_projections/models/rookie_ppg_model.pkl` |
| Result CSVs | every existing CSV in `fantasy/projections/results/` |
| Season datasets | `season_dataset_2014_2025.csv`, `season_dataset_2014_2026.csv` |
| Board + WR overlays | `draft_board_2026.py`, `fantasy/seasonal_projections/board_adp_live_2026.csv`, `fantasy/projections/results/wr_projection_adjustments_2026.csv`, `fantasy/projections/wr_player_scenarios_2026.csv` |

Pinned expectations carried from `PREREG_corrected_data_retrain_2026-07-26.md` §8:
`wr_veteran_model.pkl = 17dfbcf01054bdd5ce032f2b55df9ad2`,
`wr_rookie_model.pkl = 6c9a3f3ed02ce32c53594f383aade882`,
`rookie_ppg_model.pkl = 872467b2295fce27761f9e04da01b6e8`.

The working tree contains unrelated, intentional, uncommitted work. It is preserved exactly: nothing
is staged, committed, reverted, cleaned, or incorporated.

---

## 10. STRUCTURAL CHECK RECORD

*(appended by `--check`, before any allocation result exists; nothing above this line is edited)*

`wr_team_allocation_audit_harness.py --check` run **2026-07-26 20:48 ET**, after the corrected-data
retrain (`bt4gpx818`) reached a terminal state at **20:47 ET** and before any allocation statistic
existed. No CPU-heavy work of any kind was run concurrently with that retrain.

**FROZEN SHA256 of the harness:**
`de1b09bd11ef963669fee17987255246c52bfe3ac3d88cf6bec853535e13f370`

**Result: PASS.**

**Provenance.** Pre-fix dataset extracted read-only from git `3b4cde0` into scratch: blob
`782c831dbd50…`, md5 `8d301a194d0f17419908d9006feda6e1`, **2,977,749 bytes** — matching the retrain
prereg §10 record exactly, and asserted **different** from the corrected file on disk
(`8322a59e43251820cb393d40787f60e6`). `TEAM_CANON` read from `build_season_dataset.py` by AST
literal-eval (not re-typed, and without importing the module).

**Keys and structure (counts only).**

| Item | Value |
|---|---:|
| OOF rows total / in 2021–2025 | 1,242 / **1,242** |
| WR rows in the pre-fix dataset, 2021–2025 | **1,242** |
| Key `(player_id, season)` unique, both sides | yes |
| Rows joining on key (`_merge == both`) | **1,242 of 1,242** |
| Rows carrying a usable team | **1,235** |
| Rows with a NaN team, excluded from team-level statistics | **7** |
| Teams / team-seasons | **32 / 160** |
| Arms merged | veteran 999 + rookie 236 = 1,235 |
| 2026 WR projection rows | 394 |
| Board universe (2026 rows with ADP, all positions) | 245 |

The key join is **complete** — every OOF row has a dataset row. The 7 exclusions are genuine
no-team player-seasons, not join failures: **Odell Beckham Jr. (2022), John Ross (2022), Calvin
Ridley (2022), Tom Kennedy (2023), Jamal Agnew (2024), Malik Turner (2024), Hunter Renfrow (2024)** —
each carries `team = NaN` because he appears on no week-1 roster and has no season stats team.

**Team canonicalisation is a no-op on the evaluation window.** `TEAM_CANON` rewrites 111 WR rows
across the full 2014–2026 dataset (OAK 41, SD 16, HST 11, BLT 11, SL 11, ARZ 11, CLV 10) — **all of
them outside 2021–2025**. Within the evaluation window there are **zero** legacy codes. The mapping is
applied as specified; it simply changes nothing here.

**Time boundaries and fences.** Seasons present: exactly {2021, 2022, 2023, 2024, 2025}, asserted. No
season < 2016 is touched; the sealed 2008–2015 slice is never read.

**Synthetic planted-mis-allocation probe: PASS.** All four constructed team-seasons recovered to
machine precision — over-concentrated `+0.666667` (expected `+0.666667`), under-concentrated
`−0.659829` (expected `−0.659829`), perfect-prediction `+0.000000`, negative-prediction case
`+0.000000` with `team_pred_total` clipping to exactly 100.0. Rank-1 share residuals carry the correct
opposing signs (`−0.3333` on the over-concentrated team, `+0.3291` on the under-concentrated one).

**Structural power (§5.1) — computed from structure only, no observed allocation error used.**

| ρ | design effect | n_eff | SE | MDE (80%) | power at −0.05 |
|---:|---:|---:|---:|---:|---:|
| 0.0 | 1.00 | 160.0 | 0.01186 | 0.0332 | **0.988** |
| 0.3 | 2.20 | 72.7 | 0.01759 | 0.0493 | **0.811** |
| 0.6 | 3.40 | 47.1 | 0.02187 | 0.0613 | **0.628** |
| 1.0 | 5.00 | 32.0 | 0.02652 | 0.0743 | **0.470** |

**Approximate detectable effect: 3.3 to 7.4 percentage points**, depending on how strongly a team's
allocation error persists across seasons. **Expected power at the material −0.05 effect: 0.99 down to
0.47.** The design is comfortably powered if allocation error is close to independent across
team-seasons and **underpowered if it is strongly team-persistent**. Recorded before the shot: a PASS
is meaningful at any of these; a FAIL at high ρ is a weaker negative and will be stated as such rather
than dressed up as a clean null.

**Secondary panel: NOT AVAILABLE, established mechanically.** The corrected-data retrain reached a
terminal state — all four positions ran, verdict FAIL at each, its own protected-artifact check clean,
script SHA256 `c3a34c5b…` matching the frozen value — but it **writes no NEW corrected OOF panel**. Its
only outputs are `deploy_move_{QB,RB,WR,TE}.csv` and `fire.log`. The harness scanned that scratch
directory for any file carrying `(player_id, season, y, pred)` across all five evaluation seasons and
found none. Nothing there was edited.

**Protected artifacts: 30 files snapshotted, all 3 pinned hashes verified, byte-identical before and
after `--check`.**

No historical OOF allocation statistic was computed or printed by `--check`.

---

## 11. OUTCOMES

*(appended after the fire; nothing above this line is edited)*

**FIRED 2026-07-26 20:49 ET. Harness SHA256 `de1b09bd11ef963669fee17987255246c52bfe3ac3d88cf6bec853535e13f370`,
verified unchanged since `--check` immediately before the shot.**

# VERDICT: NO GENERIC CONCENTRATION DEFECT

**All four gates fail, and the primary statistic carries the OPPOSITE SIGN to the hypothesis.**

### 11.1 Execution note — one interrupted run, completed; not a second shot

The first invocation was piped through `head -120`. When `head` exited it closed stdout, and the
harness died of a broken pipe after printing 191 lines and before writing its output files. That is an
I/O plumbing failure in the invoking shell, external to the frozen script; no gate, threshold, panel,
definition or seed was touched. The script was re-invoked **byte-identical** (SHA verified before and
after) with stdout redirected to a file.

**The completed run reproduces the interrupted run byte-for-byte across all 191 lines the first
attempt produced** (truncated log preserved as `fire_INTERRUPTED_2049_brokenpipe.log`, md5
`c46cda9876ea19dc1b8389a449caf113`; `diff` against the same prefix of the completed `fire.log` is
empty). The harness is deterministic — one seed, no unseeded randomness — so this is the completion of
a single shot, not a re-fire, and it exercised zero degrees of freedom. Recorded here rather than
omitted.

### 11.2 Gate arithmetic — exact

Panel: 1,242 shipped OOF WR rows, 2021–2025; 1,235 with a team; **160 admissible team-seasons of 160
(zero degenerate, zero denominator-zero, zero incomplete)**; 32 teams; veteran 999 + rookie 236.

| Gate | Required | Measured | Result |
|---|---|---|---|
| **A** | pooled mean `allocation_error` ≤ **−0.050** | **+0.012153** | **FAIL** — wrong sign; misses the bar by **+0.0622** |
| **B** | team-clustered bootstrap 95% **upper** bound < 0 | **[−0.004152, +0.028531]** (2,000 draws, seed 42, 32 clusters) | **FAIL** — upper bound +0.0285 > 0; interval straddles zero |
| **C** | mean negative in **≥ 4 of 5** seasons | negative in **1 of 5** (2022 only) | **FAIL** |
| **D** | ranks 1–2 pooled share residual **> 0** with CI excluding zero, **and** ranks 7+ **< 0** | ranks 1–2 **−0.006076** [−0.014265, +0.002076]; ranks 7+ **+0.007638** [+0.002521, +0.012839] | **FAIL** on all three conditions |

Per-season mean `allocation_error` (n = 32 each): 2021 **+0.012290** · 2022 **−0.041142** ·
2023 **+0.022406** · 2024 **+0.032693** · 2025 **+0.034517**.

**Mechanism classification is not reached** (it applies only if A–D pass). For the record, the level
term is nowhere near the band: pooled predicted **73,208.3** vs pooled actual **73,524.7**, signed
error **−316.4 = −0.43%** of actual, well inside ±5%; mean |team error| **89.43** per team-season.

### 11.3 The sign inversion, stated plainly

The model does **not** under-concentrate on its own top two. On the same team-seasons, the two
receivers it ranked first and second were projected to take **59.89%** of their team's WR points and
actually took **58.67%** — the prediction was slightly **over**-concentrated, by 1.2 percentage points.
The pattern is monotone across K: top-1 +0.0151, top-2 +0.0122, top-3 +0.0120, top-6 +0.0139.

Gate D inverts as well. The rank-7-and-deeper bucket has a **positive** share residual **+0.007638**
with a bootstrap interval **excluding zero** — those players actually earned **2.74%** of their team's
WR points against **1.98%** projected. Historically the model gave the *deep* receivers **too little**,
not too much. That is the precise opposite of "assigns nonzero production to mutually exclusive
camp/depth candidates."

**The apparent contradiction with the aggregate shape statistics is itself the finding.** Predicted
HHI **0.2424** vs actual **0.2848**, predicted normalized entropy **0.8032** vs actual **0.7181** — the
predicted distribution *is* flatter than reality. But the outcome-selected (oracle) actual top-two
share averages **0.6654** while the model's *chosen* top two realize only **0.5867**. Both facts hold
at once because the missing concentration accrues to receivers the model did **not** rank first or
second. **The deficit is identification, not allocation shape.** No change to how a team's total is
divided can recover it; it is the same within-cohort discrimination deficiency already on the record
(prediction SD 19.8 against actual SD 68.4 on the WR top cohort; "chase ranking, not points").

### 11.4 The motivating 2026 comparison was against the wrong reference

Comparing a **projection** against a distribution of **outcomes** guarantees the projection looks flat:
outcomes contain realized concentration that no forecast can have. Measured against all three
references on the same panel:

| Historical reference (2021–2025) | median | p10 | p25 | 2026 teams below p10 | below p25 |
|---|---:|---:|---:|---:|---:|
| **ACTUAL, oracle (outcome-selected) top two** | 0.6689 | 0.5353 | 0.5982 | **17 / 32** | 24 / 32 |
| **ACTUAL of the prediction-selected top two** | 0.5952 | 0.3927 | 0.5107 | **0 / 32** | 13 / 32 |
| **PREDICTED, the model's own out-of-fold top two** | 0.5967 | 0.4617 | 0.5221 | **5 / 32** | 13 / 32 |

2026 projected top-two share: median **0.5337**. The disclosed "17 of 32 below the historical 10th
percentile" reproduces exactly — against the oracle-actual reference. Against the like-for-like
reference, the model's own out-of-fold projections, it is **5 of 32**. The 2026 slate is genuinely
flatter than the model's own history, but by roughly a third of the headline.

### 11.5 What the residual 2026 flatness is, since it is not generic mis-allocation

The deploy universe, measured: **12.31 WR rows per team in 2026** against a historical mean of
**7.72 per team-season**, of which only **6.72** recorded positive points. That is **+59%** more
receivers per team than the model ever trained against, exactly as §1 predicted from
`build_2026_board.py::seed_upcoming_rows()` seeding every player on a 90-man July camp roster. Per
season the historical figure is stable (8.22 / 7.84 / 7.41 / 7.62 / 7.50), so the deploy count is not
drift — it is a different population.

Board visibility, measured: **96 of 394** modeled WRs appear on the Draft Board (24.4% of rows) but
they carry **9,940.1 of 14,550.0** modeled WR points — **68.3%**. Board-visible share of the modeled
room ranges from **10.9% (MIA)** to **88.4% (SEA)**; Washington **43.3%**, Tennessee **85.7%**.

The current-roster audit (`roster_audit.md`) found **zero** stale, missing or extra WR rows at either
Washington (11 of 11) or Tennessee (13 of 13) against the clubs' current official rosters.

### 11.6 Pre-committed consequences, applied

Per §5.2, the negative outcome means the 2026 diffusion is attributable to the **deploy roster
universe**, the **board's ADP-filtered visibility**, and **not** to a generic learned mis-allocation.

**"Does the shipped WR model generically under-concentrate its projected team WR production among its
own top-two receivers?" is CLOSED for this mechanism and this panel.** Rejection is FINAL. No alternate
top-K, no threshold change, no team subset, no season removal, no outcome-selected identity, no
re-fire on another data version. A revisit requires a fresh pre-registration that opens by
acknowledging it is a second look at an answered question.

**No architecture experiment is licensed by this result.** The finding licenses no change to the model,
the projections, the board, the overlays, or any dataset, and no fix was designed or proposed.

**Power caveat, carried honestly.** §10 recorded power of 0.99 / 0.81 / 0.63 / 0.47 at
ρ = 0.0 / 0.3 / 0.6 / 1.0. This negative is not a marginal miss that low power could explain: the point
estimate is **+0.0122 against a −0.050 bar**, the wrong side of zero by more than the entire bar, and
the rank-7+ bucket is significant **in the inverted direction**. Power would matter for a small
negative; it does not rescue an inverted one.

### 11.7 Secondary panel

**NOT AVAILABLE — established mechanically, not assumed.** The corrected-data retrain reached a
terminal state at 20:47 ET (all four positions ran; verdict FAIL at each; its own protected check
clean; SHA `c3a34c5b…`), but it writes **no NEW corrected OOF panel** — only
`deploy_move_{QB,RB,WR,TE}.csv` and `fire.log`. The harness scanned that scratch directory for any file
carrying `(player_id, season, y, pred)` across all five evaluation seasons and found none. Nothing
there was read beyond that scan and the log, and nothing was edited. Per §4.2 this changes nothing: the
shipped panel is primary and its verdict stands alone.

### 11.8 Integrity

**30 protected artifacts byte-identical before and after both `--check` and `--fire`; drift 0.** All
three pins verified: `wr_veteran_model.pkl 17dfbcf01054bdd5ce032f2b55df9ad2`,
`wr_rookie_model.pkl 6c9a3f3ed02ce32c53594f383aade882`,
`rookie_ppg_model.pkl 872467b2295fce27761f9e04da01b6e8`. Every generated file is outside the repo, in
`C:\tmp\wr_team_allocation_audit_2026-07-26`. The two repo files created are this prereg and the
harness. The pre-existing uncommitted working tree was preserved exactly; nothing was staged,
committed, reverted or cleaned.
