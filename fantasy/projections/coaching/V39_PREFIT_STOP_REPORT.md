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
| 1 | The build was **not hermetic**: `projection_cutoffs()` and `hc_game_results()` both downloaded nflverse schedules, and the win ledger sat in an untracked scratch cache. A clean offline checkout failed **five** feature tests, so the 254-pass claim depended on state outside the repo. | **FIXED** — both read the repo-owned frozen snapshot; the ledger is computed in memory; suite and build now pass with egress blocked and an empty temp dir (§1.4) |
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

**Preflight: 17 → 20 checks** (`v39_artifacts_readable`, `lineage_states_the_primary_policy`,
`no_real_outcome_access`).

---

## 1. OPENING VERIFICATION

### 1.1 Inherited test baseline: **141**, reproduced exactly

The suite now contains 254 tests because this pass added 113. The **141** baseline was reproduced by
ignoring the two new v3.9 modules and deselecting the three new ownership tests:

```
pytest fantasy/projections/coaching/tests -q
  --ignore=.../tests/test_arm_features_v39.py
  --ignore=.../tests/test_coach_projection_harness_v39.py
  --deselect (all SIX new tests in test_artifact_ownership.py:
      test_each_protected_text_artifact_has_exactly_one_writer,
      test_build_arm_features_v39_writes_only_the_five_authorized_artifacts,
      test_the_harness_writes_no_repo_artifact_at_all,
      test_no_unauthorized_v39_artifact_exists_on_disk,
      test_the_head_coach_win_ledger_is_cached_outside_the_repo,
      test_the_v39_modules_never_write_outside_the_coaching_data_dir)
-> 141 passed, 6 deselected
```

(An earlier run of this check deselected only three and returned **144 passed, 3 deselected**. The
count was recomputed rather than assumed; six of the nine ownership tests are v3.9 additions.)

Interpreter: `AI_hedge_fund/.venv` (the repo's documented working interpreter; bare `python` resolves
to it via `VIRTUAL_ENV`).

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
full coaching suite   290 passed
inherited baseline    141 passed, 6 deselected
full v3.9 build       completed; all five artifact hashes reproduced
```

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

1. `REAL_FIT_AUTHORIZED = True` (module constant), **and**
2. `COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT` in the environment.

Either lock alone leaves the gate shut (`test_real_fit_is_blocked_by_a_default_closed_double_lock`
proves all four combinations). `assemble_real_panel()` is the single door and is deliberately
unimplemented past the authorization check. `--real` exits with the block message. **Both locks are
shut and neither was opened in this pass.**

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
`pipeline_timing_assertions_ran` · `run_mode_locks`.

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
| new v3.9 + v3.9a + v3.9b + v3.9c tests | **249** |
| **full coaching suite** | **390 passed, offline, egress blocked, fresh empty temp dir** |

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
| `test_coach_projection_harness_v39.py` | **155** | new |

22+33+34+27+15+7+3 = **141** inherited; 88+155+6 = **249** new; total **390**.

To reproduce the 141 exactly, ignore the two v3.9 test modules and deselect these six — the whole
`tests/` tree is untracked, so the six cannot be recovered by diffing against `HEAD`, and a mistyped
`--deselect` is silently ignored by pytest and yields 147:

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

## 11. UNRESOLVED ISSUES

0. **RESOLVED (v3.9b) — the historical source-date gate is retired**, primary history is strictly-prior
   over the full retrospective ledger, and the retired rule is a labelled in-memory sensitivity. The
   "~76 usable rows" and "200/256 ceiling" claims are **retracted**; the realised gain is **zero rows**
   and +358 caller-games (§7). **The 2019–2022 power problem is NOT relieved** — see item 1.

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
17. **The doc scan is a scratch script, not a registered test.** It is self-tested and was run to
    completion for this report, but it does not run in CI. If superseded wording matters long-term it
    should become a registered test; it is not one today.
18. **Another session wrote into this repo concurrently with this pass, and none of it is mine.**
    `scripts/bench_pages.py` and `scripts/bench_server.py` (20:55/21:00), then `app.py`,
    `dashboard_chrome.py`, `memory/streamlit-throttle.md` and `memory/MEMORY.md` (21:35). All are
    untouched by me. **`git status --short` is therefore a moving number** — it read 59 at the start of
    this pass, 61, then 65, then 67 within two minutes as that session kept working, so it is not a
    useful scope check here and no single value for it is quoted as one.

    My own footprint is instead **enumerated exactly — 15 files, all under
    `fantasy/projections/coaching/` plus the one prereg**: 2 new modules (`build_arm_features_v39.py`,
    `run_coach_projection_experiment_v39.py`), 3 test files (2 new, plus 6 tests added to
    `test_artifact_ownership.py`), the 5 authorized data artifacts, and 5 documents
    (this report, `REQUIREMENT_MATRIX.md`, `AUDIT_TODO.md`, `data/RESEARCH_LOG.md`,
    `preregs/PREREG_coach_quality_2026-07-28.md`). Nothing outside that list is mine.

    That session also **rewrote two files inside `coaching/data/` at 21:35:24** — `actual_play_caller.csv`
    and `source_ledger.csv`. Both were rewritten **byte-identically**: `actual_play_caller.csv` still
    hashes to the pinned `98f1c66b7387c16bba6a5463f4e0fa06` (the same value the RESEARCH_LOG header
    carries), so only the mtime moved. Because those writes landed *after* my earlier protected-artifact
    check, the whole 18/18 comparison, the preflight and all five v3.9 hashes were **re-run at 21:37:26**
    and are the numbers reported in this document. The v3.9 modules only ever *read*
    `actual_play_caller.csv` (one `read_csv` at `build_arm_features_v39.py:497`, plus the pin and two
    lineage strings) — they never write it. A reviewer seeing a fresh mtime on those two files should
    compare bytes, not timestamps.

---

## 12. PREFIT STOP STATEMENT

Phase 1 (data research, Stage 1 residuals, Stage 2 effects) is complete and untouched. Phase 2A
(point-in-time coaching representations) and Phase 2B (nested evaluation harness) are implemented,
tested on synthetic targets, and documented.

**No real fantasy outcome was loaded, inspected, or fit. No real player-model run was performed. No
production, preliminary, or v3.8 artifact was modified. The next step — fitting the arms against real
season-total half-PPR — requires Joseph's explicit approval and a further written PREFIT amendment.**

**STOPPED BEFORE REAL FANTASY OUTCOMES / FIRST REAL PLAYER-MODEL RUN — JOSEPH REVIEW REQUIRED.**
