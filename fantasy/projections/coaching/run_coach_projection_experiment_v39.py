"""PHASE 2B (prereg v3.9 PREFIT) — NESTED COACH-REPRESENTATION EVALUATION HARNESS.

=====================================================================================================
STOP CONDITION — READ FIRST
=====================================================================================================
**NO REAL FANTASY OUTCOME MAY BE FIT THROUGH THIS MODULE.** `REAL_FIT_AUTHORIZED` is False and every
entry point that would assemble the production player panel raises. The harness is exercised end to
end on SYNTHETIC targets only, so the machinery is verified before any outcome is visible. Turning it
on requires a written PREFIT amendment recording what was known at the time, plus Joseph's approval.

**THIS MODULE WRITES NO REPO ARTIFACT AT ALL.** v3.9 authorises exactly five new data files, all of
them owned by `build_arm_features_v39.py`. The production audit and the frozen harness spec are
returned as structures and recorded in `V39_PREFIT_STOP_REPORT.md`.

=====================================================================================================
ARM 0 IS READ OUT OF PRODUCTION, NOT RE-DECLARED
=====================================================================================================
Arm 0 is the exact ordered `feature_cols` stored in each shipped bundle, cross-checked against the
module-level feature pool in the builder that produced it. The model family, hyperparameters,
missing-value policy and prediction target all come from the same bundle. `_make_model` and `_prep`
are IMPORTED from `build_rb_projection` — the position-agnostic production engine — so the arms are
compared using production's own fitting code rather than a look-alike.

Audited and pinned (2026-07-29):

  family / params      LightGBM, objective="mae", random_state=42, verbose=-1, n_jobs=-1.
                       Per-bundle: qb_vet 31/0.03/400 · rb_vet 15/0.03/400 · rb_rook 15/0.06/400 ·
                       wr_vet 15/0.03/400 · wr_rook 31/0.06/400 · te_vet 15/0.03/400 ·
                       te_rook 15/0.03/400  (num_leaves / learning_rate / n_estimators)
  ordered baselines    veteran = the same 32 season_dataset columns for all four positions
                       (INCLUDING the existing `coach_changed` and `qb_changed`); rookie = RB 41,
                       WR 44, TE 44. `depth_rank` is excluded (RB prereg Amendment 1).
  categorical handling NONE. Every matrix is `df[feats].to_numpy(float)`; no categorical dtype, no
                       one-hot, no label encoding anywhere in the four builders.
  sample weights       NONE. `model.fit(Xtr, ytr)` is called without `sample_weight`. `season_dataset`
                       does carry `sample_weight = games`, but the projection builders never read it.
  missing values       native NaN routed by LightGBM (`median_impute` is None in all seven bundles).
                       The median+flag path exists only for the ElasticNet family, which no shipped
                       bundle selected.
  target               observed season-total half-PPR, summed from weekly REG stats as
                       `fantasy_points + 0.5*receptions` (`build_rb_projection.season_total_target`).
                       NOT `target_ppg`, which `build_season_dataset` NaNs below MIN_GAMES_TARGET = 3
                       games and which would drop partial seasons. Seasons <= 2025 fill a missing
                       total with 0.0 (rostered, never played); 2026 stays NaN.
  QB ROOKIE PATH       **DOES NOT EXIST.** There is no `qb_rookie_model.pkl` — the QB rookie arm was
                       HELD. QB is therefore evaluated on the veteran path only and the QB top-12
                       cohort is defined over veterans. Recorded, not silently absorbed.

=====================================================================================================
FROZEN EVALUATION DESIGN
=====================================================================================================
outer test seasons          2018-2025; 2021-2025 additionally reported as the recent panel
inner validation            EXPANDING, `inner training < validation < outer target`. Outer 2018 =
                            [train 2014-2015 -> validate 2016], [train 2014-2016 -> validate 2017].
                            Frozen minimums 2 training and 2 validation seasons; a target that
                            cannot meet them is SKIPPED, never fitted on relaxed folds.
arms compared               ARM_0, ARM_HC, ARM_1, ARM_2, ARM_3, ARM_4, ARM_5 (7)
identical rows              every arm predicts the SAME player rows in every fold; asserted
cohorts                     defined by the ARM 0 prediction: QB 12, RB 24, WR 24, TE 12
eligibility                 an arm is eligible only if inner FULL-PANEL MAE worsens by <= 0.25
selection                   best eligible arm by mean inner TOP-COHORT MAE; if the best coaching arm
                            improves top-cohort MAE by < 1% vs ARM0 -> select ARM0; arms within 0.25
                            top-cohort MAE points of the best -> select the one with FEWER added
                            features (ties then broken by the frozen arm order)
identity design             Design A is PRIMARY. Design B is ORACLE and can never enter selection.
diagnostics                 ARM_HC and ARMS 1-5 as FIXED arms, plus the Design B oracle variants
metrics                     full-panel and top-cohort MAE and RMSE, mean and median bias, mean
                            within-season Spearman
uncertainty                 player-clustered AND team-season-clustered bootstrap, 20,000 draws,
                            seed 20260728; Holm correction across the SIX fixed arms (ARM_HC and
                            ARMS 1-5) within each position
placebo                     within-season TEAM-LEVEL permutation: complete team coaching bundles are
                            permuted among the teams of that season, so every player on a team
                            receives another team's whole bundle. Individual player rows are never
                            shuffled and each season's bundle composition is preserved, which is what
                            makes the placebo a control for season-level structure. 200 draws.

WHY THE PLACEBO IS THE CONTROL THAT MATTERS HERE. Under Design A the caller-unknown neutral encoding
is season-correlated (0% coverage in 2017/2020/2021/2022 and ~100% in 2018/2023/2024), so a coaching
arm could in principle gain by acting as a partial season indicator rather than by carrying coaching
information. Permuting complete bundles WITHIN a season leaves that season structure intact under the
null, so a season-proxy gain reproduces in the placebo and fails the 95th-percentile bar.

Run:  python run_coach_projection_experiment_v39.py --audit
      python run_coach_projection_experiment_v39.py --synthetic
"""
import argparse
import ast
import hashlib
import json
import os
import pathlib
import sys

import numpy as np
import pandas as pd

import build_arm_features_v39 as AF

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
PROJ = HERE.parent                                   # fantasy/projections
MODELS = PROJ / "models"
SEAS = HERE.parent.parent / "seasonal_projections"

# =====================================================================================================
# THE STOP CONDITION — a DEFAULT-CLOSED gate, not a comment
# =====================================================================================================
# Two independent locks must BOTH be opened before any real outcome can be loaded:
#   1. this module-level constant, and
#   2. the environment variable named below, set to the exact literal token.
# A plain `python run_coach_projection_experiment_v39.py --synthetic` (or any import, or any test)
# therefore cannot reach a real label even by accident. Neither lock is opened in this pass.
REAL_FIT_AUTHORIZED = False
REAL_FIT_ENV_SWITCH = "COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH"
REAL_FIT_ENV_TOKEN = "I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT"
REAL_FIT_MESSAGE = (
    "REAL FANTASY FITTING IS NOT AUTHORIZED under prereg v3.9. The harness is verified on synthetic "
    "targets only. Enabling it requires (a) a written PREFIT amendment recording what was known at "
    "the time, (b) Joseph's explicit approval, (c) the exact --authorization-token, and (d) "
    f"{REAL_FIT_ENV_SWITCH}={REAL_FIT_ENV_TOKEN} in the environment. Flipping either lock without "
    "the amendment defeats the entire pre-registration.")


# --- THE INVOCATION-SCOPED AUTHORIZATION CAPABILITY -------------------------------------------------
# A contradiction was found by reading the committed source at 8ca2efc: C6 statically requires exactly
# one module-level `REAL_FIT_AUTHORIZED = False`, while `authorized_real` required that constant to be
# True at runtime. Editing the source to True made C6 — and therefore the 21-check preflight — FAIL, so
# the documented command could not open both locks by any route. The tests only reached the authorized
# path by monkeypatching the global, which the CLI has no equivalent of.
#
# The fix is a CAPABILITY, not a mutable flag. `REAL_FIT_AUTHORIZED = False` stays in the committed
# source forever as the default-closed invariant; it is never reassigned, and nothing about a real run
# is stored in a module global. Authorization exists only as an immutable object created per
# invocation, from two exact tokens, and threaded explicitly through every gate. It cannot persist
# after the call that made it.
REAL_FIT_CLI_TOKEN = "JOSEPH-AUTHORIZED-V39-FIRST-REAL-RUN"


class RealFitAuthorization:
    """Proof that BOTH runtime locks were presented in one invocation. Immutable; never global.

    Constructed only by `grant_real_fit_authorization`, only when the CLI token and the environment
    token both match their frozen literals exactly. Holding one authorizes exactly one call chain.
    """

    __slots__ = ("_cli_ok", "_env_ok")

    def __init__(self, cli_token, env_token):
        if cli_token != REAL_FIT_CLI_TOKEN:
            raise RuntimeError("authorization refused: the CLI authorization token is absent or wrong")
        if env_token != REAL_FIT_ENV_TOKEN:
            raise RuntimeError(f"authorization refused: {REAL_FIT_ENV_SWITCH} is absent or wrong")
        object.__setattr__(self, "_cli_ok", True)
        object.__setattr__(self, "_env_ok", True)

    def __setattr__(self, *_a):
        raise AttributeError("RealFitAuthorization is immutable")

    def __delattr__(self, *_a):
        raise AttributeError("RealFitAuthorization is immutable")

    @property
    def lock_state(self):
        return (self._cli_ok, self._env_ok)

    def is_valid(self):
        return self._cli_ok is True and self._env_ok is True


def grant_real_fit_authorization(cli_token=None, env=None):
    """Mint the capability, or raise. BOTH tokens, exact, in this one invocation."""
    env_token = (os.environ.get(REAL_FIT_ENV_SWITCH) if env is None else env.get(REAL_FIT_ENV_SWITCH))
    return RealFitAuthorization(cli_token, env_token)


def authorization_is_valid(authorization):
    """A forged, partial, malformed or absent capability is not authorization."""
    return isinstance(authorization, RealFitAuthorization) and authorization.is_valid()


def real_fit_lock_state(authorization=None):
    """(cli_ok, env_ok) at the moment of use. Never cached, never read from a mutable global.

    With no capability the state is CLOSED — `REAL_FIT_AUTHORIZED` is the default-closed invariant and
    is never consulted as an opener, so mutating it at runtime authorizes nothing.
    """
    if authorization is None:
        return (False, os.environ.get(REAL_FIT_ENV_SWITCH) == REAL_FIT_ENV_TOKEN)
    if not authorization_is_valid(authorization):
        return (False, False)
    return authorization.lock_state


def real_fit_is_unlocked(authorization=None):
    """BOTH locks, checked at the moment of use, from the capability alone."""
    c, e = real_fit_lock_state(authorization)
    return c and e


def require_real_fit_authorization(authorization=None):
    if not real_fit_is_unlocked(authorization):
        raise RuntimeError(REAL_FIT_MESSAGE)
    return True


# ---------------------------------------------------------------- run modes (v3.9b §3)
# The v3.9a integrity check treated an UNLOCKED gate as a failure. Correct during prefit, but it made
# `DEVELOPMENTAL CANDIDATE` unreachable for any authorized real run, because such a run must open both
# locks. The lock expectation is therefore a property of the RUN MODE, not a universal invariant.
RUN_MODE_SYNTHETIC_PREFIT = "synthetic_prefit"
RUN_MODE_AUTHORIZED_REAL = "authorized_real"
RUN_MODES = (RUN_MODE_SYNTHETIC_PREFIT, RUN_MODE_AUTHORIZED_REAL)
DEFAULT_RUN_MODE = RUN_MODE_SYNTHETIC_PREFIT

# --- WHICH C5 CONTRACT THE SOURCE MUST SATISFY -------------------------------------------------------
# Declared EXPLICITLY, never inferred from the lock state — "which contract applies" must not be
# decided by the very thing the contract protects. This says only what SHAPE `assemble_real_panel` has
# in the file. It is NOT a run mode, NOT a lock, and it authorizes nothing: with the door implemented,
# statement 1 still refuses unless BOTH locks are open and statement 2 still refuses unless preflight,
# readiness and the gate all pass. `DEFAULT_RUN_MODE` above remains `synthetic_prefit`.
ENTRY_POINT_CONTRACT_MODE = RUN_MODE_AUTHORIZED_REAL

# Names C5-A pins by value, so a rename cannot quietly satisfy the contract against a different callee.
PREFLIGHT_CLEARANCE_NAME = "require_preflight_clearance"
# The door's authorization parameter. C5-A pins statement 1 to consume exactly this name, so a
# future edit cannot swap the capability for a literal, a global or a freshly minted grant.
AUTHORIZATION_PARAM = "authorization"
PANEL_CORE_NAME = "assemble_panel_core"
# C5-A clause 3: the door may not read. Readers arrive as parameters and are called on its behalf.
ENTRY_POINT_BANNED_READER_CALLEES = frozenset({"read_csv", "read_parquet", "read_json", "open",
                                               "ParquetFile", "load", "joblib"})
# C5-A clause 4: nor may it reach a live outcome loader.
BANNED_OUTCOME_CALLEES = frozenset({"load_player_stats", "load_pbp", "load_pbp_stats",
                                    "season_total_target", "load_schedules", "load_rosters"})


def validate_run_mode(run_mode, lock_state=None, authorization=None):
    """Fail-closed run-mode contract. Returns (ok, detail).

      synthetic_prefit : BOTH locks MUST be closed
      authorized_real  : BOTH locks MUST be open (constant + env token)

    A partially authorized state is invalid in BOTH modes, so it can never be read as "close enough".
    An unknown mode is invalid. **No mode ever relaxes an artifact, timing, leakage, coverage or
    feature-policy check** — the mode governs only the lock expectation.
    """
    c, e = real_fit_lock_state(authorization) if lock_state is None else lock_state
    if run_mode not in RUN_MODES:
        return False, f"unknown run_mode {run_mode!r}; expected one of {RUN_MODES}"
    if run_mode == RUN_MODE_SYNTHETIC_PREFIT:
        if c or e:
            return False, ("synthetic_prefit requires BOTH real-fit locks CLOSED "
                           f"(constant={c}, env={e})")
        return True, "synthetic_prefit: both locks closed, as required"
    if not (c and e):
        return False, ("authorized_real requires BOTH real-fit locks OPEN "
                       f"(constant={c}, env={e}) — a partially authorized state fails closed")
    return True, "authorized_real: both locks open and the written-amendment token is present"


# Tally of the timing / leakage / row-identity assertions the pipeline actually executed. C10 requires
# each to be non-zero, so "the assertions passed" means they RAN, not merely that nothing raised.
_PIPELINE_ASSERTIONS = {"inner_fold_timing": 0, "outer_no_self_train": 0,
                        "identical_rows_across_arms": 0, "coach_join_preserved_rows": 0}


def reset_pipeline_assertions():
    for k in _PIPELINE_ASSERTIONS:
        _PIPELINE_ASSERTIONS[k] = 0


def _note_assertion(name):
    _PIPELINE_ASSERTIONS[name] = _PIPELINE_ASSERTIONS.get(name, 0) + 1

# ---------------------------------------------------------------- frozen constants
OUTER_SEASONS = list(range(2018, 2026))
RECENT_SEASONS = list(range(2021, 2026))
PANEL_FIRST_SEASON = 2014
INNER_MIN_TRAIN_SEASONS = 2
INNER_MIN_VALIDATION_SEASONS = 2
COHORT_N = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
FULL_PANEL_TOLERANCE = 0.25          # inner full-panel MAE may worsen by at most this
MIN_RELATIVE_IMPROVEMENT = 0.01      # below 1% top-cohort improvement -> ARM0
TIE_BAND = 0.25                      # within this many top-cohort MAE points -> fewer features wins
BOOTSTRAP_DRAWS = 20_000
BOOTSTRAP_SEED = 20260728
PLACEBO_DRAWS = 200
PLACEBO_SEED = 20260728
ARMS = AF.ARMS                        # ARM0, ARM_HC, ARM1..ARM5 — frozen order breaks final ties
FIXED_DIAGNOSTIC_ARMS = [a for a in ARMS if a != "ARM_0"]
POSITIONS = AF.POSITIONS
BUCKETS = ["veteran", "rookie"]
CLUSTER_UNITS = {"player": ["player_id"], "team_season": ["season", "team"]}

BUNDLE_FILE = {("QB", "veteran"): "qb_veteran_model.pkl",
               ("RB", "veteran"): "rb_veteran_model.pkl",
               ("RB", "rookie"): "rb_rookie_model.pkl",
               ("WR", "veteran"): "wr_veteran_model.pkl",
               ("WR", "rookie"): "wr_rookie_model.pkl",
               ("TE", "veteran"): "te_veteran_model.pkl",
               ("TE", "rookie"): "te_rookie_model.pkl"}
# ("QB", "rookie") is absent BY FACT: the QB rookie arm was held and no bundle was ever shipped.
MISSING_BUNDLES = [("QB", "rookie")]

PRODUCTION_HASHES = {
    "qb_veteran_model.pkl": "7632549f95995b9702baefdf016d7271",
    "rb_rookie_model.pkl": "da230ee66575ca574f02cbc2139e1a80",
    "rb_veteran_model.pkl": "167aca71a8511afcced37c0abc846004",
    "te_rookie_model.pkl": "f79dad0ab26af5cb4e06a9f1723328cd",
    "te_veteran_model.pkl": "5a2f0b504d4cc6fc9a2e04453fd76a44",
    "wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
    "wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
}
ROOKIE_PPG_MD5 = "872467b2295fce27761f9e04da01b6e8"


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


# =====================================================================================================
# PRODUCTION AUDIT — Arm 0 is READ, never re-declared
# =====================================================================================================
def _production_engine():
    """Import the production engine and the four position builders.

    Importing rather than re-implementing is the whole point: `_make_model` / `_prep` below ARE the
    functions that fit the shipped models.
    """
    if str(PROJ) not in sys.path:
        sys.path.insert(0, str(PROJ))
    import build_qb_projection as QB
    import build_rb_projection as RB
    import build_te_projection as TE
    import build_wr_projection as WR
    return RB, dict(QB=QB, RB=RB, WR=WR, TE=TE)


def builder_pools():
    """(position, bucket) -> the builder's module-level ordered feature pool."""
    _RB, mods = _production_engine()
    return {
        ("QB", "veteran"): list(mods["QB"].QB_VET_ALL),
        ("QB", "rookie"): list(mods["QB"].QB_ROOK_ALL),
        ("RB", "veteran"): list(mods["RB"].VET_ALL),
        ("RB", "rookie"): list(mods["RB"].ROOK_ALL),
        ("WR", "veteran"): list(mods["WR"].WR_VET_ALL),
        ("WR", "rookie"): list(mods["WR"].WR_ROOK_ALL),
        ("TE", "veteran"): list(mods["TE"].TE_VET_ALL),
        ("TE", "rookie"): list(mods["TE"].TE_ROOK_ALL),
    }


def arm0_definition():
    """Arm 0 from stored bundle metadata, cross-checked against builder code."""
    import joblib
    pools = builder_pools()
    out, mismatches = {}, []
    for (pos, bucket), fname in BUNDLE_FILE.items():
        p = MODELS / fname
        b = joblib.load(p)
        feats = list(b["feature_cols"])
        if feats != pools[(pos, bucket)]:
            mismatches.append(f"{pos}/{bucket}: bundle order != builder pool")
        out[(pos, bucket)] = dict(
            bundle=fname, md5=md5(p), family=b["family"], params=dict(b["params"]),
            feature_cols=feats, n_features=len(feats), target=b["target"], seed=b["seed"],
            inner_cv_mae=b["inner_cv_mae"],
            median_impute=(None if b["median_impute"] is None else sorted(b["median_impute"])),
            model_class=type(b["model"]).__module__ + "." + type(b["model"]).__name__,
            note=b.get("note"))
    assert not mismatches, "Arm 0 drift between bundle and builder:\n  " + "\n  ".join(mismatches)
    return out


def audit_production(write=False):
    """Structured production audit, read out of executable code and stored bundle metadata.

    `write` exists only for symmetry; v3.9 authorises exactly five new repo data artifacts and this
    audit is NOT one of them, so the record lives in `V39_PREFIT_STOP_REPORT.md` and in this function.
    Nothing is written unless a caller explicitly opts in, and no test does.
    """
    a0 = arm0_definition()
    RB, _mods = _production_engine()
    audit = {
        "audited": "2026-07-29 (prereg v3.9 PREFIT)",
        "TWO_ARCHITECTURES_EXIST_IN_THIS_REPO": {
            "arm0_family_USED": {
                "location": "fantasy/projections/models/ (7 bundles)",
                "target": "season_total_half_ppr — a DIRECT season total",
                "bundle_keys": ["model", "feature_cols", "family", "params", "inner_cv_mae",
                                "target", "seed", "median_impute", "note"],
                "why": "prereg §3.3/§4 define Arm 0 as each position's SHIPPED bundle for the "
                       "season-total build; that is this family",
            },
            "legacy_family_NOT_USED": {
                "location": "fantasy/seasonal_projections/models/",
                "architecture": "Model A x Model B: season total = PPG * games",
                "members": {
                    "{qb,rb,wr,te}_ppg_model.pkl": "target target_ppg, LightGBM, 31 features, "
                                                   "bundle keys algo/position/train_seasons",
                    "availability_model.pkl": "target target_games, CatBoost, 13 features, "
                                              "CARRIES cat_features",
                    "rookie_ppg_model.pkl": "target target_ppg, CatBoost, 18 features, "
                                            "CARRIES cat_features",
                },
                "IMPORTANT": "this family DOES use categorical features and DOES fit with "
                             "sample_weight=games (train_model_a.py: "
                             "model.fit(train[feats], train.target_ppg, "
                             "sample_weight=train.sample_weight)). The 'no categoricals / no sample "
                             "weights' statements below are scoped to the Arm 0 family ONLY and must "
                             "not be generalised to the repo.",
            },
        },
        "veteran_path": {
            "router": "build_season_dataset.py season_dataset_2014_2026.csv -> is_rookie == 0",
            "builders": ["build_qb_projection.py", "build_rb_projection.py",
                         "build_wr_projection.py", "build_te_projection.py"],
            "engine": "build_rb_projection.py — the position-agnostic engine the other three IMPORT "
                      "(season_total_target, nested_select, walk_forward, fit_final_model, _prep, "
                      "_grid, _make_model, _score_bundle, metrics). Never modified by them.",
            "ordered_features_identical_across_positions": True,
        },
        "rookie_path": {
            "router": "season_dataset -> is_rookie == 1, joined to the FROZEN hit-model rookie "
                      "matrix regenerated in a TEMP scratch dir (no PFF parquet in the repo), then "
                      "coalesced by (norm_name, position) for the 2026 placeholder-gsis seam",
            "qb_rookie_bundle": "ABSENT — the QB rookie arm was HELD; QB is evaluated on the "
                                "veteran path only and the QB top-12 cohort covers veterans",
        },
        "prediction_target": {
            "name": "season_total_half_ppr",
            "construction": "sum over REG weeks of (fantasy_points + 0.5*receptions), per "
                            "(player_id, season); build_rb_projection.season_total_target()",
            "not_used_by_arm0": {
                "target_ppg": "half_ppr/games, NaN below MIN_GAMES_TARGET=3 — would drop partial "
                              "seasons; this IS the legacy Model-A target",
                "target_games": "legacy Model-B availability target",
                "sample_weight": "games; present in season_dataset and USED BY THE LEGACY Model A, "
                                 "never passed to fit() in the season-total family"},
            "ppg_games_total_composition": "NOT used by Arm 0. The season total is predicted "
                                           "DIRECTLY. PPG*games composition belongs to the legacy "
                                           "family only.",
            "missing_target_rule": "seasons <= 2025 fill missing with 0.0 (rostered, never played); "
                                   "the 2026 deploy season stays NaN",
        },
        "model_families": {f"{p}/{b}": {"family": v["family"], "params": v["params"],
                                        "model_class": v["model_class"]}
                           for (p, b), v in a0.items()},
        "family_slate_available_but_not_selected": list(RB.FAMILIES),
        "categorical_handling_arm0": "NONE — every design matrix is df[feats].to_numpy(float); no "
                                     "categorical dtype, no one-hot, no label encoding, and no "
                                     "cat_features key in any of the 7 bundles",
        "sample_weights_arm0": "NONE — model.fit(X, y) is called without sample_weight",
        "missing_value_handling_arm0": "native NaN (LightGBM); median_impute is None in all 7 "
                                       "bundles. The median+missing-flag path exists only for the "
                                       "ElasticNet family, which no shipped bundle selected. "
                                       "Medians would be TRAIN-ONLY (_prep_median_flag computes "
                                       "them from tr).",
        "transforms_and_clipping": {
            "log_pick": "log(draft_pick.clip(lower=1)) — a rookie FEATURE transform",
            "prediction_clipping": "np.clip(pred, 0, None) is applied by _score_bundle and by the "
                                   "2026 face-validity path, but NOT by walk_forward(). The "
                                   "EVALUATION path is therefore UNCLIPPED, and this harness mirrors "
                                   "walk_forward, so it does not clip either.",
        },
        "ordered_baseline_features": {f"{p}/{b}": v["feature_cols"] for (p, b), v in a0.items()},
        "bundle_metadata": {f"{p}/{b}": {k: v[k] for k in
                                         ("bundle", "md5", "target", "seed", "n_features",
                                          "inner_cv_mae", "median_impute", "note")}
                            for (p, b), v in a0.items()},
        "code_vs_bundle_disagreements": {
            "bundle_note_text": "every bundle's `note` says 'RB season-total half-PPR projection' "
                                "even in the QB/WR/TE bundles, because the WR/TE/QB builders reuse "
                                "build_rb_projection.fit_final_model verbatim. COSMETIC: the "
                                "feature_cols, family and params are position-correct and match each "
                                "builder's own pool exactly (asserted by arm0_definition).",
            "feature_order": "bundle feature_cols == builder module pool for all 7 bundles",
        },
        "existing_baseline_coaching_features": ["coach_changed", "qb_changed"],
        "coach_changed_definition": "week-1 head coach of season Y vs week-1 head coach of Y-1 "
                                    "(build_season_dataset.py); NaN preserved, never a hard 0",
        "depth_rank": "EXCLUDED from every pool (RB prereg Amendment 1); disclosure-only",
        "production_write_paths_this_harness_must_never_touch": [
            str(MODELS), str(PROJ / "results"), str(SEAS)],
    }
    if write:
        raise RuntimeError(
            "v3.9 authorises exactly five new repo data artifacts and the production audit is not "
            "one of them. The record belongs in V39_PREFIT_STOP_REPORT.md.")
    return audit


def experiment_spec(write=False):
    spec = {
        "prereg": "preregs/PREREG_coach_quality_2026-07-28.md (v3.9 PREFIT)",
        "real_fit_authorized": REAL_FIT_AUTHORIZED,
        "outer_seasons": OUTER_SEASONS, "recent_panel": RECENT_SEASONS,
        "panel_first_season": PANEL_FIRST_SEASON,
        "inner_validation": "expanding: inner training < validation < outer target",
        "inner_min_train_seasons": INNER_MIN_TRAIN_SEASONS,
        "inner_min_validation_seasons": INNER_MIN_VALIDATION_SEASONS,
        "worked_example_outer_2018": [{"train": [2014, 2015], "validate": 2016},
                                      {"train": [2014, 2015, 2016], "validate": 2017}],
        "arms": ARMS, "fixed_diagnostic_arms": FIXED_DIAGNOSTIC_ARMS,
        "cohort_sizes": COHORT_N,
        "cohort_rule": "top-N by the ARM 0 prediction within (season, position)",
        "full_panel_tolerance_mae": FULL_PANEL_TOLERANCE,
        "min_relative_top_cohort_improvement": MIN_RELATIVE_IMPROVEMENT,
        "tie_band_mae": TIE_BAND,
        "tie_rule": "fewer added features; then the frozen arm order",
        "primary_design": AF.DESIGN_A,
        "oracle_design": AF.DESIGN_B,
        "oracle_rule": "Design B can never enter nested selection and is labelled nondeployable",
        "design_labels": AF.DESIGN_LABEL,
        "bootstrap_draws": BOOTSTRAP_DRAWS, "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_cluster_units": CLUSTER_UNITS,
        "multiplicity": "Holm across the six fixed arms (ARM_HC, ARM_1-ARM_5) within each position",
        "placebo": {"kind": "within-season TEAM-LEVEL permutation of complete coaching bundles",
                    "draws": PLACEBO_DRAWS, "seed": PLACEBO_SEED,
                    "bar": "observed improvement must beat the 95th percentile",
                    "never": "individual player rows are not shuffled"},
        "arm3_structurally_unavailable_before_target_season": 2018,
        "repo_writes": "NONE — this module writes no repo artifact at all",
        "improvement_statistic": {
            "name": IMPROVEMENT_STATISTIC,
            "definition": "MAE(ARM_0) - MAE(challenger) over ALL outer top-cohort rows POOLED; "
                          "positive = challenger better",
            "frozen_because": "prereg §7(1) says 'top-cohort MAE' without choosing pooled vs "
                              "mean-per-season; frozen POOLED before any real outcome was visible "
                              "because it matches the plain reading, matches what the clustered "
                              "bootstrap in condition (2) resamples, and leaves conditions (3)/(4) "
                              "to carry the per-season evidence instead of duplicating it",
            "used_identically_for": ["the §7(1) 3% rule", "the §7(9) permutation placebo"],
        },
        "primary_pass_rule_ten_conditions": {
            "c1_top_cohort_improves_3pct": PASS_MIN_RELATIVE_TOP_COHORT_IMPROVEMENT,
            "c2_both_clustered_ci_upper_below_zero": "ci_hi < 0 for BOTH cluster units",
            "c3_improves_6_of_8_outer_seasons": PASS_MIN_OUTER_SEASONS_IMPROVED,
            "c4_improves_4_of_5_recent_seasons": PASS_MIN_RECENT_SEASONS_IMPROVED,
            "c5_top_cohort_spearman_gain": PASS_MIN_SPEARMAN_GAIN,
            "c6_full_panel_mae_worsens_at_most": PASS_MAX_FULL_PANEL_MAE_WORSENING,
            "c7_full_panel_rmse_worsens_at_most_relative": PASS_MAX_FULL_PANEL_RMSE_WORSENING,
            "c8_nonbaseline_arm_in_at_least_folds": PASS_MIN_NONBASELINE_FOLDS,
            "c9_beats_placebo_percentile": PASS_PLACEBO_PERCENTILE,
            "c10_all_assertions_pass": "timing, leakage, coverage, artifact integrity, "
                                       "no-real-outcome",
            "scope": "the NESTED-SELECTED Design A pipeline ONLY; no fixed arm and no Design B "
                     "result can rescue a failed primary result",
        },
    }
    if write:
        raise RuntimeError(
            "v3.9 authorises exactly five new repo data artifacts and the harness spec is not one of "
            "them. The record belongs in V39_PREFIT_STOP_REPORT.md.")
    return spec


# =====================================================================================================
# FOLDS
# =====================================================================================================
def expanding_inner_folds(seasons, outer_season,
                          min_train_seasons=INNER_MIN_TRAIN_SEASONS,
                          min_validation_seasons=INNER_MIN_VALIDATION_SEASONS):
    """inner training < validation < outer target. Returns [] when the frozen minimums are unmet.

    Same shape as `stage_models.expanding_folds`, restated here with the Stage-independent minimums
    so the player-arm harness cannot silently inherit a Stage 1/2 relaxation.
    """
    hist = sorted(s for s in set(int(x) for x in seasons) if s < outer_season)
    folds = [(tuple(hist[:i]), hist[i]) for i in range(len(hist)) if i >= min_train_seasons]
    if len(folds) < min_validation_seasons:
        return []
    return folds


# =====================================================================================================
# FITTING — production engine, production hyperparameters
# =====================================================================================================
def fit_predict(spec, train, test, features):
    """Fit with the bundle's FIXED family and hyperparameters. The player model is never retuned."""
    RB, _ = _production_engine()
    Xtr, Xte = RB._prep(spec["family"], train, test, features)
    m = RB._make_model(spec["family"], spec["params"])
    m.fit(Xtr, train["y"].to_numpy(float))
    return np.asarray(m.predict(Xte), float)


def _mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def _rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def _spearman(y, p):
    from scipy.stats import spearmanr
    y, p = np.asarray(y, float), np.asarray(p, float)
    if len(y) < 3 or np.nanstd(p) == 0:
        return np.nan
    return float(spearmanr(y, p, nan_policy="omit").correlation)


# =====================================================================================================
# PANEL ASSEMBLY
# =====================================================================================================
def attach_coach_features(panel, coach, arm, position):
    """Left-join the arm's coaching features onto identical player rows.

    ARM 0 returns the panel untouched, so every arm predicts the SAME rows in the SAME order.
    A player row whose (season, team) has no coaching row would silently receive NaN, so it raises.
    """
    feats = AF.arm_features(arm, position)
    if not feats:
        return panel.copy(), []
    c = coach[["season", "team"] + feats].drop_duplicates(["season", "team"])
    n0 = len(panel)
    out = panel.merge(c, on=["season", "team"], how="left")
    assert len(out) == n0, "coaching join changed the player row count"
    miss = out[feats].isna().all(axis=1).sum()
    assert miss == 0, f"{miss} player rows have no coaching bundle for (season, team)"
    _note_assertion("coach_join_preserved_rows")
    return out, feats


# C5-A clause 5 pins the return callee BY NAME, so `assemble_panel_core` must resolve in this module.
# Importing the assembly module reads nothing: every reader there is default-closed (contract A6), and
# A1 forbids import-time I/O. The name is bound here rather than inside the door so the door's body
# stays exactly the three statements C5-A allows.
from assemble_real_panel_v39 import assemble_panel_core              # noqa: E402


def require_preflight_clearance(run_mode=RUN_MODE_AUTHORIZED_REAL, preflight_result=None,
                                models_dir=None, feature_columns=None, verify_inputs=True,
                                authorization=None):
    """EVERY activation gate, evaluated BEFORE any reader runs. Raises on the first failure.

    This is statement 2 of the implemented door (C5-A clause 2). It exists so the ordering
    "clear every gate, THEN read" is structural rather than a convention a future edit could reorder:
    the readers are arguments to statement 3, so they cannot be called until this has returned.

    In order:
      0. the run mode must be `authorized_real` — a `synthetic_prefit` run may not reach a reader;
      1. BOTH locks must be open (re-checked here, not trusted from statement 1);
      2. `preflight()` must be 21/21 IN `authorized_real` MODE;
      3. `activation_readiness()` must be True;
      4. `authorized_real_gate()` must be True — checked explicitly even though it re-derives 2 and 3,
         because the brief requires the gate itself to have run before either reader;
      5. every pinned input — veteran features, rookie matrix, weekly outcome snapshot — must match its
         hash and manifest provenance. The five coaching artifacts are covered by check 2's
         `v39_artifacts_pinned`.

    Returns the preflight result it cleared, so a caller cannot re-derive a different one.
    """
    import assemble_real_panel_v39 as _arp
    if run_mode != RUN_MODE_AUTHORIZED_REAL:
        raise RuntimeError(f"clearance refused: run mode is {run_mode!r}; a real panel may be "
                           f"assembled only in {RUN_MODE_AUTHORIZED_REAL!r}")
    if not real_fit_is_unlocked(authorization):
        raise RuntimeError(REAL_FIT_MESSAGE)

    pf = preflight(run_mode=RUN_MODE_AUTHORIZED_REAL, authorization=authorization) \
        if preflight_result is None else preflight_result
    ready, ready_detail = _arp.activation_readiness(models_dir=models_dir,
                                                    feature_columns=feature_columns)
    if not ready:
        raise RuntimeError(f"clearance refused: activation_readiness() is False — {ready_detail}")

    gate_ok, gate_detail = _arp.authorized_real_gate(pf, models_dir=models_dir,
                                                     feature_columns=feature_columns)
    if not gate_ok:
        raise RuntimeError(f"clearance refused: {gate_detail}")

    if verify_inputs:
        _arp.verify_pinned_activation_inputs()
    return pf


def assemble_real_panel(feature_reader, outcome_reader, authorization=None,
                        run_mode=RUN_MODE_AUTHORIZED_REAL, models_dir=None, feature_columns=None):
    """The ONLY door to a real fantasy outcome. Implemented, and default-closed behind both locks.

    Readers are INJECTED (C5-A clause 3): this function contains no reader callee, so the module
    physically cannot read a file by itself. With the locks shut, statement 1 raises and neither
    injected reader is ever called — that is the complete prohibition, preserved, and a test asserts
    it with tripwire readers.

    Build the real readers with `assemble_real_panel_v39.authorized_feature_reader()` and
    `.authorized_outcome_reader()`; both verify their own pins before returning a row.
    """
    require_real_fit_authorization(authorization)
    require_preflight_clearance(run_mode, None, models_dir, feature_columns, True, authorization)
    return assemble_panel_core(feature_reader(), outcome_reader())


def synthetic_panel(seasons=range(PANEL_FIRST_SEASON, 2026), seed=7, players_per_team=3,
                    teams=None, positions=None):
    """SYNTHETIC player panel with a SYNTHETIC target.

    Carries the production baseline feature NAMES so the harness exercises the real column contract,
    but every value and the target are generated. Nothing here is a fantasy outcome.
    """
    rng = np.random.default_rng(seed)
    all_teams = sorted(pd.read_csv(DATA / "team_coach_features_design_a_v39.csv").team.unique())
    teams = all_teams if teams is None else list(teams)
    pools = builder_pools()
    rows = []
    for pos in (positions or POSITIONS):
        for bucket in BUCKETS:
            if (pos, bucket) in MISSING_BUNDLES:
                continue
            feats = pools[(pos, bucket)]
            for s in seasons:
                for t in teams:
                    for k in range(players_per_team):
                        r = dict(player_id=f"{pos}_{bucket}_{t}_{k}", player=f"{pos} {t} {k}",
                                 season=int(s), team=t, position=pos,
                                 is_rookie=int(bucket == "rookie"), bucket=bucket)
                        for c in feats:
                            r[c] = float(rng.normal())
                        r["y"] = float(60 + 8 * r[feats[0]] + 4 * r[feats[1]] + rng.normal(0, 12))
                        rows.append(r)
    return pd.DataFrame(rows)


# =====================================================================================================
# COHORTS AND METRICS
# =====================================================================================================
def baseline_cohort_mask(frame, arm0_pred_col="pred_ARM_0"):
    """Top-N by the ARM 0 prediction within (season, position). Cohorts are BASELINE-DEFINED, so an
    arm can never reshape the cohort it is scored on."""
    mask = np.zeros(len(frame), dtype=bool)
    for (s, pos), g in frame.groupby(["season", "position"]):
        n = COHORT_N[pos]
        idx = g[arm0_pred_col].astype(float).nlargest(min(n, len(g)),
                                                      keep="first").index
        mask[frame.index.get_indexer(idx)] = True
    return mask


# =====================================================================================================
# THE FROZEN IMPROVEMENT STATISTIC (v3.9 §9a — frozen here because the prereg was ambiguous)
# =====================================================================================================
# §7 condition 1 says "improves top-cohort MAE by >= 3%" without stating whether that is POOLED over
# all outer rows or the MEAN of per-season top-cohort MAEs. Frozen now, before any real outcome is
# visible, as **POOLED over all outer rows**, because:
#   - it is the plain reading of "top-cohort MAE";
#   - it is the same quantity the clustered bootstrap resamples (condition 2), so conditions 1 and 2
#     cannot disagree about what is being estimated;
#   - per-season behaviour is already covered separately by conditions 3 and 4, so a per-season mean
#     headline would duplicate them and leave the pooled effect unmeasured.
# The SAME function computes the observed statistic and every placebo draw.
IMPROVEMENT_STATISTIC = "pooled_top_cohort_mae_reduction"

# Frozen §7 primary pass thresholds.
PASS_MIN_RELATIVE_TOP_COHORT_IMPROVEMENT = 0.03      # (1)
PASS_MIN_OUTER_SEASONS_IMPROVED = 6                  # (3) of 8
PASS_MIN_RECENT_SEASONS_IMPROVED = 4                 # (4) of 5
PASS_MIN_SPEARMAN_GAIN = 0.005                       # (5)
PASS_MAX_FULL_PANEL_MAE_WORSENING = 0.25             # (6)
PASS_MAX_FULL_PANEL_RMSE_WORSENING = 0.01            # (7)
PASS_MIN_NONBASELINE_FOLDS = 4                       # (8) of 8
PASS_PLACEBO_PERCENTILE = 95                         # (9)


def top_cohort_improvement(frame, challenger_col="pred_selected", base_col="pred_ARM_0",
                           cohort_col="in_cohort"):
    """POOLED top-cohort MAE reduction: ARM_0 MAE minus challenger MAE. Positive = challenger better.

    Cohort membership comes from ARM_0, which carries no coaching feature, so it is invariant under the
    permutation placebo — the observed statistic and every placebo draw are scored on the SAME rows.
    """
    sub = frame[frame[cohort_col].astype(bool)]
    if not len(sub):
        return np.nan
    return _mae(sub["y"], sub[base_col]) - _mae(sub["y"], sub[challenger_col])


def relative_top_cohort_improvement(frame, challenger_col="pred_selected",
                                    base_col="pred_ARM_0", cohort_col="in_cohort"):
    sub = frame[frame[cohort_col].astype(bool)]
    if not len(sub):
        return np.nan
    base = _mae(sub["y"], sub[base_col])
    return np.nan if base == 0 else top_cohort_improvement(
        frame, challenger_col, base_col, cohort_col) / base


def metric_block(frame, pred_col, label):
    y = frame["y"].to_numpy(float)
    p = frame[pred_col].to_numpy(float)
    rho = [ _spearman(g["y"], g[pred_col]) for _s, g in frame.groupby("season") ]
    return dict(label=label, n=len(frame), MAE=_mae(y, p), RMSE=_rmse(y, p),
                mean_bias=float(np.mean(p - y)), median_bias=float(np.median(p - y)),
                mean_within_season_spearman=float(np.nanmean(rho)) if rho else np.nan)


# =====================================================================================================
# NESTED SELECTION
# =====================================================================================================
def inner_scores(panel, coach, position, outer_season, arm0, verbose=False):
    """Per arm: mean inner-validation full-panel MAE and top-cohort MAE, over expanding folds."""
    folds = expanding_inner_folds(panel.season.unique(), outer_season)
    if not folds:
        return None, folds
    acc = {a: dict(full=[], top=[]) for a in ARMS}
    for train_seasons, val_season in folds:
        assert max(train_seasons) < val_season < outer_season, "inner fold timing violated"
        _note_assertion("inner_fold_timing")
        preds = {}
        row_key = None
        for arm in ARMS:
            parts = []
            for bucket in BUCKETS:
                if (position, bucket) in MISSING_BUNDLES:
                    continue
                spec = arm0[(position, bucket)]
                sub = panel[(panel.position == position) & (panel.bucket == bucket)]
                joined, cf = attach_coach_features(sub, coach, arm, position)
                feats = spec["feature_cols"] + cf
                tr = joined[joined.season.isin(train_seasons)].dropna(subset=["y"])
                va = joined[joined.season == val_season].dropna(subset=["y"])
                if not len(tr) or not len(va):
                    continue
                p = fit_predict(spec, tr, va, feats)
                parts.append(va[["player_id", "season", "team", "position", "y"]].assign(pred=p))
            if not parts:
                continue
            f = pd.concat(parts, ignore_index=True).sort_values(
                ["player_id"], kind="mergesort").reset_index(drop=True)
            key = tuple(zip(f.player_id, f.season))
            if row_key is None:
                row_key = key
            assert key == row_key, f"arm {arm} predicted a different row set in fold {val_season}"
            _note_assertion("identical_rows_across_arms")
            preds[arm] = f
        if not preds:
            continue
        base = preds["ARM_0"].rename(columns={"pred": "pred_ARM_0"})
        cmask = baseline_cohort_mask(base)
        for arm, f in preds.items():
            acc[arm]["full"].append(_mae(f.y, f.pred))
            acc[arm]["top"].append(_mae(f.y[cmask], f.pred[cmask]))
    out = {}
    for arm in ARMS:
        if acc[arm]["full"]:
            out[arm] = dict(inner_full_mae=float(np.mean(acc[arm]["full"])),
                            inner_top_mae=float(np.mean(acc[arm]["top"])),
                            n_added_features=len(AF.arm_features(arm, position)))
    if verbose:
        for a in ARMS:
            if a in out:
                print(f"      {a:7s} full {out[a]['inner_full_mae']:7.3f} "
                      f"top {out[a]['inner_top_mae']:7.3f} (+{out[a]['n_added_features']} feats)")
    return out, folds


def select_arm(scores):
    """Frozen selection rule. Returns (arm, reason, table)."""
    base = scores["ARM_0"]
    eligible = []
    for arm, s in scores.items():
        if arm == "ARM_0":
            continue
        ok = (s["inner_full_mae"] - base["inner_full_mae"]) <= FULL_PANEL_TOLERANCE
        s["eligible"] = bool(ok)
        s["full_panel_delta"] = s["inner_full_mae"] - base["inner_full_mae"]
        s["top_cohort_delta"] = s["inner_top_mae"] - base["inner_top_mae"]
        s["relative_improvement"] = (base["inner_top_mae"] - s["inner_top_mae"]) / base["inner_top_mae"]
        if ok:
            eligible.append(arm)
    if not eligible:
        return "ARM_0", "no coaching arm cleared the 0.25 full-panel MAE tolerance", scores
    best = min(eligible, key=lambda a: (scores[a]["inner_top_mae"], ARMS.index(a)))
    if scores[best]["relative_improvement"] < MIN_RELATIVE_IMPROVEMENT:
        return "ARM_0", (f"best eligible arm {best} improved top-cohort MAE by "
                        f"{100*scores[best]['relative_improvement']:.2f}% < 1%"), scores
    band = [a for a in eligible
            if scores[a]["inner_top_mae"] - scores[best]["inner_top_mae"] <= TIE_BAND]
    pick = min(band, key=lambda a: (scores[a]["n_added_features"], ARMS.index(a)))
    reason = (f"{pick} selected: top-cohort MAE within {TIE_BAND} of the best ({best}) with the "
              f"fewest added features" if pick != best
              else f"{pick} selected: best eligible top-cohort MAE")
    return pick, reason, scores


# =====================================================================================================
# OUTER EVALUATION
# =====================================================================================================
def outer_predictions(panel, coach, position, outer_season, arm0, arms=ARMS):
    """Fit on ALL seasons < outer_season, predict outer_season. Identical rows across arms."""
    frames, row_key = {}, None
    for arm in arms:
        parts = []
        for bucket in BUCKETS:
            if (position, bucket) in MISSING_BUNDLES:
                continue
            spec = arm0[(position, bucket)]
            sub = panel[(panel.position == position) & (panel.bucket == bucket)]
            joined, cf = attach_coach_features(sub, coach, arm, position)
            feats = spec["feature_cols"] + cf
            tr = joined[joined.season < outer_season].dropna(subset=["y"])
            te = joined[joined.season == outer_season].dropna(subset=["y"])
            if not len(tr) or not len(te):
                continue
            assert (tr.season < outer_season).all(), "outer fit touched its own test season"
            _note_assertion("outer_no_self_train")
            p = fit_predict(spec, tr, te, feats)
            parts.append(te[["player_id", "season", "team", "position", "y"]].assign(pred=p))
        if not parts:
            continue
        f = pd.concat(parts, ignore_index=True).sort_values(
            ["player_id"], kind="mergesort").reset_index(drop=True)
        key = tuple(zip(f.player_id, f.season))
        if row_key is None:
            row_key = key
        assert key == row_key, f"arm {arm} predicted a different outer row set ({outer_season})"
        frames[arm] = f
    return frames


def clustered_bootstrap(frame, sel_col, base_col, unit, draws=BOOTSTRAP_DRAWS,
                        seed=BOOTSTRAP_SEED):
    """Cluster bootstrap of the paired top-cohort MAE difference (selected - ARM 0).

    Resampling units are whole clusters -- all rows of a player, or all rows of a team-season --
    never individual rows, because coaching features are shared within a team-season and player rows
    repeat across seasons.
    """
    keys = frame[unit].astype(str).agg("|".join, axis=1).to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    e_sel = np.abs(frame[sel_col].to_numpy(float) - frame["y"].to_numpy(float))
    e_base = np.abs(frame[base_col].to_numpy(float) - frame["y"].to_numpy(float))
    # Per-cluster sums make a resampled MAE exact without materialising row indices:
    # mean(|e| over resampled rows) = sum(cluster sums of the drawn clusters) / sum(their counts).
    # Concatenating row indices for every draw was correct but O(rows) per draw and far too slow
    # at the frozen 20,000 draws across every arm, cluster unit and position.
    n = len(uniq)
    sel_sum = np.bincount(inv, weights=e_sel, minlength=n)
    base_sum = np.bincount(inv, weights=e_base, minlength=n)
    cnt = np.bincount(inv, minlength=n).astype(float)
    rng = np.random.default_rng(seed)
    obs = float(e_sel.mean() - e_base.mean())
    diffs = np.empty(draws)
    for b in range(draws):
        pick = rng.integers(0, n, n)
        diffs[b] = (sel_sum[pick].sum() - base_sum[pick].sum()) / cnt[pick].sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = 2.0 * min((diffs >= 0).mean(), (diffs <= 0).mean())
    return dict(unit="+".join(unit), observed_diff=obs, ci_lo=float(lo), ci_hi=float(hi),
                p_value=float(min(1.0, max(p, 1.0 / draws))), draws=draws, n_clusters=n)


def holm(pvals):
    """Holm-Bonferroni across the six fixed arms within a position."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def permute_team_bundles(coach, seed):
    """Within EACH season, permute complete team coaching bundles among that season's teams.

    Whole bundles move together and player rows are never touched, so the null preserves both the
    joint structure of the features and each season's composition.
    """
    rng = np.random.default_rng(seed)
    parts = []
    for s, g in coach.groupby("season"):
        g = g.sort_values("team").reset_index(drop=True)
        perm = rng.permutation(len(g))
        moved = g.iloc[perm].reset_index(drop=True)
        moved["season"] = s
        moved["team"] = g["team"].values          # bundle rows reassigned to different teams
        parts.append(moved)
    return pd.concat(parts, ignore_index=True)


def nested_selected_outer_frame(panel, coach, position, outer_seasons, arm0, verbose=False):
    """Run the FULL nested pipeline; return (outer frame, {outer_season: selected arm}).

    One call = expanding inner representation selection per outer fold, a fit on all prior seasons with
    that fold's selected representation, and a prediction on the outer season. The §7 verdict and the
    placebo both score this object, so the observed statistic and the null come from one code path.
    """
    merged, picks = [], {}
    for Y in outer_seasons:
        scores, _folds = inner_scores(panel, coach, position, Y, arm0, verbose=False)
        if scores is None:
            if verbose:
                print(f"  {position} {Y}: SKIPPED (frozen inner minimums not met)")
            continue
        pick, _reason, _table = select_arm(scores)
        need = ["ARM_0"] if pick == "ARM_0" else ["ARM_0", pick]
        fr = outer_predictions(panel, coach, position, Y, arm0, arms=need)
        if "ARM_0" not in fr:
            continue
        row = fr["ARM_0"].rename(columns={"pred": "pred_ARM_0"}).copy()
        row["pred_selected"] = (row["pred_ARM_0"].to_numpy(float) if pick == "ARM_0"
                                else fr[pick]["pred"].to_numpy(float))
        row["selected_arm"] = pick
        merged.append(row)
        picks[Y] = pick
    if not merged:
        return None, {}
    m = pd.concat(merged, ignore_index=True)
    m["in_cohort"] = baseline_cohort_mask(m)
    return m, picks


def placebo_distribution(panel, coach, position, outer_seasons, arm0, draws=PLACEBO_DRAWS,
                         seed=PLACEBO_SEED, verbose=False):
    """The frozen §7(9) null: the NESTED-SELECTED pipeline under permuted team bundles.

    The earlier implementation permuted bundles and then scored ONE fixed arm — the modal selection.
    That is not the pre-registered condition, which is about the nested-selected pipeline. Every draw
    now reruns representation selection independently for every outer fold on the permuted features and
    may select a DIFFERENT arm in each fold, exactly as the observed pipeline does.

    ARM_0 carries no coaching feature, so its predictions — and therefore cohort membership — are
    INVARIANT under permutation. The observed statistic and every draw are scored on identical rows,
    with an identical cohort definition and the identical pooled MAE-difference definition.

    COMPUTE COST, stated plainly: one draw is a full nested run over every outer fold, so at the frozen
    200 draws this is by far the most expensive step in the experiment. `draws` is the test-only lever.
    """
    vals, fold_picks = [], []
    for d in range(draws):
        pc = permute_team_bundles(coach, seed + d)
        m, picks = nested_selected_outer_frame(panel, pc, position, outer_seasons, arm0)
        if m is None:
            continue
        vals.append(float(top_cohort_improvement(m)))
        fold_picks.append(picks)
        if verbose and (d + 1) % 25 == 0:
            print(f"      placebo {d + 1}/{draws}")
    return np.array(vals), fold_picks


# =====================================================================================================
# DRIVER
# =====================================================================================================
def assert_no_implicit_row_loss(panel):
    """The panel must already satisfy the eligibility invariant, so no row can be lost implicitly.

    There are exactly two implicit-loss mechanisms in this pipeline: a null `team`, which makes
    `attach_coach_features` refuse, and a (position, bucket) with no shipped bundle, which the bucket
    loop SKIPS silently. If neither can occur on arrival, neither can shrink the population later.
    Applied identically to ARM_0 and every coaching arm, because it is a property of the panel.
    """
    if "team" in panel.columns:
        n_null = int(panel["team"].isna().sum())
        assert not n_null, (f"{n_null} panel row(s) have a null team; coaching exposure is undefined "
                            f"for them and they must be excluded BEFORE the run, not silently here")
    if "bucket" in panel.columns and "position" in panel.columns:
        shipped = {(p, b) for p, b in BUNDLE_FILE}
        bad = sorted({(p, b) for p, b in zip(panel["position"], panel["bucket"])
                      if (p, b) not in shipped})
        assert not bad, (f"panel carries (position, bucket) with no shipped bundle: {bad}; the bucket "
                         f"loop would skip them silently")
    return True


def run_experiment(panel, coach_a, coach_b=None, outer_seasons=OUTER_SEASONS, positions=POSITIONS,
                   bootstrap_draws=BOOTSTRAP_DRAWS, placebo_draws=PLACEBO_DRAWS,
                   run_placebo=True, verbose=True, run_mode=DEFAULT_RUN_MODE, authorization=None):
    """Full nested pipeline. Target-agnostic: it never inspects where `panel['y']` came from.

    `run_mode` governs ONLY the real-fit lock expectation (§3). It never relaxes an artifact, timing,
    leakage, coverage or feature-policy check.
    """
    ok, detail = validate_run_mode(run_mode, authorization=authorization)
    assert ok, f"invalid run mode: {detail}"
    assert_no_implicit_row_loss(panel)
    reset_pipeline_assertions()
    arm0 = arm0_definition()
    sel_rows, metric_rows, boot_rows = [], [], []
    placebo_rows, oracle_rows, verdict_rows, preflight_rows = [], [], [], []

    for pos in positions:
        outer_frames, fold_picks = {}, {}
        for Y in outer_seasons:
            scores, folds = inner_scores(panel, coach_a, pos, Y, arm0, verbose=verbose)
            if scores is None:
                if verbose:
                    print(f"  {pos} {Y}: SKIPPED (frozen inner minimums not met)")
                continue
            pick, reason, table = select_arm(scores)
            sel_rows.append(dict(position=pos, outer_season=Y, selected_arm=pick, reason=reason,
                                 n_inner_folds=len(folds),
                                 inner_folds=";".join(f"{list(t)}->{v}" for t, v in folds),
                                 **{f"inner_top_{a}": table[a]["inner_top_mae"]
                                    for a in table},
                                 **{f"inner_full_{a}": table[a]["inner_full_mae"]
                                    for a in table}))
            fr = outer_predictions(panel, coach_a, pos, Y, arm0)
            outer_frames[Y] = (fr, pick)
            fold_picks[Y] = pick
            if verbose:
                print(f"  {pos} {Y}: selected {pick} — {reason}")

        if not outer_frames:
            continue
        merged = []
        for Y, (fr, pick) in outer_frames.items():
            base = fr["ARM_0"].rename(columns={"pred": "pred_ARM_0"})
            row = base.copy()
            for arm, f in fr.items():
                row[f"pred_{arm}"] = f["pred"].to_numpy(float)
            row["pred_selected"] = row[f"pred_{pick}"]
            row["selected_arm"] = pick
            merged.append(row)
        m = pd.concat(merged, ignore_index=True)
        m["in_cohort"] = baseline_cohort_mask(m)

        for scope, sub in (("full_2018_2025", m),
                           ("top_cohort_2018_2025", m[m.in_cohort]),
                           ("full_recent_2021_2025", m[m.season.isin(RECENT_SEASONS)]),
                           ("top_cohort_recent_2021_2025",
                            m[m.in_cohort & m.season.isin(RECENT_SEASONS)])):
            if not len(sub):
                continue
            for arm in ["ARM_0", "selected"] + FIXED_DIAGNOSTIC_ARMS:
                col = f"pred_{arm}"
                if col not in sub.columns:
                    continue
                metric_rows.append(dict(position=pos, scope=scope, arm=arm, design=AF.DESIGN_A,
                                        **metric_block(sub, col, arm)))

        cohort = m[m.in_cohort].reset_index(drop=True)
        for unit_name, unit in CLUSTER_UNITS.items():
            boot_rows.append(dict(position=pos, arm="selected", design=AF.DESIGN_A,
                                  cluster=unit_name,
                                  **clustered_bootstrap(cohort, "pred_selected", "pred_ARM_0",
                                                        unit, draws=bootstrap_draws)))
        raw_p = {}
        for arm in FIXED_DIAGNOSTIC_ARMS:
            col = f"pred_{arm}"
            if col not in cohort.columns:
                continue
            per_unit = {}
            for unit_name, unit in CLUSTER_UNITS.items():
                r = clustered_bootstrap(cohort, col, "pred_ARM_0", unit, draws=bootstrap_draws)
                per_unit[unit_name] = r
                boot_rows.append(dict(position=pos, arm=arm, design=AF.DESIGN_A,
                                      cluster=unit_name, **r))
            raw_p[arm] = max(v["p_value"] for v in per_unit.values())
        adj = holm(raw_p)
        for arm, p in raw_p.items():
            boot_rows.append(dict(position=pos, arm=arm, design=AF.DESIGN_A, cluster="holm",
                                  unit="holm", observed_diff=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                                  p_value=p, draws=bootstrap_draws, n_clusters=np.nan,
                                  holm_adjusted_p=adj[arm]))

        # ---- placebo: the NESTED-SELECTED pipeline under permuted bundles, not a modal fixed arm ----
        obs_stat = float(top_cohort_improvement(m))
        placebo = dict(observed=obs_stat, p95=np.nan, draws=0)
        if run_placebo:
            dist, draw_picks = placebo_distribution(panel, coach_a, pos, outer_seasons, arm0,
                                                    draws=placebo_draws, verbose=verbose)
            if len(dist):
                placebo = dict(observed=obs_stat, p95=float(np.percentile(dist, 95)),
                               draws=int(len(dist)))
            n_multi = sum(1 for p in draw_picks if len(set(p.values())) > 1)
            placebo_rows.append(dict(
                position=pos, design=AF.DESIGN_A, challenger="nested_selected_design_a",
                improvement_statistic=IMPROVEMENT_STATISTIC,
                observed_improvement=obs_stat, draws=int(len(dist)),
                p95=placebo["p95"],
                beats_p95=bool(len(dist) and obs_stat > np.percentile(dist, 95)),
                draws_with_fold_specific_selection=n_multi,
                observed_fold_selections=";".join(f"{k}:{v}" for k, v in sorted(fold_picks.items()))))

        # ---- the frozen ten-condition §7 verdict, on the nested-selected Design A pipeline only ----
        sel_boot = {u: clustered_bootstrap(cohort, "pred_selected", "pred_ARM_0", unit,
                                           draws=bootstrap_draws)
                    for u, unit in CLUSTER_UNITS.items()}
        integrity_ok, integrity_detail, pf = _integrity_check(run_mode=run_mode)
        preflight_rows.append(dict(position=pos, run_mode=run_mode, all_ok=pf["all_ok"],
                                   n_checks=pf["n_checks"], n_failed=pf["n_failed"],
                                   **{f"chk_{k}": v["ok"] for k, v in pf["checks"].items()},
                                   **{f"why_{k}": v["detail"]
                                      for k, v in pf["checks"].items() if not v["ok"]}))
        verdict_rows.append(primary_verdict(
            pos, m, sel_boot, placebo, fold_picks,
            integrity_ok=integrity_ok, integrity_detail=integrity_detail,
            outer_seasons=outer_seasons))

        if coach_b is not None:
            for Y in outer_seasons:
                fr = outer_predictions(panel, coach_b, pos, Y, arm0)
                if "ARM_0" not in fr:
                    continue
                base = fr["ARM_0"].rename(columns={"pred": "pred_ARM_0"})
                cm = baseline_cohort_mask(base)
                for arm, f in fr.items():
                    oracle_rows.append(dict(
                        position=pos, outer_season=Y, arm=arm, design=AF.DESIGN_B,
                        label=AF.DESIGN_LABEL[AF.DESIGN_B],
                        top_cohort_mae=_mae(f.y[cm], f.pred[cm]),
                        full_panel_mae=_mae(f.y, f.pred)))

    return dict(selection=pd.DataFrame(sel_rows), metrics=pd.DataFrame(metric_rows),
                bootstrap=pd.DataFrame(boot_rows), placebo=pd.DataFrame(placebo_rows),
                oracle=pd.DataFrame(oracle_rows), verdict=pd.DataFrame(verdict_rows),
                preflight=pd.DataFrame(preflight_rows))


# =====================================================================================================
# THE NO-REAL-OUTCOME BOUNDARY, AS PRODUCTION LOGIC (v3.9c §5)
# =====================================================================================================
# C10 claims to include the no-real-outcome/access-boundary assertions, but v3.9b implemented them only
# as tests — so the runtime guarantee did not exist and the test could drift into a parallel definition.
# The validation now lives HERE and the tests call it, so there is one definition.
V39_SOURCE_MODULES = ("build_arm_features_v39.py", "run_coach_projection_experiment_v39.py")
BANNED_OUTCOME_CALLEES = frozenset({"load_player_stats", "season_total_target", "load_pbp",
                                    "assemble", "do_assemble", "walk_forward", "fit_final_model",
                                    "fit_full_and_score", "_score_bundle"})
BANNED_OUTCOME_TOKENS = ("season_dataset_2014_2026.csv", "season_dataset_2014_2025.csv",
                         "season_dataset_2002_2025.csv", "sleeper_pts_half_ppr", "target_ppg",
                         "target_games", "half_ppr")
READER_CALLEES = frozenset({"read_csv", "read_parquet", "read_json", "open"})

# --- v3.9d §1: the two FROZEN exemptions to the blanket string rule -----------------------------
# v3.9c inspected only direct literal reader arguments and literal subscripts, so the ordinary
# repository form `pd.read_csv(DATA / "season_dataset_2014_2026.csv")` — a BinOp, not a Constant
# argument — passed. Nine injections passed, not one. The rule is now: a banned token in ANY
# executable string constant is a violation, wherever it sits. That is only adoptable because
# canonical source has exactly two places where such tokens legitimately appear, and both are
# enumerated here rather than pattern-matched.
#
# E1 — the validator's own token list. Exempt ONLY a module-level assignment whose single target is
#      literally this name; nothing else in the module gets the exemption.
TOKEN_LIST_NAMES = frozenset({"BANNED_OUTCOME_TOKENS"})
# E2 — `audit_production()` is a read-only descriptive record of the PRODUCTION training pipeline;
#      it necessarily names the real panel files and legacy targets. It is documentation that happens
#      to be a dict rather than a docstring. The exemption is NOT "trust this function": it is void
#      unless the function's callee set is a subset of the frozen allowlist below, so introducing ANY
#      new call into it — a reader, a loader, anything — revokes the exemption and every token inside
#      is reported. Measured 2026-07-29: audit_production calls exactly these six.
DOCUMENTATION_ONLY_FUNCTIONS = ("audit_production",)
AUDIT_ALLOWED_CALLEES = frozenset({"RuntimeError", "_production_engine", "arm0_definition",
                                   "items", "list", "str"})

# Executable forms that could write the environment lock. Enumerated, not inferred.
ENV_NAMES = frozenset({"environ"})
ENV_MODULE = "os"
# `match` statements are 3.10+; the AST classes are absent on older interpreters.
_MatchAs = getattr(ast, "MatchAs", None)
_MatchStar = getattr(ast, "MatchStar", None)
_MatchMapping = getattr(ast, "MatchMapping", None)
ENV_WRITE_METHODS = frozenset({"update", "setdefault", "pop", "clear", "popitem", "__setitem__",
                               "__delitem__"})
ENV_WRITE_FUNCTIONS = frozenset({"putenv", "unsetenv"})
LOCK_NAME = "REAL_FIT_AUTHORIZED"
ENTRY_POINT_NAME = "assemble_real_panel"

# The ONE wording for a satisfied boundary. The prereg, requirement matrix, stop report, the
# `no_real_outcome_access` docstring and the C10 preflight row all quote this same phrase, so the
# contract cannot be described one way in a document and a different way in the result it produces.
#
# The canonical spelling uses an ASCII hyphen, never an en dash: v3.9d claimed "one wording everywhere"
# while the runtime printed `C1-C7` and every document wrote `C1–C7` — visually identical, never equal.
# The detail below is a PLAIN LITERAL, not an f-string, so these exact bytes appear in this source file
# and `test_the_exact_success_detail_appears_verbatim_in_every_document` can check the module too.
NO_OUTCOME_CONTRACT_NAME = "C1-C7 + C4b"
NO_OUTCOME_OK_DETAIL = (
    "both v3.9 modules satisfy the frozen structural no-outcome contract C1-C7 + C4b (scope, "
    "executable-only, no banned callee, no banned token in any executable string, no reading through "
    "an exemption, sealed entry point, single False lock, no environment write)")


def _executable_tree(src):
    """Parse and strip every docstring, so DOCUMENTING the boundary is not mistaken for crossing it."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:]
    return tree


def _callee_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _exempt_string_nodes(tree):
    """Ids of the string Constants covered by the two frozen exemptions E1/E2.

    Returns (exempt_ids, problems). E2 is void — and contributes a problem — when the documentation
    function's callee set escapes `AUDIT_ALLOWED_CALLEES`, so the exemption cannot be used as a
    hiding place. Everything not in the returned set is subject to the blanket rule.
    """
    exempt, problems = set(), []

    # E1: the module-level `BANNED_OUTCOME_TOKENS = (...)` assignment, and nothing else.
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in TOKEN_LIST_NAMES):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    exempt.add(id(sub))

    # E2: documentation-only functions, but only while their callee set stays inside the allowlist.
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in DOCUMENTATION_ONLY_FUNCTIONS):
            callees = {_callee_name(c) for c in ast.walk(node) if isinstance(c, ast.Call)}
            escaped = {c for c in callees if c not in AUDIT_ALLOWED_CALLEES}
            if escaped:
                problems.append(f"{node.name}() is documentation-exempt but now calls "
                                f"{sorted(escaped)} — exemption VOID, tokens inside are live")
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    exempt.add(id(sub))
    return exempt, problems


def _exemption_laundering(tree):
    """Reject reading THROUGH an exempt structure, which the exemptions would otherwise permit.

    E1/E2 exempt the string constants inside the token tuple and inside `audit_production()`. Nothing
    exempts *indexing* them back out: `pd.read_csv(DATA / BANNED_OUTCOME_TOKENS[0])` and
    `open(audit_production()["veteran_path"]["router"])` contain no banned string of their own. So any
    `/` composition or reader argument whose subtree touches an exempt source is a violation.
    """
    def touches_exempt_source(node):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in TOKEN_LIST_NAMES:
                return sub.id
            if isinstance(sub, ast.Call) and _callee_name(sub) in DOCUMENTATION_ONLY_FUNCTIONS:
                return _callee_name(sub) + "()"
        return None

    hits = []
    for node in ast.walk(tree):
        suspects = []
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            suspects = [node.left, node.right]
        elif isinstance(node, ast.Call) and _callee_name(node) in READER_CALLEES:
            suspects = list(node.args) + [k.value for k in node.keywords]
        for s in suspects:
            src = touches_exempt_source(s)
            if src:
                hits.append((getattr(node, "lineno", -1), src))
    return hits


def _lock_assignments(tree):
    """Every executable binding of the lock constant, as (kind, node, value, direct).

    Uses the shared binding walker, so destructuring (`(REAL_FIT_AUTHORIZED,) = (True,)`) and loop
    targets (`for REAL_FIT_AUTHORIZED in [True]:`) are bindings too — both previously invisible here.
    A destructured binding has no single inspectable value, so `direct` is False and it can never be
    the canonical one.
    """
    out = []
    for kind, node, _ln, direct in name_bindings(tree, LOCK_NAME):
        value = getattr(node, "value", None) if direct else None
        out.append((kind, node, value, direct))
    return out


def _is_env_ref(node):
    """True only for the PROCESS environment: `os.environ`, or a bare `environ`.

    v3.9d follow-up: this used to accept ANY attribute named `environ`, so an unrelated
    `config.environ = {}` was reported as opening the environment lock. The base must be the name `os`.
    The bare-`environ` case is retained deliberately — `from os import environ` is a real import form and
    the contract prefers a conservative false positive on a local of that exact name to a miss.
    """
    if isinstance(node, ast.Attribute):
        return (node.attr in ENV_NAMES
                and isinstance(node.value, ast.Name) and node.value.id == ENV_MODULE)
    if isinstance(node, ast.Name):
        return node.id in ENV_NAMES
    return False


# --- the ONE binding walker, shared by C5, C6 and C7 -------------------------------------------
# v3.9d follow-up: C5/C6/C7 each carried their own ad-hoc list of "assignment forms", and all three
# lists were incomplete in the same way — they knew about Assign/AnnAssign/AugAssign/NamedExpr/Delete
# and nothing else. Python binds names in many more places, and twelve injections walked straight
# through: tuple/list/starred destructuring, `for` targets, `with ... as`, `except ... as`, and `match`
# captures. One recursive walker now answers "what does this node bind?" for all three checks.
def _binding_target_exprs(node):
    """Yield each target EXPRESSION bound (or unbound) by this node, before destructuring."""
    if isinstance(node, ast.Assign):
        yield from node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        yield node.target
    elif isinstance(node, ast.Delete):
        yield from node.targets
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        yield node.target
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if item.optional_vars is not None:
                yield item.optional_vars
    elif isinstance(node, ast.comprehension):
        yield node.target


def _flatten_target(expr):
    """Recursively yield the LEAF targets of a (possibly destructured) assignment target."""
    if isinstance(expr, (ast.Tuple, ast.List)):
        for e in expr.elts:
            yield from _flatten_target(e)
    elif isinstance(expr, ast.Starred):
        yield from _flatten_target(expr.value)
    else:
        yield expr


def _bare_name_bindings(node):
    """Yield names bound by constructs whose target is a plain identifier, not an expression."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    elif isinstance(node, ast.ExceptHandler):
        if node.name:
            yield node.name
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for a in node.names:
            yield a.asname or a.name.split(".")[0]
    elif _MatchAs is not None:
        if isinstance(node, (_MatchAs, _MatchStar)) and getattr(node, "name", None):
            yield node.name
        elif isinstance(node, _MatchMapping) and getattr(node, "rest", None):
            yield node.rest


def name_bindings(tree, name):
    """Every executable construct in `tree` that binds or unbinds the identifier `name`.

    Returns [(kind, node, lineno, is_direct_name_target)]. `is_direct_name_target` is False when the
    name was reached through destructuring, because a destructured binding has no single value to
    inspect.
    """
    found = []
    for node in ast.walk(tree):
        for target in _binding_target_exprs(node):
            direct = isinstance(target, ast.Name)
            for leaf in _flatten_target(target):
                if isinstance(leaf, ast.Name) and leaf.id == name:
                    found.append((type(node).__name__, node, getattr(node, "lineno", -1), direct))
        for bound in _bare_name_bindings(node):
            if bound == name:
                found.append((type(node).__name__, node, getattr(node, "lineno", -1), True))
    return found


def _is_env_write_function(call):
    """True only for `os.putenv`/`os.unsetenv`, or the bare names, which stay conservatively banned.

    v3.9d follow-up 3: this used `_callee_name()`, which returns only the terminal attribute, so an
    unrelated `config.putenv(...)` was rejected as an environment write. C7 promises `os.putenv` and
    `os.unsetenv` specifically. The bare `putenv(...)` form remains banned for the same reason bare
    `environ` does — `from os import putenv` is a real import — and that choice is pinned by test.
    """
    f = call.func
    if isinstance(f, ast.Attribute):
        return (f.attr in ENV_WRITE_FUNCTIONS
                and isinstance(f.value, ast.Name) and f.value.id == ENV_MODULE)
    if isinstance(f, ast.Name):
        return f.id in ENV_WRITE_FUNCTIONS
    return False


def env_bindings(tree):
    """Every executable construct that binds, rebinds, deletes or mutates the process environment.

    v3.9d follow-up 3: this consumed `_binding_target_exprs()` but NOT `_bare_name_bindings()`, unlike
    `name_bindings()`. So `except Exception as environ`, `case environ`, `def environ`, `class environ`
    and `import pathlib as environ` all passed — contradicting both the documented binder list and the
    pinned decision that a bare `environ` counts. The identifier `environ` is reserved: bind it any way
    at all and C7 fires. Use `os.environ` if you need the real thing.
    """
    hits = []
    for node in ast.walk(tree):
        kind = type(node).__name__
        for target in _binding_target_exprs(node):
            for leaf in _flatten_target(target):
                if isinstance(leaf, ast.Subscript) and _is_env_ref(leaf.value):
                    hits.append((getattr(node, "lineno", -1), "os.environ[...] assignment"))
                elif _is_env_ref(leaf):
                    verb = "deletion" if isinstance(node, ast.Delete) else f"{kind} rebinding"
                    hits.append((getattr(node, "lineno", -1), f"os.environ {verb}"))
        for bound in _bare_name_bindings(node):
            if bound in ENV_NAMES:
                hits.append((getattr(node, "lineno", -1), f"os.environ {kind} rebinding"))
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ENV_WRITE_METHODS and _is_env_ref(f.value):
                hits.append((node.lineno, f"os.environ.{f.attr}()"))
            if _is_env_write_function(node):
                hits.append((node.lineno, f"{_callee_name(node)}()"))
    return hits


def _lock_mutations(tree):
    """Runtime writes to the lock that are not plain assignments: `globals()[...] = ` and `setattr`."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Call)
                        and getattr(tgt.value.func, "id", None) in ("globals", "vars")):
                    out.append((node.lineno, "globals()[...] assignment"))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)                     and node.args[1].value == LOCK_NAME:
                out.append((node.lineno, f"setattr(..., {LOCK_NAME!r}, ...)"))
    return out


def _entry_point_is_sealed(tree, contract_mode=None):
    """C5, MODE-AWARE. Which shape `assemble_real_panel` must have, per the prereg.

    Both variants demand the SAME structural guarantee first: `assemble_real_panel` is bound exactly
    once, at module level, by one undecorated `def`. A rebinding, a decorator or a second binding
    replaces the door, and that is refused in either mode.

      C5-S  `synthetic_prefit`  — the executable body is exactly TWO statements: a zero-argument
            `require_real_fit_authorization()`, then an unconditional `raise NotImplementedError`.
            The door does not exist yet; there is nothing to authorize.

      C5-A  `authorized_real`   — the door is IMPLEMENTED, and the seal moves from "the body raises"
            to "the body cannot reach data without clearing every gate first":
              1. statement 1 is a zero-argument `require_real_fit_authorization()`
              2. statement 2 is a call to `require_preflight_clearance(...)`
              3. NO reader callee appears anywhere in the body — readers are injected parameters
              4. NO banned outcome callee appears anywhere in the body
              5. the function returns the result of `assemble_panel_core(...)` and nothing else
              6. no statement precedes 1
            Clause 3 is what makes the implemented door safe: the module physically cannot read a
            file by itself, so with the locks shut statement 1 raises and no injected reader is ever
            called. That is the complete prohibition on real readers, preserved.

    `contract_mode` defaults to the module constant `ENTRY_POINT_CONTRACT_MODE`, so which contract
    applies is an explicit, reviewable declaration and is never inferred from the lock state — the
    lock state is the very thing the contract protects.
    """
    mode = ENTRY_POINT_CONTRACT_MODE if contract_mode is None else contract_mode
    if mode not in RUN_MODES:
        return [f"unknown entry-point contract mode {mode!r}; expected one of {list(RUN_MODES)}"]
    problems = []
    bindings = [(kind, node) for kind, node, _ln, _direct in name_bindings(tree, ENTRY_POINT_NAME)]
    if not bindings:
        return [f"{ENTRY_POINT_NAME} is missing"]
    if len(bindings) > 1:
        kinds = ", ".join(f"{k}@L{getattr(n, 'lineno', -1)}" for k, n in bindings)
        problems.append(f"{ENTRY_POINT_NAME} is bound {len(bindings)} times ({kinds}) — exactly one "
                        f"module-level def is allowed; a rebinding replaces the sealed door")

    module_level = {id(n) for n in tree.body}
    fns = [n for k, n in bindings if k == "FunctionDef"]
    if len(fns) != 1:
        problems.append(f"expected exactly one plain `def {ENTRY_POINT_NAME}`, found {len(fns)}")
        return problems
    fn = fns[0]
    if id(fn) not in module_level:
        problems.append(f"{ENTRY_POINT_NAME} is not defined at module level")
    if fn.decorator_list:
        problems.append(f"{ENTRY_POINT_NAME} is decorated — a decorator can replace the callable")

    body = fn.body                                  # docstrings already stripped by _executable_tree

    def _is_zero_arg_auth(stmt):
        """C5-S: the sealed door authorizes with no argument at all."""
        return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id == "require_real_fit_authorization"
                and not stmt.value.args and not stmt.value.keywords)

    def _is_capability_auth(stmt, fn_node):
        """C5-A: the implemented door authorizes with its OWN authorization parameter and nothing
        else — not a literal, not a global, not a call. The capability must arrive from the caller."""
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id == "require_real_fit_authorization"):
            return False
        args = stmt.value.args
        params = {a.arg for a in fn_node.args.args}
        return (len(args) == 1 and not stmt.value.keywords
                and isinstance(args[0], ast.Name) and args[0].id == AUTHORIZATION_PARAM
                and AUTHORIZATION_PARAM in params)

    if mode == RUN_MODE_SYNTHETIC_PREFIT:
        # ---- C5-S: the door does not exist yet ------------------------------------------------
        if len(body) != 2:
            kinds = ", ".join(type(s).__name__ for s in body) or "<empty>"
            problems.append(f"C5-S: {ENTRY_POINT_NAME} body must be exactly 2 statements "
                            f"(authorization, raise); found {len(body)}: {kinds}")
            return problems
        first, second = body
        if not _is_zero_arg_auth(first):
            problems.append(f"C5-S: {ENTRY_POINT_NAME} statement 1 must be a zero-argument "
                            f"require_real_fit_authorization() call")
        if not isinstance(second, ast.Raise):
            problems.append(f"C5-S: {ENTRY_POINT_NAME} statement 2 must be an unconditional raise, "
                            f"not {type(second).__name__} — an early return leaves it unreachable")
        else:
            exc = second.exc
            name = getattr(getattr(exc, "func", exc), "id", None)
            if name != "NotImplementedError":
                problems.append(f"C5-S: {ENTRY_POINT_NAME} must raise NotImplementedError, not {name}")
        return problems

    # ---- C5-A: the door is implemented, and gated before it can reach data ---------------------
    if len(body) != 3:
        kinds = ", ".join(type(s).__name__ for s in body) or "<empty>"
        problems.append(f"C5-A: {ENTRY_POINT_NAME} body must be exactly 3 statements "
                        f"(authorization, clearance, return); found {len(body)}: {kinds}")
        return problems
    first, second, third = body

    # clause 1 + clause 6 — the authorization is statement 1, so nothing precedes it, and it must
    # consume the INVOCATION-SCOPED capability rather than any ambient state
    if not _is_capability_auth(first, fn):
        problems.append(f"C5-A clause 1/6: {ENTRY_POINT_NAME} statement 1 must be "
                        f"require_real_fit_authorization({AUTHORIZATION_PARAM}) using its own "
                        f"parameter; found {type(first).__name__} — any statement before it runs "
                        f"unauthorized, and any other argument is not the caller's capability")

    # clause 2 — the clearance is statement 2
    ok_clear = (isinstance(second, ast.Expr) and isinstance(second.value, ast.Call)
                and isinstance(second.value.func, ast.Name)
                and second.value.func.id == PREFLIGHT_CLEARANCE_NAME)
    if not ok_clear:
        problems.append(f"C5-A clause 2: {ENTRY_POINT_NAME} statement 2 must call "
                        f"{PREFLIGHT_CLEARANCE_NAME}()")

    # clauses 3 + 4 — no reader, no banned outcome callee, ANYWHERE in the body
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
            node.func, "id", None)
        if callee in ENTRY_POINT_BANNED_READER_CALLEES:
            problems.append(f"C5-A clause 3: {ENTRY_POINT_NAME} calls reader {callee}() at line "
                            f"{node.lineno} — readers must be injected parameters")
        if callee in BANNED_OUTCOME_CALLEES:
            problems.append(f"C5-A clause 4: {ENTRY_POINT_NAME} calls banned outcome loader "
                            f"{callee}() at line {node.lineno}")

    # clause 5 — the last statement returns assemble_panel_core(...) and nothing else
    if not isinstance(third, ast.Return):
        problems.append(f"C5-A clause 5: {ENTRY_POINT_NAME} statement 3 must be a return, not "
                        f"{type(third).__name__}")
    elif not (isinstance(third.value, ast.Call)
              and getattr(third.value.func, "id", None) == PANEL_CORE_NAME):
        got = getattr(getattr(third.value, "func", None), "id", type(third.value).__name__)
        problems.append(f"C5-A clause 5: {ENTRY_POINT_NAME} must return {PANEL_CORE_NAME}(...), "
                        f"got {got}")
    return problems


def no_real_outcome_access(source_dir=None, sources=None, contract_mode=None):
    """Enforce the frozen structural no-real-outcome contract `C1-C7 + C4b` on both v3.9 modules.

    On success this returns exactly `NO_OUTCOME_OK_DETAIL`, whose clause list is
    "scope, executable-only, no banned callee, no banned token in any executable string,
    no reading through an exemption, sealed entry point, single False lock, no environment write".
    The contract name uses an ASCII hyphen; an en dash is a different string.

    This is NOT a theorem about arbitrary Python. It is a decidable structural contract over the
    executable AST of exactly two named modules, and it is worth stating exactly because v3.9c
    claimed more than it checked:

      C1  SCOPE. `sources` must map exactly `V39_SOURCE_MODULES` — both modules, no more, no fewer.
          A module omitted from the mapping cannot silently escape inspection, and an extra module is
          rejected rather than scanned under a contract not written for it.
      C2  EXECUTABLE ONLY. Every check runs on `ast.parse` output with module/class/function
          docstrings removed. Comments never reach the AST. Describing the boundary is not crossing
          it.
      C3  NO BANNED CALLEE. No call anywhere to a name in `BANNED_OUTCOME_CALLEES`.
      C4  NO BANNED TOKEN IN ANY EXECUTABLE STRING. A `BANNED_OUTCOME_TOKENS` substring inside ANY
          executable string constant is a violation regardless of position — reader argument,
          `Path(...)` argument, `/` path composition, a variable later handed to a reader, a member of
          a list/tuple/dict/set, a keyword argument, an f-string component, or a subscript. Exactly
          two frozen exemptions apply (E1 the validator's own token tuple, E2 documentation-only
          functions whose callee set stays inside `AUDIT_ALLOWED_CALLEES`); E2 voids itself the moment
          a new call appears inside it.
      C4b NO READING THROUGH AN EXEMPTION. Neither exempt structure may act as a data source: a `/`
          composition or a reader argument whose subtree references `BANNED_OUTCOME_TOKENS` or calls a
          documentation-only function is a violation, since indexing a token back out would otherwise
          launder it past C4.
      C5  ENTRY POINT SEALED. `assemble_real_panel` is bound EXACTLY ONCE across the whole module, by
          one undecorated module-level `def` — no second definition, assignment, lambda, import alias,
          deletion, augmented assignment or named-expression may rebind it. With its docstring
          stripped, its executable body is EXACTLY two statements: a zero-argument
          `require_real_fit_authorization()`, then an unconditional `raise NotImplementedError(...)`.
          An early `return` above an unreachable raise fails, as does a raise made dormant by a
          conditional, because the body must be those two statements and nothing else.
      C6  LOCK INVARIANTS. Across `Assign`, `AnnAssign`, `AugAssign` and `NamedExpr`: exactly one
          assignment to `REAL_FIT_AUTHORIZED` exists across both modules, it is module-level, it is in
          the harness, and its value is the constant `False`. Any other form or value fails.
      C7  NO ENVIRONMENT WRITE. Nothing may write, rebind or delete the process environment:
          no `os.environ[...]` assignment or deletion; no `os.environ` bound by ANY of the binding
          contexts C5 uses (assignment in every form, destructuring, `for`, `with ... as`,
          `except ... as`, `match` capture, `def`/`class`, import alias);
          no `os.environ.{update,setdefault,pop,clear,popitem,__setitem__,__delitem__}()`; and no
          `os.putenv`/`os.unsetenv`. The receiver matters: `config.environ` and `config.putenv()` are
          NOT the process environment and are allowed. The bare identifiers `environ`, `putenv` and
          `unsetenv` ARE banned, conservatively and deliberately, because `from os import environ` is a
          real import form; use `os.environ` if you need the real object.

    What it deliberately does NOT claim: it does not resolve aliases, dynamic attribute access,
    `getattr`/`eval`/`exec`, imports of third-party code, or a token assembled at runtime from
    fragments. It is a structural gate against the realistic accident and the realistic edit, not a
    proof of runtime behaviour. `source_dir`/`sources` let a regression test inject source without
    touching canonical files. Returns (ok, detail).
    """
    if sources is None:
        base = HERE if source_dir is None else pathlib.Path(source_dir)
        sources = {}
        for m in V39_SOURCE_MODULES:
            p = base / m
            if not p.exists():
                return False, f"{m} not found under {base}"
            sources[m] = p.read_text(encoding="utf-8")

    problems = []

    # C1 — scope. Exact set equality, so neither omission nor addition passes unnoticed.
    supplied, required = set(sources), set(V39_SOURCE_MODULES)
    if supplied != required:
        missing, extra = sorted(required - supplied), sorted(supplied - required)
        bits = []
        if missing:
            bits.append(f"missing {missing}")
        if extra:
            bits.append(f"unexpected {extra}")
        return False, ("sources must be exactly the two v3.9 modules: " + "; ".join(bits))

    lock_assigns = []
    for mod, src in sorted(sources.items()):
        try:
            tree = _executable_tree(src)                                   # C2
        except SyntaxError as e:
            problems.append(f"{mod}: unparseable ({e})")
            continue

        exempt, exempt_problems = _exempt_string_nodes(tree)
        problems.extend(f"{mod}: {p}" for p in exempt_problems)

        module_level = {id(n) for n in tree.body}
        for kind, node, value, direct in _lock_assignments(tree):          # C6
            lock_assigns.append((mod, kind, getattr(node, "lineno", -1), value,
                                 id(node) in module_level, direct))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):                                 # C3
                name = _callee_name(node)
                if name in BANNED_OUTCOME_CALLEES:
                    problems.append(f"{mod}:{node.lineno}: calls {name}() — a real-outcome path")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):   # C4
                if id(node) in exempt:
                    continue
                for tok in BANNED_OUTCOME_TOKENS:
                    if tok in node.value:
                        problems.append(f"{mod}:{node.lineno}: executable string contains the "
                                        f"banned outcome token {tok!r}")
                        break

        for lineno, src_name in _exemption_laundering(tree):               # C4b
            problems.append(f"{mod}:{lineno}: path/reader argument reads through the exempt "
                            f"{src_name} — exemptions may not be used as a data source")

        for lineno, form in env_bindings(tree):                            # C7
            problems.append(f"{mod}:{lineno}: {form} could open the environment lock")

    # C6 — the DEFAULT-CLOSED invariant, restated precisely (v3.9v). The constant is never edited to
    # authorize a run: exactly one canonical module-level binding exists, it is False, production
    # source contains no reassignment or mutation of it, and real authorization is invocation-scoped
    # (a `RealFitAuthorization` threaded through the call) so it cannot persist after the call.
    harness_name = "run_coach_projection_experiment_v39.py"

    def _is_canonical_lock(mod, kind, value, at_module_level, direct):
        return (mod == harness_name and kind in ("Assign", "AnnAssign") and at_module_level
                and direct and isinstance(value, ast.Constant) and value.value is False)

    canonical = [a for a in lock_assigns if _is_canonical_lock(a[0], a[1], a[3], a[4], a[5])]
    for mod, kind, lineno, value, at_module_level, direct in lock_assigns:
        if _is_canonical_lock(mod, kind, value, at_module_level, direct):
            continue
        shown = "<destructured>" if not direct else getattr(value, "value", "<expression>")
        problems.append(f"{mod}:{lineno}: {LOCK_NAME} bound by {kind} "
                        f"{'at module level' if at_module_level else 'inside a scope'} "
                        f"with value {shown!r} — only one module-level `= False` is allowed")
    if len(canonical) != 1:
        problems.append(f"expected exactly one canonical module-level {LOCK_NAME} = False in the "
                        f"harness, found {len(canonical)}")

    # C6 (cont.) — no RUNTIME mutation of the lock either: a `globals()` write or a `setattr` on the
    # module would be a reassignment the binding walker cannot see as an Assign target.
    for mod, src_text in sorted(sources.items()):
        for lineno, form in _lock_mutations(_executable_tree(src_text)):
            problems.append(f"{mod}:{lineno}: {form} could mutate {LOCK_NAME} at runtime")

    # C5 — the real-panel entry point stays sealed, in ONE binding with an exact body.
    harness = sources.get(harness_name)
    if harness is None:
        problems.append(f"harness source unavailable; cannot validate {ENTRY_POINT_NAME}")
    else:
        problems.extend(_entry_point_is_sealed(_executable_tree(harness),
                                               contract_mode=contract_mode))

    return (not problems), ("; ".join(problems[:4]) if problems else NO_OUTCOME_OK_DETAIL)


# =====================================================================================================
# CONDITION 10 — A REAL RUNTIME PREFLIGHT (v3.9b §2, extended v3.9c)
# =====================================================================================================
# v3.9a's `_integrity_check()` checked only production hashes, the ten upstream coaching hashes, and the
# lock state, while C10 was DOCUMENTED as "every timing, leakage, coverage, artifact-integrity and
# no-real-outcome assertion". This is the preflight that makes the claim true. Every check is
# deterministic and reads NO outcome.
V39_ARTIFACT_HASHES = {
    # Filled at the end of the v3.9b pass; `test_pinned_v39_hashes_match_disk` fails if it goes stale.
    "team_coach_features_design_a_v39.csv": "b3e5aa463fff10161cf3abb78e0854f2",
    "team_coach_features_design_b_oracle_v39.csv": "5f8cf19b9aa4310b7eebbfb2406092c1",
    "arm_feature_manifest_v39.json": "65b596906eec757018e5b37b367835c2",
    "arm_feature_coverage_v39.csv": "807e38813cdd51800905e2b3c1a6d507",
    # v3.9c: changed because the false primary-policy metadata was corrected (§3).
    "arm_feature_lineage_v39.csv": "fcf8692bedab4e23652486cdcfe8f0b0",
}
PREFLIGHT_CHECKS = (
    "protected_hashes", "v39_artifacts_pinned", "v39_artifacts_readable",
    "no_unauthorized_v39_artifact",
    "no_coaching_parquet", "feature_table_keys_and_rows", "design_a_outer_identity_coverage",
    "unknown_and_no_history_routing", "forbidden_feature_policy", "manifest_full_x_matches_bundles",
    "manifest_qb_rookie_null", "coverage_reconciles", "lineage_strict_timing",
    "lineage_states_the_primary_policy",
    "contribution_lineage_reconciles", "design_b_oracle_and_unselectable",
    "production_models_identical", "no_real_outcome_access",
    "assembly_module_contract",
    "pipeline_timing_assertions_ran", "run_mode_locks",
)


def preflight(run_mode=DEFAULT_RUN_MODE, pipeline_assertions=None, data_dir=None,
              require_pipeline_assertions=True, authorization=None):
    """Deterministic runtime validation backing condition (10). Reads no outcome.

    Returns `{check: {"ok": bool, "detail": str}}` plus `all_ok`. C10 passes only when EVERY required
    check is true. `data_dir` lets a test point the artifact checks at a temporary copy so a corrupted
    contract can be proven to fail **without mutating a canonical artifact**.
    """
    D = DATA if data_dir is None else pathlib.Path(data_dir)
    res, fails = {}, {}

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:                                   # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        res[name] = dict(ok=bool(ok), detail=detail)
        if not ok:
            fails[name] = detail

    # ---- FAIL-CLOSED input loading (v3.9c §2) ---------------------------------------------------
    # v3.9b read the feature tables, manifest, coverage and lineage OUTSIDE the guarded `check()`
    # wrapper, so a missing or malformed artifact raised FileNotFoundError / ParserError and the
    # promised structured record was never returned. Every input is now loaded defensively up front;
    # a load failure is recorded and every dependent semantic check reports `blocked by <load>`
    # instead of crashing the preflight.
    loaded, load_err = {}, {}

    def _load(name, fn):
        try:
            obj = fn()
            if obj is None:
                raise ValueError("loader returned None")
            loaded[name] = obj
        except Exception as e:                                   # noqa: BLE001
            load_err[name] = f"{type(e).__name__}: {e}"

    def _csv(fname, required_cols=()):
        def go():
            p = D / fname
            if not p.exists():
                raise FileNotFoundError(f"{fname} is missing")
            df = pd.read_csv(p)
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                raise ValueError(f"{fname} schema invalid: missing {missing}")
            if not len(df):
                raise ValueError(f"{fname} is empty")
            return df
        return go

    def _json(fname, required_keys=()):
        def go():
            p = D / fname
            if not p.exists():
                raise FileNotFoundError(f"{fname} is missing")
            obj = json.loads(p.read_text(encoding="utf-8"))
            missing = [k for k in required_keys if k not in obj]
            if missing:
                raise ValueError(f"{fname} schema invalid: missing keys {missing}")
            return obj
        return go

    FEATURE_COLS = ("season", "team", "caller_identity_known", "caller_history_games_career")
    _load("design_a", _csv("team_coach_features_design_a_v39.csv", FEATURE_COLS))
    _load("design_b", _csv("team_coach_features_design_b_oracle_v39.csv", FEATURE_COLS))
    _load("coverage", _csv("arm_feature_coverage_v39.csv",
                           ("design", "arm", "season", "identity_state")))
    _load("lineage", _csv("arm_feature_lineage_v39.csv", ("record_kind",)))
    _load("manifest", _json("arm_feature_manifest_v39.json", ("by_position", "full_model_x")))

    def _need(*names):
        """Return (ok, blocked_detail). `blocked_detail` is None when every input is available."""
        bad = [n for n in names if n not in loaded]
        if not bad:
            return True, None
        return False, "; ".join(f"blocked by {n} load failure ({load_err[n]})" for n in bad)

    def _artifacts_readable():
        if load_err:
            return False, "; ".join(f"{k}: {v}" for k, v in load_err.items())
        return True, "all five v3.9 artifacts load with a valid schema"
    check("v39_artifacts_readable", _artifacts_readable)

    # ---- artifact integrity -------------------------------------------------------------------
    def _protected():
        bad = [f for f, h in AF.UPSTREAM_PROTECTED.items()
               if not (D / f).exists() or md5(D / f) != h]
        bad += [f for f, h in PRODUCTION_HASHES.items()
                if not (MODELS / f).exists() or md5(MODELS / f) != h]
        r = SEAS / "models" / "rookie_ppg_model.pkl"
        if not r.exists() or md5(r) != ROOKIE_PPG_MD5:
            bad.append("rookie_ppg_model.pkl")
        return (not bad), (f"changed/missing: {bad}" if bad
                           else "18/18 protected artifacts byte-identical")
    check("protected_hashes", _protected)

    def _pinned():
        bad = [f for f, h in V39_ARTIFACT_HASHES.items()
               if not (D / f).exists() or md5(D / f) != h]
        return (not bad), (f"changed/missing: {bad}" if bad else "5/5 v3.9 artifacts match their pins")
    check("v39_artifacts_pinned", _pinned)

    def _no_extra():
        found = {p.name for p in D.glob("*_v39.*")}
        extra = sorted(found - set(V39_ARTIFACT_HASHES))
        return (not extra), (f"unauthorized v3.9 artifacts: {extra}" if extra
                             else "exactly the five authorized artifacts")
    check("no_unauthorized_v39_artifact", _no_extra)

    def _no_parquet():
        pq = [str(p) for p in (D.parent).rglob("*.parquet")]
        return (not pq), (f"parquet under coaching/: {pq[:3]}" if pq else "no coaching parquet")
    check("no_coaching_parquet", _no_parquet)

    # ---- feature tables ------------------------------------------------------------------------
    def _keys():
        ok, blocked = _need("design_a", "design_b")
        if not ok:
            return False, blocked
        a, b = loaded["design_a"], loaded["design_b"]
        bad = []
        for name, df in (("design_a", a), ("design_b_oracle", b)):
            if len(df) != 416:
                bad.append(f"{name}: {len(df)} rows, expected 416")
            if df.duplicated(["season", "team"]).any():
                bad.append(f"{name}: duplicate (season, team)")
            if sorted(df.season.unique()) != AF.TARGET_SEASONS:
                bad.append(f"{name}: unexpected season set")
        return (not bad), ("; ".join(bad) if bad else "both tables 416 rows, unique keys, 2014-2026")
    check("feature_table_keys_and_rows", _keys)

    def _cov_a():
        ok, blocked = _need("design_a")
        if not ok:
            return False, blocked
        a = loaded["design_a"]
        o = a[a.season.between(2018, 2025)]
        n = int((o.caller_identity_known == 1).sum())
        return n == 152, f"Design A outer known target identities = {n}/256 (required 152)"
    check("design_a_outer_identity_coverage", _cov_a)

    def _routing():
        ok, blocked = _need("design_a", "design_b")
        if not ok:
            return False, blocked
        a, b = loaded["design_a"], loaded["design_b"]
        bad = []
        u = a[a.caller_identity_known == 0]
        if not len(u):
            bad.append("no unknown-caller rows to validate")
        checks = [(u.pc_career_off_rank_pct, AF.PRIOR_RANKPCT, "rank pct"),
                  (u.caller_adjusted_offense_effect, AF.NEUTRAL_EFFECT, "arm3 caller"),
                  (u.noncalling_hc_context_effect, AF.NEUTRAL_EFFECT, "arm3 context"),
                  (u.pc_tenure_current_team, AF.NEUTRAL_TENURE, "tenure"),
                  (u.pc_changed_entering, AF.NEUTRAL_CHANGED, "changed"),
                  (u.caller_is_head_coach, AF.NEUTRAL_IS_HC, "is_hc")]
        for series, want, label in checks:
            if not (series == want).all():
                bad.append(f"unknown-caller {label} != {want}")
        for c in AF.ARM2_QUALITY:
            if not (u[c] == AF.PRIOR_Z).all():
                bad.append(f"unknown-caller {c} != 0")
        nh = a[(a.caller_identity_known == 1) & (a.caller_history_games_career == 0)]
        if len(nh) and not (nh.pc_career_off_rank_pct == AF.PRIOR_RANKPCT).all():
            bad.append("known-no-history rank pct != league prior")
        if len(nh) and (nh.caller_is_head_coach == AF.NEUTRAL_IS_HC).any():
            bad.append("known-no-history row carries the UNKNOWN neutral is_hc value")
        cols = [c for c in AF.ALL_FEATURE_COLUMNS if c != "hc_changed_entering"]
        if a[cols].isna().any().any() or b[cols].isna().any().any():
            bad.append("a model feature is NaN; unknown must carry the neutral VALUE")
        return (not bad), ("; ".join(bad) if bad
                           else "unknown and known-no-history route to the frozen priors")
    check("unknown_and_no_history_routing", _routing)

    def _forbidden():
        ok, blocked = _need("manifest")
        if not ok:
            return False, blocked
        AF.assert_no_forbidden_features(AF.ALL_FEATURE_COLUMNS, "preflight")
        for pos, arms in loaded["manifest"]["by_position"].items():
            for arm, feats in arms.items():
                AF.assert_no_forbidden_features(feats, f"{pos}/{arm}")
        return True, "no forbidden metadata and no retired drive name in any arm"
    check("forbidden_feature_policy", _forbidden)

    # ---- manifest ------------------------------------------------------------------------------
    def _full_x():
        ok, blocked = _need("manifest")
        if not ok:
            return False, blocked
        man = loaded["manifest"]
        a0 = arm0_definition()
        bad = []
        for (pos, bucket), spec in a0.items():
            key = f"{pos}/{bucket}"
            got = man["full_model_x"].get(key)
            if got is None:
                bad.append(f"{key}: missing from full_model_x")
                continue
            for arm in ARMS:
                want = list(spec["feature_cols"]) + AF.arm_features(arm, pos)
                if got.get(arm) != want:
                    bad.append(f"{key}/{arm}: full X != bundle + ordered additions")
        return (not bad), ("; ".join(bad[:4]) if bad
                           else "full X == bundle feature_cols + ordered arm additions everywhere")
    check("manifest_full_x_matches_bundles", _full_x)

    def _qb_rookie():
        ok, blocked = _need("manifest")
        if not ok:
            return False, blocked
        man = loaded["manifest"]
        ok2 = man["full_model_x"].get("QB/rookie", "missing") is None
        return ok2, ("QB/rookie is explicitly null" if ok2
                     else "QB/rookie must be explicitly null in full_model_x")
    check("manifest_qb_rookie_null", _qb_rookie)

    # ---- coverage / lineage --------------------------------------------------------------------
    def _cov_rec():
        """FULL-FRAME reconciliation against a fresh canonical derivation (v3.9c §1).

        The v3.9b version compared only `ARM_1 / identity_state == "all"` and only two columns, so a
        corrupted `ARM_2 / known_with_history` cell reported reconciliation as TRUE. `AF.compare_coverage`
        regenerates the entire frame with the same function the builder writes from and compares
        schema, key set, uniqueness and every cell.
        """
        ok, blocked = _need("coverage", "design_a", "design_b")
        if not ok:
            return False, blocked
        return AF.compare_coverage(loaded["coverage"], loaded["design_a"], loaded["design_b"])
    check("coverage_reconciles", _cov_rec)

    def _lin_timing():
        ok, blocked = _need("lineage")
        if not ok:
            return False, blocked
        lin = loaded["lineage"]
        r = lin[lin.record_kind.isin(["identity_routing", "caller_contribution"])]
        bad = int((~r.strict_timing_ok.astype(str).str.lower().eq("true")).sum())
        c = lin[lin.record_kind == "caller_contribution"]
        late = int((c.source_season.astype(int) >= c.season.astype(int)).sum())
        return (bad == 0 and late == 0), (
            f"{bad} rows with strict_timing_ok false, {late} contributions not strictly prior")
    check("lineage_strict_timing", _lin_timing)

    def _lin_policy():
        """The lineage artifact must STATE the adopted policy, not the retired one (v3.9c §3)."""
        ok, blocked = _need("lineage")
        if not ok:
            return False, blocked
        return AF.validate_lineage_policy(loaded["lineage"])
    check("lineage_states_the_primary_policy", _lin_policy)

    def _contrib_rec():
        ok, blocked = _need("lineage", "design_a", "design_b")
        if not ok:
            return False, blocked
        lin, a, b = loaded["lineage"], loaded["design_a"], loaded["design_b"]
        c = lin[lin.record_kind == "caller_contribution"]
        bad = []
        for design, feat in ((AF.DESIGN_A, a), (AF.DESIGN_B, b)):
            sub = c[c.design == design]
            car = (sub[sub.included_in_career == 1].groupby(["season", "team"])
                   .agg(games=("pbp_games", "sum"), segs=("segment_key", "nunique")))
            r3 = sub[sub.included_in_roll3 == 1].groupby(["season", "team"])["pbp_games"].sum()
            for row in feat.itertuples():
                k = (row.season, row.team)
                if float(car.games.get(k, 0.0)) != float(row.caller_history_games_career):
                    bad.append(f"{design} {k}: career games")
                if int(car.segs.get(k, 0)) != int(row.caller_history_segments_career):
                    bad.append(f"{design} {k}: career segments")
                if float(r3.get(k, 0.0)) != float(row.caller_history_games_roll3):
                    bad.append(f"{design} {k}: roll3 games")
        return (not bad), ("; ".join(bad[:4]) if bad
                           else "contribution lineage reconciles on all 832 feature rows")
    check("contribution_lineage_reconciles", _contrib_rec)

    def _oracle():
        bad = []
        if "ORACLE" not in AF.DESIGN_LABEL[AF.DESIGN_B].upper():
            bad.append("Design B label is not marked ORACLE")
        if "NOT achievable in deployment" not in AF.DESIGN_LABEL[AF.DESIGN_B]:
            bad.append("Design B label is not marked nondeployable")
        src = (HERE / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
        body = src.split("def run_experiment", 1)[1].split("\ndef ", 1)[0]
        # drop the signature (which necessarily names coach_b), then require that nothing between the
        # signature and the oracle-diagnostic block touches it — selection cannot see Design B
        after_sig = body.split("):", 1)[1]
        sel = after_sig.split("if coach_b is not None", 1)[0]
        if "coach_b" in sel:
            bad.append("coach_b is referenced before the oracle-diagnostic block")
        return (not bad), ("; ".join(bad) if bad
                           else "Design B is labelled oracle/nondeployable and never enters selection")
    check("design_b_oracle_and_unselectable", _oracle)

    def _prod():
        try:
            assert_no_production_writes()
            return True, "production models byte-identical"
        except AssertionError as e:
            return False, str(e)
    check("production_models_identical", _prod)

    check("no_real_outcome_access", no_real_outcome_access)

    def _assembly():
        # Imported lazily and by NAME only: this module names no outcome column, so C4 stays clean.
        import assemble_real_panel_v39 as _arp
        return _arp.assembly_module_contract()
    check("assembly_module_contract", _assembly)

    def _assertions():
        tally = _PIPELINE_ASSERTIONS if pipeline_assertions is None else pipeline_assertions
        if not require_pipeline_assertions:
            return True, f"not required in this context; tally {dict(tally)}"
        zero = [k for k, v in tally.items() if not v]
        return (not zero), (f"assertions never executed: {zero}" if zero
                            else f"all pipeline assertions ran: {dict(tally)}")
    check("pipeline_timing_assertions_ran", _assertions)

    def _mode():
        return validate_run_mode(run_mode, authorization=authorization)
    check("run_mode_locks", _mode)

    all_ok = all(v["ok"] for v in res.values())
    return dict(run_mode=run_mode, all_ok=all_ok, checks=res, failures=fails,
                n_checks=len(res), n_failed=len(fails),
                detail=("; ".join(f"{k}: {v}" for k, v in fails.items()) if fails
                        else "all preflight checks passed"))


def _integrity_check(run_mode=DEFAULT_RUN_MODE, pipeline_assertions=None):
    """C10 gate. Returns (ok, detail, structured record)."""
    pf = preflight(run_mode=run_mode, pipeline_assertions=pipeline_assertions)
    return pf["all_ok"], pf["detail"], pf


# =====================================================================================================
# THE FROZEN TEN-CONDITION PRIMARY VERDICT (prereg §7)
# =====================================================================================================
# The FROZEN denominators. v3.9a checked only the improvement COUNTS, so a truncated six-season run
# could satisfy "6 of 8" and four available recent seasons could satisfy "4 of 5". The required season
# SETS are now part of the conditions.
REQUIRED_OUTER_SEASONS = tuple(range(2018, 2026))     # 8
REQUIRED_RECENT_SEASONS = tuple(range(2021, 2026))    # 5


def _panel_completeness(cohort, fold_selections):
    """Exact-denominator audit of what was actually supplied."""
    seasons = [int(s) for s in cohort.season.tolist()]
    present = set(seasons)
    req_out, req_rec = set(REQUIRED_OUTER_SEASONS), set(REQUIRED_RECENT_SEASONS)
    dup_rows = int(cohort.duplicated(["player_id", "season"]).sum()) if \
        "player_id" in cohort.columns else 0
    folds = set(int(k) for k in fold_selections)
    return dict(
        outer_seasons_present=sorted(present),
        outer_seasons_missing=sorted(req_out - present),
        outer_seasons_unexpected=sorted(present - req_out),
        recent_seasons_missing=sorted(req_rec - present),
        duplicate_player_season_rows=dup_rows,
        fold_seasons_missing=sorted(req_out - folds),
        fold_seasons_unexpected=sorted(folds - req_out),
        outer_panel_complete=bool(present == req_out and dup_rows == 0),
        recent_panel_complete=bool(req_rec <= present and dup_rows == 0),
        fold_set_complete=bool(folds == req_out),
    )


def primary_verdict(position, outer_frame, boot_results, placebo, fold_selections,
                    integrity_ok=True, integrity_detail="", outer_seasons=None,
                    recent_seasons=None):
    """Evaluate the §7 developmental-candidate rule for the NESTED-SELECTED Design A pipeline only.

    Target-agnostic: it reads a frame of predictions and never asks where `y` came from, so the
    synthetic fixtures exercise exactly the code the real run would.

    **No fixed arm and no Design B result can appear here.** The only challenger column consulted is
    `pred_selected`, which is the nested-selected Design A pipeline. A fixed arm cannot rescue a
    failed primary result because it is never read.

    `outer_frame` columns: season, y, pred_ARM_0, pred_selected, in_cohort.
    `boot_results`: {cluster_unit: {"ci_hi": float, ...}} for the SELECTED pipeline.
    `placebo`: {"observed": float, "p95": float, "draws": int}.
    `fold_selections`: {outer_season: selected_arm}.
    """
    outer_seasons = OUTER_SEASONS if outer_seasons is None else list(outer_seasons)
    recent_seasons = RECENT_SEASONS if recent_seasons is None else list(recent_seasons)
    f = outer_frame
    cohort = f[f["in_cohort"].astype(bool)]

    abs_gain = top_cohort_improvement(f)
    rel_gain = relative_top_cohort_improvement(f)

    def season_improved(seasons):
        out = []
        for Y in seasons:
            s = cohort[cohort.season == Y]
            if not len(s):
                continue
            out.append(_mae(s.y, s.pred_ARM_0) - _mae(s.y, s.pred_selected) > 0)
        return int(sum(out)), len(out)

    n_out_imp, n_out = season_improved(outer_seasons)
    n_rec_imp, n_rec = season_improved(recent_seasons)

    def mean_rho(col):
        vals = [_spearman(g.y, g[col]) for _s, g in cohort.groupby("season")]
        return float(np.nanmean(vals)) if vals else np.nan

    rho_gain = mean_rho("pred_selected") - mean_rho("pred_ARM_0")
    full_mae_delta = _mae(f.y, f.pred_selected) - _mae(f.y, f.pred_ARM_0)
    base_rmse = _rmse(f.y, f.pred_ARM_0)
    full_rmse_rel = ((_rmse(f.y, f.pred_selected) - base_rmse) / base_rmse
                     if base_rmse else np.nan)
    n_nonbaseline = sum(1 for a in fold_selections.values() if a != "ARM_0")
    ci_his = {u: r["ci_hi"] for u, r in boot_results.items()}

    panel = _panel_completeness(cohort, fold_selections)

    conds = {
        "c1_top_cohort_improves_3pct": bool(rel_gain >= PASS_MIN_RELATIVE_TOP_COHORT_IMPROVEMENT),
        "c2_both_clustered_ci_upper_below_zero": bool(
            len(ci_his) == len(CLUSTER_UNITS) and all(v < 0 for v in ci_his.values())),
        # EXACT denominators: the required season SET must be present, not merely enough improvements.
        "c3_improves_6_of_8_outer_seasons": bool(
            panel["outer_panel_complete"] and n_out_imp >= PASS_MIN_OUTER_SEASONS_IMPROVED),
        "c4_improves_4_of_5_recent_seasons": bool(
            panel["recent_panel_complete"] and n_rec_imp >= PASS_MIN_RECENT_SEASONS_IMPROVED),
        "c5_top_cohort_spearman_gain_0p005": bool(rho_gain >= PASS_MIN_SPEARMAN_GAIN),
        "c6_full_panel_mae_worsens_le_0p25": bool(
            full_mae_delta <= PASS_MAX_FULL_PANEL_MAE_WORSENING),
        "c7_full_panel_rmse_worsens_le_1pct": bool(
            full_rmse_rel <= PASS_MAX_FULL_PANEL_RMSE_WORSENING),
        "c8_nonbaseline_arm_in_4_of_8_folds": bool(
            panel["fold_set_complete"] and n_nonbaseline >= PASS_MIN_NONBASELINE_FOLDS),
        "c9_beats_placebo_p95": bool(
            placebo.get("draws", 0) > 0
            and np.isfinite(placebo.get("p95", np.nan))
            and placebo.get("observed", -np.inf) > placebo["p95"]),
        "c10_all_assertions_pass": bool(integrity_ok),
    }
    failures = [k for k, v in conds.items() if not v]
    denom_notes = []
    if panel["outer_seasons_missing"]:
        denom_notes.append(f"outer seasons MISSING {panel['outer_seasons_missing']}")
    if panel["outer_seasons_unexpected"]:
        denom_notes.append(f"outer seasons UNEXPECTED {panel['outer_seasons_unexpected']}")
    if panel["recent_seasons_missing"]:
        denom_notes.append(f"recent seasons MISSING {panel['recent_seasons_missing']}")
    if panel["duplicate_player_season_rows"]:
        denom_notes.append(
            f"{panel['duplicate_player_season_rows']} DUPLICATE (player_id, season) cohort rows")
    if panel["fold_seasons_missing"]:
        denom_notes.append(f"fold selections MISSING {panel['fold_seasons_missing']}")
    if panel["fold_seasons_unexpected"]:
        denom_notes.append(f"fold selections UNEXPECTED {panel['fold_seasons_unexpected']}")
    return dict(
        position=position, design=AF.DESIGN_A, challenger="nested_selected_design_a",
        improvement_statistic=IMPROVEMENT_STATISTIC,
        required_outer_seasons=len(REQUIRED_OUTER_SEASONS),
        required_recent_seasons=len(REQUIRED_RECENT_SEASONS),
        outer_panel_complete=panel["outer_panel_complete"],
        recent_panel_complete=panel["recent_panel_complete"],
        fold_set_complete=panel["fold_set_complete"],
        denominator_problems="; ".join(denom_notes),
        outer_seasons_missing=str(panel["outer_seasons_missing"]),
        outer_seasons_unexpected=str(panel["outer_seasons_unexpected"]),
        recent_seasons_missing=str(panel["recent_seasons_missing"]),
        duplicate_player_season_rows=panel["duplicate_player_season_rows"],
        fold_seasons_missing=str(panel["fold_seasons_missing"]),
        fold_seasons_unexpected=str(panel["fold_seasons_unexpected"]),
        top_cohort_mae_arm0=_mae(cohort.y, cohort.pred_ARM_0) if len(cohort) else np.nan,
        top_cohort_mae_selected=_mae(cohort.y, cohort.pred_selected) if len(cohort) else np.nan,
        top_cohort_abs_improvement=abs_gain, top_cohort_rel_improvement=rel_gain,
        ci_hi_player=ci_his.get("player", np.nan),
        ci_hi_team_season=ci_his.get("team_season", np.nan),
        n_outer_seasons_improved=n_out_imp, n_outer_seasons=n_out,
        n_recent_seasons_improved=n_rec_imp, n_recent_seasons=n_rec,
        mean_within_season_spearman_gain=rho_gain,
        full_panel_mae_delta=full_mae_delta, full_panel_rmse_relative_delta=full_rmse_rel,
        n_nonbaseline_folds=n_nonbaseline, n_folds=len(fold_selections),
        placebo_observed=placebo.get("observed", np.nan), placebo_p95=placebo.get("p95", np.nan),
        placebo_draws=placebo.get("draws", 0),
        integrity_ok=bool(integrity_ok), integrity_detail=integrity_detail,
        **conds,
        n_conditions_passed=int(sum(conds.values())), n_conditions=len(conds),
        failure_reasons="; ".join(failures),
        verdict=("DEVELOPMENTAL CANDIDATE" if not failures else "NO — primary pass rule not met"),
    )


def assert_no_production_writes(before=None):
    """Every production artifact must be byte-identical after a harness run."""
    now = {f: md5(MODELS / f) for f in PRODUCTION_HASHES}
    bad = [f for f, h in PRODUCTION_HASHES.items() if now[f] != h]
    assert not bad, f"production model pkl CHANGED: {bad}"
    r = md5(SEAS / "models" / "rookie_ppg_model.pkl")
    assert r == ROOKIE_PPG_MD5, f"rookie_ppg_model.pkl CHANGED: {r}"
    if before is not None:
        assert before == now, "a production pkl changed during this run"
    return now


def parse_outer_seasons(spec):
    """`2018-2025` or `2018,2019` or `2018` -> a tuple of ints, validated against the frozen set."""
    if spec is None:
        return tuple(OUTER_SEASONS)
    text = str(spec).strip()
    if "-" in text:
        lo, _, hi = text.partition("-")
        seasons = tuple(range(int(lo), int(hi) + 1))
    else:
        seasons = tuple(int(s) for s in text.replace(",", " ").split())
    unknown = [s for s in seasons if s not in OUTER_SEASONS]
    if not seasons or unknown:
        raise SystemExit(f"--outer-seasons {spec!r}: {unknown or 'empty'} outside the frozen outer "
                         f"set {list(OUTER_SEASONS)}")
    return seasons


def run_authorized_real(outer_seasons, bootstrap_draws, placebo_draws, out_dir=None,
                        overwrite=False, verbose=True, authorization=None):
    """THE authorized-real path. Unreachable unless BOTH locks are open.

    Order is fixed and each step gates the next:
      authorization -> preflight/readiness/gate clearance -> pinned readers -> assemble_real_panel
      -> canonical adapter -> run_experiment(run_mode='authorized_real') -> validate frames
      -> atomic five-file write -> hashes.

    Statement 1 refuses on a closed or partial lock before any reader is constructed, so an
    unauthorized invocation reaches no data at all.
    """
    import assemble_real_panel_v39 as _arp
    import write_v39_results as _wr

    require_real_fit_authorization(authorization)

    pf = preflight(run_mode=RUN_MODE_AUTHORIZED_REAL, authorization=authorization)
    require_preflight_clearance(RUN_MODE_AUTHORIZED_REAL, pf, authorization=authorization)

    # the COMPOSED reader: veteran snapshot + rookie matrix under the frozen
    # SHIPPED_ARM0_BUCKETS routing, so all seven buckets are feedable
    # ELIGIBILITY runs INSIDE the feature reader, so it completes before the outcome reader is ever
    # called: Python evaluates `assemble_panel_core(feature_reader(), outcome_reader())` left to
    # right, and a malformed partition raises out of the first argument. Zero outcome-reader calls.
    composed_reader = _arp.authorized_composed_feature_reader()
    eligibility = {}

    def feature_reader():
        frame = composed_reader()
        eligible, accounting = _arp.evaluation_eligibility(frame)
        eligibility.update(accounting)
        if verbose:
            print(f"  eligibility: source {accounting['source_population']} | "
                  f"-{accounting['excluded_missing_team']} missing team | "
                  f"-{accounting['excluded_no_shipped_bundle']} no shipped bundle | "
                  f"eligible {accounting['eligible_evaluation_population']}")
        return eligible

    outcome_reader = _arp.authorized_outcome_reader()
    assembled = assemble_real_panel(feature_reader, outcome_reader, authorization,
                                    run_mode=RUN_MODE_AUTHORIZED_REAL)
    panel, report = _arp.panel_for_experiment(assembled)
    assert len(panel) == eligibility["eligible_evaluation_population"], (
        f"the adapter changed the eligible population "
        f"{eligibility['eligible_evaluation_population']} -> {len(panel)}")
    if verbose:
        print(f"  panel: {report['n_rows']} rows | buckets {report['buckets']} | "
              f"outcome states {report['outcome_states']}")

    coach_a = pd.read_csv(DATA / "team_coach_features_design_a_v39.csv")
    coach_b = pd.read_csv(DATA / "team_coach_features_design_b_oracle_v39.csv")
    frames = run_experiment(panel, coach_a, coach_b, outer_seasons=outer_seasons,
                            bootstrap_draws=bootstrap_draws, placebo_draws=placebo_draws,
                            verbose=verbose, run_mode=RUN_MODE_AUTHORIZED_REAL,
                            authorization=authorization)

    problems = _wr.validate_outputs(_wr.compose(frames, eligibility=eligibility))
    if problems:
        raise SystemExit("result validation failed: " + "; ".join(problems))
    hashes = _wr.write_results(frames, out_dir=out_dir, overwrite=overwrite, eligibility=eligibility)
    return frames, hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="print the production audit (writes nothing)")
    ap.add_argument("--synthetic", action="store_true", help="SYNTHETIC-target smoke run")
    ap.add_argument("--run-mode", choices=list(RUN_MODES), default=None,
                    help="authorized_real performs the real run; requires BOTH locks open")
    ap.add_argument("--outer-seasons", default=None, help="e.g. 2018-2025")
    ap.add_argument("--authorization-token", default=None,
                    help="the exact authorized-real CLI token; required with --run-mode "
                         "authorized_real and checked against a frozen literal")
    ap.add_argument("--overwrite-results", action="store_true",
                    help="replace existing result files (refused by default)")
    ap.add_argument("--outer", type=int, nargs="*", default=None)
    ap.add_argument("--bootstrap-draws", type=int, default=2000)
    ap.add_argument("--placebo-draws", type=int, default=10)
    a = ap.parse_args()

    if a.run_mode == RUN_MODE_AUTHORIZED_REAL:
        # BOTH runtime locks, presented together, in this one invocation. Nothing is mutated.
        try:
            authorization = grant_real_fit_authorization(a.authorization_token)
        except RuntimeError as exc:
            raise SystemExit("BLOCKED: " + str(exc))
        ok, detail = validate_run_mode(RUN_MODE_AUTHORIZED_REAL, authorization=authorization)
        if not ok:
            raise SystemExit("BLOCKED: " + detail)
        seasons = parse_outer_seasons(a.outer_seasons)
        print("=" * 96)
        print(f"AUTHORIZED REAL RUN — outer seasons {list(seasons)}")
        print("=" * 96)
        _frames, hashes = run_authorized_real(seasons, a.bootstrap_draws, a.placebo_draws,
                                              overwrite=a.overwrite_results,
                                              authorization=authorization)
        print("\n--- RESULT HASHES ---")
        for name, h in sorted(hashes.items()):
            print(f"  {name:26s} {h}")
        return hashes

    print("=" * 96)
    print("PHASE 2B v3.9 — COACH-REPRESENTATION EVALUATION HARNESS")
    print(f"REAL_FIT_AUTHORIZED = {REAL_FIT_AUTHORIZED} | env switch set = "
          f"{os.environ.get(REAL_FIT_ENV_SWITCH) == REAL_FIT_ENV_TOKEN} | "
          f"real fit unlocked = {real_fit_is_unlocked()}   (synthetic targets only)")
    print("=" * 96)
    before = assert_no_production_writes()
    audit = audit_production()
    spec = experiment_spec()
    print("\n--- PRODUCTION AUDIT ---")
    for k, v in audit["model_families"].items():
        print(f"  {k:12s} {v['family']:9s} {v['params']}")
    print(f"  QB rookie bundle: {audit['rookie_path']['qb_rookie_bundle']}")
    print(f"  target          : {audit['prediction_target']['name']} — "
          f"{audit['prediction_target']['construction']}")
    print(f"  categorical     : {audit['categorical_handling_arm0']}")
    print(f"  sample weights  : {audit['sample_weights_arm0']}")
    print(f"  missing values  : {audit['missing_value_handling_arm0']}")
    print(f"  clipping        : {audit['transforms_and_clipping']['prediction_clipping']}")
    print("  LEGACY family   : "
          + audit["TWO_ARCHITECTURES_EXIST_IN_THIS_REPO"]["legacy_family_NOT_USED"]["IMPORTANT"])
    print("\n--- FROZEN INNER FOLDS ---")
    for Y in OUTER_SEASONS:
        f = expanding_inner_folds(range(PANEL_FIRST_SEASON, 2026), Y)
        print(f"  outer {Y}: " + " | ".join(f"train {list(t)} -> validate {v}" for t, v in f))

    if a.synthetic:
        print("\n--- SYNTHETIC SMOKE RUN (targets are generated; no fantasy outcome is read) ---")
        panel = synthetic_panel()
        ca = pd.read_csv(DATA / "team_coach_features_design_a_v39.csv")
        cb = pd.read_csv(DATA / "team_coach_features_design_b_oracle_v39.csv")
        outer = a.outer or [2024, 2025]
        res = run_experiment(panel, ca, cb, outer_seasons=outer,
                             bootstrap_draws=a.bootstrap_draws, placebo_draws=a.placebo_draws)
        for k, df in res.items():
            print(f"\n[{k}] {df.shape}")
            if len(df):
                print(df.head(12).to_string(index=False))
    assert_no_production_writes(before)
    print("\nThis module wrote NOTHING. NO real fantasy outcome loaded, inspected or fit. "
          "NO production artifact touched.")
    return spec


if __name__ == "__main__":
    main()
