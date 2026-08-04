# v3.9 PREFIT STOP REPORT — coaching features + nested evaluation harness

**Date:** 2026-07-29 (revised twice the same day: an independent review — §0.1 — then a final
correctness patch — §0.2)
**Governing prereg:** `fantasy/projections/preregs/PREREG_coach_quality_2026-07-28.md`, revision
**v3.9b PREFIT**.
**Scope of this pass:** build and audit the complete coaching-feature layer and the nested
player-evaluation harness. Stop before the first real fantasy-outcome fit.

---

## 0.1 WHAT THE REVIEW FOUND, AND WHAT CHANGED

An independent review confirmed the 18 protected hashes, the five artifact hashes, Design A coverage
152/256 = 124 + 28 + 104, the lineage row counts with no timing violation, and 52 passing harness
tests — and then found seven defects. All seven are repaired.

| # | finding | status |
|---|---|---|
| 1 | The build was **not hermetic**: `projection_cutoffs()` and `hc_game_results()` both downloaded nflverse schedules, and the win ledger sat in an untracked scratch cache. A clean offline checkout failed **five** feature tests, so the then-current 254-pass claim (SUPERSEDED; the suite is now 1,275 collected) depended on state outside the repo. | **FIXED** — both read the repo-owned frozen snapshot; the ledger is computed in memory; suite and build now pass with egress blocked and an empty temp dir (§1.4) |
| 2 | The live canonical prereg sections still asserted the superseded policy **underneath** the correction banner, and this report claimed they had been corrected when only a banner covered them. | **FIXED** — §0, §2, §3.2, §4, §5, §6, §7, §8-T5, §8.1 rewritten to v3.9 truth; the false claim in this report is withdrawn (§2.1) |
| 3 | The manifest pinned only appended coaching columns; `ARM_0` was empty and the veteran/rookie baseline difference was inexpressible. | **FIXED** — full ordered X per (position, bucket, arm) (§4.1) |
| 4 | The ten-condition §7 primary verdict was **never computed**, its thresholds were not pinned, and no test covered it. | **FIXED** — `primary_verdict()` + 14 tests (§8.5) |
| 5 | The placebo scored a **modal fixed arm**, not the nested-selected pipeline. | **FIXED** — every draw reruns selection per outer fold (§8.6) |
| 6 | Lineage claimed to prove source membership but carried only aggregate counts. | **FIXED** — `caller_contribution` records + reconciliation tests (§6.2) |
| 7 | The extra historical-evidence gate was introduced silently, and `test_design_a_and_b_differ_only_on_identity_supply` overclaimed. | **SURFACED for ratification (§7) + test renamed** |

---

## 0. THE BOUNDARY — explicit statement

**No real fantasy outcome was loaded, joined, scored, inspected, summarized, or fit at any point in
this pass. No real player-model run was performed. No outer-fold result on a real label exists.**

What was done instead:

- production training/scoring **source code** and stored **bundle metadata** were read (read-only) to
  recover the exact Arm 0 architecture;
- every model fit executed in this pass ran against **programmatically generated synthetic targets**
  inside tests and one synthetic smoke run;
- the real-fit path is **default-closed and double-locked** (§8).

`build_arm_features_v39.py` never names the player panel in executable code. Enforced by AST-based
tests that strip docstrings first, so *documenting* the boundary is not mistaken for crossing it:
`test_no_v39_module_ever_CALLS_a_real_outcome_source`,
`test_no_real_outcome_token_is_used_as_a_FILE_READ_OR_COLUMN_ACCESS`,
`test_feature_construction_never_touches_a_fantasy_outcome`.

**STOPPED BEFORE REAL FANTASY OUTCOMES / FIRST REAL PLAYER-MODEL RUN — JOSEPH REVIEW REQUIRED.**

---

## 0.2 v3.9b — FINAL PREFIT CORRECTNESS PATCH

Four items. Three are **independently repaired defects**; one is an **adopted policy** with a
mandatory arithmetic retraction.

| # | item | kind | where |
|---|---|---|---|
| 1 | C3/C4/C8 checked improvement COUNTS without requiring the frozen denominators, so a truncated six-season run satisfied "6 of 8". The v3.9a report's unresolved item 11 asserted a guarantee the code did not provide. | **defect repaired** | §8.7 |
| 2 | Condition 10 was documented as "every timing, leakage, coverage, artifact-integrity and no-real-outcome assertion" but checked only production hashes, ten upstream hashes and the lock state. | **defect repaired** | §8.8 |
| 3 | `_integrity_check()` treated an unlocked real-fit gate as a failure, so **every authorized real run would have failed C10** and `DEVELOPMENTAL CANDIDATE` was unreachable forever. | **defect repaired** | §8.9 |
| 4 | The historical source-date gate is **retired**; primary history is now strictly-prior over the full retrospective ledger. Two figures in the v3.9a report are **RETRACTED**. | **policy adopted + retraction** | §7 |

**The headline correction:** v3.9a claimed retiring the gate could add "~76 more usable rows" toward
Design B's "200/256 ceiling". Both figures are wrong — Design A has only 152/256 known identities, so
the ceiling is 152 and the arithmetic maximum is 28. **Computed, the realised gain is ZERO rows**; the
effect is +358 caller-games of history depth, and 2019 gains nothing. Full detail and the reason in §7.

---

## 0.3 v3.9c — REVIEW REPAIRS

Five defects found by independent review of v3.9b. **All are repaired defects — no policy changed, and
every v3.9b conclusion was independently reproduced** (152 known / 124 with history / +0 rows / +358
games; the per-season gains; all 51 features identical on all 227 matched rows; 2016 DET the one row
anywhere that gains history).

| # | defect | proof it is fixed |
|---|---|---|
| 1 | `coverage_reconciles` inspected only `ARM_1 / all` and two columns, so corrupting `ARM_2 / known_with_history / n_team_seasons` → 999 left it **True**. Only the hash caught it, so a rebuild + repin could have shipped a semantically false artifact with C10 green. | the exact case now returns `coverage_reconciles = False` and names the cell (§10.1) |
| 2 | `preflight()` read artifacts outside the guarded wrapper, so deleting the Design A table **raised** `FileNotFoundError` instead of returning the structured record. | the exact case now returns `all_ok = False` with 5 dependents marked `blocked by design_a` (§10.1) |
| 3 | The generated lineage artifact still asserted the RETIRED source-date gate as the primary `timing_rule` on every caller-history/continuity row, contradicting the values it documented. An MD5 cannot see that. | all such rows now carry `PRIMARY_TIMING_RULE`; `validate_lineage_policy()` is a preflight check |
| 4 | Live requirement-matrix F-14 and audit item 32 still asserted the superseded policy, `~76`, `200/256` and the two-axis contrast. | F-14 withdrawn → F-14a/b/c; item 32 re-headed RESOLVED; a mechanical scan over 9 live targets reports **CLEAN** |
| 5 | C10 claimed the no-real-outcome assertions but implemented them only as tests. | `no_real_outcome_access()` is now module logic AND a preflight check; tests call it |

**Preflight: 17 → 20 → 21 checks** (v3.9c added `v39_artifacts_readable`, `lineage_states_the_primary_policy`,
`no_real_outcome_access`).

---

## 1. OPENING VERIFICATION

### 1.1 Inherited test baseline: **141**, reproduced exactly

This is the ONE canonical baseline command and the ONE canonical result. Ignore the two v3.9 test
modules, deselect the six v3.9 additions to `test_artifact_ownership.py`, and the inherited suite
reproduces:

Run from the repository root
(`C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics`), using the **repo-local**
interpreter `.\.venv-test\Scripts\python.exe` (Python 3.11.9). This is one line, fully expanded — no
`...` placeholders, no abbreviations:

```
.\.venv-test\Scripts\python.exe -m pytest fantasy/projections/coaching/tests -q -p no:warnings --ignore=fantasy/projections/coaching/tests/test_arm_features_v39.py --ignore=fantasy/projections/coaching/tests/test_coach_projection_harness_v39.py --ignore=fantasy/projections/coaching/tests/test_boundary_corpus.py --ignore=fantasy/projections/coaching/tests/test_assemble_real_panel_v39.py --ignore=fantasy/projections/coaching/tests/test_combine_snapshot_provenance.py --ignore=fantasy/projections/coaching/tests/test_rookie_matrix_v39.py --ignore=fantasy/projections/coaching/tests/test_pff_point_in_time_v39.py --ignore=fantasy/projections/coaching/tests/test_arm0_refits_from_scratch_v39.py --ignore=fantasy/projections/coaching/tests/test_activation_wiring_v39.py --ignore=fantasy/projections/coaching/tests/test_veteran_snapshot_v39.py --ignore=fantasy/projections/coaching/tests/test_authorized_runner_v39.py --ignore=fantasy/projections/coaching/tests/test_composed_feature_reader_v39.py --ignore=fantasy/projections/coaching/tests/test_evaluation_eligibility_v39.py --ignore=fantasy/projections/coaching/tests/test_authorization_capability_v39.py --ignore=fantasy/projections/coaching/tests/test_two_phase_preflight_v39.py --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_each_protected_text_artifact_has_exactly_one_writer --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_build_arm_features_v39_writes_only_the_five_authorized_artifacts --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_the_harness_writes_no_repo_artifact_at_all --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_no_unauthorized_v39_artifact_exists_on_disk --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_the_head_coach_win_ledger_is_derived_in_memory_not_cached --deselect fantasy/projections/coaching/tests/test_artifact_ownership.py::test_the_v39_modules_never_write_outside_the_coaching_data_dir
```

Literal output of that exact command:

```
........................................................................ [ 51%]
.....................................................................    [100%]
141 passed, 6 deselected in 14.74s
```

**Interpreter note, corrected.** An earlier revision of this section printed
`..\AI_hedge_fund\.venv\Scripts\python.exe` and claimed bare `python` resolves to it through
`VIRTUAL_ENV`. That is **WITHDRAWN**: that venv's `pyvenv.cfg` points at a Microsoft-Store
`WindowsApps` Python, which is not reliably executable, so the command was not reproducible outside one
particular shell. The repo-local `.venv-test` is the interpreter used for every number in this report,
and no claim is made here about what bare `python` resolves to.

Every ID above is real and was executed. `pytest --deselect` silently ignores an ID that does not
exist, so a mistyped path deselects nothing and returns 147 with no error — copy these verbatim.

**Current totals, and the only ones stated anywhere in this document:** **1,275** tests in
`coaching/tests/` — **141** inherited plus **1,134** added by this pass. The 1,134 is
88 (`test_arm_features_v39.py`) + 246 (`test_coach_projection_harness_v39.py`) + 166 (`test_boundary_corpus.py`) + 205 (`test_assemble_real_panel_v39.py`) + 9 (`test_combine_snapshot_provenance.py`) + 91 (`test_rookie_matrix_v39.py`) + 37 (`test_pff_point_in_time_v39.py`) + 38 (`test_arm0_refits_from_scratch_v39.py`) + 31 (`test_activation_wiring_v39.py`) + 45 (`test_veteran_snapshot_v39.py`) + 49 (`test_authorized_runner_v39.py`) + 47 (`test_composed_feature_reader_v39.py`) + 28 (`test_evaluation_eligibility_v39.py`) + 48 (`test_authorization_capability_v39.py`) + 6 (the v3.9 additions
to `test_artifact_ownership.py`). The per-module table in §10 carries the full split and reconciles to
the same 1,275. **SUPERSEDED:** an earlier draft quoted a suite total 254 and 113 new tests (both
**SUPERSEDED**); a later one quoted 836 total / 695 added (also **SUPERSEDED**). Only the counts above
are current, and they were collected, not estimated.

Interpreter for every number in this report: the repo-local `.\.venv-test\Scripts\python.exe`
(Python 3.11.9).

### 1.2 Protected artifacts: **18/18 byte-identical**, opening AND closing

| artifact | required md5 | opening | closing |
|---|---|---|---|
| `coaching/data/actual_play_caller.csv` | `98f1c66b7387c16bba6a5463f4e0fa06` | OK | OK |
| `coaching/data/arm3_stage1_residuals_v38.csv` | `f4ac3bee6ae208bb1aca6bdedadc9224` | OK | OK |
| `coaching/data/arm3_stage1_tuning_v38.csv` | `65720dca75a0c6a5b2b1e732f0a86e57` | OK | OK |
| `coaching/data/arm3_stage1_fold_losses_v38.csv` | `bc57b3e4d17e6d5bdbfdaa3dc8237c43` | OK | OK |
| `coaching/data/arm3_stage1_feature_schemas_v38.json` | `d0a5f34af073a2a330f13c4c8d002555` | OK | OK |
| `coaching/data/arm3_stage2_effects_v38.csv` | `4286cbd542854e23a6042bcec1b4b8ed` | OK | OK |
| `coaching/data/arm3_stage2_tuning_v38.csv` | `28873246729b558593a29956b3a14de1` | OK | OK |
| `coaching/data/arm3_stage2_fold_losses_v38.csv` | `3c73e25c1bf4fc592ab3b2d5211a44c5` | OK | OK |
| `coaching/data/arm3_residuals.csv` (preliminary) | `2ba6c51769f8dbb85c27c603b2dc93f2` | OK | OK |
| `coaching/data/arm3_effects.csv` (preliminary) | `56b47dab2c0e27689ee260deb9e29c4b` | OK | OK |
| `projections/models/qb_veteran_model.pkl` | `7632549f95995b9702baefdf016d7271` | OK | OK |
| `projections/models/rb_rookie_model.pkl` | `da230ee66575ca574f02cbc2139e1a80` | OK | OK |
| `projections/models/rb_veteran_model.pkl` | `167aca71a8511afcced37c0abc846004` | OK | OK |
| `projections/models/te_rookie_model.pkl` | `f79dad0ab26af5cb4e06a9f1723328cd` | OK | OK |
| `projections/models/te_veteran_model.pkl` | `5a2f0b504d4cc6fc9a2e04453fd76a44` | OK | OK |
| `projections/models/wr_rookie_model.pkl` | `6c9a3f3ed02ce32c53594f383aade882` | OK | OK |
| `projections/models/wr_veteran_model.pkl` | `17dfbcf01054bdd5ce032f2b55df9ad2` | OK | OK |
| `seasonal_projections/models/rookie_ppg_model.pkl` | `872467b2295fce27761f9e04da01b6e8` | OK | OK |

`projections/results/` is untouched (newest file 2026-07-27, predating this session). No parquet, no
licensed PFF row, and no real-outcome result was written anywhere.

### 1.4 HERMETIC: the suite and the build run offline with an empty temp directory

The single deterministic source for historical REG schedules, scores, coaches and season-opening dates
is now the repository-owned frozen snapshot:

```
fantasy/seasonal_projections/snapshots/schedules_1999_2025.parquet
provenance (snapshots/manifest.json): loader load_schedules, nflreadpy 0.1.5,
7,276 rows x 46 cols, fetched 2026-07-10T01:17:13Z, sha256 78ff21f9530ad3e4...
```

- **Cutoffs** = day before season Y's first REG gameday, derived from the snapshot; season 2026 keeps
  the frozen production as-of date **2026-07-21**. Derived values are cross-checked against the
  `projection_cutoff` column already persisted in `preseason_staff_snapshot.csv` — **all 13 match**, so
  the hermetic derivation cannot disagree with the artifact the eligibility gate was built with.
- **Head-coach win ledger** is computed **in memory** (6,967 REG games → 13,934 team-rows), identical to
  the values the live loader produced. No sixth artifact, no scratch cache; `SCRATCH` and `tempfile` are
  gone from the module.

Verified with egress blocked (`socket.create_connection`, `getaddrinfo`, `socket.connect`,
`connect_ex`) **and** every nflverse loader replaced by a raising stub, **and** `TEMP`/`TMP` pointed at
a freshly created empty directory:

```
full coaching suite   1,316 collected; 1,316 passed.
                      + 1 optional git cross-check (passes or skips; see below)
inherited baseline    141 passed, 6 deselected
full v3.9 build       completed; all five artifact hashes reproduced
```

**THE CANONICAL COUNT STATEMENT.** One environment-dependent test makes a bare "N passed" line
ambiguous, so this is the only form this document uses:

| | |
|---|---|
| canonical collection total | **1316** |
| mandatory tests | **1315 passed** |
| **measured on 2026-08-04, after §10.15** | **1,316 passed · 0 failed** |
| optional git cross-check | **passes when the historical blob `85c438f7d908e9df7da8d5e44ad8e30d3bbeeffe` is reachable, otherwise skips** |
| the vendored historical red proof | **runs in BOTH states — it is never skipped** |

So a green run legitimately reports either `1316 passed` or `1315 passed, 1 skipped`, and the two are the
same result. The variation is only whether `git cat-file -p <blob>` can reach the pinned blob: after the
`BettingEdgeContinued` → `JoSchoAnalytics` rename the repository is owned by another account, so git
refuses without `-c safe.directory=...` and the cross-check skips; in a review environment where the
blob is reachable it passes. **Neither state affects the red proof**, which loads the sha256-pinned
vendored fixture `tests/fixtures/historical_validator_a5b4af7.pysrc` and needs no git at all — that was
the whole point of vendoring it (§10.3, "the historical proof fails closed").

`test_no_document_states_an_incompatible_unconditional_suite_count` fails if any live document goes back
to an unconditional bare pass count.

Covering tests: `test_cutoffs_and_hc_history_build_with_NETWORK_BLOCKED`,
`test_a_full_feature_build_runs_with_NETWORK_BLOCKED`,
`test_no_v39_module_calls_a_live_nflverse_loader`,
`test_snapshot_derived_cutoffs_match_the_persisted_artifact`,
`test_the_builder_writes_no_cache_outside_the_five_artifacts`.

### 1.3 One mtime caveat, stated rather than glossed

`actual_play_caller.csv` and `source_ledger.csv` have an mtime inside every test run, because the
**pre-existing** registered test `test_coaching_phase1c.py::test_rebuild_is_byte_identical` rebuilds
them on purpose and asserts byte-identity. Their bytes are unchanged. **An mtime is not a change.**

---

## 2. v3.9 AMENDMENT SUMMARY

Written to the prereg **before** any feature was assembled. Full text in the prereg's
`Amendment record (v3.8 -> v3.9)`.

1. **Forbidden primary player features.** No observed reliability, raw/log history counts,
   `no_prior_history`, censoring fields, or observable-window fields may enter player-model X.
   Reliability survives only as the deterministic shrinkage weight *inside* a historical estimate.
   Arm 3 ridge effects get **no second shrinkage**. Tenure and entering-change stay eligible.
2. **`ARM_HC` added** → the primary comparison is seven representations; Holm covers the **six**
   nonbaseline alternatives per position.
3. **Expanding forward-chaining** replaces leave-one-season-out for representation selection.
4. **Design A is the sole primary design**; Design B is oracle/nondeployable; Design C unimplemented.
5. **Frozen neutral encoding** (a VALUE, never NaN) with its cost disclosed.
6. **Arm 3 is structurally unavailable before target 2018**, stated up front.
7. **Exactly five new repo data artifacts**; naming `ARM_0…ARM_5`; retired drive names rejected.
8. **Two production architectures exist in this repo** and the audit claims are scoped to the one
   Arm 0 uses.

### 2.1 Corrected live prereg sections — the earlier claim here is WITHDRAWN

The previous version of this report presented the table below as "corrected live sections". That was
**wrong**: §0, §2, §3.2, §4, §5, §6, §7, §8-T5 and §8.1 were only covered by a supersession banner and
still stated the old policy as executable canon underneath it. They are now **rewritten in place**.

Verified mechanically: a scan of everything from `## §0` onward for
`prior_points_per_drive | off_points_per_game | points_per_drive | SIX FROZEN | leave-one-season-out |
Arms 0–5 | Arms 1–5 | pc_reliability | hc_reliability | *_prior_games_log | season fixed effect |
adjusted_effect_reliability | pc_adjusted_offense_effect | pc_changed =` now returns only the two
lines that **assert the corrections** ("There is **no season fixed effect**",
"**Leave-one-season-out is withdrawn**"). Amendment history above §0 legitimately retains old wording.

What the live sections now say: seven representations `ARM_0 / ARM_HC / ARM_1…ARM_5`; §4.0 as a binding
player-feature policy (no reliability, counts, log counts, `no_prior_history`, censoring or
observable-window fields in X); current Arm 3 role semantics and field names with **no** season fixed
effect and **no** reliability multiplication of fitted ridge effects; canonical drive-proxy names only;
expanding forward chaining only, with LOSO explicitly withdrawn and the reason given; Holm across the
**six** nonbaseline alternatives; §6.1 freezing the pooled improvement statistic; the full unchanged
ten-condition §7 pass rule; §8.1 restated from the emitted features.

### 2.2 Original v3.9 section-correction table

| location | was | now |
|---|---|---|
| header revision | v3.8 | **v3.9**, superseding v1–v3.8 |
| FITTING STATUS | "no arm 0-5 fit" | explicit: no arm **or ARM_HC** fit, no outcome read, harness synthetic-only, `REAL_FIT_AUTHORIZED = False` |
| §4 "THE SIX FROZEN ARMS" | six arms; Arm 1/2/5 lists append `*_prior_games_log`, `*_reliability`, `*_no_prior_history` | banner: **SEVEN** arms, manifest is authoritative, those columns **WITHDRAWN** as features; body relabelled superseded history |
| §5 nested selection | "leave-one-season-out inner validation" | banner: **EXPANDING** forward chaining (LOSO would train a fold on seasons after its validation season); arm set + Holm family corrected |
| §8.1 / v3.4 companion hashes | `preseason_staff_snapshot.csv e91b45b8…`, `preseason_evidence_ledger.csv c6ff0f5b…` | **stale v3.4 pins**, superseded by v3.5–v3.7; corrected to `6295c011…` / `e1cb0d62…` in v3.9 §10 |
| Arm 3 role semantics | v3.2 HC/PC collapse | caller-first collapse + v3.6 neutral unknown rule, restated in the v3.9 routing table |
| reliability × ridge effect | permitted in earlier arm lists | **forbidden**; "NONE — ridge already pooled" recorded in the lineage artifact |
| McVay history counts | "2018, 2020-2025 = 7 seasons / 117 games" (§8.1) | superseded; the live figure is the caller-block 181 games through 2025 (v3.6), and the v3.9 builder recomputes it from segments |
| unknown vs known-no-history | conflated in places | three explicit `identity_state` values in the coverage artifact |

Superseded statements are retained inside labelled amendment-history blocks, never as live policy.

### 2.2 Ambiguity I had to resolve, disclosed rather than tuned

The prereg fixes league priors for rank percentiles (0.500) and z-scores (0.000) but **does not
specify a neutral value for the two binary caller indicators** (`pc_changed_entering`,
`caller_is_head_coach`) when no caller identity exists. Every option is imperfect:

- `0` asserts the head coach delegated — no evidence;
- `1` asserts he called his own plays — no evidence;
- `NaN` reopens a missingness channel that, under Design A, is close to a season indicator
  (0% caller coverage in 2017; ~100% in 2018/2023/2024).

**Frozen choice: 0.5** — "assume neither", the literal v3.6 neutral rule. It is a distinguishable
third level and it *is* season-correlated; that is why the within-season team-level permutation
placebo is the pre-registered control. Chosen on principle before any outcome was visible and
**never tuned against a result**. Caller tenure takes the frozen neutral **0.0**, which is
deliberately *not* a distinguishable level (a genuine first-year caller receives the same value).

---

## 3. EXACT FEATURE DEFINITIONS

Grain: one row per (design, target season, team), target seasons **2014–2026**, 416 rows per design,
**51** model features + 10 diagnostic-only columns.

Shrinkage everywhere: `r = g/(g+32)`, `shrunk = r*value + (1-r)*prior`, `g` = **`pbp_games`** (games
observed in play-by-play inside the sourced week range; equal to the canonical `n_games_attributed`
on every played segment, asserted at load). Per-metric games are counted **only where that metric is
non-null**. Windows: `career` (all eligible prior) and `roll3` (prior 3 seasons).

### ARM_HC — head-coach résumé and continuity
Regular season only, no playoffs, **tie = 0.5 win** and stays in the denominator; scheduled-but-
unplayed games are dropped, never scored 0.

- `hc_career_win_pct_shrunk`, `hc_roll3_win_pct_shrunk` — wins/games, shrunk to prior 0.500
- `hc_tenure_current_team` — consecutive completed prior seasons opening for this team (relocations
  folded onto one code, so tenure bridges STL→LA / SD→LAC / OAK→LV)
- `hc_changed_entering` — week-1 HC of Y vs final-week HC of Y−1

### ARM_1 — ARM_HC + caller résumé
Adds `pc_career_off_rank_pct`, `pc_roll3_off_rank_pct`, `pc_tenure_current_team`,
`pc_changed_entering`, `caller_is_head_coach`.
Rank composite = equal-weight mean of available within-season rank percentiles
`1-(r-1)/(n-1)` for **drive-scoring points/game proxy, yards/play, EPA/play, success rate,
drive-scoring points/drive proxy**, requiring **≥3 of 5**, placed against the **full team-season**
reference distribution so a partial segment sits on the same scale.

### ARM_2 — continuous caller efficiency (caller-only; ARM_HC is NOT folded in)
Career + roll3 z-scores, kept as separate dimensions, for EPA/play, success rate,
**drive-scoring points/drive proxy**, yards/play, explosive rate, red-zone TD rate; plus the three
caller-continuity features. 15 total.

### ARM_3 — personnel-adjusted effects
`caller_adjusted_offense_effect`, `noncalling_hc_context_effect`, `caller_is_head_coach`, read
directly from `arm3_stage2_effects_v38.csv` at the target season. **No reliability multiplication, no
exposure counts.** Routing:

| situation | caller effect | HC-context effect |
|---|---|---|
| unknown caller | 0 | 0 |
| self-calling head coach | fitted caller effect | **exactly 0**, never duplicated |
| distinct known caller | fitted caller effect | that HC's fitted context effect |
| identity absent from the target-season table | 0 (league prior) | 0 (league prior) |

### ARM_4 — scheme / allocation, position-specific
Career + roll3 of caller tendencies from segment PBP.
`pc_career_rush_tendency_z` is the **exact negation** of `pc_pass_tendency_z`: within a source season
`z(1−neutral pass rate) = −z(neutral pass rate)`, and negation commutes with shrinkage toward 0. It is
emitted so the RB block reads in rushing terms; the identity is asserted by test.

### ARM_5 — adjusted quality + scheme
`hc_tenure_current_team`, `hc_changed_entering`, `pc_tenure_current_team`, `pc_changed_entering`,
`caller_is_head_coach`, the two Arm 3 effects, and the position-specific Arm 4 block.
**Excludes** Arm 1 win/rank, Arm 2 efficiency, and all reliability/count/censoring metadata — asserted
in `manifest()`, not merely documented.

---

## 4. ORDERED MANIFESTS BY POSITION AND ARM

Authoritative source: `data/arm_feature_manifest_v39.json`. Arm 0 carries **no** coaching feature; its
baseline is the production bundle's `feature_cols` (§7).

| arm | QB | RB | WR | TE |
|---|---|---|---|---|
| ARM_0 | 0 | 0 | 0 | 0 |
| ARM_HC | 4 | 4 | 4 | 4 |
| ARM_1 | 9 | 9 | 9 | 9 |
| ARM_2 | 15 | 15 | 15 | 15 |
| ARM_3 | 3 | 3 | 3 | 3 |
| ARM_4 | 10 | 10 | 10 | **8** |
| ARM_5 | 17 | 17 | 17 | **15** |

**ARM_HC** (all positions), in order:
`hc_career_win_pct_shrunk, hc_roll3_win_pct_shrunk, hc_tenure_current_team, hc_changed_entering`

**ARM_1** (all positions): ARM_HC then
`pc_career_off_rank_pct, pc_roll3_off_rank_pct, pc_tenure_current_team, pc_changed_entering, caller_is_head_coach`

**ARM_2** (all positions):
`pc_career_epa_play_z, pc_roll3_epa_play_z, pc_career_success_rate_z, pc_roll3_success_rate_z, pc_career_drive_scoring_points_per_drive_proxy_z, pc_roll3_drive_scoring_points_per_drive_proxy_z, pc_career_yards_play_z, pc_roll3_yards_play_z, pc_career_explosive_rate_z, pc_roll3_explosive_rate_z, pc_career_redzone_td_rate_z, pc_roll3_redzone_td_rate_z, pc_tenure_current_team, pc_changed_entering, caller_is_head_coach`

**ARM_3** (all positions):
`caller_adjusted_offense_effect, noncalling_hc_context_effect, caller_is_head_coach`

**ARM_4**, career/roll3 pairs in this order:

| position | base tendencies |
|---|---|
| QB | `plays_per_game_z, pass_tendency_z, pace_z, redzone_pass_rate_z, qb_carry_share_z` |
| RB | `plays_per_game_z, rush_tendency_z, rb_carry_share_z, rb_target_share_z, rz_rb_share_z` |
| WR | `plays_per_game_z, pass_tendency_z, wr_target_share_z, team_adot_z, rz_wr_share_z` |
| TE | `plays_per_game_z, pass_tendency_z, te_target_share_z, rz_te_share_z` |

**ARM_5** = `hc_tenure_current_team, hc_changed_entering, pc_tenure_current_team,
pc_changed_entering, caller_is_head_coach, caller_adjusted_offense_effect,
noncalling_hc_context_effect` + that position's ARM_4 block.

**Diagnostic-only columns** (emitted for audit, absent from every arm):
`expected_caller_id, expected_hc_id, caller_identity_known, caller_history_games_career,
caller_history_games_roll3, hc_resume_games_career, caller_history_segments_career,
caller_first_source_season, caller_last_source_season, arm3_effects_available`.

### 4.1 FULL ORDERED PLAYER X — now pinned in the manifest

The manifest previously stored only the appended coaching columns, so `ARM_0` was an empty list, the
production baseline order lived only in Python/bundle metadata, and the veteran/rookie baseline
difference could not be represented. It now additionally pins:

- `arm0_baseline_features` — exact ordered baseline per `(position, bucket)`, read from the bundles;
- `missing_production_paths` — `QB/rookie` is explicitly `null` with the reason (the arm was HELD);
- `full_model_x` — exact ordered **complete** X per `(position, bucket, arm)` = baseline in shipped
  order, verbatim, followed by that arm's ordered coaching additions;
- `full_model_x_counts`, and the coaching additions separately in `by_position`.

Column counts of the complete matrix:

| (position, bucket) | baseline | ARM_0 | ARM_HC | ARM_1 | ARM_2 | ARM_3 | ARM_4 | ARM_5 |
|---|---|---|---|---|---|---|---|---|
| QB/veteran | 32 | 32 | 36 | 41 | 47 | 35 | 42 | 49 |
| QB/rookie | — | **path does not exist** | | | | | | |
| RB/veteran | 32 | 32 | 36 | 41 | 47 | 35 | 42 | 49 |
| RB/rookie | 41 | 41 | 45 | 50 | 56 | 44 | 51 | 58 |
| WR/veteran | 32 | 32 | 36 | 41 | 47 | 35 | 42 | 49 |
| WR/rookie | 44 | 44 | 48 | 53 | 59 | 47 | 54 | 61 |
| TE/veteran | 32 | 32 | 36 | 41 | 47 | 35 | 40 | 47 |
| TE/rookie | 44 | 44 | 48 | 53 | 59 | 47 | 52 | 59 |

`manifest()` asserts, for every cell: the baseline occupies the front of X verbatim, the tail is exactly
the arm's ordered additions, there are no duplicate columns, and no forbidden metadata appears.
`test_manifest_full_model_x_is_exactly_what_reaches_fit` then proves the manifest's list is the column
list the harness hands to the production fitter, including the resulting matrix width.

---

## 5. FEATURE COVERAGE BY SEASON, AND DESIGN A vs DESIGN B

`arm_feature_coverage_v39.csv` is at (design, arm, season, `identity_state`) grain with
`identity_state ∈ {all, known_with_history, known_no_history, unknown}`. **Filter
`identity_state == "all"` before summing** or every season double-counts.

### Design A (PRIMARY, point-in-time, deployable)

| season | teams | caller known | known WITH history | known NO history | unknown | mean prior caller games | Arm 3 available |
|---|---|---|---|---|---|---|---|
| 2014 | 32 | 5 | 0 | 5 | 27 | 0.000 | no |
| 2015 | 32 | 3 | 3 | 0 | 29 | 1.500 | no |
| 2016 | 32 | 11 | 9 | 2 | 21 | 6.375 | no |
| 2017 | 32 | **0** | 0 | 0 | 32 | 0.000 | no |
| 2018 | 32 | 31 | 25 | 6 | 1 | 28.594 | yes |
| 2019 | 32 | 7 | **3** | 4 | 25 | 2.469 | yes |
| 2020 | 32 | 6 | **4** | 2 | 26 | 6.406 | yes |
| 2021 | 32 | 7 | **7** | 0 | 25 | 9.000 | yes |
| 2022 | 32 | 6 | **6** | 0 | 26 | 16.031 | yes |
| 2023 | 32 | 32 | 26 | 6 | 0 | 50.219 | yes |
| 2024 | 32 | 32 | 26 | 6 | 0 | 51.438 | yes |
| 2025 | 32 | 31 | 27 | 4 | 1 | 63.156 | yes |
| 2026 | 32 | 32 | 27 | 5 | 0 | 73.312 | yes |

**Outer 2018–2025 Design A caller coverage = 152/256.** Computed, not assumed — it matches the
pre-registered figure exactly. Decomposition: **124** identified-with-history, **28**
identified-with-no-history, **104** unknown.

### Design B (ORACLE — NONDEPLOYABLE)

**Outer 2018–2025 = 244/256** (200 with history, 44 no-history, 12 unknown), i.e. the retrospective
attribution rate. Every B field and row carries
`ORACLE IDENTITY — uses information unavailable at the projection cutoff. NOT achievable in
deployment. NOT evidence of real preseason performance.`

### The number that actually bounds the caller channel

Identified callers **with any eligible prior history**, out of 32:
**25 / 3 / 4 / 7 / 6 / 26 / 26 / 27** for 2018–2025. In 2019–2022 the caller channel is nearly empty.
**A null caller arm on this panel is jointly a statement about coaching signal and about archive
retrievability, and cannot separate them.** Design B exists to bound the second.

---

## 6. LAC / RAMS / KC ROUTING — computed values

All from `team_coach_features_design_a_v39.csv`, season 2026. Every assertion passes.

| | LAC | LA (Rams) | KC |
|---|---|---|---|
| expected caller | `mike_mcdaniel` | `sean_mcvay` | `andy_reid` |
| previous caller (Y−1 closing) | `greg_roman` | `sean_mcvay` | `andy_reid` |
| expected HC | `jim_harbaugh` | `sean_mcvay` | `andy_reid` |
| `pc_changed_entering` | **1.0** | 0.0 | 0.0 |
| `caller_is_head_coach` | 0.0 | 1.0 | 1.0 |
| `caller_adjusted_offense_effect` | **+0.005262** | **+0.025936** | **+0.038287** |
| `noncalling_hc_context_effect` | **2.368030e-18** (numerical zero) | **0.0** (exact) | **0.0** (exact) |
| `hc_career_win_pct_shrunk` | 0.634615 | 0.596685 | 0.630064 |
| `hc_tenure_current_team` | 2.0 | 9.0 | 13.0 |
| `pc_tenure_current_team` | 0.0 | 9.0 | 12.0 |
| `pc_career_off_rank_pct` | 0.564812 | 0.667400 | 0.728739 |

**Three different kinds of zero, deliberately not conflated:**

- **LAC** — Harbaugh *is* a distinct non-calling head coach, so his context coefficient legitimately
  applies; that coefficient is **numerically** zero (2.37e-18) because entering 2026
  `alpha_hc_context` sat at the extended 1e16 upper boundary (effective complete pooling). The feature
  carries the **fitted value** and is *not* forced to 0.
- **LA** — McVay has **no context row at all** in the effect table, so the effect appears exactly once
  and the context feature is exactly 0. Asserted directly against the effect table.
- **KC** — Reid *does* have a context coefficient (his 5 verified delegated games to Matt Nagy, KC
  2017); self-calling routing suppresses it, so the feature is exactly 0.

**No forced positive upgrade.** McDaniel `+0.005262` is **0.002219 EPA/play BELOW** Roman
`+0.007482`. Arm 3 supplies **no** basis for describing the Chargers as a play-calling upgrade, and
nothing in the v3.9 code, artifacts, or tests asserts one — `test_arm3_does_not_support_a_chargers_upgrade`
pins the sign and the magnitude.

---

## 6.2 LINEAGE NOW PROVES MEMBERSHIP, NOT JUST TOTALS

The previous report said lineage proved source-segment/game membership. It did not — routing rows
carried only aggregate counts and first/last source seasons. `arm_feature_lineage_v39.csv` now has a
third `record_kind`:

| record_kind | rows | what it establishes |
|---|---|---|
| `feature_definition` | 51 | per emitted feature: source artifact/column, window, aggregation, weight, shrinkage, prior, neutral value, timing rule |
| `identity_routing` | 832 | per (design × target season × team): the identity decision, totals, first/last source season, `strict_timing_ok`, league-prior fallback with reason |
| `caller_contribution` | **1,631** | per CANDIDATE historical segment behind each caller aggregate — **included or excluded** |

Breakdown: Design A **618** included in the career aggregate and **35** excluded by the evidence gate;
Design B **978** included (it gates nothing). Total lineage artifact = **2,514** rows.

Each contribution row carries: `design`, target `season`/`team`, `expected_caller_id`,
`source_season`, `source_team`, `source_week_start`, `source_week_end`, `segment_key`, `pbp_games`,
`source_upper_bound`, `target_cutoff` (Design A only), `gate_eligible`, `gate_exclusion_reason`,
`segment_has_pbp_games`, `included_in_career`, `included_in_roll3`, `strict_timing_ok`, and
`game_id_trace`.

Game-level trace: `coach_reliability_lineage.csv` already maps (season, person, role) → game_ids, so
`segment_key` + `pbp_games` reconcile membership exactly without duplicating game rows or letting any
fantasy outcome near the artifact.

**Reconciliation is asserted, not asserted-about.** `contribution_lineage()` is deliberately
*recomputed* from `segment_offense.csv` rather than captured during the build, so
`test_contribution_rows_reconcile_with_the_feature_table_game_counts` compares two independent paths on
**all 416 rows of both designs**: summed `pbp_games` over gate-eligible career contributions ==
`caller_history_games_career`; distinct `segment_key` count == `caller_history_segments_career`;
roll3 sum == `caller_history_games_roll3`. If the gating logic ever drifts, that test fails instead of
the artifact quietly agreeing with itself.

Exclusions carry a reason from a closed set (`attributing source postdates the target cutoff`,
`attributing source has no usable date`); the oracle design has `gate_eligible == 1` everywhere and a
null `target_cutoff`. `test_a_gate_excluded_segment_appears_but_contributes_zero` pins the BUF-2014 case:
present as a candidate for targets 2015/2016, excluded there, eligible from 2017.

---

## 7. THE PRIMARY HISTORICAL-HISTORY POLICY — **ADOPTED (v3.9b)**, with the arithmetic corrected

### 7.1 The adopted policy

- The **target-season expected caller** stays evidence-gated at the frozen preseason cutoff.
- An unknown target caller still receives league-prior caller features and **no** HC-context effect.
- Once the target caller is known, his career / rolling-three history uses the **full retrospective
  caller-attribution ledger**, restricted to source seasons and games **strictly before Y**.
- A past segment is **not** gated by the publication date of the surviving citation.
- Prior-season opening/closing caller identity (tenure, entering-change) follows the same rule, since it
  is historical attribution rather than target-season expectation.

Reason: the past play-calling role was a contemporaneously observable fact. The citation's publication
date records when I can now *prove* it, not when it became knowable.

`PRIMARY_HISTORY_SOURCE_DATE_GATED = False`.

### 7.2 **RETRACTION — two claims in the v3.9a version of this report were wrong**

The v3.9a version of this report contained the following claim. Every figure in it is wrong. Each line
below is individually marked so the sentence can never be quoted out of context:

> **[RETRACTED]** "Design A's known-with-history counts rise — the ceiling is Design B's 200/256, …"
> **[RETRACTED]** "… i.e. up to ~76 more usable rows, concentrated in the thin 2019–2022 seasons."

**WITHDRAWN in full.** The correct figures follow.

**Both figures are withdrawn.** Design A has only **152/256** known target identities, and an unknown
identity stays at the league prior however complete the history ledger is. So Design A
known-with-history ≤ 152 by construction, the ceiling is not 200, and the arithmetic maximum increase
over 124 is **28**, not 76.

**And the realised increase, computed from code, is ZERO.**

| Design A, outer 2018–2025 | strict gate | primary (adopted) | change |
|---|---|---|---|
| known target identity | 152 | 152 | — |
| known **with** history | 124 | **124** | **0** |
| known **no** history | 28 | 28 | 0 |
| unknown identity | 104 | 104 | — |
| caller-games of history | 7,274 | **7,632** | **+358 (+4.9%)** |

**Why zero.** All 28 outer known-no-history rows are genuine **first-time play-callers with no prior
segment in the ledger at all** — Daboll 2018, Kellen Moore 2019, Joe Brady 2020, Monken/Slowik/Canales
2023, Grubb/Coen/Callahan 2024, Caley/Engstrand/Patullo/Grizzard 2025, and the rest. The gate was never
what suppressed them, so removing it cannot recover them. Even the 28 upper bound is not attained.

Across **all** target seasons exactly one row gains history: **2016 DET, Jim Bob Cooter, 0 → 9 games.**

Per-season game gain: 2018 **+106** · **2019 +0** · 2020 +16 · 2021 +42 · 2022 +16 · 2023 +71 ·
2024 +71 · 2025 +36.

### 7.3 A stated rationale that is NOT achieved

The change was proposed partly to "avoid concentrating archive-retrievability missingness in 2019–2022".
**It does not do that.** 2019 — the thinnest season — gains **zero** games, and no season gains a row.
Those seasons are thin because their *target identities* are unknown (25 of 32 in 2019), not because
their history was gated.

The policy is adopted on two grounds that do hold: it is the methodologically correct treatment of a
contemporaneously observable fact, and it restores a single-axis Design A/B contrast. **It is not a
power improvement, and the 2019–2022 limitation stands undiminished.**

### 7.4 Design A vs Design B is now SINGLE-AXIS

Both designs use the identical strictly-prior retrospective history rule. They differ on exactly one
thing: **target-season identity supply.** Verified feature-by-feature —
`test_design_a_and_b_now_differ_on_target_identity_ONLY` checks all 51 model features on all **227**
identity-matching rows and finds zero differences.

Design B remains **oracle / nondeployable** purely because its target identity is retrospective. It
still holds more history in total (244/256 known identities vs 152/256), but from the same rule, not a
different one — the test that formerly implied otherwise is renamed
`test_design_b_holds_more_history_because_it_KNOWS_more_identities`.

### 7.5 The retired strict rule survives as a labelled diagnostic sensitivity

`build_arm_features_v39.strict_gate_sensitivity()` — computed **in memory**, nonprimary, nonselectable,
cannot rescue or alter the primary result, **never a sixth repo artifact**. Every row carries
`SENSITIVITY_LABEL`. It also stays auditable per row from `arm_feature_lineage_v39.csv` via
`strict_source_date_gate_would_exclude` and `strict_gate_exclusion_reason` (123 contribution rows would
have been dropped, 35 of them under Design A).

---

## 7A. PRODUCTION MODEL AUDIT

Recovered by tracing the executable call graph and loading bundle metadata read-only. **No production
training or scoring path was executed; no realized label was loaded.**

### 7.1 THIS REPO HAS TWO ARCHITECTURES — the audit is scoped to the one Arm 0 uses

| | **Arm 0 family (USED)** | legacy family (NOT used) |
|---|---|---|
| location | `fantasy/projections/models/` — 7 bundles | `fantasy/seasonal_projections/models/` |
| architecture | **direct season total** | **Model A × Model B: season total = PPG × games** |
| target | `season_total_half_ppr` | `target_ppg`, `target_games` |
| categoricals | **none** | `availability_model.pkl` (CatBoost, 13 feats) and `rookie_ppg_model.pkl` (CatBoost, 18 feats) **carry `cat_features`** |
| sample weights | **none** | **`train_model_a.py` fits with `sample_weight=train.sample_weight` (= games)** |
| bundle keys | `model, feature_cols, family, params, inner_cv_mae, target, seed, median_impute, note` | `model, feature_cols, algo, position, target, train_seasons` (+`cat_features`) |

So "no categoricals, no sample weights, no PPG×games composition" is **true of Arm 0 and false of the
repo as a whole**. Recorded because a blanket phrasing would have been wrong.

### 7.2 Arm 0 contract (authoritative)

- **Router.** `build_season_dataset.py` → `season_dataset_2014_2026.csv`; `is_rookie == 0` → veteran,
  `is_rookie == 1` → rookie joined to the frozen hit-model rookie matrix regenerated in a **temp**
  scratch dir (no PFF parquet in the repo), then coalesced by `(norm_name, position)` for the 2026
  placeholder-gsis seam.
- **Engine.** `build_rb_projection.py` is position-agnostic and **imported** by the QB/WR/TE builders
  (`season_total_target, nested_select, walk_forward, fit_final_model, _prep, _grid, _make_model,
  _score_bundle, metrics_block`). It is never modified by them. This harness imports `_make_model`
  and `_prep` from it, so the arms are compared with production's own fitting code.
- **Family / hyperparameters** — all seven LightGBM, `objective="mae"`, `random_state=42`,
  `verbose=-1`, `n_jobs=-1`:

| bundle | md5 | num_leaves / lr / n_estimators | n features |
|---|---|---|---|
| `qb_veteran_model.pkl` | `7632549f…` | 31 / 0.03 / 400 | 32 |
| `rb_veteran_model.pkl` | `167aca71…` | 15 / 0.03 / 400 | 32 |
| `rb_rookie_model.pkl` | `da230ee6…` | 15 / 0.06 / 400 | 41 |
| `wr_veteran_model.pkl` | `17dfbcf0…` | 15 / 0.03 / 400 | 32 |
| `wr_rookie_model.pkl` | `6c9a3f3e…` | 31 / 0.06 / 400 | 44 |
| `te_veteran_model.pkl` | `5a2f0b50…` | 15 / 0.03 / 400 | 32 |
| `te_rookie_model.pkl` | `f79dad0a…` | 15 / 0.03 / 400 | 44 |

- **Ordered baseline features.** The four **veteran** pools are the *same 32* season_dataset columns
  (verified identical), including the existing coaching feature `coach_changed` and `qb_changed`.
  Rookie pools: RB 41, WR 44, TE 44. `depth_rank` is excluded everywhere (RB prereg Amendment 1) and
  is disclosure-only. Bundle `feature_cols` == the builder's module pool for all seven, asserted by
  `arm0_definition()`.
- **Categorical handling.** None. Every design matrix is `df[feats].to_numpy(float)` — no categorical
  dtype, no one-hot, no label encoding, no `cat_features` key.
- **Sample weights.** None. `model.fit(Xtr, ytr)` is called without `sample_weight`.
- **Missing values.** Native NaN routed by LightGBM; `median_impute` is `None` in all seven. The
  median+missing-flag path exists only for the ElasticNet family, which no shipped bundle selected;
  when used, its medians are **train-only**.
- **Target.** Observed season-total half-PPR = Σ over REG weeks of
  `fantasy_points + 0.5*receptions`, per `(player_id, season)`
  (`build_rb_projection.season_total_target()`). **Not** `target_ppg`, which
  `build_season_dataset.py` NaNs below `MIN_GAMES_TARGET = 3` and which would drop partial seasons.
  Missing total: seasons ≤ 2025 → `0.0` (rostered, never played); 2026 → NaN.
- **PPG / games / total composition.** Not used by Arm 0 — the season total is predicted **directly**.
  PPG×games belongs to the legacy family only.
- **Transforms and clipping.** `log_pick = log(draft_pick.clip(lower=1))` is a rookie *feature*
  transform. `np.clip(pred, 0, None)` is applied by `_score_bundle` and the 2026 face-validity path
  but **not** by `walk_forward()` — so the **evaluation path is unclipped**. This harness mirrors
  `walk_forward` and therefore does not clip. Asserted against the production source by
  `test_audit_records_the_clipping_asymmetry`.
- **QB rookie path DOES NOT EXIST.** There is no `qb_rookie_model.pkl`; the QB rookie arm was HELD.
  QB is evaluated on the **veteran path only** and the QB top-12 cohort covers veterans. Recorded, not
  silently absorbed.

### 7.3 Code-vs-bundle disagreement found

Every bundle's `note` reads *"RB season-total half-PPR projection…"* — including the QB/WR/TE
bundles — because those builders reuse `build_rb_projection.fit_final_model` verbatim. **Cosmetic
only:** `feature_cols`, `family` and `params` are position-correct and match each builder's own pool
exactly. Recorded rather than "repaired", since repairing it would mean rewriting shipped bundles.

---

## 8. PLAYER-EVALUATION HARNESS DESIGN

`run_coach_projection_experiment_v39.py`. **Writes nothing.** Implemented in full; exercised on
synthetic targets only.

### 8.1 The default-closed double lock

Both must be open before any real outcome can be reached:

1. `REAL_FIT_AUTHORIZED = True` (module constant) — **SUPERSEDED by §10.14**, and
2. `COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT` in the environment.

**Item 1 is WITHDRAWN as contradictory.** C6 statically requires exactly one module-level
`REAL_FIT_AUTHORIZED = False`, so editing the constant to True made C6 — and therefore the 21-check
preflight — fail, and the run could not clear gate 1. The constant stays `False` in committed source
as the default-closed invariant and is never edited. The two runtime locks are now an exact CLI
authorization token and the exact environment token, which together mint an immutable,
invocation-scoped capability; see §10.14.

Either lock alone leaves the gate shut. `assemble_real_panel()` is the single door; it is now
IMPLEMENTED under C5-A (§10.9) and its statement 1 consumes the caller's capability. The `--real`
dead end is removed (§10.11). **Both locks are shut and neither was opened in this pass.**

### 8.2 Frozen design

| item | value |
|---|---|
| outer seasons | 2018–2025 |
| recent panel | 2021–2025, reported separately |
| inner validation | expanding: `inner training < validation < outer target`; minimums **2** train / **2** validation; unmet → **SKIP**, never relaxed |
| outer 2018 folds | `train 2014-2015 → validate 2016`; `train 2014-2016 → validate 2017` (asserted exactly) |
| arms | `ARM_0, ARM_HC, ARM_1…ARM_5` |
| identical rows | every arm predicts the same `(player_id, season)` set in every fold; asserted |
| cohorts | top-N by the **ARM_0** prediction within (season, position): QB 12, RB 24, WR 24, TE 12 |
| eligibility | inner full-panel MAE may worsen by ≤ **0.25** (exactly 0.25 is eligible) |
| selection | best eligible by inner top-cohort MAE; best arm improving < **1%** → ARM_0; arms within **0.25** of the best → **fewer added features**, then frozen arm order |
| model settings | production family + hyperparameters fixed; never retuned |
| primary input | **Design A only** |
| diagnostics | fixed ARM_HC and ARM_1…ARM_5; Design B oracle, always labelled |
| metrics | full-panel and top-cohort MAE and RMSE, mean and median bias, mean within-season Spearman |
| bootstrap | player-clustered **and** team-season-clustered, **20,000** draws, seed **20260728** |
| multiplicity | Holm across the six nonbaseline arms within each position |
| placebo | within-season **team-level** permutation, **200** draws, seed **20260728** |

Bootstrap resamples **whole clusters** via per-cluster error sums (exact, and fast enough for 20,000
draws across every arm × unit × position). Tests may pass fewer draws through an explicit parameter
while `test_frozen_bootstrap_constants` and `test_spec_pins_every_frozen_constant` assert the
production defaults.

### 8.3 The permutation placebo

`permute_team_bundles` permutes **complete team coaching bundles among the teams of the same season**.
Team labels stay put; whole feature rows move together; every player on a team-season receives the
same permuted bundle. It never permutes columns independently and never permutes player rows —
`test_permutation_never_touches_player_rows` scans the function for any reference to `player_id`,
`panel` or `y`.

This is the pre-registered control for the disclosed §2.2 cost: permuting within a season preserves
that season's bundle composition under the null, so a gain that came from acting as a partial season
indicator reproduces in the placebo and fails the 95th-percentile bar.

### 8.5 THE TEN-CONDITION PRIMARY VERDICT — now computed

`primary_verdict()` evaluates all ten §7 conditions and returns **one row per position** carrying every
raw statistic, every Boolean, the failure reasons and the verdict. It reads **only** `pred_selected`,
the nested-selected Design A pipeline, so a fixed arm sitting in the same frame cannot rescue a failure
and Design B cannot appear at all.

| # | condition | frozen threshold |
|---|---|---|
| 1 | pooled top-cohort MAE improves | ≥ **3%** |
| 2 | both clustered 95% CI upper bounds | **< 0** (both units required) |
| 3 | top-cohort MAE improves in outer seasons | ≥ **6 of 8** |
| 4 | improves in recent seasons | ≥ **4 of 5** |
| 5 | mean within-season top-cohort Spearman gain | ≥ **0.005** |
| 6 | full-panel MAE worsening | ≤ **0.25** |
| 7 | full-panel RMSE worsening | ≤ **1%** |
| 8 | nonbaseline arm selected in folds | ≥ **4 of 8** |
| 9 | beats the placebo percentile | **95th** |
| 10 | all timing / leakage / coverage / artifact-integrity / no-real-outcome assertions | pass |

Condition 10 is `_integrity_check()`: production pkls unchanged, all ten inherited v3.8/preliminary
artifacts unchanged, and the real-fit gate still locked (an unlocked gate makes a *prefit* verdict
meaningless, so it fails the condition).

**§6.1 frozen improvement statistic.** §7(1) said only "top-cohort MAE". Frozen as **pooled over all
outer top-cohort rows**: it matches the plain reading, matches what the condition-2 bootstrap resamples,
and leaves conditions 3/4 to carry per-season evidence rather than duplicating it.
`test_the_improvement_statistic_is_pooled_not_a_per_season_mean` pins the distinction on a fixture where
the two answers differ (2.5 pooled vs 5.0 per-season-mean).

Fixtures: `test_a_fixture_engineered_to_satisfy_all_ten_conditions_passes`;
`test_every_condition_can_fail_independently` (all ten flipped one at a time by a targeted
perturbation); one dedicated test per condition; plus
`test_a_fixed_arm_cannot_rescue_a_failed_nested_selected_result` (a *perfect* `pred_ARM_3` column in the
frame leaves every verdict statistic bit-identical) and `test_design_b_cannot_affect_the_verdict`
(running with and without `coach_b` yields identical verdict frames).

### 8.6 THE PLACEBO NOW TESTS THE NESTED-SELECTED PIPELINE

Previously: permute bundles, then score the **modal** selected arm as a fixed arm. That is not the
pre-registered condition.

Now, per draw: permute complete team bundles within each season → **rerun expanding inner
representation selection independently for every outer fold** → fit that draw/fold's selected
representation on all prior seasons → predict the outer season on unchanged player rows → assemble the
draw's nested-selected pipeline → compute the **same** pooled statistic as the observed value. A draw
may select a different arm in each fold, exactly as the observed pipeline does.

**Why observed and null are commensurable:** ARM_0 has no coaching feature, so its predictions are
invariant under permutation, and since the cohort is ARM_0-defined the cohort is invariant too.
Identical rows, identical cohort, identical statistic —
`test_arm0_and_therefore_the_cohort_are_invariant_under_permutation` proves it.

Regression guard: `test_placebo_can_select_different_arms_in_different_folds` forces ARM_2 in one fold
and ARM_4 in another and asserts the placebo requested exactly those arms per fold, so a return to
modal-fixed-arm behaviour fails.
`test_placebo_distribution_runs_and_is_seeded` additionally asserts the function no longer accepts an
`arm` parameter at all.

200 draws and seed 20260728 retained; `draws` is the test-only lever. **Compute cost:** one draw is now
a full nested run over every outer fold, making the placebo by far the dominant cost of the real
experiment.

### 8.7 EXACT denominators (v3.9b §1)

C3, C4 and C8 now require the frozen denominator to be **present**, not merely enough successes:

| condition | requirement |
|---|---|
| C3 | cohort season set **==** `{2018…2025}` exactly, **no** duplicate `(player_id, season)` rows, **and** ≥ 6 improve |
| C4 | `{2021…2025}` all present, no duplicates, **and** ≥ 4 improve |
| C8 | fold-selection key set **==** `{2018…2025}` exactly, **and** ≥ 4 non-baseline |

Missing / duplicate / unexpected seasons and fold keys fail the relevant condition and are named in
`denominator_problems` plus six dedicated columns. Proven by
`test_six_improving_seasons_supplied_as_only_six_seasons_fails_c3` (six real improvements, C3 still
False), the matching C4 and C8 tests, and the unexpected/duplicate/missing-key tests. The complete 8/5
fixture still passes all ten.

### 8.8 CONDITION 10 IS A 17-CHECK RUNTIME PREFLIGHT (v3.9b §2)

`preflight()` reads no outcome and returns one Boolean plus a detail string per check:

`protected_hashes` (18) · `v39_artifacts_pinned` (5) · `no_unauthorized_v39_artifact` ·
`no_coaching_parquet` · `feature_table_keys_and_rows` (416, unique keys, 2014–2026, both designs) ·
`design_a_outer_identity_coverage` (exactly 152/256) · `unknown_and_no_history_routing` (frozen neutral
values, no NaN) · `forbidden_feature_policy` (every manifest arm) ·
`manifest_full_x_matches_bundles` · `manifest_qb_rookie_null` · `coverage_reconciles` ·
`lineage_strict_timing` · `contribution_lineage_reconciles` ·
`design_b_oracle_and_unselectable` · `production_models_identical` ·
`pipeline_timing_assertion_state` (RENAMED v3.9w from `pipeline_timing_assertions_ran`; phase-aware, see the manifest §3a) · `run_mode_locks`.

C10 passes only when all 17 are true; the record is returned as a `preflight` frame beside the verdict.

One check is about **execution, not state**: `_PIPELINE_ASSERTIONS` counts the timing / leakage /
row-identity assertions the pipeline actually ran, so C10 cannot be satisfied by a path that never
reached them. `test_the_pipeline_actually_increments_every_assertion_counter` proves all four fire.

Eleven tests corrupt one contract each **on a temporary copy** (`preflight(data_dir=…)`) and assert the
right check fails — canonical artifacts are never mutated.

### 8.9 RUN MODES — the real-authorization paradox (v3.9b §3)

```
synthetic_prefit : BOTH locks MUST be closed
authorized_real  : BOTH locks MUST be open (module constant AND environment token)
```

A partially authorized state is invalid in **both** modes; an unknown mode is invalid. The contract
fails closed, proven by an 8-case truth table. **No mode relaxes any artifact, timing, leakage,
coverage or feature-policy check** — `test_no_run_mode_relaxes_a_non_lock_check` corrupts an artifact
and confirms both modes still fail.

This pass runs `synthetic_prefit` with both locks shut. `REAL_FIT_AUTHORIZED` has exactly one
assignment in the module and its value is `False`, verified at AST level (a substring scan would flag
the docstring, which legitimately quotes what a future authorized run must do). Nothing in the module
sets the environment token.

### 8.4 Separation guarantees

Selection reads inner folds only; the outer season never enters training or selection; no fixed arm
and no Design B result can affect selection (`test_selection_is_identical_whether_or_not_the_oracle_is_supplied`
runs the whole pipeline with and without `coach_b` and asserts identical selection frames).

---

## 9. REQUIREMENT MATRIX SUMMARY

Full requirement→code→test mapping in `REQUIREMENT_MATRIX.md`:
**32 Phase-2A rows (F-1…F-32)** and **29 Phase-2B rows (H-1…H-29)**, every one PASS, each naming its
generating function, input columns, timing rule, missing-value rule, and covering test.

---

## 10. TEST COUNTS AND ARTIFACT HASHES

| scope | count |
|---|---|
| inherited baseline (reproduced, offline) | **141** |
| new v3.9 + v3.9a + v3.9b + v3.9c + v3.9d + v3.9e + v3.9f + v3.9g + v3.9i + v3.9j + v3.9k + v3.9m + v3.9n + v3.9o + v3.9p + v3.9q + v3.9r + v3.9s + v3.9t + v3.9u + v3.9v tests | **1,134** |
| **full coaching suite** | **1,316 collected · 1,315 mandatory passed · 1 optional git cross-check (passes when the pinned blob is reachable, otherwise skips) — offline, egress blocked, fresh empty temp dir** |

### 10.1 THE TWO CODEX REPRODUCTIONS NOW FAIL SEMANTICALLY

Run before and after the repairs, on temporary artifact copies (canon never mutated):

```
REPRO 1: corrupt design_a / ARM_2 / known_with_history / n_team_seasons -> 999
  v3.9b:  coverage_reconciles = True    <-- the defect: only the byte-hash objected
  v3.9c:  coverage_reconciles = False
          detail: 1 column(s) disagree: n_team_seasons at {'design': 'design_a', 'arm': 'ARM_2',
                  'season': 2014, 'identity_state': 'known_with_history'}: artifact 999 != derived 32

REPRO 2: delete team_coach_features_design_a_v39.csv from the temp copy
  v3.9b:  RAISED FileNotFoundError      <-- the defect: no structured record at all
  v3.9c:  RETURNED structurally. all_ok = False, 7 checks failed:
            v39_artifacts_pinned              changed/missing: [team_coach_features_design_a_v39.csv]
            v39_artifacts_readable            design_a: FileNotFoundError
            feature_table_keys_and_rows       blocked by design_a load failure (FileNotFoundError…)
            design_a_outer_identity_coverage  blocked by design_a load failure (FileNotFoundError…)
            unknown_and_no_history_routing    blocked by design_a load failure (FileNotFoundError…)
            coverage_reconciles               blocked by design_a load failure (FileNotFoundError…)
            contribution_lineage_reconciles   blocked by design_a load failure (FileNotFoundError…)
```

Both are pinned as named tests: `test_THE_EXACT_CODEX_CASE_corrupting_ARM_2_known_with_history_now_fails`
and `test_THE_EXACT_CODEX_CASE_deleting_design_a_returns_instead_of_raising`.

### 10.2 The live-document scan

A mechanical scan over 9 live targets — the prereg from `## §0`, requirement matrix, audit TODO, research
log, this report, both v3.9 module sources, the manifest and the generated lineage artifact — reports
**CLEAN**: none of the five superseded claims is asserted unqualified anywhere. Each is listed with its
own same-line qualifier:

- RETIRED — source-date gating of primary historical segments, and the same for prior-season openers.
- RETRACTED — the row gain of 28 or ~76 rows (the realised gain is zero rows).
- RETRACTED — the 200/256 known-with-history ceiling (the reachable ceiling is 152).
- REFUTED — any relief of the 2019–2022 power problem (retiring the gate gave 2019 +0 games).
- WITHDRAWN — any second, gating axis in the Design A vs Design B contrast, which is single-axis.

The scanner is self-tested: it still catches every one of them when injected as a plain unqualified
sentence. It is line-based and demands the qualifier on the SAME physical line, which is why each bullet
above carries its own.

Per-module counts, collected rather than estimated:

| module | tests | inherited / new |
|---|---|---|
| `test_arm3_orchestration.py` | 22 | inherited |
| `test_coaching_phase1c.py` | 33 | inherited |
| `test_reliability_phase1d.py` | 34 | inherited |
| `test_stage_models_synthetic.py` | 27 | inherited |
| `test_personnel_controls.py` | 15 | inherited |
| `test_drive_definitions.py` | 7 | inherited |
| `test_artifact_ownership.py` | 9 | 3 inherited + **6 new** |
| `test_arm_features_v39.py` | **88** | new |
| `test_coach_projection_harness_v39.py` | **246** | new (155 at v3.9c; +91 from the v3.9d boundary, C5/C6/C7 binding-context and wording work) |
| `test_boundary_corpus.py` | **146** | new |
| `test_assemble_real_panel_v39.py` | **203** | new (200 at v3.9m; +2 at v3.9n, splitting the two missingness/readiness properties into a live case and an injected fail-closed case) |
| `test_combine_snapshot_provenance.py` | **9** | new |
| `test_rookie_matrix_v39.py` | **91** | new at v3.9n — the frozen rookie matrix, its corruption cases and its input pins |
| `test_pff_point_in_time_v39.py` | **37** | new at v3.9o — the PFF temporal-leak repair, red-before-green |
| `test_arm0_refits_from_scratch_v39.py` | **38** | new at v3.9p — the serialized estimator never reaches a prediction |
| `test_activation_wiring_v39.py` | **31** | new at v3.9q — the implemented C5-A door and every transition into it |
| `test_veteran_snapshot_v39.py` | **45** | new at v3.9r — the frozen veteran snapshot and its 2026-independence |
| `test_authorized_runner_v39.py` | **49** | new at v3.9s — result ownership, the panel adapter, the CLI and the 5-file mapping |
| `test_composed_feature_reader_v39.py` | **47** | new at v3.9t — the frozen veteran+rookie routing, implemented |
| `test_evaluation_eligibility_v39.py` | **28** | new at v3.9u — the pre-outcome eligibility partition |
| `test_authorization_capability_v39.py` | **48** | new at v3.9v — the invocation-scoped authorization capability |
| `test_boundary_corpus.py` | **166** | 146 at v3.9o; +20 at v3.9q for the 10 C5-A injections |

22+33+34+27+15+7+3 = **141** inherited; 88+246+166+205+9+91+37+38+31+45+49+47+28+48+6 = **1,134** new; total **1,275**.

To reproduce the 141 exactly, ignore the fourteen v3.9 test modules and deselect these six tests. (The `tests/`
tree **is now tracked** — Joseph committed it on 2026-07-30, so new-vs-inherited *can* be diffed against
`HEAD` today; the earlier statement that it was untracked is **SUPERSEDED**. The six IDs are still
listed verbatim because a mistyped `--deselect` is silently ignored by pytest and yields 147.)

```
test_artifact_ownership.py::test_each_protected_text_artifact_has_exactly_one_writer
test_artifact_ownership.py::test_build_arm_features_v39_writes_only_the_five_authorized_artifacts
test_artifact_ownership.py::test_the_harness_writes_no_repo_artifact_at_all
test_artifact_ownership.py::test_no_unauthorized_v39_artifact_exists_on_disk
test_artifact_ownership.py::test_the_head_coach_win_ledger_is_derived_in_memory_not_cached
test_artifact_ownership.py::test_the_v39_modules_never_write_outside_the_coaching_data_dir
```

Confirmed run: `141 passed, 6 deselected`. The three genuinely inherited ownership tests are
`test_each_protected_artifact_has_exactly_one_writer`, `test_build_exposure_writes_only_its_three_artifacts`
and `test_build_exposure_print_message_matches_what_it_writes`.

**No existing test was weakened or deleted.** Six were CORRECTED because the policy or a name was wrong,
each with the reason recorded in its docstring:

| test | why it changed |
|---|---|
| `test_design_a_and_b_differ_only_on_identity_supply` → `..._share_rows_schema_and_the_entire_hc_block` | the old name overclaimed (v3.9a) |
| `test_design_b_history_is_ungated_and_therefore_larger` → `..._holds_more_history_because_it_KNOWS_more_identities` | under v3.9b BOTH designs are ungated; B is larger only because it knows more identities |
| `test_the_two_designs_differ_on_BOTH_identity_and_history...` → `..._differ_on_target_identity_and_that_is_the_ONLY_axis` | v3.9b restored the single-axis contrast, so the two-axis assertion is withdrawn |
| `test_synthetic_design_a_gate_hides_a_post_cutoff_source` → `..._the_primary_policy_does_NOT_hide_a_late_published_source` | inverted by the v3.9b policy; the strict behaviour is still asserted via the diagnostic flag |
| `test_lineage_records_the_design_a_gate...` → `..._the_target_identity_gate_and_the_shared_history_rule` | `evidence_gate` was replaced by `target_identity_gate` + `history_rule` |
| `test_contribution_rows_record_why_a_segment_was_excluded` → `..._exclude_nothing_by_source_date_under_the_primary_policy` | the primary policy excludes nothing; the retired rule is asserted separately |

### v3.9 outputs — exactly five, byte-identical across two consecutive rebuilds

**FINAL v3.9c hashes** (rebuild #1 and rebuild #2 both reproduced all five exactly):

```
team_coach_features_design_a_v39.csv         b3e5aa463fff10161cf3abb78e0854f2   unchanged from v3.9b
team_coach_features_design_b_oracle_v39.csv  5f8cf19b9aa4310b7eebbfb2406092c1   unchanged from v3.9b
arm_feature_manifest_v39.json                65b596906eec757018e5b37b367835c2   unchanged from v3.9b
arm_feature_coverage_v39.csv                 807e38813cdd51800905e2b3c1a6d507   unchanged from v3.9b
arm_feature_lineage_v39.csv                  fcf8692bedab4e23652486cdcfe8f0b0   CHANGED in v3.9c
```

**The lineage hash changed, as it had to.** Its false primary-policy metadata was corrected: every
caller-history and caller-continuity `timing_rule` moved off the **RETIRED** wording
(`"…Design A additionally requires source upper bound <= Y cutoff"` — WITHDRAWN) onto the pinned
`PRIMARY_TIMING_RULE`, and the `pc_tenure_current_team` note moved off the **RETIRED** "openers are
themselves gated" claim onto a statement that prior-season openers come from the same full
retrospective ledger. **No feature value, row count or column changed** — 2,514 rows, same three `record_kind` values
— only the policy text. The other four artifacts are byte-identical to v3.9b, which is the check that
v3.9c changed documentation and validation only, not data.

These five values are also pinned in `run_coach_projection_experiment_v39.V39_ARTIFACT_HASHES` and
checked by preflight; `test_pinned_v39_hashes_match_disk` fails if the pins go stale.

**Full hash history across the three passes, with the value-level reason for every change. No hash is
claimed unchanged where the value moved:**

| artifact | v3.9 | v3.9a | v3.9b | reason for each change |
|---|---|---|---|---|
| `..._design_a_v39.csv` | `021162a8` | `021162a8` | **`b3e5aa46`** | v3.9b: Design A history is now ungated (+358 outer caller-games) and its prior-season caller openers are ungated too, changing `pc_tenure_current_team` / `pc_changed_entering` on some rows |
| `..._design_b_oracle_v39.csv` | `5f8cf19b` | `5f8cf19b` | `5f8cf19b` | unchanged in all three — Design B was already ungated, which independently confirms the change is confined to Design A |
| `arm_feature_manifest_v39.json` | `6e96251d` | **`65b59690`** | `65b59690` | v3.9a: added `arm0_baseline_features`, `arm0_baseline_counts`, `missing_production_paths`, `buckets`, `full_model_x`, `full_model_x_counts`, `full_model_x_note`. No pre-existing key changed. |
| `arm_feature_coverage_v39.csv` | `fc088362` | `fc088362` | **`807e3881`** | v3.9b: Design A identity-state decomposition and history-game means moved with the policy |
| `arm_feature_lineage_v39.csv` | `3f55156a` | **`3a7d56e5`** | **`32a45898`** | v3.9a: real snapshot provenance on the two ARM_HC rows + 1,631 `caller_contribution` rows. v3.9b: `evidence_gate` → `target_identity_gate` + `history_rule`; `gate_eligible` now 1 everywhere with the retired rule recorded as `strict_source_date_gate_would_exclude` / `strict_gate_exclusion_reason`. |

Design A's row/column contract is unchanged (416 rows, 51 model features, same keys); only values moved.
The **verified v3.6 history totals are preserved** — Reid 192, McVay 181, McDaniel 68 caller-games
entering 2026 — asserted by `test_2026_routing_history_totals_match_the_verified_v36_figures`.

The head-coach win ledger is no longer written anywhere — it is computed in memory from the frozen
snapshot on every call (§1.4).

`arm_feature_lineage_v39.csv` = **2,514** rows: 51 `feature_definition` + 832 `identity_routing`
(2 designs × 13 target seasons × 32 teams) + **1,631** `caller_contribution`. `strict_timing_ok` is true
on every routing and contribution row.

---

## 10.3 v3.9d — THE BOUNDARY CHECK WAS STILL A FALSE NEGATIVE, AND LIVE DOCS STILL CARRIED RETIRED CONTRACTS

### 10.3.1 `no_real_outcome_access()` missed the ordinary repository path form

v3.9c added the check as production logic, which was the right move, but it inspected only two
positions: a string constant passed **directly** as a reader argument, and a **literal** subscript. The
normal way this repository names a file is neither — `DATA / "season_dataset_2014_2026.csv"` is a
`BinOp`, so the string never appears where the check was looking. Codex injected exactly that into pure
source and the check returned `ok=True`.

Measured before the repair, on pure in-memory source (canonical files never modified): **nine** distinct
injections passed, not one.

| injection | v3.9c | v3.9d |
|---|---|---|
| `pd.read_csv(DATA / "season_dataset_2014_2026.csv")` — the exact Codex case | **passed** | caught |
| `p = DATA / "season_dataset_2014_2026.csv"` then `pd.read_csv(p)` | **passed** | caught |
| `p = pathlib.Path("season_dataset_2014_2026.csv")` then `pd.read_parquet(p)` | **passed** | caught |
| token parked in a dict, read back via subscript | **passed** | caught |
| token in an f-string component | **passed** | caught |
| outcome columns parked in a list | **passed** | caught |
| `REAL_FIT_AUTHORIZED: bool = True` (AnnAssign) | **passed** | caught |
| `os.environ.update({SWITCH: TOKEN})` | **passed** | caught |
| `os.putenv(SWITCH, TOKEN)` / `os.environ.setdefault(...)` | **passed** | caught |
| an EXTRA module in the `sources` mapping | **passed** | caught |
| `os.environ[SWITCH] = TOKEN` | caught | caught |
| a module OMITTED from `sources` | caught | caught |
| gutted `assemble_real_panel` | caught | caught |

**The contract is now stated exactly, and it is not a theorem about Python.** Its canonical name is
`C1-C7 + C4b` — **ASCII hyphen, never an en dash.** That distinction is not pedantry: v3.9d claimed "one
wording everywhere" while the runtime printed `C1-C7` and every document wrote `C1–C7`, two strings that
are visually identical and never equal.

The single success string is the module constant `NO_OUTCOME_OK_DETAIL`, and here it is verbatim — this
document, `REQUIREMENT_MATRIX.md` H-24, the prereg and the module all contain these exact bytes:

```
both v3.9 modules satisfy the frozen structural no-outcome contract C1-C7 + C4b (scope, executable-only, no banned callee, no banned token in any executable string, no reading through an exemption, sealed entry point, single False lock, no environment write)
```

This is a **copy** in static Markdown, not a generated include — Markdown cannot quote a Python constant.
What makes it safe is enforcement, not hope: `test_the_exact_success_detail_appears_verbatim_in_every_document`
reads all four files and fails unless the literal string is present, and
`test_the_c10_success_row_prints_the_exact_pinned_detail` asserts the preflight row equals the same
constant. Change the constant without updating the documents and the suite goes red.

It is a decidable structural contract over the executable AST of two named modules:

- **C1 scope** — the `sources` mapping must be exactly the two modules; omission *and* addition fail.
- **C2 executable-only** — docstrings stripped, comments never parsed.
- **C3** — no call to a banned outcome-producing callee.
- **C4** — **no banned outcome token in ANY executable string constant, in any position**.
- **C4b** — **no reading through an exemption**: neither exempt structure may act as a data source.
- **C5 sealed entry point** — `assemble_real_panel` is bound exactly once, by one undecorated
  module-level `def`, whose executable body is exactly two statements: a zero-argument
  `require_real_fit_authorization()` then an unconditional `raise NotImplementedError(...)`.
- **C6** — exactly one module-level `REAL_FIT_AUTHORIZED = False` across
  `Assign`/`AnnAssign`/`AugAssign`/`NamedExpr`.
- **C7** — no environment write, rebinding or deletion by any enumerated form.

The docstring on `no_real_outcome_access()` is the authoritative statement and names what it does
**not** cover: aliasing, dynamic attribute access, `getattr`/`eval`/`exec`, third-party imports, and
tokens assembled at runtime from fragments.

C4 is a blanket rule, which is only adoptable because canonical source was **measured** first: all 17
executable strings containing a banned token sit in exactly two places, and both are enumerated rather
than pattern-matched. **E1** is the module-level `BANNED_OUTCOME_TOKENS` tuple itself. **E2** is
`audit_production()`, a read-only descriptive record of the production pipeline that necessarily names
the real panel files. E2 is not "trust this function": it is **void** unless the function's callee set
stays inside the frozen `AUDIT_ALLOWED_CALLEES` (measured: `RuntimeError`, `_production_engine`,
`arm0_definition`, `items`, `list`, `str`), so smuggling a reader into it revokes the exemption and
reports every token inside. C4b then closes the last route — indexing a token back out of an exempt
structure, which would otherwise launder it past C4.

**The tests no longer own a parallel definition.** `test_no_v39_module_ever_CALLS_a_real_outcome_source`
and `test_no_real_outcome_token_is_used_as_a_FILE_READ_OR_COLUMN_ACCESS` carried their own docstring
stripper and their own copies of the banned sets, and had drifted to exactly the same blind spot — the
Codex injection passed the module check **and** its test. Both now delegate to the runtime contract, and
`test_the_module_owns_the_banned_sets_and_the_tests_do_not_copy_them` fails if the copies return.

Two adjacent tests were substring scans that broke once the module *enumerated* the forms it bans —
`"putenv" not in src` cannot tell a ban from a use. They now delegate to the AST contract, which is the
same "documenting is not crossing" distinction the walk exists to make.

### 10.3.1b C5, C6 and C7 were still evadable — two further review rounds

The first v3.9d pass tightened C4 but left the entry point, the lock and the environment enforced by the
older, weaker logic. Two review rounds followed, and the honest arithmetic is worse than either round's
headline.

**The red proof is now a permanent, executable corpus — not prose.** Earlier revisions of this section
quoted "nine", then "fourteen", then "fifteen", then "27 of 46". **Every one of those is SUPERSEDED and
none was supported**: no test materialised the historical validator, and the "46" was produced by
counting `test_c5*`/`test_c6*`/`test_c7*` collected nodes, which sweeps in positive controls and unrelated
statistical tests that merely share a prefix. A count of evasions is meaningless without an enumerated
list.

The list is now enumerated once, in `tests/boundary_corpus.py`, with a stable id, category, payload and
recorded historical result per case. `tests/test_boundary_corpus.py` runs both validators over the corpus
and **asserts the arithmetic**; `test_the_reported_arithmetic_appears_in_the_stop_report` then fails
unless this document states the same numbers. The corpus is 75 injections plus 7 positive controls held
in a separate table, so a control can never be miscounted as an evasion.

**The historical proof fails closed.** The first version of this test called `git show` and
`pytest.skip`-ped when git was missing or the revision unreachable — meaning a fully green suite was
possible with the red proof never executed. A proof that can silently not run is not a proof. The
historical validator is therefore **vendored into the repo** and every failure path is an assertion:

| provenance | value |
|---|---|
| fixture | `tests/fixtures/historical_validator_a5b4af7.pysrc` |
| commit | `a5b4af7c71b8cf5663757488770181de13e32664` |
| blob | `85c438f7d908e9df7da8d5e44ad8e30d3bbeeffe` |
| path at that commit | `fantasy/projections/coaching/run_coach_projection_experiment_v39.py` |
| sha256 of the fixture | `17909c28b95bbc9394d0d1c208802fb02aeb542210ccfc42c37598eed2c46c27` |

The red proof loads those bytes with **no git, no network and no reachable history**, and fails — never
skips — if the fixture is absent or its sha256 moves. A separate cross-check compares the fixture against
`git cat-file -p <blob>` when git happens to be available; only that *cross-check* may skip, and the
proof itself is unaffected by its absence.

**The two arms are measured against different source shapes, deliberately.** The vendored `a5b4af7`
validator's C5 clause only knows the C5-S door; the live harness now carries the C5-A implemented door
(§10.8). Judging today's source with the historical validator would flag the door itself and make every
other injection look "caught" for a reason that has nothing to do with the clause under test — measured,
that collapses the historical figure from 41 to **5**. The historical arm therefore reverts ONLY the
entry point to C5-S (`boundary_corpus.historical_pure_sources()`); every other clause is still exercised
against the live module body. The operative safety number — **0 undetected now** — is measured against
the LIVE source, unmodified.

Measured, and asserted by that corpus:

| category | undetected at `a5b4af7` | undetected now |
|---|---|---|
| C1 scope | C1 0/2 | 0 |
| C3 banned callee | C3 0/1 | 0 |
| C4 banned tokens | C4 0/8 | 0 |
| C4b reading through an exemption | C4b 0/2 | 0 |
| **C5 sealed entry point (C5-S)** | **C5 19/21** | 0 |
| **C5A implemented door (C5-A)** | **C5A 0/10** | 0 |
| **C6 lock invariant** | **C6 8/12** | 0 |
| **C7 process environment** | **C7 14/19** | 0 |
| **total** | **41 of 75 injections passed undetected** | **0 of 75** |

Every figure in that table is generated from the corpus and asserted by
`test_the_reported_arithmetic_appears_in_the_stop_report`, which builds the expected strings from
`totals()` — including both totals and **all seven** category rows, not a subset. Change the corpus and
this document fails the suite until it is updated.

C1/C3/C4/C4b are 0 at `a5b4af7` because that commit already contained the C4/C4b rewrite — Joseph's
`cleanup` commit swept it in mid-pass (§10.3.3). The failures at `a5b4af7` are exactly the three checks
that had not yet been repaired.

**A ledger correction.** `c3-banned-callee` was previously filed under C4. It calls
`season_total_target()` and is caught by the banned-**callee** clause C3, which is a different check from
the banned-**token** clause C4 — it would fire with no banned string present anywhere. C3 is now a
declared category, the split is C3 0/1 and C4 0/8, and the totals are unchanged at 41/65 and 0/65.
`test_every_declared_category_is_exercised_by_the_corpus` fails if a declared category has no cases, and
`test_the_banned_callee_case_is_categorised_as_c3_not_c4` pins the classification.

**The isolated augmented-assignment case matters**: the earlier regression wrote
`assemble_real_panel = None` before `assemble_real_panel += 1`, so the plain assignment did the catching
and the `AugAssign` form was never actually isolated. The corpus case
`c5-rebind-augassign-standalone` is the bare statement, and `test_the_corpus_contains_the_standalone_augmented_assignment_case`
pins that it stays bare.

All injections run on pure in-memory source; canonical files were never modified.

**The root cause was structural, not a missing case.** C5, C6 and C7 each carried their own ad-hoc list
of "assignment forms", and all three lists were incomplete in the same way — they knew
`Assign`/`AnnAssign`/`AugAssign`/`NamedExpr`/`Delete` and nothing else. Python binds names in many more
places. Twelve injections walked straight through all three checks: tuple, list and starred
destructuring, `for` targets, `with ... as`, `except ... as`, `match` captures and comprehension targets.

There is now **one recursive binding-target walker** (`name_bindings` for an identifier, `env_bindings`
for the process environment) used by all three checks. It handles: `Name`; `Tuple`/`List`/`Starred`
destructuring, recursively; `Assign`/`AnnAssign`/`AugAssign`/`NamedExpr`/`Delete`; `For`/`AsyncFor`
targets; `With`/`AsyncWith` `optional_vars`; `ExceptHandler` names; `MatchAs`/`MatchStar`/`MatchMapping`
captures; comprehension targets; `FunctionDef`/`AsyncFunctionDef`/`ClassDef`; and import aliases. C6
additionally records whether a binding was reached through destructuring, because a destructured binding
has no single inspectable value and therefore can never be the canonical `= False`.

**C5** searched for *a* `def assemble_real_panel` and then asked whether a `NotImplementedError` was
raised *anywhere* inside it. Both halves were too weak:

| C5 evasion | before | after |
|---|---|---|
| `assemble_real_panel = lambda *_a, **_k: None` after the def | **passed** | caught (`bound 2 times`) |
| `require_real_fit_authorization(); return None; raise NotImplementedError(...)` | **passed** | caught (body must be exactly 2 statements) |
| a second `def` of the same name | **passed** | caught |
| `from os import path as assemble_real_panel` | **passed** | caught |
| `del assemble_real_panel` | **passed** | caught |
| `(assemble_real_panel := None)` | **passed** | caught |
| raise made dormant by `if False:` | **passed** | caught |
| `require_real_fit_authorization(True)` (arguments) | **passed** | caught (must be zero-argument) |
| a decorated definition | **passed** | caught |

C5 now requires **exactly one binding** of the name across the module — no second definition,
assignment, lambda, import alias, deletion, augmented assignment or named expression — by one
**undecorated module-level `def`**, whose docstring-stripped body is **exactly two statements**: a
zero-argument `require_real_fit_authorization()`, then an unconditional
`raise NotImplementedError(...)`. "Exactly two statements, the second a `Raise`" is what makes an early
return and a dormant raise both impossible; there is no separate reachability analysis, and none is
claimed.

**C7** inspected only subscript targets and selected method calls, so replacing the mapping wholesale
passed while the result asserted "no environment write":

| C7 evasion | before | after |
|---|---|---|
| `os.environ = {SWITCH: TOKEN}` | **passed** | caught (`os.environ Assign rebinding`) |
| `os.environ \|= {SWITCH: TOKEN}` | **passed** | caught (`AugAssign rebinding`) |
| `os.environ: dict = {...}` | **passed** | caught (`AnnAssign rebinding`) |
| `del os.environ` | **passed** | caught (`deletion`) |
| bare `environ = {...}` | **passed** | caught |
| `os.environ[SWITCH] = TOKEN` | caught | caught |

Reading the environment is deliberately still permitted — `os.environ.get(...)` is how the lock reads
itself, and `test_c7_still_permits_READING_the_environment` pins that so the repair cannot be
over-tightened into breaking the lock.

**C7 also had false positives, in the opposite direction — two rounds of them.** `_is_env_ref()` accepted
*any* attribute named `environ`, so an unrelated `config.environ = {}` or `config.environ.update({})` was
reported as opening the environment lock. Then `_callee_name()` discarded the receiver, so
`config.putenv(...)` and `config.unsetenv(...)` were rejected too, although C7 promises `os.putenv` and
`os.unsetenv` specifically. A check that fires on innocent code teaches people to ignore it. Both now
require the receiver to be the name `os`, and four positive controls in the corpus
(`ctl-config-environ-assign`, `ctl-config-environ-update`, `ctl-config-putenv`, `ctl-config-unsetenv`)
assert unrelated attributes and methods stay allowed.

**And C7 was applying only half of the shared walker.** `env_bindings()` consumed
`_binding_target_exprs()` but never `_bare_name_bindings()`, unlike `name_bindings()` — so
`except Exception as environ`, `case environ`, `def environ`, `class environ` and
`import pathlib as environ` all passed, contradicting both the binder list printed in this report and the
pinned decision that a bare `environ` counts. It now consumes both halves.

The bare identifiers `environ`, `putenv` and `unsetenv` remain banned **deliberately and
conservatively** — `from os import environ` is a real import form — and that is a stated contract in the
C7 docstring, not an accident: bind the name `environ` in any way at all and C7 fires; use `os.environ`
if you need the real object.

**The frozen vocabulary is now pinned by value.** The eleven constants the walker consults
(`V39_SOURCE_MODULES`, `BANNED_OUTCOME_CALLEES`, `BANNED_OUTCOME_TOKENS`, `READER_CALLEES`,
`TOKEN_LIST_NAMES`, `DOCUMENTATION_ONLY_FUNCTIONS`, `AUDIT_ALLOWED_CALLEES`, `ENV_NAMES`,
`ENV_WRITE_METHODS`, `ENV_WRITE_FUNCTIONS`, `LOCK_NAME`, plus `ENTRY_POINT_NAME`) are asserted
element-by-element by `test_the_frozen_boundary_vocabulary_is_pinned_by_value`. Before this, deleting a
banned token that no other test happened to exercise narrowed the production contract with the whole
suite still green. The tests still do **not** reimplement the walker — they pin what it looks for.

### 10.3.2 Live documents still asserted retired contracts

The §1.1 opening block was live verification text, not a historical record, and it contradicted the
verified §10 closing section. It asserted a suite total of 254 (SUPERSEDED) and a count of
113 added tests (SUPERSEDED), and it told the reader to deselect a RETIRED ownership-test ID —
`test_the_head_coach_win_ledger_is_cached_outside_the_repo` (WITHDRAWN; no such test exists). All three
are corrected; §1.1 now carries one canonical command, the six real IDs, and one result.

An audit of every test name in `REQUIREMENT_MATRIX.md` found the problem was wider than the rows
reported: the matrix names **268** distinct tests and **7** of them did not exist while their rows were
marked **PASS** — F-29, F-32, H-19, H-20, R-12 and two Phase-1 rows. A matrix row naming a nonexistent
test is a PASS with no evidence behind it, so this is now pinned by
`test_every_test_named_in_the_requirement_matrix_actually_exists`, which checks the whole matrix rather
than the rows that happened to be noticed.

Retired contracts corrected in place: the head-coach win ledger is **derived in memory** from the frozen
snapshot and cached nowhere (the `COACH_V39_SCRATCH` contract is RETIRED); the harness writes
**nothing** (the "two outcome-free repo artifacts" contract is RETIRED); H-24 now names the production
`no_real_outcome_access()` contract and its regression tests; the Phase-2B header reads **246**, not 52;
`test_arm_features_v39.py` reads **88**, not 55.

The retired-identifier sweep is no longer a scratchpad script. It is
`test_no_live_document_asserts_a_retired_identifier_unqualified` over five live documents, with
`test_the_retired_claim_scanner_actually_catches_each_claim` proving each pattern still fires on an
unqualified sample and still respects a same-line qualifier.

### 10.3.3 PART OF THIS PASS WAS COMMITTED MID-FLIGHT BY A CONCURRENT SESSION — READ THIS BEFORE REVIEWING

**I made zero commits.** But the v3.9c work was committed by Joseph during this pass
(`3e6344b`, `dedd55e`, `fa80c2e`, `26ebef4`, `0b7e7dd`, `a5b4af7`, 12:07–12:29 on 2026-07-30), and the
last of those — **`a5b4af7 "cleanup"`, committed 12:29:35** — swept in
`run_coach_projection_experiment_v39.py` **as it stood at 12:21:56**, which already contained the
rewritten `no_real_outcome_access()`. `git log -S _exemption_laundering` confirms `a5b4af7` introduced
it.

So the FIRST v3.9d validator rewrite (the C4/C4b work) went into `HEAD` **unreviewed**. The second
review round then reopened that same file to repair C5 and C7, so it is modified again and the whole
pass is once more uncommitted — but a reviewer diffing only the working tree will not see the C4/C4b
change, because part of it is already the baseline.

**Current scope — 8 modified files plus 3 new untracked test files differ from `HEAD` (`a5b4af7`),
and nothing else.** The new files are `tests/boundary_corpus.py`, `tests/test_boundary_corpus.py` and
`tests/fixtures/historical_validator_a5b4af7.pysrc`; because they are untracked, `git diff --shortstat`
does **not** count them, which is why the diffstat covers 8 files rather than 11:

| file | contents |
|---|---|
| `run_coach_projection_experiment_v39.py` | C5/C7 repair, `NO_OUTCOME_OK_DETAIL`, contract docstring (the earlier C4/C4b half is already in `HEAD`) |
| `tests/test_coach_projection_harness_v39.py` | C5/C7 regressions, frozen-vocabulary pin, matrix and retired-claim scanners |
| `tests/test_artifact_ownership.py` | the RETIRED "belongs in SCRATCH" comment |
| `build_arm_features_v39.py` | escape debris + a comment quoting a SUPERSEDED suite total |
| `V39_PREFIT_STOP_REPORT.md` | §1.1, §1.4, §10.3, unresolved items 17 and 18 |
| `REQUIREMENT_MATRIX.md` | F-29, F-32, H-19, H-20, H-24, R-12, test counts |
| `AUDIT_TODO.md` | items 24, 26, 27 |
| `preregs/PREREG_coach_quality_2026-07-28.md` | §E contract wording, status counts |
| `tests/boundary_corpus.py` *(new, untracked)* | the enumerated 75-injection + 7-control corpus |
| `tests/test_boundary_corpus.py` *(new, untracked)* | runs the frozen `a5b4af7` validator, asserts the red/green arithmetic |
| `tests/fixtures/historical_validator_a5b4af7.pysrc` *(new, untracked)* | the frozen historical validator, sha256-pinned |

No insertion/deletion totals are quoted here on purpose: this document is itself one of the eight files,
so any edit to this paragraph changes the number the paragraph states. Run
`git diff --shortstat` for the live value. The **file list** is the stable, checkable claim.

The five data artifacts are tracked and byte-identical to `HEAD`; **no artifact changed in this pass**,
which is the expected result for repairs that are validation and documentation only.

### 10.3.4 Source corruption removed

`build_arm_features_v39.py:181` carried the literal characters `` `r`n `` inside a comment — PowerShell
escape debris from an earlier edit, not a data change, but not something to commit. Replaced with two
normal comment lines.

---

## 10.4 v3.9e — REAL-OUTCOME TRANSITION PREPARED, NOT ACTIVATED

**Opening state, reproduced against `0fd34b9 "prefit system verification"` with a clean worktree:**
(HISTORICAL opening snapshot, SUPERSEDED by the canonical statement in §1.4) 627 tests · baseline
141 passed / 6 deselected · boundary corpus 146 · preflight 20/20 · 18/18 protected · five artifact pins
unchanged · both locks closed.

### 10.4.1 WITHDRAWN — the "outcome is not repo-owned" blocker was FALSE

An earlier revision of this section claimed the Arm 0 outcome was not repo-owned, that the first run
could not be hermetic, and that an authorized network fetch was needed to freeze a new snapshot.
**All of that is WRONG and is withdrawn.** I traced `season_total_target()` to
`nfl.load_player_stats(...)`, concluded the outcome was unreachable offline, and never checked whether
the repository already owned a snapshot of that same loader. It does, and it is pinned:

```
fantasy/seasonal_projections/snapshots/player_stats_2011_2025.parquet
sha256  e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344   (VERIFIED on disk)
loader  nflreadpy.load_player_stats · 269,594 rows x 115 cols · seasons 2011-2025
```

`wr_recent_full_game_features_harness.build_panel()` (lines 185-191) already reproduces the production
target from it, **so the OUTCOME path is hermetic and needs no fetch.** That scope is the whole claim:
the four veteran feature buckets are also hermetic, and the three rookie buckets are NOT
activation-ready (§10.4.1a). `OUTCOME_SNAPSHOT`, `OUTCOME_SNAPSHOT_MD5` and the "snapshot does not exist" tests
are removed, and `test_no_outcome_snapshot_constant_survives` fails if any of them come back.

The lesson is the one this project keeps relearning: *I asserted an absence without searching for the
thing I claimed was absent.* A blocker is a claim, and a claim needs the same evidence as a result.

### 10.4.1a THE REAL BLOCKER — three of seven Arm 0 bundles have no feature source

Having withdrawn a false blocker, I then **overcorrected into a false all-clear**: "the first authorized
run is already hermetic" is true of the outcome path and the four veteran buckets, and false of the
full seven-bundle feature path. Arm 0 ships **seven** bundles. I defined the contract as "identity + 32
veteran features", called it the Arm 0 contract, and pinned exactly one bundle
(`rb_veteran_model.pkl`) in a test — so the gap was invisible to the suite.

Measured against `season_dataset_2014_2026.csv` (47 columns):

| bundle | features | present | **missing** |
|---|---|---|---|
| QB/RB/WR/TE veteran (×4) | 32 each | 32 | **0** ✅ |
| `rb_rookie_model.pkl` | 41 | 9 | **32** ❌ |
| `wr_rookie_model.pkl` | 44 | 9 | **35** ❌ |
| `te_rookie_model.pkl` | 44 | 9 | **35** ❌ |

The missing fields are combine, college-box (`cfb_*`) and PFF-derived. Production rebuilds them via
`fantasy/rookie/harness`, which imports `nflreadpy` and calls `load_player_stats`, `load_draft_picks`
and `load_combine` **live**, and reads `fantasy/seasonal_projections/pff/` — **SUPERSEDED count, see §10.5.8: 941 local files, 0
tracked** (`.gitignore:37`). A clean checkout cannot assemble those three buckets at all.

**This is now fail-closed and layered.** `activation_readiness()` returns `False`, naming each blocked
bucket and the counts; `preflight()` stays at 21/21 so the committed v3.9d prefit checkpoint remains
green, and `test_prefit_integrity_and_activation_readiness_are_DIFFERENT_layers` fails if anyone folds
activation readiness into the prefit preflight. The contract is renamed `VETERAN_FEATURE_COLUMNS`,
`SHIPPED_ARM0_BUCKETS` declares all seven with their required input, and every bundle's ordered
`feature_cols` is now pinned — not just one.

**The rookie-source decision is Joseph's and is deliberately UNRESOLVED** (manifest §0b): freeze a
feature-only pinned artifact (my recommendation, conditional on PFF licensing), use an external pinned
artifact, or amend the population to exclude rookies. I wrote no artifact, touched no PFF file, and did
not regenerate the rookie matrix.

### 10.4.1d TWO FALSE CLAIMS ABOUT THE AUTHORIZATION GATE — both WITHDRAWN

**Claim 1, WITHDRAWN: "readiness is a mandatory authorized-real gate ... in the manifest's required
gates and stop conditions."** The manifest contained no such section. It listed 21 preflight checks and
a stop-condition list that never mentioned `activation_readiness()` or `authorized_real_gate()`. The
requirement now exists as manifest §6 (both gates, gate order, and the explicit rule that a
`synthetic_prefit` result can never authorize a real run) and appears in the §7 stop conditions, pinned
by `test_the_manifest_states_the_required_activation_gates` and
`test_the_manifest_lists_readiness_failure_as_a_stop_condition`.

**Claim 2, WITHDRAWN: "fails closed on a malformed preflight."** It did not. Measured before repair,
five inputs FAIL-OPENED — and the second is the serious one:

| input | before | after |
|---|---|---|
| `{"all_ok": True}` — no `run_mode`, `n_checks`, `n_failed`, `checks` | **True** | refused |
| **the REAL `synthetic_prefit` 21/21 result, both locks CLOSED** | **True** | refused |
| `n_checks` absent | **True** | refused |
| one check `ok=False` while `all_ok=True` | **True** | refused |
| `n_failed=0` while `failures` is non-empty | **True** | refused |

The mechanism was truthiness on absent keys: `.get("n_failed")` on a missing key is `None`, which is
falsy, which read as "no failures". The second row is worse than a shape bug — a `synthetic_prefit`
result's entire meaning is that **both locks are shut**, so accepting it as authorization inverted the
lock contract.

`validate_authorized_preflight()` now requires, by identity or equality and never by truthiness: a real
dict · `all_ok is True` · `run_mode == "authorized_real"` · `n_checks` exactly the frozen count ·
`n_failed` exactly integer `0` (with `bool` excluded, since `True` is an `int`) · a `checks` dict with
exactly the expected names, each explicitly `ok` · no non-empty `failures`. The lock contract is carried
*through* that result: only both-locks-open produces `run_mode == "authorized_real"`, and a partial
state is refused by `validate_run_mode` in both directions. Red-before-green tests cover all of it, with
a constructed authorized-shaped preflight plus injected readiness as the positive control — no lock is
opened and the real tree stays blocked.

### 10.4.1e THE GATE'S OWN VOCABULARY WAS CALLER-CONTROLLED, AND MALFORMED INPUT CRASHED IT

Two further defects in the gate that §10.4.1d had just repaired. Measured before this repair:

**1 — the frozen vocabulary was a parameter.** `authorized_real_gate` accepted `expected_checks`, so:

```
authorized_real_gate(
    {"all_ok": True, "run_mode": "authorized_real",
     "n_checks": 0, "n_failed": 0, "failures": 0, "checks": {}},
    expected_checks=())            ->  True   ("0/0 checks and 0 failures")
```

A checker that lets the caller supply the thing being checked against is not a checker. The parameter
is **removed from both the gate and the validator**; validation is against the module literal
`FROZEN_AUTHORIZED_PREFLIGHT_CHECKS` only, pinned by value and in order against the harness's canonical
`PREFLIGHT_CHECKS` by `test_the_frozen_authorization_vocabulary_matches_the_harness`, and
`test_the_gate_exposes_no_parameter_that_can_change_the_vocabulary` inspects the signature so the
parameter cannot come back. Empty / subset / subset-claiming-21 / replaced / extended vocabularies all
refuse.

**2 — malformed nested values raised instead of refusing.** `(checks[c] or {}).get("ok")` calls `.get`
on whatever the caller put there:

| `checks["protected_hashes"]` | before | after |
|---|---|---|
| `True` | **AttributeError** | refused |
| `"ok"` | **AttributeError** | refused |
| `["ok"]` | **AttributeError** | refused |
| `None` | refused | refused |
| `{}` | refused | refused |

A crash is not a refusal — a caller with a broad `except` could read it as neither. Every check entry
must now itself be a dict whose `ok` **is** `True`, and `test_no_adversarial_input_ever_raises_out_of_
the_gate` sweeps a corpus proving nothing propagates.

**3 — `failures` was unvalidated, and the spec I was given did not match the emitter.** Missing,
`None`, `[]` and `False` all passed. The instruction was to require `failures` to be *"exactly integer
0, matching the real preflight output"* — but the real `preflight()` emits
**`failures = {}`, an empty dict**, not an integer. Requiring integer 0 would have rejected the genuine
authorized result. The frozen schema therefore pins what the emitter actually produces: `failures` must
be **present and an empty dict**. `test_the_frozen_failures_schema_matches_what_preflight_actually_
emits` measures it from `preflight()` rather than asserting it, and the positive-control fixture is
type-checked against the real result so a GREEN test cannot pass on a shape the system never produces.

The full frozen schema: `all_ok is True` · `run_mode == "authorized_real"` · `n_checks` exactly integer
21 (bool excluded) · `n_failed` exactly integer 0 (bool excluded) · `failures` present and an empty
dict · `checks` a dict with exactly the 21 frozen names, each value a dict whose `ok` is exactly `True`.
Any missing field refuses.

### 10.4.1c A2 was still evadable four ways

Receiver-name matching missed `import requests as r; r.get(...)`, `from requests import get; get(...)`,
`requests.Session().get(...)` and `client = requests.Session(); client.get(...)` — all returned
`ok=True`. Chasing call shapes means chasing aliasing, and aliasing wins. Since this module needs no
network-capable package, A2 now rejects the **import**: any `Import`/`ImportFrom` whose root is
`requests`, `httpx`, `urllib`, `urllib3`, `aiohttp`, `nflreadpy`, `socket`, `http`, `ftplib`,
`telnetlib` or `webbrowser`. A module that cannot import `requests` cannot call it under any name.
Positive controls keep `dict.get`, `config.get`, an injected `client.get` and non-network imports
legal, and the docstring states the remaining deliberate limits — `importlib`/`__import__` with a
computed name, `eval`/`exec`, an injected network client, and third-party packages that fetch
internally. No theorem over arbitrary Python is claimed.

### 10.4.1b Two further defects in what I built, both found by review

**The authorized feature reader contradicted its own validator.** It returned the whole
`season_dataset_2014_2026.csv` — including the 2026 deploy season and `target_ppg`, `target_games`,
`sample_weight` — while `validate_feature_frame` requires 2014-2025 and rejects exactly those columns.
Nothing caught it because no test ever ran the reader's OUTPUT through the validator; 663 tests passed
over a reader that could not have worked. There is now a frozen feature-column contract (the 8 identity/
routing columns plus the 32 ordered Arm 0 veteran features, read from the production bundles and pinned
by `test_the_frozen_feature_contract_matches_the_production_bundles`), an explicit `usecols` so a
forbidden column is never loaded at all, a 2014-2025 filter applied before returning, and an
end-to-end integration test that drives both authorized readers into `assemble_panel_core`.

**The assembler changed the production target and denominator.** `build_rb_projection.assemble()`
LEFT-joins the weekly target and fills a missing pre-2026 `y` with **0.0** — a rostered player with no
weekly stat row scored zero, which is an observation, not a gap. My assembler *refused* those rows.
It now matches production: every eligible feature row is retained, zero-filled, and labelled
`zero_filled_no_stat_row`, pinned by a production-equivalence test.

**The accounting states were not a partition.** A null `player_id` incremented both `missing_identity`
and `missing_outcome`. The four states are now mutually exclusive by construction —
`missing_identity` → `zero_filled_no_stat_row` → `matched_stat_target` over feature rows, with
`unmatched_outcome_key` counted over the *outcome* denominator — and the sum is asserted to equal the
feature-row count.

**One more over-broad matcher, caught by my own positive control.** Adding `get` to the banned callees
to catch `requests.get` also rejected `dict.get` in this very module — the same defect as
`config.putenv()` failing C7. Network methods are now receiver-aware, with a positive control proving
`d.get('k')` stays legal.

### 10.4.2 The door is UNCHANGED, deliberately

`assemble_real_panel()` is still one undecorated module-level `def` whose body is exactly
`require_real_fit_authorization()` then `raise NotImplementedError(...)`. C5 is untouched, all 15
`c5-rebind-*` and 5 `c5-body-*` corpus cases are untouched, and the 41/65 → 0/65 red/green arithmetic is
unchanged. The assembly logic was built as a **separate, fully tested module** rather than by opening the
door, so this pass adds capability without spending the seal. Activation remains a single documented
change, specified in the manifest §1–§2 including the mode-aware C5-S/C5-A replacement and a row-by-row
list of every protection that changes and what replaces it. **Nothing was retired or weakened.**

### 10.4.3 What was built

`coaching/assemble_real_panel_v39.py` — the join, validation and accounting, under its own contract
**A1–A6** (no import-time I/O; no live loader; every reader injected and default-closed; no fitting; the
outcome column is in the forbidden-in-features set; the default readers refuse). It lives outside
`V39_SOURCE_MODULES` because assembly code must name outcome columns, which C4 forbids in the harness —
so C4 stays absolute for the module it protects instead of being weakened. A1–A6 is enforced at runtime
as the **21st preflight check**, `assembly_module_contract`.

Design choices worth stating: features and outcomes are returned as **separate objects**, so no object
exists that a model could be handed carrying both X and y; a missing outcome **refuses** rather than
silently inner-joining, because a silent inner join is denominator drift; and the three unmatched
reasons — `missing_outcome`, `missing_identity`, `unmatched_player` — are counted separately rather than
collapsed into one number.

**36 new tests** cover both locks closed, each partial lock state, `authorized_real` with both open,
unknown modes, import-time reads, authorization-before-reader, duplicate keys, missing/extra seasons,
unmatched accounting, every legacy target rejected from the feature frame, schema drift, denominator
drift, Design B unselectable, and a mocked reader proven not to run in `synthetic_prefit`. Two are
red-before-green: `test_no_module_level_reader_call_exists` proves the A1 check fires on a module-level
read before showing canon clean, and `test_the_outcome_reader_refuses_until_the_snapshot_is_pinned`
proves the outcome path is closed.

### 10.4.4 What was NOT done

No lock opened · no real fantasy outcome read, inspected, printed, aggregated or compared · no model fit ·
no result artifact written · no production file touched. **The rookie-matrix line in this paragraph is
SUPERSEDED by §10.5**: Joseph selected Option A on 2026-08-03, the derived matrix was generated, and
the private PFF directory was read under that authorization. Everything else in this paragraph still
holds. The two authorized readers are exercised only against temporary synthetic files written by the
tests themselves; the real weekly snapshot and feature source are verified by **hash and manifest
metadata only**, never by reading a value.

---

## 10.5 v3.9n — OPTION A: THE FROZEN ROOKIE FEATURE MATRIX

**Authorization used.** Joseph selected Option A (§10.4.1a / manifest §0b) and confirmed he is
authorized to use and commit PFF-*derived* feature values, with the raw PFF files remaining private and
untracked. That is the only new authorization exercised in this pass. **Both real-fit locks stayed
closed, no fantasy outcome was read, nothing was fit, nothing was activated, and no commit was made.**

> **§10.5 DESCRIBES A SUPERSEDED ARTIFACT.** Everything below was true of the v1 matrix as built, but
> that matrix was found on the same day to be **temporally contaminated** through the production PFF
> join and has been replaced. Read **§10.6** for the defect, the repair and the current artifact. The
> Option A authorization, the population, the null semantics, the determinism method and the licensing
> posture all carry over unchanged; the sha256, the column count and the readiness verdict do not.

### 10.5.1 The artifact

```
fantasy/seasonal_projections/snapshots/rookie_arm0_features_2014_2025.parquet
sha256    4b4655abde1c63d6316db2277d2a5301360842c9cec94fea0c2c5d77f5252584   <-- INVALID, see §10.6
shape     1,263 rows x 59 columns
keys      (player_id, season) - unique, no nulls
seasons   2014-2025, all twelve present
positions RB 387 · WR 584 · TE 292   (387+584+292 = 1,263)
generator fantasy/seasonal_projections/build_rookie_arm0_features.py
manifest  snapshots/manifest.json, key `rookie_arm0_features_2014_2025`
```

59 = 5 identity/routing keys (`player_id`, `season`, `position`, `is_rookie`, `norm_name`) + the
**54-column union** of the three rookie bundle pools (RB 41, WR 44, TE 44; WR and TE are
byte-identical), pinned in a fixed order: RB's pool in bundle order, then WR's 13 additional features
in WR bundle order.

### 10.5.2 Production logic, not a parallel implementation

The generator imports `fantasy/rookie/harness/assemble_features.py` and calls the **real**
`build_features()`. Only the two network-backed nflverse loaders are injected — `nfl.load_draft_picks`
and `nfl.load_combine` are replaced by readers over the pinned local snapshots
(`snapshots/draft_picks.parquet`, `snapshots/combine.parquet`). `_load_pff` is left untouched and reads
the authorized private directory. No feature formula is reimplemented anywhere in the generator or in
its tests.

### 10.5.3 What it does not contain, enforced three ways

No fantasy outcome, target, label, sample weight, ADP, market projection or target-season realized
statistic:

1. the generator refuses to write if any column name matches a forbidden token;
2. `verify_rookie_matrix_provenance()` refuses to load a file whose schema intersects
   `FORBIDDEN_IN_FEATURES`;
3. a parametrized test injects **every** name in `FORBIDDEN_IN_FEATURES` in turn and asserts refusal,
   and a second parametrized test scans column names for 13 outcome/market tokens.

**A self-caught defect in my own guard.** The generator's first forbidden-token list used the bare
substrings `_y` and `ppg`, which flagged **10 legitimate college columns** (`cfb_rec_ypg`,
`cfb_career_scrim_yds`, …) and aborted the build. The tokens were made precise and split into
substring and exact-name sets. An over-broad matcher that blocks real work is the same defect class as
one that lets real leakage through; it is recorded rather than quietly fixed.

### 10.5.4 Null semantics are production's

A player without a combine row, without a PFF row, or without a college-box row keeps that row with
nulls. No proxy substitution, no imputation, no row dropped for being incompletely measured, and the
frozen population is not amended. Measured non-null coverage by source group:

```
draft     4 cols   mean non-null  54.7%
combine   8 cols   mean non-null  37.2%
college  13 cols   mean non-null  45.0%
pff      21 cols   mean non-null  42.8%
landing   6 cols   mean non-null  66.5%
(bmi and speed_score are derived, in no source group: 4+8+13+21+6 = 52 of the 54 features)

rows with ANY null: 1,263 of 1,263 - every one RETAINED
```

### 10.5.5 Determinism

Rows sorted by `(season, player_id)` with a stable mergesort; fixed dtypes (identity as `string`,
`season` int32, `is_rookie` int8, all 54 features float64); `to_parquet(index=False,
engine="pyarrow", compression="snappy")`. **Two fresh rebuilds into a temp directory reproduced the
sha256 above byte-for-byte.**

### 10.5.6 Integration and the two-layer gate

`assemble_real_panel_v39.py` gained `ROOKIE_MATRIX*` pins (path, sha256, manifest key, generator, rows,
cols, positions, identity, and the **59-name ordered schema literal**, pinned independently of the
generator), plus `verify_rookie_matrix_provenance()`, `rookie_matrix_columns()`,
`authorized_rookie_matrix_reader()`, `validate_rookie_matrix()`, `bundle_feature_cols()` and
`rookie_bucket_frame()`. A5 now checks the rookie pins for self-consistency and A6 requires a
`default_rookie_matrix_reader` that refuses. `ParquetFile` was added to `ASSEMBLY_READER_CALLEES`, so
A1/A3 still forbid module-level reads.

Measured state after integration:

```
all seven Arm 0 buckets     complete, 0 features missing from their declared source
activation_readiness()      True     (SUPERSEDED — False again as of §10.6)
preflight()                 21/21, all_ok True, run_mode synthetic_prefit
authorized_real_gate()      False    - refused at gate 1: a synthetic_prefit result asserts
                                       BOTH LOCKS CLOSED and can never authorize a real run
REAL_FIT_AUTHORIZED         False
env lock                    unset
assemble_real_panel()       still sealed (two statements: authorization check, then raise)
```

**Readiness moved; the refusal did not weaken — it moved from gate 2 to gate 1.** Gate 2's refusal path
is kept live by injection (`rookie_columns=set()`) rather than by observation, so the fail-closed
behaviour that v3.9g added does not silently stop being tested now that the real tree passes it.

### 10.5.7 A vacuous check I wrote and then replaced

The first version of `validate_rookie_matrix()` asserted `matrix[list(fc)].columns != fc` for each
rookie bundle. **That can never fail** — selecting columns by name always returns them in that name
order — so it was a check that always said yes.

The replacement is honest about what is and is not enforceable. The matrix is a **shared** pool, and RB
and WR order their common features differently, so no single physical column order can equal all three
bundle orders at once (measured: RB inverts at `coach_changed`; WR/TE at `cfb_rec_pg`). Therefore:

- **storage order** is pinned by the `ROOKIE_MATRIX_COLUMNS` literal and by the file hash;
- **feed order** — the order a model would actually receive — is enforced at the point of use, by
  `rookie_bucket_frame()` → `bucket_frame_satisfies_bundle()`, and a test shuffles a bucket frame's
  columns and asserts refusal;
- a test measures the RB/WR/TE order conflict rather than asserting it, so if the pools ever became
  mutually consistent the weaker contract would be revisited.

### 10.5.8 Licensing posture, verified

`fantasy/seasonal_projections/pff/` holds **941 local files (409 of them CSVs)** and `git ls-files` returns **zero** of them
(`.gitignore:37`). Only derived feature values are repo-owned. A test asserts that tracked count is
still zero and that derived `pff_*` values survived into the matrix. Regenerating the matrix still
requires the authorized private directory, so *rebuilding* it is not a clean-checkout operation even
though *using* it now is.

### 10.5.9 Tests and counts

`tests/test_rookie_matrix_v39.py` — **91** tests: schema/hash/manifest agreement, the frozen
population, null preservation, forbidden-column rejection (parametrized over every forbidden name), a
flipped byte, an absent file, reordered / renamed / added / dropped columns, row loss at both file and
frame level, duplicate and null keys, a missing season, an out-of-range season, a foreign position, a
non-rookie row, seven manifest-field disagreements, bundle-order enforcement on the bucket frame, the
default reader refusing, the reader running its own output through its own validator, readiness True,
readiness failing closed on a missing file and on a hash mismatch, the gate still refusing, and the
four non-PFF input pins with a RED case proving a drifted input is refused, and a MEASURED PFF
local-file count that fails if a document quotes a superseded figure.

Two tests in `test_assemble_real_panel_v39.py` were **split** rather than relaxed: the missingness and
readiness properties now have a live case (the real, ready tree) and an injected fail-closed case.
`test_combine_snapshot_provenance.py::test_the_snapshot_does_not_make_activation_ready` was renamed to
`..._alone_does_not_make_activation_ready` and now proves the combine snapshot *by itself* supplies
nothing to the rookie bundles. **No test was deleted or weakened.**

Recomputed, collected rather than estimated: **929 collected · 928 mandatory · 1 optional**; inherited
baseline **141 passed, 6 deselected** (unchanged). The baseline command in §1.1 gained one `--ignore`
for the new module.

### 10.5.10 What was NOT done in v3.9n

No lock opened · no fantasy outcome read, inspected, printed, aggregated or compared · no model fit ·
no activation · no result artifact written · no production model, projection, dashboard, betting,
market or draft-board file touched · no commit, no staging. The 18 protected artifacts and the five
v3.9 artifacts are byte-identical to their pins.


---

## 10.6 v3.9o — MATERIAL LEAKAGE: the production PFF join was not point-in-time

**Found by Codex, reproduced here, repaired at the production source. The v1 rookie matrix (§10.5) is
INVALID and has been replaced.** No lock was opened, no outcome was read, nothing was fit, nothing was
retrained, nothing was committed.

### 10.6.1 The defect

`fantasy/rookie/harness/assemble_features.py::_load_pff` did:

```python
idx = alld.groupby("norm_name")["season"].idxmax()      # FINAL college season row
fin = alld.loc[idx, ["norm_name"] + keep]
...
p = p.merge(recv, on="norm_name", how="left")           # season already gone
```

It selected the **latest PFF college season in 2014-2025 for a name** and merged on the name alone. The
source season never reached the join, so nothing prevented a later college player from supplying
features to an earlier NFL rookie.

### 10.6.2 Reproduced, and enumerated

Measured against the frozen 1,263-row rookie population:

| block | matches | source season >= NFL rookie season |
|---|---|---|
| receiving | **963** | **20** |
| rushing, whole panel | 724 | 17 |
| rushing, RB rows only (the bundle that consumes it) | **308** | **8** |

The two rushing rows are the same measurement over different denominators — Codex reported the RB-only
view, this report gives both, and they agree.

- **28** leaked `(row, kind)` pairs over **22 unique rookie player-seasons** — WR 10, RB 9, TE 3.
- **292** contaminated non-null feature cells in the shipped v1 artifact.
- Leaked source seasons ran 2014-2025; affected rookie seasons ran 2014-2024.
- Named examples confirmed exactly: 2014 Mike Evans took **2021** receiving; 2016 Michael Thomas took
  **2025** receiving; 2015 Matt Jones took **2025** receiving *and* rushing.

**Same-person mistiming vs same-name collision, separated.** Of the 37 leaked pairs measured at join
level, **21** have a `norm_name` mapping to more than one PFF `player_id` — true identity collisions.
Classified by recoverability:

| class | receiving | rushing | meaning |
|---|---|---|---|
| **A — recoverable** | 14 | 7 | an eligible earlier season existed; `idxmax` picked a later one |
| **B — unrecoverable** | 6 | 10 | no PFF season precedes the rookie season, so the match could never have been this player |

Every 2014-class case is Class B: the PFF college summary library **begins at 2014** (the 2008-2013
directories exist but contain no receiving/rushing/passing summaries), and a 2014 NFL rookie's final
college season is 2013.

### 10.6.3 Bundle-training provenance — ESTABLISHED, not unknown

Read from the generating code, not from bundle metadata:

```
build_rb_projection.frozen_rb_matrix()      (and the WR/TE twins in build_wr_/build_te_projection.py)
  -> shutil.copy2(HARNESS/"assemble_features.py", scratch)
  -> subprocess.run([sys.executable, "assemble_features.py"])
  -> pd.read_parquet(scratch/"feat_hit.parquet")   -> trains {rb,wr,te}_rookie_model.pkl
```

All three builders copy and **execute the same `assemble_features.py`**. The shipped rookie bundles
were therefore fit on the contaminated join. This is proven, not inferred; the answer is not UNKNOWN.

**The INFERENCE drawn from this fact in §10.6.7 is WITHDRAWN (see §10.7):** the experiment never uses a
bundle's fitted weights, so what those bundles were historically fit on cannot reach a result. The fact
above stands; the activation conclusion drawn from it did not.

### 10.6.4 The repair — one shared production implementation

`_load_pff` is gone. `_pff_long` retains the source season; `_pff_point_in_time` selects it. The frozen
rule, in order:

1. eligible = rows for the name with `pff_season < reference_season`. A row at or after the reference
   season is **never** eligible.
2. no eligible row -> NULL.
3. one PFF identity -> that identity's **latest eligible** season.
4. several identities -> disambiguate by (a) position compatibility, then (b) presence in
   `reference_season - 1`; if neither is decisive -> **NULL**.
5. ties: latest season, then most college games, then lowest PFF player id.

`build_features` now **raises** on a panel with no reference-season column (`entry_year` or `season`)
instead of silently joining without one, and asserts after the join that no attached source season
reaches the reference season. The matrix generator calls this same production function; a test asserts
the generator contains no PFF join of its own.

**A school-based disambiguator was considered and rejected.** PFF `team_name` and combine `school`
share only 69 of 126 values ("APP STATE" vs "Appalachian St."), so matching them would be a fuzzy guess
presented as identity evidence — the same error class as the leak. The conservative NULL is kept and
its cost is measured below.

**A defect in my own repair, caught by my own test:** when every candidate was an unresolvable
collision, `pd.concat([])` raised `ValueError` instead of returning "no PFF block for this row". Fixed;
the empty case is now the normal outcome it should always have been.

### 10.6.5 Provenance fingerprint of the private inputs

The build consumes **36** files — the receiving/rushing/passing college summaries for 2014-2025 — not
the 941 files in the local library. `pff_provenance()` computes one SHA-256 over, per file in sorted
relative-path order, the path bytes then the file bytes:

```
sha256   148e2465abb6389cdd4e741dee21f0d168638f91dc23f66407950d2fbd718038
n_files  36 | kinds passing, receiving, rushing | seasons 2014-2025
```

Verified **before** any value is read (`verify_pff_inputs`) and **again after** the build. Recorded in
the generator and in the snapshot manifest under `pff_consumed`. No PFF value is exposed: the manifest
carries a digest, a file count, kinds and seasons only, and a test asserts the recorded block contains
no player data.

### 10.6.6 The regenerated artifact, and the old-vs-new difference

```
sha256    7625980495886141efd65fb9c65862ef7f3cf8af67e50f231c6c3c12d9f45385
shape     1,263 x 61   (59 + pff_receiving_source_season + pff_rushing_source_season)
seasons   2014-2025 | RB 387 | WR 584 | TE 292 | keys unique | two rebuilds byte-identical
```

The two new columns are provenance, not features; they are in no bundle pool and make the guarantee
checkable **from the artifact alone**, without the private library.

Old vs new, same 1,263 rows, keys identical, **no outcome consulted**:

```
33 non-PFF feature columns              byte-identical
PFF non-null cells        11,343 -> 11,231      (4 gained | 116 lost | 181 changed)
rookie player-seasons with any PFF change          22   (WR 10 | RB 9 | TE 3)
of 38 changed (row, kind) pairs:  28 temporal leaks
                                   1 same-name identity collision - jonathan williams, an NFL RB
                                     who was being handed a college WR's row (id 21322 over 10790)
                                   9 unchanged for that block (the row changed in the other block)
source-season lag, new artifact:  receiving min 1 | rushing min 1 | zero rows with lag < 1
                                  receiving {1:807, 2:95, 3:37, 4:12, 6:4, 7:2}
```

**Cost of the conservative identity rule, stated rather than buried:** 3 rushing blocks become NULL
because two same-name, same-position players both appear in the eligible window — `matt jones` 2015,
`tyree jackson` 2021, `zach evans` 2023.

### 10.6.7 ACTIVATION — readiness returns to False  **[WITHDRAWN — superseded by §10.7]**

> **THIS SUBSECTION IS WITHDRAWN.** Its premise — that a bundle trained on contaminated features is
> unusable here — is false: `fit_predict` builds a fresh estimator every fold and the serialized object
> is never fitted or predicted from. Readiness is **True**. Kept for the record; read §10.7.

Per the activation rule as I then understood it: the shipped rookie bundles were proven to have been
trained on the contaminated join, so readiness must remain False and name the blocker.

```
rookie features        COMPLETE and point-in-time   (features_available = True)
rookie bundles         TRAINED ON THE LEAKED JOIN   (training_contract_ok = False)
activation_readiness() False  -> ROOKIE_BUNDLE_TRAINING_BLOCKER
preflight()            21/21, all_ok True, run_mode synthetic_prefit
authorized_real_gate() False  -> BOTH gates refuse (gate 1 synthetic_prefit, gate 2 the blocker)
REAL_FIT_AUTHORIZED    False | env lock unset | assemble_real_panel() sealed
```

`arm0_bucket_table()` now separates **feature availability** from **training compatibility**; conflating
them is what would have let a corrected-features / contaminated-model run look ready. A GREEN control
test clears `CONTAMINATED_TRAINED_BUCKETS` in memory and shows readiness would be True, so the check is
not hard-wired to fail. **Nothing was retrained. Retraining is Joseph's decision.**

**A production consequence Joseph should know:** `assemble_features.py` is shared, so the next run of
`build_rb_projection.py` / `build_wr_projection.py` / `build_te_projection.py` will fit the rookie arms
on point-in-time features and produce **different** bundles. No bundle was regenerated in this pass;
all 18 protected artifacts and the 8 production models are byte-identical to their pins.

### 10.6.8 Tests

`tests/test_pff_point_in_time_v39.py` — **37** tests, red-before-green throughout. The retired rule is
reproduced in the test module (never in production) so each measured leak has a RED side: three
parametrized cases assert the retired rule selects 2021 / 2025 / 2025 and that each IS a leak, and the
matching GREEN cases assert the shipped rule returns NULL / 2015 / 2014. Also covered: the exact
strictly-less-than season boundary (source 2017 -> 2017, source 2018 -> NULL, source 2019 -> NULL, for
a 2018 rookie), no eligible prior season, multiple eligible seasons, a later same-name player never
matching, a collision resolved by position, a collision resolved by the immediately-prior season, an
unresolvable collision yielding NULL, an unambiguous name surviving a position disagreement,
determinism under input reordering, the retired collapse being absent from production, `build_features`
refusing a panel with no reference season, the generator not owning a copy of the join, and — read from
the repo-owned artifact with no private data — every measured example corrected, no row drawing from
its own season or later, and every PFF block having a recorded source season.

### 10.6.9 What was NOT done

No lock opened | no fantasy outcome read, inspected, printed, aggregated or compared | no model fit |
**no bundle retrained** | no activation | no result artifact written | no production model, projection,
dashboard, betting, market or draft-board file touched | no commit, no staging.


---

## 10.7 v3.9p — THE BUNDLE-TRAINING BLOCKER IS WITHDRAWN. ARM 0 refits from scratch.

**§10.6.3 and §10.6.7 drew a wrong conclusion from a right observation, and this section withdraws it.**
The observation stands: the shipped rookie bundles were historically fit on the contaminated PFF join.
The conclusion — that this makes them unusable and readiness must stay `False` — was **FALSE**, because
this experiment never uses a bundle's fitted weights.

### 10.7.1 What I got wrong, and how I checked it this time

I reasoned that a model fit on contaminated features "still encodes what the contaminated features
taught it". That is true of the artifact and irrelevant to the experiment, because the experiment does
not predict from the artifact. Codex traced it; I then read the harness rather than taking the trace on
assertion. Four findings, each verified in source:

| claim | verified where |
|---|---|
| `arm0_definition()` returns metadata only | line 286 is its ONLY touch of `bundle["model"]`, and it reads `type(...)` to build a class-name **string** |
| `fit_predict()` builds a fresh estimator | line 500: `m = RB._make_model(spec["family"], spec["params"])`; line 501 fits `m`; line 502 predicts from `m` |
| every fold refits from scratch | `fit_predict` is called per inner and per outer fold; no estimator is cached or passed forward |
| the fitted object never reaches a prediction | `bundle["model"]` appears nowhere in `fit_predict`; `inner_cv_mae` is recorded as metadata and never used for selection |

### 10.7.2 The proof that is now permanent

`tests/test_arm0_refits_from_scratch_v39.py` — **38** tests. The decisive one,
`test_POISONING_the_stored_estimator_cannot_change_a_single_prediction`, writes a temp models directory
whose every bundle carries an `ExplodingEstimator` — an object that raises on ANY attribute access or
call — then runs the full nested pipeline twice, canonical and poisoned, and asserts the metrics and
selection frames are **exactly equal** (`atol=0, rtol=0`). A prediction sourced from the stored object
would detonate; stale state would diverge. Neither happens.

Three guards keep that from passing vacuously: `test_the_sentinel_really_does_explode` proves the
sentinel is unusable; `test_arm0_definition_survives_a_poisoned_estimator` proves the poisoned bundles
are the ones being read; and the poisoning test itself asserts `model_class` ends with
`ExplodingEstimator` before it runs. Canonical bundles are never touched.

Also pinned: an AST test that `bundle["model"]` appears in `arm0_definition` **only inside `type(...)`**;
that `fit_predict` names no `"model"` key and does call `_make_model`; that two `fit_predict` calls
construct two distinct estimator instances and return identical predictions; and that the frame handed
to `.fit` is the fold's own.

### 10.7.3 What the experiment DOES inherit — now pinned by value

The bundle contributes a **specification**, not a model: `feature_cols` (order included), `family`,
`params`, `median_impute`, `seed`, `target`. `tests/arm0_bundle_pins.py` gains `BUNDLE_SPEC_PINS` — seven
independent literals checked against disk, with a RED control proving a mutated pin cannot pass.
`arm0_bucket_table()` reports `spec_contract_ok` (and `spec_problems`) in place of the withdrawn
`training_contract_ok`; `bundle_spec_problems()` is its implementation, with a parametrized RED test
removing each spec field in turn.

### 10.7.4 The limitation that IS real — disclosed, not gated

The fixed hyperparameters (`family`, `params`, `median_impute`, `seed`) were selected under the
historical production pipeline, which used the pre-repair join. They are **frozen pre-experiment and
applied identically to ARM_0 and to every coaching arm**, and the experiment does not retune them.

That is a limitation of the comparison's absolute level, not a leakage path into the arm contrast: a
hyperparameter common to every arm cannot differentially favour one. It is recorded in
`FROZEN_HYPERPARAMETER_DISCLOSURE`, stated in manifest §0d, and deliberately **not** an activation gate.
Retuning under the corrected features would be a different, retrospectively-specified experiment.

### 10.7.5 State after the withdrawal

```
all seven buckets      features_available True | spec_contract_ok True | complete True
activation_readiness() TRUE   ("all 7 shipped Arm 0 buckets have a complete pinned feature source")
preflight()            21/21, all_ok True, run_mode synthetic_prefit
authorized_real_gate() FALSE  -- gate 1 ONLY: run_mode is synthetic_prefit and BOTH LOCKS CLOSED.
                              A test asserts the refusal text contains no "gate 2".
REAL_FIT_AUTHORIZED    False | env lock unset | assemble_real_panel() sealed
```

The corrected point-in-time matrix is preserved unchanged — sha256 `7625980495…`, 1,263x61 — as is the
aggregate digest `148e2465…` over exactly the 36 consumed private PFF files. Nothing was retrained; all
18 protected artifacts and the 8 production model bundles are byte-identical to their pins.

### 10.7.6 What was NOT done

No lock opened | no fantasy outcome read, inspected, printed, aggregated or compared | no model fit
against a real target | **no bundle retrained or modified** | no activation | no result artifact
written | no production model, projection, dashboard, betting, market or draft-board file touched |
no commit, no staging.


---

## 10.9 v3.9q — THE ACTIVATION WIRING IS BUILT. Still not executed.

The entry point is no longer a `raise`. It is implemented under the preregistered **C5-A** contract,
and the seal has **moved rather than weakened**. Both locks remain closed, no real outcome was read,
nothing was fit, and no result artifact exists.

### 10.9.1 C5 is now mode-aware

`_entry_point_is_sealed(tree, contract_mode)` dispatches on a new module constant,
`ENTRY_POINT_CONTRACT_MODE`. Both variants first demand the same structural guarantee — the entry point
is bound exactly once, at module level, by one undecorated `def`, so a rebinding or a decorator is
refused in either mode.

```
C5-S  synthetic_prefit   body is exactly 2 statements: zero-arg require_real_fit_authorization(),
                         then an unconditional raise NotImplementedError.
C5-A  authorized_real    1. statement 1 is a zero-arg require_real_fit_authorization()
                         2. statement 2 calls require_preflight_clearance(...)
                         3. NO reader callee anywhere in the body
                         4. NO banned outcome callee anywhere in the body
                         5. the last statement returns assemble_panel_core(...) and nothing else
                         6. no statement precedes 1
```

`ENTRY_POINT_CONTRACT_MODE = authorized_real` is the live declaration. It says only what SHAPE the door
has in the file. **It is not a run mode and not a lock**: `DEFAULT_RUN_MODE` is still
`synthetic_prefit`, `REAL_FIT_AUTHORIZED` is still `False`, and the environment lock is unset. Which
contract applies is declared explicitly and is never inferred from the lock state — the lock state is
the thing the contract protects.

### 10.9.2 Where the seal went

Clause 3 is what makes an implemented door safe: **the module contains no reader callee at all**, so it
physically cannot read a file by itself. The readers arrive as parameters and are called only in
statement 3, after clearance has returned. So with the locks shut, statement 1 raises and neither
injected reader is ever touched.

That is asserted directly, not argued: `test_with_the_locks_CLOSED_the_door_refuses_and_no_reader_is_called`
passes tripwire readers that record every call and raise if invoked, and checks `calls == []`. The same
tripwire assertion covers all three partial/closed lock states and a `synthetic_prefit` run mode with
both locks open. **This is the complete prohibition on real readers in `synthetic_prefit`, preserved.**

### 10.9.3 What `require_preflight_clearance` enforces, in order

0. run mode is `authorized_real` — a `synthetic_prefit` run may not reach a reader;
1. BOTH locks open, re-checked here rather than trusted from statement 1;
2. `preflight()` 21/21 **in `authorized_real` mode**;
3. `activation_readiness()` True;
4. `authorized_real_gate()` True — checked explicitly even though it re-derives 2 and 3, because the
   gate itself must have run before either reader;
5. every pinned input verified by `verify_pinned_activation_inputs()` — veteran features (md5), rookie
   matrix (sha256 + manifest + exact 61-column schema), weekly outcome snapshot (sha256 + manifest
   loader/rows/cols). The five coaching artifacts are covered by step 2's `v39_artifacts_pinned`.

It returns the preflight result it cleared, so a caller cannot substitute a different one afterwards.
A test proves the ordering is real: with the gate blocked, input verification is never reached.

### 10.9.4 The panel path

`return assemble_panel_core(feature_reader(), outcome_reader())` — the same already-tested core, with
production's LEFT-join zero-fill and the mutually exclusive accounting partition. A test asserts the
door's output is byte-equal to calling `assemble_panel_core` directly on the same frames, and a second
asserts the zero-filled state and accounting totals survive the door. Design B stays oracle and
unselectable; a test confirms the door introduced no `coach_b` path.

Everything in this subsection is exercised against **synthetic frames and temp files written by the
tests**. The canonical weekly snapshot is never opened — a self-scan test proves this module names it
in no executable string, with the needle assembled at runtime so the scan cannot match itself.

### 10.9.5 The boundary corpus, and a measurement that had to be re-based

Ten **C5A** injections were added: missing clearance, a reader callee in the body, a banned outcome
callee, returning something other than `assemble_panel_core(...)`, a statement before the
authorization, clearance before authorization, authorization with arguments, a renamed clearance, a
decorated door, and an extra statement. All ten are caught by the live validator.

**The historical arm had to be re-based, and this is worth stating plainly.** The vendored `a5b4af7`
validator's C5 clause only knows C5-S. Judging today's source with it flags the door itself, which
makes every *other* injection look "caught" for a reason unrelated to the clause under test — measured,
the historical figure collapses from **41 to 5**. The historical arm therefore reverts ONLY the entry
point to C5-S (`boundary_corpus.historical_pure_sources()`); every other clause is still exercised
against the live module body. The operative safety number, **0 undetected now**, is measured against
the LIVE source, unmodified. Totals move from 41/65 → **41/75** and 0/65 → **0/75**.

### 10.9.6 ⚠ A PINNED PRODUCTION INPUT DRIFTED MID-PASS  **[SCOPE CORRECTED — see §10.10]**

While this pass was running, a **concurrent session modified a tracked production input**:

```
fantasy/seasonal_projections/season_dataset_2014_2026.csv
pinned md5   8322a59e43251820cb393d40787f60e6
current md5  71bad6a2d6af122b5f24ce1f03d486b9        (mtime 2026-08-03 18:23)
same header, same 8,273 data rows, 1,572 lines changed in place
```

> **TWO CLAIMS IN THIS SUBSECTION ARE WITHDRAWN (§10.10).** "1,572 changed rows" was `git --numstat`
> LINE arithmetic, not a row count — the semantic figure is **916 rows, all season 2026**. And calling
> the ten columns "inside the veteran feature contract" was true of column membership but misleading
> about impact: nine differed only by float round-trip noise (max 3.5527e-15) and all ten were
> 2026-only. **No 2014-2025 value changed.** The refusal was still correct; the PIN was at the wrong
> scope, and §10.10 fixes that.

**All ten changed columns are INSIDE the Arm 0 veteran feature contract** — `prior_ppg`, `ppg_2yr`,
`ppg_trend`, `career_high_ppg`, `prior_targets_pg`, `prior_ypc`, `prior_rec_epa`, `prior_rush_epa`,
`age`, `qb_changed`. **None** is a market or ADP column. `player_id`, `season`, `position` and
`is_rookie` are unchanged, so the frozen rookie population is intact, and **0 of the 1,263 frozen
rookie-matrix rows** are touched by the `qb_changed` drift (916 rows changed dataset-wide, none of them
in the matrix).

**I did not write this file, I have not reverted it, and I have NOT re-pinned to the new md5.**
Re-pinning would silently absorb an unreviewed change to the experiment's feature inputs. The fail-
closed machinery is working exactly as designed: `verify_pinned_activation_inputs()` refuses, so an
authorized run cannot start, and **four** tests are RED on purpose. Every one of them cites the same
md5 mismatch and nothing else:

```
test_activation_wiring_v39.py::test_clearance_reaches_and_ENFORCES_the_input_pins
test_activation_wiring_v39.py::test_all_four_pinned_input_families_are_verified_before_reading
test_assemble_real_panel_v39.py::test_the_feature_source_matches_the_production_pin
test_rookie_matrix_v39.py::test_every_non_pff_input_is_pinned_and_currently_matches
```

(An earlier draft of this section said **two**; that was written before the two new wiring tests were
added and is corrected here. The count is four.)

**RESOLVED in §10.10, and NOT by re-pinning or reverting.** The consumed 2014-2025 window is now an
immutable feature-only snapshot, and the experiment reads that instead of the mutable CSV. The 2026 QB
work was left exactly as the concurrent session wrote it. The clause above about the "veteran feature
VALUES" having moved is **withdrawn**: they did not, and the rookie matrix did not need rebuilding
(it rebuilds byte-identical from the snapshot).

### 10.9.7 State at the stop

```
ENTRY_POINT_CONTRACT_MODE  authorized_real   (the SHAPE of the door; not a lock, not a run mode)
DEFAULT_RUN_MODE           synthetic_prefit
preflight()                21/21, all_ok True, run_mode synthetic_prefit
activation_readiness()     TRUE
authorized_real_gate()     FALSE — gate 1 only: run_mode is synthetic_prefit, BOTH LOCKS CLOSED.
                           A test asserts the refusal text contains no "gate 2".
REAL_FIT_AUTHORIZED        False | env lock unset
readers reached            NONE — proven with tripwires, in every closed/partial lock state
18/18 protected · 8 production models · 5 v3.9 artifacts   byte-identical
```

### 10.9.8 What was NOT done

No lock opened | no real fantasy outcome read, inspected, printed, aggregated or compared | no model
fit against a real target | no bundle retrained or modified | **no real run executed** | no result
artifact written | no production model, projection, dashboard, betting, market or draft-board file
touched | **the drifted season dataset was neither reverted nor re-pinned** | no commit, no staging.


---

## 10.10 v3.9r — THE VETERAN INPUT IS RE-SCOPED. §10.9.6 was too broad, and is corrected here.

**§10.9.6 called the season-dataset change a blocker whose ten changed columns were "inside the Arm 0
veteran feature contract", and quoted "1,572 changed rows". Both framings are WITHDRAWN.** The
underlying refusal was correct — a pinned input had moved — but the pin was at the wrong scope and my
description of the change overstated it. Reproduced independently before any edit:

| claim | measured |
|---|---|
| `season_dataset_2014_2026.pre_qbchanged.csv` md5 | **`8322a59e43251820cb393d40787f60e6`** — exactly the value that was pinned |
| where the two files differ | **season 2026 only**, every difference |
| nine non-`qb_changed` columns | CSV float round-trip noise, **max |diff| 3.5527e-15**, zero null-status flips |
| the one substantive change | **`qb_changed` on 916 rows of season 2026**: NaN → 717 zeros, 199 ones |
| any 2014-2025 value differing | **NONE**, bitwise, across all 47 columns; the consumed 40-column block is exactly equal |
| "1,572 changed rows" | **`git diff --numstat` line arithmetic** (1572 added / 1572 deleted), not a row count. The semantic figure is **916 rows, all season 2026.** |

So the experiment-consumed data never moved. The failure was a **scope error of mine**: pinning a
mutable 2014-2026 production file in order to protect an immutable 2014-2025 window. Refreshing the
deploy season is normal and must not gate activation.

### 10.10.1 The frozen veteran snapshot

```
fantasy/seasonal_projections/snapshots/veteran_arm0_features_2014_2025.parquet
sha256    45cb2583acf7d046ecf54275d1ee3e70fcb9e4882d69a6b203e36350376bfbc8
shape     7,350 rows x 40 columns   keys (player_id, season) unique   seasons 2014-2025
generator fantasy/seasonal_projections/build_veteran_arm0_snapshot.py
manifest  snapshots/manifest.json, key `veteran_arm0_features_2014_2025`
```

**Derived, not invented.** The generator reads the schema and window from the LIVE contracts at build
time — `VETERAN_FEATURE_COLUMNS` (`IDENTITY_COLUMNS` + the 32 `ARM0_VETERAN_FEATURES`) and
`ALL_PANEL_SEASONS` — and cross-checks the 32 features against the four shipped veteran bundles' own
`feature_cols` before writing. It hard-codes neither list; if a contract moves, the snapshot moves with
it and its hash changes.

**Feature-only.** No target, outcome, label, sample weight, ADP or market column. `usecols` is
explicit, so `target_ppg`, `target_games`, `sample_weight`, `adp_half_ppr`, `adp_overall_rank`,
`adp_pos_rank` and `sleeper_pts_half_ppr` are never loaded at all; a non-vacuity test proves the source
really does carry them and the snapshot really does drop them. The frame is also passed through the
same `validate_feature_frame` the authorized reader applies to its own output.

### 10.10.2 The asymmetry that makes this work

The **generator** may read the live production CSV. The **authorized experiment** may not — it reads
only the frozen snapshot. `authorized_feature_reader` now opens the parquet and contains no `read_csv`
at all; `verify_pinned_activation_inputs` no longer references `FEATURE_SOURCE`; and
`FEATURE_SOURCE_MD5` is **deleted**, not merely unused, with a test asserting the attribute is gone.

### 10.10.3 Proof that 2026 cannot reach it

Three independent ways, all asserted permanently:

1. **Building from the pre-refresh copy reproduces the identical sha256.** The 2026-08-03 `qb_changed`
   refresh cannot move this artifact, and that is demonstrated rather than argued.
2. **A deliberate 2026-only mutation changes nothing.** A test rewrites `qb_changed` and `prior_ppg`
   for every 2026 row, rebuilds, and the bytes are unchanged.
3. **A 2014-2025 mutation DOES change it.** Parametrized over `prior_ppg`, `age`, `qb_changed`,
   `draft_pick` and `is_rookie`: perturb season 2019, rebuild, and the hash must move. Without this
   the first two would be satisfied by an artifact that ignored its source entirely.

Plus: two fresh rebuilds byte-identical; the snapshot equals the source's 2014-2025 consumed values
column by column (null-aware); a corrupted snapshot, a dropped or extra column, and a smuggled 2026 row
are each refused.

### 10.10.4 The rookie matrix was not touched

`rookie_arm0_features_2014_2025.parquet` remains `7625980495…`, 1,263x61, point-in-time verified, and
was **not rebuilt**. A test asserts the hash, the shape and the source-season lag.

### 10.10.5 The four red tests are green, for the correct reason

They are green because the experiment no longer pins a mutable file, **not** because an assertion was
relaxed. Every one of them still fails closed on real drift: `VETERAN_SNAPSHOT_SHA256`,
`ROOKIE_MATRIX_SHA256` and `WEEKLY_SNAPSHOT_SHA256` each break activation independently when corrupted,
and that is parametrized.

**The 2026 QB-change work was not reverted, not overwritten, not re-pinned and not touched.**
`season_dataset_2014_2026.csv` is exactly as the concurrent session left it.


---

## 10.11 v3.9s — THE AUTHORIZED RUNNER IS BUILT. Result paths moved. Still not executed.

**Approved 2026-08-03 as a pre-outcome OPERATIONAL amendment (Option A).** No lock was opened, no real
outcome was read, no model was fit, no result file was created, nothing was staged or committed.

### 10.11.1 Why the result paths moved

Manifest §5 preregistered five result files into `coaching/data/`. The preflight check
`no_unauthorized_v39_artifact` requires the `*_v39.*` set in that directory to equal **exactly** the
five FEATURE artifacts in `V39_ARTIFACT_HASHES`. Measured on a temp copy:

```
temp copy, BEFORE writing results : 21 / 21  all_ok True
temp copy, AFTER  writing results : 20 / 21  all_ok False
  no_unauthorized_v39_artifact: unauthorized v3.9 artifacts:
    ['arm_bootstrap_v39.csv','arm_metrics_v39.csv','arm_placebo_v39.csv',
     'arm_selection_v39.csv','arm_verdict_v39.csv']
```

The run could not both write its preregistered outputs and pass its own preregistered gate. The five
results now own **`coaching/results/`**. `V39_ARTIFACT_HASHES` and `no_unauthorized_v39_artifact` are
**UNCHANGED** and still protect exactly the five feature artifacts in `coaching/data/`.

**This changes storage only.** No population, feature, arm, hyperparameter, threshold, cohort,
selection rule or verdict criterion is affected.

### 10.11.2 The result-output contract

A new module, `write_v39_results.py`, is the ONLY writer. It could not live in either existing module:
the harness is held to "every `to_csv` targets `DATA /`" and the assembly module to "no writer callee
at all", and both prohibitions are worth keeping exactly as they are.

  * exactly the five permitted names — a missing or extra frame refuses;
  * a pre-existing output refuses unless `overwrite=True` is passed explicitly (separately tested);
  * every file is written atomically (temp file in the same directory, then `os.replace`);
  * a partial write **fails closed** — an injected failure on the 3rd file removes the 1st and 2nd and
    leaves no `.partial` behind;
  * SHA-256 is emitted only after all five have landed.

### 10.11.3 The lossless five-file mapping

`run_experiment` returns **seven** frames; §5 defines **five** files. Nothing is silently discarded:

| returned frame | file | how |
|---|---|---|
| selection | `arm_selection_v39.csv` | direct |
| metrics | `arm_metrics_v39.csv` | `record_type = "metric"` |
| **oracle** | `arm_metrics_v39.csv` | `record_type = "oracle"` — every oracle field preserved |
| bootstrap | `arm_bootstrap_v39.csv` | direct |
| placebo | `arm_placebo_v39.csv` | direct |
| verdict | `arm_verdict_v39.csv` | direct |
| **preflight** | `arm_verdict_v39.csv` | merged on `position` with a `preflight_` prefix |

Round-trip tests read the SERIALIZED files back and recover the oracle, metrics, preflight and verdict
frames exactly, so the merge is proven reversible rather than asserted to be.

### 10.11.4 The canonical panel adapter

`assemble_real_panel_v39.panel_for_experiment()` is the one place the outcome and the features meet,
and the only place the verified outcome column becomes `y`. It joins on the frozen panel keys only,
requires strict one-to-one alignment, preserves the feature-row population and order, retains the
zero-fill/accounting states on the panel, and refuses duplicate, missing or extra outcome keys.

`y` is deliberately IN `FORBIDDEN_IN_FEATURES` — it must never appear in a FEATURE frame — so the leak
check excludes it at this one boundary and `panel_feature_columns()` keeps it, `outcome_state` and
`bucket` out of any model feature list.

**Two real defects were caught by these tests and fixed:** the adapter first validated the POST-core
outcome frame with the PRE-core reader validator, which rejected every well-formed assembled result;
and the leak check tripped on its own sanctioned target.

### 10.11.5 The authorized-real CLI

The `--real` dead end (`raise SystemExit` with no lock check) is **removed**, so there is exactly one
authorized-real path. The documented interface now exists:

```
$env:COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH='I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT'
.\.venv-test\Scripts\python.exe fantasy\projections\coaching\run_coach_projection_experiment_v39.py `
    --run-mode authorized_real --outer-seasons 2018-2025
```

`run_authorized_real()` executes in this fixed order, each step gating the next:

```
require_real_fit_authorization()          <- BOTH locks, or it raises before anything is constructed
require_preflight_clearance()             <- run mode + locks + preflight 21/21 + readiness + gate
                                             + every pinned input
authorized_feature_reader / outcome_reader
assemble_real_panel()
panel_for_experiment()                    <- the canonical adapter
run_experiment(..., run_mode='authorized_real')
validate_outputs(compose(frames))
write_results()                           <- atomic, fail-closed
sha256 report
```

An AST-order test asserts that sequence in the source. Parametrized tests show that in every closed or
partial lock state **zero readers are constructed**, and that `--run-mode synthetic_prefit` never
reaches the real path.

### 10.11.6 ⚠ A REMAINING BLOCKER, FOUND PRE-OUTCOME: the panel cannot feed the rookie buckets

The door takes ONE feature reader, and the veteran snapshot is the veteran contract by construction
(`validate_feature_frame` refuses any column outside it). Measured:

```
veteran snapshot            7,350 rows   40 columns
  is_rookie == 1            1,380 rows   (QB 117 · RB 387 · WR 584 · TE 292)
RB/rookie bundle needs      41 features; present in the snapshot: 9
```

So rows routed to the three ROOKIE buckets exist but carry only 9 of their 41/44/44 features.
`run_experiment` skips a bucket with no usable rows **silently**, which would shrink the population
without anyone noticing. The adapter therefore refuses by default (`require_bucket_coverage=True`) and
names each unfeedable bucket.

**RESOLVED in §10.12.** This was a missing IMPLEMENTATION of an already-frozen contract, not an open
design question: `SHIPPED_ARM0_BUCKETS` had assigned the rookie buckets to `SOURCE_ROOKIE_MATRIX` all
along. `authorized_composed_feature_reader()` now composes both pinned sources under that routing, and
all seven buckets are feedable. The sentence above about a "design decision" is **withdrawn**.

### 10.11.7 What was NOT done

No lock opened · no real fantasy outcome read, inspected, printed, aggregated or compared · no model
fit against a real target · **no result file created** · no production model, projection, dashboard,
betting, market or draft-board file touched · the 2026 QB work untouched · no commit, no staging.


---

## 10.12 v3.9t — THE COMPOSED FEATURE READER. The frozen routing, implemented.

`SHIPPED_ARM0_BUCKETS` already assigned the four VETERAN buckets to the veteran snapshot and the
RB/WR/TE ROOKIE buckets to `SOURCE_ROOKIE_MATRIX`. §10.11.6 reported the panel could not feed the
rookie buckets; that was a MISSING IMPLEMENTATION of an existing contract, not an open design
question, and it is now implemented. No lock opened, no outcome read, no fit, no real result written.

### 10.12.1 The composed reader

`authorized_composed_feature_reader()` verifies BOTH pinned sources independently — hash, manifest and
exact ordered schema — before either frame is accepted, then merges them on the frozen panel keys:

```
spine (population + routing)  veteran_arm0_features_2014_2025.parquet   7,350 x 40
rookie-bucket rows            rookie_arm0_features_2014_2025.parquet    1,263 x 61
composed union frame                                                    7,350 x 87
```

Union schema = 40 veteran + 45 rookie-only + 2 point-in-time provenance = **87**, exact and ordered.
The spine's row count and order are preserved exactly.

**Key-set equality is required, not assumed.** The rookie matrix's keys must equal the spine's
`is_rookie == 1` RB/WR/TE rows **exactly**: measured 1,263 = 1,263, sets equal.

### 10.12.2 Explicit per-row source ownership

NINE columns exist in both sources — `draft_round`, `draft_pick`, `age`, and the six landing-spot
features. A rookie-bucket row takes the **ROOKIE** value for every one of them, **including a NULL**.
Assignment is direct; there is no `fillna`/`combine_first` anywhere in the composition, because an
intentional rookie NULL means "not measured" and must never be back-filled from the veteran source.
A constructed test nulls a shared column in the rookie source, confirms the spine HAS a value there,
and asserts the composed frame is NULL.

### 10.12.3 QB/rookie — the frozen exclusion, preserved and enforced

QB/rookie is absent from `SHIPPED_ARM0_BUCKETS` (the arm was HELD). Its **117** spine rows are not in
the rookie matrix and keep veteran-source values. A QB row appearing in the rookie matrix is REFUSED.
No QB-rookie arm was invented and its routing is unchanged.

### 10.12.4 Per-bucket rows and required-feature coverage (measured)

| bucket | rows | required features | present | rows with >=1 non-null |
|---|---|---|---|---|
| QB/veteran | 885 | 32 | 32/32 | 885 |
| RB/veteran | 1,496 | 32 | 32/32 | 1,496 |
| WR/veteran | 2,266 | 32 | 32/32 | 2,266 |
| TE/veteran | 1,323 | 32 | 32/32 | 1,323 |
| RB/rookie | 387 | 41 | 41/41 | 387 |
| WR/rookie | 584 | 44 | 44/44 | 584 |
| TE/rookie | 292 | 44 | 44/44 | 292 |
| **QB/rookie** | **117** | — | frozen exclusion, veteran-source values | — |
| **total panel** | **7,350** | | | |

7,233 bucket rows + 117 QB/rookie = 7,350. `panel_bucket_gaps()` and `union_bucket_gaps()` are
**empty** on the pinned inputs, and a RED control drops one required feature to prove the check still
fires.

### 10.12.5 Validation widened WITHOUT weakening

`validate_feature_frame` now accepts exactly two schemas: the VETERAN contract, or the UNION contract.
A union frame is accepted **only if all seven shipped buckets are feedable from it**, so the wider
schema can never smuggle in an incomplete panel. Model input is still selected per bucket in each
bundle's exact `feature_cols` order, and the two provenance columns are in no bundle pool — a test
asserts that for all seven.

### 10.12.6 A measured population fact Joseph should see

**80 of the 7,350 panel rows carry a NULL `team`** (QB 14 · RB 15 · TE 20 · WR 31, all veteran-bucket,
spread across 2014-2024). They come from the veteran SOURCE — composition does not introduce them —
and every non-null `(season, team)` pair IS covered by the Design A coaching table.

`attach_coach_features` refuses a row whose `(season, team)` has no coaching bundle, so an authorized
run over the full panel would have raised on these 80 rows. **RESOLVED in §10.13**: they are now
excluded by an explicit pre-outcome eligibility rule, with a reason and a count, adopted as a
population amendment. Recorded permanently by
`test_the_null_team_rows_are_MEASURED_not_assumed` so the number cannot drift silently.

### 10.12.7 Documentation corrected

The module docstring that still said the rookie buckets "have no repo-owned source at all" is
SUPERSEDED — true from v3.9g to v3.9m, resolved by Option A. That correction is the only documentation
change in this pass.

### 10.12.8 What was NOT done

No lock opened · no real fantasy outcome read · no model fit against a real target · no real result
written · no production model or pinned input touched · the 2026 QB work untouched · no commit.


---

## 10.13 v3.9u — EVALUATION ELIGIBILITY: a PRE-OUTCOME population amendment

Adopted 2026-08-03, **before any outcome was accessed**. A row is eligible only when BOTH hold:

1. `team` is non-null, so OC/HC exposure is **defined** for it; and
2. its `(position, bucket)` has a shipped Arm 0 bundle.

Determined solely from the frozen feature frame, and applied **identically to ARM_0 and every coaching
arm** — eligibility is a property of the panel, not of an arm. Nothing is imputed, proxied or
fabricated.

### 10.13.1 The measured partition

Verified rather than trusted; the categories are mutually exclusive and exhaustive:

```
source_population                  7,350
excluded_missing_team                 80
excluded_no_shipped_bundle           117   (QB/rookie)
eligible_evaluation_population     7,153

overlap between the two exclusion reasons: 0     (so the partition is unambiguous)
80 + 117 + 7,153 = 7,350                          (so it is exhaustive)
```

Excluded by missing team, by position: **WR 31 · TE 20 · RB 15 · QB 14**, all veteran-bucket, spread
across 2014-2024. Excluded for no shipped bundle: **QB 117**, all QB/rookie.

Eligible rows by bucket: QB/veteran 871 · RB/veteran 1,481 · WR/veteran 2,235 · TE/veteran 1,303 ·
RB/rookie 387 · WR/rookie 584 · TE/rookie 292. All twelve seasons and all eight outer seasons remain
represented, and `union_bucket_gaps()` on the eligible frame is **empty**.

### 10.13.2 Why these two rules

**Missing team.** OC/HC exposure is undefined without a team: there is no coaching staff for the row to
be exposed to. **Neutral imputation was considered and REJECTED** — assigning a placeholder invents the
very quantity the experiment measures, and would let a fabricated exposure enter both the baseline and
every coaching arm. `attach_coach_features` already refused such a row; the amendment makes the
exclusion explicit and counted rather than a runtime crash.

**No shipped bundle.** The 117 QB/rookie rows were **already outside** the shipped seven-bundle
experiment — the QB rookie arm was HELD and there is no `qb_rookie_model.pkl`. The bucket loop skipped
them *silently*. They are now excluded **explicitly, with a reason and a count**, which is the actual
change: the population is the same, the accounting is honest.

**No outcome was accessed when the rule or the counts were chosen.** The rule reads `team` and
`position` only; a test asserts `evaluation_eligibility` names no outcome column, and a constructed
test attaches a synthetic target and shows the partition is bit-identical.

### 10.13.3 Where it runs

`evaluation_eligibility()` is the single canonical function. In the authorized runner it executes
**inside the feature reader**, so it completes before the outcome reader is ever called — Python
evaluates `assemble_panel_core(feature_reader(), outcome_reader())` left to right, and a malformed
partition raises out of the first argument. A test injects a failure and asserts **zero
outcome-reader calls**.

The full 7,350-row source validation and source-ownership checks in
`authorized_composed_feature_reader()` are preserved unchanged; eligibility runs after composition.

`run_experiment` now calls `assert_no_implicit_row_loss(panel)` on entry. There are exactly two
implicit-loss mechanisms — a null team (which makes `attach_coach_features` refuse) and an unshipped
bucket (which the loop skips) — so forbidding both on arrival forbids later silent loss.

### 10.13.4 Accounting, carried without a sixth artifact

The counts ride in `arm_verdict_v39.csv` under an `eligibility_` prefix, beside the `preflight_` block:
source, both excluded counts by reason, the eligible total, the exclusivity/exhaustiveness flags, and
the per-position and per-season breakdowns. `recover_eligibility()` reads them back from the serialized
file, and the preflight and verdict round-trips are unaffected. **Still exactly five result files.**

### 10.13.5 What was NOT done

No lock opened · no outcome read · no fit · no real result written · no imputed or proxied coaching
exposure · no change to any feature, arm, hyperparameter, threshold, cohort, selection rule or verdict
criterion · no commit.


---

## 10.14 v3.9v — THE ACTIVATION CONTRADICTION: the two-lock system could not be opened

Found by reading the committed source at `8ca2efc`, reproduced before any edit.

### 10.14.1 The contradiction

```
C6                          statically requires exactly one module-level REAL_FIT_AUTHORIZED = False
validate_run_mode           authorized_real required that constant to be True at runtime
manifest §3                 instructed editing and committing it as True
```

Measured, both horns:

```
source edited to True   -> C6 FAILS: "only one module-level `= False` is allowed"
                           -> no_real_outcome_access False -> preflight 20/21 -> gate 1 refuses
source left as False    -> validate_run_mode(authorized_real) False:
                           "requires BOTH real-fit locks OPEN (constant=False, env=False)"
```

So the published command could not open both locks by any route. The tests only reached the authorized
path by monkeypatching the module global, and **the documented CLI had no equivalent mechanism** — the
two-lock system was openable only by bypassing its own interface.

### 10.14.2 The repair — a capability, not a flag

`REAL_FIT_AUTHORIZED = False` stays in committed source as the default-closed invariant and is never
reassigned. Authorization exists only as `RealFitAuthorization`: immutable (`__slots__`, `__setattr__`
and `__delattr__` raise), minted per invocation by `grant_real_fit_authorization()` **only** when the
CLI token and the environment token both match their frozen literals exactly, and threaded explicitly
through `validate_run_mode` → `preflight` → `require_real_fit_authorization` →
`require_preflight_clearance` → `assemble_real_panel` → `run_authorized_real`.

It is never stored in a module global — a test enumerates `vars()` and asserts none holds one — so it
cannot persist after the call that made it. **Mutating `REAL_FIT_AUTHORIZED` at runtime now authorizes
nothing**: `real_fit_lock_state()` never consults it as an opener, and a test proves the old monkeypatch
route is dead.

### 10.14.3 C5-A and C6, tightened

**C5-A clause 1** now requires statement 1 to be `require_real_fit_authorization(authorization)` using
the door's **own parameter** — not a literal, not a global, not a freshly minted grant. Four injections
(`()`, `(True)`, `(grant_real_fit_authorization('x'))`, `(REAL_FIT_AUTHORIZED)`) are all rejected.

**C6** is restated precisely: exactly one canonical module-level binding, it is `False`, production
source contains no reassignment **or mutation** — a new `_lock_mutations` walker rejects
`globals()['REAL_FIT_AUTHORIZED'] = True` and `setattr(m, 'REAL_FIT_AUTHORIZED', True)`, which the
Assign-target walker could not see — and real authorization is invocation-scoped. The existing
binding-target/evasion corpus stays live (75 injections, categories C1/C3/C4/C4b/C5/C5A/C6/C7).

### 10.14.4 The exact command

```
$env:COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH='I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT'
.\.venv-test\Scripts\python.exe fantasy\projections\coaching\run_coach_projection_experiment_v39.py `
    --run-mode authorized_real `
    --authorization-token JOSEPH-AUTHORIZED-V39-FIRST-REAL-RUN `
    --outer-seasons 2018-2025
```

The previously published command — the same line without `--authorization-token` — is tested and
**refuses before any reader is constructed**.

### 10.14.5 What was NOT done

No real outcome read · nothing fit · no result written · the real token pair presented only in-process
against injected/stubbed readers · `REAL_FIT_AUTHORIZED` still `False` in source after every test ·
no commit.

---

## 10.15 v3.9w — THE FIRST AUTHORIZED REAL RUN WAS ATTEMPTED AND REFUSED (2026-08-03/04)

### 10.15.1 What happened

The run was authorized from clean commit `193503fb` and executed **once**. It stopped after two seconds
at **pre-run clearance** — `require_preflight_clearance`, gate 1 — reached from `run_authorized_real`
BEFORE either reader was constructed:

```
gate 1 (authorized preflight): check(s) not explicitly ok: ['pipeline_timing_assertions_ran']
```

**Nothing was produced and nothing moved.** No reader was constructed, no fantasy outcome was read, no
model was fit, and no result file landed — `coaching/results/` did not exist before the attempt and did
not exist after it. The environment token was cleared by the invocation's `finally`;
`REAL_FIT_AUTHORIZED` stayed `False` in source and at runtime; the lock state returned to
`(False, False)`; the scoped tree stayed clean; 18/18 protected artifacts, the production models and
every pinned input were unchanged. The refusal was total and correct in effect — but for the wrong
reason.

### 10.15.2 Cause — a circular gate of my own construction

`pipeline_timing_assertions_ran` required every `_PIPELINE_ASSERTIONS` counter to be non-zero. Those
counters are incremented **by** `run_experiment`, which runs **after** clearance. In a fresh process all
four are zero, so `preflight(run_mode='authorized_real')` returned 19/21 and the authorized path could
never clear its own gate.

**Why no test caught it.** Every test that exercised the authorized path either passed
`pipeline_assertions={k: 3 ...}` explicitly or replaced `require_preflight_clearance` with a stub. Both
supply a value the real path cannot produce, so the real path's inability to produce it was
unobservable. This is the same class as the earlier "the check didn't check what it claimed" findings —
a test that manufactures the very evidence it is meant to verify.

### 10.15.3 The repair — two-phase 21-check preflight

The timing check is **not** disabled, relaxed or faked. It is phase-aware and asserted **twice**, all 21
checks in both phases:

| phase | required counter state | evaluated |
|---|---|---|
| `pre_run` | every counter EXACTLY zero; a stale non-zero counter FAILS, naming it | before any reader |
| `post_pipeline` | every frozen counter POSITIVE; any that did not execute is NAMED | after `run_experiment`, before compose/write |

Renamed `pipeline_timing_assertions_ran` → **`pipeline_timing_assertion_state`**: "…_ran" was false in
the pre-run phase, where the check passes precisely because the pipeline has NOT run. The frozen check
count stays **21** and both pinned vocabularies were updated by value.

`validate_authorized_preflight` accepts only a `pre_run` result; the new
`validate_post_pipeline_preflight` only a `post_pipeline` result. Neither can be replayed as the other,
and both are phase-parameterised only through a PRIVATE helper — the public entry points take no phase
argument, for the same reason `expected_checks` was removed.

`run_authorized_real` now executes: authorization → **reset counters** → `pre_run` 21/21 →
clearance/readiness/gate → readers and assembly → `run_experiment` → **`post_pipeline` 21/21** → validate
result frames → atomic write. If the post-pipeline gate fails, **zero result files land**.
`run_experiment`'s per-position C10 records use `post_pipeline` semantics and still require every timing
assertion.

### 10.15.4 The blind spot itself is now tested

`tests/test_two_phase_preflight_v39.py` exercises the REAL `run_authorized_real` control flow with
synthetic injected readers and the REAL preflight functions: no supplied `pipeline_assertions`, no
stubbed clearance, counters observed at zero before and positive after, both phases 21/21, and the
writer reached only afterward. Also tested: stale counters fail `pre_run` before any reader; zero
counters fail `post_pipeline` before any write; one missing counter fails and is named; a wrong-phase
result refuses; and **no result file survives any failure path**.

### 10.15.5 The two operational defects in the published command

1. **CMD syntax.** `set NAME=value` is inert in PowerShell, so the documented command would not have set
   the lock at all. Corrected to `$env:NAME='value'` and pinned in a test.
2. **Test-scale draw defaults.** `--bootstrap-draws` defaulted to `2000` against the frozen `20_000`,
   `--placebo-draws` to `10` against the frozen `200`. The documented command omitted both flags, so it
   would have produced a real result at one tenth and one twentieth of the preregistered resolution.
   In `authorized_real` the flags now **default to the frozen constants** and
   `validate_authorized_draw_counts()` **refuses any other value**; reduced counts remain reachable only
   through a direct injected call from a test.

### 10.15.6 What was NOT done

**No statistical rule, threshold, denominator, seed or frozen constant changed** — the repair is
entirely in the ordering and phase of the runtime gate. No real outcome was read · nothing was fit · no
real result was written · `coaching/results/` remains absent · `REAL_FIT_AUTHORIZED` is still `False` in
source · the authorized command was NOT rerun · nothing staged · no commit.

---

## 11. UNRESOLVED ISSUES

0. **RESOLVED (v3.9b) — the historical source-date gate is retired**, primary history is strictly-prior
   over the full retrospective ledger, and the retired rule is a labelled in-memory sensitivity. The
   "~76 usable rows" and "200/256 ceiling" claims are **retracted**; the realised gain is **zero rows**
   and +358 caller-games (§7). **The 2019–2022 power problem is NOT relieved** — see item 1.

0c. **CLOSED, and my own blocker WITHDRAWN (v3.9p, §10.7).** I raised "the shipped rookie bundles
   were trained on a leaked PFF join" as an activation blocker. The historical fact is true; the
   blocker was **wrong**, because `fit_predict` builds a fresh estimator every fold and the serialized
   weights never enter a prediction. Readiness is **True**. What survives as a stated limitation, NOT
   a gate: the fixed hyperparameters were tuned under the old pipeline, are frozen pre-experiment and
   are applied identically to every arm. One production note remains: `assemble_features.py` is shared,
   so the next run of the RB/WR/TE projection builders will produce different rookie bundles.

0b. **PARTLY SUPERSEDED (v3.9n, corrected by v3.9o) — the rookie feature source.** Joseph selected Option A; the derived,
   outcome-free rookie matrix is frozen, hash-pinned and manifest-pinned, and `activation_readiness()`
   is now `True` for all seven Arm 0 bundles (§10.5). Two residual facts, stated rather than closed:
   **regenerating** the matrix still requires the authorized private PFF directory (941 local files, 0
   tracked), so a clean checkout can *use* but not *rebuild* it; and readiness is **False**, not True —
   the sentence that once said otherwise is superseded by item 0c. Both locks remain closed and
   `authorized_real_gate()` refuses at both gates.

1. **Design A caller power is thin in 2019–2022** — 3/4/7/6 of 32 team-seasons have an identified
   caller with any eligible prior history. A null caller arm cannot separate "no coaching signal" from
   "no retrievable identity". Highest-value remaining research: a qualifying **pre-cutoff** league-wide
   caller source for 2019–2022 (logged in `data/RESEARCH_LOG.md`).
2. **The neutral 0.5 on the two binary caller indicators is a distinguishable third level** and is
   season-correlated under Design A. Controlled by the permutation placebo; not eliminated.
3. **Arm 3 does not exist before target season 2018** (Stage 2's frozen minimums). Both outer-2018
   inner folds validate on 2016/2017, so Arms 3 and 5 cannot be selected on evidence in that fold.
   Nothing is backfilled and Stage 2 is not re-estimated.
4. **Head-coach identity is an assumption, not evidence-gated research** — taken from the week-1 head
   coach. Defensible (HC hires are public preseason) but not held to the caller evidence standard, and
   ARM_HC's "full point-in-time coverage" rests on it.
5. **A consequence of the frozen selection rule**, recorded before any result: the 1% gate applies to
   the **best** coaching arm, and the 0.25 tie-band then selects on parsimony — so the finally selected
   arm can be one whose own improvement is below 1%. That follows from §5 as written; not changed here.
6. **`build_coach_features.py` and `build_arm3_effects.py` remain unrepaired** and are not used by
   v3.9. They still join on (season, team) and carry pre-v3.3 metric names. They should be deleted or
   repaired rather than left beside a working builder.
7. **The legacy PPG×games family is still on disk** with categoricals and sample weights. It is not
   Arm 0, but anyone auditing "the production model" could easily read the wrong family.
8. **`test_rebuild_is_byte_identical` rewrites the canonical table on every suite run.** Byte-safe,
   but it means an mtime check alone can never establish that the table was untouched.
9. **PFF-enhanced sensitivity (prereg §11) not run** in this pass, as instructed.
10. **The placebo is now the dominant compute cost** of the real experiment: 200 draws × 8 outer folds ×
    a full nested selection each. Budget for it before authorizing the real run; it is not a
    correctness problem, but it is a scheduling one.
11. **Condition 3/4 denominators are absolute.** The verdict counts improvements against the frozen
    6-of-8 and 4-of-5 requirements. A partial run (fewer outer seasons) therefore cannot pass those
    conditions — correct, but worth knowing before interpreting a truncated diagnostic run.
12. **The legacy `hc_game_results_v39.csv` is gone** from `coaching/data/`. If any external note
    referenced that path, it now resolves to nothing by design.
13. **The v3.9a report's unresolved item 11 was a claim, not a guarantee** — it said a partial run could
    not pass conditions 3/4, while the code checked only counts. Now enforced (§8.7). Recorded here
    because the same failure mode (documenting a limitation instead of enforcing it) is easy to repeat.
14. **`authorized_real` mode is implemented and tested but never exercised.** The real outcome join is
    deliberately unimplemented — `assemble_real_panel()` raises `NotImplementedError` after the
    authorization check passes. The state machine is verified with synthetic lock states only.
15. **The 2019–2022 caller channel remains the binding constraint**, and v3.9b proves retiring the gate
    does not help it: 2019 gains zero games and no season gains a row. Only a qualifying **pre-cutoff**
    league-wide caller source for 2019–2022 would move it.
16. **The `V39_ARTIFACT_HASHES` pins must be updated deliberately with every intentional rebuild.**
    v3.9c showed why that is not merely bookkeeping: before the full-frame coverage check existed, the
    pin was the *only* thing standing between a corrupted artifact and a green C10. The semantic checks
    now carry that weight, but `test_pinned_v39_hashes_match_disk` still fails loudly if a pin goes stale.
17. **RESOLVED (v3.9d follow-up) — the doc scan is now a registered test.** The earlier statement that
    it "is a scratch script, not a registered test" and "does not run in CI" is **SUPERSEDED**. It runs
    with the suite as `test_no_live_document_asserts_a_retired_identifier_unqualified` over the five
    live documents, and `test_the_retired_claim_scanner_actually_catches_each_claim` proves every
    pattern still fires on an unqualified sample and still honours a same-line qualifier — so a
    scanner that silently stopped matching cannot pass vacuously. The companion
    `test_every_test_named_in_the_requirement_matrix_actually_exists` pins the whole matrix.
18. **Concurrent writes by other sessions — the v3.9c footprint text below is HISTORICAL and no longer
    describes the tree.** On 2026-07-29 another session wrote `scripts/bench_*.py`, `app.py`,
    `dashboard_chrome.py` and two memory files while v3.9c was closing, and `git status --short` moved
    59 → 61 → 65 → 67 within two minutes. Everything the v3.9c report said about a "15-file untracked
    footprint" is **SUPERSEDED**: Joseph committed the coaching work on 2026-07-30, so those files are
    tracked and the current scope is a diff, not an inventory. The live scope statement is §10.3.3.

    The one durable point from that episode, which still applies: **`git status --short` is a moving
    number while another session is active, so it is not a scope check.** Scope is stated here as an
    explicit diff against `HEAD` plus per-file hashes, and every number in this report was re-read from
    the tree immediately before it was written down.

    Also still true and worth keeping: `actual_play_caller.csv` and `source_ledger.csv` acquire a fresh
    mtime during ordinary test runs and were once rewritten **byte-identically** by a concurrent
    session — `actual_play_caller.csv` still hashes to the pinned `98f1c66b7387c16bba6a5463f4e0fa06`,
    the value the RESEARCH_LOG header carries. The v3.9 modules only ever *read* it (one `read_csv` in
    `build_arm_features_v39.py`, plus the pin and two lineage strings); they never write it. **A
    reviewer seeing a fresh mtime on those two files should compare bytes, not timestamps.**

---

## 12. PREFIT STOP STATEMENT

Phase 1 (data research, Stage 1 residuals, Stage 2 effects) is complete and untouched. Phase 2A
(point-in-time coaching representations) and Phase 2B (nested evaluation harness) are implemented,
tested on synthetic targets, and documented.

**No real fantasy outcome was loaded, inspected, or fit. No real player-model run was performed. No
production, preliminary, or v3.8 artifact was modified. The next step — fitting the arms against real
season-total half-PPR — requires Joseph's explicit approval and a further written PREFIT amendment.**

**STOPPED BEFORE REAL FANTASY OUTCOMES / FIRST REAL PLAYER-MODEL RUN — JOSEPH REVIEW REQUIRED.**
