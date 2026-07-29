# PHASE 1 AUDIT — confirmed defects in the preliminary Arm 3 build

Raised by Joseph 2026-07-28, each VERIFIED against the code before being accepted. **Do not
interpret any current Arm 3 effect until every item below is fixed and the build re-run.**

## Status of record (corrects the earlier "nothing has been fit" claim)

- **No player-projection arm (Arms 0–5) has been fit.**
- **No outer projection result has been examined.**
- **Preliminary Arm 3 models WERE fit** — `RidgeCV` expectation models (one per season, Stage 1)
  and `RidgeCV` + `Ridge` cross-classified coach-effect models (Stage 2).
- Their alpha choices and effect magnitudes **were observed** before this audit. That observation
  is recorded here so no later choice can be made on the basis of which option yields larger
  effects.

## Confirmed defects

### 1. Midseason play-caller attribution — segments get full-season values
`build_coach_features.py` merges each play-caller segment onto the **full team-season** offense
row, so both callers in a split team-season receive identical efficiency and scheme values. Violates
the requirement to use the games each coach actually called.
**Fix:** build segment-level offense metrics from PBP restricted to `week_start:week_end`; place
partial segments against the frozen within-season league distribution for rank percentiles and
z-scores; let `g/(g+32)` shrink small segments. Assert PBP weeks fall inside the sourced range and
attributed games match the ledger.

### 2. Arm 3 midseason exposure — secondary callers discarded
Stage 2 attaches ONE primary caller per team-season, discarding the secondary caller from all 18
sourced splits.
**Fix:** game-share exposure weights in the design matrix (10 of 16 games → weight 10/16). Same for
midseason HC changes. Preserve the HC==PC collapse without duplicating the effect. Synthetic test
must assert exact weights for: full-season HC caller, full-season OC caller, midseason caller
change, midseason HC change, unknown caller.

### 3. Reliability formula is an approximation — VERIFIED at lines 110 and 116
Code computes `n_seasons / (n_seasons + 32/16)`. The frozen formula is
**`prior_games / (prior_games + 32)`**.
**Fix:** use attributed games from the HC game ledger and the play-caller segment ledger. Emit
prior games and reliability separately for HC and PC adjusted effects. Never substitute
team-season counts for games.

### 4. Arm 3 controls incomplete — VERIFIED
`prior_qb_id` is **absent** from `CONTROLS` although it exists in `personnel_controls.csv`
(alongside `prior_qb_epa_play`, `prior_qb_cpoe`, `qb_returns`, `ret_qb_attempt_share`). The comment
at line 64 claims "season fixed effect = training-season mean of the target, applied as an
intercept shift" — the implementation does no such thing; it fits numeric controls with a plain
ridge intercept and **no season indicators**. The comment overstates the code.
**Fix:** add `prior_qb_id` as a categorical with unknown handling; implement training-season effects
or write a **prefit amendment** explaining the identifiable alternative for an unseen season S.
Preprocessing (medians, categories, scaling) must be learned from training seasons only.

### 5. Ridge regularization — row-level CV and an UNRESOLVED BOUNDARY — VERIFIED
`RidgeCV` uses default row-level validation, not season-blocked. Grid is `np.logspace(-1, 3, 25)`,
max 1000.

**Boundary counts, both denominators (Stage 2 only):**
- **FIT-LEVEL (primary diagnostic): 9 of 10 target-season fits selected alpha = 1000**, the grid
  maximum. Only 2019 chose an interior value (146.78).
- **ROW-WEIGHTED: 1,194 of 1,292 effect rows = 92.4%**, because the boundary fits emitted more rows.

**Stage 1 alpha was never persisted** — `arm3_residuals.csv` carries no alpha column — so the 92.4%
figure describes **Stage 2 only** and says nothing about the expectation model. The corrected
implementation must persist Stage-1 and Stage-2 tuning diagnostics separately.

**What a boundary at the maximum means.** Ridge minimises `||y - Xb||^2 + alpha*||b||^2`. Selecting
the largest available alpha means the inner validation preferred **at least** that much
regularisation, and possibly more than the grid allowed. Widening the grid could therefore select an
even **larger** alpha and shrink the coefficient vector **further** toward zero. Tuning is
UNRESOLVED, not biased in a known direction.
**Fix:** season-blocked (leave-one-season-out or another frozen group-by-season) selection for BOTH
Stage 1 and Stage 2, with preprocessing fit inside each inner-training split; freeze a wider
log-spaced grid and a BOUNDARY PROTOCOL before running the corrected model:

1. Start from a preregistered broad log-spaced grid appropriate after scaling.
2. If an optimum lands on either boundary, expand in that direction by a preregistered number of
   decades, for a preregistered maximum number of iterations.
3. If the upper boundary is still preferred at the frozen maximum, **record that as evidence
   favouring effective complete pooling** — do not force an interior solution.
4. Report fit-level boundary counts, row-weighted counts, and Stage 1 vs Stage 2 separately.

Never enlarge the grid repeatedly until a coach effect becomes non-zero or the result looks
favourable. Do not inspect player-projection performance while choosing the grid.

### 6. The preliminary effects are UNINTERPRETABLE (corrected 2026-07-28)
Observed magnitudes: largest entering 2026 Andy Reid +0.0007 EPA/play; McDaniel +0.00004.

**These are uninterpretable — not "too small".** Two independent reasons: (a) tuning did not resolve,
because 9 of 10 Stage-2 fits sat at the grid boundary; and (b) the implementation carries defects
1-4 (segment attribution, exposure, reliability, controls). The corrected values **could increase,
decrease, change sign, or converge to zero.** No direction is implied.

**An earlier version of this file claimed the boundary "mechanically shrinks every coach effect
toward zero" and that the estimates were "very likely an artifact of defect 5". That reasoning was
BACKWARDS and is withdrawn.** A larger alpha produces *more* shrinkage, so a ceiling on alpha is a
floor on effect size, not a cause of over-shrinkage. If anything, an unconstrained grid may shrink
these further.

**A persistent preference for very large alpha may itself be a real finding** — it is consistent with
coach identities adding little predictive information once the personnel controls are in. That
possibility is explicitly NOT ruled out, and the corrected build must not be tuned until it
disappears. Only the nested player-projection evaluation supplies the verdict either way.

After the corrected build, report: residual calibration by season; expectation-model walk-forward
error; ridge alpha by target season; effect distribution; effective sample size; McDaniel and McVay
values **as routing diagnostics only**. The nested player-projection evaluation supplies the verdict.

## Gate

Phase 1 must complete before any player-projection arm is fit. Produce a
requirement-to-code matrix (prereg requirement · generating function · source columns · timing rule
· aggregation grain · missing-value rule · covering assertion · pass/fail) for every Arm 1–5 feature
family first.
