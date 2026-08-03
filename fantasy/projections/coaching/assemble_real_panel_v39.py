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

NOT READY — the features. Arm 0 ships SEVEN bundles. The four veteran buckets are fully supplied by the
pinned season dataset; the three ROOKIE buckets (RB/WR/TE) have no repo-owned source at all. See
`ROOKIE_INPUT_BLOCKER` and `activation_readiness()`, which returns False until Joseph resolves it.

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
FEATURE_SOURCE = SEAS / "season_dataset_2014_2026.csv"
FEATURE_SOURCE_MD5 = "8322a59e43251820cb393d40787f60e6"

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

# Declared input sources. `season_dataset` is repo-owned and pinned; `rookie_matrix` does not exist as
# a repo-owned artifact and cannot be rebuilt from a clean checkout (see ROOKIE_INPUT_BLOCKER).
SOURCE_SEASON_DATASET = "season_dataset"
SOURCE_ROOKIE_MATRIX = "rookie_matrix"
SOURCE_UNRESOLVED = None

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
ROOKIE_INPUT_BLOCKER = (
    "the three rookie buckets have NO repo-owned feature source. Of their bundle features, the season "
    "dataset lacks RB 32 of 41, WR 35 of 44 and TE 35 of 44 (combine, college-box and PFF-derived); the "
    "declared rookie_matrix source does not exist at all, so it supplies none of them. Production "
    "regenerates them via fantasy/rookie/harness, which calls live nflreadpy loaders and reads "
    "fantasy/seasonal_projections/pff/ — a directory holding 418 local files and ZERO tracked files "
    "(.gitignore:37). A clean checkout therefore cannot assemble these buckets. Joseph's decision is "
    "required; see V39_ACTIVATION_MANIFEST.md section 0b.")

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


def authorized_feature_reader(path=None, verify_hash=True):
    """Build the REAL feature reader. Constructing it is not reading; the returned callable reads.

    `usecols` is explicit, so a forbidden target or market column is never loaded at all, and the frame
    is filtered to 2014-2025 BEFORE it is returned — the source runs to 2026, which has no outcome.
    """
    src = FEATURE_SOURCE if path is None else pathlib.Path(path)

    def _read():
        if not src.exists():
            raise AssemblyError(f"feature source missing: {src}")
        if verify_hash:
            actual = file_md5(src)
            if actual != FEATURE_SOURCE_MD5:
                raise AssemblyError(f"feature source hash drift: expected {FEATURE_SOURCE_MD5}, "
                                    f"got {actual}")
        header = pd.read_csv(src, nrows=0)
        available = set(header.columns)
        missing = [c for c in FROZEN_FEATURE_COLUMNS if c not in available]
        if missing:
            raise AssemblyError(f"feature source is missing frozen column(s): {missing}")
        forbidden_loaded = sorted(set(FROZEN_FEATURE_COLUMNS) & FORBIDDEN_IN_FEATURES)
        if forbidden_loaded:
            raise AssemblyError(f"the frozen contract itself names forbidden column(s): "
                                f"{forbidden_loaded}")

        df = pd.read_csv(src, usecols=list(FROZEN_FEATURE_COLUMNS))
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
    return out[[PLAYER_KEY, SEASON_KEY, OUTCOME_COLUMN]]


# =====================================================================================================
# VALIDATION
# =====================================================================================================
def validate_feature_frame(features, required_seasons=ALL_PANEL_SEASONS):
    problems = []
    missing_keys = [k for k in PANEL_KEYS if k not in features.columns]
    if missing_keys:
        return [f"feature frame missing identity key(s) {missing_keys}"]

    missing_frozen = [c for c in FROZEN_FEATURE_COLUMNS if c not in features.columns]
    if missing_frozen:
        problems.append(f"feature frame missing frozen column(s): {missing_frozen}")
    unexpected = sorted(set(features.columns) - set(FROZEN_FEATURE_COLUMNS))
    if unexpected:
        problems.append(f"feature frame carries column(s) outside the frozen contract: {unexpected}")

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
def arm0_bucket_table(models_dir=None, feature_columns=None):
    """One row per shipped (position, bucket): the ordered `feature_cols`, its declared input, and
    which features that input actually supplies.

    Reads bundle METADATA only. `feature_columns` lets a test inject a column set instead of touching
    the real season dataset.
    """
    import pickle
    md = MODELS_DIR if models_dir is None else pathlib.Path(models_dir)
    if feature_columns is None:
        feature_columns = set(pd.read_csv(FEATURE_SOURCE, nrows=0).columns)   # header only, 0 rows
    available = {SOURCE_SEASON_DATASET: set(feature_columns), SOURCE_ROOKIE_MATRIX: set()}

    rows = []
    for (pos, bucket), (fname, expected_n, source) in sorted(SHIPPED_ARM0_BUCKETS.items()):
        path = md / fname
        if not path.exists():
            rows.append({"position": pos, "bucket": bucket, "bundle": fname, "source": source,
                         "n_features": None, "missing": None, "error": f"bundle missing: {path}"})
            continue
        b = pickle.loads(path.read_bytes())
        fc = tuple(b.get("feature_cols") or ())
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
            "complete": bool(fc) and not missing_src, "feature_cols": fc, "error": None,
        })
    return rows


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


def activation_readiness(models_dir=None, feature_columns=None):
    """Can an AUTHORIZED real run actually assemble every shipped bundle? Returns (ok, detail).

    This is a SEPARATE layer from prefit integrity. `preflight()` answering 21/21 says the prefit
    system is sound; it must never be read as "ready to activate". Until the rookie input decision is
    resolved this returns False and names each bucket that cannot be built.
    """
    rows = arm0_bucket_table(models_dir=models_dir, feature_columns=feature_columns)
    blocked = [r for r in rows if r.get("error") or not r.get("complete")]
    if not blocked:
        return True, (f"all {len(rows)} shipped Arm 0 buckets have a complete pinned feature source")
    parts = []
    for r in blocked:
        if r.get("error"):
            parts.append(f"{r['position']}/{r['bucket']}: {r['error']}")
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
    "pipeline_timing_assertions_ran",
    "run_mode_locks",
)


def _is_exact_int(value, expected):
    """int equality that refuses bool. `True == 1` in Python, so `isinstance(x, bool)` must be excluded."""
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def validate_authorized_preflight(preflight_result):
    """Gate 1, FAIL-CLOSED. Returns a list of problems; empty means the result authorizes a real run.

    Takes NO vocabulary parameter: it validates against `FROZEN_AUTHORIZED_PREFLIGHT_CHECKS` only.

    The frozen schema, matching what `preflight()` actually emits:
      all_ok    exactly True
      run_mode  exactly "authorized_real"
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


def authorized_real_gate(preflight_result, models_dir=None, feature_columns=None):
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
                                                   feature_columns=feature_columns)
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
ASSEMBLY_READER_CALLEES = frozenset({"read_csv", "read_parquet", "read_json", "open"})
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
    if len(WEEKLY_SNAPSHOT_SHA256) != 64 or len(FEATURE_SOURCE_MD5) != 32:
        problems.append("A5: an input pin is malformed")
    if REG_SEASON_TYPE != "REG":
        problems.append("A5: the season-type filter is not REG")
    for reader, kind in ((default_feature_reader, "feature"), (default_outcome_reader, "outcome")):
        try:
            reader()
        except AssemblyError:
            pass
        else:
            problems.append(f"A6: the default {kind} reader did not refuse")

    return (not problems), ("; ".join(problems[:4]) if problems else ASSEMBLY_OK_DETAIL)
