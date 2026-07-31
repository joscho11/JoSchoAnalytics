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


---

# PHASE 1C IS NOT PASSED — point-in-time staff identity is an open leakage blocker

## 7. `preseason_snapshot()` is retrospective, not point-in-time (CONFIRMED)

It derives `opening_caller_id` from the FIRST ACTUAL GAME in the attribution ledger. It never reads
`source_date`, an evidence-known date, or any projection cutoff. Its docstring claimed
"knowable at the cutoff"; the code enforced nothing of the kind.

**Measured against a Sept-1 cutoff** — opening-caller sources published AFTER Sept 1 of their own
season:

| season | late/total | | season | late/total |
|---|---|---|---|---|
| 2014 | 22/27 (81%) | | 2020 | 31/32 (97%) |
| 2015 | 21/30 (70%) | | 2021 | **30/30 (100%)** |
| 2016 | 10/27 (37%) | | 2022 | 30/30 (100%) |
| 2017 | 29/32 (91%) | | 2023-2026 | 0 |
| 2018 | 0/32 | | | |
| 2019 | 17/24 (71%) | | **TOTAL** | **190 of 392** |

## 8. A FABRICATED source_date was hiding part of the problem (NEW)

`yardbarker2021` carried `date="2021-01-01"` — a placeholder I entered because the fetch gave no
date. It is wrong, and wrong in the direction that grants FALSE preseason eligibility: an article
ranking the 2021 season cannot predate it. The real byline is **"Updated October 18, 2021"**.

Corrected. **2021 moved from 0% late to 100% late** — it was a false negative created by my own
placeholder. Other approximations remain and must be audited before eligibility is trusted:
`espn2023/2024/2025` were entered as `YYYY-08-01` from a fetch that said only "August", and
`cbs2022phi` as `2022-01-01`. A `date_precision` field (exact | month-only | inferred) is required
before any eligibility gate can rely on this column.

## 9. SELF-INFLICTED REGRESSION, caught and fixed (NEW)

Rebuilding the table to apply the source_date fix **silently reverted the v3.2 game-count
correction** — counts returned to 14/2/12/4 instead of 13/3/11/5 — because
`build_playcaller_table.py` still computed `n_games_attributed` by week arithmetic. A patch script
that a rebuild can undo is not a fix.

The correct counting now lives **inside the builder**, which is therefore idempotent: a full rebuild
reproduces 13/3/11/5, keeps the corrected 2021 date, keeps 2026 prospective counts at 17, and T0
still passes at 244/256 and 116/128. **Lesson: a correction applied by an external patch script is
not durable — it belongs in the generator.**

## 10. No production projection cutoff exists (CHECKED)

`grep` over the four position builders and `build_season_dataset.py` for
`as_of|asof|cutoff|snapshot_date|projection_date` returns **nothing**. There is no recorded
historical as-of date, so the frozen rule must be **the day before season Y's first regular-season
game**, with the live 2026 snapshot using the actual production timestamp.

## Remaining Phase 1C work before it can pass

- build the evidence-backed point-in-time snapshot (`expected_opening_*`, `*_known_date`,
  `*_eligible_at_cutoff`, `unknown_reason`) and rename the retrospective artifact
- add `date_precision` and audit every approximate source_date
- convert printed invariants into hard assertions; exact-value routing assertions
- register all tests in a discoverable suite
- emit a reproducible drive-impact artifact
- propagate the proxy renames into `build_coach_features.py` and update the requirement matrix

## 11. Caller-history left-censoring confound (Phase 1D, 2026-07-29) — OPEN

`caller_prior_games` is left-censored at 2014 while `hc_resume_prior_games` reaches back to 1999.
A veteran caller's count therefore rises with target season purely from window width (Reid: 16
entering 2015 → 192 entering 2026). Flagged per-row via `history_left_censored`, but **not
corrected**. Detection misses pre-2014 non-HC play-callers entirely.

Decision needed before caller reliability is used as a feature: (a) restrict comparisons to
within-target-season, (b) extend the caller table before 2014, or (c) carry censoring explicitly in
the model. Do not use raw cross-season caller reliability until this is settled.

## 12. Unknown-caller HC-context contamination (v3.6, 2026-07-29) — RESOLVED

`ctx_mask = ~same` credited unknown-caller games to the HC "delegated offense" block. Reid entering
2026: 245 reported delegated = **5 verified + 240 unknown** (all 1999–2013). Fixed to
`known & (hc != caller)`; unknown games now activate neither identity block and are tracked in a
separate `unknown_caller_hc_games` role. Mean unknown share across team-seasons is **0.561**, so the
contamination was large, not marginal.

Item 11 (left-censoring) is RECLASSIFIED, not fixed: reliability is now explicitly defined as
observed-sample confidence rather than career experience, so the censoring is a correct statement
about available evidence. The residual risk is only that raw game counts get read as experience —
blocked by the v3.6 feature-use policy and its test.

---

# PHASE 2 AUDIT (v3.9, 2026-07-29)

Status: point-in-time coaching representations and the nested evaluation harness are BUILT.
**No player-projection arm fit; no fantasy outcome read.** 236 registered tests pass.

## 13. Historical caller evidence was NOT point-in-time gated — FIXED in v3.9

v3.8 gated only the TARGET-season caller identity. The historical record fed Arms 1/2/4 ungated, so a
later article could build an earlier feature. Concrete case from the canonical table: **BUF 2014's
caller is attributed by an ESPN piece dated 2016-10-29**, and under the old rule that segment entered
target-2015 caller history. That is the same look-ahead leakage v3.5 removed from the snapshot,
surviving one layer down.

Design A now requires `season < Y` **and** source upper bound <= season Y's frozen cutoff. Measured:
2015 **15/27** eligible prior segments, 2019 154/163, 2026 364/378. Design B is deliberately left
ungated so A and B differ on exactly one axis. Covered by
`test_a_later_source_cannot_build_an_earlier_feature` and
`test_the_gate_shrinks_eligible_history_and_the_effect_is_measured`.

## 14. `None` became `NaN` through a DataFrame round-trip — FIXED, and it was silent

Identities were carried in a dict, put into a DataFrame (which converts `None` to `NaN`), then read
back with `is not None`. `float('nan') is not None` is **True**, so every unknown-caller row tested as
KNOWN. Three real consequences, all silent:

- `pc_changed_entering` became `float(NaN != prev_caller)` = **1.0** instead of the neutral 0.5;
- `caller_is_head_coach` became `float(NaN == hc)` = **0.0**, asserting delegation with no evidence;
- a distinct head coach collected an **Arm 3 HC-context effect on a row with no caller evidence at
  all** — precisely the v3.6 defect, reintroduced through a type coercion rather than a rule.

The quality features were unaffected only by luck (`dict.get(nan)` misses, so they fell to the
prior). Fixed by routing every identity read through `_none()`. Coverage went from a nonsensical
32/32 known in every season to the correct 152/256 on the outer window.

## 15. `df[[]]` selects zero COLUMNS, not zero rows — FIXED

The evidence gate was applied as `s = s[[eligible_at(u, cutoff) for u in ...]]`. For the first target
season no prior segment exists, the comprehension is `[]`, and `df[[]]` is an empty **column**
selection, so the next attribute access raised `AttributeError: 'DataFrame' object has no attribute
'pbp_games'`. Masks are now numpy bool arrays applied with `.loc` (`_gate_mask`).

## 16. Three different kinds of zero in the 2026 routing assertions — RESOLVED

An initial assertion demanded `context effect == 0.0` for all three pinned teams and FAILED on LAC.
It was the assertion that was wrong, not the routing:

- **LAC** — Harbaugh IS a distinct non-calling head coach, so his context coefficient legitimately
  applies, and that coefficient is **numerically** zero (2.368e-18) because entering 2026
  `alpha_hc_context` sat at the extended 1e16 upper boundary. The feature carries the fitted value and
  is NOT forced to 0.
- **LA** — McVay has NO context row in the effect table at all, so the effect appears exactly once
  and the context feature is **exactly** 0.
- **KC** — Reid DOES have a context coefficient (his 5 delegated games to Nagy in 2017), and
  self-calling routing suppresses it, so the feature is **exactly** 0.

## 17. The v3.4 companion hashes in the prereg were STALE — corrected in v3.9 §10

`preseason_staff_snapshot.csv` and `preseason_evidence_ledger.csv` were pinned at their v3.4 values
and never repinned when v3.5/v3.6/v3.7 rewrote the eligibility logic and the snapshot schema. Current
values recorded in v3.9 §10; both files predate this session and were not touched by Phase 2.

Separately: `actual_play_caller.csv` and `source_ledger.csv` have an mtime inside every suite run
because the registered test `test_rebuild_is_byte_identical` rebuilds them and asserts byte-identity.
Their **bytes are unchanged** (`98f1c66b…`, `931470c7…`). An mtime is not a change.

## 18. OPEN — Design A caller power is thin in 2019-2022

Team-seasons whose expected caller has ANY eligible prior history, out of 32:
2018 **25** · 2019 **3** · 2020 **4** · 2021 **7** · 2022 **6** · 2023 26 · 2024 26 · 2025 27.
In 2019-2022 the caller channel is nearly empty. **A null caller arm on this panel is jointly a test
of coaching signal and of archive retrievability and cannot separate them.** No gate is lowered and
the outer window is not narrowed in response.

## 19. OPEN — the neutral 0.5 level is a partial season indicator under Design A

`caller_is_head_coach` and `pc_changed_entering` take 0.5 on unknown-caller rows, which IS a
distinguishable third level, and Design A coverage is ~0% in some seasons and ~100% in others. Every
alternative is worse (0 asserts delegation, 1 asserts self-calling, NaN reopens the missingness
channel on every caller feature at once). The pre-registered control is the within-season TEAM-LEVEL
permutation placebo, which preserves each season's composition under the null. **This is a control,
not a proof of absence.**

## 20. OPEN — Arm 3 does not exist before target season 2018

Stage 1 residuals begin in 2014 and the frozen Stage 2 minimums make entering-2018 the earliest
estimable target, so 2014-2017 carry all-zero Arm 3 effects. Both inner folds for outer 2018 validate
on 2016 or 2017, so Arms 3 and 5 cannot be selected on evidence in that fold. Structural, disclosed,
not backfilled.

## 21. OPEN — head-coach identity is an assumption, not evidence-gated research

It is taken from the week-1 head coach in both designs. Defensible (HC hires are public before the
season) but it is NOT held to the pre-cutoff evidence standard applied to callers, and ARM_HC's "full
point-in-time coverage" rests on that assumption.

## 22. OPEN — `build_coach_features.py` is still unrepaired

It retains the original defects (joins on season+team, pre-v3.3 metric names). v3.9 does not use it.
It should be deleted or repaired rather than left as a loaded gun beside a working builder.

## 23. My own retired-name violation, caught by the new guard — FIXED

The v3.9 hardening added "reject retired drive names in features, manifests and outputs". It
immediately failed on **my own** Arm 2 stem, `points_per_drive_z`, which embeds the RETIRED
unqualified name. Renamed to `drive_scoring_points_per_drive_proxy_z` (= `drive_definitions.PPD_PROXY`).

The guard then had to be corrected too: `drive_scoring_points_per_drive_proxy` legitimately CONTAINS
`points_per_drive` as a substring, so a naive scan rejects the *correct* name. Retired names are now
detected only in what remains after the canonical names are removed
(`_strip_canonical_drive_names`). **The check was wrong in one direction and the feature name in the
other; both are fixed.**

## 24. Artifact scope tightened — three of my own files removed

v3.9 authorises **exactly five** new repo data artifacts. I had additionally written
`hc_game_results_v39.csv`, `production_pipeline_audit_v39.json` and
`coach_projection_experiment_spec_v39.json`. All three were untracked and created in the same session;
all three are removed. The audit/spec live in `V39_PREFIT_STOP_REPORT.md`. The head-coach win ledger was
cached in `COACH_V39_SCRATCH` at this point — a contract **RETIRED one item later** (see item 27): it is
now derived in memory from the frozen schedule snapshot on every build and cached nowhere at all.
`audit_production(write=True)` / `experiment_spec(write=True)` now RAISE, and
`test_no_unauthorized_v39_artifact_exists_on_disk` fails if a sixth `*_v39.*` file appears.

## 25. TWO production architectures exist, and my earlier audit phrasing was unscoped — CORRECTED

`fantasy/seasonal_projections/models/` holds a **legacy Model A × Model B** family (season total =
PPG × games) alongside the direct season-total family Arm 0 uses. The legacy family **does** use
categorical features (`availability_model.pkl` and `rookie_ppg_model.pkl` carry `cat_features`) and
**does** fit with `sample_weight=games` (`train_model_a.py`). My earlier statement "no categorical
handling, no sample weights" was true of Arm 0 and **would have been false as a claim about the
repo**. Now explicitly scoped in the audit, the prereg and the stop report, with a test
(`test_audit_scopes_its_no_categorical_no_weight_claims_to_the_arm0_family`).

Also recorded: **prediction clipping is asymmetric.** `np.clip(pred, 0, None)` is applied by
`_score_bundle` and the 2026 face-validity path but **not** by `walk_forward()`, so the evaluation
path is unclipped. The harness mirrors `walk_forward` and does not clip.

Also recorded (cosmetic, deliberately NOT "fixed"): every bundle's `note` says "RB season-total
half-PPR projection" even in the QB/WR/TE bundles, because those builders reuse
`build_rb_projection.fit_final_model` verbatim. `feature_cols`/`family`/`params` are position-correct.

## 37. `coverage_reconciles` WAS A SPOT-CHECK MAKING A FALSE CLAIM — FIXED (v3.9c)

It inspected only `ARM_1 / identity_state == "all"` and only two columns, then reported "coverage
reconciles with both feature tables". Corrupting `ARM_2 / known_with_history / n_team_seasons` to 999
left it **True**; only the byte-hash noticed. A deliberate rebuild plus an updated pin could therefore
have shipped a semantically false artifact with C10 green.

Now `compare_coverage()` regenerates the ENTIRE frame with `coverage()` — the builder's own function, so
there is one canonical derivation — and compares schema, key set, uniqueness and every cell.
**Lesson: a check that inspects one slice must not be described as reconciling the artifact.**

## 38. `preflight()` COULD CRASH INSTEAD OF REPORTING — FIXED (v3.9c)

Required artifacts were read outside the guarded `check()` wrapper, so deleting the Design A table raised
`FileNotFoundError` and the promised structured record never came back — the exact failure mode a
fail-closed preflight exists to prevent. All inputs are now loaded defensively; dependents report
`blocked by <input> load failure (<error>)`; the preflight never raises.

## 39. THE GENERATED LINEAGE ARTIFACT CONTRADICTED ITS OWN VALUES — FIXED (v3.9c)

The v3.9b feature values used the adopted policy, but every caller-history and caller-continuity lineage
row still carried the RETIRED `timing_rule` (RETIRED: `"…requires source upper bound <= Y cutoff"`) and
the RETIRED opener note (RETIRED: `"…openers are themselves gated"`). Both are WITHDRAWN; they are quoted
here only to identify what was removed. **An MD5 cannot see a metadata/value contradiction.** Corrected to the pinned `PRIMARY_TIMING_RULE`, with
`validate_lineage_policy()` wired into the preflight so a reintroduction fails semantically.

## 40. C10's "no-real-outcome" CLAIM HAD NO RUNTIME IMPLEMENTATION — FIXED (v3.9c)

The boundary was enforced only by tests, so C10 asserted a guarantee it did not implement and the test
could drift into a parallel definition. `no_real_outcome_access()` now lives in the harness module, is a
preflight check, and accepts injected pure source so tests exercise the same function without touching
canonical files. **Lesson: if a condition claims it, the condition must compute it.**

## 33. THE §7 DENOMINATORS WERE COUNTS, NOT DENOMINATORS — FIXED (v3.9b)

C3/C4/C8 checked only `n_improved >= 6`, `>= 4`, `n_nonbaseline >= 4`. So a truncated six-season run
satisfied "6 of 8" and four available recent seasons satisfied "4 of 5". Worse, the v3.9a stop report's
unresolved item 11 **asserted a guarantee the code did not provide**. The conditions now require the
exact frozen season SETS (`{2018..2025}`, `{2021..2025}`) plus no duplicate `(player_id, season)` cohort
rows, and every missing / duplicate / unexpected season or fold key is named in `denominator_problems`.

**Lesson: writing a limitation into a report is not the same as enforcing it in code.**

## 34. CONDITION 10 DID NOT CHECK WHAT IT CLAIMED — FIXED (v3.9b)

C10 was documented as "every timing, leakage, coverage, artifact-integrity and no-real-outcome
assertion" but checked only production hashes, the ten upstream hashes and the lock state. `preflight()`
now runs 17 deterministic checks and C10 passes only when all 17 are true; the structured record is
returned as a `preflight` frame. Each contract is proven to fail independently **on a temporary copy**,
so the corruption tests never mutate a canonical artifact.

One check is about EXECUTION rather than state: `_PIPELINE_ASSERTIONS` counts the timing / leakage /
row-identity assertions the pipeline actually ran, so "the assertions passed" cannot be satisfied by a
code path that never reached them.

## 35. THE REAL-AUTHORIZATION PARADOX — FIXED (v3.9b)

v3.9a treated an unlocked real-fit gate as an integrity failure. Correct during prefit, but it meant
**every authorized real run would automatically fail C10**, making `DEVELOPMENTAL CANDIDATE`
unreachable forever. The lock expectation is now a property of the run mode: `synthetic_prefit` requires
both locks closed, `authorized_real` requires both open, a partial state is invalid in both, and an
unknown mode fails closed. No mode relaxes any other check. Locks not opened in this pass.

## 36. THE HISTORY-GATE ARITHMETIC WAS WRONG TWICE — CORRECTED (v3.9b)

The v3.9a report claimed adopting ungated history could lift Design A known-with-history from 124/256
toward Design B's 200/256, "~76 more usable rows". **Impossible**: Design A has only 152/256 known
target identities and an unknown identity stays at the league prior regardless, so the ceiling is 152
and the arithmetic maximum gain is 28.

**Computed, the actual gain is ZERO.** All 28 outer known-no-history rows are genuine first-time callers
with no prior segment in the ledger at all — the gate never suppressed them. So the 28 bound is not
attained either. The real effect is history DEPTH: 7,274 → 7,632 caller-games (+358, +4.9%), with
**2019 gaining zero**, and exactly one row anywhere gaining history (2016 DET Jim Bob Cooter, 0 → 9).

**The stated rationale that this "avoids concentrating archive-retrievability missingness in 2019-2022"
is NOT achieved.** The policy is adopted on methodological grounds and for restoring the single-axis
Design A/B contrast — not for power. Both the 200/256 and the ~76 claims are retracted.

**Lesson: an upper bound is not an estimate. Compute the realised value.**

## 27. THE BUILD WAS NOT HERMETIC — FIXED (v3.9a)

`build_preseason_snapshot.projection_cutoffs()` and the old `hc_game_results()` both called
`nflreadpy.load_schedules()`, and the win ledger was cached in an untracked scratch directory. So a
clean offline checkout **failed five v3.9 feature tests**, and the then-reported result of
254 passes (SUPERSEDED; the suite is now 708) depended on mutable state that is not in the repo.
That is a reproducibility defect, not a cosmetic one: nobody else could have reproduced the number.

Both now read `fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet` (repo-owned, frozen,
provenance in `snapshots/manifest.json`). The win ledger is computed in memory — no sixth artifact, no
cache. Derived cutoffs are cross-checked against the `projection_cutoff` column already persisted in
`preseason_staff_snapshot.csv`; all 13 match. Suite and build both verified with egress blocked and an
empty temp dir. **Lesson: "the tests pass" is only a claim about this machine until the inputs are in
the checkout.**

## 28. THE LIVE PREREG CONTRADICTED ITS OWN BANNER — FIXED (v3.9a)

v3.9 added a correct supersession banner and left §0, §2, §3.2, §4, §5, §6, §7, §8-T5 and §8.1 asserting
the OLD policy underneath it as executable canon — retired drive names, "THE SIX FROZEN ARMS",
reliability/count fields in player X, nonexistent season fixed effects, leave-one-season-out selection,
Holm across Arms 1–5. Worse, the stop report **claimed those sections had been corrected** when only a
banner covered them.

All rewritten in place; the false claim is withdrawn in the report. A token scan over everything from
`## §0` onward now returns only the two lines that assert the corrections. **Lesson: a banner over stale
canon is not a correction, and saying it was is a reporting error in its own right.**

## 29. THE §7 PRIMARY VERDICT WAS NEVER COMPUTED — FIXED (v3.9a)

The harness produced metrics and selections but never evaluated the ten-condition developmental-candidate
rule, `experiment_spec()` did not pin the thresholds, and no test covered it. Implemented as
`primary_verdict()` with 14 covering tests including one per condition and a proof that a perfect fixed
arm in the frame cannot move the verdict.

Freezing forced a decision the prereg had left open: §7(1) said "top-cohort MAE" without choosing pooled
vs mean-per-season. **Frozen POOLED** before any outcome was visible, with the reasons recorded, and used
identically for the 3% rule and the placebo.

## 30. THE PLACEBO TESTED THE WRONG THING — FIXED (v3.9a)

It permuted bundles and then scored the **modal selected arm** as a fixed arm. The pre-registered
condition is about the nested-selected pipeline. Every draw now reruns representation selection
independently for every outer fold and may pick a different arm per fold.
`test_placebo_can_select_different_arms_in_different_folds` is the regression guard.

Consequence to plan for: the placebo is now the dominant compute cost of the real experiment.

## 31. LINEAGE OVERCLAIMED — FIXED (v3.9a)

The stop report said lineage proved source-segment/game membership; routing rows carried only aggregate
counts. Added 1,631 `caller_contribution` rows (one per candidate segment, included or excluded, with
segment key, week range, `pbp_games`, source upper bound, target cutoff, gate eligibility + reason,
career/roll3 inclusion). Deliberately recomputed independently of the build so the reconciliation test
compares two paths; it reconciles on all 416 rows of both designs.

## 32. ~~OPEN~~ **RESOLVED BY v3.9b — THE EXTRA HISTORICAL-EVIDENCE GATE IS RETIRED**

> **STATUS: SUPERSEDED. Every quantitative claim in the original text below was WRONG. Read the
> resolution first; the strikethrough paragraph is kept only so the error is traceable.**

**RESOLUTION (v3.9b, adopted).** The gate on historical segments is **retired**. The target-season
expected caller stays evidence-gated; historical performance and prior-season caller continuity use
source seasons `< Y` from the full retrospective ledger. The retired rule survives as a labelled
in-memory sensitivity (`strict_gate_sensitivity`) plus per-row diagnostic columns in the lineage
artifact. Design A vs Design B is a **SINGLE-AXIS** contrast — target identity supply only, verified on
all 51 features across all 227 identity-matching rows.

**THE ACTUAL NUMBERS, computed from code:**

| Design A, outer 2018–2025 | strict gate | primary (adopted) |
|---|---|---|
| known target identity | 152 | 152 |
| known **with** history | 124 | **124 — ZERO row gain** |
| known no history | 28 | 28 |
| caller-games of history | 7,274 | **7,632 (+358, +4.9%)** |

All 28 known-no-history rows are genuine **first-time callers with no prior segment in the ledger at
all**, so the gate never suppressed them. 2019 — the thinnest season — gains **zero** games. Exactly one
row anywhere gains history (2016 DET, Jim Bob Cooter, 0 → 9).

~~Original text: "it costs Design A up to ~76 usable rows (concentrated in the already-thin 2019–2022),
and it makes Design A vs Design B a two-axis contrast rather than one."~~ **RETRACTED.** Design A has only
152/256 known identities, so 200/256 was never reachable and the arithmetic maximum was 28, not 76 — and
the realised gain is 0. The two-axis description was true of v3.9a only and is no longer current.

Related test renames: `test_design_a_and_b_differ_only_on_identity_supply` →
`..._share_rows_schema_and_the_entire_hc_block` (it overclaimed); the v3.9a two-axis test →
`test_the_designs_differ_on_target_identity_and_that_is_the_ONLY_axis`;
`test_design_b_history_is_ungated_and_therefore_larger` →
`..._holds_more_history_because_it_KNOWS_more_identities`.

## 26. The 141 baseline is only reproducible with an explicit deselect list — CURRENT (updated v3.9d)

**Current status: the full suite is 708; the inherited baseline is 141, reproduced as `141 passed,
6 deselected`.** Reproducing it requires ignoring the four v3.9 test modules (`test_arm_features_v39.py`,
`test_coach_projection_harness_v39.py`, `test_boundary_corpus.py`, `test_assemble_real_panel_v39.py`) **and deselecting all six**
v3.9 additions to `test_artifact_ownership.py`, by their exact IDs:

```
test_each_protected_text_artifact_has_exactly_one_writer
test_build_arm_features_v39_writes_only_the_five_authorized_artifacts
test_the_harness_writes_no_repo_artifact_at_all
test_no_unauthorized_v39_artifact_exists_on_disk
test_the_head_coach_win_ledger_is_derived_in_memory_not_cached
test_the_v39_modules_never_write_outside_the_coaching_data_dir
```

Inherited per module: 22 + 33 + 34 + 27 + 15 + 7 + 3 = **141**. Full suite: 141 + 88 + 246 + 146 + 81 + 6 = **708**.

`pytest --deselect` **silently ignores an ID that does not exist**, so a mistyped path deselects
nothing and the run reports 147 with no error at all. Copy the six IDs verbatim; do not retype them.

*Historical, superseded, recorded only so the numbers in older drafts can be placed:* at v3.9a the
suite was 254 (SUPERSEDED); an early attempt deselected only three IDs and returned 144 passed,
3 deselected (SUPERSEDED); a later attempt used six IDs that were mistyped and returned 147
(SUPERSEDED). None of those three figures is current.

## 41. THE REAL-OUTCOME TRANSITION — a false blocker, then a false all-clear (v3.9e/f)

**41a. I claimed the Arm 0 outcome was not repo-owned. WRONG, WITHDRAWN.** I traced
`season_total_target()` to `nfl.load_player_stats(...)` and asserted the outcome was unreachable offline
without checking whether the repo already owned a snapshot of that same loader. It does:
`snapshots/player_stats_2011_2025.parquet`, tracked, pinned (sha256 `e8dad7e4...`, 269,594x115,
2011-2025), and `wr_recent_full_game_features_harness.build_panel()` already reproduces the target from
it. *A blocker is a claim and needs the same evidence as a result.*

**41b. Then I overcorrected: "the first run is already hermetic" was an unqualified ALL-CLEAR and is
also WITHDRAWN.** True of the outcome path and the four VETERAN buckets; false of the full seven-bundle
feature path. Arm 0 ships SEVEN bundles; I defined the contract as "identity + 32 veteran features",
called it the Arm 0 contract, and pinned exactly ONE bundle in a test, so the gap was invisible.
Measured: RB rookie 32/41 features missing, WR 35/44, TE 35/44 — combine, college-box and PFF-derived.
Production rebuilds them via `fantasy/rookie/harness` (live `nflreadpy` loaders + a read of
`fantasy/seasonal_projections/pff/`, which holds 418 local files and **0 tracked** files,
`.gitignore:37`). A clean checkout cannot assemble those buckets. `activation_readiness()` now returns
False and names them; `preflight()` stays 21/21 so the committed prefit checkpoint stays green.
**OPEN — Joseph's decision (manifest §0b): freeze a feature-only pinned artifact (recommended,
conditional on PFF licensing) / external pinned artifact / amend the population.** No artifact written,
no PFF file touched, no rookie matrix regenerated.

**41c. Three implementation defects behind it, all fixed:** the authorized feature reader returned 2026
and the forbidden legacy target columns while its own validator rejects both (663 tests passed over a
reader that could not work, because nothing ran its OUTPUT through the validator); the assembler refused
rows that production LEFT-joins and zero-fills, changing the target and denominator; and the accounting
states double-counted a null `player_id`.

**41d. A2 was evadable four ways** — `import requests as r`, `from requests import get`,
`requests.Session().get(...)`, and a client variable — all returned ok=True under receiver-name
matching. A2 now rejects the network IMPORT itself; positive controls keep `dict.get`/`config.get`/an
injected `client.get` legal, and the deliberate limits (`importlib`/`eval`/`exec`/injected client) are
stated rather than glossed.

