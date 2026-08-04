# v3.9e ACTIVATION MANIFEST — the first real player-model run

**Status: NOT EXECUTED. NOT AUTHORIZED.** This document describes a run that has not happened. Both
real-fit locks are closed, no real outcome has been read, and no result artifact exists.

**The wiring is now BUILT (v3.9q).** `assemble_real_panel()` is implemented under the preregistered
C5-A contract; the seal has MOVED, not gone. The body contains **no reader callee at all** (C5-A
clause 3), so the module cannot read a file by itself: statement 1 refuses unless both locks are open,
statement 2 refuses unless run mode, preflight, readiness, the gate and every input pin all clear, and
the injected readers are called only in statement 3. With the locks closed, tripwire tests prove
**neither reader is ever touched**.

**The season-dataset blocker is RESOLVED (v3.9r), and not by re-pinning or reverting.** The earlier
description of it was too broad and is withdrawn: the 2026-08-03 change touched **season 2026 only** —
nine columns by float round-trip noise (max 3.5527e-15) and `qb_changed` on 916 rows — and **no
2014-2025 value differed** in any of the 47 columns. "1,572 changed rows" was `git --numstat` line
arithmetic, not a row count.

The fault was the PIN's scope: a mutable 2014-2026 file was pinned to protect an immutable 2014-2025
window. The experiment now reads a frozen, feature-only veteran snapshot
(`snapshots/veteran_arm0_features_2014_2025.parquet`, sha256 `45cb2583…`, 7,350 x 40) and never the
production CSV. The 2026 QB-change work was left exactly as written. See stop report §10.10.

**`activation_readiness()` returns `True`.** All seven shipped Arm 0 buckets have a complete,
repo-owned, pinned feature source with a well-formed bundle specification: four veteran buckets from
the frozen `snapshots/veteran_arm0_features_2014_2025.parquet` (v3.9r), and RB/WR/TE rookie from the frozen derived matrix
`snapshots/rookie_arm0_features_2014_2025.parquet`, which is now **point-in-time** (§0c).

Its history, so nobody re-derives it from a stale sentence: `False` v3.9g-v3.9m (no rookie source at
all); briefly `True` at v3.9n; `False` again at v3.9o on a "the rookie bundles were trained on the
contaminated join" blocker; and `True` now, because that blocker rested on a **FALSE PREMISE** and is
**WITHDRAWN** — the experiment builds a fresh estimator every fold and the serialized weights never
enter it (§0d).

**Readiness is NOT authorization.** `authorized_real_gate()` returns `False` **solely** because the
preflight result is a `synthetic_prefit` one and both real-fit locks are closed — gate 2 is clear.
`REAL_FIT_AUTHORIZED` is `False`, the environment lock is unset, `assemble_real_panel()` is sealed, no
real fantasy outcome has been read, and no result artifact exists. Nothing here may be executed without
Joseph's explicit written authorization and a committed PREFIT amendment.

---

## 0. THE OUTCOME PATH IS HERMETIC — and, since 2026-08-03, so is the seven-bundle FEATURE path

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

**Scope of that claim, corrected, then re-scoped twice.** A previous revision said flatly that "the
first authorized run is already hermetic". That was **WITHDRAWN** as an unqualified statement when it
covered only the OUTCOME path and the four VETERAN buckets. As of 2026-08-03 the seven-bundle feature
path is also repo-owned and pinned (§0b, Option A) — but **hermetic is not the same as correct**: the
first frozen rookie matrix was hermetic AND temporally contaminated (§0c). Three qualifications stand:
*regenerating* the rookie matrix still requires the authorized private PFF directory, which is
untracked by design; hermetic assembly is not authorization; and the shipped rookie bundles were fit
on the contaminated features, which is the current activation blocker.

---

## 0b. RESOLVED 2026-08-03 — Option A: the frozen rookie feature matrix

**Joseph selected Option A and confirmed he is authorized to use and commit PFF-*derived* feature
values, with the raw PFF files remaining private and untracked.** The record of the blocker as it
stood, and of how it was closed, is kept below because the decision changes what may be claimed about
hermeticity.

### The blocker, as measured

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
- that directory holds **941 local files (409 CSVs)** and **0 tracked files** — `git ls-files` returns nothing (the earlier **418** figure is **SUPERSEDED**; it matched no measurement of the directory),
  because `.gitignore:37` ignores it.

A clean checkout could not assemble the three rookie buckets at all. `activation_readiness()` returned
`False` and named them; it is a *separate layer* from `preflight()`, so the committed v3.9d prefit
checkpoint stayed green at 21/21 while activation was blocked.

Options B (external pinned artifact) and C (amend the experiment to drop rookie buckets, changing the
frozen population) were presented and are **not adopted**. C's row/cohort impact was deliberately never
quantified, and still is not.

### What Option A produced

```
fantasy/seasonal_projections/snapshots/rookie_arm0_features_2014_2025.parquet
sha256    7625980495886141efd65fb9c65862ef7f3cf8af67e50f231c6c3c12d9f45385   (v2, point-in-time)
shape     1,263 rows x 61 columns
keys      (player_id, season), unique
seasons   2014-2025, all twelve present
positions RB 387 · WR 584 · TE 292
generator fantasy/seasonal_projections/build_rookie_arm0_features.py
manifest  snapshots/manifest.json, key `rookie_arm0_features_2014_2025`, schema_version 2

SUPERSEDED  sha256 4b4655abde1c63d6316db2277d2a5301360842c9cec94fea0c2c5d77f5252584 (59 cols)
            INVALID — temporally contaminated PFF join. See §0c.
```

The 61 columns are 5 identity/routing keys (`player_id`, `season`, `position`, `is_rookie`,
`norm_name`), **2 point-in-time provenance columns** (`pff_receiving_source_season`,
`pff_rushing_source_season` — added in v2, in no bundle pool), plus the **54-column union** of the
three rookie bundle pools (RB 41, WR 44, TE 44; WR and TE are byte-identical), in a pinned order: RB's
pool in bundle order, then WR's 13 additional features in WR bundle order.

The two provenance columns make the point-in-time guarantee checkable **from the artifact alone**, with
no access to the private PFF library: for every row, the recorded source season must be strictly less
than the NFL rookie season.

**How it was built — the production path, not a parallel one.** The generator imports
`fantasy/rookie/harness/assemble_features.py` and calls the **real** `build_features()`. Only the two
network-backed nflverse loaders are injected, reading the pinned local snapshots
(`snapshots/draft_picks.parquet`, `snapshots/combine.parquet`); `_load_pff` is left untouched and reads
the authorized private directory. Nothing about the feature logic is reimplemented.

**What it does NOT contain.** No fantasy outcome, target, label, sample weight, ADP, market projection
or target-season realized statistic. Enforced three ways: the generator refuses to write if any column
name matches a forbidden token; `verify_rookie_matrix_provenance()` refuses to load a file whose schema
intersects `FORBIDDEN_IN_FEATURES`; and a parametrized test injects every forbidden column in turn and
asserts refusal.

**Null semantics are production's.** A player without a combine row, without a PFF row or without a
college-box row keeps that row with nulls. No proxy substitution, no imputation, no row dropped for
being incompletely measured, and the population is not amended. Measured non-null coverage by source
group (col counts 4/8/13/21/6): draft 54.7%, combine 37.2%, college 45.0%, PFF 42.8%, landing-spot 66.5%; every one of the 1,263
rows carries at least one null and every one is retained.

**Determinism.** Rows sorted by `(season, player_id)` with a stable mergesort, fixed dtypes (identity
as `string`, `season` int32, `is_rookie` int8, all 54 features float64), snappy, `index=False`. Two
fresh rebuilds reproduced the sha256 above byte-for-byte.

**Licensing posture.** Raw PFF files stay private and untracked: `fantasy/seasonal_projections/pff/`
holds **941 local files (409 CSVs)** and `git ls-files` returns **zero** of them (`.gitignore:37`). The **418** figure carried since v3.9g is **SUPERSEDED**. Only derived
feature values are repo-owned. A test asserts that tracked count is still zero.

**Storage order is not bundle order, and cannot be.** RB and WR order their shared features
differently, so no single physical column order equals all three bundle orders at once (RB inverts at
`coach_changed`; WR/TE at `cfb_rec_pg`). Storage order is pinned by the `ROOKIE_MATRIX_COLUMNS`
literal; the order a model would actually be fed is enforced separately, on the per-bucket frame, by
`rookie_bucket_frame()` → `bucket_frame_satisfies_bundle()`. An earlier draft of the validator checked
`matrix[list(fc)].columns != fc`, which is **vacuous** — selecting by name always returns that order —
and it was replaced.


---

## 0c. THE PFF TEMPORAL LEAK — the first frozen matrix was INVALID (found 2026-08-03)

**The defect.** `fantasy/rookie/harness/assemble_features.py::_load_pff` collapsed every PFF college
row with `groupby("norm_name")["season"].idxmax()` and merged on `norm_name` alone. The **source season
was discarded before the join**, so the latest college season carrying a name — very often a different,
later player — was attached to every panel row with that name.

**Measured on the frozen 1,263-row population** (whole panel unless noted):

| block | matches | source season >= NFL rookie season |
|---|---|---|
| receiving | 963 | **20** |
| rushing (whole panel) | 724 | **17** |
| rushing (RB rows, the bundle that uses it) | 308 | **8** |

28 leaked `(row, kind)` pairs over **22 unique rookie player-seasons** (WR 10, RB 9, TE 3), touching
**292 non-null feature cells** in the shipped artifact. Examples: 2014 Mike Evans took **2021**
receiving; 2016 Michael Thomas took **2025**; 2015 Matt Jones took **2025** receiving and rushing.

**Two distinct failure modes, separated:**

- **Class A — recoverable (21 of 37 leaked row-kind pairs).** An eligible earlier season existed for
  the name; `idxmax` simply picked a later one. The corrected join recovers the right season.
- **Class B — unrecoverable (16).** No PFF season precedes the NFL rookie season at all, so the matched
  row could never have been this player. These become NULL. Every 2014-class case is Class B: the PFF
  college library begins at 2014, and a 2014 NFL rookie's final college season is 2013.

21 of the 37 leaked pairs involve a `norm_name` mapping to more than one PFF `player_id` — genuine
same-name identity collisions, not merely mistimed lookups.

**The repair — one shared production implementation.** `_load_pff` is replaced by `_pff_long`
(retains the source season) and `_pff_point_in_time` (selects it). The rule, in order:

1. eligible = PFF rows for the name with `pff_season < reference_season`; a row at or after the
   reference season is **never** eligible;
2. no eligible row -> NULL;
3. one PFF identity -> that identity's latest eligible season;
4. several identities -> disambiguate by (a) position compatibility, then (b) presence in
   `reference_season - 1`; if neither is decisive -> **NULL**, because guessing is what caused the leak;
5. ties resolve deterministically: latest season, then most college games, then lowest PFF player id.

`build_features` now **refuses a panel with no reference-season column** rather than silently joining
without one, and asserts after the join that no attached source season reaches the reference season.
The matrix generator calls this same production function — there is no generator-only join.

**Effect on the artifact** (old vs new, same 1,263 rows, keys identical):

```
33 non-PFF feature columns          byte-identical
PFF non-null cells      11,343 -> 11,231     (4 gained, 116 lost, 181 changed)
rookie player-seasons with any PFF change        22    (WR 10 · RB 9 · TE 3)
of the 38 changed (row, kind) pairs: 28 were temporal leaks,
                                      1 was a same-name identity collision (jonathan williams,
                                        an NFL RB who was being given a college WR's row)
source-season lag (new)  receiving min 1 season · rushing min 1 season · zero rows with lag < 1
```

Cost of the conservative identity rule, stated: **3** rushing blocks are nulled because two same-name,
same-position players both appear in the eligible window (`matt jones` 2015, `tyree jackson` 2021,
`zach evans` 2023). A school-based disambiguator was considered and **rejected**: PFF `team_name` and
combine `school` share only 69 of 126 values, so matching them would be a fuzzy guess presented as
identity evidence — the same error class as the leak.

### THE ACTIVATION CONSEQUENCE — readiness stays False

Traced through the **generating code**, not inferred from bundle metadata:
`build_rb_projection.frozen_rb_matrix()` and its twins in `build_wr_projection.py` /
`build_te_projection.py` copy `assemble_features.py` into a temp directory and **execute** it, then fit
the shipped rookie bundles on its output. The three shipped rookie bundles were therefore **trained on
the contaminated join**. This is established, not UNKNOWN.

The feature builder is repaired and the matrix is rebuilt, but `rb_rookie_model.pkl`,
`wr_rookie_model.pkl` and `te_rookie_model.pkl` are **unchanged** — they still encode what the
contaminated features taught them. Feeding corrected features to a model fit on contaminated ones is a
different experiment from the one Arm 0 pins.

**This paragraph's original conclusion is WITHDRAWN.** It read that the rookie buckets were therefore
`training_contract_ok=False` and that readiness must stay `False`. That inference was wrong: the
experiment never uses the serialized estimator, so what those bundles were historically fit on cannot
reach a result. See §0d. `arm0_bucket_table()` now reports `spec_contract_ok`, and readiness is `True`.

What remains true from this section is the **feature** repair and one production note: the builder is
shared, so the next run of `build_rb_projection.py` (or the WR/TE twins) will fit on point-in-time
features and will produce different bundles. Nothing was retrained here.


---

## 0d. WITHDRAWN — the "contaminated trained bundles" blocker. ARM 0 refits from scratch.

**A v3.9o revision of this manifest refused activation on the grounds that the shipped rookie bundles
had been FIT on the pre-repair PFF join, so their weights were contaminated. That blocker rested on a
FALSE PREMISE and is WITHDRAWN.** The serialized estimator never enters this experiment. Verified by
reading the harness, not by assertion:

- **`arm0_definition()` returns metadata only.** Its single touch of the stored estimator is
  `type(b["model"]).__module__ + "." + type(b["model"]).__name__` — a class-name **string**. The object
  is not placed in the returned spec. An AST test asserts `bundle["model"]` appears only inside
  `type(...)`.
- **`fit_predict(spec, train, test, features)` builds a NEW estimator every call** via
  `RB._make_model(spec["family"], spec["params"])`, fits it on that fold's own training rows, and
  predicts from that fresh object. `bundle["model"]` is never fitted and never predicted from.
- **Every inner and outer fold repeats construct-and-fit**, so nothing survives across folds.
- **`inner_cv_mae` is a metadata record and is never used for selection.**

Pinned permanently by `tests/test_arm0_refits_from_scratch_v39.py`. Its decisive test replaces every
bundle's stored estimator with a sentinel that raises on ANY attribute access or call, runs the full
nested pipeline, and shows the metrics and selection frames are **identical** to the canonical run — a
prediction sourced from the stored object would detonate, and stale state would diverge.

**What the experiment DOES inherit from a shipped bundle** is its *specification*: `feature_cols`
(order included), `family`, `params`, `median_impute`, `seed`, `target`. Those are now pinned by value
in `tests/arm0_bundle_pins.py::BUNDLE_SPEC_PINS`, checked against disk, with a RED control proving a
mutated pin does not silently pass. `arm0_bucket_table()` reports `spec_contract_ok` in place of the
withdrawn `training_contract_ok`.

**The corrected point-in-time matrix is what every fold trains on** — the rookie buckets declare it as
their source, it is hash-pinned, and a test spies on every `fit_predict` call to assert no fold frame
carries a PFF block at or after its own season.

### The limitation that IS real — disclosed, deliberately NOT gated

The fixed production hyperparameters (`family`, `params`, `median_impute`, `seed`) were **selected
under the historical production pipeline**, which used the pre-repair PFF join. They are **frozen
pre-experiment and applied identically to ARM_0 and every coaching arm**, and the experiment **does not
retune** them.

This is a limitation of the comparison's absolute level, not a leakage path into the arm contrast:
a hyperparameter common to every arm cannot differentially favour one. It is therefore recorded in
`FROZEN_HYPERPARAMETER_DISCLOSURE` and stated here, and it is **not** an activation gate. Retuning them
under the corrected features would be a different, retrospectively-specified experiment and is not
authorized.

**Nothing was retrained.** All 18 protected artifacts and the 8 production model bundles are
byte-identical to their pins.

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

**LIVE as of 2026-08-03 (v3.9q): `ENTRY_POINT_CONTRACT_MODE = authorized_real`.** The door is
implemented and C5-A is the enforced contract; `_entry_point_is_sealed(tree, contract_mode)` dispatches
on that constant. C5-S has not been deleted — it is still implemented and still self-tested, on
constructed sources, by `test_C5_S_still_ACCEPTS_the_sealed_shape` and by the ten C5-S corpus
injections. The constant declares only the SHAPE of the door: `DEFAULT_RUN_MODE` remains
`synthetic_prefit`, `REAL_FIT_AUTHORIZED` remains `False`, and the environment lock remains unset.

**Where the seal went.** C5-A clause 3 forbids any reader callee inside the body, so the implemented
door cannot reach data by itself. Statement 1 (`require_real_fit_authorization`) refuses unless both
locks are open; statement 2 (`require_preflight_clearance`) refuses unless the run mode is
`authorized_real`, both locks are open, preflight is 21/21 in `authorized_real` mode,
`activation_readiness()` is True, `authorized_real_gate()` is True, and every pinned input matches;
only statement 3 calls the injected readers. `test_activation_wiring_v39.py` asserts with tripwires
that in every closed or partial lock state, and in `synthetic_prefit` mode with both locks open,
**neither reader is called at all**.

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

**All four inputs now exist, are tracked and are pinned.** The rookie-feature line below read "DOES NOT
EXIST" from v3.9g through v3.9m; it was closed on 2026-08-03 by Option A (§0b).

| input | path | pin | status |
|---|---|---|---|
| veteran features | `fantasy/seasonal_projections/snapshots/veteran_arm0_features_2014_2025.parquet` | sha256 `45cb2583acf7d046ecf54275d1ee3e70fcb9e4882d69a6b203e36350376bfbc8`, plus manifest rows/cols/seasons/keys/schema/generator and the exact 40-column ordered schema | ✅ v3.9r — feature-only, 2014-2025, IMMUTABLE. Replaces the whole-CSV md5 pin, which moved on an ordinary deploy-season refresh (§0c/§10.10). The CSV is the generator's input only. |
| weekly stats → the target | `fantasy/seasonal_projections/snapshots/player_stats_2011_2025.parquet` | sha256 `e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344`, plus manifest loader/rows/cols | ✅ tracked, pinned |
| combine measurements (a rookie-feature INPUT) | `fantasy/seasonal_projections/snapshots/combine.parquet` | sha256 `1b6c48a0b56e515b043dd678ea38a2e6ae83cb9de488e6a0a89f8b2f980bf2cf` | ✅ frozen 2026-08-03, manifest key `combine` |
| **rookie features (RB/WR/TE)** | `fantasy/seasonal_projections/snapshots/rookie_arm0_features_2014_2025.parquet` | sha256 `7625980495886141efd65fb9c65862ef7f3cf8af67e50f231c6c3c12d9f45385`, plus manifest rows/cols/seasons/keys/positions/generator, the 61-column ordered schema literal, and the consumed-PFF digest `148e2465…` over 36 files | ✅ v2 point-in-time, 2026-08-03. The v1 artifact (`4b4655ab…`, 59 cols) is **INVALID** — see §0c |

**Snapshot provenance checkpoint, 2026-08-03.** Under explicit one-time authorization, the public
nflverse combine asset was fetched **once** from
`https://github.com/nflverse/nflverse-data/releases/download/combine/combine.parquet` and frozen
byte-for-byte: 374,318 bytes, 8,968 rows × 18 columns, seasons 2000–2026 (the frozen 2014–2025 rookie
window is fully inside it). It carries no fantasy outcome, target, projection, ADP, market or
sample-weight column, and the measurements are pre-draft, so they are point-in-time for every rookie
season. `bmi` and `speed_score` are **not** source fields — production derives them from `ht`/`wt`/
`forty`, and a test pins that distinction.

This closed the last missing INPUT for the rookie matrix. It is **not** the rookie matrix; readiness
stayed **False** until the derived, outcome-free matrix was built the same day (§0b), at which point it
became **True**.

Verified by `tests/test_combine_snapshot_provenance.py` — 9 tests, no network, no `load_combine` call.
One of them **exercises production rather than copying it**: it imports
`fantasy/rookie/harness/assemble_features.py` and calls the real `build_features()` with
`nfl.load_draft_picks` and `nfl.load_combine` injected from the local snapshots and `_load_pff` stubbed
to an empty frame, so no private PFF file is read and no network call is reachable. It asserts the real
output attaches the expected identity and produces `ht_in`, `bmi` and `speed_score` with production's
own formulas. An earlier version of that test re-implemented those formulas in the test body — a
parallel implementation, which is not production-equivalence evidence.
| coaching features (Design A) | `coaching/data/team_coach_features_design_a_v39.csv` | md5 `b3e5aa463fff10161cf3abb78e0854f2` |
| coaching features (Design B, oracle) | `coaching/data/team_coach_features_design_b_oracle_v39.csv` | md5 `5f8cf19b9aa4310b7eebbfb2406092c1` |
| arm manifest | `coaching/data/arm_feature_manifest_v39.json` | md5 `65b596906eec757018e5b37b367835c2` |
| coverage | `coaching/data/arm_feature_coverage_v39.csv` | md5 `807e38813cdd51800905e2b3c1a6d507` |
| lineage | `coaching/data/arm_feature_lineage_v39.csv` | md5 `fcf8692bedab4e23652486cdcfe8f0b0` |
| 18 protected artifacts | v3.8 + preliminary Arm 3 + 8 production models | as pinned in `UPSTREAM_PROTECTED` / `PRODUCTION_PINS` |

---

## 4b. EVALUATION ELIGIBILITY — a pre-outcome population amendment (2026-08-03)

A row is eligible only when `team` is non-null (so OC/HC exposure is DEFINED) **and** its
`(position, bucket)` has a shipped Arm 0 bundle. Decided from the frozen feature frame before any
outcome access, applied identically to ARM_0 and every coaching arm, and never imputed or proxied.

```
source_population                  7,350
excluded_missing_team                 80    (WR 31 · TE 20 · RB 15 · QB 14, all veteran)
excluded_no_shipped_bundle           117    (QB/rookie — the arm was HELD)
eligible_evaluation_population     7,153
```

Mutually exclusive (overlap 0) and exhaustive, both measured. Neutral imputation was rejected because
it invents exposure. The 117 QB/rookie rows were already outside the shipped seven-bundle experiment;
they are now excluded explicitly with a reason and a count rather than skipped silently. The counts
ride in `arm_verdict_v39.csv` under an `eligibility_` prefix — no sixth artifact. Stop report §10.13.

## 5. Outputs — files that will be NEWLY written

**AMENDED 2026-08-03 (Option A, pre-outcome, operational only): the five results live in
`coaching/results/`, NOT `coaching/data/`.** The original paths contradicted the exact input-artifact
gate: `no_unauthorized_v39_artifact` requires the `*_v39.*` set in `coaching/data/` to equal exactly
the five FEATURE artifacts, so writing results there took preflight from 21/21 to 20/21 (measured).
`V39_ARTIFACT_HASHES` and that check are UNCHANGED. **Storage moved; the experiment did not** — no
population, feature, arm, hyperparameter, threshold, selection rule or verdict criterion is affected.

**Also corrected:** an earlier revision of this document described a command
(`--run-mode authorized_real --outer-seasons 2018-2025`) and five writers that **did not exist**.
`main()` had no `--run-mode`, `--real` was an unconditional `SystemExit`, and no module wrote any
result file. Both are now implemented — see stop report §10.11 — and the CLI below is the real one.

`run_experiment` returns SEVEN frames and §5 defines FIVE files; the lossless mapping folds `oracle`
into `arm_metrics_v39.csv` under `record_type` and `preflight` into `arm_verdict_v39.csv` under a
`preflight_` prefix, with round-trip tests recovering both exactly from the serialized files.

Nothing on this list exists today.

| path | contents |
|---|---|
| `coaching/results/arm_selection_v39.csv` | per outer season: selected arm, inner-fold scores |
| `coaching/results/arm_metrics_v39.csv` | pooled top-cohort MAE per arm per outer season |
| `coaching/results/arm_bootstrap_v39.csv` | 20,000-draw cluster bootstrap, seed 20260728 |
| `coaching/results/arm_placebo_v39.csv` | within-season team-level permutation null |
| `coaching/results/arm_verdict_v39.csv` | the §7 ten-condition verdict |
| `coaching/V39_REAL_RUN_REPORT.md` | the run report |

**No production model, projection, or existing artifact is written.** The five v3.9 artifacts and the
18 protected artifacts must be byte-identical before and after.

---

## 6. REQUIRED ACTIVATION GATES — both, before any outcome reader

**A previous revision of this report claimed these gates were already mandatory here. They were not —
this section did not exist. That claim is WITHDRAWN and the requirement is written below.**

Two gates, both mandatory, evaluated by `assemble_real_panel_v39.authorized_real_gate()`:

1. **`preflight()` returns 21/21 IN `authorized_real` MODE** — `all_ok is True`,
   `run_mode == "authorized_real"`, `n_checks == 21`, `n_failed` exactly integer `0`, a `checks` dict
   carrying exactly the 21 expected names each explicitly `ok`, and no non-empty `failures`.
   A `synthetic_prefit` result **can never** authorize a real run: its meaning is that both locks are
   CLOSED.
2. **`activation_readiness() == True`** — every shipped Arm 0 bucket must have a complete pinned
   feature source and a well-formed bundle SPECIFICATION (feature order, family, params, null handling,
   seed, target). **It is currently `True`.** Gate 2 is clear; the refusal is gate 1 alone. Readiness
   does NOT require that a bundle's historical training matrix match the corrected one, because the
   experiment refits from scratch every fold and never uses the serialized estimator (§0d).

**`authorized_real_gate()` MUST execute and return `True` BEFORE any outcome reader is called.** No
outcome may be read, and `assemble_panel_core` may not be invoked on real data, until it has passed.
Anything missing, malformed, synthetic-mode, partially locked or self-contradictory refuses.

These requirements are pinned by `test_the_manifest_states_the_required_activation_gates`.

## 6b. Preflight checks that must all pass (21)

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

- **`activation_readiness()` returns False** — on its own it stops the run. It currently returns
  **True**, so this condition is not the one holding the run back; gate 1 is;
- **`authorized_real_gate()` returns False** for any reason, including a preflight result that is
  missing, malformed, in `synthetic_prefit` mode, or self-contradictory;
- any attached PFF block carries a source season >= the row's rookie season, or a rookie-matrix
  provenance column is absent (the point-in-time contract, §0c);
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
