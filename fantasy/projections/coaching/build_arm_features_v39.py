"""PHASE 2A (prereg v3.9 PREFIT) — POINT-IN-TIME COACHING REPRESENTATIONS for Arms HC and 1-5.

**NO FANTASY OUTCOME IS READ, JOINED OR FIT HERE.** This module builds team-season coaching
features only. It never opens `season_dataset_*.csv`, never touches a player row, and never writes a
production artifact. `run_coach_projection_experiment_v39.py` consumes what this emits.

=====================================================================================================
WHAT CHANGED IN v3.9 AND WHY
=====================================================================================================
1. FORBIDDEN PRIMARY FEATURES (v3.9 decision 1). No observed reliability, no raw or log history
   counts, no `no_prior_history`, no censoring field, no observable-window field may enter a primary
   player feature. `observed_reliability = g/(g+32)` is a strictly monotone bijection of the count,
   and the caller count is left-censored at 2014 while HC résumé reaches 1999, so the count carries
   the season index. Reliability survives ONLY as the deterministic shrinkage weight INSIDE a
   historical estimate. Tenure and entering-change indicators remain eligible.

   Arm 3 ridge effects receive NO second shrinkage: Stage 2 already partially pooled them by sample
   size, and multiplying a fitted coefficient by reliability afterwards shrinks twice.

2. HISTORY POLICY (v3.9b, Joseph's decision — SUPERSEDES the v3.9/v3.9a strict gate).
   The TARGET-season expected caller stays evidence-gated at the frozen preseason cutoff. Once he is
   known, his career / rolling-three history uses the FULL retrospective caller-attribution ledger,
   restricted to source seasons and games STRICTLY BEFORE Y. A past segment is NOT gated by the
   publication date of the surviving citation, because the past play-calling role was a
   contemporaneously observable fact and the citation's date only records when it can now be proved.

   Prior-season opening/closing caller identity (tenure, entering-change) follows the same rule, since
   it is historical attribution rather than target-season expectation.

   MEASURED EFFECT vs the retired strict gate, on the outer window (computed, not assumed):
       known-with-history rows   124/256 -> 124/256   ZERO change
       caller-games of history   7,274   -> 7,632     +358 (+4.9%)
       2019 (the thinnest season)                     +0 games
   All 28 outer known-no-history rows are genuine FIRST-TIME callers with no prior segment in the
   ledger at all, so the gate was never what suppressed them. The change adds history DEPTH, not rows,
   and does NOT relieve the 2019-2022 power problem.

   The retired strict rule survives as `strict_gate_sensitivity()` — in-memory, nonprimary,
   nonselectable, never a repo artifact.

3. DESIGN A vs DESIGN B IS NOW A SINGLE-AXIS CONTRAST: **target-season identity supply only**. Both
   use the identical strictly-prior retrospective history. B supplies the retrospective opening caller
   and therefore remains ORACLE and NONDEPLOYABLE; every B number carries that label.

4. NEUTRAL ENCODING, NOT NaN (frozen). An unknown caller must not be identifiable from a missingness
   pattern: Design A caller coverage is 0% in five historical seasons and ~100% in three, so a
   NaN-vs-present channel is close to a season indicator, which is exactly the calendar proxy the
   policy exists to exclude. Unknown-caller rows therefore receive the FROZEN NEUTRAL VALUE:

       rank-percentile composite            0.500
       z-score quality / scheme tendency    0.000
       Arm 3 adjusted effect                0.000
       caller tenure                        0.0    (the value a first-year caller receives)
       caller entering-change               0.5
       caller_is_head_coach                 0.5

   DISCLOSED LIMITATION: 0.5 on the two binary caller indicators IS a distinguishable third level,
   and under Design A it correlates with season. It is retained because the alternatives assert
   something false (0 asserts delegation, 1 asserts self-call) and NaN reopens the missingness
   channel on every caller feature at once. The pre-registered control is the within-season
   TEAM-LEVEL permutation placebo, which preserves each season's composition under the null.

5. ARM 3 IS STRUCTURALLY UNAVAILABLE BEFORE TARGET 2018. `arm3_stage2_effects_v38.csv` covers
   target seasons 2018-2026 only, because Stage 1 residuals begin in 2014 and the frozen Stage 2
   minimums (2 training + 2 validation seasons) make entering-2018 the earliest estimable target.
   Target seasons 2014-2017 therefore carry all-zero Arm 3 effects. Nothing is backfilled and the
   effects table is not re-estimated. Consequence, stated up front: any inner-validation fold that
   validates on 2016 or 2017 gives Arms 3 and 5 no caller/context effect information, so the
   outer-2018 fold cannot select Arm 3 on evidence.

=====================================================================================================
IDENTITY SOURCES
=====================================================================================================
  Design A (PRIMARY, deployable)   `preseason_staff_snapshot.csv`, `expected_opening_caller_id` where
                                   `eligible_at_cutoff`; otherwise UNKNOWN -> neutral. No continuity
                                   imputation. Outer 2018-2025 caller coverage 152/256.
  Design B (ORACLE, NONDEPLOYABLE) `retrospective_staff_transitions.csv`, `opening_caller_id`.
  Design C                         NOT AUTHORIZED. No code path exists here.

Head-coach identity is taken as publicly knowable at the cutoff in both designs, which is the
standing prereg position (`PROPOSED_DESIGNS_A_B_C.md`: expected HC identity is 100% point-in-time
covered). It is derived from the week-1 head coach, NOT from evidence-gated research, so it is an
ASSUMPTION rather than an evidence-verified quantity, and it is recorded as such.

Run:  python build_arm_features_v39.py --build
"""
import argparse
import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

import build_exposure as BE
import build_reliability as BR
import date_provenance as DP
import drive_definitions as DD
import playcaller_sources as SRC

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

# =====================================================================================================
# HERMETIC INPUTS — no network, no external cache
# =====================================================================================================
# The repository-owned FROZEN schedule snapshot is the single deterministic source for historical
# regular-season schedules, scores, coaches and season-opening dates.
#
# It replaces two live `nflreadpy.load_schedules()` calls (one in
# `build_preseason_snapshot.projection_cutoffs`, one in the previous `hc_game_results`). Those made a
# clean checkout fail five tests and made the 254-pass result depend on mutable external state that is
# not in the repo. Provenance is recorded in `snapshots/manifest.json`:
# loader `load_schedules`, nflreadpy 0.1.5, 7,276 rows x 46 cols, fetched 2026-07-10T01:17:13Z,
# sha256 78ff21f9...
#
# The snapshot ends at 2025, which is exactly right: it supplies PLAYED games (results) and
# season-opening dates for 1999-2025, while season 2026 uses the frozen production as-of date and has
# no played games to score.
SCHEDULE_SNAPSHOT = (HERE.parent.parent / "seasonal_projections" / "snapshots"
                     / "schedules_1999_2025.parquet")
SNAPSHOT_LAST_SEASON = 2025
# Live 2026 deployment: projections were produced 2026-07-21, well before Week 1. Frozen in v3.4.
DEPLOY_CUTOFF = {2026: "2026-07-21"}

TARGET_SEASONS = list(range(2014, 2027))
OUTER_SEASONS = list(range(2018, 2026))
K_SHRINK = BR.K_SHRINK                       # 32, frozen
ROLL_WINDOW = 3                              # frozen
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}

# The inherited v3.8 / preliminary artifacts this pass must never alter. Re-checked at verdict time
# by the harness so condition (10) covers artifact integrity, not just timing.
UPSTREAM_PROTECTED = {
    "actual_play_caller.csv": "98f1c66b7387c16bba6a5463f4e0fa06",
    "arm3_stage1_residuals_v38.csv": "f4ac3bee6ae208bb1aca6bdedadc9224",
    "arm3_stage1_tuning_v38.csv": "65720dca75a0c6a5b2b1e732f0a86e57",
    "arm3_stage1_fold_losses_v38.csv": "bc57b3e4d17e6d5bdbfdaa3dc8237c43",
    "arm3_stage1_feature_schemas_v38.json": "d0a5f34af073a2a330f13c4c8d002555",
    "arm3_stage2_effects_v38.csv": "4286cbd542854e23a6042bcec1b4b8ed",
    "arm3_stage2_tuning_v38.csv": "28873246729b558593a29956b3a14de1",
    "arm3_stage2_fold_losses_v38.csv": "3c73e25c1bf4fc592ab3b2d5211a44c5",
    "arm3_residuals.csv": "2ba6c51769f8dbb85c27c603b2dc93f2",
    "arm3_effects.csv": "56b47dab2c0e27689ee260deb9e29c4b",
}

# =====================================================================================================
# PRIMARY HISTORICAL-HISTORY POLICY (v3.9b — Joseph's decision, 2026-07-29)
# =====================================================================================================
# The TARGET-season expected caller stays evidence-gated at the frozen preseason cutoff. Once that
# person is known, his career / rolling-three performance history uses the FULL retrospective
# caller-attribution ledger, restricted to source seasons and games STRICTLY BEFORE target season Y.
# A past segment is NOT gated by the publication date of the surviving citation.
#
# Rationale: the past play-calling role was a contemporaneously observable historical fact. The
# surviving citation's publication date is evidence of when *I* can prove it, not of when it became
# knowable. The RETIRED gate had also made Design A vs Design B a two-axis contrast; the primary
# policy restores the single axis.
#
# MEASURED EFFECT ON THE OUTER WINDOW (computed, not assumed — see the stop report):
#   known-with-history rows  124/256 -> 124/256   (ZERO change)
#   caller-games of history  7,274   -> 7,632     (+358, +4.9%)
#   2019, the thinnest season                     (+0 games)
# All 28 outer known-no-history rows are genuine first-time callers with NO prior segment in the
# ledger at all, so the gate was never what suppressed them. The change adds history DEPTH, not rows,
# and does NOT relieve the 2019-2022 power problem.
PRIMARY_HISTORY_SOURCE_DATE_GATED = False

# The one wording used for every caller-history and caller-continuity lineage row. Pinned so a future
# edit cannot reintroduce a source-date claim into the generated artifact without failing a test AND
# the runtime preflight.
PRIMARY_TIMING_RULE = ("source seasons < Y from the FULL retrospective caller-attribution ledger; "
                       "NOT gated by the attributing source's publication date")
# Features that compare two TARGET-season identities and aggregate no history.
TARGET_SEASON_ONLY_RULE = "target-season identities only"
# RETIRED wording that may never again appear as a PRIMARY timing rule or note. These strings are the`r`n# BANNED list itself; each is superseded by PRIMARY_TIMING_RULE above.
RETIRED_HISTORY_GATE_PHRASES = (
    "source upper bound <= Y cutoff",                      # RETIRED v3.9b
    "Design A additionally requires source upper bound",   # RETIRED v3.9b
    "openers are themselves gated",                        # RETIRED v3.9b
)

DESIGN_A, DESIGN_B = "design_a", "design_b_oracle"
DESIGN_LABEL = {
    DESIGN_A: "POINT-IN-TIME (pre-cutoff evidence only) — primary, deployable",
    DESIGN_B: ("ORACLE IDENTITY — uses information unavailable at the projection cutoff. "
               "NOT achievable in deployment. NOT evidence of real preseason performance."),
}

# ---------------------------------------------------------------- frozen neutral values
PRIOR_RANKPCT = 0.500
PRIOR_Z = 0.000
PRIOR_WINPCT = 0.500
NEUTRAL_EFFECT = 0.000
NEUTRAL_TENURE = 0.0
NEUTRAL_CHANGED = 0.5
NEUTRAL_IS_HC = 0.5


# =====================================================================================================
# FEATURE DEFINITIONS — one place, so the manifest, the lineage artifact and the code cannot drift.
# =====================================================================================================
# caller quality / scheme aggregates: stem -> (segment_offense column, league prior)
# ARM 1: the >=3-of-5 rank-percentile composite (drive-scoring points/game proxy, yards/play,
# EPA/play, success rate, drive-scoring points/drive proxy) is already assembled upstream as
# `off_rank_composite`, which returns NaN when fewer than three components are available.
RANK_STEMS = {"off_rank_pct": ("off_rank_composite", PRIOR_RANKPCT)}
# ARM 2: continuous offensive-effectiveness z-scores, kept as separate dimensions (no composite).
EFFICIENCY_STEMS = {
    "epa_play_z": ("z_epa_play", PRIOR_Z),
    "success_rate_z": ("z_success_rate", PRIOR_Z),
    "drive_scoring_points_per_drive_proxy_z": ("z_drive_scoring_points_per_drive_proxy", PRIOR_Z),
    "yards_play_z": ("z_yards_play", PRIOR_Z),
    "explosive_rate_z": ("z_explosive_rate", PRIOR_Z),
    "redzone_td_rate_z": ("z_redzone_td_rate", PRIOR_Z),
}
# ARM 4: scheme and positional-allocation tendencies.
SCHEME_STEMS = {
    "plays_per_game_z": ("z_plays_per_game", PRIOR_Z),
    "pass_tendency_z": ("z_neutral_pass_rate", PRIOR_Z),
    "pace_z": ("z_seconds_per_play", PRIOR_Z),
    "redzone_pass_rate_z": ("z_redzone_pass_rate", PRIOR_Z),
    "qb_carry_share_z": ("z_qb_carry_share", PRIOR_Z),
    "rb_carry_share_z": ("z_rb_carry_share", PRIOR_Z),
    "rb_target_share_z": ("z_rb_target_share", PRIOR_Z),
    "rz_rb_share_z": ("z_rz_rb_share", PRIOR_Z),
    "wr_target_share_z": ("z_wr_target_share", PRIOR_Z),
    "team_adot_z": ("z_team_adot", PRIOR_Z),
    "rz_wr_share_z": ("z_rz_wr_share", PRIOR_Z),
    "te_target_share_z": ("z_te_target_share", PRIOR_Z),
    "rz_te_share_z": ("z_rz_te_share", PRIOR_Z),
}
SEG_METRICS = {**RANK_STEMS, **EFFICIENCY_STEMS, **SCHEME_STEMS}
STEM_ARMS = ({s: ["ARM_1"] for s in RANK_STEMS}
             | {s: ["ARM_2"] for s in EFFICIENCY_STEMS}
             | {s: ["ARM_4", "ARM_5"] for s in SCHEME_STEMS})
STEM_BLOCK = ({s: "caller_rank_quality" for s in RANK_STEMS}
              | {s: "caller_efficiency" for s in EFFICIENCY_STEMS}
              | {s: "caller_scheme" for s in SCHEME_STEMS})
# `rush_tendency_z` is the EXACT negation of `pass_tendency_z`: within a source season,
# z(1 - neutral_pass_rate) = -z(neutral_pass_rate), and shrinking toward 0 commutes with negation.
# It is emitted so the RB block reads in rushing terms; the identity is asserted by test.
DERIVED_NEGATION = {"rush_tendency_z": "pass_tendency_z"}

WINDOWS = ["career", "roll3"]

ARM_HC_FEATURES = [
    "hc_career_win_pct_shrunk",
    "hc_roll3_win_pct_shrunk",
    "hc_tenure_current_team",
    "hc_changed_entering",
]

CALLER_CONTINUITY = ["pc_tenure_current_team", "pc_changed_entering", "caller_is_head_coach"]
HC_CONTINUITY = ["hc_tenure_current_team", "hc_changed_entering"]

ARM1_CALLER = ["pc_career_off_rank_pct", "pc_roll3_off_rank_pct"] + CALLER_CONTINUITY
ARM1_FEATURES = ARM_HC_FEATURES + ARM1_CALLER

ARM2_QUALITY = [f"pc_{w}_{s}" for s in EFFICIENCY_STEMS for w in WINDOWS]
ARM2_FEATURES = ARM2_QUALITY + CALLER_CONTINUITY

ARM3_FEATURES = ["caller_adjusted_offense_effect", "noncalling_hc_context_effect",
                 "caller_is_head_coach"]

ARM4_STEMS = {
    "QB": ["plays_per_game_z", "pass_tendency_z", "pace_z", "redzone_pass_rate_z",
           "qb_carry_share_z"],
    "RB": ["plays_per_game_z", "rush_tendency_z", "rb_carry_share_z", "rb_target_share_z",
           "rz_rb_share_z"],
    "WR": ["plays_per_game_z", "pass_tendency_z", "wr_target_share_z", "team_adot_z",
           "rz_wr_share_z"],
    "TE": ["plays_per_game_z", "pass_tendency_z", "te_target_share_z", "rz_te_share_z"],
}
POSITIONS = ["QB", "RB", "WR", "TE"]


def arm4_features(position):
    return [f"pc_{w}_{s}" for s in ARM4_STEMS[position] for w in WINDOWS]


def arm5_features(position):
    """Staff continuity/tenure + Arm 3 effects + position-specific Arm 4.

    EXCLUDES Arm 1 win-pct/rank features, Arm 2 raw efficiency z-scores, and every sample-size or
    censoring field -- by construction, asserted by test.
    """
    return (HC_CONTINUITY + CALLER_CONTINUITY
            + ["caller_adjusted_offense_effect", "noncalling_hc_context_effect"]
            + arm4_features(position))


def arm_features(arm, position):
    if arm == "ARM_0":
        return []
    if arm == "ARM_HC":
        return list(ARM_HC_FEATURES)
    if arm == "ARM_1":
        return list(ARM1_FEATURES)
    if arm == "ARM_2":
        return list(ARM2_FEATURES)
    if arm == "ARM_3":
        return list(ARM3_FEATURES)
    if arm == "ARM_4":
        return arm4_features(position)
    if arm == "ARM_5":
        return arm5_features(position)
    raise ValueError(arm)


ARMS = ["ARM_0", "ARM_HC", "ARM_1", "ARM_2", "ARM_3", "ARM_4", "ARM_5"]
COACHING_ARMS = [a for a in ARMS if a != "ARM_0"]

# Every column the two feature CSVs carry, in a frozen order.
ALL_FEATURE_COLUMNS = list(dict.fromkeys(
    ARM_HC_FEATURES
    + [f"pc_{w}_{s}" for s in RANK_STEMS for w in WINDOWS]
    + ARM2_QUALITY
    + [f"pc_{w}_{s}" for s in list(SCHEME_STEMS) + list(DERIVED_NEGATION) for w in WINDOWS]
    + ["caller_adjusted_offense_effect", "noncalling_hc_context_effect"]
    + CALLER_CONTINUITY))

# Diagnostic columns that ride along in the CSV but may NEVER enter a model. Enforced by
# `assert_no_forbidden_features` and by the manifest, which lists model columns only.
DIAGNOSTIC_COLUMNS = [
    "expected_caller_id", "expected_hc_id", "caller_identity_known",
    "caller_history_games_career", "caller_history_games_roll3", "hc_resume_games_career",
    "caller_history_segments_career", "caller_first_source_season", "caller_last_source_season",
    "arm3_effects_available",
]
FORBIDDEN_SUBSTRINGS = ("reliability", "prior_games", "games_log", "no_prior_history",
                        "left_censored", "observable_prior", "history_start", "n_observed",
                        "observed_exposure", "hc_resume", "unknown_caller_hc_games")


# canonical proxy names, longest first, so removing them cannot leave a partial match behind
_CANONICAL_DRIVE_NAMES = sorted(
    {DD.PRIOR_PPD_PROXY, DD.PPD_PROXY, DD.PPG_PROXY}, key=len, reverse=True)


def _strip_canonical_drive_names(text):
    """Remove the CANONICAL proxy names before scanning for retired ones.

    `drive_scoring_points_per_drive_proxy` legitimately CONTAINS the retired token
    `points_per_drive`, so a naive substring scan rejects the correct name. Retired names are
    detected only in what remains after the canonical names are removed.
    """
    for name in _CANONICAL_DRIVE_NAMES:
        text = text.replace(name, "")
    return text


def assert_no_retired_drive_names(strings, where):
    bad = [s for s in strings
           if any(r in _strip_canonical_drive_names(s) for r in DD.RETIRED_NAMES)]
    assert not bad, f"{where}: retired drive-metric names -> {bad}"
    return True


def assert_no_forbidden_features(columns, where):
    bad = [c for c in columns
           if any(s in c for s in FORBIDDEN_SUBSTRINGS) or c in BR.FORBIDDEN_IN_X]
    assert not bad, f"{where}: forbidden metadata in primary features -> {bad}"
    assert_no_retired_drive_names(columns, where)
    return True


# =====================================================================================================
# INPUTS
# =====================================================================================================
def _canon(s):
    return pd.Series(s, dtype="object").replace(TEAM_CANON)


def source_upper_bounds():
    """source_url -> conservative UPPER bound of the attributing source's date (or None).

    Joined by URL because the canonical table carries `source_url`, not `source_key`. Missing and
    inferred precisions yield None and are therefore NEVER eligible.
    """
    out = {}
    for key, meta in {**SRC.SOURCES, **SRC.PARTIAL_SOURCES}.items():
        prov = DP.classify(key, meta.get("date"))
        _lo, hi = DP.bounds(prov["source_date"], prov["source_date_precision"])
        out[meta.get("url")] = hi
    return out


def eligible_at(upper, cutoff):
    """DP.eligible_at with an explicit NaN guard.

    `DP.eligible_at` tests `if not upper_bound`, and float('nan') is TRUTHY, so a NaN upper bound
    reaches `date.fromisoformat('nan')` and raises. A pandas column of source dates always contains
    NaN, so the guard belongs here rather than at every call site.
    """
    if upper is None or (isinstance(upper, float) and np.isnan(upper)) or pd.isna(upper):
        return False
    return DP.eligible_at(upper, cutoff)


def _none(v):
    """NaN/NA -> None. A dict carrying None becomes NaN the moment it enters a DataFrame, and
    `float('nan') is not None` is True, so an unknown identity silently tested as KNOWN: it then
    reached `float(cal != prev_caller)` (giving 1.0 instead of the neutral 0.5) and let a distinct
    head coach collect an Arm 3 context effect on a row with no caller evidence at all. Every
    identity read out of a frame passes through here."""
    return None if (v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v)) else v


def _gate_mask(frame, cutoff):
    """Boolean mask of segments whose attributing source clears `cutoff`.

    Returned as a numpy bool array and applied with `.loc`, because `df[[]]` selects zero COLUMNS
    rather than zero rows -- which silently produced an empty-column frame for the first target
    season, where no prior segment exists.
    """
    return np.array([eligible_at(u, cutoff) for u in frame["source_upper_bound"]], dtype=bool)


def snapshot_schedules(_memo={}):
    """The FROZEN repo-owned schedule snapshot, REG only. No network, no external cache.

    Memoised per process only — nothing is written to disk, so a clean checkout with an empty temp
    directory and no connectivity reproduces the build exactly.
    """
    if "reg" not in _memo:
        assert SCHEDULE_SNAPSHOT.exists(), (
            f"missing the frozen schedule snapshot {SCHEDULE_SNAPSHOT}. v3.9 is hermetic by design "
            f"and will NOT fall back to a network fetch.")
        s = pd.read_parquet(SCHEDULE_SNAPSHOT)
        s = s[s["game_type"] == "REG"].copy()
        s["gameday"] = pd.to_datetime(s["gameday"], errors="coerce")
        _memo["reg"] = s
    return _memo["reg"]


def projection_cutoffs(_memo={}):
    """Day before season Y's first REG game, from the frozen snapshot; 2026 = production as-of date.

    Cross-checked against the `projection_cutoff` column already persisted in
    `preseason_staff_snapshot.csv` by its owning builder, so the hermetic derivation cannot silently
    disagree with the artifact the eligibility gate was actually built with.
    """
    if not _memo:
        s = snapshot_schedules()
        first = s.groupby("season")["gameday"].min()
        cut = {int(k): (v - pd.Timedelta(days=1)).date().isoformat()
               for k, v in first.items() if pd.notna(v)}
        cut.update(DEPLOY_CUTOFF)
        snap_path = DATA / "preseason_staff_snapshot.csv"
        if snap_path.exists():
            persisted = (pd.read_csv(snap_path)[["season", "projection_cutoff"]]
                         .drop_duplicates().dropna())
            bad = [(int(r.season), r.projection_cutoff, cut.get(int(r.season)))
                   for r in persisted.itertuples()
                   if cut.get(int(r.season)) != r.projection_cutoff]
            assert not bad, (
                "snapshot-derived projection cutoffs disagree with the persisted ones "
                f"(season, persisted, derived): {bad}")
        _memo.update(cut)
    return _memo


def hc_game_results():
    """Per (season, team, game_id) head-coach win credit, built from the frozen snapshot.

    REG only; a TIE counts **0.5** and stays in the denominator; playoff games never enter. A game
    without a recorded `result` is DROPPED rather than scored 0 (the snapshot contains no such REG
    row, and the unplayed 2026 season is simply absent from it).

    Computed in memory. It is neither a repo artifact nor a disk cache, so nothing outside the
    checkout can change the answer.
    """
    s = snapshot_schedules()
    s = s.assign(result=pd.to_numeric(s["result"], errors="coerce")).dropna(subset=["result"])
    home = pd.DataFrame(dict(season=s["season"], week=s["week"], game_id=s["game_id"],
                             team=_canon(s["home_team"].values), head_coach=s["home_coach"],
                             margin=s["result"]))
    away = pd.DataFrame(dict(season=s["season"], week=s["week"], game_id=s["game_id"],
                             team=_canon(s["away_team"].values), head_coach=s["away_coach"],
                             margin=-s["result"]))
    g = pd.concat([home, away], ignore_index=True).dropna(subset=["head_coach"])
    g["hc_person_id"] = g["head_coach"].map(BE._pid)
    g["win"] = np.where(g.margin > 0, 1.0, np.where(g.margin < 0, 0.0, 0.5))
    g = g.sort_values(["season", "week", "team"], kind="mergesort").reset_index(drop=True)
    return g[["season", "week", "team", "game_id", "head_coach", "hc_person_id", "margin", "win"]]


def caller_segments():
    """`segment_offense.csv` + the attributing source's conservative upper bound per segment."""
    seg = pd.read_csv(DATA / "segment_offense.csv")
    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    tbl = tbl[tbl.person_id.notna()].copy()
    tbl["week_start"] = pd.to_numeric(tbl["week_start"], errors="coerce").fillna(1).astype(int)
    tbl["week_end"] = pd.to_numeric(tbl["week_end"], errors="coerce").fillna(99).astype(int)
    ub = source_upper_bounds()
    tbl["source_upper_bound"] = [ub.get(u) for u in tbl.source_url]
    key = ["season", "team", "person_id", "week_start", "week_end"]
    n0 = len(seg)
    seg = seg.merge(tbl[key + ["source_upper_bound", "n_games_attributed"]], on=key, how="left")
    assert len(seg) == n0, "segment/ledger join changed the row count"
    played = seg[seg.pbp_games > 0]
    assert (played.pbp_games == played.n_games_attributed).all(), (
        "pbp_games disagrees with the canonical n_games_attributed on a played segment")
    return seg


def game_identity():
    gl = pd.read_csv(DATA / "game_level_identity.csv")
    gl["week"] = pd.to_numeric(gl["week"], errors="coerce")
    return gl.sort_values(["season", "team", "week"])


def hc_openers_closers(gl):
    """Week-1 and final-week head coach per (season, team)."""
    f = gl.groupby(["season", "team"], as_index=False).first()[["season", "team", "hc_person_id"]]
    l = gl.groupby(["season", "team"], as_index=False).last()[["season", "team", "hc_person_id"]]
    f = f.rename(columns={"hc_person_id": "hc_opener"})
    l = l.rename(columns={"hc_person_id": "hc_closer"})
    out = f.merge(l, on=["season", "team"])
    out["hc_opener"] = [_none(v) for v in out.hc_opener]
    out["hc_closer"] = [_none(v) for v in out.hc_closer]
    return out


# =====================================================================================================
# CALLER IDENTITY, AS OF A CUTOFF
# =====================================================================================================
def caller_openers_closers(seg, cutoff=None):
    """Opening / closing caller per (season, team) from the segment ledger.

    When `cutoff` is given (Design A), only segments whose attributing source clears that cutoff are
    admitted, so the opener/closer are what the archive could prove at that moment. When it is None
    (Design B oracle) every resolved segment is admitted.
    """
    s = seg[seg.person_id.notna()].copy()
    if cutoff is not None:
        s = s.loc[_gate_mask(s, cutoff)]
    if not len(s):
        return pd.DataFrame(columns=["season", "team", "caller_opener", "caller_closer"])
    s = s.sort_values(["season", "team", "week_start"])
    f = s.groupby(["season", "team"], as_index=False).first()[["season", "team", "person_id"]]
    l = s.groupby(["season", "team"], as_index=False).last()[["season", "team", "person_id"]]
    return (f.rename(columns={"person_id": "caller_opener"})
             .merge(l.rename(columns={"person_id": "caller_closer"}), on=["season", "team"]))


def target_identities(design, seg, gl):
    """Per (season in TARGET_SEASONS, team): expected caller + expected HC for that target season."""
    if design not in (DESIGN_A, DESIGN_B):
        raise ValueError(f"unsupported design {design!r} — Design C is NOT AUTHORIZED")
    hco = hc_openers_closers(gl)
    rows = []
    if design == DESIGN_A:
        snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
        forbidden = {"retrospective_opening_caller_id", "expectation_matched_actual",
                     "closing_caller_id", "historical_primary_caller_id"}
        leak = forbidden & set(snap.columns)
        assert not leak, f"Design A read a forbidden retrospective column: {sorted(leak)}"
        snap = snap[snap.season.isin(TARGET_SEASONS)]
        for r in snap.itertuples():
            cal = r.expected_opening_caller_id if (
                bool(r.eligible_at_cutoff) and pd.notna(r.expected_opening_caller_id)) else None
            rows.append(dict(season=int(r.season), team=r.team, expected_caller_id=cal,
                             expected_hc_id=(r.expected_opening_hc_id
                                             if pd.notna(r.expected_opening_hc_id) else None)))
    elif design == DESIGN_B:
        retro = pd.read_csv(DATA / "retrospective_staff_transitions.csv")
        retro = retro[retro.season.isin(TARGET_SEASONS)]
        for r in retro.itertuples():
            rows.append(dict(season=int(r.season), team=r.team,
                             expected_caller_id=(r.opening_caller_id
                                                 if pd.notna(r.opening_caller_id) else None),
                             expected_hc_id=(r.opening_hc_id
                                             if pd.notna(r.opening_hc_id) else None)))
    out = pd.DataFrame(rows)
    out = out.merge(hco[["season", "team", "hc_opener"]], on=["season", "team"], how="left")
    # HC identity is the week-1 head coach in both designs (see module docstring).
    out["expected_hc_id"] = out["expected_hc_id"].fillna(out["hc_opener"])
    out = out.drop(columns=["hc_opener"])
    for c in ("expected_caller_id", "expected_hc_id"):
        out[c] = out[c].astype("object").where(out[c].notna(), None)
    return out.sort_values(["season", "team"]).reset_index(drop=True)


# =====================================================================================================
# AGGREGATION PRIMITIVES
# =====================================================================================================
def _shrink(value, games, prior):
    """FROZEN: reliability = g/(g+32); shrunk = r*value + (1-r)*prior. Zero games -> exactly prior.

    Reliability is used HERE and only here, as the deterministic weight inside a historical estimate.
    It is never emitted as a feature and never applied twice.
    """
    if games is None or games <= 0 or value is None or (isinstance(value, float) and np.isnan(value)):
        return float(prior)
    r = games / (games + K_SHRINK)
    return float(r * value + (1.0 - r) * prior)


def _window_aggregate(frame, window):
    """Games-weighted, shrunk per-person values for one window. Vectorized, no per-person loop.

    Per-metric games are counted ONLY where that metric is non-null, so a segment missing one
    measurement (pre-2006 `proe`/`team_adot`, or a composite with fewer than three rank components)
    does not inflate confidence in it. A metric with zero supporting games collapses to exactly its
    league prior.
    """
    g = pd.to_numeric(frame["pbp_games"], errors="coerce").fillna(0.0)
    acc = pd.DataFrame({"person_id": frame["person_id"].values})
    for stem, (col, _prior) in SEG_METRICS.items():
        m = pd.to_numeric(frame[col], errors="coerce")
        ok = (m.notna() & (g > 0)).values
        acc[f"num__{stem}"] = np.where(ok, m.values * g.values, 0.0)
        acc[f"den__{stem}"] = np.where(ok, g.values, 0.0)
    acc["games"] = g.values
    tot = acc.groupby("person_id", sort=True).sum()

    out = pd.DataFrame(index=tot.index)
    for stem, (_col, prior) in SEG_METRICS.items():
        den = tot[f"den__{stem}"].astype(float)
        val = np.where(den > 0, tot[f"num__{stem}"].astype(float) / den.replace(0, np.nan), np.nan)
        r = den / (den + K_SHRINK)
        out[f"{window}_{stem}"] = np.where(den > 0, r * val + (1.0 - r) * prior, float(prior))
    for stem, src in DERIVED_NEGATION.items():
        out[f"{window}_{stem}"] = -out[f"{window}_{src}"]
    out[f"{window}_games"] = tot["games"].astype(float)
    return out


def caller_history(seg, target_season, cutoff, gated):
    """person_id -> {window_stem: shrunk value} from segments STRICTLY BEFORE target_season.

    Weight is `pbp_games` (games actually observed in play-by-play inside the sourced week range);
    on every played segment it equals the canonical `n_games_attributed`, asserted at load.

    Design A additionally requires the attributing source's conservative UPPER BOUND to clear season
    `target_season`'s frozen projection cutoff, so a later article can never build an earlier feature.
    """
    s = seg[(seg.season < target_season) & seg.person_id.notna()].copy()
    if gated:
        s = s.loc[_gate_mask(s, cutoff)]
    s = s[pd.to_numeric(s["pbp_games"], errors="coerce").fillna(0) > 0]
    if not len(s):
        return {}, {}
    car = _window_aggregate(s, "career")
    r3 = _window_aggregate(s[s.season >= target_season - ROLL_WINDOW], "roll3")
    r3 = r3.reindex(car.index)
    for stem, (_col, prior) in SEG_METRICS.items():
        r3[f"roll3_{stem}"] = r3[f"roll3_{stem}"].fillna(float(prior))
    for stem in DERIVED_NEGATION:
        r3[f"roll3_{stem}"] = r3[f"roll3_{stem}"].fillna(PRIOR_Z)
    r3["roll3_games"] = r3["roll3_games"].fillna(0.0)
    joined = car.join(r3)

    n_seg = s.groupby("person_id").size()
    lo = s.groupby("person_id")["season"].min()
    hi = s.groupby("person_id")["season"].max()
    hist = {pid: {k: float(v) for k, v in rec.items() if not k.endswith("_games")}
            for pid, rec in joined.to_dict("index").items()}
    support = {pid: dict(career_games=float(joined.at[pid, "career_games"]),
                         roll3_games=float(joined.at[pid, "roll3_games"]),
                         career_segments=int(n_seg.get(pid, 0)),
                         first_source_season=int(lo[pid]), last_source_season=int(hi[pid]))
               for pid in joined.index}
    # STRICT TIMING, asserted rather than assumed: no source season may reach the target season.
    bad = {p: v["last_source_season"] for p, v in support.items()
           if v["last_source_season"] >= target_season}
    assert not bad, f"caller history for target {target_season} used season >= Y: {bad}"
    return hist, support


def hc_history(res, target_season):
    """person_id -> (career shrunk win pct, roll3 shrunk win pct, career REG games).

    Regular season only, no playoffs, ties 0.5. Full point-in-time coverage: schedules and results
    are public the moment each game ends.
    """
    prior = res[res.season < target_season]
    roll = prior[prior.season >= target_season - ROLL_WINDOW]
    out = {}
    ca = prior.groupby("hc_person_id")["win"].agg(["sum", "size"])
    ro = roll.groupby("hc_person_id")["win"].agg(["sum", "size"])
    for pid in ca.index:
        cg = float(ca.loc[pid, "size"])
        cw = float(ca.loc[pid, "sum"]) / cg if cg else np.nan
        if pid in ro.index and ro.loc[pid, "size"] > 0:
            rg = float(ro.loc[pid, "size"])
            rw = float(ro.loc[pid, "sum"]) / rg
        else:
            rg, rw = 0.0, np.nan
        out[pid] = (_shrink(cw, cg, PRIOR_WINPCT), _shrink(rw, rg, PRIOR_WINPCT), cg)
    return out


def tenure(openers, target_season, team, person):
    """Consecutive completed seasons immediately before `target_season` in which `person` opened for
    `team`. A first-year appointment scores 0. Franchise relocations are already folded onto one team
    code upstream (STL->LA, SD->LAC, OAK->LV), so tenure bridges a move instead of resetting."""
    if person is None:
        return NEUTRAL_TENURE
    n = 0
    while True:
        s = target_season - 1 - n
        v = openers.get((s, team))
        if v is None or v != person:
            break
        n += 1
    return float(n)


def arm3_lookup(effects, target_season):
    cal = effects[(effects.target_season == target_season) & (effects.role == BR.ROLE_CALLER)]
    ctx = effects[(effects.target_season == target_season) & (effects.role == BR.ROLE_HC_CTX)]
    return (dict(zip(cal.person_id, cal.effect)), dict(zip(ctx.person_id, ctx.effect)))


def route_arm3(caller, hc, cal_eff, ctx_eff):
    """FROZEN Arm 3 routing. Returns (caller effect, non-calling-HC context effect).

      unknown caller             -> (0, 0). We assume NEITHER delegation NOR self-calling, so no
                                    identity block activates. This is the v3.6 neutral rule.
      self-calling head coach    -> (caller effect, 0). HC and caller are not separately
                                    identifiable on such a game, so the whole contribution sits in
                                    the portable caller block and the effect appears exactly ONCE.
      distinct known caller      -> (caller effect, HC context effect).
      identity absent from the
      effect table               -> that block's contribution is the zero league prior.
    """
    if caller is None:
        return NEUTRAL_EFFECT, NEUTRAL_EFFECT
    pc = float(cal_eff.get(caller, NEUTRAL_EFFECT))
    if hc is None or caller == hc:
        return pc, NEUTRAL_EFFECT
    return pc, float(ctx_eff.get(hc, NEUTRAL_EFFECT))


# =====================================================================================================
# BUILD
# =====================================================================================================
def build_features(design, seg=None, gl=None, res=None, effects=None, verbose=True,
                   ident=None, cutoffs=None, target_seasons=None,
                   history_source_date_gated=None):
    """Team-season coaching features for one identity design.

    `ident`, `cutoffs` and `target_seasons` exist so a SYNTHETIC test can drive this exact function
    -- the one the real build calls -- instead of a parallel re-implementation. When they are None
    the real artifacts and the frozen cutoffs are used.

    `history_source_date_gated` defaults to the PRIMARY policy
    (`PRIMARY_HISTORY_SOURCE_DATE_GATED = False`, v3.9b). Passing True reproduces the retired strict
    variant for the labelled in-memory diagnostic sensitivity ONLY -- it is never a repo artifact and
    can never enter selection.
    """
    seg = caller_segments() if seg is None else seg
    gl = game_identity() if gl is None else gl
    res = hc_game_results() if res is None else res
    effects = (pd.read_csv(DATA / "arm3_stage2_effects_v38.csv") if effects is None else effects)
    target_seasons = TARGET_SEASONS if target_seasons is None else list(target_seasons)

    gated = (PRIMARY_HISTORY_SOURCE_DATE_GATED if history_source_date_gated is None
             else bool(history_source_date_gated))
    cutoffs = projection_cutoffs() if cutoffs is None else {int(k): v for k, v in cutoffs.items()}
    ident = target_identities(design, seg, gl) if ident is None else ident
    hco = hc_openers_closers(gl)
    hc_open = {(int(r.season), r.team): r.hc_opener for r in hco.itertuples()}
    hc_close = {(int(r.season), r.team): r.hc_closer for r in hco.itertuples()}
    effect_targets = set(effects.target_season.unique())

    rows = []
    for Y in target_seasons:
        cutoff = cutoffs.get(Y)
        hist, support = caller_history(seg, Y, cutoff, gated)
        hcw = hc_history(res, Y)
        cal_eff, ctx_eff = arm3_lookup(effects, Y)
        # Prior-season opening/closing caller identity is HISTORICAL ATTRIBUTION, so under the primary
        # policy it uses the same ungated strictly-prior ledger as performance history. That is what
        # makes Design A vs Design B a SINGLE-AXIS contrast: target-season identity supply only.
        co = caller_openers_closers(seg, cutoff if gated else None)
        cal_open = {(int(r.season), r.team): r.caller_opener for r in co.itertuples()}
        cal_close = {(int(r.season), r.team): r.caller_closer for r in co.itertuples()}

        for r in ident[ident.season == Y].itertuples():
            team = r.team
            cal, hc = _none(r.expected_caller_id), _none(r.expected_hc_id)
            known = cal is not None
            row = dict(season=Y, team=team, design=design,
                       expected_caller_id=cal, expected_hc_id=hc,
                       caller_identity_known=int(known),
                       arm3_effects_available=int(Y in effect_targets))

            # ---- ARM HC (full point-in-time coverage) ----
            cw, rw, cg = hcw.get(hc, (PRIOR_WINPCT, PRIOR_WINPCT, 0.0))
            row["hc_career_win_pct_shrunk"] = cw
            row["hc_roll3_win_pct_shrunk"] = rw
            row["hc_resume_games_career"] = cg
            row["hc_tenure_current_team"] = tenure(hc_open, Y, team, hc)
            prev_hc = _none(hc_close.get((Y - 1, team)))
            row["hc_changed_entering"] = (
                np.nan if (hc is None or prev_hc is None) else float(hc != prev_hc))

            # ---- caller history (neutral where identity is unknown) ----
            h = hist.get(cal) if known else None
            for w in WINDOWS:
                for stem, (_col, prior) in SEG_METRICS.items():
                    row[f"pc_{w}_{stem}"] = h[f"{w}_{stem}"] if h else float(prior)
                for stem in DERIVED_NEGATION:
                    row[f"pc_{w}_{stem}"] = h[f"{w}_{stem}"] if h else PRIOR_Z
            sup = support.get(cal, {}) if known else {}
            row["caller_history_games_career"] = float(sup.get("career_games", 0.0))
            row["caller_history_games_roll3"] = float(sup.get("roll3_games", 0.0))
            row["caller_history_segments_career"] = int(sup.get("career_segments", 0))
            row["caller_first_source_season"] = sup.get("first_source_season")
            row["caller_last_source_season"] = sup.get("last_source_season")

            # ---- caller continuity ----
            row["pc_tenure_current_team"] = (
                tenure(cal_open, Y, team, cal) if known else NEUTRAL_TENURE)
            prev_cal = _none(cal_close.get((Y - 1, team)))
            row["pc_changed_entering"] = (
                NEUTRAL_CHANGED if (not known or prev_cal is None) else float(cal != prev_cal))
            row["caller_is_head_coach"] = (
                NEUTRAL_IS_HC if (not known or hc is None) else float(cal == hc))

            # ---- ARM 3 routing ----
            pc_e, hc_e = route_arm3(cal, hc, cal_eff, ctx_eff)
            row["caller_adjusted_offense_effect"] = pc_e
            row["noncalling_hc_context_effect"] = hc_e
            rows.append(row)

        if verbose:
            k = int(ident[ident.season == Y].expected_caller_id.notna().sum())
            print(f"  {design} {Y}: caller identity known {k}/32 | "
                  f"arm3 effects {'yes' if Y in effect_targets else 'NO (structural)'}")

    out = pd.DataFrame(rows)
    cols = ["season", "team", "design"] + ALL_FEATURE_COLUMNS + DIAGNOSTIC_COLUMNS
    missing = [c for c in cols if c not in out.columns]
    assert not missing, f"builder did not emit {missing}"
    out = out[cols].sort_values(["season", "team"]).reset_index(drop=True)
    assert_no_forbidden_features(ALL_FEATURE_COLUMNS, f"{design} model columns")
    assert not out[ALL_FEATURE_COLUMNS].drop(columns=["hc_changed_entering"]).isna().any().any(), (
        "a model feature other than hc_changed_entering is NaN; unknown identities must carry the "
        "frozen neutral VALUE, not NaN")
    return out


# =====================================================================================================
# RETIRED STRICT SOURCE-DATE GATE — IN-MEMORY DIAGNOSTIC SENSITIVITY ONLY
# =====================================================================================================
SENSITIVITY_LABEL = ("DIAGNOSTIC SENSITIVITY — retired strict source-date-gated history. NONPRIMARY, "
                     "NONSELECTABLE, cannot rescue or alter the primary result. Never persisted.")


def strict_gate_sensitivity(seg=None, gl=None, res=None, effects=None, target_seasons=None,
                            verbose=False):
    """Primary (ungated) vs the retired strict source-date-gated history, computed IN MEMORY.

    Returns a per-(design, season) comparison frame. It is **never written to a repo artifact**, can
    never enter representation selection, and cannot rescue a failed primary result. Every row carries
    `SENSITIVITY_LABEL`.

    This exists so the retired rule stays measurable rather than merely described.
    """
    seg = caller_segments() if seg is None else seg
    gl = game_identity() if gl is None else gl
    res = hc_game_results() if res is None else res
    effects = (pd.read_csv(DATA / "arm3_stage2_effects_v38.csv") if effects is None else effects)
    target_seasons = TARGET_SEASONS if target_seasons is None else list(target_seasons)

    rows = []
    for design in (DESIGN_A, DESIGN_B):
        ident = target_identities(design, seg, gl)
        prim = build_features(design, seg, gl, res, effects, verbose=False, ident=ident,
                              target_seasons=target_seasons, history_source_date_gated=False)
        strict = build_features(design, seg, gl, res, effects, verbose=False, ident=ident,
                                target_seasons=target_seasons, history_source_date_gated=True)
        p = prim.set_index(["season", "team"])
        s = strict.set_index(["season", "team"])
        for Y in target_seasons:
            pp = p.loc[p.index.get_level_values("season") == Y]
            ss = s.loc[s.index.get_level_values("season") == Y]
            known = pp.caller_identity_known == 1
            rows.append(dict(
                label=SENSITIVITY_LABEL, design=design, season=int(Y),
                n_team_seasons=len(pp), caller_identity_known=int(known.sum()),
                primary_known_with_history=int(((pp.caller_history_games_career > 0)
                                                & known).sum()),
                strict_known_with_history=int(((ss.caller_history_games_career > 0)
                                               & known).sum()),
                primary_caller_games=float(pp.loc[known, "caller_history_games_career"].sum()),
                strict_caller_games=float(ss.loc[known, "caller_history_games_career"].sum()),
                n_rows_with_any_feature_difference=int(
                    (~np.isclose(pp[ALL_FEATURE_COLUMNS].fillna(-999).values,
                                 ss[ALL_FEATURE_COLUMNS].fillna(-999).values)).any(axis=1).sum())))
    out = pd.DataFrame(rows)
    out["rows_gained_by_primary"] = (out.primary_known_with_history
                                     - out.strict_known_with_history)
    out["games_gained_by_primary"] = out.primary_caller_games - out.strict_caller_games
    if verbose:
        print("\n--- " + SENSITIVITY_LABEL + " ---")
        print(out.to_string(index=False))
    return out


# =====================================================================================================
# MANIFEST / COVERAGE / LINEAGE
# =====================================================================================================
BUCKETS = ["veteran", "rookie"]
# ("QB", "rookie") has NO shipped production bundle: the QB rookie arm was HELD. Recorded as a fact,
# not silently absorbed, so the manifest can state which (position, bucket) paths actually exist.
MISSING_PRODUCTION_PATHS = [("QB", "rookie")]


def arm0_baselines():
    """Exact ordered Arm 0 features per (position, bucket), READ from the shipped bundles.

    Arm 0 is production, so it is read, never re-declared here. Imported lazily because the feature
    builder must stay importable without the production projection engine on the path.
    """
    import run_coach_projection_experiment_v39 as EX
    a0 = EX.arm0_definition()
    return {k: list(v["feature_cols"]) for k, v in a0.items()}


def full_model_x(position, bucket, arm, baselines=None):
    """The COMPLETE ordered design matrix for one (position, bucket, arm).

    baseline features (production order, verbatim) THEN that arm's ordered coaching additions.
    This is exactly what reaches `fit()`; a test asserts that against the harness.
    """
    baselines = arm0_baselines() if baselines is None else baselines
    if (position, bucket) not in baselines:
        return None
    return list(baselines[(position, bucket)]) + arm_features(arm, position)


def manifest():
    m = {
        "prereg": "preregs/PREREG_coach_quality_2026-07-28.md (v3.9 PREFIT)",
        "note": ("Ordered COACHING features appended to each position's Arm-0 baseline. Arm 0 is "
                 "defined by the production bundle's `feature_cols` and is pinned by "
                 "run_coach_projection_experiment_v39.py, not here."),
        "arms": ARMS,
        "designs": DESIGN_LABEL,
        "frozen_neutral_values": {
            "rank_percentile_composite": PRIOR_RANKPCT, "z_score": PRIOR_Z,
            "arm3_effect": NEUTRAL_EFFECT, "caller_tenure": NEUTRAL_TENURE,
            "caller_entering_change": NEUTRAL_CHANGED, "caller_is_head_coach": NEUTRAL_IS_HC,
            "hc_win_pct": PRIOR_WINPCT,
        },
        "shrinkage": "reliability = pbp_games / (pbp_games + 32); frozen, never tuned",
        "rolling_window_seasons": ROLL_WINDOW,
        "arm3_effect_source": "data/arm3_stage2_effects_v38.csv",
        "arm3_structurally_unavailable_before_target_season": 2018,
        "forbidden_in_primary_features": sorted(BR.FORBIDDEN_IN_X),
        "diagnostic_only_columns": DIAGNOSTIC_COLUMNS,
        "by_position": {},
    }
    for pos in POSITIONS:
        m["by_position"][pos] = {arm: arm_features(arm, pos) for arm in ARMS}
        for arm in ARMS:
            assert_no_forbidden_features(m["by_position"][pos][arm], f"{pos}/{arm}")
    # Arm-5 exclusion contract, asserted rather than merely documented
    arm1_only = set(["hc_career_win_pct_shrunk", "hc_roll3_win_pct_shrunk",
                     "pc_career_off_rank_pct", "pc_roll3_off_rank_pct"])
    for pos in POSITIONS:
        a5 = set(arm5_features(pos))
        assert not (a5 & arm1_only), f"Arm 5 leaked an Arm 1 win/rank feature for {pos}"
        assert not (a5 & set(ARM2_QUALITY)), f"Arm 5 leaked an Arm 2 efficiency feature for {pos}"
    m["feature_counts"] = {pos: {arm: len(arm_features(arm, pos)) for arm in ARMS}
                           for pos in POSITIONS}

    # ---------------- EXACT FULL ORDERED PLAYER X, per (position, bucket, arm) ----------------
    # `by_position` above lists only the APPENDED coaching columns, which cannot express the
    # veteran/rookie baseline difference and left ARM_0 as an empty list. The manifest now pins the
    # complete matrix as well: production baseline order verbatim, then the arm's coaching additions.
    base = arm0_baselines()
    m["arm0_baseline_features"] = {f"{p}/{b}": list(v) for (p, b), v in sorted(base.items())}
    m["arm0_baseline_counts"] = {f"{p}/{b}": len(v) for (p, b), v in sorted(base.items())}
    m["missing_production_paths"] = {
        f"{p}/{b}": ("ABSENT — no shipped bundle. The QB rookie arm was HELD, so QB is evaluated on "
                     "the veteran path only and the QB top-12 cohort covers veterans.")
        for p, b in MISSING_PRODUCTION_PATHS}
    m["buckets"] = BUCKETS
    m["full_model_x"] = {}
    m["full_model_x_counts"] = {}
    for pos in POSITIONS:
        for bucket in BUCKETS:
            key = f"{pos}/{bucket}"
            if (pos, bucket) not in base:
                m["full_model_x"][key] = None          # explicit: the path does not exist
                m["full_model_x_counts"][key] = None
                continue
            m["full_model_x"][key] = {arm: full_model_x(pos, bucket, arm, base) for arm in ARMS}
            m["full_model_x_counts"][key] = {
                arm: len(m["full_model_x"][key][arm]) for arm in ARMS}
            for arm in ARMS:
                x = m["full_model_x"][key][arm]
                nb = len(base[(pos, bucket)])
                assert x[:nb] == list(base[(pos, bucket)]), (
                    f"{key}/{arm}: the baseline order is not preserved verbatim at the front of X")
                assert x[nb:] == arm_features(arm, pos), (
                    f"{key}/{arm}: coaching additions are not the manifest's ordered list")
                assert len(set(x)) == len(x), f"{key}/{arm}: duplicate column in X"
                assert_no_forbidden_features(arm_features(arm, pos), f"{key}/{arm}")
    m["full_model_x_note"] = (
        "baseline features in production order, verbatim, followed by that arm's ordered coaching "
        "additions. ARM_0 == the baseline alone. This is exactly what reaches fit().")
    return m


IDENTITY_STATES = ["all", "known_with_history", "known_no_history", "unknown"]
CALLER_DEPENDENT_ARMS = ("ARM_1", "ARM_2", "ARM_3", "ARM_4", "ARM_5")


def identity_state(row):
    """THREE distinct diagnostic states, never collapsed into one flag.

    `unknown` (we do not know WHO will call plays) and `known_no_history` (we DO know who, and he has
    called zero qualifying prior games) both route to the league prior, but for entirely different
    reasons and with different downstream diagnostics.
    """
    if not int(row["caller_identity_known"]):
        return "unknown"
    return "known_with_history" if float(row["caller_history_games_career"]) > 0 \
        else "known_no_history"


def coverage(frames):
    """(design, arm, season, identity_state) coverage with counts AND rates.

    An `all` row carries the season aggregate; the three identity-state rows decompose it. Arm-level
    columns record how many rows that arm actually reads at the league prior, which is the number a
    null result must be quoted with.
    """
    rows = []
    for design, df in frames.items():
        for Y, g in df.groupby("season"):
            g = g.copy()
            g["_state"] = [identity_state(r) for _i, r in g.iterrows()]
            n = len(g)
            counts = {s: int((g._state == s).sum()) for s in IDENTITY_STATES[1:]}
            counts["all"] = n
            for arm in ARMS:
                caller_dependent = arm in CALLER_DEPENDENT_ARMS
                for st in IDENTITY_STATES:
                    sub = g if st == "all" else g[g._state == st]
                    # rows whose CALLER-quality features sit at the league prior: unknown identity
                    # OR identified-but-no-history. Both are prior-valued; only the reason differs.
                    prior_rows = int(((g._state != "known_with_history") if st == "all"
                                      else (sub._state != "known_with_history")).sum())
                    rows.append(dict(
                        design=design, arm=arm, season=int(Y), identity_state=st,
                        n_rows=counts[st] if st != "all" else n,
                        n_team_seasons=n,
                        row_coverage_rate=round(counts[st] / n, 6) if n else np.nan,
                        caller_identity_known=int((sub.caller_identity_known == 1).sum()),
                        caller_known_with_history=int((sub._state == "known_with_history").sum()),
                        caller_known_no_history=int((sub._state == "known_no_history").sum()),
                        caller_identity_unknown=int((sub._state == "unknown").sum()),
                        mean_caller_history_games=(
                            round(float(sub.caller_history_games_career.mean()), 3)
                            if len(sub) else np.nan),
                        mean_hc_resume_games=(round(float(sub.hc_resume_games_career.mean()), 3)
                                              if len(sub) else np.nan),
                        arm3_effects_available=int(g.arm3_effects_available.iloc[0]),
                        caller_effect_nonzero=int(
                            (sub.caller_adjusted_offense_effect != 0).sum()) if len(sub) else 0,
                        context_effect_nonzero=int(
                            (sub.noncalling_hc_context_effect != 0).sum()) if len(sub) else 0,
                        neutral_is_head_coach=int(
                            (sub.caller_is_head_coach == NEUTRAL_IS_HC).sum()) if len(sub) else 0,
                        neutral_changed=int(
                            (sub.pc_changed_entering == NEUTRAL_CHANGED).sum()) if len(sub) else 0,
                        arm_uses_caller_identity=int(caller_dependent),
                        n_features_QB=len(arm_features(arm, "QB")),
                        n_features_RB=len(arm_features(arm, "RB")),
                        n_features_WR=len(arm_features(arm, "WR")),
                        n_features_TE=len(arm_features(arm, "TE")),
                        rows_at_league_prior_for_this_arm=(prior_rows if caller_dependent else 0),
                        league_prior_rate_for_this_arm=(
                            round(prior_rows / n, 6) if (caller_dependent and n) else 0.0)))
    return pd.DataFrame(rows).sort_values(
        ["design", "arm", "season", "identity_state"]).reset_index(drop=True)


def routing_lineage(frames):
    """One row per (design, target season, team): the identity decision and its source membership.

    This is what makes the feature table AUDITABLE rather than merely plausible. It proves, per row:
    strict target-season timing (`last_source_season < season`), which caller/HC identity was used,
    how many sourced segments and PBP games fed the aggregate, which identity state applied, and
    whether the league-prior fallback fired and why. It contains NO fantasy outcome.
    """
    rows = []
    for design, df in frames.items():
        for r in df.itertuples():
            st = identity_state({"caller_identity_known": r.caller_identity_known,
                                 "caller_history_games_career": r.caller_history_games_career})
            rows.append(dict(
                record_kind="identity_routing", design=design, season=int(r.season), team=r.team,
                expected_caller_id=r.expected_caller_id, expected_hc_id=r.expected_hc_id,
                identity_state=st,
                # v3.9b: history is UNGATED in both designs; the gate applies to TARGET identity only,
                # which is the single axis on which the two designs differ.
                target_identity_gate=(
                    "pre-cutoff evidence required (preseason_staff_snapshot.eligible_at_cutoff)"
                    if design == DESIGN_A
                    else "NONE — ORACLE retrospective opening caller, nondeployable"),
                history_rule="strictly prior seasons, full retrospective ledger, NOT source-date gated",
                n_source_segments=int(r.caller_history_segments_career),
                n_source_games_career=float(r.caller_history_games_career),
                n_source_games_roll3=float(r.caller_history_games_roll3),
                first_source_season=(int(r.caller_first_source_season)
                                     if pd.notna(r.caller_first_source_season) else None),
                last_source_season=(int(r.caller_last_source_season)
                                    if pd.notna(r.caller_last_source_season) else None),
                strict_timing_ok=bool(pd.isna(r.caller_last_source_season)
                                      or int(r.caller_last_source_season) < int(r.season)),
                caller_features_at_league_prior=int(st != "known_with_history"),
                league_prior_reason=("no caller identity is established" if st == "unknown"
                                     else "identified caller has zero qualifying prior games"
                                     if st == "known_no_history" else ""),
                arm3_effects_available=int(r.arm3_effects_available),
                caller_effect_source=("arm3_stage2_effects_v38.csv"
                                      if r.caller_adjusted_offense_effect != 0 else "zero_prior"),
                context_effect_source=("arm3_stage2_effects_v38.csv"
                                       if r.noncalling_hc_context_effect != 0 else "zero_prior"),
                hc_resume_games_career=float(r.hc_resume_games_career)))
    out = pd.DataFrame(rows)
    bad = out[~out.strict_timing_ok]
    assert bad.empty, f"strict timing violated on {len(bad)} routing rows"
    return out


def _segment_key(season, team, person, ws, we):
    return f"{int(season)}|{team}|{person}|{int(ws)}-{int(we)}"


def contribution_lineage(frames, seg=None):
    """One row per CANDIDATE historical segment behind each caller aggregate — included or excluded.

    The routing records prove per-row timing and totals; these prove MEMBERSHIP: exactly which sourced
    segments fed a target-season caller feature and how the games reconcile.

    **v3.9c wording correction.** This docstring previously said segments "were excluded by the Design A
    evidence gate", which was true only of the RETIRED rule. Under the adopted policy the primary
    excludes nothing by publication date — `gate_eligible` is 1 on every row — and the retired rule is
    recorded per row, diagnostic-only, as `strict_source_date_gate_would_exclude` with
    `strict_gate_exclusion_reason`.

    Deliberately RECOMPUTED here from `segment_offense.csv` rather than captured during the build, so
    the reconciliation tests compare two independent paths. If the gating logic ever drifts, the
    reconciliation assertion fails instead of the artifact quietly agreeing with itself.

    Game-level trace: `coach_reliability_lineage.csv` already maps (season, person, role) to game_ids.
    `segment_key` + `pbp_games` here reconcile exactly against that and against the feature table's
    diagnostic counts, so no fantasy outcome and no game-row duplication is needed in this artifact.
    """
    seg = caller_segments() if seg is None else seg
    seg = seg[seg.person_id.notna()].copy()
    seg["pbp_games"] = pd.to_numeric(seg["pbp_games"], errors="coerce").fillna(0.0)
    cutoffs = projection_cutoffs()
    rows = []
    for design, df in frames.items():
        for Y, grp in df.groupby("season"):
            Y = int(Y)
            cutoff = cutoffs.get(Y)
            prior = seg[seg.season < Y]
            if not len(prior):
                continue
            # PRIMARY policy: strictly-prior is the ONLY history gate. `strict_gate_ok` is carried
            # alongside so the retired source-date variant stays auditable from this artifact without
            # a sixth repo file.
            strict_ok = _gate_mask(prior, cutoff)
            prior = prior.assign(gate_ok=np.ones(len(prior), dtype=bool), strict_ok=strict_ok)
            for r in grp.itertuples():
                cal = _none(r.expected_caller_id)
                if cal is None:
                    continue
                cand = prior[prior.person_id == cal]
                for c in cand.itertuples():
                    played = float(c.pbp_games) > 0
                    included = bool(c.gate_ok) and played
                    rows.append(dict(
                        record_kind="caller_contribution", design=design, season=Y, team=r.team,
                        expected_caller_id=cal,
                        source_season=int(c.season), source_team=c.team,
                        source_week_start=int(c.week_start), source_week_end=int(c.week_end),
                        segment_key=_segment_key(c.season, c.team, c.person_id,
                                                 c.week_start, c.week_end),
                        pbp_games=float(c.pbp_games),
                        source_upper_bound=(None if pd.isna(c.source_upper_bound)
                                            else c.source_upper_bound),
                        target_cutoff=cutoff,
                        gate_eligible=int(bool(c.gate_ok)),
                        gate_exclusion_reason="",
                        # DIAGNOSTIC ONLY: would the retired strict source-date rule have dropped it?
                        strict_source_date_gate_would_exclude=int(not bool(c.strict_ok)),
                        strict_gate_exclusion_reason=(
                            "" if bool(c.strict_ok)
                            else ("attributing source has no usable date"
                                  if pd.isna(c.source_upper_bound)
                                  else "attributing source postdates the target cutoff")),
                        segment_has_pbp_games=int(played),
                        included_in_career=int(included),
                        included_in_roll3=int(included and int(c.season) >= Y - ROLL_WINDOW),
                        strict_timing_ok=bool(int(c.season) < Y),
                        game_id_trace="coach_reliability_lineage.csv"))
    out = pd.DataFrame(rows)
    assert out.strict_timing_ok.all(), "a contribution row used a source season >= its target season"
    return out


def lineage(frames=None, seg=None):
    """Feature-definition lineage, plus row-level routing and segment-level contribution lineage.

    All three live in one artifact because v3.9 authorises exactly five new data files. The
    `record_kind` column discriminates `feature_definition` / `identity_routing` /
    `caller_contribution`; the record kinds use different columns and are NaN-padded against each
    other.
    """
    rows = []

    def add(feature, arms, block, artifact, columns, window, agg, weight, shrink, prior, neutral,
            timing, note=""):
        rows.append(dict(record_kind="feature_definition", feature=feature, arms="|".join(arms),
                         block=block, source_artifact=artifact, source_columns=columns,
                         window=window, aggregation=agg, weight=weight, shrinkage=shrink,
                         league_prior=prior, neutral_on_unknown_identity=neutral,
                         timing_rule=timing, note=note))

    # v3.9c: these strings previously asserted the RETIRED source-date gate as the primary timing
    # rule, so the generated artifact contradicted the values it was documenting. The primary rule is
    # strictly prior source seasons over the FULL retrospective ledger; only the TARGET-season expected
    # caller is evidence-gated. `PRIMARY_TIMING_RULE` is asserted verbatim by test and by preflight.
    T_CALLER = PRIMARY_TIMING_RULE
    T_HC = "seasons < Y (schedules are public the moment each game ends)"
    add("hc_career_win_pct_shrunk", ["ARM_HC", "ARM_1"], "hc_resume", "snapshots/schedules_1999_2025.parquet",
        "win (REG only; tie=0.5)", "career", "wins/games", "games", "g/(g+32)", PRIOR_WINPCT,
        "n/a (HC identity always known)", T_HC, "no playoffs; unplayed games dropped, never 0")
    add("hc_roll3_win_pct_shrunk", ["ARM_HC", "ARM_1"], "hc_resume", "snapshots/schedules_1999_2025.parquet",
        "win (REG only; tie=0.5)", "prior 3 seasons", "wins/games", "games", "g/(g+32)",
        PRIOR_WINPCT, "n/a", T_HC)
    add("hc_tenure_current_team", ["ARM_HC", "ARM_1", "ARM_5"], "hc_continuity",
        "game_level_identity.csv", "hc_person_id (week 1)", "consecutive prior seasons",
        "count", "n/a", "none", "n/a", "n/a", T_HC, "relocations folded onto one team code")
    add("hc_changed_entering", ["ARM_HC", "ARM_1", "ARM_5"], "hc_continuity",
        "game_level_identity.csv", "hc_person_id (week 1 of Y vs final week of Y-1)", "entering Y",
        "indicator", "n/a", "none", "n/a", "NaN only when Y-1 identity is absent", T_HC)
    for stem, (col, prior) in SEG_METRICS.items():
        note = ("mean of >=3 of 5 rank percentiles, 1-(r-1)/(n-1) against the FULL team-season "
                "reference distribution" if stem in RANK_STEMS
                else "per-metric games counted only where the metric is non-null")
        for w in WINDOWS:
            add(f"pc_{w}_{stem}", STEM_ARMS[stem], STEM_BLOCK[stem],
                "segment_offense.csv", col, "career" if w == "career" else "prior 3 seasons",
                "games-weighted mean over the caller's prior segments", "pbp_games", "g/(g+32)",
                prior, prior, T_CALLER, note)
    for stem, src in DERIVED_NEGATION.items():
        for w in WINDOWS:
            add(f"pc_{w}_{stem}", ["ARM_4", "ARM_5"], "caller_scheme", "derived",
                f"-pc_{w}_{src}", "career" if w == "career" else "prior 3 seasons",
                "exact negation", "n/a", "inherited", PRIOR_Z, PRIOR_Z, T_CALLER,
                "z(1-x) = -z(x) within a source season; negation commutes with shrinkage to 0")
    add("pc_tenure_current_team", ["ARM_1", "ARM_2", "ARM_5"], "caller_continuity",
        "segment_offense.csv + actual_play_caller.csv", "opening caller per (season, team)",
        "consecutive prior seasons", "count", "n/a", "none", "n/a", NEUTRAL_TENURE, T_CALLER,
        "prior-season openers come from the SAME full retrospective ledger; only the TARGET-season "
        "expected caller is evidence-gated")
    add("pc_changed_entering", ["ARM_1", "ARM_2", "ARM_5"], "caller_continuity",
        "segment_offense.csv + actual_play_caller.csv",
        "opening caller of Y vs closing caller of Y-1", "entering Y", "indicator", "n/a", "none",
        "n/a", NEUTRAL_CHANGED, T_CALLER)
    add("caller_is_head_coach", ["ARM_1", "ARM_2", "ARM_3", "ARM_5"], "caller_continuity",
        "derived", "expected_caller_id == expected_hc_id", "target season", "indicator", "n/a",
        "none", "n/a", NEUTRAL_IS_HC, TARGET_SEASON_ONLY_RULE)
    add("caller_adjusted_offense_effect", ["ARM_3", "ARM_5"], "arm3_caller",
        "arm3_stage2_effects_v38.csv", "effect where role=caller", "entering Y",
        "ridge coefficient (Stage 2)", "exposure fractions", "NONE — ridge already pooled",
        NEUTRAL_EFFECT, NEUTRAL_EFFECT, "effects fit on residuals from seasons < Y",
        "zero for targets < 2018 (structurally unavailable) and for identities absent from the table")
    add("noncalling_hc_context_effect", ["ARM_3", "ARM_5"], "arm3_hc_context",
        "arm3_stage2_effects_v38.csv", "effect where role=noncalling_hc_context", "entering Y",
        "ridge coefficient (Stage 2)", "exposure fractions", "NONE", NEUTRAL_EFFECT,
        NEUTRAL_EFFECT, "effects fit on residuals from seasons < Y",
        "zero while the HC calls his own plays and zero when the caller is unknown")
    out = pd.DataFrame(rows)
    emitted = set(ALL_FEATURE_COLUMNS)
    listed = set(out.feature)
    assert listed == emitted, (f"lineage/feature mismatch: missing {sorted(emitted - listed)}, "
                               f"extra {sorted(listed - emitted)}")
    # RETIRED drive names must not survive anywhere in the lineage record either.
    blob = out.astype(str).agg("|".join, axis=1).str.cat(sep="|")
    assert_no_retired_drive_names([blob], "lineage artifact")
    out = out.sort_values(["block", "feature"], kind="mergesort").reset_index(drop=True)
    if frames is None:
        return out
    routes = routing_lineage(frames).sort_values(
        ["design", "season", "team"], kind="mergesort").reset_index(drop=True)
    contrib = contribution_lineage(frames, seg=seg).sort_values(
        ["design", "season", "team", "source_season", "source_team", "source_week_start"],
        kind="mergesort").reset_index(drop=True)
    both = pd.concat([out, routes, contrib], ignore_index=True, sort=False)
    front = ["record_kind", "design", "season", "team", "feature"]
    cols = front + [c for c in both.columns if c not in front]
    return both[cols]


# =====================================================================================================
# CANONICAL SEMANTIC VALIDATORS — one derivation, used by the builder AND by the runtime preflight
# =====================================================================================================
def compare_coverage(artifact, design_a, design_b):
    """FULL-FRAME reconciliation of the coverage artifact against a fresh canonical derivation.

    v3.9b's preflight compared only `arm == ARM_1 and identity_state == "all"`, and only
    `n_team_seasons` / `caller_identity_known`. Corrupting an ARM_2 `known_with_history` row therefore
    left `coverage_reconciles` TRUE while only the byte-hash caught it — so an intentional rebuild plus
    an updated pin could have shipped a semantically false artifact with C10 green.

    This regenerates the ENTIRE frame with `coverage()` — the same function the builder writes from —
    and compares schema, key set, key uniqueness and every cell. Comparison runs through one CSV
    round-trip so dtype and float formatting are identical on both sides by construction.

    Returns (ok, detail).
    """
    import io
    expected = coverage({DESIGN_A: design_a, DESIGN_B: design_b})
    exp = pd.read_csv(io.StringIO(expected.to_csv(index=False)))
    key = ["design", "arm", "season", "identity_state"]

    if list(artifact.columns) != list(exp.columns):
        missing = [c for c in exp.columns if c not in artifact.columns]
        extra = [c for c in artifact.columns if c not in exp.columns]
        return False, f"schema differs: missing {missing}, unexpected {extra}"
    if len(artifact) != len(exp):
        return False, f"row count {len(artifact)} != expected {len(exp)}"
    if artifact.duplicated(key).any():
        dup = artifact[artifact.duplicated(key, keep=False)][key].head(3).to_dict("records")
        return False, f"duplicate coverage keys: {dup}"
    a = artifact.sort_values(key, kind="mergesort").reset_index(drop=True)
    e = exp.sort_values(key, kind="mergesort").reset_index(drop=True)
    if not a[key].equals(e[key]):
        a_keys = set(map(tuple, a[key].values))
        e_keys = set(map(tuple, e[key].values))
        return False, (f"key set differs: missing {sorted(e_keys - a_keys)[:3]}, "
                       f"unexpected {sorted(a_keys - e_keys)[:3]}")
    bad = []
    for c in exp.columns:
        if c in key:
            continue
        av, ev = a[c], e[c]
        if pd.api.types.is_numeric_dtype(ev) and pd.api.types.is_numeric_dtype(av):
            same = np.isclose(av.astype(float), ev.astype(float), equal_nan=True, atol=0, rtol=0)
        else:
            same = av.astype(str).values == ev.astype(str).values
        if not same.all():
            i = int(np.flatnonzero(~same)[0])
            bad.append(f"{c} at {a.loc[i, key].to_dict()}: artifact {av.iloc[i]!r} "
                       f"!= derived {ev.iloc[i]!r}")
    if bad:
        return False, f"{len(bad)} column(s) disagree: " + "; ".join(bad[:3])
    return True, (f"full-frame reconciliation: {len(exp)} rows x {len(exp.columns)} columns, "
                  f"all cells match a fresh derivation")


def validate_lineage_policy(lineage_artifact):
    """Semantic check that the lineage artifact states the CURRENT policy, not the retired one.

    v3.9b's preflight relied on the MD5 for this, so the generated artifact could — and did — assert
    the retired source-date gate as the primary timing rule while the feature VALUES used the adopted
    policy. That contradiction is exactly what a hash cannot see.
    """
    lin = lineage_artifact
    problems = []
    fd = lin[lin.record_kind == "feature_definition"]
    caller_blocks = {"caller_rank_quality", "caller_efficiency", "caller_scheme",
                     "caller_continuity"}
    cal = fd[fd.block.isin(caller_blocks)]
    if not len(cal):
        problems.append("no caller feature-definition rows found")
    # `caller_is_head_coach` compares two TARGET-season identities and aggregates no history, so it
    # legitimately carries the target-season rule rather than the historical one.
    hist = cal[cal.timing_rule.astype(str) != TARGET_SEASON_ONLY_RULE]
    off = hist[hist.timing_rule.astype(str) != PRIMARY_TIMING_RULE]
    if len(off):
        problems.append(f"{len(off)} caller-history rows do not carry the primary timing rule, e.g. "
                        f"{off.feature.iloc[0]!r} -> {off.timing_rule.iloc[0]!r}")
    if not len(hist):
        problems.append("no caller-HISTORY rows found to validate")
    # No live row may assert a source-date gate anywhere in its policy text.
    for col in ("timing_rule", "note", "shrinkage", "aggregation"):
        if col not in fd.columns:
            continue
        text = fd[col].fillna("").astype(str)
        for phrase in RETIRED_HISTORY_GATE_PHRASES:
            hit = fd[text.str.contains(phrase, regex=False)]
            if len(hit):
                problems.append(f"{col} on {hit.feature.iloc[0]!r} still asserts {phrase!r}")
    rt = lin[lin.record_kind == "identity_routing"]
    if len(rt):
        if rt.history_rule.nunique() != 1:
            problems.append("identity_routing carries more than one history_rule")
        elif "NOT source-date gated" not in str(rt.history_rule.iloc[0]):
            problems.append(f"routing history_rule is {rt.history_rule.iloc[0]!r}")
        if "evidence_gate" in rt.columns:
            problems.append("the retired `evidence_gate` column is still present")
    ct = lin[lin.record_kind == "caller_contribution"]
    if len(ct):
        if not (ct.gate_eligible == 1).all():
            problems.append("a contribution row is gate-excluded under the primary policy")
        if "strict_source_date_gate_would_exclude" not in ct.columns:
            problems.append("the retired rule is no longer recorded as a diagnostic")
    return (not problems), ("; ".join(problems) if problems
                            else "lineage states the primary policy; retired rule diagnostic-only")


# =====================================================================================================
# ROUTING ASSERTIONS
# =====================================================================================================
NUMERICAL_ZERO = 1e-12

# Three DIFFERENT kinds of zero, and they must not be conflated:
#   LAC  Harbaugh IS a distinct non-calling head coach, so his context coefficient legitimately
#        applies -- and that coefficient is NUMERICALLY zero (2.37e-18) because entering 2026 the
#        HC-context block sat at the extended upper alpha boundary (1e16 = effective complete
#        pooling). The feature carries the fitted value; it is NOT forced to 0.
#   LA   McVay calls his own plays and has NO context row in the effect table at all, so the effect
#        appears exactly once and the context feature is EXACTLY 0.
#   KC   Reid DOES have a context coefficient, but self-calling routing suppresses it, so the
#        feature is EXACTLY 0 while he calls his own plays.
EXPECT_2026 = {
    "LAC": dict(caller="mike_mcdaniel", hc="jim_harbaugh", changed=1.0, is_hc=0.0,
                caller_effect=0.005262, context="numerical_zero"),
    "LA": dict(caller="sean_mcvay", hc="sean_mcvay", changed=0.0, is_hc=1.0,
               caller_effect=0.025936, context="exact_zero"),
    "KC": dict(caller="andy_reid", hc="andy_reid", changed=0.0, is_hc=1.0,
               caller_effect=0.038287, context="exact_zero"),
}


def _context_ok(mode, value):
    return value == 0.0 if mode == "exact_zero" else abs(value) < NUMERICAL_ZERO


def routing_report(df_a, effects=None):
    effects = (pd.read_csv(DATA / "arm3_stage2_effects_v38.csv") if effects is None else effects)
    cal26, ctx26 = arm3_lookup(effects, 2026)
    print("\n--- 2026 ROUTING ASSERTIONS (Design A) ---")
    ok = True
    for team, exp in EXPECT_2026.items():
        r = df_a[(df_a.season == 2026) & (df_a.team == team)].iloc[0]
        checks = [
            ("expected caller", r.expected_caller_id == exp["caller"], r.expected_caller_id),
            ("expected HC", r.expected_hc_id == exp["hc"], r.expected_hc_id),
            ("caller changed entering", r.pc_changed_entering == exp["changed"],
             r.pc_changed_entering),
            ("caller_is_head_coach", r.caller_is_head_coach == exp["is_hc"], r.caller_is_head_coach),
            ("caller effect", abs(r.caller_adjusted_offense_effect - exp["caller_effect"]) < 5e-7,
             r.caller_adjusted_offense_effect),
            (f"context {exp['context']}",
             _context_ok(exp["context"], r.noncalling_hc_context_effect),
             r.noncalling_hc_context_effect),
        ]
        for label, good, got in checks:
            ok &= bool(good)
            print(f"  {'PASS' if good else 'FAIL'}  2026 {team:3s} {label:24s} = {got}")
    # LAC: previous caller was Greg Roman, whose ADJUSTED effect is HIGHER than McDaniel's.
    d = cal26["mike_mcdaniel"] - cal26["greg_roman"]
    print(f"\n  McDaniel {cal26['mike_mcdaniel']:+.6f} vs Roman {cal26['greg_roman']:+.6f} "
          f"-> difference {d:+.6f} EPA/play")
    print("  Arm 3 does NOT support a Chargers play-calling UPGRADE. McDaniel's adjusted coefficient "
          "is BELOW Roman's.")
    ok &= (d < 0)
    # Rams: McVay never appears in the HC-context block at all -> no duplicate effect
    mv_ctx = effects[(effects.person_id == "sean_mcvay")
                     & (effects.role == BR.ROLE_HC_CTX)]
    print(f"  McVay HC-context rows in the effect table: {len(mv_ctx)} (expect 0 — he calls his own "
          f"plays, so the effect appears exactly once)")
    ok &= (len(mv_ctx) == 0)
    # KC: Reid HAS a context row, but self-calling routing must suppress it
    reid_ctx = float(ctx26.get("andy_reid", 0.0))
    print(f"  Reid's HC-context coefficient exists ({reid_ctx:.3e}) but routing suppresses it while "
          f"he self-calls -> feature value 0.0")
    assert ok, "2026 routing assertions FAILED"
    return ok


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


# OWNERSHIP (asserted by tests/test_artifact_ownership.py). v3.9 authorises EXACTLY these five new
# repo artifacts; the head-coach win ledger is derived in memory from the frozen snapshot.
OWNED_ARTIFACTS = ["team_coach_features_design_a_v39.csv",
                   "team_coach_features_design_b_oracle_v39.csv",
                   "arm_feature_manifest_v39.json", "arm_feature_coverage_v39.csv",
                   "arm_feature_lineage_v39.csv"]


def build():
    print("=" * 92)
    print("PHASE 2A v3.9 — POINT-IN-TIME COACHING REPRESENTATIONS (no fantasy outcome touched)")
    print("=" * 92)
    seg = caller_segments()
    gl = game_identity()
    res = hc_game_results()
    effects = pd.read_csv(DATA / "arm3_stage2_effects_v38.csv")
    print(f"segments {len(seg)} | hc game-results {len(res)} | arm3 effect rows {len(effects)}")

    a = build_features(DESIGN_A, seg, gl, res, effects)
    b = build_features(DESIGN_B, seg, gl, res, effects)
    a.to_csv(DATA / "team_coach_features_design_a_v39.csv", index=False)
    b.to_csv(DATA / "team_coach_features_design_b_oracle_v39.csv", index=False)

    frames = {DESIGN_A: a, DESIGN_B: b}
    man = manifest()
    (DATA / "arm_feature_manifest_v39.json").write_text(
        json.dumps(man, indent=2, sort_keys=True), encoding="utf-8")
    cov = coverage(frames)
    cov.to_csv(DATA / "arm_feature_coverage_v39.csv", index=False)
    lin = lineage(frames, seg=seg)
    lin.to_csv(DATA / "arm_feature_lineage_v39.csv", index=False)

    print("\n--- FEATURE COUNTS BY POSITION AND ARM ---")
    print(pd.DataFrame(man["feature_counts"]).T[ARMS].to_string())

    print("\n--- DESIGN A CALLER COVERAGE BY SEASON ---")
    ca = cov[(cov.design == DESIGN_A) & (cov.arm == "ARM_1")
             & (cov.identity_state == "all")]
    print(ca[["season", "caller_identity_known", "caller_known_with_history",
              "caller_known_no_history", "caller_identity_unknown", "mean_caller_history_games",
              "arm3_effects_available", "caller_effect_nonzero",
              "context_effect_nonzero"]].to_string(index=False))
    o = ca[ca.season.isin(OUTER_SEASONS)]
    print(f"  OUTER 2018-2025 Design A caller coverage: "
          f"{int(o.caller_identity_known.sum())}/{int(o.n_team_seasons.sum())}")
    cb = cov[(cov.design == DESIGN_B) & (cov.arm == "ARM_1")
             & (cov.identity_state == "all")]
    ob = cb[cb.season.isin(OUTER_SEASONS)]
    print(f"  OUTER 2018-2025 Design B (ORACLE, NONDEPLOYABLE) caller coverage: "
          f"{int(ob.caller_identity_known.sum())}/{int(ob.n_team_seasons.sum())}")

    routing_report(a, effects)

    print("\n--- ARTIFACT HASHES ---")
    for f in OWNED_ARTIFACTS:
        print(f"  {f:46s} {md5(DATA / f)}")
    print("\nNO fantasy outcome was read. NO production artifact was written.")
    return a, b, man, cov, lin


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.build:
        build()
    else:
        raise SystemExit("pass --build")
