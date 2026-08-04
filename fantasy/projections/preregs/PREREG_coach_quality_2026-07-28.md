# PRE-REGISTRATION — Coach-Quality Quantification for Season-Total Projections

**Date frozen:** 2026-07-28
**Revision:** **v3.9c** — supersedes v1, v2, v3, v3.1, v3.2, v3.3, v3.4, v3.5, v3.6, v3.7, v3.8, v3.9,
v3.9a and v3.9b in full. The live canonical sections below (§0 onward) state CURRENT policy; every amendment
record above them is history and may quote superseded wording.
**Statistical design:** **RATIFIED by Joseph 2026-07-28**, subject to the v3 amendments below.
**Execution status:** **RATIFIED AND T0 PASSED — 2026-07-28.**
**Frozen source table:** `coaching/data/actual_play_caller.csv`, md5 `98f1c66b7387c16bba6a5463f4e0fa06` (v3.4 PREFIT). Superseded, in order: `ac9883e98cdb1bd04a1c0978746cc023` → `391be44c4e4205ceea6456ea935794c0` → `3752405a4f499223aac08841dabc5f74` (provisional/intermediate, never canonical). Full chain and semantics in the v3.3→v3.4 amendment.
**FITTING STATUS (v3.9, 2026-07-29):** No player-projection arm (0-5 or ARM_HC) has been fit, no
fantasy outcome has been read, and no outer projection result has been examined. Phase 2 built the
point-in-time coaching representations and the nested evaluation harness, and exercised the harness on
SYNTHETIC targets only (`REAL_FIT_AUTHORIZED = False`). **Preliminary Arm 3 nuisance and coach-effect
models WERE fit** — `RidgeCV` expectation models (one per season) and `RidgeCV`+`Ridge`
cross-classified coach-effect models — and their alpha choices and effect magnitudes were observed
before audit. An earlier claim that "nothing has been fit" was inaccurate and is withdrawn.
Five confirmed defects gate the next step; see `coaching/AUDIT_TODO.md`. **The observed effect
magnitudes must not be interpreted** — Stage-2 tuning did not resolve (9 of 10 target-season
fits selected the grid-maximum alpha; 1,194/1,292 rows = 92.4% row-weighted) and defects 1-4
remain. The corrected values could increase, decrease, change sign, or converge to zero.
**Subproject:** `fantasy/projections/coaching/`

> **T0 FINAL 2026-07-28 — BOTH GATES PASS.**
> Outer 2018-2025: **95.3% row / 95.4% game** (244/256 team-seasons; 4,058/4,254 games) vs a 95% gate.
> Prior-building 2014-2017: **90.6% row / 90.6% game** (116/128; 1,856/2,048 games) vs a 90% gate.
> 410 resolved rows, all `high` confidence, 108 distinct persons, **18 dated midseason splits,
> 0 overlapping week ranges, 0 duplicate attributions**. The outer window was NOT narrowed and
> nominal OC was NOT substituted at any point.
> Table frozen at md5 `98f1c66b7387c16bba6a5463f4e0fa06` (UNCHANGED through v3.5; T0 numbers RECOMPUTED and unchanged at 244/256 and 116/128). **T0 measures RETROSPECTIVE historical attribution only — it is NOT point-in-time coverage, which is 59.4% on the outer window. See the v3.5 amendment §5.**

> **PHASE 1D EXECUTED AND PASSED — 2026-07-29.** Game-based reliability built at
> (person_id, target_season, role) grain: `coaching/data/coach_reliability.csv`
> (md5 `d3847317dd17d7356318ea69c3dde397`, 6,340 rows, 225 persons, targets 2000-2026) with
> game-id lineage in `coach_reliability_lineage.csv`. **Hashes and the Reid decomposition in this note were SUPERSEDED by v3.6 below** -- the original claim that Reid's 245 HC-context games were 'delegated' was false (5 delegated, 240 unknown-caller).
> Three semantically separate counts — `caller` / `hc_resume` / `noncalling_hc_context` — with
> `reliability = g/(g+32)` on GAMES, never `16 x n_seasons`. Exact routing verified: McDaniel
> caller 68 (0.68), McVay caller 181 (181/213, unified LA 149 + WAS 32), Reid hc_resume 437 =
> 192 called + 245 delegated context. 55 registered tests pass.
> **Finding:** caller history is left-censored at 2014 while HC résumé reaches 1999, so
> `caller_reliability` is confounded with target season (Reid 16 entering 2015 -> 192 entering
> 2026). Flagged per row (`history_left_censored`), NOT corrected — see `AUDIT_TODO.md` item 11.
> No Stage-1 model fit; no Phase 1E.

### Amendment record (v3.9b -> v3.9c, 2026-07-29, PREFIT — review repairs)

**Still PREFIT. No real fantasy outcome loaded, inspected, joined, scored or fit; both real-fit locks
stayed shut; all 18 protected artifacts byte-identical.** Five defects found by independent review of
v3.9b, all repaired. The v3.9b policy conclusions are unchanged and were independently reproduced.

#### A. `coverage_reconciles` was a spot-check that made a false claim

It inspected only `arm == ARM_1 and identity_state == "all"`, and only `n_team_seasons` and
`caller_identity_known`. Corrupting `ARM_2 / known_with_history / n_team_seasons` to 999 left
`coverage_reconciles = True` — only the byte-hash caught it, so an intentional rebuild plus an updated
pin could have shipped a semantically false artifact with C10 green.

`build_arm_features_v39.compare_coverage()` now regenerates the **entire** frame with `coverage()` —
the same function the builder writes from, so there is one canonical derivation — and compares schema,
`(design, arm, season, identity_state)` key set, key uniqueness and **every cell** (counts, rates,
means with the builder's rounding/NaN semantics, arm feature counts, caller-dependence flags,
league-prior rows and rates, all identity-state decompositions) after a stable sort, through a single
CSV round-trip so dtypes and float formatting match by construction. The preflight calls it.

#### B. `preflight()` did not always return the promised structured record

The feature tables, coverage, lineage and manifest were read OUTSIDE the guarded `check()` wrapper, so
deleting the Design A table raised `FileNotFoundError` instead of returning the record. Every input is
now loaded defensively up front; a missing, unreadable, malformed, schema-invalid or empty CSV, and
malformed JSON, are recorded by a new `v39_artifacts_readable` check, and each dependent semantic check
reports `blocked by <input> load failure (<error>)` rather than crashing.

#### C. The GENERATED lineage artifact still asserted the retired policy as primary

The feature VALUES used the adopted policy but the lineage metadata contradicted them:
`timing_rule = "seasons < Y; Design A additionally requires source upper bound <= Y cutoff"` on every
caller-history and caller-continuity row, plus the note "Design A openers are themselves gated on Y's
cutoff". A hash cannot see that contradiction.

Both are corrected to the pinned `PRIMARY_TIMING_RULE`
("source seasons < Y from the FULL retrospective caller-attribution ledger; NOT gated by the attributing
source's publication date"), the `contribution_lineage()` docstring no longer claims gate exclusions,
and a new `validate_lineage_policy()` — called by the preflight as
`lineage_states_the_primary_policy` — rejects any live row asserting a source-date gate on history or
openers. The retired rule remains as diagnostic-only fields.

#### D. Live requirement/audit text still asserted the superseded policy

Requirement-matrix **F-14** is withdrawn (retained struck-through for traceability) and replaced by
**F-14a** (target identity evidence-gated at the frozen cutoff), **F-14b** (historical performance and
prior-season continuity use source seasons `< Y` from the full retrospective ledger, no source-date
gate) and **F-14c** (the retired rule is diagnostic-only, nonselectable, unpersisted, cannot rescue the
primary result). `AUDIT_TODO.md` item 32 is re-headed **RESOLVED BY v3.9b** with the corrected
zero-row/+358-game result stated in the item itself and the `~76` / `200/256` / two-axis claims struck
through at the point of occurrence.

A mechanical scan over the live prereg (from §0), requirement matrix, audit TODO, research log, stop
report, both v3.9 module sources, the manifest and the generated lineage artifact now reports **CLEAN**:
no unqualified assertion that primary historical segments or prior openers are source-date gated, that
the gain is 28/76/200, that 2019-2022 power improved, or that Design A/B is a two-axis contrast. The
scanner is self-tested against all five reintroductions.

#### E. The "no-real-outcome" part of C10 is now production logic

C10 claimed the no-real-outcome/access-boundary assertions but implemented them only as tests, so the
runtime guarantee did not exist and test and C10 could drift apart. `no_real_outcome_access()` now lives
in the harness module and is a preflight check.

It enforces the frozen structural contract `C1-C7 + C4b` (ASCII hyphen — the canonical spelling), over
the executable AST of exactly the two v3.9 modules with docstrings stripped. On success it returns this
exact string, which also appears verbatim in the requirement matrix (H-24) and the stop report, and is
pinned as the module constant `NO_OUTCOME_OK_DETAIL`:

```
both v3.9 modules satisfy the frozen structural no-outcome contract C1-C7 + C4b (scope, executable-only, no banned callee, no banned token in any executable string, no reading through an exemption, sealed entry point, single False lock, no environment write)
```

Markdown cannot include a Python constant, so each of these is a copy; the guarantee is a test
(`test_the_exact_success_detail_appears_verbatim_in_every_document`) that fails unless every copy matches
the constant byte for byte. The clauses:

> **C1** scope — `sources` must be exactly the two modules, omission *and* addition rejected ·
> **C2** executable-only · **C3** no banned outcome-producing callee ·
> **C4** no banned outcome token in ANY executable string constant, in any position ·
> **C4b** **no reading through an exemption** ·
> **C5** `assemble_real_panel` bound exactly once by one undecorated module-level `def` whose
> executable body is exactly two statements — zero-argument `require_real_fit_authorization()` then an
> unconditional `raise NotImplementedError(...)` ·
> **C6** exactly one module-level `REAL_FIT_AUTHORIZED = False` across
> `Assign`/`AnnAssign`/`AugAssign`/`NamedExpr` ·
> **C7** no environment write, rebinding or deletion by any enumerated form.

It is a decidable structural contract, **not** a claim about arbitrary Python behaviour: it does not
resolve aliasing, dynamic attribute access, `getattr`/`eval`/`exec`, third-party imports, or a token
assembled at runtime from fragments, and the docstring says so. It accepts injected pure source so
regression tests exercise the SAME function without touching canonical files.

**Preflight is now 21 checks** (17 → 20 at v3.9c, → 21 at v3.9e): added `v39_artifacts_readable`,
`lineage_states_the_primary_policy`, `no_real_outcome_access`.

**Status:** **836 collected** offline with an empty temp directory — **835 mandatory tests pass**, plus 1 optional git cross-check that passes when the pinned historical blob is reachable and otherwise skips (the vendored red proof runs in both states). (141 inherited + 695
new). Locks not opened; the real outcome join remains unimplemented.

### Amendment record (v3.9a -> v3.9b, 2026-07-29, PREFIT — final correctness patch)

**Still PREFIT. No real fantasy outcome loaded, inspected, joined, scored or fit; both real-fit locks
stayed shut; all 18 protected artifacts byte-identical.**

#### A. §7 denominators are now EXACT, not just counts

v3.9a checked `n_improved >= 6`, `>= 4` and `n_nonbaseline >= 4` without requiring the frozen
denominators to be present, so a truncated six-season run could satisfy "6 of 8" and four available
recent seasons could satisfy "4 of 5". The report's unresolved item 11 asserted a guarantee the code
did not provide.

Conditions are now:

```
C3: cohort season set == {2018..2025} exactly, no duplicate (player_id, season) rows, AND >= 6 improve
C4: {2021..2025} all present, no duplicates,                                         AND >= 4 improve
C8: fold-selection key set == {2018..2025} exactly,                                  AND >= 4 nonbaseline
```

Missing, duplicate and unexpected seasons or fold keys fail the relevant condition and are reported
explicitly in `denominator_problems`, `outer_seasons_missing`, `outer_seasons_unexpected`,
`recent_seasons_missing`, `duplicate_player_season_rows`, `fold_seasons_missing`,
`fold_seasons_unexpected`.

#### B. Condition 10 is now the assertion set it claims to be

v3.9a's `_integrity_check()` checked production hashes, the ten upstream coaching hashes and the lock
state — while C10 was documented as "every timing, leakage, coverage, artifact-integrity and
no-real-outcome assertion". `preflight()` ran **17** deterministic checks at that point (SUPERSEDED; it
is 21 now), reading no outcome:

protected hashes (18) · the five v3.9 artifacts against their pins · no unauthorized `*_v39.*` and no
coaching parquet · feature-table key uniqueness and 416 rows per design · Design A outer identity
coverage exactly 152/256 · unknown and known-no-history routing plus the no-NaN rule · forbidden-feature
and retired-name policy across every manifest arm · manifest full X == every shipped bundle plus ordered
arm additions · explicit `QB/rookie: null` · coverage reconciles with both feature tables · lineage
strict timing · contribution-lineage career/roll3 game and segment reconciliation on all 832 feature
rows · Design B labelled oracle/nondeployable and unreachable from selection · production models
byte-identical · every pipeline timing/leakage/row-identity assertion actually EXECUTED (counted, not
assumed) · the run-mode lock contract.

C10 passes only when all 17 are true. The structured record is returned as a `preflight` frame beside
the verdict.

#### C. The real-authorization paradox is resolved by run modes

v3.9a treated an unlocked gate as an integrity failure, which made `DEVELOPMENTAL CANDIDATE`
unreachable for any authorized real run. The lock expectation is a property of the run mode:

```
synthetic_prefit : BOTH locks MUST be closed
authorized_real  : BOTH locks MUST be open (constant + env token)
```

A partially authorized state is invalid in **both** modes, and an unknown mode is invalid — it fails
closed. **No mode relaxes any artifact, timing, leakage, coverage or feature-policy check.** The locks
are NOT opened in this pass and the real outcome join is deliberately unimplemented.

#### D. PRIMARY HISTORICAL-HISTORY POLICY — ADOPTED, and the arithmetic corrected

**Adopted.** The target-season expected caller stays evidence-gated at the frozen preseason cutoff;
unknown target callers still receive league-prior caller features and no HC-context effect. Once the
target caller is known, his career / rolling-three history uses the **full retrospective
caller-attribution ledger restricted to source seasons and games strictly before Y**, and a past
segment is **not** gated by the publication date of the surviving citation. Prior-season opening and
closing caller identity (tenure, entering-change) follows the same rule.

Reason: the past play-calling role was a contemporaneously observable fact; the citation's publication
date records when it can now be proved, not when it became knowable. This matches the original brief and
restores a **single-axis** Design A / Design B contrast — target identity supply only, verified feature
by feature on all 227 identity-matching rows.

**MANDATORY ARITHMETIC CORRECTION — two prior claims are RETRACTED.**

The v3.9a stop report said Design A known-with-history could rise from 124/256 toward Design B's
200/256, "up to ~76 more usable rows". **That was impossible and is withdrawn.** Design A has only
152/256 known target identities, and an unknown identity stays at the league prior however complete the
ledger is, so the ceiling is 152 and the arithmetic maximum increase is 28.

**Computed from code, the actual increase is ZERO.** All 28 outer known-no-history rows are genuine
first-time callers with **no prior segment in the ledger at all** — the gate was never what suppressed
them. So the "28" upper bound is also not attained.

| Design A, outer 2018-2025 | strict gate | primary (ungated) |
|---|---|---|
| known target identity | 152 | **152** (unchanged by this policy) |
| known WITH history | 124 | **124** |
| known NO history | 28 | **28** |
| unknown identity | 104 | **104** |
| caller-games of history | 7,274 | **7,632 (+358, +4.9%)** |

Per-season game gain: 2018 +106 · **2019 +0** · 2020 +16 · 2021 +42 · 2022 +16 · 2023 +71 · 2024 +71 ·
2025 +36. Across all target seasons exactly **one** row gains history: 2016 DET Jim Bob Cooter, 0 → 9
games.

**Stated plainly: this policy adds history DEPTH, not usable rows, and it does NOT relieve the
2019-2022 power problem** — 2019, the thinnest season, gains zero games. The rationale offered for the
change ("avoids concentrating archive-retrievability missingness in 2019-2022") is **not** achieved.
The change is justified on methodological grounds and on restoring the single-axis contrast, not on power.

**The retired strict rule survives as a labelled diagnostic sensitivity**
(`build_arm_features_v39.strict_gate_sensitivity`): in memory only, nonprimary, nonselectable, cannot
rescue or alter the primary result, never a sixth repo artifact. It also remains auditable per row from
`arm_feature_lineage_v39.csv` via `strict_source_date_gate_would_exclude` and
`strict_gate_exclusion_reason`.

**Status at that amendment (HISTORICAL, SUPERSEDED):** **343 registered tests passed** offline with an empty temp directory (141 inherited + 202
new). Five v3.9 artifacts; three hashes changed for identified value-level reasons recorded in the stop
report. No player-projection arm fit; no fantasy outcome loaded or inspected.

### Amendment record (v3.9 -> v3.9a, 2026-07-29, PREFIT — review-repair pass)

**Correction pass answering an independent review. No real fantasy outcome was loaded, inspected or
fit; the real-fit gate stayed shut; all 18 protected artifacts are byte-identical.**

#### A. The build is now HERMETIC

`build_preseason_snapshot.projection_cutoffs()` and the old `hc_game_results()` both called
`nflreadpy.load_schedules()`, and the win ledger was cached in an untracked scratch directory. A clean
checkout with an empty temp directory and no connectivity therefore **failed five v3.9 feature tests**,
and the then-current 254-pass result (SUPERSEDED — the suite is now 836 collected) depended on mutable state that
is not in the repo.

Both now read the repository-owned frozen snapshot
`fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet` (provenance in
`snapshots/manifest.json`: `load_schedules`, nflreadpy 0.1.5, 7,276 × 46, fetched 2026-07-10T01:17:13Z,
sha256 `78ff21f9…`). It supplies historical REG schedules, scores, coaches and season-opening dates for
1999–2025; season 2026 keeps the frozen production as-of date **2026-07-21** and has no played games to
score. The win ledger is computed **in memory** — no sixth artifact, no external cache.

Derived cutoffs are cross-checked against the `projection_cutoff` column already persisted in
`preseason_staff_snapshot.csv`, so the hermetic derivation cannot silently disagree with the artifact
the eligibility gate was built with. All 13 match.

The whole suite and a full build now pass with **egress blocked and an empty temp directory**, proven
by `test_cutoffs_and_hc_history_build_with_NETWORK_BLOCKED` and
`test_a_full_feature_build_runs_with_NETWORK_BLOCKED`, plus
`test_no_v39_module_calls_a_live_nflverse_loader`.

#### B. The live canonical prereg sections are rewritten, not merely bannered

v3.9 corrected the amendment banner but left §0, §2, §3.2, §4, §5, §6, §7, §8-T5 and §8.1 asserting the
superseded policy underneath it. Those sections now state v3.9 truth directly: seven representations;
§4.0 as a binding player-feature policy; current Arm 3 role semantics with no season fixed effect and
no reliability multiplication; canonical drive-proxy names; expanding forward chaining only, with LOSO
explicitly withdrawn; Holm across the six nonbaseline alternatives; the unchanged ten-condition pass
rule; and §8.1 restated from the emitted features. Old wording survives only inside amendment history.

#### C. §6.1 — the improvement statistic is now FROZEN

§7(1) said "top-cohort MAE" without choosing pooled vs mean-per-season, and the two disagree whenever
cohort sizes differ. **Frozen: POOLED over all outer top-cohort rows**, because it matches the plain
reading, matches what the §7(2) clustered bootstrap resamples, and leaves §7(3)/(4) to carry the
per-season evidence instead of duplicating it. The identical function computes the observed statistic
and every placebo draw. Frozen before any real outcome was visible.

#### D. The ten-condition verdict is implemented

`primary_verdict()` evaluates all ten §7 conditions on the **nested-selected Design A pipeline only**
and returns one row per position with every raw statistic, every Boolean, failure reasons and the
verdict. Synthetic fixtures prove an all-pass case, each condition failing independently, that a
perfect fixed arm in the frame cannot change the verdict, and that supplying Design B leaves it
bit-identical. `experiment_spec()` pins all ten thresholds.

#### E. The placebo now tests the nested-selected pipeline

It previously permuted bundles and scored ONE fixed arm — the modal selection — which is not the
pre-registered condition. Every draw now reruns representation selection independently for every outer
fold on the permuted features and may select a different arm per fold. ARM_0 carries no coaching
feature, so its predictions and therefore cohort membership are invariant under permutation: observed
and null are scored on identical rows with one statistic. 200 draws, seed 20260728 retained. Compute
cost is now the dominant term in the experiment and is stated as such.

#### F. The manifest pins the FULL ordered player X

It previously stored only appended coaching columns, left `ARM_0` empty, and could not express the
veteran/rookie baseline difference. It now also pins `arm0_baseline_features` per
`(position, bucket)`, the explicit missing `QB/rookie` production path, and `full_model_x` per
`(position, bucket, arm)` = baseline in shipped order followed by the arm's ordered additions. Asserted
against every bundle and builder pool, and against what actually reaches `fit()`.

#### G. Lineage proves membership

`arm_feature_lineage_v39.csv` gained a third `record_kind`, `caller_contribution`: one row per
CANDIDATE historical segment behind each caller aggregate — included or excluded — carrying the segment
key, source season/team/week range, `pbp_games`, the source upper bound and target cutoff, gate
eligibility with an exclusion reason, career/roll3 inclusion, and a pointer to the existing game-id
trace (`coach_reliability_lineage.csv`). Recomputed independently of the build so the reconciliation
tests compare two paths; they reconcile on all 416 rows per design.

#### H. **A NEW METHODOLOGICAL DECISION REQUIRING JOSEPH'S RATIFICATION**

The v3.9 request required pre-cutoff evidence for the target-season expected caller and strictly prior
historical seasons. This implementation went further and **also gates every historical caller segment
by the publication date of the source that establishes that past attribution**. That is an additional
anti-lookahead rule, not a restatement of the request, and it materially reduces usable history.

**Kept as-is pending Joseph's explicit decision.** Full framing, the exact counts, and the alternative
are in `coaching/V39_PREFIT_STOP_REPORT.md` §7. In one line: the alternative is to evidence-gate the
TARGET identity only and compute strictly-prior historical performance from the full retrospective
attribution ledger — which would raise Design A's known-with-history counts and make Design A vs
Design B a single-axis contrast. Under the rule as implemented the two designs differ on **two** axes
(current identity supply AND historical attribution availability), and the test that formerly claimed
otherwise has been renamed.

**Status at that amendment (HISTORICAL, SUPERSEDED):** **290 registered tests passed** (141 inherited + 149 new), offline, with an empty temp
directory. Five v3.9 artifacts; three hashes changed for identified value-level reasons (§10 of the
stop report). No player-projection arm fit; no fantasy outcome loaded or inspected.

### Amendment record (v3.8 -> v3.9, 2026-07-29, PREFIT)

**Phase 2 PREFIT. The coaching REPRESENTATIONS and the nested evaluation HARNESS are built; NO
player-projection arm has been fit and NO fantasy outcome has been read.** The harness is verified
end to end on SYNTHETIC targets, so the machinery is checked before any outcome is visible.
`REAL_FIT_AUTHORIZED = False`; turning it on requires a further written amendment plus approval.

Phase 1 numbers were RECOMPUTED from the frozen artifacts and reproduce exactly: Stage 1 over
2018-2025 model MSE **0.00686090**, league-average relative-EPA baseline **0.00824548**
(**16.79%** improvement), prior-season relative-EPA baseline **0.00921907** (**25.58%**), correlation
**0.42159**; entering-2026 caller effects McDaniel **+0.005262**, Roman **+0.007482**, McVay
**+0.025936**, Reid **+0.038287**; Harbaugh and Reid HC-context numerically zero. These remain
**routing and feature-generation results** and establish nothing about fantasy projections.

#### 1. Forbidden primary player features

A primary player feature may NOT be, or be derived from, `observed_reliability`, any raw or log
history count, `no_prior_history`, any censoring field, or any observable-window field.
`observed_reliability = g/(g+32)` is a strictly monotone bijection of the count, and caller history is
left-censored at 2014 while HC résumé reaches 1999, so the count carries the season index.

Reliability survives ONLY as the deterministic shrinkage weight INSIDE a historical estimate.
Unknown identities and known-no-history identities both receive league priors. **Arm 3 ridge effects
receive no second shrinkage** — Stage 2 already partially pooled them by sample size.
**Tenure and entering-change indicators remain eligible.**

Enforced by `build_arm_features_v39.assert_no_forbidden_features`, which inspects the actual emitted
column list and every manifest arm, not a hand-maintained list.

#### 2. ARM_HC added; the primary comparison is seven arms

`ARM_HC` = `hc_career_win_pct_shrunk`, `hc_roll3_win_pct_shrunk`, `hc_tenure_current_team`,
`hc_changed_entering`. Regular season only, no playoffs, a tie counts **0.5** and stays in the
denominator. ARM_HC has full point-in-time coverage in every season and excludes all caller and
HC-context effects. **McVay's offensive identity stays in the CALLER channel** — when the head coach
calls the plays that game routes to the portable caller block, so an HC-only arm does not capture it.

Primary nested selection compares **Arm 0, ARM_HC, and Arms 1-5**. Holm correction therefore runs
across the **six** fixed arms (ARM_HC and Arms 1-5) within each position, replacing v3.8's five.
This is the more conservative choice and is frozen before any outcome is seen.

#### 3. Expanding inner validation

    inner training seasons  <  validation season  <  outer target season

Frozen minimums **2 training** and **2 validation** seasons; a target that cannot meet them is
SKIPPED, never fitted on relaxed folds. For outer **2018** the folds are exactly

    train 2014-2015 -> validate 2016
    train 2014-2016 -> validate 2017

Production model families and hyperparameters are **fixed** and read from the shipped bundles; the
player model is never retuned.

#### 4. Identity sources

**Design A — PRIMARY, deployable.** TARGET-season identity from `preseason_staff_snapshot.csv`,
`expected_opening_caller_id` where `eligible_at_cutoff`; otherwise UNKNOWN -> league prior. No
continuity imputation. Outer 2018-2025 caller coverage **152/256**, reproduced by the builder.

**Design B — ORACLE, NONDEPLOYABLE.** Retrospective opening caller (outer coverage **244/256**).
It cannot enter primary selection and every reported B number carries the label "ORACLE IDENTITY —
uses information unavailable at the projection cutoff. NOT achievable in deployment. NOT evidence of
real preseason performance."

**Design C — NOT AUTHORIZED.** No code path exists; `target_identities` raises on any other design.

**SINGLE AXIS (v3.9b).** Both designs use the identical historical rule — strictly prior seasons from
the full retrospective caller-attribution ledger, NOT gated by the publication date of the surviving
citation. The two designs therefore differ on exactly one thing: **target-season identity supply.**
Verified feature-by-feature on all 227 identity-matching rows. Design B remains oracle purely because
its target identity is retrospective. The retired source-date-gated history rule survives only as a
labelled in-memory diagnostic sensitivity that can never enter selection.

**NEW IN v3.9 — the historical caller record is gated too.** v3.8 gated only the TARGET-season
identity. The historical record was ungated, so a later article could build an earlier feature: BUF
2014's caller is attributed by an ESPN piece dated **2016-10-29**, which under the old rule fed
target-2015 caller history. That is look-ahead leakage of exactly the kind v3.5 removed from the
snapshot. Design A now admits a historical segment for target Y only when `season < Y` **and** the
attributing source's conservative UPPER BOUND <= season Y's frozen projection cutoff.

Measured effect (eligible / prior segments): 2015 **15/27** · 2016 38/63 · 2017 77/95 · 2018 119/130
· 2019 **154/163** · 2020 170/189 · 2021 206/222 · 2022 237/252 · 2023 267/282 · 2024 299/314 ·
2025 331/346 · 2026 **364/378**.

Design B is left UNGATED on both axes, so A and B differ on exactly one thing — archive
retrievability — which is the axis B exists to probe.

**Consequence that must be read with the coverage number, not around it.** Under Design A the number
of team-seasons whose caller has ANY eligible prior history is 25 (2018), **3 (2019)**, 4 (2020),
7 (2021), 6 (2022), 26 (2023), 26 (2024), 27 (2025) out of 32. In 2019-2022 the caller channel is
close to empty. A null caller arm on this panel is **jointly** a statement about coaching signal and
about archive retrievability and cannot separate them.

**Head-coach identity is an ASSUMPTION, not evidence-gated research.** It is taken from the week-1
head coach in both designs, on the standing position that HC hires are public before the season. It
is not established by the same pre-cutoff evidence standard applied to callers. Recorded as a
disclosed assumption.

#### 5. Frozen neutral encoding — a VALUE, never NaN

Design A caller coverage is 0% in 2017 and ~100% in 2018/2023/2024, so a NaN-vs-present channel
would be close to a season indicator — the calendar proxy the feature policy exists to exclude. An
unknown-caller row therefore carries the frozen neutral VALUE:

| feature kind | neutral value |
|---|---|
| rank-percentile composite | **0.500** |
| z-score quality / scheme tendency | **0.000** |
| Arm 3 adjusted effect (caller, HC context) | **0.000** |
| caller tenure | **0.0** (the value a first-year caller receives) |
| caller entering-change | **0.5** |
| `caller_is_head_coach` | **0.5** |
| HC win percentage with no prior games | **0.500** |

**DISCLOSED LIMITATION.** 0.5 on the two binary caller indicators IS a distinguishable third level,
and under Design A it correlates with season. It is retained because every alternative is worse: 0
asserts delegation, 1 asserts self-calling, and NaN reopens the missingness channel across every
caller feature at once. The pre-registered control is the within-season TEAM-LEVEL permutation
placebo, which preserves each season's composition under the null, so a season-proxy gain reproduces
in the placebo and fails the 95th-percentile bar. `arm_feature_coverage_v39.csv` reports the neutral
share per season so the confound stays visible.

#### 6. Arm 3 is structurally unavailable before target season 2018

`arm3_stage2_effects_v38.csv` covers target seasons **2018-2026 only**, because Stage 1 residuals
begin in 2014 and the frozen Stage 2 minimums (2 training + 2 validation seasons) make entering-2018
the earliest estimable target. Target seasons 2014-2017 therefore carry **all-zero** Arm 3 effects.
Nothing is backfilled and Stage 2 is NOT re-estimated to widen the window.

**Stated up front, not discovered later:** both inner folds for outer 2018 validate on 2016 or 2017,
so Arms 3 and 5 receive no caller/context effect information in that fold and Arm 3 cannot be
selected there on evidence. This is a structural property of the frozen design, not a defect.

#### 7. Feature construction and artifacts

**Representation names are `ARM_0`, `ARM_HC`, `ARM_1` … `ARM_5`** in code, manifest and coverage.

**v3.9 authorises EXACTLY FIVE new repo data artifacts**, all written by `build_arm_features_v39.py`
and by nothing else:
`team_coach_features_design_a_v39.csv`, `team_coach_features_design_b_oracle_v39.csv`,
`arm_feature_manifest_v39.json`, `arm_feature_coverage_v39.csv`, `arm_feature_lineage_v39.csv`.

The head-coach win ledger is **derived in memory** on every build from the repo-owned frozen snapshot
`fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet`, and is written **nowhere at all** —
not to `coaching/data/` and not to a scratch directory. (RETIRED: the `COACH_V39_SCRATCH` cache used
through v3.9a — WITHDRAWN, because a cache outside the repo made the build non-hermetic.)
`run_coach_projection_experiment_v39.py` writes **nothing at all**; the production audit and the
frozen harness spec are returned as structures and recorded in `coaching/V39_PREFIT_STOP_REPORT.md`.
`audit_production(write=True)` and `experiment_spec(write=True)` RAISE, so the artifact set cannot
grow by accident. A test asserts no sixth `*_v39.*` file exists on disk.

Arm 3's player-facing fields are `caller_adjusted_offense_effect`, `noncalling_hc_context_effect`
and `caller_is_head_coach`.

**Retired drive names are rejected in features, manifests and the lineage artifact.** This caught a
naming violation of my own: the Arm 2 stem was `points_per_drive_z`, which embeds the RETIRED
unqualified name. It is now `drive_scoring_points_per_drive_proxy_z`, matching
`drive_definitions.PPD_PROXY`. The guard removes the canonical names before scanning, because
`drive_scoring_points_per_drive_proxy` legitimately CONTAINS `points_per_drive` as a substring.

`arm_feature_coverage_v39.csv` is at (design, arm, season, **identity_state**) grain, where
identity_state ∈ {`all`, `known_with_history`, `known_no_history`, `unknown`}, carrying counts AND
rates plus `rows_at_league_prior_for_this_arm`. Summing without filtering `identity_state == "all"`
double-counts.

`arm_feature_lineage_v39.csv` carries a `record_kind` discriminator: `feature_definition` rows (one
per emitted feature) and `identity_routing` rows (one per design × target season × team, 832 rows)
recording the identity decision, source-segment and source-game membership, first/last source
season, and the league-prior fallback WITH its reason. `strict_timing_ok` is asserted true on every
routing row, so `last_source_season < season` is provable per row rather than promised.

Historical caller aggregation uses `segment_offense.csv` weighted by **`pbp_games`** (asserted equal
to the canonical `n_games_attributed` on every played segment). All target-season features use
seasons `< Y`. Career and rolling-three windows; per-metric games counted only where that metric is
non-null, so a segment missing one measurement does not inflate confidence in it.

Arm 1's composite requires **>=3 of 5** rank components (drive-scoring points/game proxy, yards/play,
EPA/play, success rate, drive-scoring points/drive proxy). Arm 2 keeps six efficiency z-scores as
separate dimensions. Arm 4 is position-specific. Arm 5 combines staff continuity/tenure, the Arm 3
effects and the position-specific Arm 4 block, and **excludes** Arm 1's win/rank features, Arm 2's
raw efficiency features and all sample-size metadata — asserted, not merely documented.

`rush_tendency_z` is the EXACT negation of `pass_tendency_z`: within a source season
z(1 - neutral pass rate) = -z(neutral pass rate), and negation commutes with shrinkage toward 0. It
is emitted so the RB block reads in rushing terms; the identity is asserted by test.

#### 8. Arm 3 routing (frozen)

| situation | caller effect | HC-context effect |
|---|---|---|
| unknown caller | 0 | 0 |
| self-calling head coach | fitted caller effect | **0** |
| distinct known caller | fitted caller effect | fitted HC-context effect |
| identity absent from the effect table | 0 (league prior) | 0 (league prior) |

#### 9. Evaluation harness

`run_coach_projection_experiment_v39.py`. Arm 0 is READ from the shipped bundles and cross-checked
against each builder's module-level pool; `_make_model` and `_prep` are IMPORTED from
`build_rb_projection`, so arms are compared with production's own fitting code.

Audited and pinned: all seven bundles are **LightGBM** (`objective="mae"`, `random_state=42`,
`n_jobs=-1`); veteran pools are the SAME 32 season_dataset columns for all four positions including
the existing `coach_changed` and `qb_changed`; rookie pools RB 41 / WR 44 / TE 44; `depth_rank`
excluded; **no categorical handling** (every matrix is `df[feats].to_numpy(float)`); **no sample
weights**; **native-NaN** missing values (`median_impute` is None in all seven); target = observed
season-total half-PPR summed from weekly REG stats as `fantasy_points + 0.5*receptions`, NOT
`target_ppg` (which NaNs below MIN_GAMES_TARGET = 3 and would drop partial seasons); seasons <= 2025
fill a missing total with 0.0, 2026 stays NaN.

**THIS REPO CONTAINS TWO PRODUCTION ARCHITECTURES, and the audit statements above are scoped to the
one Arm 0 actually uses.** Do not generalise them.

| | Arm 0 family (USED) | legacy family (NOT used) |
|---|---|---|
| location | `fantasy/projections/models/` (7 bundles) | `fantasy/seasonal_projections/models/` |
| architecture | **direct season total** | **Model A × Model B: season total = PPG × games** |
| target | `season_total_half_ppr` | `target_ppg` and `target_games` |
| categoricals | **none** | `availability_model.pkl` and `rookie_ppg_model.pkl` **carry `cat_features`** |
| sample weights | **none** | **`train_model_a.py` fits with `sample_weight=train.sample_weight` (= games)** |

So "no categoricals, no sample weights, no PPG×games composition" is true of Arm 0 and **false of the
repo as a whole**. Recorded because the earlier phrasing did not scope it.

**Prediction clipping is asymmetric in production.** `np.clip(pred, 0, None)` is applied by
`_score_bundle` and by the 2026 face-validity path, but **not** by `walk_forward()`. The EVALUATION
path is therefore unclipped, and this harness mirrors `walk_forward`, so it does not clip either.
Asserted against the production source by test.

**Cosmetic code-vs-bundle mismatch, recorded rather than "fixed":** every bundle's `note` reads
"RB season-total half-PPR projection" even in the QB/WR/TE bundles, because those builders reuse
`build_rb_projection.fit_final_model` verbatim. The `feature_cols`, `family` and `params` are
position-correct and match each builder's own module pool exactly — asserted by `arm0_definition`.

**There is no `qb_rookie_model.pkl`** — the QB rookie arm was HELD. QB is therefore evaluated on the
veteran path only and the QB top-12 cohort covers veterans. Recorded, not silently absorbed.

**The rookie feature source — frozen 2026-08-03 (Option A), PREFIT.** The three rookie bundles need 41
(RB) / 44 (WR) / 44 (TE) features, of which the season dataset supplies only 9; the rest are combine,
college-box and PFF-derived and were regenerated live by `fantasy/rookie/harness` over an untracked
private PFF directory. Joseph authorized committing PFF-*derived* feature values with the raw files
staying private, and the derived, **outcome-free** matrix is now a repo-owned pinned artifact:

```
fantasy/seasonal_projections/snapshots/rookie_arm0_features_2014_2025.parquet
sha256 4b4655abde1c63d6316db2277d2a5301360842c9cec94fea0c2c5d77f5252584
1,263 rows x 59 cols · keys (player_id, season) · seasons 2014-2025 · RB 387 / WR 584 / TE 292
generator fantasy/seasonal_projections/build_rookie_arm0_features.py
```

It is 5 identity/routing keys, 2 point-in-time provenance columns and the 54-column union of the three
rookie pools, built by calling the **real** production `assemble_features.build_features()` with only
the two nflverse loaders injected from pinned local snapshots.

**AMENDMENT, PREFIT, 2026-08-03 (v3.9o) — the college PFF join is POINT-IN-TIME.** The first frozen
matrix (sha256 `4b4655ab…`, 59 cols) is **INVALID and withdrawn**: production selected the latest
college season carrying a player's name across 2014-2025 and merged on the name alone, so a later
college player could supply features to an earlier NFL rookie (963 receiving matches, 20 leaked; 308 RB
rushing matches, 8 leaked; 28 leaked pairs over 22 player-seasons). The production builder now retains
the PFF source season and attaches only the **latest college season strictly before** the panel row's
NFL season, resolving same-name collisions by position then by the immediately-prior season and
returning NULL when identity cannot be established. The artifact carries `pff_receiving_source_season`
and `pff_rushing_source_season` so the guarantee is checkable without the private library. This
tightens the feature definition; it changes no population, threshold, cohort or evaluation rule.

**CONSEQUENCE FOR ARM 0, RECORDED PREFIT — and the retraction of an over-strong reading.** The shipped
`rb/wr/te_rookie_model.pkl` were historically fit on the contaminated join (established by reading
`build_rb_projection.frozen_rb_matrix()` and its twins, which copy and execute the same builder). An
earlier version of this amendment concluded that Arm 0 was therefore unusable until they were retrained.
**That conclusion is RETRACTED.** This experiment does not predict from a shipped bundle: `arm0_definition`
reads bundle METADATA only, and `fit_predict` constructs a fresh estimator from `(family, params)` and
fits it on each fold's own training rows. Every fold trains on the corrected point-in-time matrix. No
bundle was retrained or modified, and none needs to be for this experiment.

**WHAT ARM 0 INHERITS, and the one limitation that remains.** From each bundle the experiment takes a
frozen specification — `feature_cols` (order included), `family`, `params`, `median_impute`, `seed`,
`target` — pinned by value in `tests/arm0_bundle_pins.py::BUNDLE_SPEC_PINS`. Those fixed hyperparameters
were selected under the historical production pipeline, which used the pre-repair join. They are
**frozen pre-experiment and applied identically to ARM_0 and to every coaching arm**, and the experiment
does not retune them. This is DISCLOSED as a limitation of the comparison's absolute level; it is not a
leakage path into the arm contrast, since a hyperparameter common to every arm cannot differentially
favour one, and it is deliberately not an activation gate. It carries **no fantasy outcome, target, label, sample weight, ADP, market
projection or target-season realized statistic**, and production's null semantics are preserved exactly
— no imputation, no proxy substitution, no row dropped and **no amendment to the frozen population**.
Two rebuilds are byte-identical. This changes only where the rookie features are READ FROM; it changes
no feature definition, no population, no threshold and no evaluation rule in this prereg.

**AMENDMENT, PREFIT, 2026-08-03 (v3.9q) — the activation wiring is BUILT, not executed.** The single
door `assemble_real_panel` moves from the sealed C5-S shape to the preregistered **C5-A** shape. The
seal MOVES rather than lifting: the body contains no reader callee at all, so the module cannot reach
data by itself; statement 1 refuses unless both locks are open; statement 2
(`require_preflight_clearance`) refuses unless the run mode is `authorized_real`, both locks are open,
`preflight()` is 21/21 in `authorized_real` mode, `activation_readiness()` is True,
`authorized_real_gate()` is True and every pinned input (veteran features, rookie matrix, weekly
outcome snapshot; coaching artifacts via preflight) matches its hash and manifest; only then does
statement 3 call the injected readers and return `assemble_panel_core(...)`. Which contract applies is
a declared module constant, never inferred from the lock state. This changes no population, feature
definition, threshold, cohort or evaluation rule — it is the mechanism by which an authorized run would
later be permitted to start. **Both locks remain closed and no real run has been executed.**

**AMENDMENT, PREFIT, 2026-08-03 (v3.9r) — the VETERAN input is a frozen snapshot.** The experiment
previously pinned `season_dataset_2014_2026.csv` by whole-file md5. That file is a live production
artifact carrying deploy-season 2026, and an ordinary 2026 refresh moved its hash without changing a
single consumed value (measured: differences confined to 2026; nine columns differing only by float
round-trip noise at most 3.5527e-15; `qb_changed` populated on 916 rows of 2026; **no 2014-2025 value
different in any of the 47 columns**). The consumed 2014-2025 window is now frozen as
`snapshots/veteran_arm0_features_2014_2025.parquet` (sha256 `45cb2583…`, 7,350 x 40, feature-only), and
the authorized run reads that and nothing else; the CSV remains the generator's input. Schema and
population are derived at build time from `VETERAN_FEATURE_COLUMNS` and `ALL_PANEL_SEASONS` and
cross-checked against the four shipped veteran bundles. **This changes no population, feature
definition, threshold, cohort or evaluation rule** — the values are provably identical; it changes only
which file the experiment reads them from, so deploy-season maintenance can no longer gate activation.

**AMENDMENT, PREFIT, 2026-08-03 (v3.9s) — result storage and the authorized runner.** Three
operational facts, none of them statistical. (1) The five preregistered result files move from
`coaching/data/` to `coaching/results/`, because the preflight check `no_unauthorized_v39_artifact`
requires the `*_v39.*` set in `data/` to equal exactly the five FEATURE artifacts — writing results
there took preflight from 21/21 to 20/21. That check and `V39_ARTIFACT_HASHES` are unchanged.
(2) The authorized-real CLI and the five-file writer, both previously documented but **never
implemented**, now exist, together with the canonical adapter that turns the assembled panel into the
frame `run_experiment` requires. (3) `run_experiment` returns seven frames for five files, so `oracle`
is folded into `arm_metrics` under `record_type` and `preflight` into `arm_verdict` under a
`preflight_` prefix, both provably recoverable. **No population, feature, arm, hyperparameter,
threshold, cohort, selection rule or verdict criterion is changed by any of this.**

**AMENDMENT, PREFIT, 2026-08-03 (v3.9u) — EVALUATION ELIGIBILITY.** A row enters the evaluation only
when (1) `team` is non-null, so OC/HC exposure is defined for it, and (2) its `(position, bucket)` has
a shipped Arm 0 bundle. Determined from the frozen feature frame BEFORE any outcome access and applied
identically to ARM_0 and every coaching arm. Measured, mutually exclusive and exhaustive:

```
source_population                  7,350
excluded_missing_team                 80    (WR 31 · TE 20 · RB 15 · QB 14, all veteran-bucket)
excluded_no_shipped_bundle           117    (QB/rookie)
eligible_evaluation_population     7,153
```

Coaching exposure is undefined without a team, and **neutral imputation was rejected because it invents
the exposure the experiment measures**. The 117 QB/rookie rows were already outside the shipped
seven-bundle experiment — the QB rookie arm was HELD — and are now excluded explicitly with a reason
and a count rather than skipped silently by the bucket loop. All twelve seasons and all eight outer
seasons remain represented, and every retained bucket keeps complete ordered features. **No outcome was
accessed when this rule or these counts were chosen**, and no feature, arm, hyperparameter, threshold,
cohort, selection rule or verdict criterion is changed.

**The real-fit gate is DEFAULT-CLOSED and double-locked.** Both `REAL_FIT_AUTHORIZED = True` and
`COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT` are required; either
alone leaves the gate shut. `assemble_real_panel` is the single door and is deliberately
unimplemented beyond the authorization check. Both locks are shut in this pass.

Frozen: outer 2018-2025 with 2021-2025 as the recent panel; identical player rows across arms;
baseline-defined cohorts (QB 12, RB 24, WR 24, TE 12) taken from the **Arm 0** prediction; full-panel
eligibility tolerance **0.25** MAE; best-arm improvement below **1%** selects Arm 0; arms within
**0.25** top-cohort MAE of the best resolve to **fewer added features** then the frozen arm order;
full/top-cohort MAE and RMSE, mean and median bias, mean within-season Spearman; player-clustered and
team-season-clustered bootstrap, **20,000** draws, seed **20260728**; Holm across the six fixed arms;
within-season **team-level** permutation placebo, **200** draws, seed 20260728, which permutes
COMPLETE team feature bundles among that season's teams and never shuffles individual player rows.

Note a consequence of the frozen rule, recorded before any result: the 1% gate applies to the BEST
coaching arm, and the 0.25 tie-band then selects on parsimony, so the finally selected arm can be one
whose own improvement is below 1%. That follows from §5 as written and is not changed here.

The harness writes nothing. Its audit and spec are recorded in `coaching/V39_PREFIT_STOP_REPORT.md`.

#### 10. Corrected companion hashes (the v3.4 pins were stale)

The v3.3->v3.4 amendment pinned `preseason_staff_snapshot.csv` at `e91b45b8...` and
`preseason_evidence_ledger.csv` at `c6ff0f5b...`. Those pins were **superseded by v3.5/v3.6/v3.7**,
which rewrote the eligibility logic and the snapshot schema, and were never updated. Current values,
verified unchanged through all of Phase 2 (file mtimes predate this session):

```
preseason_staff_snapshot.csv    6295c01178562eadd3ffecf3fbd9b4c9
preseason_evidence_ledger.csv   e1cb0d62f35676d2ee019dd1a5b2f10a
```

`actual_play_caller.csv` `98f1c66b7387c16bba6a5463f4e0fa06`, `source_ledger.csv`
`931470c713c0d20508d9361b4bf859a0` and `retrospective_staff_transitions.csv`
`54a048fe7ce4b416c7f980b0a809d0db` are UNCHANGED. The registered test
`test_rebuild_is_byte_identical` rebuilds the canonical table on every suite run and asserts
byte-identity, so its mtime moves while its bytes do not.

#### 11. Interpretation fences carried forward

McDaniel's adjusted entering-2026 coefficient is **below** Roman's by **0.002219** EPA/play. **Arm 3
supplies no basis for describing the Chargers as a play-calling upgrade**, and none is asserted
anywhere in the v3.9 code, artifacts or tests.

The HC-context block is numerically zero in **six of nine** target seasons (2020-2024 and 2026), with
`alpha_hc_context` at 3.16e15 or the extended 1e16 upper boundary. It measures **delegated offensive
context only** and does not answer whether general HC win history, tenure or change improves
projections — that question is what ARM_HC exists to test.

**Status at the v3.9a freeze (HISTORICAL — SUPERSEDED, see the v3.9d status above for current):**
**254 registered tests passed at that point (SUPERSEDED; now 836 collected)** — the **141** inherited baseline
reproduced exactly, plus **113 new v3.9 tests at that point (SUPERSEDED; now 695)**. The deselect list
quoted in that freeze was three IDs and is also SUPERSEDED: six exact IDs are required, and they are
listed in `coaching/AUDIT_TODO.md` item 26. The five v3.9 artifacts rebuild **byte-identically** across
two consecutive builds. All 18 protected artifacts (8 v3.8 + 2 preliminary + 8 production) are
byte-identical. No player-projection arm fit; no fantasy outcome loaded or inspected; no production
artifact written. Full record: `coaching/V39_PREFIT_STOP_REPORT.md`.

### Amendment record (v3.7 -> v3.8, Joseph 2026-07-29, PREFIT)

**Data-layer corrections found by Joseph in code review, plus the frozen model protocol. Written
BEFORE the first real Stage 1 / Stage 2 fit.** Canonical retrospective table unchanged at
`98f1c66b7387c16bba6a5463f4e0fa06`; production artifacts unchanged; the preliminary
`arm3_residuals.csv` / `arm3_effects.csv` are preserved byte-for-byte and remain UNINTERPRETABLE.

#### 1. Same-team roster correction

Returning usage requires the player to remain on the **same canonical team**. The builder had
constructed ONE league-wide `ret_ids` set per season, so a player who left KC for BUF still counted
as returning for KC. A player who changes teams now counts as **vacated** for his prior team, and
missing roster evidence produces **NaN**, never 0.

Measured effect of the correction:

| field | changed |
|---|---|
| `qb_returns` | **143 / 859** (flipped 1 -> 0) |
| `ret_wrte_target_share` | **714 / 859** |
| `ret_rb_carry_share` | **482 / 859** |
| `ret_qb_attempt_share` | **442 / 859** |

#### 2. Returning skill production

FROZEN: `half_ppr = fantasy_points + 0.5 * receptions`.

`ret_skill_fantasy_share` uses prior-season **RB/WR/TE** production:
numerator = prior half-PPR from players remaining on the same team at the season-S cutoff;
denominator = that team's total prior RB/WR/TE half-PPR. Quarterbacks are EXCLUDED. A zero or
unavailable denominator produces NaN. It previously computed
`mean(ret_rb_carry_share, ret_wrte_target_share)` -- an average of two OPPORTUNITY shares, not
production; 852/857 rows changed.

#### 3. Exact drive scoring and canonical proxy names

All builders import the shared exact mapping in `drive_definitions.py`; an unmapped
`fixed_drive_result` category RAISES. The substring test survived in
`build_team_offense_panel.py` and `build_allocation_panel.py` for six revisions after v3.3 fixed
only `build_segment_offense.py`.

Measured effect over 861 team-seasons: points/drive **mean -0.2001** (max |d| 0.9716); points/game
**mean -2.2626** (max 10.6875); red-zone TD rate -0.0075 on 247 team-seasons.

Canonical names: `drive_scoring_points_per_drive_proxy`, `drive_scoring_points_per_game_proxy`,
`prior_drive_scoring_points_per_drive_proxy`. The retired names may appear only in
superseded-history sections and are asserted absent from the live panel and at Stage 1 load.

#### 4. Artifact ownership

`build_team_offense_panel.py` solely writes `team_offense_base.csv`; `build_allocation_panel.py`
solely writes canonical `team_offense_panel.csv`; `build_personnel_controls.py` reads the completed
canonical panel. Previously both wrote the same file, so running the efficiency builder AFTER the
allocation builder erased the allocation and OL fields.

#### 5. Stage-specific temporal-CV minimums (FROZEN before fitting)

| stage | min inner-training seasons | min validation seasons |
|---|---|---|
| Stage 1 | **5** | **3** |
| Stage 2 | **2** | **2** |

Stage 2 is deliberately looser because it consumes Stage 1 residuals, which only begin in 2014;
entering-2018 therefore validates on **2016 and 2017** with expanding prior-season training. A
target that cannot meet its frozen minimum is **SKIPPED**, never fitted on relaxed folds.

#### 6. Joint Stage 2 tie and boundary protocol

Every `(alpha_caller, alpha_hc_context)` pair is scored by season-averaged validation MSE.

Exact ties resolve deterministically, without privileging either role:
1. maximise `log10(alpha_caller) + log10(alpha_hc_context)` (greatest TOTAL pooling)
2. then the larger `alpha_caller`
3. then the larger `alpha_hc_context`

If either coordinate reaches a boundary it is extended in that direction by four decades at
half-decade spacing; **both coordinates extend in the same iteration when both hit boundaries**; at
most two extensions per coordinate per direction. Boundary status is persisted **separately** for
caller and HC context, and a persistent upper-boundary selection records effective complete pooling
for **that block only**.

#### 7. `no_prior_history`

Routing-only in Stage 1 and Stage 2. It cannot enter X. Any use in the later player-projection arms
is deferred to a separate prereg decision.

#### 8. Coverage terminology

Stage 2 fits historical effects using **retrospective actual-caller exposure**:
outer retrospective coverage **244/256**, prior-building **116/128**. The **152/256 = 59.4%**
point-in-time figure applies to later Design A application and **must not** be used to describe
Stage 2 training coverage or alpha support.

#### 9. Stage 1 / Stage 2 orchestration

`run_arm3_v38.py` implements the complete pipeline and is the entry point invoked by BOTH the
synthetic end-to-end tests and the real build, so a passing synthetic test exercises the production
code path. Stage 1 targets 2014-2025; Stage 2 entering-season effects 2018-2026.

Stage 2's row universe is supplied by the **Stage 1 residual panel**, not by exposure rows.
Deriving keys from exposure silently DROPPED every team-season whose caller is unknown -- exactly
the rows the v3.6 neutral rule creates -- so those residuals would have vanished from the fit
instead of appearing as all-zero identity rows carrying the intercept.

Versioned artifacts only: `arm3_stage1_{residuals,tuning,fold_losses}_v38.csv`,
`arm3_stage1_feature_schemas_v38.json`, `arm3_stage2_{effects,tuning,fold_losses}_v38.csv`.

`observed_exposure` and `n_observed_team_seasons` are persisted as DIAGNOSTICS only: they cannot
enter X and cannot post-shrink a fitted coefficient.

**Status at that freeze (HISTORICAL, SUPERSEDED):** 141 registered tests passed. No player-projection arm fit; no fantasy outcome
inspected.

### Amendment record (v3.6 -> v3.7, Joseph 2026-07-29, PREFIT)

**Phase 1D.1 corrections plus the Stage 1 / Stage 2 design. IMPLEMENTED BUT NOT EXECUTED ON REAL
OUTCOMES.** Canonical retrospective table unchanged at `98f1c66b7387c16bba6a5463f4e0fa06`;
production projection artifacts unchanged.

#### 1. Reliability is PRECISION-ONLY, never a predictor

`observed_reliability = g/(g+32)` is a **strictly monotone bijection** of
`g = observed_prior_games`: `g = 32r/(1-r)` recovers the count exactly. Admitting `r` as an
independent predictor therefore readmits the forbidden count -- and its left-censoring and calendar
signal -- through the back door. Renaming a count does not remove its information.

Four DISJOINT lists replace the previous two:

| list | contents | may enter X? |
|---|---|---|
| `MODEL_PREDICTORS` | `caller_exposure`, `noncalling_hc_context_exposure` | **yes** |
| `PRECISION_ONLY` | `observed_reliability` | **no** -- shrinkage/uncertainty/diagnostics only |
| `ROUTING_ONLY` | `no_prior_history`, `caller_identity_unknown`, routing flags | **no** |
| `AUDIT_ONLY` | counts, logs, `observable_prior_seasons`, `history_left_censored`, `hc_resume`, `unknown_caller_hc_games` | **no** |

`observed_reliability` may not enter X, hyperparameter selection, stratification, or interaction
generation. `no_prior_history` controls league-prior routing and may be retained as a labelled
missing-history indicator only where this prereg explicitly calls for it; it is **not** coach
quality and is not a Stage 1/Stage 2 identity predictor.

**No double shrinkage.** Stage 2 ridge already partially pools identity coefficients by sample size.
A fitted ridge effect may NOT be multiplied by `observed_reliability` afterwards, and reliability
may NOT be added beside it as another column.

Enforcement is `assert_design_matrix_is_clean(X_columns, stage)`, which inspects the **actual**
design matrix, not only the hand-maintained lists.

#### 2. Canonical reliability schema

The v3.6 artifact shipped DUPLICATE ALIASES -- the claimed rename had only added columns:
`prior_games` **and** `observed_prior_games`, `reliability` **and** `observed_reliability`,
`log1p_prior_games` **and** `observed_games_log`. Legacy aliases are now removed from the persisted
CSV. One name per concept:

```
person_id, target_season, role,
observed_prior_games, observed_games_log, observed_reliability,
no_prior_history, n_observed_prior_seasons, max_observed_season,
observed_history_start, observable_prior_seasons, history_left_censored
```

#### 3. Artifact ownership

| writer | artifacts |
|---|---|
| `build_exposure.py` | `game_level_identity.csv`, `coach_exposure.csv`, `caller_known_share.csv` |
| `build_preseason_snapshot.py` | `retrospective_staff_transitions.csv`, `preseason_staff_snapshot.csv`, `preseason_evidence_ledger.csv` |
| `build_playcaller_table.py` | `actual_play_caller.csv`, `source_ledger.csv` |
| `build_reliability.py` | `coach_reliability.csv`, `coach_reliability_lineage.csv` |

The retrospective writer is removed from `build_exposure.py` and its false success message is
corrected. `tests/test_artifact_ownership.py` fails on any second writer -- this failure mode has
now occurred twice (`source_ledger.csv`, `preseason_staff_snapshot.csv`).

#### 4. Documentation repair

Every live statement that an unknown caller grants the head coach a context effect is corrected. The
obsolete "Unknown caller -> HC context retained | PASS" matrix row is struck through and relabelled
WITHDRAWN -- it asserted the defect, not a requirement. The old rule survives only inside labelled
superseded-history blocks.

#### 5. Stage 1 estimand (replaces the non-identifiable "season fixed effect")

Season S's own coefficient cannot be estimated from seasons < S. Replaced by same-season centering:

    relative_epa_play(team, S) = epa_play(team, S) - league mean epa_play in S
    team_offense_residual      = observed relative_epa_play - predicted relative_epa_play

The same-season league mean is **historical outcome normalization only**: never a preseason
predictor, never consumed by a model running before S completes. `predicted_relative_epa_play` is a
prediction of a CENTERED quantity and must never be reported as an absolute preseason EPA forecast.
Residuals are built for 2014-2025; for target S, training uses only seasons before S.

#### 6. Stage 1 predictors and preprocessing

Frozen personnel controls, `prior_qb_id` categorical: `prior_epa_play`, `prior_success_rate`,
`prior_points_per_drive`, `prior_plays`, `prior_pass_rate`, `prior_ol_sack_rate`, `prior_qb_id`,
`prior_qb_epa_play`, `prior_qb_cpoe`, `qb_returns`, `ret_qb_attempt_share`, `ret_rb_carry_share`,
`ret_wrte_target_share`, `vacated_rush_share`, `vacated_target_share`, `ret_skill_fantasy_share`,
`relocated`.

Medians, scaling parameters and QB vocabulary are learned **inside each inner-training fold**.
Numeric controls standardized; binary indicators kept at natural 0/1. Explicit `MISSING_QB` and
`UNSEEN_QB` levels; target-season categories are never learned, so an unseen target QB receives the
**zero league-prior identity contribution**, not a coefficient fitted on target data. The fitted
feature schema is persisted per target season.

#### 7. Temporal inner validation

Expanding forward chaining in BOTH stages:

    inner training seasons  <  validation season  <  outer target season

No shuffled folds, no generalized leave-one-row-out, no fold training on seasons after its
validation season. MSE is computed **inside each validation season**, then season-level MSEs are
averaged, so a large season cannot dominate tuning. Minimum training-history and
minimum-validation-season requirements are frozen before fitting; if unmet the fold set is empty
rather than silently relaxed. Preprocessing is refit separately inside every inner fold.

#### 8. Stage 2 design

Residuals from seasons < Y only. Blocks: caller identity (`role=caller`) and non-calling HC context
(`role=noncalling_hc_context`), exposures in [0,1]. A self-calling HC contributes only to the
portable caller block; a distinct known caller permits the HC-context block; **unknown games
contribute zero to both**.

Unpenalized intercept and **separate** penalties `alpha_caller` / `alpha_hc_context`. A single
shared penalty imposes one variance prior on two blocks with very different support and is not
retained. Excluded from the identity matrix: `hc_resume`, `unknown_caller_hc_games`, observed game
counts, `observed_reliability`, censoring fields, calendar proxies.

#### 9. Frozen alpha protocol

Grid starts at `np.logspace(-4, 8, 25)` (half-decade spacing) with Stage 1 numeric scaling applied
and Stage 2 exposures on their natural scale. Stage 1 searches one alpha; Stage 2 searches the
two-dimensional caller/context grid.

A boundary optimum extends that boundary by **four decades at the same half-decade spacing**, at
most **two extensions per direction**. Exact score ties resolve toward the **larger** alpha. If the
final upper boundary remains preferred, that is recorded as **effective complete pooling** for that
stage or block -- an interior solution is never forced. All candidates, season-level fold losses,
selected penalties, boundary status and expansion counts are persisted, with Stage 1 and Stage 2
penalties reported separately.

#### 10. Status

`stage_models.py` implements the above. **It has NOT been run on real outcomes.** 97 registered
tests pass (27 new synthetic Stage 1/2 tests). The preliminary `arm3_residuals.csv`
(`2ba6c51769f8dbb85c27c603b2dc93f2`) and `arm3_effects.csv` (`56b47dab2c0e27689ee260deb9e29c4b`) are
**untouched and remain UNINTERPRETABLE** -- they predate every correction from v3.2 onward.

No player-projection arm fit, no outer fantasy outcome inspected, no production change.

### Amendment record (v3.5 -> v3.6, Joseph 2026-07-29, PREFIT)

**Withdraws the unknown-caller HC-context rule. Companion artifacts only; the canonical
retrospective table remains byte-identical at `98f1c66b7387c16bba6a5463f4e0fa06`.**

#### 1. The withdrawn rule, and the damage it did

v3.3 froze `ctx_mask = ~same` for the non-calling-HC-context block, where
`same = known & (hc == caller)`. `same` is False in TWO different situations: a distinct known
person called, **and** the caller is simply unknown. So every unknown-caller game was credited to
the head coach's "delegated offense" effect. It was labelled conservative. **It is not** -- it
assigns offensive residuals to a head coach with no evidence that he delegated, and equally no
evidence that he did not call the plays himself.

**Measured on Andy Reid entering 2026:**

| quantity | games |
|---|---|
| `hc_resume` | **437** |
| known self-called | **192** |
| known delegated (Matt Nagy, KC 2017) | **5** |
| caller UNKNOWN | **240** |

The v3.5 artifact reported `noncalling_hc_context = 245`, and the Phase 1D report described that as
"437 = 192 called + 245 delegated". **That statement was false.** Only **5** games are verified
delegated. The other 240 are unknown-caller games, and every one of them falls in **1999-2013** --
entirely before the attribution window opens in 2014. The "delegated offense" block for
long-tenured head coaches was therefore almost purely an artifact of missing attribution.

#### 2. Corrected rule -- neutral treatment of unknown

Historical game with an unknown caller:
- **no caller identity block activates**
- **no non-calling-HC-context block activates**
- the game may remain in the residual dataset with all coach-identity columns zero
- the known head coach still accrues ordinary **résumé / win / tenure** history from it
- `unknown_caller_share` is emitted so the missing attribution stays visible

Target-season row with an unknown expected caller:
- caller identity contribution routes to the **league prior**
- non-calling-HC-context identity contribution **also** routes to the league prior
- **do not assume the HC delegated; do not assume the HC called plays**
- general HC résumé / change / tenure features are retained

`build_exposure.exposure_long` now uses `hc_context_mask = known & (hc != caller)`. Per team-season
the three shares reconcile: caller exposure = known share, HC-context exposure = known-distinct
share, unknown share = 1 - known share.

#### 3. Rebuilt artifacts and exact regression values

`coach_reliability.csv` gains a fourth role, `unknown_caller_hc_games`, tracked separately and never
folded into HC-context. Asserted identity per person:
`hc_resume = self_called + known_delegated + unknown_caller`.

| person (entering 2026) | caller | hc_resume | known delegated | unknown |
|---|---|---|---|---|
| Andy Reid | 192 | 437 | **5** | **240** |
| Mike McDaniel | 68 | 68 | 0 | 0 |
| Sean McVay | 181 | 149 | 0 | 0 |

Reid's 5 delegated games route to Matt Nagy, KC 2017 -- confirmed against the canonical table, which
records a Reid/Nagy midseason split for that team-season.

#### 4. Reliability semantics -- observed sample, not career experience

Reliability is **kept** and **nothing is imputed**. It is redefined explicitly as *confidence
supported by the caller-performance games actually observed since the attribution window opens*.

It is **NOT** true career experience, **NOT** total career games, and **NOT** evidence that Reid was
inexperienced in 2015. His low early reliability is an accurate statement about available evidence:
the model cannot learn performance from games it has never seen, which is exactly what makes
`observed_prior_games / (observed_prior_games + 32)` the right shrinkage weight.

Caller fields renamed accordingly: `observed_prior_games`, `observed_games_log`,
`observed_reliability`, `observed_history_start`. `history_left_censored` and
`observable_prior_seasons` are retained as **audit diagnostics only**.

The caller table is **NOT** extended backwards and pre-2014 games are **NOT** imputed.

#### 5. Feature-use decision (enforced by test)

Confirmatory caller arms MAY use `observed_reliability`, `no_prior_history`, and observed
expanding-career / rolling-three quality estimates.

Confirmatory caller arms MUST NOT use raw `observed_games_log` / `log1p_prior_games` /
`observed_prior_games` as a quality feature, and must never describe them as true career experience.
They stay in the audit artifact; a separately labelled sensitivity is permitted.

`history_left_censored`, `observable_prior_seasons` and `observed_history_start` are **forbidden as
model features** -- `observable_prior_seasons` is `target_season` minus a constant, so passing it to
a model hands over the season index as a calendar proxy.

**Pre-registered sensitivity: ROLLING-THREE-ONLY caller quality.** Comparable across the whole
2018-2025 outer window, because every fold has at least three prior seasons inside the 2014+
attribution window.

#### 6. Status

62 registered tests pass. The prior test asserting that unknown-caller games grant HC context has
been **deleted as wrong** and replaced with the neutral-treatment cases (2-known/2-unknown shares,
all-unknown, and per-team-season share reconciliation). No model fit, no Phase 1E, production
artifacts unchanged.

### Amendment record (v3.4 -> v3.5, Joseph 2026-07-29, PREFIT)

**Eligibility-rule correction. Changes the PRESEASON EVIDENCE / SNAPSHOT logic only. Historical
attribution is untouched and `actual_play_caller.csv` remains byte-identical at
`98f1c66b7387c16bba6a5463f4e0fa06`.**

#### 1. The prior rule was itself look-ahead leakage

v3.4 rejected qualifying pre-cutoff evidence naming caller A whenever the retrospective opener
turned out to be caller B, labelling it a "conflict". **That is look-ahead leakage.** At the
projection cutoff, A was the information the model possessed; using the later actual opener to veto
A filters the snapshot down to expectations that later proved correct -- an oracle-filtered subset.
Design A would then have measured "expectations that happened to be right", not "what the website
would have believed".

Two further defects followed from the same mistake:
- a row whose retrospective attribution was unresolved could never receive an expected caller, even
  where a pre-cutoff source explicitly named one;
- the evidence loop selected the EARLIEST eligible item, which is backwards for an as-of snapshot.

#### 2. The retrospective opener is now an AUDIT LABEL ONLY

It may be used **only** as a historical attribution label, to measure whether the preseason
expectation later proved correct, in oracle Design B, and as the validation label for proposed
Design C. **It may not determine eligibility for Design A.**

`expectation_matched_actual` is emitted for measurement and, together with
`retrospective_opening_caller_id`, is added to `FORBIDDEN_IN_SNAPSHOT` -- both are asserted absent
from the feature-eligible snapshot, so the eventual answer is never one join away from a feature
builder.

#### 3. Latest-information (as-of) rule

For each team-season: collect ALL qualifying evidence published on or before the cutoff, then take
the **LATEST unambiguous expectation**.

| situation | expected caller |
|---|---|
| earlier A, later explicit B, both pre-cutoff | **B** (later info supersedes) |
| earlier A, B announced AFTER the cutoff | **A** |
| two equally-current pre-cutoff sources disagree | **UNKNOWN** |
| a single source naming "A/B" | **UNKNOWN** |
| pre-cutoff source names A, actual opener was B | **A**, eligible, `expectation_matched_actual=False` |
| pre-cutoff source names A, actual opener unresolved | **A**, eligible, match = NA |

Actual Week-1 identity never breaks a preseason-source tie. Full evidence history is preserved; no
earlier evidence row is overwritten.

#### 4. Conflict redefined

Only disagreement **among qualifying pre-cutoff evidence** can make the expectation ambiguous
(`pre_cutoff_ambiguity`). Expected A vs actual opener B is **not** a conflict -- it is an
**expectation miss**, measured after the fact and reported separately from coverage.

2025 NYG remains correctly UNKNOWN: the pre-cutoff evidence itself reads "Brian Daboll/Mike Kafka".

#### 5. Two quantities, reported separately

Coverage is **never** reduced because an expectation later proved wrong -- that forecast error is
part of a realistic deployable backtest.

- **Point-in-time expectation coverage (outer 2018-2025): 152/256 = 59.4%**
- **Expectation accuracy vs actual opener: 152/152 = 100.0%, 0 mismatches**

**The 100% must not be read as a validated finding.** It is an artifact of the current evidence
pool, which is dominated by preseason play-caller rankings compiled close to the season and by teams
with stable arrangements. It is a property of WHICH rows have evidence, not of preseason
predictability in general. Expect it to fall as harder rows (midseason-hire teams, unresolved
attributions) are researched.

Per-season coverage: 2018 96.9 · 2019 21.9 · 2020 18.8 · 2021 21.9 · 2022 18.8 · 2023 100 ·
2024 100 · 2025 96.9. UNKNOWN reasons: post_cutoff_only 88, unresolved_attribution 12,
missing_date 3, pre_cutoff_ambiguity 1.

#### 6. Design C floor withdrawn

The proposed >=70% HC-change accuracy floor is **WITHDRAWN**. The continuity rule was conditioned on
HC stability to begin with, so a cell tolerating a 30% identity-error rate cannot authorize
categorical caller imputation. No replacement floor is proposed; a separate continuity-validation
protocol is to be drafted after Phase 1C is correct. Nothing calculated, nothing fit.

#### 7. Tests

The test asserting that every recovered expectation must match the retrospective opener was
**deleted as wrong**. Six replacements (A-F) pin the corrected behaviour: expectation-differs-from-
actual is still eligible; unresolved-actual can still be eligible; later pre-cutoff source
supersedes; post-cutoff change does not move the expectation; true pre-cutoff ambiguity is UNKNOWN;
audit fields are isolated from the feature snapshot. **29 tests pass.**

**Status:** no player-projection arm fit, no outer projection outcome examined, production artifacts
unchanged. **2019 research COMPLETED 2026-07-29: 27/27 rows carry a recorded disposition** (7 recovered_eligible, 18 searched_no_qualifying_source, 7 source_date_unverifiable); 2019 final coverage 7/32 = 21.9%. See `coaching/research_attempts_2019.py`.

### Amendment record (v3.3 -> v3.4, Joseph 2026-07-28, PREFIT)

**Date/provenance audit and the point-in-time split. Made BEFORE any player-projection arm was fit
and before any outer projection outcome was examined.**

#### 1. Corrected diagnostic denominator

A previously reported "190 of 392" post-Sept-1 figure was WRONG: it pooled 2026 deploy rows into a
historical denominator. On the 2014-2025 table (384 team-seasons, 360 resolved opening identities,
342 of those carrying a nonblank source date):

- **190/360 = 52.8%** of RESOLVED opening identities have a post-Sept-1 source date
- **190/342 = 55.6%** of DATED resolved opening identities

**September 1 is only a diagnostic probe.** The eligibility gate is the frozen season-specific
projection cutoff defined in section 2.

#### 2. Frozen projection cutoff

The production projection builders record NO as-of date -- verified by grepping
`as_of|asof|cutoff|snapshot_date|projection_date` across all four position builders and
`build_season_dataset.py`, which returns nothing. The frozen rule is therefore the maximal-preseason
fallback: **the day before season Y's first regular-season game**, computed from the schedule. The
live 2026 deployment uses the actual production as-of date (2026-07-21), not a future Week-1 date.

#### 3. Honest date provenance (`date_provenance.py`)

Encoding an uncertain date as the first day of its month or year manufactures precision. In this
project it did so TWICE in the direction that granted FALSE preseason eligibility:

| source | stored | audited byline | effect |
|---|---|---|---|
| `yardbarker2021` | 2021-01-01 (fabricated placeholder) | **Oct 18, 2021** | POST-cutoff |
| `espn2025` | 2025-08-01 (inferred) | **Sep 9, 2025** | POST-cutoff |
| `espn2023` | 2023-08-01 (inferred) | **Aug 23, 2023** | verdict unchanged |
| `espn2024` | 2024-08-01 (inferred) | **Aug 30, 2024** | verdict unchanged |
| `cbs2022phi` | 2022-01-01 (inferred) | none captured | now MISSING |

Every source now carries `source_date_raw`, `source_date_precision`
(exact_day/month/year/missing/inferred), `source_date_lower_bound`, `source_date_upper_bound`,
`source_date_provenance` and `source_date_note`. **Eligibility uses the conservative UPPER bound**:
month-only qualifies only if the month's last day precedes the cutoff; year-only only if Dec 31
does; missing and inferred are NEVER eligible. A placeholder-pattern detector flags any residual
Jan-1/Aug-1 value automatically -- it caught a fourth, `sf2014shared`, that had not been listed.

All **89** sources (13 season tables + 76 per-row) are now in the ledger; 4 are inferred/missing.

#### 4. Publication date is not fact-known date

`preseason_evidence.py` is a SEPARATE ledger answering "who was publicly established to be calling
plays before season Y began", distinct from "who did call plays". A later article that cites an
earlier announcement never backdates itself -- the earlier announcement is entered with its own date.

**Targeted research outcome: NO qualifying pre-cutoff league-wide source was recovered for 2020,
2021, 2022 or 2025.** The Fantasy Index annual "Ranking the play callers 1 thru 32" series is
confirmed to run in those years, but those editions are paywalled/unindexed and return only
fragments. A fragment naming one coach cannot establish 32 identities.

**Returning-caller continuity was REFUSED on principle, not availability.** That a person called
plays late in Y-1 does not establish he would call them in Y; promoting continuity to evidence is
the complement-inference this prereg forbids. If a continuity rule is wanted it must be
pre-registered explicitly as a tested assumption, never smuggled in as evidence.

#### 5. Two physically separate artifacts

- `retrospective_staff_transitions.csv` -- historical attribution ONLY (opening/closing caller,
  within-season changes, realized exposure). Never a season-Y feature source.
- `preseason_staff_snapshot.csv` -- cutoff-eligible fields ONLY. A `FORBIDDEN_IN_SNAPSHOT` list is
  ASSERTED at build time, and an unavailable identity emits **NA, never 0**.

#### 6. POINT-IN-TIME COVERAGE -- the experiment may be underpowered

Measured at the frozen cutoff. **This is NOT T0**, which measures retrospective attribution and
still passes at 244/256 and 116/128.

| season | eligible | row cov | season | eligible | row cov |
|---|---|---|---|---|---|
| 2014 | 5/32 | 15.6% | 2021 | **0/32** | **0.0%** |
| 2015 | 3/32 | 9.4% | 2022 | **0/32** | **0.0%** |
| 2016 | 11/32 | 34.4% | 2023 | 32/32 | 100.0% |
| 2017 | **0/32** | **0.0%** | 2024 | 32/32 | 100.0% |
| 2018 | 31/32 | 96.9% | 2025 | **0/32** | **0.0%** |
| 2019 | 5/32 | 15.6% | 2026 | 32/32 | 100.0% |
| 2020 | **0/32** | **0.0%** | | | |

**OUTER 2018-2025 point-in-time caller coverage: 100/256 rows = 39.1%** (vs 95.3% retrospective).
UNKNOWN reasons (outer): post_cutoff_evidence_only **141**, unresolved_historical_attribution 12,
missing_or_uncertain_date 3. Expected HC identity is available for 100% of outer rows.
Identities recovered by targeted pre-cutoff research: **0**.

**STOP CONDITION MET.** Coverage is both low (39.1%) and extremely uneven -- five of twelve
historical seasons sit at exactly 0% because their only league-wide source postdates their own
season. Under this prereg the coaching arms are therefore **potentially underpowered or
unidentifiable for the play-caller channel on the available archive**. A diluted or null coaching
arm under these conditions **must not be interpreted as evidence that coaching lacks signal** -- it
is an archive limitation. No gate is lowered, the outer window is not narrowed, and no nominal OC is
promoted in response.

#### 7. Deterministic, authoritative builder

`source_ledger.csv` is now emitted by `build_playcaller_table.write_source_ledger()`, not by the
separate reporting script. It was previously possible -- and actually occurred -- for
`actual_play_caller.csv` to hold 2021-10-18 while `source_ledger.csv` held the fabricated
2021-01-01. A registered test asserts the two cannot diverge.

#### 8. Drive-impact artifact reproduced, with a correction

`report_drive_impact.py` regenerates the section-4 numbers from raw PBP. The category enumeration
**reproduces the v3.3 record exactly** (Punt 8671, Touchdown 5099, Field goal 3483, Turnover 2419,
End of half 1719, Turnover on downs 1138, Missed FG 619, **Opp touchdown 611**, Safety 56) once two
bugs in the *reporting script* were fixed: `fixed_drive_result` pairs with `fixed_drive`, not
`drive`, and the measurement is REG-only.

The **impact** figures are restated on 4 seasons / **128** team-seasons (v3.3 quoted 3 seasons / 96
while enumerating 4 -- an internal inconsistency in that record):

- team-seasons affected **127/128**; points/drive mean change **-0.178**, max |change| **0.505**
- red-zone TD rate mean change **-0.037**, max **0.123**
- rank churn 19-25 of 32 teams per season, **up to 11 places**

The v3.3 red-zone figure (-0.005) is NOT reproduced and is superseded; it appears to have divided
all TD drives by red-zone trips, letting an 'Opp touchdown' drive that never reached the red zone
inflate the numerator. The corrected rate restricts the numerator to red-zone-reaching drives.

#### 9. Hash chain

| md5 | status | semantic change |
|---|---|---|
| `ac9883e98cdb1bd04a1c0978746cc023` | superseded | T0-ratified table |
| `391be44c4e4205ceea6456ea935794c0` | superseded | v3.2: `n_games_attributed` COUNTED, not week arithmetic (bye weeks) |
| `3752405a4f499223aac08841dabc5f74` | **provisional/intermediate -- never canonical** | yardbarker2021 date correction only; ledger still divergent, no provenance |
| **`98f1c66b7387c16bba6a5463f4e0fa06`** | **ACTIVE (v3.4 PREFIT)** | audited espn2023/24/25 dates + full provenance + builder-owned ledger |

Companion artifacts: `source_ledger.csv` `931470c713c0d20508d9361b4bf859a0` ·
`retrospective_staff_transitions.csv` `54a048fe7ce4b416c7f980b0a809d0db` ·
`preseason_staff_snapshot.csv` `e91b45b8d5c2fb1a26550e6e9c20c1ea` ·
`preseason_evidence_ledger.csv` `c6ff0f5b40fe2b717cf9ee88975229f0`.

**Status:** no player-projection arm fit, no outer projection outcome examined, production artifacts
unchanged. 18/18 registered tests pass. T0 recomputed and still PASSES (244/256, 116/128).

### Amendment record (v3.2 -> v3.3, Joseph 2026-07-28, PREFIT)

**Five corrections, all made BEFORE any player-projection arm was fit and before any outer
projection outcome was examined.**

#### 1. CALLER-FIRST portable identity (replaces the HC-first collapse)

The v3.2 exposure design collapsed HC==caller games into the HEAD-COACH block. That was a verified
design failure which defeats the experiment's central question. Measured on real data:

| person | caller-block prior games entering 2026, HC-first | caller-first |
|---|---|---|
| Mike McDaniel (MIA 2022-25 called while HC) | **0** | **68** |
| Sean McVay (WAS OC + LA HC) | 32 (Rams years stranded in the HC block) | **181** |

Two blocks are now defined:

- **`caller_effect`** — active for the ACTUAL play-caller on every resolved game, whatever his staff
  title. OC games, HC-who-calls games and any-other-title games accumulate under ONE person
  identity, so play-calling skill transfers across teams and titles.
- **`noncalling_hc_context_effect`** — active for the head coach ONLY on games where a DISTINCT
  KNOWN person called plays. It is the contextual head-coach contribution to a delegated offense and
  **must never be read as a universal head-coach effect** applicable to HC-called games.

**Identifiability.** On a game where the head coach is also the caller, the head-coach and caller
contributions cannot be separately identified. Those games are assigned to the **portable
caller / offensive-lead effect** and contribute nothing to the HC-context block. No game ever
activates both blocks for the same person. The collapse is decided **per game**, so a coach who
takes over or relinquishes play-calling midseason splits correctly between his caller games and his
HC-context games.

#### 2. Unknown-caller treatment (frozen, conservative)

No pooled "unknown person" identity is ever created — that would merge unrelated people into a
single estimated effect. On an unknown-caller game the caller effect remains at the **league prior**
(the person contributes no caller exposure) while the **known head coach still receives HC-context
exposure**. We do not infer that the unknown caller was, or was not, the head coach.
`caller_known_share` is emitted so the dilution is visible. Caller exposure therefore sums to
`caller_known_share`, which is 1.0 only for fully resolved team-seasons.

#### 3. Preseason staff snapshot and the three caller-change concepts

Historical attribution and season-Y preseason routing are now separated.

**Feature-eligible for season Y:**
- `pc_changed_entering` / `hc_changed_entering` — identity OPENING season Y vs the identity that
  ENDED season Y-1.
- `prior_season_pc_changed_within` / `prior_season_hc_changed_within` — lagged completed-season
  metadata.

**NOT eligible as a season-Y preseason feature** (historical attribution metadata only):
- `pc_within_season_change` for season Y itself,
- `historical_primary_caller_id` (determined from completed-season game counts; renamed from
  `pc_primary_person_id` to make its historical nature explicit),
- any eventual game-share blend of callers within Y,
- any assignment learned only from a source published after the projection cutoff.

Season Y's midseason information becomes usable when Y becomes training data for Y+1, never to route
Y's own preseason features. Enforced by a leakage test: a synthetic season where caller A opens and
caller B takes over at midseason must route its preseason row entirely through caller A and must not
carry the within-season-change outcome; the following season may use the completed transition.

#### 4. Drive-scoring PROXY definitions, and an exact category mapping

**Substring classification is withdrawn as unsafe.** `str.contains("Touchdown", case=False)` also
matches **`'Opp touchdown'`** — a defensive or return score by the OPPONENT — which the previous code
credited to the offense as **+7** and counted as a red-zone touchdown. Enumerated frequencies over
2014/2018/2022/2025: Punt 8,671 · Touchdown 5,099 · Field goal 3,483 · Turnover 2,419 · End of half
1,719 · Turnover on downs 1,138 · Missed field goal 619 · **Opp touchdown 611** · Safety 56.

An exact mapping now governs, and any unmapped category raises rather than being silently
classified. `'Touchdown'` is the ONLY category counting as an offensive touchdown, and the same flag
feeds red-zone TD rate.

**MEASURED impact of the fix** (3 seasons, 96 team-seasons) — reported because the ranking effect
must be measured, not assumed:
- **96 of 96 team-seasons affected**
- points/drive mean change **-0.173**, max |change| 0.389
- red-zone TD rate mean change **-0.005**, max |change| 0.043
- points/drive RANK: **20-26 of 32 teams change rank per season, moves up to 6 places**

**Renamed columns**, because a flat TD=7 assumes the extra point and ignores 2-point attempts and
missed XPs, and the measure excludes all defensive and special-teams scoring:
- `off_points_per_game` -> **`drive_scoring_points_per_game_proxy`**
- `points_per_drive` -> **`drive_scoring_points_per_drive_proxy`**

Both feed the Arm-1 composite, whose specification is updated accordingly. Neither may be described
as literal offensive points per game.

#### 5. v3.2 reconciliation enforcement completed

`build_segment_offense.py` now **asserts** zero historical canonical-vs-audit mismatches rather than
merely printing the count, and its output states that canonical `n_games_attributed` is authoritative
with `pbp_games` as an independent agreement check. The stale superseded md5 in
`build_coach_features.py` was repointed to `391be44c4e4205ceea6456ea935794c0`.

**Status:** no player-projection arm fit, no outer projection outcome examined, production artifacts
unchanged.

### Amendment record (v3.1 -> v3.2, Joseph 2026-07-28, PREFIT)

**`n_games_attributed` corrected in the canonical table; table re-frozen under a new md5.**

- **Superseded md5:** `ac9883e98cdb1bd04a1c0978746cc023`
- **New canonical md5:** `391be44c4e4205ceea6456ea935794c0`
- Superseded copy retained on disk as `actual_play_caller.SUPERSEDED_ac9883e9.csv`.

**Reason.** The column was originally derived by WEEK ARITHMETIC
(`min(week_end, team_games) - week_start + 1`), which over-counts any segment spanning a bye week.
GB 2015 weeks 1-14 span 14 WEEKS but only 13 GAMES (bye in wk 7). The column feeds exposure weights
and the frozen `g/(g+32)` reliability directly, so a known-wrong canonical value is not worth
preserving to retain a checksum. **The checksum is an integrity tripwire, not the scientific object.**

**Exact diff — 14 rows, 7 team-seasons, 2015-2017 only, every one a clean +1/-1 pair:**

| season | team | person_id | weeks | old | new |
|---|---|---|---|---|---|
| 2015 | GB | tom_clements | 1-14 | 14 | **13** |
| 2015 | GB | mike_mccarthy | 15-99 | 2 | **3** |
| 2015 | LA | frank_cignetti | 1-13 | 13 | **12** |
| 2015 | LA | rob_boras | 14-99 | 3 | **4** |
| 2015 | MIA | bill_lazor | 1-12 | 12 | **11** |
| 2015 | MIA | zac_taylor | 13-99 | 4 | **5** |
| 2015 | TEN | ken_whisenhunt | 1-8 | 8 | **7** |
| 2015 | TEN | jason_michael | 9-99 | 8 | **9** |
| 2016 | JAX | greg_olson | 1-8 | 8 | **7** |
| 2016 | JAX | nathaniel_hackett | 9-99 | 8 | **9** |
| 2016 | MIN | norv_turner | 1-8 | 8 | **7** |
| 2016 | MIN | pat_shurmur | 9-99 | 8 | **9** |
| 2017 | KC | andy_reid | 1-12 | 12 | **11** |
| 2017 | KC | matt_nagy | 13-99 | 4 | **5** |

**Sourced evidence did NOT change.** A strict diff allowlist asserts that `n_games_attributed` is the
ONLY column with any changed cell, and that row count and row order are identical. Unchanged:
season, team, person_id, actual_play_caller, play_caller_role, week_start, week_end, nominal_oc,
head_coach, source_url, source_date, source_publisher, confidence, ambiguity_status,
pc_is_head_coach, pc_is_nominal_oc, note.

**Counting rules.**
- *Historical (season <= 2025):* distinct actual REG games inside `[week_start, week_end]`, from the
  PBP-derived weekly components using the same normalised team identifiers as
  `build_segment_offense.py`. Weeks spanning a bye are not games.
- *Prospective (2026):* games have not occurred, so the count is REG games **scheduled** for that team
  in the week range, from the nflverse schedule. Explicitly a scheduled count, **not** set to zero
  because PBP is unavailable. Zero 2026 rows changed (already 17).

**Reconciliation tests now enforced** (`fix_games_attributed.py`, re-checked in
`build_segment_offense.py`): canonical count == independently computed `pbp_games` on every
historical segment (0 of 378 disagree); every counted game inside the sourced week range; segment
sums == team distinct REG games for all 360 resolved historical team-seasons; no overlapping ranges;
no played game inside a resolved range left unassigned.

**T0 RECOMPUTED, not assumed.** Outer 2018-2025 **244/256 rows, 4,058/4,254 games**; prior-building
2014-2017 **116/128 rows, 1,856/2,048 games**. Identical to the pre-correction values, as expected
from paired +1/-1 corrections that leave every team-season total unchanged. Both gates still PASS.

**No player-projection arm was fit and no outer projection outcome was examined** at any point in
this correction.

### Amendment record (v3 → v3.1, Joseph 2026-07-28, PREFIT)

**Phase 1 audit required before any player-projection arm is fit.** Five defects confirmed against
the preliminary Arm 3 implementation, all recorded with their pre-audit observations in
`coaching/AUDIT_TODO.md` so no later choice can be justified by which option yields larger effects:

1. **Segment attribution** — play-caller segments currently inherit FULL team-season offense values;
   both callers in a split receive identical metrics. Must be rebuilt from PBP inside each sourced
   `week_start:week_end`, placed against the frozen within-season league distribution.
2. **Arm 3 exposure** — only the primary caller enters the design matrix, discarding all 18 splits'
   secondary callers. Replace with game-share exposure weights (HC changes too), preserving the
   HC==PC collapse without duplication.
3. **Reliability** — coded as `n_seasons/(n_seasons + 32/16)`; the frozen formula is
   `prior_games/(prior_games + 32)` on attributed games, emitted separately for HC and PC.
4. **Expectation controls** — `prior_qb_id` absent; no season indicators despite a code comment
   claiming them. Add the categorical with unknown handling and implement training-season effects,
   or file a prefit amendment for an identifiable alternative for an unseen season.
5. **Regularisation** — `RidgeCV` uses row-level CV, not season-blocked. Stage-2 tuning did NOT
   resolve: **9 of 10 target-season fits selected the grid-maximum alpha of 1000** (primary
   diagnostic), emitting **1,194 of 1,292 effect rows = 92.4% row-weighted**. Stage-1 alpha was
   never persisted, so 92.4% describes **Stage 2 only**.
   **Interpretation (corrected).** Ridge minimises `||y-Xb||^2 + alpha*||b||^2`, so an optimum at
   the grid maximum means the validation wanted **at least** that much shrinkage — widening the
   grid can only select a LARGER alpha and shrink coefficients FURTHER. A ceiling on alpha is a
   floor on effect size, not a cause of over-shrinkage. An earlier claim that the boundary
   'mechanically crushed' the effects was backwards and is withdrawn. **A persistent preference
   for very large alpha may itself be a genuine finding** that coach identities add little after
   controls; that possibility is NOT ruled out.
   **Fix + frozen boundary protocol:** season-blocked inner validation in both stages, with
   preprocessing fit inside each inner-training split; a preregistered broad log-spaced grid; on a
   boundary optimum, expand in that direction by a preregistered number of decades for a
   preregistered maximum number of iterations; if the upper boundary is still preferred at the
   frozen maximum, RECORD IT as evidence favouring effective complete pooling rather than forcing
   an interior solution; persist and report Stage-1 and Stage-2 diagnostics separately, at both
   fit level and row level. Never enlarge the grid until a coach effect becomes non-zero.

### Amendment record (v2 → v3, Joseph 2026-07-28)

1. **Play-caller research standard.** Sources ranked: contemporaneous team announcements /
   press conferences → contemporaneous ESPN, AP, CBS, NFL Network, local beat or established
   football publications → season previews and archived articles → coach biographies or
   retrospectives naming role and season → Wikipedia only where its cited source supports the
   claim. **The article itself must be read.** Search-result snippets, AI summaries, forum posts
   and fan sites do not qualify.
2. **Complement-inference is FORBIDDEN.** A source naming only the head-coach callers does not
   establish the caller for the remaining teams. The `medium`-confidence complement rows used in
   v2 were **removed**; 2018 is now covered by a direct 32-team source instead.
3. **Coverage gates apply to BOTH row and game-weighted coverage** (v2 assessed row primarily).
   Split rows may not inflate the numerator: a team-season with two resolved segments counts
   **once** for row coverage and **by attributed games** for game coverage.
4. **PFF-enhanced personnel sensitivity added** as a diagnostic-only arm (§11). It cannot enter
   nested selection and cannot rescue a failed primary result.
5. **Assertions extended** to T8 (PFF target-season leakage), T9 (PFF raw files stay ignored and
   uncommitted) and T10 (artifact hashes, row counts, feature order, prediction joins stable).

### Amendment record (v1 → v2)

v1 proposed sourcing the `pc_*` feature family from the **nominal offensive coordinator** because no
machine-readable actual-play-caller dataset exists. **That substitution is withdrawn.** It replaced
the variable the experiment is about with a different variable, which would have invalidated the
central question — whether demonstrated offensive-lead quality *travels between teams* — precisely
at the cases that motivate it.

v2 replaces it with a **citation-backed actual-play-caller table**, keyed on a **stable person
identity that survives job titles and teams**, plus **pre-registered minimum coverage gates that
block model fitting** when evidence is insufficient.

The substitution was not merely inelegant, it was measurably wrong: **13 team-seasons in the
assembled table have a play-caller who is neither the head coach nor the nominal OC** (e.g. 2021 LV
= Jon Gruden with Greg Olson as nominal OC; 2023 LV = Josh McDaniels with Mick Lombardi as nominal
OC). A nominal-OC rule mis-attributes every one.

---

## §0. THE QUESTION

Whether the incoming or incumbent offensive leadership has a **demonstrated, portable** track record
that improves player-level season-total half-PPR projections — and if so, *which quantification* of
coach quality does the work. **Seven** competing quantifications are frozen as
**ARM_0, ARM_HC, ARM_1 … ARM_5** and chosen among by nested walk-forward selection using training
seasons only.

1. Does head-coach résumé alone — win percentage, tenure, entering change — add signal? (**ARM_HC**)
2. Do offenses' annual rankings under a play-caller add signal, on top of the HC résumé? (ARM_1)
3. Are continuous offensive-efficiency measurements better than ordinal rankings? (ARM_2)
4. Does coach performance survive controls for team, quarterback and roster quality? (ARM_3)
5. Are scheme and positional-allocation tendencies more useful than generic coach quality? (ARM_4)
6. Does a combined quality-plus-scheme representation improve the website's projections? (ARM_5)

ARM_HC was added in v3.9 because the HC-context block of ARM_3 measures only DELEGATED offensive
context and collapses to numerical zero in six of nine target seasons — so it never answered whether
general head-coach win history, tenure or change carries signal. That is now its own arm, and it has
full point-in-time identity coverage.

---

## §1. IDENTITY AND ROLE ATTRIBUTION

### §1.1 Four separate identities

| Identity | Source | Grain | Coverage (2014–2026) |
|---|---|---|---|
| `head_coach` | nflverse `load_schedules` | **game** | 100% |
| `actual_play_caller` | citation-backed table, `playcaller_sources.py` | game-range | **56.7%** (see §1.6) |
| `nominal_oc` | Wikipedia season articles + cited current-OC list | season | 90.8% — **metadata only** |
| `pc_is_head_coach` | derived: play-caller vs head coach | game-range | wherever the play-caller is known |

### §1.2 Attribution rule (frozen)

**Offensive results are attributed to the ACTUAL PLAY-CALLER.** Historical performance belongs to
**the function the person actually performed, not the title he held.**

- A **nominal-OC season is never credited as a play-calling season** without evidence that the
  nominal OC actually called plays.
- **Nominal OC is staff-continuity metadata only.** It is never promoted to play-caller, and it
  never overrides a play-caller determination. A change of nominal OC **does not** set
  `pc_changed_entering = 1` when the evidenced play-caller is unchanged.
- Where no reliable play-caller can be established, the observation routes to **UNKNOWN** → league
  prior, `reliability = 0`, `no_prior_history = 1`. It is **never** backfilled with the nominal OC.

### §1.3 Stable person identity

`person_id` is a normalized-name key that is **constant across every team and every job title** the
person ever holds, with generational suffixes folded (sources write both "Pete Carmichael" and
"Pete Carmichael Jr." for one man). This is what makes a record portable: Mike McDaniel's four
Miami seasons — held under a **head-coach** title — carry the same `person_id` as his 2026 Chargers
**coordinator** season, so his play-calling record follows him. Verified: no two distinct NFL
play-callers in 2014–2026 collide on a normalized name.

### §1.4 Role derivation — sources are not trusted

`play_caller_role` is **derived** by comparing the play-caller against the authoritative nflverse
head-coach table, never taken from a source's label. Published tables mislabel roles routinely
(Fantasy Index 2026 lists Sean McVay as an "offensive coordinator"; Yardbarker 2022 lists Luke
Getsy as a "head coach"). Every source/derived disagreement is reported.

### §1.5 Effective dates, midseason changes, ambiguity

- Head coach is attributed **game-by-game** (43 of 893 team-seasons had a midseason HC change).
- A midseason play-calling change is **split by games** where a defensible effective week exists
  (e.g. 2015 GB — McCarthy reclaimed play-calling, NFL.com dated 2015-12-13, week 15; 2020 CHI —
  Nagy relinquished after nine games, week 11). Otherwise the team-season is marked
  **ambiguous** and excluded from that coach's quality history — never split by guesswork.
- Co-play-callers with no single attributable person → **ambiguous** (2021 MIA, 2022 NE).
- Sources in direct conflict → **unresolved**, never silently reconciled (2022 PHI: Yardbarker
  names Sirianni, CBS reports Steichen took full-time play-calling).

### §1.6 PRE-REGISTERED MINIMUM COVERAGE GATES — these block model fitting

Assessed on **both** row and game-weighted coverage; **both** must clear the threshold.

| Scope | Gate | **Measured 2026-07-28** | Status |
|---|---|---|---|
| Outer-test team-seasons 2018–2025 | **≥ 95% row AND game** | **95.3% row / 95.4% game** (244/256; 4,058/4,254 games) | **PASS** |
| Historical team-seasons building their priors (2014–2017) | **≥ 90% row AND game** | **90.6% row / 90.6% game** (116/128; 1,856/2,048 games) | **PASS** |
| Deploy season 2026 | — | 100% row / 100% game | ok |

**Row coverage counts each (season, team) once** regardless of how many caller segments it carries,
so a midseason split cannot inflate the numerator. **Game coverage** is attributed games over
actual team games, capped per team-season at the real schedule length.

**No model may be fit while either gate is failing.** On failure the required output is the
unresolved rows, the search avenues attempted, the best available evidence and the exact coverage —
**not** a narrowed outer window and **not** nominal-OC attribution.

**Blocking seasons: 2014, 2015, 2016, 2019** — 127 of the 131 unresolved team-seasons. No
qualifying 32-team play-caller source exists for any of them; see
`coaching/data/RESEARCH_LOG.md` for the eleven search avenues attempted and their outcomes.

### §1.7 Table schema — `data/actual_play_caller.csv`

`season, team, person_id, actual_play_caller, play_caller_role, week_start, week_end,
n_games_attributed, nominal_oc, head_coach, source_url, source_date, source_publisher, confidence,
ambiguity_status, pc_is_head_coach, pc_is_nominal_oc, note`

**Confidence levels.** `high` — the source names this person as the team's play-caller.
`medium` — the source establishes the play-caller is *not* the head coach and the complement is
taken (documented inference, disclosed; **excluded from the primary coverage number**).
`conflict` — sources disagree → UNKNOWN. Absent → UNKNOWN.

All 238 currently resolved rows are `high`. No `medium` rows are admitted under v2.

### §1.8 Sources of record

| Season(s) | Source | Publisher | Date |
|---|---|---|---|
| **2017 (all 32)** | [ESPN — "The playcallers for all 32 teams and where their offenses rank"](https://www.espn.com/nfl/story/_/page/32for32x17115/nfl-2017-playcallers-all-32-nfl-teams-how-their-offense-ranks) | ESPN | 2017-11-15 |
| **2018 (all 32)** | [Fantasy Index — "Offensive coaches: Ranking the play callers 1 thru 32"](https://fantasyindex.com/2018/06/28/ian-allan/offensive-coaches) | Fantasy Index | 2018-06-28 |
| 2018 corroboration (14 HC callers) | [ESPN NFL Nation](https://www.espn.com/blog/nflnation/post/_/id/277514/finding-the-next-sean-mcvay-head-coaches-who-call-offensive-plays) | ESPN | 2018-07-12 |
| 2017 KC midseason split (wk 13) | [CBS Sports — Reid cedes play-calling to Nagy](https://www.cbssports.com/nfl/news/andy-reid-reportedly-cedes-play-calling-duties-to-offensive-coordinator-matt-nagy/) | CBS Sports | 2017-12-03 |
| 2018 CLE midseason split (wk 9) | [Newsweek — Jackson and Haley fired](https://www.newsweek.com/hue-jackson-todd-haley-fired-cleveland-browns-midway-through-season-1192594) | Newsweek | 2018-10-29 |
| 2020 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_callers_from_every_nfl_team/s1__32555903) | Yardbarker | 2020-10-22 |
| 2021 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__35857394) | Yardbarker | 2021 |
| 2022 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__37978942) | Yardbarker | 2022-12-05 |
| 2023 | [ESPN](https://www.espn.com/nfl/story/_/id/38108724/key-intel-all-32-nfl-playcallers-including-mike-mccarthy) | ESPN | 2023-08 |
| 2024 | [ESPN](https://www.espn.com/nfl/story/_/id/41018846/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-nathaniel-hackett) | ESPN | 2024-08 |
| 2025 | [ESPN](https://www.espn.com/nfl/story/_/id/46137832/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-brian-schottenheimer) | ESPN | 2025-08 |
| 2026 | [Fantasy Index](https://fantasyindex.com/2026/02/20/around-the-nfl/ranking-the-offensive-play-callers) | Fantasy Index | 2026-02-20 |
| midseason changes | cached Wikipedia team-season / coach articles | Wikipedia | various |

### §1.9 Strict-priority timing

Every historical quantity attached to a target-season **Y** row uses only games and seasons
**strictly before Y**. Asserted mechanically per fold (§8-T1).

---

## §2. COMMON SHRINKAGE (frozen — not tunable)

```
reliability  = prior_games / (prior_games + 32)
shrunk_value = reliability * observed_value + (1 - reliability) * league_prior
```

League priors: **0.500** for win percentage and rank percentiles; **0.000** for season-normalized
z-scores and residual effects.

**Reliability is a WEIGHT INSIDE this formula and nothing else.** It is not emitted as a feature, and
neither are `log1p(prior_games)`, `prior_games`, or `no_prior_history` — see §4.0. A fitted Arm 3
ridge coefficient is **never** multiplied by reliability afterwards: Stage 2 has already pooled it by
sample size, and a second multiplication shrinks twice.

Two DISTINCT states both route to the league prior, and they are never collapsed into one flag:
**unknown identity** (no person is named, so no person's history applies) and **known identity with no
qualifying history** (we know who, and he has called zero prior games). Both are reported separately in
`arm_feature_coverage_v39.csv` via `identity_state`. **Unknown coaches are uncertain, not bad.**

Both windows computed: **career-to-date** through Y−1 and **rolling three-season** through Y−1.
The expanding league mean is recomputed from seasons `< Y` only.

The 32-game constant, 3-season window and league priors are **frozen** and may not be tuned against
any evaluation outcome.

---

## §3. DATA — built and validated 2026-07-28

### §3.1 Team-offense panel — `build_team_offense_panel.py` + `build_allocation_panel.py`
861 team-seasons, **1999–2025**, 33 columns.

**Frozen PBP filters:** `season_type == 'REG'`, `posteam` non-null; offensive plays =
`play_type ∈ {pass, run}`; **kneels, spikes and two-point conversions excluded** from all rate
metrics (removes 0.3% of scrimmage plays); drive metrics from `fixed_drive` / `fixed_drive_result`.

**Pace** (`seconds_per_play`) is the mean gap between consecutive snaps *within a drive* from
`game_seconds_remaining`, keeping gaps in (0, 60] s — 77% of plays qualify. This replaces v1's
all-null placeholder.

100% non-null: `epa_play`, `success_rate`, `yards_play`, `explosive_rate`,
`drive_scoring_points_per_drive_proxy`,
`redzone_td_rate`, `neutral_pass_rate`, `early_down_pass_rate`, `redzone_pass_rate`,
`seconds_per_play`, `drive_scoring_points_per_game_proxy`, `rb_carry_share`, `qb_carry_share`,
`rb_target_share`,
`wr_target_share`, `te_target_share`, `rz_{rb,wr,te,qb}_share`, `ol_sack_rate`.
**74.3%**: `proe` and `team_adot` — nflverse's `xpass`/air-yards models begin in **2006**; pre-2006
seasons carry native NaN, never an imputed value. Every outer test season and its training window
sit inside the covered era.

Face validity: 2024 best offenses by EPA/play = BAL, BUF, DET, WAS, TB, PHI; worst = CLE, LV, TEN.
2024 top TE target shares = ARI 34.0%, KC 33.6%, LV 33.4%. Pace: DAL fastest, GB slowest.

### §3.2 Arm 3 personnel controls — `build_personnel_controls.py`
896 team-seasons. Every column knowable **before** season S: lagged team form
(`prior_epa_play`, `prior_success_rate`, `prior_drive_scoring_points_per_drive_proxy`,
`prior_plays`,
`prior_pass_rate`, `prior_ol_sack_rate`), preseason QB identity and continuity (`prior_qb_id`,
`prior_qb_epa_play`, `prior_qb_cpoe`, `qb_returns`), returning shares
(`ret_qb_attempt_share`, `ret_rb_carry_share`, `ret_wrte_target_share`,
`ret_skill_fantasy_share`), `vacated_rush_share`, `vacated_target_share`, and `relocated`.
All 100% non-null across 2014–2026.

> Where a season's week-1 roster does not yet exist (the unplayed deploy season), returning shares
> fall back to the season roster and, failing that, emit **NaN — never 0**, which would otherwise
> read as "the entire roster departed" and hand every team a fabricated vacated share of 1.0.
> This bug was caught and fixed before freezing.

### §3.3 Player panel
`fantasy/seasonal_projections/season_dataset_2014_2026.csv` — the exact frame the four shipped
position builds consume. Target = **observed season-total half-PPR** summed from weekly REG stats,
identical to `build_rb_projection.season_total_target()`.

---

## §4. THE SEVEN FROZEN REPRESENTATIONS

**Authoritative ordered lists: `coaching/data/arm_feature_manifest_v39.json`.** That artifact pins,
per `(position, veteran/rookie bucket, arm)`, the COMPLETE design matrix — the production baseline in
its exact shipped order followed by that arm's ordered coaching additions. This section is the prose
statement of what that manifest contains; if the two ever disagree the manifest is what ran and the
build asserts them equal.

### §4.0 Player-feature policy (binding on every arm)

**MAY NOT enter player-model X, in any arm:** `observed_reliability` or any reliability field; raw or
log history counts (`observed_prior_games`, `observed_games_log`, …); `no_prior_history`; censoring
fields (`history_left_censored`, `observed_history_start`); observable-window fields
(`observable_prior_seasons`); exposure counts; and any retired drive-metric name.

Reasons: `reliability = g/(g+32)` is a strictly monotone bijection of the count, so admitting it
readmits the count; the caller count is left-censored at 2014 while HC résumé reaches 1999, so the
count carries the season index; `observable_prior_seasons` is literally `target_season` minus a
constant.

**MAY enter:** shrunk historical estimates (reliability having acted as the internal weight), tenure,
entering-change indicators, `caller_is_head_coach`, and the Arm 3 ridge effects **unmultiplied**.

Unknown identities and known-no-history identities both receive the frozen league-prior VALUE, never
NaN (v3.9 amendment §5 gives the frozen table). Enforced by
`build_arm_features_v39.assert_no_forbidden_features` against the actual emitted columns and against
every manifest arm.

### §4.1 The representations

**ARM_0 — CURRENT BASELINE.** The exact ordered `feature_cols` of each position's shipped bundle, per
bucket: veteran 32 (identical across all four positions, including the existing `coach_changed` and
`qb_changed`), rookie RB 41 / WR 44 / TE 44. `depth_rank` excluded (RB prereg Amendment 1). **No
coaching feature beyond the baseline.** There is **no QB rookie bundle** — that arm was HELD — so QB is
evaluated on the veteran path only and the QB top-12 cohort covers veterans.

**ARM_HC — HEAD-COACH RÉSUMÉ AND CONTINUITY (4).**
`hc_career_win_pct_shrunk`, `hc_roll3_win_pct_shrunk`, `hc_tenure_current_team`,
`hc_changed_entering`. Wins/games are counted game-by-game from the frozen schedule snapshot,
**regular season only, no playoffs**; a tie counts **0.5 win** and stays in the denominator. Expected
HC identity has full point-in-time coverage. ARM_HC contains **no caller feature and no HC-context
effect**. McVay-style offensive-mind value stays in the CALLER channel, so ARM_HC does not represent
it.

**ARM_1 — SIMPLE COACH RÉSUMÉ (9).** ARM_HC plus `pc_career_off_rank_pct`,
`pc_roll3_off_rank_pct`, `pc_tenure_current_team`, `pc_changed_entering`, `caller_is_head_coach`.

The rank composite uses the offense's within-season league rank percentile
`1 - (rank - 1) / (n_teams - 1)` (1.0 best) in **drive-scoring points/game proxy, yards/play,
EPA/play, success rate, drive-scoring points/drive proxy**, equal weight, requiring **≥3 of 5**
components. Segment values are placed against the **full team-season** reference distribution, then
aggregated across the caller's strictly prior segments **weighted by `pbp_games`**, then shrunk.

**ARM_2 — CONTINUOUS OFFENSIVE EFFECTIVENESS (15).** Within each source season standardize across
teams (`z = (team − mean) / sd`), aggregate each z across the caller's strictly prior segments
weighted by `pbp_games`, shrink toward 0.000. Career and rolling-three versions of
`pc_*_epa_play_z`, `pc_*_success_rate_z`, `pc_*_drive_scoring_points_per_drive_proxy_z`,
`pc_*_yards_play_z`, `pc_*_explosive_rate_z`, `pc_*_redzone_td_rate_z`, plus
`pc_tenure_current_team`, `pc_changed_entering`, `caller_is_head_coach`. Dimensions stay separate —
**no hand-weighted composite**, and no count or reliability field.

**ARM_3 — PERSONNEL-ADJUSTED COACH EFFECT (3).**
`caller_adjusted_offense_effect`, `noncalling_hc_context_effect`, `caller_is_head_coach`, read
directly from `coaching/data/arm3_stage2_effects_v38.csv` at the target season.

*Stage 1 estimand.* There is **no season fixed effect** — season S's own coefficient is not
identifiable from seasons `< S`. The target is same-season-centred
`relative_epa_play(team, S) = epa_play(team, S) − league mean epa_play in S`, predicted from the §3.2
controls (all strictly prior), with `team_offense_residual = observed − predicted`. The same-season
league mean is historical outcome normalization only and never reaches a preseason predictor.

*Stage 2 blocks (caller-first, v3.3/v3.6).* A **portable caller effect** active for the ACTUAL
play-caller on every resolved game whatever his title, and a **non-calling-HC context effect** active
for the head coach ONLY on games where a DISTINCT KNOWN person called. The latter is the head coach's
contribution to a DELEGATED offense and must never be read as a universal head-coach effect.

*Frozen target-season routing:*

| situation | caller effect | HC-context effect |
|---|---|---|
| unknown caller | 0 | 0 — assume neither delegation nor self-calling |
| self-calling head coach | fitted caller effect | **exactly 0**; the effect appears exactly ONCE |
| distinct known caller | fitted caller effect | that head coach's fitted context effect |
| identity absent from the target-season table | 0 (league prior) | 0 (league prior) |

*Availability.* The effect table covers target seasons **2018–2026 only**, because residuals begin in
2014 and the frozen Stage 2 minimums make entering-2018 the earliest estimable target. Targets
2014–2017 carry all-zero Arm 3 effects; nothing is backfilled.

**ARM_4 — SCHEME AND FANTASY ALLOCATION (QB/RB/WR 10, TE 8).** Career and rolling-three shrunk caller
tendencies, built from the caller's own segments, appended **position-specifically**:

| Model | Appended (career + rolling-three each) |
|---|---|
| QB | plays/game, pass tendency, pace, red-zone pass rate, QB carry share |
| RB | plays/game, rush tendency, RB carry share, RB target share, RB red-zone share |
| WR | plays/game, pass tendency, WR target share, `team_adot`, WR red-zone share |
| TE | plays/game, pass tendency, TE target share, TE red-zone share |

`rush_tendency_z` is the exact negation of `pass_tendency_z` (within a source season
`z(1−x) = −z(x)`, and negation commutes with shrinkage toward 0).

**ARM_5 — ADJUSTED QUALITY PLUS SCHEME (QB/RB/WR 17, TE 15).** `hc_tenure_current_team`,
`hc_changed_entering`, `pc_tenure_current_team`, `pc_changed_entering`, `caller_is_head_coach`, the
two Arm 3 effects, and that position's ARM_4 block. **Excludes** ARM_1's win-percentage and rank
features, ARM_2's efficiency z-scores, and every reliability/count/no-history/censoring field — by
construction, asserted in `manifest()`.

---

## §5. NESTED REPRESENTATION SELECTION

For each position and outer test season Y: training data = seasons `< Y`; compare
**ARM_0, ARM_HC, ARM_1, ARM_2, ARM_3, ARM_4, ARM_5** by **EXPANDING FORWARD-CHAINING inner
validation within training data only**:

    inner training seasons  <  validation season  <  outer target season

Frozen minimums **2 training** and **2 validation** seasons; a target that cannot meet them is
SKIPPED, never fitted on relaxed folds. For outer 2018 the folds are exactly
`train 2014-2015 → validate 2016` and `train 2014-2016 → validate 2017`.

**Leave-one-season-out is withdrawn**: it trains a fold on seasons AFTER its validation season, which
is look-ahead inside the selection step.

Use the **exact fixed production model family and hyperparameters** from the position's shipped
bundle — the player model is **never** retuned. Preprocessing and categorical handling are learned
inside each inner-training fold. Rank arms by mean inner-validation MAE on the
**ARM_0-defined draft-relevant cohort** (QB top 12, RB top 24, WR top 24, TE top 12).

An arm is **eligible** only if inner full-panel MAE worsens by ≤ **0.25** points. If the best eligible
coaching arm improves inner top-cohort MAE by **< 1%** vs ARM_0 → **select ARM_0**. If multiple arms
are within **0.25** top-cohort MAE points of the best → select the arm with **fewer added features**,
then the frozen arm order. Fit the selected arm on all seasons `< Y`; predict Y.

*Recorded consequence of the rule as written:* the 1% gate applies to the BEST coaching arm and the
tie-band then selects on parsimony, so the finally selected arm can be one whose own improvement is
below 1%.

The resulting outer predictions are the **sole primary challenger**. Individual fixed arms are
diagnostic and can never be selected using outer-test results. **Design A is the only input to
selection**; Design B is an oracle diagnostic and can never enter it.

---

## §6. OUTER EVALUATION

Outer test seasons **2018–2025**; **2021–2025** reported separately as the recent panel. Per
position, nested-selected pipeline vs ARM_0 **on identical rows**. Report full-panel and top-cohort
MAE; RMSE; mean and median bias; mean within-season Spearman; per-season changes; player-clustered
and team-season-clustered bootstrap intervals; **selection frequency across ARM_0, ARM_HC and
ARM_1–ARM_5**; each fixed arm as diagnostic only. Bootstrap: **20,000 draws, seed `20260728`**.
Fixed arms carry **Holm correction across the SIX nonbaseline alternatives (ARM_HC and ARM_1–ARM_5)
within each position**.

### §6.1 The frozen improvement statistic

`top_cohort_MAE(ARM_0) − top_cohort_MAE(challenger)`, **POOLED over all outer top-cohort rows**;
positive means the challenger is better. Frozen in the v3.9 amendment because §7(1) said only
"top-cohort MAE": pooling matches the plain reading, matches what the clustered bootstrap in §7(2)
resamples, and leaves §7(3)/(4) to carry the per-season evidence rather than duplicating it. **The
identical function computes the observed statistic and every permutation-placebo draw.**

---

## §7. PRIMARY PASS RULE

A position becomes a **developmental candidate** only if the nested-selected pipeline: (1) improves
top-cohort MAE by **≥ 3%**; (2) has **both** clustered 95% interval upper bounds **< 0**;
(3) improves top-cohort MAE in **≥ 6 of 8** outer seasons; (4) improves in **≥ 4 of 5** recent
seasons; (5) improves mean within-season top-cohort Spearman by **≥ 0.005**; (6) worsens full-panel
MAE by **≤ 0.25** points; (7) worsens full-panel RMSE by **≤ 1%**; (8) selects a non-baseline arm in
**≥ 4 of 8** folds; (9) beats the **95th percentile** of the frozen within-season coaching-feature
permutation placebo; (10) passes every timing, leakage, coverage and artifact-integrity assertion.

All ten conditions are evaluated by `run_coach_projection_experiment_v39.primary_verdict`, which reads
**only** the nested-selected Design A pipeline. The **placebo of §7(9) is the nested-selected
pipeline** too: every draw permutes complete team bundles within season and then reruns
representation selection independently for every outer fold, so a draw may select a different arm in
each fold exactly as the observed pipeline does. Scoring a single modal fixed arm under permutation is
**not** this condition.

### §7.1 EXACT denominators (v3.9b)

Conditions 3, 4 and 8 require the frozen denominator to be **present**, not merely enough successes:

- **C3** — the cohort's season set must equal exactly `{2018 … 2025}`, with no duplicate
  `(player_id, season)` rows, **and** ≥ 6 seasons improve.
- **C4** — `{2021 … 2025}` must all be present, no duplicates, **and** ≥ 4 improve.
- **C8** — the fold-selection key set must equal exactly `{2018 … 2025}`, **and** ≥ 4 be non-baseline.

A missing, duplicated or unexpected season or fold key fails the relevant condition and is named in
`denominator_problems`. A truncated run therefore **cannot** produce a developmental candidate.

### §7.2 What condition 10 actually checks (v3.9c)

`preflight()` runs **21** deterministic checks, reading no outcome (20 at v3.9c; `assembly_module_contract`
added at v3.9e):

18 protected hashes · the five v3.9 artifacts against their pins · **all five artifacts load with a
valid schema** (`v39_artifacts_readable`) · no unauthorized `*_v39.*` and no coaching parquet ·
feature-table key uniqueness and 416 rows per design · Design A outer identity coverage exactly
152/256 · unknown and known-no-history routing plus the no-NaN rule · forbidden-feature and
retired-name policy across every manifest arm · manifest full X == bundle + ordered additions ·
explicit `QB/rookie: null` · **coverage FULL-FRAME reconciliation against a fresh canonical derivation
— every cell, every arm, every identity state** · lineage strict timing · **lineage states the PRIMARY
policy and no live row asserts a source-date gate** · contribution-lineage reconciliation · Design B
oracle-labelled and unreachable from selection · production models byte-identical · **no executable path
to a real fantasy outcome, and `assemble_real_panel()` is authorization-first and unimplemented** ·
every pipeline timing/leakage/row-identity assertion actually EXECUTED · the run-mode lock contract.

**Fail-closed.** Every artifact is loaded defensively; a missing, unreadable, malformed, schema-invalid
or empty input is reported by `v39_artifacts_readable` and each dependent check returns
`blocked by <input> load failure (<error>)`. The preflight always returns its structured record and
never raises.

### §7.3 Run modes (v3.9b)

    synthetic_prefit : BOTH real-fit locks MUST be closed
    authorized_real  : BOTH locks MUST be open (module constant AND environment token)

A partially authorized state is invalid in both modes and an unknown mode is invalid — the contract
fails closed. The mode governs **only** the lock expectation; it never relaxes an artifact, timing,
leakage, coverage or feature-policy check. This resolves the v3.9a paradox in which an authorized real
run would have failed C10 automatically and could never have produced a developmental candidate.

**No individual fixed arm can rescue a failed nested-selected result.** A result that selects Arm 0
in nearly every fold is **evidence that coaching features do not add stable signal** — a
publishable outcome, not a failure.

---

## §11. PFF-ENHANCED PERSONNEL SENSITIVITY (DIAGNOSTIC ONLY)

The public-data experiment remains the **sole primary test**. This adds one pre-registered
sensitivity. It **cannot** select a production feature representation and **cannot** rescue a
failed primary result.

**Approved files only** (regular-season scope confirmed before use): `nfl_offense_blocking_YYYY`,
`nfl_offense_pass_blocking_YYYY`, `nfl_line_pass_blocking_efficiency_YYYY`, YYYY = 2013–2025.

> **Path note.** The ratifying prompt cited these as `nfl_YYYY/offense_blocking.csv`. They were
> renamed to the repo convention on 2026-07-28 and now read `nfl_YYYY/nfl_offense_blocking_YYYY.csv`
> etc. Same 52 files, same content.

**Excluded:** the PFF passing / receiving / rushing summary exports **include postseason games**
and are barred from this regular-season experiment.

For target team-season S, features derive from **S−1 only**; no season-S PFF performance enters.
Prior-team position-group aggregates: QB snap-weighted offensive grade; RB/FB snap-weighted
offensive grade; WR/TE snap-weighted offensive grade; OL snap-weighted pass-block grade; OL
snap-weighted run-block grade; OL pressures allowed per pass-block snap; team pass-blocking
efficiency. Weights are prior-season offensive or pass-block snaps. Aggregates are standardized
within source season, carry coverage / sample-size / missing-history fields, and are shrunk toward
the expanding position-season mean. **Missing grades are never encoded as zero.**

Used **only** to build a PFF-enhanced variant of the Arm 3 expectation model. Reported: public vs
PFF-enhanced adjusted coach effects, sign agreement, rank correlation, and fixed Arm 3 / Arm 5
projection diagnostics. **Never added to primary nested arm selection.**

No raw PFF rows are copied into `coaching/` or committed; any row-level intermediate stays ignored.
Only non-licensed aggregate diagnostics are saved.

---

## §8. ASSERTIONS

- **T0 — coverage gate.** §1.6 must pass on **both** row and game coverage for every scope before
  any fit. **PASSED 2026-07-28** (95.3/95.4 outer, 90.6/90.6 prior).
- **T1 — timing.** Every coaching feature on a season-Y row derives only from games `season < Y`.
- **T2 — walk-forward.** No fold trains on its own test season.
- **T3 — shuffle-leak probe.** Coaching features carry aligned signal on a proof-model and lose it
  when the target is shuffled within season.
- **T4 — no double-counting.** Where the head coach is also the caller, the effect appears exactly
  once — in the portable caller block — and the HC-context contribution is exactly 0.
- **T5 — unknown routing.** No qualifying history → the frozen league-prior VALUE, never NaN, never a
  penalty and never a bonus. `reliability` and `no_prior_history` are DIAGNOSTICS and are asserted
  ABSENT from player X (§4.0); an unknown identity and a known identity with no history are reported as
  two distinct `identity_state` values rather than one flag.
- **T6 — artifact integrity.** `rookie_ppg_model.pkl` md5 `872467b2295fce27761f9e04da01b6e8`
  unchanged; the four shipped position pkls unchanged; no parquet and no licensed PFF table written
  into the repo. **This experiment never rewrites a production artifact.**
- **T7 — routing assertions.** §8.1.
- **T8 — PFF timing.** Every PFF feature attached to season S derives from seasons `< S`; no
  season-S PFF performance enters any control.
- **T9 — PFF containment.** Raw PFF files remain gitignored and uncommitted; no row-level PFF data
  is written into `coaching/`.
- **T10 — artifact stability.** Artifact hashes, row counts, feature order and prediction joins
  unchanged end-to-end.

**Production hashes captured 2026-07-28 (T6 baseline, verified unchanged at handback):**
```
qb_veteran_model.pkl  7632549f95995b9702baefdf016d7271
rb_rookie_model.pkl   da230ee66575ca574f02cbc2139e1a80
rb_veteran_model.pkl  167aca71a8511afcced37c0abc846004
te_rookie_model.pkl   f79dad0ab26af5cb4e06a9f1723328cd
te_veteran_model.pkl  5a2f0b504d4cc6fc9a2e04453fd76a44
wr_rookie_model.pkl   6c9a3f3ed02ce32c53594f383aade882
wr_veteran_model.pkl  17dfbcf01054bdd5ce032f2b55df9ad2
rookie_ppg_model.pkl  872467b2295fce27761f9e04da01b6e8
```

### §8.1 Routing assertions — VERIFIED against `team_coach_features_design_a_v39.csv`

Values below are the emitted v3.9 features. `reliability` figures that appeared here in earlier
revisions are **withdrawn as feature values** (§4.0); reliability acts only inside the shrinkage.

**Los Angeles Chargers, 2026** ✅
```
expected_hc_id                  = jim_harbaugh     hc_changed_entering       = 0.0
expected_caller_id              = mike_mcdaniel    pc_changed_entering       = 1.0
caller_is_head_coach            = 0.0              pc_tenure_current_team    = 0.0
caller_adjusted_offense_effect  = +0.005262
noncalling_hc_context_effect    =  2.368030e-18    [NUMERICAL zero — see below]
nominal_oc                      = Mike McDaniel    [metadata only]
McDaniel's prior play-calling  : MIA 2022-2025 under a HEAD-COACH title = 68 games
```
His Miami record follows his **person identity across the title change**, which is the whole point.
Harbaugh IS a distinct non-calling head coach, so his context coefficient legitimately applies — and
entering 2026 that coefficient is numerically zero because the HC-context block sat at the extended
upper alpha boundary. The feature carries the **fitted** value; it is not forced to 0.

**Los Angeles Rams, 2026** ✅
```
expected_hc_id                  = sean_mcvay       hc_changed_entering       = 0.0
expected_caller_id              = sean_mcvay       pc_changed_entering       = 0.0
caller_is_head_coach            = 1.0              pc_tenure_current_team    = 9.0
caller_adjusted_offense_effect  = +0.025936
noncalling_hc_context_effect    =  0.0             [EXACTLY zero: no context row exists at all]
nominal_oc                      = Nathan Scheelhaase  [metadata only — does NOT set pc_changed]
McVay's caller identity unifies WAS-as-OC and LA-as-HC games under ONE person
```
The nominal-OC change is correctly ignored. McVay has no row in the HC-context block, so his effect
appears exactly once.

**Kansas City, 2026** ✅
```
expected_caller_id = andy_reid   expected_hc_id = andy_reid   caller_is_head_coach = 1.0
caller_adjusted_offense_effect = +0.038287
noncalling_hc_context_effect   = 0.0   [EXACTLY zero by routing: he calls his own plays]
```
Reid DOES carry a context coefficient (his 5 verified delegated games to Matt Nagy, KC 2017); the
self-calling routing rule is what suppresses it.

**Unknown caller** ✅ every caller-dependent feature takes the frozen league-prior VALUE, both Arm 3
effects are 0, no subjective penalty and no bonus. **Known caller with no prior history** ✅ the same
prior values, but a DIFFERENT diagnostic state — he is identified.

---

## §9. POST-VERDICT INTERPRETATION

Report which representation — if any — was repeatedly selected: **head-coach résumé alone (ARM_HC)** /
HC résumé + offensive ranks / continuous efficiency / personnel-adjusted effect / scheme-allocation /
adjusted quality plus scheme / **or no coaching information at all**.

**Only if a position passes**, run a 2026 counterfactual audit comparing actual staff assignment;
same roster and all non-coaching features; and a league-average no-history play-caller. Report
team-level and position-level movement for the Chargers and Rams. **Diagnostic only** — not
validation, not authorization to change the website.

**Never manually force McDaniel or McVay upward.** If their calculated priors are not positive after
the frozen definitions and controls, say so plainly.

---

## §10. FENCES

- This experiment **writes no production artifact**.
- A pass makes a position a **developmental candidate only**.
- "Beating Sleeper" is not a bar and is not evaluated here.
- The shrinkage constant, rolling window, league priors, cohort definitions, eligibility margins
  (0.25 / 1% / 3%), bootstrap seed, coverage gates and pass rule are frozen by this document.
  Changing any of them after seeing a result requires a written amendment stating what was known at
  the time.
