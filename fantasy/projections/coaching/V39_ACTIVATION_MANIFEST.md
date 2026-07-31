# v3.9e ACTIVATION MANIFEST — the first real player-model run

**Status: NOT EXECUTED. NOT AUTHORIZED. NOT READY.** This document describes a run that has not
happened. Both real-fit locks are closed, `assemble_real_panel()` is still sealed, no real fantasy
outcome has been read, and no result artifact exists.

**`activation_readiness()` currently returns `False`.** Three of the seven shipped Arm 0 bundles —
RB/WR/TE rookie — have no repo-owned feature source, so the run cannot be assembled even with both
locks open. **§0b holds an unresolved decision that is Joseph's to make.** Nothing here may be executed
without that decision, Joseph's explicit written authorization, and a committed PREFIT amendment.

---

## 0. THE RUN IS ALREADY HERMETIC — no fetch, no new input artifact

**A previous revision of this manifest claimed the Arm 0 outcome was not repo-owned and that a network
fetch plus a new `season_total_half_ppr` snapshot were required. That claim was WRONG and is
WITHDRAWN.** I checked `build_rb_projection.season_total_target()`, saw it call
`nfl.load_player_stats(...)`, and concluded the outcome was unavailable offline — without checking
whether the repository already owned a snapshot of that same loader. It does.

```
fantasy/seasonal_projections/snapshots/player_stats_2011_2025.parquet
sha256  e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344   (VERIFIED on disk)
loader  nflreadpy.load_player_stats · nflreadpy 0.1.5 · fetched 2026-07-09T23:10:30Z
shape   269,594 rows x 115 columns · seasons 2011-2025
```

It is tracked, pinned in `snapshots/manifest.json`, and carries `player_id`, `season`, `season_type`,
`fantasy_points` and `receptions` — everything the target needs.
`wr_recent_full_game_features_harness.build_panel()` already reproduces the production target from it
(lines 185-191: read the snapshot, `season_type == "REG"`, `fantasy_points.fillna(0) +
0.5*receptions.fillna(0)`).

`authorized_outcome_reader()` derives the target from this snapshot, verifying both the sha256 and the
manifest provenance (loader, rows, cols) before reading. `OUTCOME_SNAPSHOT`, `OUTCOME_SNAPSHOT_MD5` and
the "snapshot does not exist" tests are **removed**; `test_no_outcome_snapshot_constant_survives` fails
if any of them return.

**Scope of that claim, corrected.** A previous revision said flatly that "the first authorized run is
already hermetic". **That is WITHDRAWN as an unqualified statement.** It is true of the OUTCOME path and
of the four VETERAN feature buckets. It is NOT true of the full seven-bundle feature path — see §0b.

---

## 0b. THE REAL BLOCKER — three of seven Arm 0 bundles have no repo-owned feature source

Arm 0 ships **seven** bundles, not four. An earlier revision defined the feature contract as
"identity + the 32 veteran features" and called it the Arm 0 contract; it covers four bundles. Only
`rb_veteran_model.pkl` was pinned by a test, so the omission was invisible.

Measured 2026-07-30 against `season_dataset_2014_2026.csv` (47 columns):

| bundle | features | in season dataset | **missing** | source |
|---|---|---|---|---|
| `qb_veteran_model.pkl` | 32 | 32 | 0 | season dataset ✅ |
| `rb_veteran_model.pkl` | 32 | 32 | 0 | season dataset ✅ |
| `wr_veteran_model.pkl` | 32 | 32 | 0 | season dataset ✅ |
| `te_veteran_model.pkl` | 32 | 32 | 0 | season dataset ✅ |
| `rb_rookie_model.pkl` | 41 | 9 | **32** | **none** ❌ |
| `wr_rookie_model.pkl` | 44 | 9 | **35** | **none** ❌ |
| `te_rookie_model.pkl` | 44 | 9 | **35** | **none** ❌ |

(QB/rookie is deliberately absent: the QB rookie arm was HELD.)

The missing features are combine (`forty`, `vertical`, `bmi`, `speed_score`, …), college-box
(`cfb_*`) and PFF-derived (`pff_receiving_*`, `pff_rushing_*`). Production regenerates them through
`fantasy/rookie/harness`:

- `assemble_panel.py` imports `nflreadpy` and calls `load_player_stats`, `load_draft_picks` — **live**;
- `assemble_features.py` also calls `load_combine`, and reads `fantasy/seasonal_projections/pff/`;
- that directory holds **418 local files** and **0 tracked files** — `git ls-files` returns nothing,
  because `.gitignore:37` ignores it.

**A clean checkout therefore cannot assemble the three rookie buckets at all.** `activation_readiness()`
returns `False` and names them; it is a *separate layer* from `preflight()`, so the committed v3.9d
prefit checkpoint stays green at 21/21 while activation stays blocked.

### The decision — Joseph's, not mine

| option | what it means | cost / risk |
|---|---|---|
| **A. Freeze a feature-only rookie matrix as a repo-owned pinned artifact** | Generate once, containing ONLY point-in-time feature values and identity keys — no outcome, no HIT construction — with provenance and a pinned hash, like `schedules_1999_2025.parquet` | Self-contained clean-checkout builds thereafter. **Requires a PFF licensing/privacy decision**: the artifact is PFF-derived and the source directory is gitignored, plausibly deliberately. Must not be written before that is settled. |
| **B. External pinned artifact** | Store it outside the repo and retrieve it by a documented contract (URL/path + sha256 verified before use) | Honest about not being self-contained. A clean checkout still cannot build without the external fetch, so "hermetic" would need qualifying wherever it is claimed. |
| **C. Amend the experiment to exclude rookie buckets** | Evaluate the veteran path only | **Changes the frozen population.** Would need the exact rows/cohorts/conditions quantified and a prereg amendment. Not adoptable without explicit authorization. |

**My recommendation: A**, conditional on the PFF licensing question — it is the only option that keeps
both the frozen population and clean-checkout reproducibility. **I have not written any artifact, have
not touched the PFF directory, and have not regenerated the rookie matrix.** Option C's row/cohort
impact is deliberately NOT quantified here, because quantifying it would mean deciding the shape of an
amendment before you have chosen one.

---

## 1. What must change when `assemble_real_panel()` moves from sealed to implemented

Today the door is:

```python
def assemble_real_panel(*_a, **_k):
    """..."""
    require_real_fit_authorization()
    raise NotImplementedError(...)
```

C5 requires its executable body to be **exactly two statements**. An implementation is therefore
impossible without changing C5 — by design, and this is the single deliberate act of activation.

**Every protection that structurally depends on the seal, and what happens to each:**

| protection | where | at activation |
|---|---|---|
| **C5** exactly one binding; body exactly 2 statements; statement 2 an unconditional `raise NotImplementedError` | `no_real_outcome_access()` | **Replaced** by mode-aware C5 (§2). Not deleted, not loosened for `synthetic_prefit`. |
| `test_assemble_real_panel_must_stay_authorization_first_and_unimplemented` | harness tests | Split: the *authorization-first* half survives verbatim; the *unimplemented* half moves to the `synthetic_prefit` contract. |
| corpus cases `c5-body-*` (5 cases: early-return, dormant-raise, auth-with-args, decorated, wrong-exception) | `boundary_corpus.py` | `c5-body-early-return` and `c5-body-dormant-raise` become `synthetic_prefit`-only. The other three (auth-with-args, decorated, wrong-exception) apply in BOTH modes and are unchanged. |
| corpus cases `c5-rebind-*` (15 cases) | `boundary_corpus.py` | **Unchanged in both modes.** Rebinding the door is never legitimate. |
| C-14 "authorization-FIRST and unimplemented" | `REQUIREMENT_MATRIX.md` | Reworded to "authorization-FIRST, and unimplemented in `synthetic_prefit`". |
| H-19 "real fantasy fitting is BLOCKED" | `REQUIREMENT_MATRIX.md` | Reworded to "blocked unless BOTH locks are open AND preflight passes". |
| prereg §C5 clause | `PREREG_coach_quality_2026-07-28.md` | Amended in the PREFIT amendment, quoting the new clause verbatim. |
| `NO_OUTCOME_OK_DETAIL` | harness | Gains a mode marker; the exact-bytes test updates with it. |

**Nothing above is deleted.** Every retired assertion is replaced by a strictly mode-scoped one, and the
`synthetic_prefit` prohibition remains exactly as strong as it is today.

---

## 2. The mode-aware C5 that replaces the current one

```
C5-S  synthetic_prefit  (UNCHANGED from today, verbatim)
      assemble_real_panel is bound exactly once, by one undecorated module-level def, whose
      docstring-stripped body is exactly two statements: a zero-argument
      require_real_fit_authorization(), then an unconditional raise NotImplementedError(...).

C5-A  authorized_real
      assemble_real_panel is bound exactly once, by one undecorated module-level def, and:
        1. statement 1 is a zero-argument require_real_fit_authorization()
        2. statement 2 is a call to require_preflight_clearance()
        3. no reader callee appears anywhere in the body — the readers are injected parameters
        4. no banned outcome callee appears anywhere in the body
        5. the function returns the result of assemble_panel_core(...) and nothing else
        6. no statement precedes 1
```

The mode is selected by an explicit module constant, not inferred from the lock state, so that
"which contract applies" can never be decided by the very thing the contract is protecting.

---

## 3. The exact command

```
set COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT
.\.venv-test\Scripts\python.exe fantasy\projections\coaching\run_coach_projection_experiment_v39.py --run-mode authorized_real --outer-seasons 2018-2025
```

Required simultaneously:

| lock | required value |
|---|---|
| `REAL_FIT_AUTHORIZED` (module constant) | `True` — edited in source, committed, reviewed |
| `COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH` | exactly `I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT` |

Either alone is refused. A partial state is refused in **both** modes.

---

## 4. Inputs and pinned hashes

**The outcome and veteran-feature inputs exist, are tracked and are pinned. The rookie-feature input
DOES NOT EXIST and must be resolved by the §0b decision before activation.**

| input | path | pin | status |
|---|---|---|---|
| veteran features | `fantasy/seasonal_projections/season_dataset_2014_2026.csv` | md5 `8322a59e43251820cb393d40787f60e6` | ✅ tracked, pinned |
| weekly stats → the target | `fantasy/seasonal_projections/snapshots/player_stats_2011_2025.parquet` | sha256 `e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344`, plus manifest loader/rows/cols | ✅ tracked, pinned |
| **rookie features (RB/WR/TE)** | — | — | ❌ **DOES NOT EXIST** — see §0b |
| coaching features (Design A) | `coaching/data/team_coach_features_design_a_v39.csv` | md5 `b3e5aa463fff10161cf3abb78e0854f2` |
| coaching features (Design B, oracle) | `coaching/data/team_coach_features_design_b_oracle_v39.csv` | md5 `5f8cf19b9aa4310b7eebbfb2406092c1` |
| arm manifest | `coaching/data/arm_feature_manifest_v39.json` | md5 `65b596906eec757018e5b37b367835c2` |
| coverage | `coaching/data/arm_feature_coverage_v39.csv` | md5 `807e38813cdd51800905e2b3c1a6d507` |
| lineage | `coaching/data/arm_feature_lineage_v39.csv` | md5 `fcf8692bedab4e23652486cdcfe8f0b0` |
| 18 protected artifacts | v3.8 + preliminary Arm 3 + 8 production models | as pinned in `UPSTREAM_PROTECTED` / `PRODUCTION_PINS` |

---

## 5. Outputs — files that will be NEWLY written

Nothing on this list exists today.

| path | contents |
|---|---|
| `coaching/data/arm_selection_v39.csv` | per outer season: selected arm, inner-fold scores |
| `coaching/data/arm_metrics_v39.csv` | pooled top-cohort MAE per arm per outer season |
| `coaching/data/arm_bootstrap_v39.csv` | 20,000-draw cluster bootstrap, seed 20260728 |
| `coaching/data/arm_placebo_v39.csv` | within-season team-level permutation null |
| `coaching/data/arm_verdict_v39.csv` | the §7 ten-condition verdict |
| `coaching/V39_REAL_RUN_REPORT.md` | the run report |

**No production model, projection, or existing artifact is written.** The five v3.9 artifacts and the
18 protected artifacts must be byte-identical before and after.

---

## 6. Preflight checks that must all pass (21)

`protected_hashes` · `v39_artifacts_pinned` · `v39_artifacts_readable` · `no_unauthorized_v39_artifact` ·
`no_coaching_parquet` · `feature_table_keys_and_rows` · `design_a_outer_identity_coverage` ·
`unknown_and_no_history_routing` · `forbidden_feature_policy` · `manifest_full_x_matches_bundles` ·
`manifest_qb_rookie_null` · `coverage_reconciles` · `lineage_strict_timing` ·
`lineage_states_the_primary_policy` · `contribution_lineage_reconciles` ·
`design_b_oracle_and_unselectable` · `production_models_identical` · `no_real_outcome_access` ·
`assembly_module_contract` · `pipeline_timing_assertions_ran` · `run_mode_locks`

`all_ok` must be `True` with `n_failed == 0` **before** the first outcome read. A single failure aborts
before any outcome is touched.

---

## 7. Stop conditions — abort the run and touch nothing further

- any preflight check fails;
- either lock is found closed at the moment of use;
- feature md5 or weekly-snapshot sha256 drift, or manifest provenance mismatch;
- the weekly frame is missing any of `player_id`, `season`, `season_type`, `fantasy_points`,
  `receptions`, or a non-`REG` row survives the filter;
- duplicate `(player_id, season)` keys in either frame;
- the feature frame carries a season outside `{2014..2025}` or a column outside the frozen contract;
- the panel season set is not exactly `{2014..2025}`, the outer set not exactly `{2018..2025}`, or
  team-seasons ≠ 256;
- any outcome-bearing column appears in any arm matrix or the full X;
- the accounting partition does not sum to the feature-row count;
- **any feature row is dropped** — production retains every eligible row and zero-fills, so a shrinking
  denominator is a stop condition, not a warning;
- Design B appears in any selection;
- any production artifact or v3.9 artifact hash changes.

---

## 8. Rollback / cleanup

1. `git status --short` — the six output files above are the ONLY new paths permitted.
2. Delete them: they are outputs, not inputs; no other file is touched.
3. Re-run `preflight` and the protected-hash check; 18/18 and the five pins must be unchanged.
4. Set `REAL_FIT_AUTHORIZED = False` and clear the environment variable.
5. `git checkout --` nothing: the run writes no tracked file.

Because the run writes only new files and mutates none, rollback is deletion plus re-verification.

---

## 9. Information that must NOT be examined until the run finishes

Until the §7 verdict is computed and written, do not look at, print, plot, aggregate or compare:

- any real outcome value, or any statistic of one;
- per-arm MAE, per-season MAE, or any arm-vs-arm comparison;
- bootstrap intervals or placebo draws;
- which arm was selected in any fold;
- McDaniel, McVay, Reid or any named-coach effect;
- Design B (oracle) results in any form.

The run is one shot. Looking at an intermediate result and then changing a threshold, a fold, an arm
definition, the selection rule, the placebo, or the verdict is the failure mode the entire
pre-registration exists to prevent. **No exploratory summary, no tuning, no threshold change, and no
prereg amendment may be informed by an observed result.**

---

**NOT EXECUTED. Joseph authorizes; Joseph commits.**
