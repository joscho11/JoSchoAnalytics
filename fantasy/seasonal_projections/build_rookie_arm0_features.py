"""Build the frozen, OUTCOME-FREE rookie Arm 0 feature matrix (prereg v3.9, Option A).

    fantasy/seasonal_projections/snapshots/rookie_arm0_features_2014_2025.parquet

WHY THIS EXISTS
---------------
Arm 0 ships seven bundles. The four VETERAN buckets are fully supplied by the pinned
`season_dataset_2014_2026.csv`. The three ROOKIE buckets (RB/WR/TE) need 41/44/44 features of which
32/35/35 are combine, college-box and PFF-derived and are NOT in the season dataset. Production
regenerates them through `fantasy/rookie/harness/assemble_features.py`, which calls live nflverse
loaders and reads the PRIVATE PFF library — so a clean checkout cannot build them.

Option A, authorized by Joseph 2026-08-03: freeze a repo-owned, outcome-free matrix of DERIVED feature
values. Raw PFF stays private and untracked; only derived values are committed.

NOT A PARALLEL IMPLEMENTATION
-----------------------------
This module does not reimplement any feature. It imports the production
`assemble_features.build_features()` and calls it, injecting the two nflverse loaders from repo-owned
snapshots so the derivation is hermetic. `_load_pff` is left REAL and reads Joseph's authorized private
PFF library — that is the one-time private input the freeze exists to capture. The landing-spot block
is read from the pinned season dataset, which is where production reads it.

WHAT IT MUST NOT CONTAIN
------------------------
No fantasy outcome, target, label, sample weight, ADP, market projection, or any target-season realized
statistic. `HIT` construction is never touched: the population comes from the season dataset's
`is_rookie` flag, not from either `panel_hit.parquet` / `panel_scoring.parquet`, which are
outcome-derived.

Run:  python fantasy/seasonal_projections/build_rookie_arm0_features.py
"""
import argparse
import hashlib
import importlib.util
import pathlib
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SNAP = HERE / "snapshots"
HARNESS = REPO / "fantasy" / "rookie" / "harness"

OUT = SNAP / "rookie_arm0_features_2014_2025.parquet"
SEASON_DATASET = HERE / "season_dataset_2014_2026.csv"       # historical; no longer read here
VETERAN_SNAPSHOT = SNAP / "veteran_arm0_features_2014_2025.parquet"
COMBINE = SNAP / "combine.parquet"
DRAFT = SNAP / "draft_picks.parquet"
COLLEGE = HERE / "college_features.csv"

FIRST_SEASON, LAST_SEASON = 2014, 2025
POSITIONS = ("RB", "WR", "TE")           # QB rookie was HELD; there is no QB rookie bundle
PLAYER_KEY, SEASON_KEY = "player_id", "season"

# Identity / routing. `is_rookie` and `position` are the routing keys Arm 0 uses to pick a bundle.
IDENTITY_COLUMNS = (PLAYER_KEY, SEASON_KEY, "position", "is_rookie", "norm_name")

# Landing-spot features that live in the season dataset rather than the rookie harness.
LANDING_COLUMNS = ("coach_changed", "qb_changed", "prior_team_pass_rate", "prior_team_plays",
                   "vacated_target_share", "vacated_rush_share")

# The union of the three rookie pools, in pinned order: RB's 41 in bundle order, then the 13 WR/TE
# columns RB does not use, in WR bundle order. Derived from tests/arm0_bundle_pins.py and asserted
# against the bundles at build time.
UNION_FEATURE_COLUMNS = (
    "draft_round", "draft_pick", "log_pick", "age",
    "forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "ht_in", "wt", "bmi",
    "speed_score",
    "cfb_final_dom", "cfb_best_dom", "cfb_scrim_ypg", "cfb_rush_ypg", "cfb_rec_ypg", "cfb_ypc",
    "cfb_ypr", "cfb_career_scrim_yds", "cfb_career_scrim_td", "cfb_seasons", "cfb_breakout_class",
    "pff_rushing_grades_run", "pff_rushing_grades_offense", "pff_rushing_elusive_rating",
    "pff_rushing_breakaway_percent", "pff_rushing_elu_yco", "pff_rushing_avoided_tackles",
    "pff_rushing_first_downs", "pff_rushing_touchdowns",
    "pff_receiving_yprr", "pff_receiving_routes",
    "coach_changed", "qb_changed", "prior_team_pass_rate", "prior_team_plays",
    "vacated_target_share", "vacated_rush_share",
    "cfb_rec_pg", "cfb_final_recshare",
    "pff_receiving_grades_offense", "pff_receiving_grades_pass_route",
    "pff_receiving_avg_depth_of_target", "pff_receiving_contested_catch_rate",
    "pff_receiving_drop_rate", "pff_receiving_yards_after_catch_per_reception",
    "pff_receiving_targeted_qb_rating", "pff_receiving_receptions", "pff_receiving_yards",
    "pff_receiving_touchdowns", "pff_receiving_avoided_tackles",
)

# Point-in-time provenance, carried INTO the artifact so the guarantee can be verified offline by
# anyone, without the private PFF library: for every row, the PFF college season the block came from
# must be strictly less than the NFL rookie season. These are NOT features and are in no bundle pool.
PROVENANCE_COLUMNS = ("pff_receiving_source_season", "pff_rushing_source_season")

FROZEN_COLUMNS = IDENTITY_COLUMNS + PROVENANCE_COLUMNS + UNION_FEATURE_COLUMNS

# Anything here would make the artifact an outcome carrier. Checked before writing.
#
# The tokens are deliberately PRECISE. A first draft used `_y` and `ppg`, which flagged ten legitimate
# COLLEGE columns — `cfb_scrim_ypg`, `cfb_ypc`, `cfb_ypr`, `pff_receiving_yprr`, `pff_rushing_elu_yco`,
# `pff_receiving_yards...`. Those are pre-NFL college measurements, definitionally not target-season
# outcomes, and rejecting them is the over-broad-matcher failure this project keeps hitting. Yards per
# route run in college is not a fantasy outcome.
FORBIDDEN_SUBSTRINGS = ("fantasy_points", "half_ppr", "target_ppg", "target_games", "sample_weight",
                        "season_total", "adp_", "sleeper", "hit_prob", "outcome", "yhat")
# Exact names that would be outcomes regardless of context.
FORBIDDEN_EXACT = frozenset({"y", "ppg", "games", "label", "target", "adp", "projection",
                             "prior_ppg", "prior_half_ppr", "reconstructed"})


# Every non-PFF input is PINNED. A rebuild against a drifted input must fail loudly rather than
# silently produce a different artifact under the same provenance story. The PFF library is
# deliberately NOT pinned here: it is private, untracked and outside this repo's hash contract, which
# is exactly why the derived output is frozen instead of regenerated.
# The PRIVATE PFF input, fingerprinted without exposing a byte of it: one SHA-256 over the sorted
# relative paths and bytes of exactly the files the build CONSUMES (36 of the 941 local files — the
# receiving/rushing/passing college summaries for 2014-2025). Verified before any value is read and
# again after the build. Raw PFF files stay untracked; only this digest is repo-owned.
PFF_CONSUMED_SHA256 = "148e2465abb6389cdd4e741dee21f0d168638f91dc23f66407950d2fbd718038"
PFF_CONSUMED_FILES = 36
PFF_CONSUMED_KINDS = ("passing", "receiving", "rushing")
PFF_CONSUMED_SEASONS = tuple(range(2014, 2026))

INPUT_PINS = {
    # The IMMUTABLE 2014-2025 veteran snapshot, not the live production CSV. Pinning the CSV was the
    # wrong scope: a deploy-season-2026 refresh moved its md5 without changing one consumed value.
    "snapshots/veteran_arm0_features_2014_2025.parquet":
        ("sha256", "45cb2583acf7d046ecf54275d1ee3e70fcb9e4882d69a6b203e36350376bfbc8"),
    "college_features.csv":         ("md5", "32328aa482155d1c44687dd1bfc7f5ce"),
    "snapshots/combine.parquet":    ("sha256",
                                     "1b6c48a0b56e515b043dd678ea38a2e6ae83cb9de488e6a0a89f8b2f980bf2cf"),
    "snapshots/draft_picks.parquet": ("sha256",
                                      "d5e88f23a11e6208ebfe31be17fd974fb5b32efe94c1a5069fdae50039e56508"),
}


class BuildError(RuntimeError):
    """Any violation of the frozen build contract. Never caught here."""


def verify_inputs():
    """Hash every pinned input before reading a value from it. Returns the verified digests."""
    digests = {}
    problems = []
    for rel, (algo, pinned) in sorted(INPUT_PINS.items()):
        path = HERE / rel
        if not path.exists():
            problems.append(f"{rel}: MISSING")
            continue
        actual = hashlib.new(algo, path.read_bytes()).hexdigest()
        digests[rel] = actual
        if actual != pinned:
            problems.append(f"{rel}: {algo} {actual} != pinned {pinned}")
    if problems:
        raise BuildError("input provenance: " + "; ".join(problems))
    return digests


def expected_pff_files(mod):
    """Exactly the PFF files this build will consume — enumerated, not the whole local library."""
    return [mod.PFF / f"college_{yr}" / f"college_{kind}_summary_{yr}.csv"
            for kind in PFF_CONSUMED_KINDS for yr in PFF_CONSUMED_SEASONS
            if (mod.PFF / f"college_{yr}" / f"college_{kind}_summary_{yr}.csv").exists()]


def verify_pff_inputs(mod):
    """Fingerprint the private PFF inputs BEFORE a value is read. Raises on any drift."""
    files = expected_pff_files(mod)
    prov = mod.pff_provenance(files=files)
    problems = []
    if prov["n_files"] != PFF_CONSUMED_FILES:
        problems.append(f"{prov['n_files']} consumed files, pinned {PFF_CONSUMED_FILES}")
    if tuple(prov["kinds"]) != tuple(sorted(PFF_CONSUMED_KINDS)):
        problems.append(f"kinds {prov['kinds']} != {sorted(PFF_CONSUMED_KINDS)}")
    if tuple(prov["seasons"]) != PFF_CONSUMED_SEASONS:
        problems.append(f"seasons {prov['seasons']} != {list(PFF_CONSUMED_SEASONS)}")
    if prov["sha256"] != PFF_CONSUMED_SHA256:
        problems.append(f"aggregate sha256 {prov['sha256']} != pinned {PFF_CONSUMED_SHA256}")
    if problems:
        raise BuildError("PFF consumed-input provenance: " + "; ".join(problems))
    return prov


def _load_production_module():
    """Import the REAL production feature builder (no copy, no reimplementation)."""
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))          # for `from _utils import norm_name`
    spec = importlib.util.spec_from_file_location("assemble_features_production",
                                                  HARNESS / "assemble_features.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _frozen_population(season_dataset=None):
    """Every eligible rookie player-season. NO row is dropped for a missing measurement.

    Reads the IMMUTABLE veteran snapshot, not the live production CSV. Every column this needs —
    the identity/routing keys and the six landing-spot features — is inside the snapshot's consumed
    contract, and the snapshot is already windowed to 2014-2025. That makes both generators
    independent of deploy-season 2026 refreshes. A caller may still inject a fixture path.
    """
    src = VETERAN_SNAPSHOT if season_dataset is None else pathlib.Path(season_dataset)
    cols = [PLAYER_KEY, SEASON_KEY, "position", "is_rookie", "norm_name"] + list(LANDING_COLUMNS)
    sd = (pd.read_parquet(src, columns=cols) if src.suffix == ".parquet"
          else pd.read_csv(src, usecols=cols))
    pop = sd[(sd["is_rookie"] == 1)
             & sd[SEASON_KEY].between(FIRST_SEASON, LAST_SEASON)
             & sd["position"].isin(POSITIONS)].copy()
    if pop.duplicated(subset=[PLAYER_KEY, SEASON_KEY]).any():
        raise BuildError("the frozen population is not unique on (player_id, season)")
    return pop.reset_index(drop=True)


def build(out=OUT, season_dataset=None, verbose=True):
    """Derive the matrix. Returns the DataFrame that was written."""
    mod = _load_production_module()
    if season_dataset is None:
        verify_inputs()                # pinned inputs only; a test may inject its own fixture instead
        verify_pff_inputs(mod)         # PRIVATE inputs, fingerprinted BEFORE any value is read

    draft_local = pd.read_parquet(DRAFT)
    combine_local = pd.read_parquet(COMBINE)

    # Inject the two nflverse loaders from repo-owned snapshots. `_load_pff` is deliberately NOT
    # patched: it reads Joseph's authorized private PFF library, which is the point of this freeze.
    mod.nfl.load_draft_picks = lambda *a, **k: draft_local
    mod.nfl.load_combine = lambda *a, **k: combine_local

    pop = _frozen_population(season_dataset)
    n_pop = len(pop)
    if verbose:
        print(f"frozen population: {n_pop} rookie player-seasons "
              f"{FIRST_SEASON}-{LAST_SEASON} {dict(pop.position.value_counts())}")

    # production's panel contract: gsis_id + round/pick. Draft capital comes from the same snapshot
    # production reads, keyed by gsis_id.
    d = (draft_local.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
         [["gsis_id", "round", "pick"]])
    # `season` is the point-in-time reference the PFF join must precede; `position` is identity
    # evidence used only to disambiguate same-name collisions. Both are REQUIRED by build_features.
    panel = (pop[[PLAYER_KEY, SEASON_KEY, "position"]].rename(columns={PLAYER_KEY: "gsis_id"})
             .merge(d, on="gsis_id", how="left"))
    if len(panel) != n_pop:
        raise BuildError(f"panel row count changed: {n_pop} -> {len(panel)}")

    feat, groups, _ = mod.build_features(panel)          # <-- REAL production function
    if len(feat) != n_pop:
        raise BuildError(f"production build_features changed the row count: {n_pop} -> {len(feat)}")

    feat = feat.rename(columns={"gsis_id": PLAYER_KEY})
    merged = pop.merge(feat.drop(columns=[c for c in feat.columns
                                          if c in pop.columns and c not in (PLAYER_KEY, SEASON_KEY)]),
                       on=[PLAYER_KEY, SEASON_KEY], how="left", validate="one_to_one")
    if len(merged) != n_pop:
        raise BuildError(f"identity join changed the row count: {n_pop} -> {len(merged)}")

    missing = [c for c in FROZEN_COLUMNS if c not in merged.columns]
    if missing:
        raise BuildError(f"production did not supply frozen column(s): {missing}")

    out_df = merged[list(FROZEN_COLUMNS)].copy()

    # --- deterministic shape ------------------------------------------------------------------
    out_df = out_df.sort_values([SEASON_KEY, PLAYER_KEY], kind="mergesort").reset_index(drop=True)
    out_df[SEASON_KEY] = out_df[SEASON_KEY].astype("int32")
    out_df["is_rookie"] = out_df["is_rookie"].astype("int8")
    for c in (PLAYER_KEY, "position", "norm_name"):
        out_df[c] = out_df[c].astype("string")
    for c in PROVENANCE_COLUMNS + UNION_FEATURE_COLUMNS:
        out_df[c] = pd.to_numeric(out_df[c], errors="coerce").astype("float64")

    _assert_contract(out_df, n_pop)
    prov = mod.pff_provenance()
    if verbose:
        print(f"PFF consumed: {prov['n_files']} files, kinds={prov['kinds']}, "
              f"seasons {prov['seasons'][0]}-{prov['seasons'][-1]}, sha256={prov['sha256']}")
    if prov["sha256"] != PFF_CONSUMED_SHA256:
        raise BuildError(f"PFF consumed-input digest drift: {prov['sha256']} != pinned "
                         f"{PFF_CONSUMED_SHA256}")
    if prov["n_files"] != PFF_CONSUMED_FILES:
        raise BuildError(f"PFF consumed {prov['n_files']} files, pinned {PFF_CONSUMED_FILES}")

    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
    if verbose:
        sha = hashlib.sha256(pathlib.Path(out).read_bytes()).hexdigest()
        print(f"wrote {out}  rows={len(out_df)} cols={len(out_df.columns)} sha256={sha}")
    return out_df


def _assert_contract(df, n_pop):
    if len(df) != n_pop:
        raise BuildError(f"row loss: {len(df)} != {n_pop}")
    if tuple(df.columns) != FROZEN_COLUMNS:
        raise BuildError("column order does not match the frozen contract")
    if df.duplicated(subset=[PLAYER_KEY, SEASON_KEY]).any():
        raise BuildError("duplicate (player_id, season) keys")
    if df[PLAYER_KEY].isna().any():
        raise BuildError("null player_id")
    seasons = sorted(int(s) for s in pd.unique(df[SEASON_KEY]))
    if seasons != list(range(FIRST_SEASON, LAST_SEASON + 1)):
        raise BuildError(f"season coverage is {seasons}")
    if not set(pd.unique(df["position"])) <= set(POSITIONS):
        raise BuildError(f"unexpected positions: {set(pd.unique(df['position']))}")
    hits = sorted({c for c in df.columns for f in FORBIDDEN_SUBSTRINGS if f in c.lower()})
    hits += sorted(c for c in df.columns if c.lower() in FORBIDDEN_EXACT)
    if hits:
        raise BuildError(f"forbidden outcome/market column(s): {sorted(set(hits))}")
    # THE POINT-IN-TIME CONTRACT, asserted on the artifact itself. Every attached PFF block must come
    # from a college season STRICTLY BEFORE the NFL rookie season. This is the defect that invalidated
    # the first matrix (2014 Mike Evans carried 2021 receiving), and it can never ship silently again.
    for sc in PROVENANCE_COLUMNS:
        late = df[sc].notna() & (df[sc] >= df[SEASON_KEY])
        if bool(late.any()):
            bad = df.loc[late, ["norm_name", SEASON_KEY, sc]].head(5).to_dict("records")
            raise BuildError(f"POINT-IN-TIME VIOLATION: {int(late.sum())} row(s) carry {sc} >= "
                             f"{SEASON_KEY}; e.g. {bad}")
    # every bundle pool must be fully present
    for pool in _bundle_pools().values():
        absent = [c for c in pool if c not in df.columns]
        if absent:
            raise BuildError(f"bundle pool not covered: {absent}")


def _bundle_pools():
    models = REPO / "fantasy" / "projections" / "models"
    import pickle
    out = {}
    for pos, fname in (("RB", "rb_rookie_model.pkl"), ("WR", "wr_rookie_model.pkl"),
                       ("TE", "te_rookie_model.pkl")):
        out[pos] = tuple(pickle.loads((models / fname).read_bytes())["feature_cols"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    build(out=args.out)
