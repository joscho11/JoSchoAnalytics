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
