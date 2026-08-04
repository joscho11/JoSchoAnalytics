"""Real-panel assembly for the coach-quality experiment — BUILT AND TESTED, NOT ACTIVATED.

This module contains the join, validation and accounting that a future AUTHORIZED run will use to put
a real fantasy outcome beside the frozen coaching features. It reads nothing by itself: every reader is
injected or explicitly constructed, and the whole path is exercised in the test suite against synthetic
and temporary fixtures only.

WHAT IS HERMETIC, AND WHAT IS NOT — the exact scope
---------------------------------------------------
**The OUTCOME path and the four VETERAN feature buckets are hermetic. The full seven-bundle run is NOT
activation-ready.** Two earlier claims are withdrawn: that the Arm 0 outcome was not repo-owned (false),
and then that "the first authorized run is already hermetic" (an unqualified all-clear that was true only
of the outcome and veteran paths).

HERMETIC — the outcome. The repository owns and pins the weekly player stats:

    fantasy/seasonal_projections/snapshots/player_stats_2011_2025.parquet
    sha256 e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344
    loader nflreadpy.load_player_stats, 269,594 rows x 115 cols, seasons 2011-2025

and `wr_recent_full_game_features_harness.build_panel()` already reproduces
`build_rb_projection.season_total_target()` from it, so the outcome needs no fetch and no new artifact.

THE FEATURES — both sources are repo-owned, pinned, and composed under the FROZEN routing.
Arm 0 ships SEVEN bundles. `SHIPPED_ARM0_BUCKETS` assigns the four VETERAN buckets to
`snapshots/veteran_arm0_features_2014_2025.parquet` and the RB/WR/TE ROOKIE buckets to
`snapshots/rookie_arm0_features_2014_2025.parquet`. `authorized_composed_feature_reader()` verifies
both independently and merges them on the frozen panel keys, with the veteran snapshot as the
population/routing spine. QB/rookie is deliberately absent from that mapping — the arm was HELD — and
those spine rows keep veteran-source values.

The earlier statement here that the rookie buckets "have no repo-owned source at all" is SUPERSEDED:
that was true from v3.9g to v3.9m and was resolved by Option A on 2026-08-03.

WHY THIS IS A SEPARATE MODULE
-----------------------------
`run_coach_projection_experiment_v39.py` is governed by contract C1-C7 + C4b, whose clause C4 forbids a
`BANNED_OUTCOME_TOKENS` substring in ANY executable string constant of that module. Assembly code must
name outcome columns, so putting it there would force C4 to be weakened for the module it exists to
protect. The assembly therefore lives here under its own contract (A1-A6, enforced as a preflight
check), and `V39_SOURCE_MODULES` is left exactly as it was.

STATE OF THE DOOR
-----------------
`run_coach_projection_experiment_v39.assemble_real_panel()` is STILL SEALED. This module does not touch
it. Activation is a documented change recorded in `V39_ACTIVATION_MANIFEST.md`.
"""
import hashlib
import json
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
SEAS = HERE.parent.parent / "seasonal_projections"
SNAPSHOTS = SEAS / "snapshots"

# =====================================================================================================
# FROZEN INPUTS — both repo-owned, both pinned
# =====================================================================================================
# --- the VETERAN feature input -----------------------------------------------------------------
# An earlier revision pinned the whole production CSV by md5. That was the WRONG SCOPE: the file is a
# LIVE artifact carrying deploy-season 2026, so an ordinary 2026 refresh moved the hash and refused
# activation for a reason unrelated to the experiment's inputs. Measured on the 2026-08-03 refresh:
# every difference was confined to season 2026; nine columns differed only by CSV float round-trip
# noise (max |diff| 3.5527e-15, no null flips); the one substantive change was `qb_changed` on 916
# rows of 2026; and NO 2014-2025 value differed, bitwise, in any of the 47 columns.
#
# The experiment now reads an IMMUTABLE, feature-only 2014-2025 snapshot instead. Building it from the
# pre-refresh copy of the CSV reproduces the same sha256, which is asserted by test.
VETERAN_SNAPSHOT = SNAPSHOTS / "veteran_arm0_features_2014_2025.parquet"
VETERAN_SNAPSHOT_SHA256 = "45cb2583acf7d046ecf54275d1ee3e70fcb9e4882d69a6b203e36350376bfbc8"
VETERAN_SNAPSHOT_MANIFEST_KEY = "veteran_arm0_features_2014_2025"
VETERAN_SNAPSHOT_GENERATOR = "fantasy/seasonal_projections/build_veteran_arm0_snapshot.py"
VETERAN_SNAPSHOT_ROWS = 7350
VETERAN_SNAPSHOT_COLS = 40

# The generator's input, and the ONLY thing that still points at the mutable CSV. The authorized
# experiment never reads it; `verify_pinned_activation_inputs` does not hash it.
FEATURE_SOURCE = SEAS / "season_dataset_2014_2026.csv"

WEEKLY_SNAPSHOT = SNAPSHOTS / "player_stats_2011_2025.parquet"
WEEKLY_SNAPSHOT_SHA256 = "e8dad7e48fd202d414d66f5a14fb23f72d4bdb5a1b60a09c5d71556444203344"
WEEKLY_SNAPSHOT_MANIFEST_KEY = "player_stats_2011_2025"
WEEKLY_SNAPSHOT_LOADER = "load_player_stats"
WEEKLY_SNAPSHOT_ROWS = 269_594
WEEKLY_SNAPSHOT_COLS = 115
SNAPSHOT_MANIFEST = SNAPSHOTS / "manifest.json"

PLAYER_KEY = "player_id"
SEASON_KEY = "season"
PANEL_KEYS = (PLAYER_KEY, SEASON_KEY)

# =====================================================================================================
# THE CANONICAL PANEL-KEY CONTRACT (v3.9x)
# =====================================================================================================
# The first authorized real run reached the adapter and refused with "the join reordered the feature
# rows". The rows were NOT reordered. The feature reader emitted `player_id` as pandas
# `string[python]`; the outcome reader emitted it as numpy `object`; the merge resolved the key to
# `object`; and the adapter's assertion used `DataFrame.equals`, which compares DTYPES as well as
# values. A pure dtype disagreement between the two readers was reported as a row-ordering failure.
#
# The repair is a contract, not a relaxation. ONE canonical key schema is defined here and enforced at
# BOTH real reader boundaries, so the two sides cannot disagree in the first place; the adapter then
# checks dtype and ordering SEPARATELY and names whichever actually failed.
PANEL_KEY_DTYPES = {
    PLAYER_KEY: pd.StringDtype(storage="python"),
    SEASON_KEY: np.dtype("int32"),
}
# nflverse gsis ids are `00-00XXXXX`; the frozen panel window is 2014-2025. The season bound is wide
# on purpose — it rejects a corrupt or overflowing value, not a legitimate one.
SEASON_MIN, SEASON_MAX = 1920, 2100
# Strings that a careless `astype(str)` would manufacture out of a NULL. A player id equal to any of
# these is a null that has already been stringified upstream, and it must not be accepted as identity.
STRINGIFIED_NULLS = ("nan", "none", "null", "na", "n/a", "<na>", "nat", "")


def canonical_key_dtype_problems(frame, where):
    """Report every key column whose dtype is not the canonical one. Never raises, never converts."""
    problems = []
    for key, want in PANEL_KEY_DTYPES.items():
        if key not in frame.columns:
            problems.append(f"{where}: key column {key!r} is missing")
            continue
        got = frame[key].dtype
        if got != want:
            problems.append(f"{where}: key {key!r} has dtype {got!r}, canonical is {want!r}")
    return problems


def canonicalize_panel_keys(frame, where):
    """Return `frame` with the panel keys in the CANONICAL dtypes, validating before converting.

    Deliberately NOT `astype(str)` / `astype("int32")`. A blind cast is how a null becomes the literal
    string "nan" and how 2018.7 or a 2**40 season silently becomes a plausible integer. Every rejection
    below is checked BEFORE any conversion, so a bad value refuses rather than being manufactured into
    a good-looking one:

      player_id   must already be textual (object-of-str or a pandas string dtype) — a numeric or
                  categorical id column is refused, not coerced; no nulls; no value that is a
                  stringified null; no blank/whitespace-only id.
      season      must be integral in VALUE (a float column is accepted only if every value is exactly
                  integral), non-null, and inside [SEASON_MIN, SEASON_MAX] so the int32 narrowing is
                  provably lossless. The round-trip is verified after conversion.
    """
    missing = [k for k in PANEL_KEYS if k not in frame.columns]
    if missing:
        raise AssemblyError(f"{where}: missing panel key column(s) {missing}")

    out = frame.copy()

    # ---- player_id -------------------------------------------------------------------------------
    col = out[PLAYER_KEY]
    if col.isna().any():
        raise AssemblyError(f"{where}: {PLAYER_KEY} has {int(col.isna().sum())} null value(s); "
                            f"identity must be resolved before canonicalization")
    is_text = isinstance(col.dtype, pd.StringDtype) or (
        col.dtype == object and col.map(lambda v: isinstance(v, str)).all())
    if not is_text:
        raise AssemblyError(f"{where}: {PLAYER_KEY} has dtype {col.dtype!r} and is not textual; "
                            f"a non-string player id is refused, never coerced with astype(str)")
    stripped = col.astype(object).map(lambda v: v.strip())
    bad = stripped[stripped.str.lower().isin(STRINGIFIED_NULLS)]
    if len(bad):
        raise AssemblyError(f"{where}: {PLAYER_KEY} has {len(bad)} value(s) that are stringified "
                            f"nulls or blank, e.g. {sorted(set(bad))[:5]}; these are missing "
                            f"identities, not identifiers")
    out[PLAYER_KEY] = pd.array(col.astype(object).to_numpy(), dtype=PANEL_KEY_DTYPES[PLAYER_KEY])

    # ---- season ----------------------------------------------------------------------------------
    col = out[SEASON_KEY]
    if col.isna().any():
        raise AssemblyError(f"{where}: {SEASON_KEY} has {int(col.isna().sum())} null value(s)")
    if not pd.api.types.is_numeric_dtype(col) or pd.api.types.is_bool_dtype(col):
        raise AssemblyError(f"{where}: {SEASON_KEY} has dtype {col.dtype!r}; it must be numeric")
    as_float = col.astype("float64")
    fractional = as_float[as_float != np.floor(as_float)]
    if len(fractional):
        raise AssemblyError(f"{where}: {SEASON_KEY} has {len(fractional)} non-integral value(s), "
                            f"e.g. {sorted(set(fractional))[:5]}")
    lo, hi = float(as_float.min()), float(as_float.max())
    if lo < SEASON_MIN or hi > SEASON_MAX:
        raise AssemblyError(f"{where}: {SEASON_KEY} range [{lo:.0f}, {hi:.0f}] is outside "
                            f"[{SEASON_MIN}, {SEASON_MAX}]; the int32 narrowing would be lossy")
    narrowed = as_float.astype(PANEL_KEY_DTYPES[SEASON_KEY])
    if not np.array_equal(narrowed.astype("float64").to_numpy(), as_float.to_numpy()):
        raise AssemblyError(f"{where}: {SEASON_KEY} did not survive the int32 round trip; "
                            f"the conversion would be lossy")
    out[SEASON_KEY] = narrowed

    # ---- non-null and unique ---------------------------------------------------------------------
    dup = out.duplicated(subset=list(PANEL_KEYS)).sum()
    if dup:
        raise AssemblyError(f"{where}: {int(dup)} duplicate {list(PANEL_KEYS)} row(s); panel keys "
                            f"must be unique")

    residual = canonical_key_dtype_problems(out, where)
    if residual:                                          # unreachable by construction; asserted anyway
        raise AssemblyError("canonicalization did not produce the canonical dtypes: "
                            + "; ".join(residual))
    return out


def ordered_key_values(frame):
    """The key columns as a plain object array — dtype-free, so ORDER can be compared on its own."""
    return frame[list(PANEL_KEYS)].astype(object).to_numpy()

# The Arm 0 target, reproduced EXACTLY as production defines it.
OUTCOME_COLUMN = "season_total_half_ppr"
WEEKLY_REQUIRED_COLUMNS = (PLAYER_KEY, SEASON_KEY, "season_type", "fantasy_points", "receptions")
REG_SEASON_TYPE = "REG"
TARGET_FORMULA = "sum over REG weeks of (fantasy_points.fillna(0) + 0.5 * receptions.fillna(0))"

# Panel window. The feature source runs to 2026 (the deploy season, which has no observed outcome);
# the evaluation panel is 2014-2025 and the reader filters to it BEFORE returning.
PANEL_FIRST_SEASON, PANEL_LAST_SEASON = 2014, 2025
ALL_PANEL_SEASONS = tuple(range(PANEL_FIRST_SEASON, PANEL_LAST_SEASON + 1))
OUTER_SEASONS = tuple(range(2018, 2026))
DEPLOY_SEASON = 2026
REQUIRED_OUTER_TEAM_SEASONS = 256

# --- the frozen feature-column contracts, PER BUCKET -------------------------------------------------
# Arm 0 ships SEVEN bundles, not four. The 32 ordered veteran features below are identical across all
# four veteran bundles (asserted by `arm0_definition`) and every one of them is in the season dataset.
# The three ROOKIE bundles need 41/44/44 features, of which 32/35/35 are NOT in the season dataset —
# they are combine, college-box and PFF-derived. An earlier revision defined the contract as
# "identity + the 32 veteran features" and called that the Arm 0 feature contract. It is not: it covers
# four of seven bundles. The veteran contract is scoped as such below, and the rookie buckets are
# declared with NO input path until Joseph decides (see V39_ACTIVATION_MANIFEST.md §0b).
ARM0_VETERAN_FEATURES = (
    "prior_ppg", "prior_half_ppr", "prior_games", "ppg_2yr", "ppg_3yr", "ppg_trend",
    "career_high_ppg", "prior_snap_share_pg", "prior_targets_pg", "prior_carries_pg",
    "prior_receptions_pg", "prior_touches_pg", "prior_target_share", "prior_air_yards_share",
    "prior_adot", "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa", "prior_rush_epa",
    "age", "years_exp", "draft_round", "draft_pick", "prior_team_pass_rate", "prior_team_plays",
    "vacated_target_share", "vacated_rush_share", "coach_changed", "qb_changed",
    "prior_games_missed", "missed_prior_season",
)
IDENTITY_COLUMNS = (PLAYER_KEY, "player", "norm_name", "position", "team", SEASON_KEY,
                    "reconstructed", "is_rookie")

# The VETERAN contract only. Named so nobody can mistake it for the full Arm 0 contract again.
VETERAN_FEATURE_COLUMNS = IDENTITY_COLUMNS + ARM0_VETERAN_FEATURES
FROZEN_FEATURE_COLUMNS = VETERAN_FEATURE_COLUMNS          # backwards-compatible alias, veteran scope

# Declared input sources. BOTH are now repo-owned and pinned: Option A was authorized on 2026-08-03 and
# the derived, outcome-free rookie matrix was frozen (raw PFF stays private and untracked).
SOURCE_SEASON_DATASET = "season_dataset"
SOURCE_ROOKIE_MATRIX = "rookie_matrix"
SOURCE_UNRESOLVED = None

ROOKIE_MATRIX = SNAPSHOTS / "rookie_arm0_features_2014_2025.parquet"
ROOKIE_MATRIX_SHA256 = "7625980495886141efd65fb9c65862ef7f3cf8af67e50f231c6c3c12d9f45385"
ROOKIE_MATRIX_MANIFEST_KEY = "rookie_arm0_features_2014_2025"
ROOKIE_MATRIX_GENERATOR = "fantasy/seasonal_projections/build_rookie_arm0_features.py"
ROOKIE_MATRIX_ROWS = 1263
ROOKIE_MATRIX_COLS = 61
ROOKIE_MATRIX_POSITIONS = ("RB", "TE", "WR")
ROOKIE_MATRIX_IDENTITY = (PLAYER_KEY, SEASON_KEY, "position", "is_rookie", "norm_name")
# Point-in-time provenance carried IN the artifact: the PFF college season each block came from. Not
# features, in no bundle pool. They make the guarantee checkable offline, without the private library:
# every non-null value must be STRICTLY LESS than the row's rookie season.
ROOKIE_MATRIX_PROVENANCE = ("pff_receiving_source_season", "pff_rushing_source_season")
# The private PFF inputs the matrix was derived from, fingerprinted without exposing any content:
# one sha256 over the sorted relative paths + bytes of exactly the 36 files the build consumes.
ROOKIE_MATRIX_PFF_SHA256 = "148e2465abb6389cdd4e741dee21f0d168638f91dc23f66407950d2fbd718038"
ROOKIE_MATRIX_PFF_FILES = 36
# The EXACT ordered schema, pinned here INDEPENDENTLY of the generator: a rebuild that reorders or
# adds a column changes the hash AND fails this literal, so neither pin can silently absorb the other.
ROOKIE_MATRIX_COLUMNS = (
    "player_id", "season", "position", "is_rookie", "norm_name",
    "pff_receiving_source_season", "pff_rushing_source_season",
    "draft_round", "draft_pick", "log_pick", "age",
    "forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "ht_in", "wt", "bmi", "speed_score",
    "cfb_final_dom", "cfb_best_dom", "cfb_scrim_ypg", "cfb_rush_ypg", "cfb_rec_ypg", "cfb_ypc",
    "cfb_ypr", "cfb_career_scrim_yds", "cfb_career_scrim_td", "cfb_seasons", "cfb_breakout_class",
    "pff_rushing_grades_run", "pff_rushing_grades_offense", "pff_rushing_elusive_rating",
    "pff_rushing_breakaway_percent", "pff_rushing_elu_yco", "pff_rushing_avoided_tackles",
    "pff_rushing_first_downs", "pff_rushing_touchdowns", "pff_receiving_yprr", "pff_receiving_routes",
    "coach_changed", "qb_changed", "prior_team_pass_rate", "prior_team_plays",
    "vacated_target_share", "vacated_rush_share",
    "cfb_rec_pg", "cfb_final_recshare",
    "pff_receiving_grades_offense", "pff_receiving_grades_pass_route",
    "pff_receiving_avg_depth_of_target", "pff_receiving_contested_catch_rate",
    "pff_receiving_drop_rate", "pff_receiving_yards_after_catch_per_reception",
    "pff_receiving_targeted_qb_rating", "pff_receiving_receptions", "pff_receiving_yards",
    "pff_receiving_touchdowns", "pff_receiving_avoided_tackles",
)

# (position, bucket) -> the bundle that ships it, and the input that must supply its features.
SHIPPED_ARM0_BUCKETS = {
    ("QB", "veteran"): ("qb_veteran_model.pkl", 32, SOURCE_SEASON_DATASET),
    ("RB", "veteran"): ("rb_veteran_model.pkl", 32, SOURCE_SEASON_DATASET),
    ("WR", "veteran"): ("wr_veteran_model.pkl", 32, SOURCE_SEASON_DATASET),
    ("TE", "veteran"): ("te_veteran_model.pkl", 32, SOURCE_SEASON_DATASET),
    ("RB", "rookie"): ("rb_rookie_model.pkl", 41, SOURCE_ROOKIE_MATRIX),
    ("WR", "rookie"): ("wr_rookie_model.pkl", 44, SOURCE_ROOKIE_MATRIX),
    ("TE", "rookie"): ("te_rookie_model.pkl", 44, SOURCE_ROOKIE_MATRIX),
}
# QB/rookie is deliberately ABSENT: the QB rookie arm was HELD, and the prereg records QB as evaluated
# on the veteran path only.
MODELS_DIR = HERE.parent / "models"

# --- TWO DIFFERENT MISSINGNESS CONCEPTS, kept apart ---------------------------------------------
# They were previously conflated, which produced an internally inconsistent readiness message: the
# headline said "RB 32/41" while the per-bucket line said "41/41 missing from rookie_matrix". Both were
# true of DIFFERENT denominators, and printing them together made the report contradict itself.
#
#   n_missing_from_season_dataset : how many of a bundle's features the SEASON DATASET lacks. This is
#                                   the substantive fact about what a rookie matrix would have to
#                                   supply. Measured, not asserted (see `arm0_bucket_table`).
#   n_missing_from_declared_source: how many the bucket's OWN declared source lacks. For a veteran
#                                   bucket the declared source IS the season dataset, so the two
#                                   coincide at 0. For a rookie bucket the declared source does not
#                                   exist, so this is trivially the whole pool — a statement about
#                                   the source being absent, NOT about the feature overlap.
#
# Measured 2026-07-30 against season_dataset_2014_2026.csv (47 columns); recomputed and asserted by
# `test_the_rookie_missing_counts_are_derived_not_asserted`.
ROOKIE_MISSING_FROM_SEASON_DATASET = {("RB", "rookie"): (32, 41), ("WR", "rookie"): (35, 44),
                                      ("TE", "rookie"): (35, 44)}
# --- WITHDRAWN: the "contaminated trained bundles" activation blocker -------------------------------
# A v3.9o revision of this module refused activation on the grounds that the shipped rookie bundles had
# been FIT on the pre-repair PFF join, so their learned weights were contaminated. **That blocker rested
# on a FALSE PREMISE and is WITHDRAWN.** The serialized estimator never enters this experiment:
#
#   * `arm0_definition()` returns METADATA ONLY. Its single touch of `bundle["model"]` is
#     `type(b["model"]).__module__ + "." + type(b["model"]).__name__` — a class-name STRING. The
#     estimator object is not placed in the returned spec.
#   * `fit_predict(spec, train, test, features)` calls `RB._make_model(spec["family"], spec["params"])`
#     and fits THAT fresh estimator on the fold's own training rows. Its `predict` is called on the
#     fresh model. `bundle["model"]` is never fitted, never predicted from, never unpickled into a
#     prediction path.
#   * every inner and outer fold repeats that construct-and-fit, so nothing survives across folds.
#   * `inner_cv_mae` is carried as a metadata record and is never used for selection.
#
# Verified by reading the harness, not by assertion, and pinned by
# `tests/test_arm0_refits_from_scratch_v39.py`. What the experiment actually inherits from a shipped
# bundle is the SPECIFICATION below; the corrected point-in-time matrix is what every fold trains on.
BUNDLE_SPEC_FIELDS = ("feature_cols", "family", "params", "median_impute", "seed", "target")

# DISCLOSED, NOT GATED. The fixed hyperparameters in each bundle's `params` (and `median_impute`,
# `seed`) were selected under the historical production pipeline, which used the pre-repair PFF join.
# They are FROZEN pre-experiment and applied IDENTICALLY to ARM_0 and to every coaching arm, so they
# cannot differentially favour any arm, and the experiment does not retune them. This is a stated
# limitation of the comparison's absolute level, not a leakage path into the arm contrast, and it is
# deliberately NOT an activation gate. See V39_ACTIVATION_MANIFEST.md §0d.
FROZEN_HYPERPARAMETER_DISCLOSURE = (
    "the fixed production hyperparameters (family, params, median_impute, seed) were selected under the "
    "historical production pipeline, which used the pre-repair PFF join. They are frozen pre-experiment "
    "and applied identically to ARM_0 and every coaching arm; the experiment does not retune them. "
    "Disclosed as a limitation of the absolute level, NOT gated: it is common to all arms and therefore "
    "cannot differentially favour one.")

ROOKIE_INPUT_BLOCKER = (
    "RESOLVED 2026-08-03 by Option A: the derived, outcome-free rookie matrix is frozen at "
    "snapshots/rookie_arm0_features_2014_2025.parquet and pinned in the snapshot manifest. The season "
    "dataset still separately lacks RB 32 of 41, WR 35 of 44 and TE 35 of 44 bundle features — that "
    "gap is what the matrix fills. Raw PFF remains private and untracked; only derived feature values "
    "are repo-owned. Regenerating the matrix still requires the authorized private sources and is a "
    "separate provenance operation.")


# Never loadable, never permitted in a feature frame. `target_ppg`/`target_games`/`sample_weight` are
# the LEGACY Model-A/B targets; `sleeper_pts_half_ppr` is a market projection of the very quantity being
# predicted; `adp_*` are market prices.
FORBIDDEN_IN_FEATURES = frozenset({
    OUTCOME_COLUMN, "target_ppg", "target_games", "sample_weight", "ppg", "half_ppr",
    "sleeper_pts_half_ppr", "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "y",
})

# Mutually exclusive, exhaustive accounting states for a feature row (A4).
STATE_MISSING_IDENTITY = "missing_identity"
STATE_ZERO_FILLED = "zero_filled_no_stat_row"
STATE_MATCHED = "matched_stat_target"
FEATURE_ROW_STATES = (STATE_MISSING_IDENTITY, STATE_ZERO_FILLED, STATE_MATCHED)
# Outcome-side state: a weekly-stat key with no feature row. Counted separately, over a DIFFERENT
# denominator, so it can never overlap the three above.
STATE_UNMATCHED_OUTCOME = "unmatched_outcome_key"


class AssemblyError(RuntimeError):
    """Any violation of the frozen input contract. Never caught inside this module."""


# =====================================================================================================
# READERS — explicit, pinned, and default-closed
# =====================================================================================================
def _refuse(kind):
    def _reader(*_a, **_k):
        raise AssemblyError(
            f"the default {kind} reader is closed. Real data is reachable only through an authorized "
            "run that constructs an explicit reader; importing this module reads nothing.")
    return _reader


default_feature_reader = _refuse("feature")
default_outcome_reader = _refuse("outcome")
default_rookie_matrix_reader = _refuse("rookie matrix")


def file_md5(path):
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()


def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def verify_weekly_snapshot_provenance(manifest_path=None):
    """Check the snapshot against `snapshots/manifest.json`. Metadata only — no row is read."""
    path = SNAPSHOT_MANIFEST if manifest_path is None else pathlib.Path(manifest_path)
    if not path.exists():
        raise AssemblyError(f"snapshot manifest missing: {path}")
    entry = json.loads(path.read_text(encoding="utf-8")).get(WEEKLY_SNAPSHOT_MANIFEST_KEY)
    if entry is None:
        raise AssemblyError(f"manifest has no entry {WEEKLY_SNAPSHOT_MANIFEST_KEY!r}")
    problems = []
    if entry.get("sha256") != WEEKLY_SNAPSHOT_SHA256:
        problems.append(f"manifest sha256 {entry.get('sha256')} != pinned {WEEKLY_SNAPSHOT_SHA256}")
    if entry.get("loader") != WEEKLY_SNAPSHOT_LOADER:
        problems.append(f"loader {entry.get('loader')!r} != {WEEKLY_SNAPSHOT_LOADER!r}")
    if entry.get("rows") != WEEKLY_SNAPSHOT_ROWS:
        problems.append(f"rows {entry.get('rows')} != {WEEKLY_SNAPSHOT_ROWS}")
    if entry.get("cols") != WEEKLY_SNAPSHOT_COLS:
        problems.append(f"cols {entry.get('cols')} != {WEEKLY_SNAPSHOT_COLS}")
    if problems:
        raise AssemblyError("weekly snapshot provenance: " + "; ".join(problems))
    return entry


def verify_veteran_snapshot_provenance(path=None, manifest_path=None, verify_hash=True,
                                       verify_manifest=True):
    """Existence, sha256, manifest entry and exact ordered schema. METADATA ONLY — no row is read."""
    import pyarrow.parquet as pq
    src = VETERAN_SNAPSHOT if path is None else pathlib.Path(path)
    if not src.exists():
        raise AssemblyError(f"veteran snapshot missing: {src}")

    problems = []
    if verify_hash:
        actual = file_sha256(src)
        if actual != VETERAN_SNAPSHOT_SHA256:
            problems.append(f"sha256 {actual} != pinned {VETERAN_SNAPSHOT_SHA256}")

    entry = None
    if verify_manifest:
        mpath = SNAPSHOT_MANIFEST if manifest_path is None else pathlib.Path(manifest_path)
        if not mpath.exists():
            raise AssemblyError(f"snapshot manifest missing: {mpath}")
        entry = json.loads(mpath.read_text(encoding="utf-8")).get(VETERAN_SNAPSHOT_MANIFEST_KEY)
        if entry is None:
            raise AssemblyError(f"manifest has no entry {VETERAN_SNAPSHOT_MANIFEST_KEY!r}")
        for field, pinned in (("sha256", VETERAN_SNAPSHOT_SHA256),
                              ("generator", VETERAN_SNAPSHOT_GENERATOR),
                              ("rows", VETERAN_SNAPSHOT_ROWS), ("cols", VETERAN_SNAPSHOT_COLS)):
            if entry.get(field) != pinned:
                problems.append(f"manifest {field} {entry.get(field)!r} != pinned {pinned!r}")
        if sorted(entry.get("seasons") or ()) != list(ALL_PANEL_SEASONS):
            problems.append(f"manifest seasons {entry.get('seasons')} != {list(ALL_PANEL_SEASONS)}")
        if tuple(entry.get("schema") or ()) != tuple(VETERAN_FEATURE_COLUMNS):
            problems.append("manifest schema differs from the consumed contract")

    schema = tuple(pq.ParquetFile(src).schema_arrow.names)
    if schema != tuple(VETERAN_FEATURE_COLUMNS):
        problems.append(f"schema differs from the consumed contract (got {len(schema)} column(s))")
    # The row count is an attribute of the ONE pinned artifact, not of the schema contract, so it is
    # checked exactly when the hash is. A test that deliberately injects a different file has already
    # said so by passing verify_hash=False; the schema, season and forbidden-column checks still bind.
    if verify_hash and pq.ParquetFile(src).metadata.num_rows != VETERAN_SNAPSHOT_ROWS:
        problems.append(f"row count {pq.ParquetFile(src).metadata.num_rows} != pinned "
                        f"{VETERAN_SNAPSHOT_ROWS}")
    leaked = sorted(set(schema) & FORBIDDEN_IN_FEATURES)
    if leaked:
        problems.append(f"outcome-bearing column(s) present: {leaked}")

    # The season set is checked on the FILE, not merely on the manifest. The reader also windows to
    # 2014-2025, but a snapshot that CONTAINS 2026 was built wrong, and silently filtering it away
    # would hide that. One column is read; no feature value is touched.
    if SEASON_KEY in schema:
        seasons = sorted(int(s) for s in
                         pd.unique(pd.read_parquet(src, columns=[SEASON_KEY])[SEASON_KEY].dropna()))
        if seasons != list(ALL_PANEL_SEASONS):
            problems.append(f"season coverage is {seasons}, must be exactly {list(ALL_PANEL_SEASONS)}")

    if problems:
        raise AssemblyError("veteran snapshot provenance: " + "; ".join(problems))
    return entry


def authorized_feature_reader(path=None, verify_hash=True, verify_manifest=True):
    """Build the REAL veteran feature reader. Constructing it is not reading; the callable reads.

    Reads the IMMUTABLE 2014-2025 snapshot, never the live production CSV. The snapshot is already
    feature-only and already windowed, so no forbidden column exists to exclude and no season filter
    is needed — but both are still ASSERTED, because a check that is merely unnecessary today is the
    kind that stops being true quietly.
    """
    src = VETERAN_SNAPSHOT if path is None else pathlib.Path(path)

    def _read():
        verify_veteran_snapshot_provenance(path=src, verify_hash=verify_hash,
                                           verify_manifest=verify_manifest)
        df = pd.read_parquet(src, columns=list(FROZEN_FEATURE_COLUMNS))
        forbidden_loaded = sorted(set(df.columns) & FORBIDDEN_IN_FEATURES)
        if forbidden_loaded:
            raise AssemblyError(f"the frozen contract itself names forbidden column(s): "
                                f"{forbidden_loaded}")
        df = df[(df[SEASON_KEY] >= PANEL_FIRST_SEASON) & (df[SEASON_KEY] <= PANEL_LAST_SEASON)]
        df = df.reset_index(drop=True)
        problems = validate_feature_frame(df)
        if problems:
            raise AssemblyError("feature reader output failed its own validator: " + "; ".join(problems))
        return df
    return _read


def authorized_outcome_reader(path=None, verify_hash=True, verify_manifest=True):
    """Build the REAL outcome reader: grouped REG-season totals from the PINNED weekly snapshot.

    This reproduces `build_rb_projection.season_total_target()` exactly. The OUTCOME path specifically is
    hermetic — no network, no artifact to create. That says nothing about the rookie FEATURE buckets,
    which remain blocked; see `activation_readiness()`.
    """
    src = WEEKLY_SNAPSHOT if path is None else pathlib.Path(path)

    def _read():
        if not src.exists():
            raise AssemblyError(f"weekly snapshot missing: {src}")
        if verify_hash:
            actual = file_sha256(src)
            if actual != WEEKLY_SNAPSHOT_SHA256:
                raise AssemblyError(f"weekly snapshot hash drift: expected {WEEKLY_SNAPSHOT_SHA256}, "
                                    f"got {actual}")
        if verify_manifest:
            verify_weekly_snapshot_provenance()
        weekly = pd.read_parquet(src, columns=list(WEEKLY_REQUIRED_COLUMNS))
        return grouped_season_totals(weekly)
    return _read


def verify_rookie_matrix_provenance(path=None, manifest_path=None, verify_hash=True,
                                    verify_manifest=True):
    """Existence, sha256, manifest entry and EXACT ordered schema of the frozen rookie matrix.

    METADATA ONLY — the parquet schema is read, not a single row. Raises `AssemblyError` on any
    violation; returns the manifest entry (or `None` when manifest verification is switched off).
    """
    import pyarrow.parquet as pq
    src = ROOKIE_MATRIX if path is None else pathlib.Path(path)
    if not src.exists():
        raise AssemblyError(f"rookie matrix missing: {src}")

    problems = []
    if verify_hash:
        actual = file_sha256(src)
        if actual != ROOKIE_MATRIX_SHA256:
            problems.append(f"sha256 {actual} != pinned {ROOKIE_MATRIX_SHA256}")

    entry = None
    if verify_manifest:
        mpath = SNAPSHOT_MANIFEST if manifest_path is None else pathlib.Path(manifest_path)
        if not mpath.exists():
            raise AssemblyError(f"snapshot manifest missing: {mpath}")
        entry = json.loads(mpath.read_text(encoding="utf-8")).get(ROOKIE_MATRIX_MANIFEST_KEY)
        if entry is None:
            raise AssemblyError(f"manifest has no entry {ROOKIE_MATRIX_MANIFEST_KEY!r}")
        for field, pinned in (("sha256", ROOKIE_MATRIX_SHA256),
                              ("generator", ROOKIE_MATRIX_GENERATOR),
                              ("rows", ROOKIE_MATRIX_ROWS), ("cols", ROOKIE_MATRIX_COLS)):
            if entry.get(field) != pinned:
                problems.append(f"manifest {field} {entry.get(field)!r} != pinned {pinned!r}")
        if sorted(entry.get("seasons") or ()) != list(ALL_PANEL_SEASONS):
            problems.append(f"manifest seasons {entry.get('seasons')} != {list(ALL_PANEL_SEASONS)}")
        if tuple(entry.get("keys") or ()) != PANEL_KEYS:
            problems.append(f"manifest keys {entry.get('keys')} != {list(PANEL_KEYS)}")
        if tuple(entry.get("positions") or ()) != ROOKIE_MATRIX_POSITIONS:
            problems.append(f"manifest positions {entry.get('positions')} != "
                            f"{list(ROOKIE_MATRIX_POSITIONS)}")

    meta = pq.ParquetFile(src)
    schema = tuple(meta.schema_arrow.names)
    if schema != ROOKIE_MATRIX_COLUMNS:
        problems.append(f"schema differs from the pinned {ROOKIE_MATRIX_COLS}-column contract "
                        f"(got {len(schema)} column(s); first difference at "
                        f"{_first_schema_difference(schema, ROOKIE_MATRIX_COLUMNS)})")
    if meta.metadata.num_rows != ROOKIE_MATRIX_ROWS:
        problems.append(f"row count {meta.metadata.num_rows} != pinned {ROOKIE_MATRIX_ROWS}")
    leaked = sorted(set(schema) & FORBIDDEN_IN_FEATURES)
    if leaked:
        problems.append(f"outcome-bearing column(s) present: {leaked}")

    if problems:
        raise AssemblyError("rookie matrix provenance: " + "; ".join(problems))
    return entry


def _first_schema_difference(actual, expected):
    for i in range(max(len(actual), len(expected))):
        a = actual[i] if i < len(actual) else "<absent>"
        e = expected[i] if i < len(expected) else "<absent>"
        if a != e:
            return f"index {i}: {a!r} vs expected {e!r}"
    return "none"


def rookie_matrix_columns(path=None, **kwargs):
    """The pinned column tuple, returned only after provenance verification passes. No row is read."""
    verify_rookie_matrix_provenance(path=path, **kwargs)
    return ROOKIE_MATRIX_COLUMNS


def authorized_rookie_matrix_reader(path=None, verify_hash=True, verify_manifest=True):
    """Build the REAL rookie-feature reader. Constructing it is not reading; the callable reads.

    The frame carries derived, outcome-free rookie features only. Its own output is passed through
    `validate_rookie_matrix` before it is returned, so a reader that cannot satisfy the contract can
    never hand a frame to the assembler.
    """
    src = ROOKIE_MATRIX if path is None else pathlib.Path(path)

    def _read():
        verify_rookie_matrix_provenance(path=src, verify_hash=verify_hash,
                                        verify_manifest=verify_manifest)
        df = pd.read_parquet(src, columns=list(ROOKIE_MATRIX_COLUMNS))
        problems = validate_rookie_matrix(df)
        if problems:
            raise AssemblyError("rookie matrix reader output failed its own validator: "
                                + "; ".join(problems))
        return df
    return _read


def validate_rookie_matrix(matrix, models_dir=None):
    """Schema order, keys, seasons, positions, row count and bundle coverage. Returns a problem list."""
    problems = []
    if tuple(matrix.columns) != ROOKIE_MATRIX_COLUMNS:
        problems.append(f"column schema differs from the pinned contract "
                        f"({_first_schema_difference(tuple(matrix.columns), ROOKIE_MATRIX_COLUMNS)})")
        if not set(ROOKIE_MATRIX_IDENTITY) <= set(matrix.columns):
            return problems                       # nothing key-based is checkable without identity

    if len(matrix) != ROOKIE_MATRIX_ROWS:
        problems.append(f"row count {len(matrix)} != pinned {ROOKIE_MATRIX_ROWS} (silent row loss)")
    n_dup = int(matrix.duplicated(subset=list(PANEL_KEYS)).sum())
    if n_dup:
        problems.append(f"{n_dup} duplicate {list(PANEL_KEYS)} row(s)")
    for key in PANEL_KEYS:
        if matrix[key].isna().any():
            problems.append(f"null {key}")

    seasons = sorted(int(s) for s in pd.unique(matrix[SEASON_KEY].dropna()))
    if seasons != list(ALL_PANEL_SEASONS):
        problems.append(f"season coverage {seasons} != required {list(ALL_PANEL_SEASONS)}")
    positions = tuple(sorted(set(pd.unique(matrix["position"].dropna()).tolist())))
    if positions != ROOKIE_MATRIX_POSITIONS:
        problems.append(f"positions {positions} != {ROOKIE_MATRIX_POSITIONS}")
    if not bool((matrix["is_rookie"] == 1).all()):
        problems.append("a non-rookie row is present")

    leaked = sorted(set(matrix.columns) & FORBIDDEN_IN_FEATURES)
    if leaked:
        problems.append(f"outcome-bearing column(s) present: {leaked}")

    # THE POINT-IN-TIME CONTRACT. The first matrix shipped with a PFF join that took the LATEST
    # college season for a name across 2014-2025 and attached it regardless of the rookie season, so
    # 2014 Mike Evans carried 2021 receiving. Checkable here from the artifact alone.
    for sc in ROOKIE_MATRIX_PROVENANCE:
        if sc not in matrix.columns:
            problems.append(f"provenance column {sc} is absent; point-in-time is unverifiable")
            continue
        late = matrix[sc].notna() & (matrix[sc] >= matrix[SEASON_KEY])
        if bool(late.any()):
            ex = matrix.loc[late, ["norm_name", SEASON_KEY, sc]].head(3).to_dict("records")
            problems.append(f"TEMPORAL LEAK: {int(late.sum())} row(s) carry {sc} >= {SEASON_KEY}; "
                            f"e.g. {ex}")

    # COVERAGE, not storage order. The matrix is a SHARED pool: RB and WR order their common features
    # differently, so no single physical column order can equal all three bundle orders at once
    # (measured: RB inverts at `coach_changed`, WR/TE at `cfb_rec_pg`). Storage order is pinned instead
    # by ROOKIE_MATRIX_COLUMNS, and the ORDER a model is fed is enforced where it matters — on the
    # per-bucket frame, by `rookie_bucket_frame` / `bucket_frame_satisfies_bundle`.
    md = MODELS_DIR if models_dir is None else pathlib.Path(models_dir)
    for (position, bucket), (fname, _n, source) in sorted(SHIPPED_ARM0_BUCKETS.items()):
        if source != SOURCE_ROOKIE_MATRIX:
            continue
        if not (md / fname).exists():
            problems.append(f"{position}/{bucket} bundle missing: {md / fname}")
            continue
        fc = bundle_feature_cols(position, bucket, models_dir=md)
        absent = [c for c in fc if c not in matrix.columns]
        if absent:
            problems.append(f"{position}/{bucket} missing {len(absent)} of {len(fc)} bundle "
                            f"feature(s): {absent[:6]}")
    return problems


def bundle_feature_cols(position, bucket, models_dir=None):
    """The ordered `feature_cols` a shipped bundle expects. Bundle METADATA only."""
    import pickle
    md = MODELS_DIR if models_dir is None else pathlib.Path(models_dir)
    fname = SHIPPED_ARM0_BUCKETS[(position, bucket)][0]
    return tuple(pickle.loads((md / fname).read_bytes())["feature_cols"])


def rookie_bucket_frame(matrix, position, bucket, models_dir=None):
    """Select one rookie bucket's features FROM the shared matrix, in bundle order, and verify it.

    This is the point at which order becomes real: the returned frame is what a model would be fed.
    """
    if SHIPPED_ARM0_BUCKETS[(position, bucket)][2] != SOURCE_ROOKIE_MATRIX:
        raise AssemblyError(f"{position}/{bucket} is not sourced from the rookie matrix")
    fc = bundle_feature_cols(position, bucket, models_dir=models_dir)
    absent = [c for c in fc if c not in matrix.columns]
    if absent:
        raise AssemblyError(f"{position}/{bucket} missing {len(absent)} bundle feature(s): {absent[:8]}")
    rows = matrix[matrix["position"] == position]
    frame = rows[list(ROOKIE_MATRIX_IDENTITY) + list(fc)]
    bucket_frame_satisfies_bundle(frame.columns, position, bucket, models_dir=models_dir)
    return frame


MODEL_TARGET_COLUMN = "y"

# --- THE COMPOSED UNION SCHEMA -------------------------------------------------------------------
# `SHIPPED_ARM0_BUCKETS` already froze the routing: the four VETERAN buckets are fed by the veteran
# snapshot, the three ROOKIE buckets by the rookie matrix. This is that contract, implemented — not a
# new design choice. The union is the veteran contract plus the rookie matrix's own feature columns,
# in the rookie matrix's pinned order, plus its two point-in-time provenance columns.
#
# NINE columns appear in BOTH sources (draft_round, draft_pick, age, and the six landing-spot
# features). Ownership is explicit and per row: a rookie-bucket row takes the ROOKIE value for every
# one of them, INCLUDING a NULL. Nothing is coalesced — an intentional rookie NULL must never be
# back-filled from the veteran source.
ROOKIE_SOURCE_FEATURE_COLUMNS = tuple(
    c for c in ROOKIE_MATRIX_COLUMNS
    if c not in ROOKIE_MATRIX_IDENTITY and c not in ROOKIE_MATRIX_PROVENANCE)
ROOKIE_ONLY_FEATURE_COLUMNS = tuple(c for c in ROOKIE_SOURCE_FEATURE_COLUMNS
                                    if c not in VETERAN_FEATURE_COLUMNS)
SHARED_SOURCE_COLUMNS = tuple(c for c in ROOKIE_SOURCE_FEATURE_COLUMNS
                              if c in VETERAN_FEATURE_COLUMNS)
FROZEN_UNION_FEATURE_COLUMNS = (VETERAN_FEATURE_COLUMNS + ROOKIE_ONLY_FEATURE_COLUMNS
                                + ROOKIE_MATRIX_PROVENANCE)
# Never a model input unless a bundle names it explicitly (none does).
NON_MODEL_HELPER_COLUMNS = ROOKIE_MATRIX_PROVENANCE


def authorized_composed_feature_reader(veteran_path=None, rookie_path=None, verify_hash=True,
                                       verify_manifest=True, models_dir=None):
    """THE composed feature reader: veteran snapshot + rookie matrix, per the FROZEN routing.

    Constructing it is not reading; the returned callable reads. Both sources are verified
    INDEPENDENTLY — hash, manifest and exact ordered schema — before either frame is accepted.

    The veteran snapshot is the population and routing SPINE: its row count and order are preserved
    exactly, and every row keeps its identity. The rookie matrix supplies the RB/WR/TE rookie-bucket
    rows, whose key set must equal the spine's `is_rookie == 1` RB/WR/TE rows exactly.

    QB/rookie is untouched: it is absent from `SHIPPED_ARM0_BUCKETS` (the arm was HELD), so those
    spine rows are NOT expected in the rookie matrix and keep veteran-source values. That frozen
    exclusion is asserted, not assumed.
    """
    vet_src = VETERAN_SNAPSHOT if veteran_path is None else pathlib.Path(veteran_path)
    rook_src = ROOKIE_MATRIX if rookie_path is None else pathlib.Path(rookie_path)

    def _read():
        verify_veteran_snapshot_provenance(path=vet_src, verify_hash=verify_hash,
                                           verify_manifest=verify_manifest)
        verify_rookie_matrix_provenance(path=rook_src, verify_hash=verify_hash,
                                        verify_manifest=verify_manifest)
        spine = pd.read_parquet(vet_src, columns=list(VETERAN_FEATURE_COLUMNS))
        rookie = pd.read_parquet(rook_src, columns=list(ROOKIE_MATRIX_COLUMNS))
        frame = compose_feature_frame(spine, rookie, models_dir=models_dir)
        # v3.9x: the canonical key contract is applied HERE, at the boundary, so this reader and the
        # outcome reader cannot disagree about `player_id`'s dtype. That disagreement — string[python]
        # against object — is what the first authorized real run died on.
        frame = canonicalize_panel_keys(frame, "composed feature reader")
        problems = validate_feature_frame(frame)
        if problems:
            raise AssemblyError("composed feature reader output failed its own validator: "
                                + "; ".join(problems))
        return frame
    return _read


def compose_feature_frame(spine, rookie, models_dir=None):
    """Merge the two pinned sources under the frozen routing. Pure: takes frames, returns a frame."""
    keys = list(PANEL_KEYS)
    spine = spine.reset_index(drop=True).copy()

    if list(spine.columns) != list(VETERAN_FEATURE_COLUMNS):
        raise AssemblyError("composition: the spine is not the veteran contract")
    if list(rookie.columns) != list(ROOKIE_MATRIX_COLUMNS):
        raise AssemblyError("composition: the rookie frame is not the rookie contract")
    if rookie.duplicated(subset=keys).any():
        n = int(rookie.duplicated(subset=keys).sum())
        raise AssemblyError(f"composition: {n} duplicate {keys} row(s) in the rookie matrix")

    routed = (spine["is_rookie"].astype(int) == 1) & spine["position"].isin(ROOKIE_MATRIX_POSITIONS)
    spine_keys = set(map(tuple, spine.loc[routed, keys].to_numpy()))
    rook_keys = set(map(tuple, rookie[keys].to_numpy()))
    missing, extra = sorted(spine_keys - rook_keys)[:5], sorted(rook_keys - spine_keys)[:5]
    if missing:
        raise AssemblyError(f"composition: {len(spine_keys - rook_keys)} routed rookie row(s) have no "
                            f"rookie-matrix row; e.g. {missing}")
    if extra:
        raise AssemblyError(f"composition: {len(rook_keys - spine_keys)} rookie-matrix row(s) match no "
                            f"routed spine row; e.g. {extra}")

    # QB/rookie is a FROZEN exclusion: those spine rows must not appear in the rookie matrix.
    qb_rookie = spine[(spine["is_rookie"].astype(int) == 1) & (spine["position"] == "QB")]
    leaked_qb = set(map(tuple, qb_rookie[keys].to_numpy())) & rook_keys
    if leaked_qb:
        raise AssemblyError(f"composition: {len(leaked_qb)} QB/rookie row(s) are in the rookie matrix; "
                            f"the QB rookie arm is HELD and has no bundle")

    # rookie values, reordered onto the spine's routed rows
    ordered = spine.loc[routed, keys].merge(rookie, on=keys, how="left", validate="one_to_one")
    if len(ordered) != int(routed.sum()):
        raise AssemblyError("composition: the rookie join changed the routed row count")

    mismatch = (ordered["position"].to_numpy() != spine.loc[routed, "position"].to_numpy())
    if mismatch.any():
        raise AssemblyError(f"composition: {int(mismatch.sum())} rookie row(s) disagree with the spine "
                            f"on position")
    if not (ordered["is_rookie"].astype(int) == 1).all():
        raise AssemblyError("composition: a rookie-matrix row is not flagged is_rookie == 1")

    frame = spine.copy()
    for c in ROOKIE_ONLY_FEATURE_COLUMNS + ROOKIE_MATRIX_PROVENANCE:
        frame[c] = np.nan                                   # veteran rows have no rookie feature
    # EXPLICIT per-row ownership. Direct assignment, never fillna/combine_first: a NULL in the rookie
    # matrix is an intentional "not measured" and must survive, not be back-filled from the spine.
    for c in ROOKIE_SOURCE_FEATURE_COLUMNS + ROOKIE_MATRIX_PROVENANCE:
        frame.loc[routed, c] = ordered[c].to_numpy()

    frame = frame[list(FROZEN_UNION_FEATURE_COLUMNS)]
    if len(frame) != len(spine):
        raise AssemblyError(f"composition: row count changed {len(spine)} -> {len(frame)}")

    gaps = union_bucket_gaps(frame, models_dir=models_dir)
    if gaps:
        raise AssemblyError("composition: not every shipped bucket is feedable: " + "; ".join(gaps))
    return frame


# =====================================================================================================
# EVALUATION ELIGIBILITY — a PRE-OUTCOME population rule, decided from features alone
# =====================================================================================================
# Adopted 2026-08-03. A row is eligible only when BOTH hold:
#   1. `team` is non-null, so OC/HC exposure is DEFINED for it;
#   2. its (position, bucket) has a shipped Arm 0 bundle.
#
# Determined solely from the frozen feature frame, BEFORE any outcome reader runs, and applied
# identically to ARM_0 and every coaching arm. Coaching exposure is never imputed, proxied or
# fabricated: a row with no team has no OC/HC to be exposed to, and inventing a neutral value would
# invent the very quantity under test.
ELIGIBLE = "eligible"
EXCLUDED_MISSING_TEAM = "excluded_missing_team"
EXCLUDED_NO_SHIPPED_BUNDLE = "excluded_no_shipped_bundle"
ELIGIBILITY_STATES = (ELIGIBLE, EXCLUDED_MISSING_TEAM, EXCLUDED_NO_SHIPPED_BUNDLE)


def bucket_of(frame):
    """`is_rookie` -> the routing bucket. The only place the mapping is written."""
    return frame["is_rookie"].astype(int).map({1: "rookie", 0: "veteran"})


def evaluation_eligibility(frame, models_dir=None):
    """THE canonical eligibility rule. Returns (eligible_frame, accounting).

    Exactly one `eligibility_state` per SOURCE row; the three states are mutually exclusive and
    exhaustive, and that is asserted here rather than assumed. Source order is retained among the
    eligible rows. Nothing about an outcome is consulted — this runs before the outcome reader.
    """
    if "team" not in frame.columns or "position" not in frame.columns:
        raise AssemblyError("eligibility: the frame lacks `team` or `position`")

    bucket = bucket_of(frame)
    unknown_bucket = sorted(set(bucket.dropna()) - {"rookie", "veteran"})
    if unknown_bucket:
        raise AssemblyError(f"eligibility: unknown bucket(s) {unknown_bucket}")
    known_positions = {p for p, _b in SHIPPED_ARM0_BUCKETS} | {"QB"}
    unknown_pos = sorted(set(frame["position"].dropna()) - known_positions)
    if unknown_pos:
        raise AssemblyError(f"eligibility: unknown position(s) {unknown_pos}")

    shipped = set(SHIPPED_ARM0_BUCKETS)
    has_bundle = pd.Series([(p, b) in shipped for p, b in zip(frame["position"], bucket)],
                           index=frame.index)
    missing_team = frame["team"].isna()

    # Precedence is explicit: a row with NO shipped bundle is outside the experiment structurally,
    # whatever its team. The two reasons are also required to be DISJOINT, so no row is ambiguous.
    both = int((missing_team & ~has_bundle).sum())
    state = pd.Series(ELIGIBLE, index=frame.index, dtype=object)
    state[missing_team] = EXCLUDED_MISSING_TEAM
    state[~has_bundle] = EXCLUDED_NO_SHIPPED_BUNDLE

    counts = {s: int((state == s).sum()) for s in ELIGIBILITY_STATES}
    if sum(counts.values()) != len(frame):
        raise AssemblyError(f"eligibility: states do not partition the source "
                            f"({sum(counts.values())} vs {len(frame)})")
    if set(pd.unique(state)) - set(ELIGIBILITY_STATES):
        raise AssemblyError("eligibility: an unknown state was assigned")
    if both:
        raise AssemblyError(f"eligibility: {both} row(s) match BOTH exclusion reasons; the partition "
                            f"would be ambiguous")

    eligible = frame[state == ELIGIBLE].copy()          # boolean mask preserves source order
    if missing_team[state == ELIGIBLE].any():
        raise AssemblyError("eligibility: a retained row has a null team")
    retained_bucket = bucket_of(eligible)
    bad = [(p, b) for p, b in zip(eligible["position"], retained_bucket) if (p, b) not in shipped]
    if bad:
        raise AssemblyError(f"eligibility: {len(bad)} retained row(s) map to no shipped bundle")

    by_reason = {}
    for s in (EXCLUDED_MISSING_TEAM, EXCLUDED_NO_SHIPPED_BUNDLE):
        sub = frame[state == s]
        by_reason[s] = {
            "n": int(len(sub)),
            "by_position": {str(k): int(v) for k, v in sub["position"].value_counts().items()},
            "by_season": {int(k): int(v) for k, v in sub[SEASON_KEY].value_counts().sort_index().items()},
        }

    accounting = {
        "source_population": int(len(frame)),
        "excluded_missing_team": counts[EXCLUDED_MISSING_TEAM],
        "excluded_no_shipped_bundle": counts[EXCLUDED_NO_SHIPPED_BUNDLE],
        "eligible_evaluation_population": counts[ELIGIBLE],
        "states_are_exhaustive": True,
        "states_are_mutually_exclusive": both == 0,
        "by_reason": by_reason,
        "eligible_seasons": sorted(int(s) for s in pd.unique(eligible[SEASON_KEY])),
        "eligible_by_bucket": {f"{p}/{b}": int(((eligible['position'] == p)
                                                & (retained_bucket == b)).sum())
                               for p, b in sorted(shipped)},
    }
    gaps = union_bucket_gaps(eligible, models_dir=models_dir) if \
        list(eligible.columns) == list(FROZEN_UNION_FEATURE_COLUMNS) else []
    if gaps:
        raise AssemblyError("eligibility: the retained frame cannot feed every shipped bucket: "
                            + "; ".join(gaps))
    return eligible.reset_index(drop=True), accounting


def union_bucket_gaps(frame, models_dir=None):
    """Which shipped (position, bucket) the union frame cannot feed. Empty means all seven are OK."""
    gaps = []
    is_rookie = frame["is_rookie"].astype(int) == 1
    for (pos, bucket), (_f, _n, _s) in sorted(SHIPPED_ARM0_BUCKETS.items()):
        want_rookie = bucket == "rookie"
        rows = frame[(frame["position"] == pos) & (is_rookie == want_rookie)]
        if not len(rows):
            gaps.append(f"{pos}/{bucket}: no rows")
            continue
        fc = bundle_feature_cols(pos, bucket, models_dir=models_dir)
        absent = [c for c in fc if c not in frame.columns]
        if absent:
            gaps.append(f"{pos}/{bucket}: missing {len(absent)} of {len(fc)} feature(s) "
                        f"(e.g. {absent[:4]})")
    return gaps


def panel_for_experiment(assembled, models_dir=None, require_bucket_coverage=True):
    """THE canonical adapter: `assemble_real_panel()`'s separated result -> `run_experiment`'s panel.

    This is the ONE place where the outcome and the features are allowed to meet, and the only place
    the verified outcome column is renamed to `y`. Everything upstream keeps them in separate objects
    deliberately; everything downstream expects one frame.

    Contract, all enforced:
      * the join is on the FROZEN panel keys and nothing else;
      * alignment is strictly ONE-TO-ONE — duplicate, missing, extra or reordered outcome keys refuse;
      * the feature-row POPULATION and ORDER are preserved exactly;
      * the accounting/zero-fill states are retained on the panel and reported, not dropped;
      * no outcome-bearing field may enter the feature space: the target arrives ONLY as `y`, and the
        original outcome column name does not survive into the panel.

    `bucket` is derived from `is_rookie`, which is how `run_experiment` routes rows to a bundle.
    """
    for key in ("features", "outcomes"):
        if key not in assembled:
            raise AssemblyError(f"assembled result is missing {key!r}")
    features, outcomes = assembled["features"], assembled["outcomes"]

    # The adapter's input is POST-core, so the outcome frame legitimately carries `outcome_state`,
    # which `validate_outcome_frame` (the READER's schema) forbids. Validating the post-core frame
    # with the pre-core validator was a real bug: it rejected every well-formed assembled result.
    problems = validate_feature_frame(features)
    required = list(PANEL_KEYS) + [OUTCOME_COLUMN, "outcome_state"]
    absent = [c for c in required if c not in outcomes.columns]
    if absent:
        problems.append(f"assembled outcome frame is missing {absent}")
    else:
        unexpected = sorted(set(outcomes.columns) - set(required))
        if unexpected:
            problems.append(f"assembled outcome frame carries unexpected column(s): {unexpected}")
        bad_state = sorted(set(pd.unique(outcomes["outcome_state"].dropna()))
                           - set(FEATURE_ROW_STATES) - {STATE_UNMATCHED_OUTCOME})
        if bad_state:
            problems.append(f"unknown outcome_state value(s): {bad_state}")
    if problems:
        raise AssemblyError("adapter input: " + "; ".join(problems))

    keys = list(PANEL_KEYS)

    # v3.9x: DTYPE FIRST, AND ON ITS OWN. The old code asserted ordering with `DataFrame.equals`,
    # which compares dtypes too, so a dtype disagreement between the readers was reported as
    # "the join reordered the feature rows" — a false and misleading diagnosis that stopped the first
    # authorized real run. Dtype and ordering are now two checks with two messages.
    key_problems = (canonical_key_dtype_problems(features, "adapter feature frame")
                    + canonical_key_dtype_problems(outcomes, "adapter outcome frame"))
    if key_problems:
        raise AssemblyError("adapter: panel key dtype contract violated (this is a DTYPE failure, "
                            "not a row-ordering failure): " + "; ".join(key_problems))

    if outcomes.duplicated(subset=keys).any():
        n = int(outcomes.duplicated(subset=keys).sum())
        raise AssemblyError(f"adapter: {n} duplicate {keys} row(s) in the outcome frame")

    fk = features[keys].apply(tuple, axis=1)
    ok = outcomes[keys].apply(tuple, axis=1)
    fset, oset = set(fk), set(ok)
    if len(fset) != len(features):
        raise AssemblyError("adapter: the feature frame has duplicate panel keys")
    missing, extra = sorted(fset - oset)[:5], sorted(oset - fset)[:5]
    if missing:
        raise AssemblyError(f"adapter: {len(fset - oset)} feature row(s) have no outcome key; "
                            f"e.g. {missing}")
    if extra:
        raise AssemblyError(f"adapter: {len(oset - fset)} outcome key(s) match no feature row; "
                            f"e.g. {extra}")

    aligned = features[keys].merge(outcomes, on=keys, how="left", validate="one_to_one")
    if len(aligned) != len(features):
        raise AssemblyError(f"adapter: alignment changed the row count "
                            f"{len(features)} -> {len(aligned)}")
    # ORDER, compared on VALUES ONLY — `ordered_key_values` drops dtype metadata, so this fires if and
    # only if a key value actually moved. The dtype contract was already asserted above.
    lhs = ordered_key_values(features.reset_index(drop=True))
    rhs = ordered_key_values(aligned)
    if not np.array_equal(lhs, rhs):
        moved = int(np.sum(np.any(lhs != rhs, axis=1)))
        first = int(np.argmax(np.any(lhs != rhs, axis=1)))
        raise AssemblyError(
            f"adapter: the join reordered the feature rows — {moved} row(s) hold a different key "
            f"after alignment; first at position {first}: expected {tuple(lhs[first])}, "
            f"got {tuple(rhs[first])}")

    panel = features.reset_index(drop=True).copy()
    panel[MODEL_TARGET_COLUMN] = aligned[OUTCOME_COLUMN].to_numpy(float)
    panel["outcome_state"] = aligned["outcome_state"].to_numpy()
    panel["bucket"] = panel["is_rookie"].map(lambda v: "rookie" if int(v) == 1 else "veteran")

    # `y` is IN `FORBIDDEN_IN_FEATURES` — deliberately, because it must never appear in a FEATURE
    # frame. This is the one boundary where it is the sanctioned target, so it is excluded from the
    # leak set here and nowhere else. Every other outcome-bearing name is still refused, and
    # `panel_feature_columns()` below keeps `y` out of the model feature lists.
    leaked = sorted((set(panel.columns) & FORBIDDEN_IN_FEATURES) - {MODEL_TARGET_COLUMN})
    if leaked:
        raise AssemblyError(f"adapter: outcome-bearing column(s) reached the panel: {leaked}")
    if OUTCOME_COLUMN in panel.columns:
        raise AssemblyError(f"adapter: {OUTCOME_COLUMN} survived into the panel; the target must "
                            f"appear only as {MODEL_TARGET_COLUMN!r}")

    if require_bucket_coverage:
        gaps = panel_bucket_gaps(panel, models_dir=models_dir)
        if gaps:
            raise AssemblyError(
                "adapter: the panel cannot supply every shipped bucket, and an incomplete panel would "
                "SILENTLY shrink the population (run_experiment skips a bucket with no usable rows): "
                + "; ".join(gaps))

    states = pd.Series(panel["outcome_state"]).value_counts().to_dict()
    return panel, {"n_rows": len(panel), "accounting": assembled.get("accounting"),
                   "outcome_states": states,
                   "buckets": panel["bucket"].value_counts().to_dict()}


def panel_feature_columns(panel):
    """The panel columns a model may be fed: everything that is not the target or bookkeeping.

    The requirement is "no outcome field may enter the model feature lists". `y` and `outcome_state`
    are the two the adapter adds, and both are excluded here.
    """
    excluded = {MODEL_TARGET_COLUMN, "outcome_state", "bucket"} | set(FORBIDDEN_IN_FEATURES)
    return [c for c in panel.columns if c not in excluded]


def panel_bucket_gaps(panel, models_dir=None):
    """Which shipped (position, bucket) the panel cannot feed. Empty list means full coverage."""
    gaps = []
    for (pos, bucket), (_fname, _n, _src) in sorted(SHIPPED_ARM0_BUCKETS.items()):
        sub = panel[(panel["position"] == pos) & (panel["bucket"] == bucket)]
        if not len(sub):
            gaps.append(f"{pos}/{bucket}: no rows")
            continue
        fc = bundle_feature_cols(pos, bucket, models_dir=models_dir)
        absent = [c for c in fc if c not in panel.columns]
        if absent:
            gaps.append(f"{pos}/{bucket}: panel lacks {len(absent)} of {len(fc)} bundle feature(s) "
                        f"(e.g. {absent[:4]})")
    return gaps


def verify_pinned_activation_inputs(strict=True):
    """Every pinned INPUT an authorized run will read, checked by hash and manifest BEFORE reading.

    Metadata only — not one row is read here. Covers the three data inputs:
      * veteran features  `season_dataset_2014_2026.csv`      (md5)
      * rookie features   `rookie_arm0_features_2014_2025.parquet` (sha256 + manifest + exact schema)
      * weekly outcome    `player_stats_2011_2025.parquet`    (sha256 + manifest loader/rows/cols)
    The five coaching artifacts are pinned by `preflight()`'s `v39_artifacts_pinned`, which
    `require_preflight_clearance` evaluates before this runs.
    """
    problems = []
    # The VETERAN input is the immutable 2014-2025 snapshot, NOT the live production CSV. The CSV is
    # the generator's input only; refreshing deploy-season 2026 in it must never gate activation.
    try:
        verify_veteran_snapshot_provenance()
    except AssemblyError as exc:
        problems.append(str(exc))

    if not WEEKLY_SNAPSHOT.exists():
        problems.append(f"weekly outcome snapshot missing: {WEEKLY_SNAPSHOT}")
    else:
        actual = file_sha256(WEEKLY_SNAPSHOT)
        if actual != WEEKLY_SNAPSHOT_SHA256:
            problems.append(f"weekly snapshot sha256 {actual} != pinned {WEEKLY_SNAPSHOT_SHA256}")
        else:
            try:
                verify_weekly_snapshot_provenance()
            except AssemblyError as exc:
                problems.append(str(exc))

    try:
        verify_rookie_matrix_provenance()
    except AssemblyError as exc:
        problems.append(str(exc))

    if problems and strict:
        raise AssemblyError("pinned activation inputs: " + "; ".join(problems))
    return problems


def grouped_season_totals(weekly, seasons=ALL_PANEL_SEASONS):
    """REG-only, 2014-2025, `fantasy_points + 0.5*receptions`, summed per (player_id, season).

    Pure: takes a frame, returns a frame. The formula and the REG filter are the production ones.
    """
    missing = [c for c in WEEKLY_REQUIRED_COLUMNS if c not in weekly.columns]
    if missing:
        raise AssemblyError(f"weekly schema drift: missing {missing}")
    reg = weekly[weekly["season_type"] == REG_SEASON_TYPE].copy()
    if not (reg["season_type"] == REG_SEASON_TYPE).all():
        raise AssemblyError("POSTSEASON leaked into the weekly frame")
    reg = reg[reg[SEASON_KEY].isin(list(seasons))]
    reg[OUTCOME_COLUMN] = (reg["fantasy_points"].fillna(0).astype(float)
                           + 0.5 * reg["receptions"].fillna(0).astype(float))
    out = (reg.groupby([PLAYER_KEY, SEASON_KEY])[OUTCOME_COLUMN].sum()
              .reset_index())
    out = out[[PLAYER_KEY, SEASON_KEY, OUTCOME_COLUMN]]
    # v3.9x: the SAME canonical key contract the feature reader applies. `groupby(...).reset_index()`
    # hands back whatever dtypes the weekly parquet carried — `object` for `player_id` — and that
    # mismatch is what the adapter mis-reported as a row reordering.
    return canonicalize_panel_keys(out, "grouped season-total outcome reader")


# =====================================================================================================
# VALIDATION
# =====================================================================================================
def validate_feature_frame(features, required_seasons=ALL_PANEL_SEASONS):
    problems = []
    missing_keys = [k for k in PANEL_KEYS if k not in features.columns]
    if missing_keys:
        return [f"feature frame missing identity key(s) {missing_keys}"]

    # TWO accepted schemas, both exact. The VETERAN contract is what a veteran-only frame must be;
    # the UNION contract is the composed veteran+rookie frame the frozen routing produces. A union
    # frame is accepted ONLY if all seven shipped buckets are feedable from it, so the wider schema
    # can never be a way to smuggle in an incomplete panel.
    cols = list(features.columns)
    if cols == list(FROZEN_UNION_FEATURE_COLUMNS):
        gaps = union_bucket_gaps(features)
        if gaps:
            problems.append("union feature frame cannot feed every shipped bucket: " + "; ".join(gaps))
    elif cols != list(FROZEN_FEATURE_COLUMNS):
        missing_frozen = [c for c in FROZEN_FEATURE_COLUMNS if c not in features.columns]
        if missing_frozen:
            problems.append(f"feature frame missing frozen column(s): {missing_frozen}")
        unexpected = sorted(set(features.columns) - set(FROZEN_UNION_FEATURE_COLUMNS))
        if unexpected:
            problems.append(f"feature frame carries column(s) outside the frozen contract: "
                            f"{unexpected}")
        if not missing_frozen and not unexpected:
            problems.append("feature frame matches neither the veteran nor the union contract "
                            "exactly (column order or membership differs)")

    dup = features.duplicated(subset=list(PANEL_KEYS)).sum()
    if dup:
        problems.append(f"feature frame has {dup} duplicate {PANEL_KEYS} row(s)")

    leaked = sorted(set(features.columns) & FORBIDDEN_IN_FEATURES)
    if leaked:
        problems.append(f"outcome-bearing column(s) present in the feature frame: {leaked}")

    seasons = set(pd.unique(features[SEASON_KEY].dropna()).tolist())
    expected = set(required_seasons)
    extra, absent = sorted(seasons - expected), sorted(expected - seasons)
    if extra:
        problems.append(f"unexpected season(s) in the feature frame: {extra}")
    if absent:
        problems.append(f"missing season(s) in the feature frame: {absent}")
    return problems


def validate_outcome_frame(outcomes):
    problems = []
    expected_cols = {PLAYER_KEY, SEASON_KEY, OUTCOME_COLUMN}
    if set(outcomes.columns) != expected_cols:
        return [f"outcome schema drift: expected exactly {sorted(expected_cols)}, "
                f"got {sorted(outcomes.columns)}"]
    dup = outcomes.duplicated(subset=list(PANEL_KEYS)).sum()
    if dup:
        problems.append(f"outcome frame has {dup} duplicate {PANEL_KEYS} row(s)")
    if not pd.api.types.is_numeric_dtype(outcomes[OUTCOME_COLUMN]):
        problems.append(f"{OUTCOME_COLUMN} must be numeric")
    return problems


def assemble_panel_core(features, outcomes, *, required_seasons=ALL_PANEL_SEASONS):
    """Pair frozen features with the real outcome using PRODUCTION semantics, WITHOUT merging them.

    Production (`build_rb_projection.assemble()`) LEFT-joins the weekly-stat target onto the feature
    rows and fills a missing pre-2026 `y` with **0.0** — a rostered player with no weekly stat row
    scored zero, and that is a real observation, not a missing one. An earlier revision of this module
    REFUSED those rows, which silently changed both the target and the denominator. It now matches
    production: **every eligible feature row is retained.**

    Returns three deliberately SEPARATE objects, so no object exists carrying both X and y:
      ``features``   the feature frame, guaranteed free of outcome-bearing columns;
      ``outcomes``   one row per feature row, keyed, with the target and its state;
      ``accounting`` a mutually exclusive, exhaustive partition of the rows.
    """
    problems = validate_feature_frame(features, required_seasons=required_seasons)
    problems += validate_outcome_frame(outcomes)
    if problems:
        raise AssemblyError("; ".join(problems))

    # v3.9x DEFENSIVE KEY-DTYPE ASSERTION. Both real readers canonicalize their own output, so this
    # can only fire for an INJECTED or hand-built frame — and when it does it must say so accurately,
    # naming the offending column and both dtypes, rather than surfacing later as a bogus "reordered"
    # or a silently upcast join key.
    key_problems = (canonical_key_dtype_problems(features, "feature frame")
                    + canonical_key_dtype_problems(outcomes, "outcome frame"))
    if key_problems:
        raise AssemblyError("panel key dtype contract violated (both real readers emit the canonical "
                            "dtypes; an injected frame must too): " + "; ".join(key_problems))

    keys = features[list(PANEL_KEYS)].copy()
    aligned = keys.merge(outcomes, on=list(PANEL_KEYS), how="left", validate="one_to_one")
    if len(aligned) != len(features):
        raise AssemblyError(f"alignment changed the row count: {len(features)} -> {len(aligned)}")

    missing_identity = aligned[PLAYER_KEY].isna().to_numpy()
    has_target = aligned[OUTCOME_COLUMN].notna().to_numpy()

    # Mutually exclusive by construction: identity first, then target presence.
    state = np.where(missing_identity, STATE_MISSING_IDENTITY,
                     np.where(has_target, STATE_MATCHED, STATE_ZERO_FILLED))
    aligned["outcome_state"] = state
    # Production fill: an eligible player-season with no weekly row scored 0.0.
    aligned.loc[state == STATE_ZERO_FILLED, OUTCOME_COLUMN] = 0.0

    if missing_identity.any():
        raise AssemblyError(f"{int(missing_identity.sum())} feature row(s) have a null {PLAYER_KEY}; "
                            f"identity must be resolved before assembly")

    fk = keys.drop_duplicates()
    unmatched_outcome = int(len(outcomes.merge(fk.assign(_f=1), on=list(PANEL_KEYS), how="left")
                                .query("_f.isna()", engine="python")))

    acct = {
        "n_feature_rows": int(len(features)),
        "n_outcome_rows": int(len(outcomes)),
        STATE_MISSING_IDENTITY: int((state == STATE_MISSING_IDENTITY).sum()),
        STATE_ZERO_FILLED: int((state == STATE_ZERO_FILLED).sum()),
        STATE_MATCHED: int((state == STATE_MATCHED).sum()),
        STATE_UNMATCHED_OUTCOME: unmatched_outcome,
    }
    partition = acct[STATE_MISSING_IDENTITY] + acct[STATE_ZERO_FILLED] + acct[STATE_MATCHED]
    if partition != acct["n_feature_rows"]:
        raise AssemblyError(f"accounting partition {partition} != {acct['n_feature_rows']} feature rows")

    if aligned[OUTCOME_COLUMN].isna().any():
        raise AssemblyError("a feature row still has no target after the production zero-fill")

    return {
        "features": features.copy(),
        "outcomes": aligned[[*PANEL_KEYS, OUTCOME_COLUMN, "outcome_state"]].copy(),
        "accounting": acct,
        "seasons": tuple(sorted(set(pd.unique(features[SEASON_KEY]).tolist()))),
    }


# =====================================================================================================
# ARM 0 BUCKET AUDIT — all SEVEN shipped bundles, not the four that happen to be easy
# =====================================================================================================
def arm0_bucket_table(models_dir=None, feature_columns=None, rookie_columns=None):
    """One row per shipped (position, bucket): the ordered `feature_cols`, its declared input, and
    which features that input actually supplies.

    Reads bundle METADATA only. `feature_columns` / `rookie_columns` let a test inject a column set
    instead of touching the real season dataset or the frozen rookie matrix. When `rookie_columns` is
    omitted the matrix's columns are taken from `rookie_matrix_columns()`, which VERIFIES provenance
    first — if that fails the rookie source is reported as unavailable, so readiness fails closed
    rather than trusting an unverified file.
    """
    import pickle
    md = MODELS_DIR if models_dir is None else pathlib.Path(models_dir)
    if feature_columns is None:
        feature_columns = set(pd.read_csv(FEATURE_SOURCE, nrows=0).columns)   # header only, 0 rows
    rookie_error = None
    if rookie_columns is None:
        try:
            rookie_columns = rookie_matrix_columns()
        except AssemblyError as exc:
            rookie_columns, rookie_error = (), str(exc)
    available = {SOURCE_SEASON_DATASET: set(feature_columns),
                 SOURCE_ROOKIE_MATRIX: set(rookie_columns)}

    rows = []
    for (pos, bucket), (fname, expected_n, source) in sorted(SHIPPED_ARM0_BUCKETS.items()):
        path = md / fname
        if not path.exists():
            rows.append({"position": pos, "bucket": bucket, "bundle": fname, "source": source,
                         "n_features": None, "missing": None, "error": f"bundle missing: {path}"})
            continue
        b = pickle.loads(path.read_bytes())
        fc = tuple(b.get("feature_cols") or ())
        spec_problems = bundle_spec_problems(b)
        # The two denominators, computed separately and never merged (see the note above).
        missing_sd = [c for c in fc if c not in available[SOURCE_SEASON_DATASET]]
        supplied = available.get(source, set())
        missing_src = [c for c in fc if c not in supplied]
        rows.append({
            "position": pos, "bucket": bucket, "bundle": fname, "source": source,
            "target": b.get("target"), "n_features": len(fc), "expected_n": expected_n,
            "n_missing_from_season_dataset": len(missing_sd),
            "missing_from_season_dataset": missing_sd,
            "n_missing_from_declared_source": len(missing_src),
            "missing_from_declared_source": missing_src,
            "source_exists": source is not None and bool(supplied),
            "features_available": bool(fc) and not missing_src,
            # What the experiment actually inherits from the bundle: the SPECIFICATION. The fitted
            # estimator is never used (see BUNDLE_SPEC_FIELDS above), so a bundle is usable when its
            # spec is complete and well-formed, NOT when its historical training matrix matches.
            "spec_contract_ok": not spec_problems,
            "spec_problems": spec_problems,
            "complete": bool(fc) and not missing_src and not spec_problems,
            "feature_cols": fc,
            "error": rookie_error if source == SOURCE_ROOKIE_MATRIX and rookie_error else None,
        })
    return rows


def bundle_spec_problems(bundle):
    """Is the bundle's SPECIFICATION complete and well-formed? Returns a problem list.

    Only the fields `fit_predict` and `arm0_definition` actually consume. The serialized estimator is
    deliberately NOT inspected beyond its presence: it is never fitted, predicted from, or carried into
    a fold, so its state cannot reach a result.
    """
    p = []
    for field in BUNDLE_SPEC_FIELDS:
        if field not in bundle:
            p.append(f"spec field {field!r} is absent")
    if p:
        return p
    if not bundle["feature_cols"]:
        p.append("feature_cols is empty")
    if not isinstance(bundle["family"], str) or not bundle["family"]:
        p.append(f"family is {bundle['family']!r}")
    if not isinstance(bundle["params"], dict) or not bundle["params"]:
        p.append("params is not a non-empty dict")
    if bundle["seed"] is None:
        p.append("seed is None; the fold fit would not be reproducible")
    if bundle["target"] != OUTCOME_COLUMN:
        p.append(f"target is {bundle['target']!r}, must be {OUTCOME_COLUMN!r}")
    return p


def bucket_frame_satisfies_bundle(frame_columns, position, bucket, models_dir=None):
    """Does an assembled bucket-specific frame carry every required feature, in bundle order?"""
    import pickle
    md = MODELS_DIR if models_dir is None else pathlib.Path(models_dir)
    fname = SHIPPED_ARM0_BUCKETS[(position, bucket)][0]
    fc = tuple(pickle.loads((md / fname).read_bytes())["feature_cols"])
    cols = list(frame_columns)
    missing = [c for c in fc if c not in cols]
    if missing:
        raise AssemblyError(f"{position}/{bucket} frame is missing {len(missing)} bundle feature(s): "
                            f"{missing[:8]}")
    order = [c for c in cols if c in set(fc)]
    if tuple(order) != fc:
        raise AssemblyError(f"{position}/{bucket} frame does not present features in bundle order")
    leaked = sorted(set(cols) & FORBIDDEN_IN_FEATURES)
    if leaked:
        raise AssemblyError(f"{position}/{bucket} frame carries outcome-bearing column(s): {leaked}")
    return True


def activation_readiness(models_dir=None, feature_columns=None, rookie_columns=None):
    """Can an AUTHORIZED real run actually assemble every shipped bundle? Returns (ok, detail).

    This is a SEPARATE layer from prefit integrity. `preflight()` answering 21/21 says the prefit
    system is sound; it must never be read as "ready to activate", and readiness being True is not
    authorization either — `authorized_real_gate()` still requires both locks, which stay closed.
    """
    rows = arm0_bucket_table(models_dir=models_dir, feature_columns=feature_columns,
                             rookie_columns=rookie_columns)
    blocked = [r for r in rows if r.get("error") or not r.get("complete")]
    if not blocked:
        by_source = {}
        for r in rows:
            by_source.setdefault(r["source"], []).append(f"{r['position']}/{r['bucket']}")
        detail = "; ".join(f"{src}: {', '.join(sorted(v))}" for src, v in sorted(by_source.items()))
        return True, (f"all {len(rows)} shipped Arm 0 buckets have a complete pinned feature source "
                      f"({detail}). READY IS NOT AUTHORIZED: both real-fit locks remain closed and "
                      f"`authorized_real_gate()` still refuses.")
    parts = []
    for r in blocked:
        if r.get("error"):
            parts.append(f"{r['position']}/{r['bucket']}: {r['error']}")
            continue
        if r.get("features_available") and not r.get("spec_contract_ok"):
            parts.append(f"{r['position']}/{r['bucket']} ({r['bundle']}): features are complete, but "
                         f"the bundle SPECIFICATION is not: {'; '.join(r['spec_problems'])}")
            continue
        src = r["source"] or "NO DECLARED SOURCE"
        if not r["source_exists"]:
            # Say the source is absent; do NOT dress that up as a feature-overlap statistic.
            parts.append(f"{r['position']}/{r['bucket']} ({r['bundle']}, {r['n_features']} features): "
                         f"declared source {src!r} DOES NOT EXIST, so it supplies none of them; the "
                         f"season dataset separately lacks {r['n_missing_from_season_dataset']} of "
                         f"{r['n_features']}")
        else:
            parts.append(f"{r['position']}/{r['bucket']} ({r['bundle']}): "
                         f"{r['n_missing_from_declared_source']} of {r['n_features']} features missing "
                         f"from {src}")
    return False, ("ACTIVATION NOT READY — " + "; ".join(parts) + ". " + ROOKIE_INPUT_BLOCKER)


# The mode a preflight result must carry to authorize a REAL run. A `synthetic_prefit` result is a
# statement that both locks are CLOSED; treating it as authorization inverts its meaning.
AUTHORIZED_RUN_MODE = "authorized_real"
SYNTHETIC_RUN_MODE = "synthetic_prefit"

# --- the FROZEN authorization vocabulary ------------------------------------------------------------
# An earlier revision let the caller pass `expected_checks`, so `expected_checks=()` with an empty
# `checks` dict authorised a real run on "0/0 checks" — the frozen vocabulary was caller-controlled,
# which is the same class of defect as a checker that trusts its input. The tuple below is a LITERAL
# held here, the gate uses only it, and NO parameter can replace, shorten or extend it.
# `test_the_frozen_authorization_vocabulary_matches_the_harness` pins it by value against the harness's
# canonical `PREFLIGHT_CHECKS`.
FROZEN_AUTHORIZED_PREFLIGHT_CHECKS = (
    "protected_hashes",
    "v39_artifacts_pinned",
    "v39_artifacts_readable",
    "no_unauthorized_v39_artifact",
    "no_coaching_parquet",
    "feature_table_keys_and_rows",
    "design_a_outer_identity_coverage",
    "unknown_and_no_history_routing",
    "forbidden_feature_policy",
    "manifest_full_x_matches_bundles",
    "manifest_qb_rookie_null",
    "coverage_reconciles",
    "lineage_strict_timing",
    "lineage_states_the_primary_policy",
    "contribution_lineage_reconciles",
    "design_b_oracle_and_unselectable",
    "production_models_identical",
    "no_real_outcome_access",
    "assembly_module_contract",
    # RENAMED v3.9w from `pipeline_timing_assertions_ran`: the check is phase-aware and in the pre-run
    # phase it passes precisely because the assertions have NOT run, so "…_ran" was a false name.
    "pipeline_timing_assertion_state",
    "run_mode_locks",
)

# The two gate phases, pinned here BY VALUE against the harness's own literals so a phase can neither
# be renamed on one side only nor widened by a caller.
PREFLIGHT_PHASE_PRE_RUN = "pre_run"
PREFLIGHT_PHASE_POST_PIPELINE = "post_pipeline"
PREFLIGHT_PHASES = (PREFLIGHT_PHASE_PRE_RUN, PREFLIGHT_PHASE_POST_PIPELINE)


def _is_exact_int(value, expected):
    """int equality that refuses bool. `True == 1` in Python, so `isinstance(x, bool)` must be excluded."""
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _validate_preflight_shape(preflight_result, expected_phase):
    """Gate shape validation, FAIL-CLOSED. Returns a list of problems; empty means it authorizes.

    PRIVATE and phase-parameterised. The two PUBLIC entry points below each pin their own phase
    literal and take NO phase parameter, for the same reason `expected_checks` was removed: a gate
    whose vocabulary the caller supplies is not a gate. `validate_authorized_preflight` accepts only
    `pre_run`; `validate_post_pipeline_preflight` accepts only `post_pipeline`; neither result can be
    replayed as the other.

    Takes NO vocabulary parameter: it validates against `FROZEN_AUTHORIZED_PREFLIGHT_CHECKS` only.

    The frozen schema, matching what `preflight()` actually emits:
      all_ok    exactly True
      run_mode  exactly "authorized_real"
      phase     exactly the expected phase literal for this gate
      n_checks  exactly 21, an int and not a bool
      n_failed  exactly integer 0, not a bool
      failures  PRESENT and an EMPTY DICT — measured: the real preflight emits `failures = {}`,
                a dict, not an integer. Missing / None / non-empty / wrong type all refuse.
      checks    a dict whose keys are exactly the frozen names, each value itself a dict whose
                "ok" is exactly True.

    This function never raises on a malformed input: every shape is reported as a problem. An earlier
    version crashed with `AttributeError` on `checks={"protected_hashes": True}` because it called
    `.get()` on a non-dict — a crash is not a refusal, and a caller that catches broadly could read it
    as neither.
    """
    p = []
    if not isinstance(preflight_result, dict):
        return [f"preflight result is {type(preflight_result).__name__}, not a dict"]

    _MISSING = object()

    if preflight_result.get("all_ok") is not True:
        p.append(f"all_ok is {preflight_result.get('all_ok', _MISSING)!r}, must be exactly True")

    mode = preflight_result.get("run_mode", _MISSING)
    if mode != AUTHORIZED_RUN_MODE:
        shown = "MISSING" if mode is _MISSING else repr(mode)
        p.append(f"run_mode is {shown}, must be exactly {AUTHORIZED_RUN_MODE!r}"
                 + (" — a synthetic_prefit result asserts BOTH LOCKS CLOSED and can never authorize a "
                    "real run" if mode == SYNTHETIC_RUN_MODE else ""))

    phase = preflight_result.get("phase", _MISSING)
    if phase != expected_phase:
        shown = "MISSING" if phase is _MISSING else repr(phase)
        p.append(f"phase is {shown}, must be exactly {expected_phase!r}"
                 + (f" — a {phase!r} result attests a DIFFERENT pipeline-counter state and cannot be "
                    f"replayed as {expected_phase!r} clearance"
                    if isinstance(phase, str) and phase in PREFLIGHT_PHASES else ""))

    expected = FROZEN_AUTHORIZED_PREFLIGHT_CHECKS
    n_checks = preflight_result.get("n_checks", _MISSING)
    if not _is_exact_int(n_checks, len(expected)):
        shown = "MISSING" if n_checks is _MISSING else repr(n_checks)
        p.append(f"n_checks is {shown}, must be exactly integer {len(expected)}")

    n_failed = preflight_result.get("n_failed", _MISSING)
    if not _is_exact_int(n_failed, 0):
        shown = "MISSING" if n_failed is _MISSING else repr(n_failed)
        p.append(f"n_failed is {shown}, must be exactly integer 0")

    if "failures" not in preflight_result:
        p.append("failures is MISSING; it must be present and empty")
    else:
        failures = preflight_result["failures"]
        if not isinstance(failures, dict):
            p.append(f"failures is {type(failures).__name__}, must be a dict (the real preflight "
                     f"emits an empty dict)")
        elif failures:
            p.append(f"failures is non-empty ({len(failures)}) while n_failed claims 0 — contradictory")

    if "checks" not in preflight_result:
        p.append("checks is MISSING")
    else:
        checks = preflight_result["checks"]
        if not isinstance(checks, dict):
            p.append(f"checks is {type(checks).__name__}, must be a dict")
        else:
            missing = [c for c in expected if c not in checks]
            extra = [c for c in checks if c not in expected]
            if missing:
                p.append(f"checks is missing {missing}")
            if extra:
                p.append(f"checks has unexpected entries {extra}")
            malformed, not_ok = [], []
            for c in expected:
                if c not in checks:
                    continue
                entry = checks[c]
                if not isinstance(entry, dict):
                    malformed.append(f"{c}={type(entry).__name__}")
                elif entry.get("ok") is not True:
                    not_ok.append(c)
            if malformed:
                p.append(f"check entr(ies) are not dicts: {malformed}")
            if not_ok:
                p.append(f"check(s) not explicitly ok: {sorted(not_ok)}")

    return p


def validate_authorized_preflight(preflight_result):
    """Gate 1 (PRE-RUN), FAIL-CLOSED. Empty problem list means the result authorizes a real run.

    Accepts ONLY a `pre_run` result: 21/21 in `authorized_real` with every pipeline timing counter
    exactly zero. A `post_pipeline` result is refused here even though it is also 21/21, because it
    attests that a pipeline has ALREADY executed and therefore cannot be pre-run clearance.
    """
    return _validate_preflight_shape(preflight_result, PREFLIGHT_PHASE_PRE_RUN)


def validate_post_pipeline_preflight(preflight_result):
    """Gate 2 (POST-PIPELINE), FAIL-CLOSED. Empty problem list means results may be composed/written.

    Accepts ONLY a `post_pipeline` result: the same 21 checks in `authorized_real`, with every frozen
    timing assertion POSITIVE. A `pre_run` result is refused, so pre-run clearance can never be
    replayed to authorize a write.
    """
    return _validate_preflight_shape(preflight_result, PREFLIGHT_PHASE_POST_PIPELINE)


def authorized_real_gate(preflight_result, models_dir=None, feature_columns=None,
                         rookie_columns=None):
    """BOTH gates an authorized real run must clear BEFORE any outcome reader is called.

    Gate 1 — a preflight result that is *itself* an authorized-real result, validated against the
             module-frozen `FROZEN_AUTHORIZED_PREFLIGHT_CHECKS`. **There is deliberately no parameter
             for the expected vocabulary**: an earlier signature accepted `expected_checks`, and
             `expected_checks=()` with an empty `checks` dict authorised a real run on "0/0 checks".
    Gate 2 — activation readiness: every shipped Arm 0 bucket has a complete pinned feature source.

    Both are mandatory. The function is fail-closed AND never raises: anything missing, malformed,
    synthetic-mode, partially locked or self-contradictory returns `(False, detail)`.
    """
    problems = [f"gate 1 (authorized preflight): {msg}"
                for msg in validate_authorized_preflight(preflight_result)]

    try:
        ready, ready_detail = activation_readiness(models_dir=models_dir,
                                                   feature_columns=feature_columns,
                                                   rookie_columns=rookie_columns)
    except Exception as exc:                      # noqa: BLE001 - a crash must refuse, not propagate
        ready, ready_detail = False, f"readiness check raised {type(exc).__name__}: {exc}"
    if not ready:
        problems.append(f"gate 2 (activation readiness): {ready_detail}")

    if problems:
        return False, ("AUTHORIZED REAL RUN REFUSED — " + " || ".join(problems))
    n = len(FROZEN_AUTHORIZED_PREFLIGHT_CHECKS)
    return True, (f"both gates clear: preflight all_ok in {AUTHORIZED_RUN_MODE} mode with "
                  f"{n}/{n} frozen checks and 0 failures, and every shipped Arm 0 bucket has a "
                  f"complete pinned feature source")


def assert_no_outcome_in_matrix(matrix_columns, label="feature matrix"):
    leaked = sorted(set(matrix_columns) & FORBIDDEN_IN_FEATURES)
    if leaked:
        raise AssemblyError(f"{label} contains outcome-bearing column(s): {leaked}")
    return True


# =====================================================================================================
# A1-A6 — this module's own structural contract, checked at runtime like C1-C7 + C4b
# =====================================================================================================
ASSEMBLY_MODULE = "assemble_real_panel_v39.py"
ASSEMBLY_BANNED_CALLEES = frozenset({"load_player_stats", "load_pbp", "load_pbp_stats",
                                     "load_draft_picks", "load_combine", "load_schedules",
                                     "load_rosters", "load_players",
                                     "fit", "fit_final_model", "walk_forward"})
# A2, repaired: ban the IMPORT, not the call shape.
#
# Receiver-name matching was evadable four ways that all returned ok=True — `import requests as r;
# r.get(...)`, `from requests import get; get(...)`, `requests.Session().get(...)`, and
# `client = requests.Session(); client.get(...)`. Chasing call shapes means chasing aliasing, and
# aliasing always wins. This module needs NO network-capable package, so the reliable rule is that it
# may not import one. A module that cannot import `requests` cannot call it under any name.
NETWORK_ROOT_MODULES = frozenset({"requests", "httpx", "urllib", "urllib3", "aiohttp", "nflreadpy",
                                  "socket", "http", "ftplib", "telnetlib", "webbrowser"})
NETWORK_FUNCTIONS = frozenset({"urlopen", "urlretrieve"})
ASSEMBLY_READER_CALLEES = frozenset({"read_csv", "read_parquet", "read_json", "open",
                                     "ParquetFile"})
ASSEMBLY_CONTRACT_NAME = "A1-A6"
ASSEMBLY_OK_DETAIL = (
    "assemble_real_panel_v39.py satisfies the frozen assembly contract A1-A6 (no import-time I/O, no "
    "live loader or network fallback, every reader explicit and default-closed, both inputs repo-owned "
    "and pinned, REG-only 2014-2025 target reproducing production, outcome kept out of the feature "
    "frame, no model fit)")


def assembly_module_contract(source=None):
    """A1 no module-level I/O · A2 no network-capable import and no live loader · A3 every reader call
    inside a function · A4 no fitting · A5 the pins, schema, season set and formula are declared and the
    outcome is forbidden in features · A6 the default readers refuse. Returns (ok, detail).

    DELIBERATE LIMITS, stated rather than papered over. A2 is a rule about the module's import list and
    its call names. It does NOT cover `__import__`/`importlib.import_module` with a computed name,
    `eval`/`exec`, a network client injected as a function argument, or a third-party package that
    itself fetches. This is a structural gate against the realistic edit, not a theorem about arbitrary
    Python — the same disclaimer C1-C7 + C4b carries.
    """
    import ast
    src = (HERE / ASSEMBLY_MODULE).read_text(encoding="utf-8") if source is None else source
    problems = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"{ASSEMBLY_MODULE}: unparseable ({e})"

    inside = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                inside.add(id(sub))
    for node in ast.walk(tree):
        # A2 — no network-capable IMPORT, under any alias or from-form.
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root in NETWORK_ROOT_MODULES:
                    problems.append(f"A2: imports network module {a.name!r}"
                                    + (f" as {a.asname}" if a.asname else "")
                                    + f" at line {node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in NETWORK_ROOT_MODULES:
                names = ", ".join(a.name for a in node.names)
                problems.append(f"A2: from {node.module!r} import {names} at line {node.lineno}")
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in ASSEMBLY_BANNED_CALLEES:
                problems.append(f"A2/A4: calls {name}() at line {node.lineno}")
            if name in NETWORK_FUNCTIONS:
                problems.append(f"A2: network call {name}() at line {node.lineno}")
            if name in ASSEMBLY_READER_CALLEES and id(node) not in inside:
                problems.append(f"A1/A3: module-level {name}() at line {node.lineno}")

    # A5 — the frozen declarations must be present and self-consistent.
    if OUTCOME_COLUMN not in FORBIDDEN_IN_FEATURES:
        problems.append("A5: the outcome column is not in FORBIDDEN_IN_FEATURES")
    if set(FROZEN_FEATURE_COLUMNS) & FORBIDDEN_IN_FEATURES:
        problems.append("A5: the frozen feature contract names a forbidden column")
    if tuple(ALL_PANEL_SEASONS) != tuple(range(2014, 2026)):
        problems.append(f"A5: panel seasons are {ALL_PANEL_SEASONS}, expected 2014-2025")
    if len(WEEKLY_SNAPSHOT_SHA256) != 64 or len(VETERAN_SNAPSHOT_SHA256) != 64:
        problems.append("A5: an input pin is malformed")
    if tuple(VETERAN_FEATURE_COLUMNS) != IDENTITY_COLUMNS + ARM0_VETERAN_FEATURES:
        problems.append("A5: the consumed veteran schema is not identity + the 32 features")
    if len(VETERAN_FEATURE_COLUMNS) != VETERAN_SNAPSHOT_COLS:
        problems.append(f"A5: consumed schema is {len(VETERAN_FEATURE_COLUMNS)} column(s) but "
                        f"VETERAN_SNAPSHOT_COLS is {VETERAN_SNAPSHOT_COLS}")
    if REG_SEASON_TYPE != "REG":
        problems.append("A5: the season-type filter is not REG")
    # A5 — the rookie-matrix declarations, pinned independently of the generator.
    if len(ROOKIE_MATRIX_SHA256) != 64:
        problems.append("A5: the rookie matrix pin is malformed")
    if len(ROOKIE_MATRIX_COLUMNS) != ROOKIE_MATRIX_COLS:
        problems.append(f"A5: the pinned rookie schema has {len(ROOKIE_MATRIX_COLUMNS)} column(s) but "
                        f"ROOKIE_MATRIX_COLS is {ROOKIE_MATRIX_COLS}")
    if len(set(ROOKIE_MATRIX_COLUMNS)) != len(ROOKIE_MATRIX_COLUMNS):
        problems.append("A5: the pinned rookie schema repeats a column")
    if not set(ROOKIE_MATRIX_IDENTITY) <= set(ROOKIE_MATRIX_COLUMNS):
        problems.append("A5: a rookie identity column is absent from the pinned schema")
    if set(ROOKIE_MATRIX_COLUMNS) & FORBIDDEN_IN_FEATURES:
        problems.append("A5: the pinned rookie schema names a forbidden column")
    for reader, kind in ((default_feature_reader, "feature"), (default_outcome_reader, "outcome"),
                         (default_rookie_matrix_reader, "rookie matrix")):
        try:
            reader()
        except AssemblyError:
            pass
        else:
            problems.append(f"A6: the default {kind} reader did not refuse")

    return (not problems), ("; ".join(problems[:4]) if problems else ASSEMBLY_OK_DETAIL)
