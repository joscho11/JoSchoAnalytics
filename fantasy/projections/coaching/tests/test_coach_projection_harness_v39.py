"""PHASE 2B tests (prereg v3.9 PREFIT) — the nested evaluation harness.

Every test runs on SYNTHETIC targets. The harness is verified BEFORE any fantasy outcome is visible,
which is the whole point of stopping here.
"""
import json
import os
import pathlib
import re
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
DATA = COACH / "data"
sys.path.insert(0, str(COACH))

import build_arm_features_v39 as AF   # noqa: E402
import run_coach_projection_experiment_v39 as EX   # noqa: E402

SMALL_TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI"]
SMALL_SEASONS = list(range(2014, 2020))


@pytest.fixture(scope="module")
def coach_a():
    return pd.read_csv(DATA / "team_coach_features_design_a_v39.csv")


@pytest.fixture(scope="module")
def coach_b():
    return pd.read_csv(DATA / "team_coach_features_design_b_oracle_v39.csv")


@pytest.fixture(scope="module")
def small_panel():
    return EX.synthetic_panel(seasons=SMALL_SEASONS, teams=SMALL_TEAMS, players_per_team=2,
                              positions=["RB"], seed=11)


@pytest.fixture(scope="module")
def arm0():
    return EX.arm0_definition()


# =====================================================================================================
# TIMING AND EXPANDING FOLDS
# =====================================================================================================
def test_outer_2018_inner_folds_are_exactly_the_frozen_pair():
    f = EX.expanding_inner_folds(range(2014, 2026), 2018)
    assert f == [((2014, 2015), 2016), ((2014, 2015, 2016), 2017)]


def test_folds_are_expanding_and_never_train_on_their_own_or_a_later_season():
    for Y in EX.OUTER_SEASONS:
        folds = EX.expanding_inner_folds(range(2014, 2026), Y)
        assert len(folds) >= EX.INNER_MIN_VALIDATION_SEASONS
        prev = None
        for train, val in folds:
            assert max(train) < val < Y, "inner training < validation < outer target violated"
            assert all(s < val for s in train)
            if prev is not None:
                assert set(prev).issubset(set(train)), "folds must EXPAND, not slide"
            prev = train


def test_frozen_inner_minimums_skip_a_target_without_enough_history():
    assert EX.expanding_inner_folds(range(2014, 2017), 2017) == []
    assert EX.expanding_inner_folds([2014, 2015], 2016) == []
    assert EX.INNER_MIN_TRAIN_SEASONS == 2 and EX.INNER_MIN_VALIDATION_SEASONS == 2


def test_outer_fit_never_touches_its_own_test_season(small_panel, coach_a, arm0):
    fr = EX.outer_predictions(small_panel, coach_a, "RB", 2019, arm0, arms=["ARM_0"])
    assert set(fr["ARM_0"].season) == {2019}


# =====================================================================================================
# ARM 0 IS READ FROM PRODUCTION
# =====================================================================================================
def test_arm0_is_read_from_the_bundle_and_matches_the_builder_pool(arm0):
    assert set(arm0) == set(EX.BUNDLE_FILE)
    for (pos, bucket), v in arm0.items():
        assert v["family"] == "lightgbm"
        assert v["target"] == "season_total_half_ppr"
        assert v["median_impute"] is None, "every shipped bundle routes NaN natively"
        assert v["md5"] == EX.PRODUCTION_HASHES[v["bundle"]]
    assert arm0[("RB", "veteran")]["n_features"] == 32
    assert arm0[("RB", "rookie")]["n_features"] == 41
    assert arm0[("WR", "rookie")]["n_features"] == 44
    assert arm0[("TE", "rookie")]["n_features"] == 44
    vet = {p: tuple(arm0[(p, "veteran")]["feature_cols"]) for p in AF.POSITIONS}
    assert len(set(vet.values())) == 1, "the four veteran pools are the same 32 columns"
    assert "coach_changed" in vet["RB"] and "qb_changed" in vet["RB"]
    assert not any("depth_rank" in c for c in vet["RB"])


def test_arm0_appends_no_coaching_feature():
    for pos in AF.POSITIONS:
        assert AF.arm_features("ARM_0", pos) == []


def test_qb_rookie_path_is_absent_and_recorded():
    assert ("QB", "rookie") in EX.MISSING_BUNDLES
    assert ("QB", "rookie") not in EX.BUNDLE_FILE
    audit = EX.audit_production(write=False)
    assert "ABSENT" in audit["rookie_path"]["qb_rookie_bundle"]
    assert "HELD" in audit["rookie_path"]["qb_rookie_bundle"]


def test_audit_records_the_full_production_contract():
    a = EX.audit_production()
    assert a["categorical_handling_arm0"].startswith("NONE")
    assert a["sample_weights_arm0"].startswith("NONE")
    assert "native NaN" in a["missing_value_handling_arm0"]
    assert a["prediction_target"]["name"] == "season_total_half_ppr"
    assert "fantasy_points + 0.5*receptions" in a["prediction_target"]["construction"]
    assert "target_ppg" in a["prediction_target"]["not_used_by_arm0"]
    assert "sample_weight" in a["prediction_target"]["not_used_by_arm0"]
    assert "target_games" in a["prediction_target"]["not_used_by_arm0"]
    assert set(a["ordered_baseline_features"]) == {f"{p}/{b}" for p, b in EX.BUNDLE_FILE}
    assert "IMPORT" in a["veteran_path"]["engine"]


# =====================================================================================================
# IDENTICAL ROWS ACROSS ARMS
# =====================================================================================================
def test_identical_player_rows_across_every_arm(small_panel, coach_a, arm0):
    fr = EX.outer_predictions(small_panel, coach_a, "RB", 2019, arm0)
    assert set(fr) == set(AF.ARMS)
    keys = {a: tuple(zip(f.player_id, f.season)) for a, f in fr.items()}
    ref = keys["ARM_0"]
    for a, k in keys.items():
        assert k == ref, f"{a} predicted a different row set"
    for a, f in fr.items():
        pd.testing.assert_series_equal(f["y"], fr["ARM_0"]["y"], check_names=False)


def test_attach_coach_features_preserves_the_row_count(small_panel, coach_a):
    sub = small_panel[small_panel.bucket == "veteran"]
    for arm in AF.ARMS:
        out, feats = AF.attach_coach_features(sub, coach_a, arm, "RB") if False else \
            EX.attach_coach_features(sub, coach_a, arm, "RB")
        assert len(out) == len(sub)
        assert feats == AF.arm_features(arm, "RB")
        assert list(out.player_id) == list(sub.player_id), "row ORDER must not move"


def test_a_player_row_without_a_coaching_bundle_raises(small_panel, coach_a):
    bad = small_panel.copy()
    bad.loc[bad.index[0], "team"] = "ZZZ"
    with pytest.raises(AssertionError, match="no coaching bundle"):
        EX.attach_coach_features(bad, coach_a, "ARM_HC", "RB")


# =====================================================================================================
# ARM-0-DEFINED COHORTS
# =====================================================================================================def
def test_cohorts_are_defined_by_the_arm0_prediction_only():
    f = pd.DataFrame(dict(season=[2020] * 4, position=["TE"] * 4, y=[1.0, 2, 3, 4],
                          pred_ARM_0=[10.0, 9, 8, 7], pred_ARM1=[7.0, 8, 9, 10]))
    m = EX.baseline_cohort_mask(f)
    assert m.all(), "TE cohort is 12; four rows all qualify"
    f2 = pd.concat([f] * 5, ignore_index=True)
    f2["pred_ARM_0"] = np.arange(20, 0, -1, dtype=float)
    f2["pred_ARM1"] = np.arange(1, 21, dtype=float)      # exactly reversed
    m2 = EX.baseline_cohort_mask(f2)
    assert int(m2.sum()) == EX.COHORT_N["TE"] == 12
    assert m2[:12].all() and not m2[12:].any(), "the cohort follows ARM 0, not the challenger"


def test_cohort_sizes_are_the_frozen_draft_relevant_ones():
    assert EX.COHORT_N == {"QB": 12, "RB": 24, "WR": 24, "TE": 12}


def test_cohort_is_computed_per_season_and_position():
    f = pd.DataFrame(dict(season=[2020] * 30 + [2021] * 30, position=["TE"] * 60,
                          y=list(range(60)), pred_ARM_0=list(range(60, 0, -1))))
    m = EX.baseline_cohort_mask(f)
    assert int(m[:30].sum()) == 12 and int(m[30:].sum()) == 12


# =====================================================================================================
# SELECTION RULES
# =====================================================================================================
def _scores(**kw):
    """kw: arm -> (inner_full_mae, inner_top_mae, n_added_features)."""
    return {a: dict(inner_full_mae=f, inner_top_mae=t, n_added_features=n)
            for a, (f, t, n) in kw.items()}


def test_an_arm_that_regresses_the_full_panel_is_ineligible():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_2=(10.30, 5.0, 15))
    pick, reason, tab = EX.select_arm(s)
    assert pick == "ARM_0" and "tolerance" in reason
    assert tab["ARM_2"]["eligible"] is False
    s2 = _scores(ARM_0=(10.0, 8.0, 0), ARM_2=(10.25, 5.0, 15))
    assert EX.select_arm(s2)[0] == "ARM_2", "exactly 0.25 is still eligible"


def test_improvement_below_one_percent_selects_arm0():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_3=(10.0, 7.9601, 3))   # 0.499% better
    pick, reason, _ = EX.select_arm(s)
    assert pick == "ARM_0" and "< 1%" in reason
    s2 = _scores(ARM_0=(10.0, 8.0, 0), ARM_3=(10.0, 7.9200, 3))  # exactly 1.0% better
    assert EX.select_arm(s2)[0] == "ARM_3"


def test_tie_band_prefers_the_arm_with_fewer_added_features():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_2=(10.0, 7.00, 15), ARM_3=(10.0, 7.20, 3))
    pick, reason, _ = EX.select_arm(s)
    assert pick == "ARM_3", "within 0.25 of the best, parsimony wins"
    assert "fewest added features" in reason
    s2 = _scores(ARM_0=(10.0, 8.0, 0), ARM_2=(10.0, 7.00, 15), ARM_3=(10.0, 7.30, 3))
    assert EX.select_arm(s2)[0] == "ARM_2", "0.30 apart is outside the band"


def test_a_final_tie_breaks_on_the_frozen_arm_order():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_HC=(10.0, 7.0, 4), ARM_1=(10.0, 7.0, 4))
    assert EX.select_arm(s)[0] == "ARM_HC"
    assert AF.ARMS.index("ARM_HC") < AF.ARMS.index("ARM_1")


def test_arm_hc_can_win_selection():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_HC=(9.9, 7.0, 4), ARM_5=(9.9, 7.9, 17))
    pick, reason, _ = EX.select_arm(s)
    assert pick == "ARM_HC"
    assert "ARM_HC" in AF.ARMS and AF.arm_features("ARM_HC", "RB") == AF.ARM_HC_FEATURES


def test_no_eligible_arm_falls_back_to_arm0():
    s = _scores(ARM_0=(10.0, 8.0, 0), ARM_1=(11.0, 1.0, 9), ARM_2=(12.0, 1.0, 15))
    assert EX.select_arm(s)[0] == "ARM_0"


# =====================================================================================================
# ORACLE ISOLATION
# =====================================================================================================
def test_oracle_design_never_enters_selection(small_panel, coach_a, coach_b):
    res = EX.run_experiment(small_panel, coach_a, coach_b, outer_seasons=[2019],
                            positions=["RB"], bootstrap_draws=50, run_placebo=False,
                            verbose=False)
    assert len(res["selection"]) == 1
    assert "design" not in res["selection"].columns or \
        set(res["selection"].get("design", [AF.DESIGN_A])) == {AF.DESIGN_A}
    assert set(res["metrics"].design) == {AF.DESIGN_A}
    assert set(res["bootstrap"].design) == {AF.DESIGN_A}
    assert set(res["oracle"].design) == {AF.DESIGN_B}


def test_every_oracle_row_carries_the_nondeployable_label(small_panel, coach_a, coach_b):
    res = EX.run_experiment(small_panel, coach_a, coach_b, outer_seasons=[2019],
                            positions=["RB"], bootstrap_draws=50, run_placebo=False,
                            verbose=False)
    for lab in res["oracle"].label:
        assert "ORACLE IDENTITY" in lab and "NOT achievable in deployment" in lab


def test_selection_is_identical_whether_or_not_the_oracle_is_supplied(small_panel, coach_a,
                                                                     coach_b):
    a = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=50, run_placebo=False, verbose=False)
    b = EX.run_experiment(small_panel, coach_a, coach_b, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=50, run_placebo=False, verbose=False)
    pd.testing.assert_frame_equal(a["selection"], b["selection"])


# =====================================================================================================
# CLUSTERED RESAMPLING
# =====================================================================================================
def _boot_frame():
    return pd.DataFrame(dict(
        player_id=["p1", "p1", "p2", "p2"], season=[2020, 2021, 2020, 2021],
        team=["A", "A", "B", "B"], y=[0.0, 0.0, 0.0, 0.0],
        pred_ARM_0=[1.0, 1.0, 3.0, 3.0], pred_sel=[1.0, 1.0, 1.0, 1.0]))


def test_bootstrap_resamples_whole_clusters_not_rows():
    """Two player clusters with constant within-cluster errors. Cluster resampling can only ever
    produce the three cluster-level means; a row-level bootstrap would produce more."""
    f = _boot_frame()
    r = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=500, seed=1)
    assert r["n_clusters"] == 2
    assert r["observed_diff"] == pytest.approx(-1.0)     # (1+1+1+1)/4 - (1+1+3+3)/4
    # achievable cluster-level differences: {0, -1, -2}
    r2 = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=200, seed=2)
    assert r2["ci_lo"] >= -2.0 - 1e-9 and r2["ci_hi"] <= 0.0 + 1e-9


def test_both_frozen_cluster_units_are_available():
    assert EX.CLUSTER_UNITS == {"player": ["player_id"], "team_season": ["season", "team"]}
    f = _boot_frame()
    p = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=100)
    t = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["season", "team"], draws=100)
    assert p["n_clusters"] == 2 and t["n_clusters"] == 4
    assert p["unit"] == "player_id" and t["unit"] == "season+team"


def test_bootstrap_is_reproducible_under_the_frozen_seed():
    # Enough clusters that the percentiles are genuinely seed-sensitive; a 2-cluster frame pins the
    # 2.5/97.5 percentiles at the extreme cluster means for EVERY seed and would prove nothing.
    rng = np.random.default_rng(0)
    n = 40
    f = pd.DataFrame(dict(player_id=[f"p{i}" for i in range(n)], season=2020,
                          team=[f"T{i%8}" for i in range(n)], y=np.zeros(n),
                          pred_ARM_0=rng.normal(0, 3, n), pred_sel=rng.normal(0, 3, n)))
    a = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=300,
                               seed=EX.BOOTSTRAP_SEED)
    b = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=300,
                               seed=EX.BOOTSTRAP_SEED)
    assert a == b
    c = EX.clustered_bootstrap(f, "pred_sel", "pred_ARM_0", ["player_id"], draws=300, seed=999)
    assert (a["ci_lo"], a["ci_hi"]) != (c["ci_lo"], c["ci_hi"])
    assert a["observed_diff"] == c["observed_diff"], "the point estimate is seed-independent"


def test_frozen_bootstrap_constants():
    assert EX.BOOTSTRAP_DRAWS == 20_000 and EX.BOOTSTRAP_SEED == 20260728


def test_holm_is_monotone_and_never_reduces_a_p_value():
    raw = {"ARM_HC": 0.001, "ARM_1": 0.01, "ARM_2": 0.02, "ARM_3": 0.20, "ARM_4": 0.5, "ARM_5": 0.9}
    adj = EX.holm(raw)
    assert all(adj[k] >= raw[k] for k in raw)
    order = sorted(raw, key=raw.get)
    vals = [adj[k] for k in order]
    assert vals == sorted(vals), "Holm-adjusted p-values must be non-decreasing"
    assert adj["ARM_HC"] == pytest.approx(6 * 0.001)


# =====================================================================================================
# TEAM-LEVEL PERMUTATION PLACEBO
# =====================================================================================================
def test_permutation_moves_COMPLETE_team_bundles(coach_a):
    p = EX.permute_team_bundles(coach_a, seed=5)
    assert len(p) == len(coach_a)
    for s in coach_a.season.unique():
        o = coach_a[coach_a.season == s].sort_values("team").reset_index(drop=True)
        n = p[p.season == s].sort_values("team").reset_index(drop=True)
        assert list(o.team) == list(n.team), "the team labels themselves must not change"
        # every bundle still present exactly once, as a WHOLE row
        ocols = o[AF.ALL_FEATURE_COLUMNS].round(10).astype(str).agg("|".join, axis=1)
        ncols = n[AF.ALL_FEATURE_COLUMNS].round(10).astype(str).agg("|".join, axis=1)
        assert sorted(ocols) == sorted(ncols), "bundles were altered, not merely reassigned"


def test_permutation_stays_strictly_within_season(coach_a):
    p = EX.permute_team_bundles(coach_a, seed=5)
    key = lambda d: d.groupby("season").apply(  # noqa: E731
        lambda g: tuple(sorted(g.hc_career_win_pct_shrunk.round(10))), include_groups=False)
    pd.testing.assert_series_equal(key(coach_a), key(p), check_names=False)


def test_permutation_actually_reassigns_something(coach_a):
    p = EX.permute_team_bundles(coach_a, seed=5)
    o = coach_a.sort_values(["season", "team"]).reset_index(drop=True)
    n = p.sort_values(["season", "team"]).reset_index(drop=True)
    assert not o.hc_career_win_pct_shrunk.equals(n.hc_career_win_pct_shrunk)


def test_permutation_never_touches_player_rows():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    body = src.split("def permute_team_bundles", 1)[1].split("\ndef ", 1)[0]
    for token in ("player_id", "panel", "y"):
        assert not re.search(rf"\b{token}\b", body), (
            f"the permutation references {token}; it must only reassign team bundles")


def test_frozen_placebo_constants():
    assert EX.PLACEBO_DRAWS == 200 and EX.PLACEBO_SEED == 20260728


def test_placebo_distribution_runs_and_is_seeded(small_panel, coach_a, arm0):
    """No fixed-arm argument any more: the placebo scores the nested-selected pipeline."""
    d1, p1 = EX.placebo_distribution(small_panel, coach_a, "RB", [2019], arm0, draws=2, seed=3)
    d2, p2 = EX.placebo_distribution(small_panel, coach_a, "RB", [2019], arm0, draws=2, seed=3)
    assert len(d1) == 2 and np.allclose(d1, d2)
    assert p1 == p2
    import inspect
    assert "arm" not in inspect.signature(EX.placebo_distribution).parameters, (
        "the placebo must not accept a single fixed arm")


# =====================================================================================================
# POSITION-SPECIFIC MANIFESTS REACH THE MODEL
# =====================================================================================================
def test_position_specific_arm4_columns_reach_the_design_matrix(small_panel, coach_a):
    sub = small_panel[small_panel.bucket == "veteran"]
    _rb, rb_feats = EX.attach_coach_features(sub, coach_a, "ARM_4", "RB")
    _wr, wr_feats = EX.attach_coach_features(sub, coach_a, "ARM_4", "WR")
    _te, te_feats = EX.attach_coach_features(sub, coach_a, "ARM_4", "TE")
    assert rb_feats != wr_feats and len(te_feats) == 8
    assert any("rb_carry_share" in c for c in rb_feats)
    assert not any("rb_carry_share" in c for c in wr_feats)


def test_selected_arm_features_are_appended_after_the_baseline(small_panel, coach_a, arm0):
    spec = arm0[("RB", "veteran")]
    sub = small_panel[small_panel.bucket == "veteran"]
    _j, cf = EX.attach_coach_features(sub, coach_a, "ARM_5", "RB")
    feats = spec["feature_cols"] + cf
    assert feats[:32] == spec["feature_cols"], "the baseline order must be preserved exactly"
    assert feats[32:] == AF.arm5_features("RB")


# =====================================================================================================
# NO PRODUCTION WRITES / STOP CONDITION / DETERMINISM
# =====================================================================================================
def test_real_fit_is_blocked_by_a_default_closed_double_lock(monkeypatch):
    assert EX.REAL_FIT_AUTHORIZED is False
    assert EX.real_fit_is_unlocked() is False
    with pytest.raises(RuntimeError, match="NOT AUTHORIZED"):
        EX.assemble_real_panel()
    # the env switch ALONE must not unlock it
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    assert EX.real_fit_is_unlocked() is False
    with pytest.raises(RuntimeError, match="NOT AUTHORIZED"):
        EX.assemble_real_panel()
    # the constant ALONE must not unlock it either
    monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True)
    assert EX.real_fit_is_unlocked() is False
    with pytest.raises(RuntimeError, match="NOT AUTHORIZED"):
        EX.assemble_real_panel()
    # both locks open -> authorization passes, and the real path is still unimplemented here
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    assert EX.real_fit_is_unlocked() is True
    with pytest.raises(NotImplementedError):
        EX.assemble_real_panel()


def test_the_wrong_env_token_does_not_unlock(monkeypatch):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, "yes")
    assert EX.real_fit_is_unlocked() is False


V39_MODULES = ("build_arm_features_v39.py", "run_coach_projection_experiment_v39.py")
# Callees that would read a real fantasy outcome.
BANNED_CALLEES = {"load_player_stats", "season_total_target", "load_pbp_stats"}
# Real-outcome payload tokens that could only appear in code as a column/file access.
BANNED_CODE_TOKENS = {"season_dataset_2014_2026.csv", "season_dataset_2014_2025.csv",
                      "sleeper_pts_half_ppr", "target_ppg", "target_games", "half_ppr"}


def _executable_ast(path):
    """Parse, then strip every docstring so DOCUMENTING the boundary is not mistaken for crossing it.

    The audit RECORD must name `season_total_target()` and `season_dataset_*.csv` -- that is its whole
    job. What must not exist is a CALL or a data access. Only executable nodes are scanned.
    """
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:]
    return tree


def test_no_v39_module_ever_CALLS_a_real_outcome_source():
    import ast
    for mod in V39_MODULES:
        tree = _executable_ast(COACH / mod)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert name not in BANNED_CALLEES, f"{mod} calls {name}() — a real-outcome source"
            if name in ("read_csv", "read_parquet"):
                blob = ast.dump(node)
                assert "season_dataset" not in blob, f"{mod} reads the real player panel"


def test_no_real_outcome_token_is_used_as_a_FILE_READ_OR_COLUMN_ACCESS():
    """Prose naming the outcome inside the audit RECORD is required; a data ACCESS is forbidden.

    Only two positions can actually read an outcome: a string handed to a reader call, and a string
    used as a subscript (`df["target_ppg"]`). Descriptive dict values are neither.
    """
    import ast
    readers = {"read_csv", "read_parquet", "open", "read_json", "load_player_stats"}
    for mod in V39_MODULES:
        tree = _executable_ast(COACH / mod)
        for node in ast.walk(tree):
            probes = []
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if name in readers:
                    probes = [a.value for a in node.args
                              if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            elif isinstance(node, ast.Subscript):
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    probes = [sl.value]
                elif isinstance(sl, (ast.List, ast.Tuple)):
                    probes = [e.value for e in sl.elts
                              if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            for p in probes:
                for tok in BANNED_CODE_TOKENS:
                    assert tok not in p, (
                        f"{mod} accesses the real-outcome token {tok!r} (position: {p!r})")


def test_the_boundary_IS_documented_in_both_modules():
    """The complement of the two tests above: the boundary must be stated, not merely obeyed."""
    for mod in V39_MODULES:
        src = (COACH / mod).read_text(encoding="utf-8")
        assert "NO FANTASY OUTCOME" in src.upper()


def test_audit_and_spec_refuse_to_write_a_repo_artifact():
    with pytest.raises(RuntimeError, match="five new repo data artifacts"):
        EX.audit_production(write=True)
    with pytest.raises(RuntimeError, match="five new repo data artifacts"):
        EX.experiment_spec(write=True)


def test_audit_scopes_its_no_categorical_no_weight_claims_to_the_arm0_family():
    """The legacy seasonal_projections family DOES use categoricals and DOES fit with
    sample_weight=games. The audit must not generalise Arm 0's contract to the whole repo."""
    a = EX.audit_production()
    two = a["TWO_ARCHITECTURES_EXIST_IN_THIS_REPO"]
    legacy = two["legacy_family_NOT_USED"]
    assert "sample_weight" in legacy["IMPORTANT"]
    assert "cat_features" in legacy["IMPORTANT"] or "categorical" in legacy["IMPORTANT"]
    assert "PPG * games" in legacy["architecture"]
    assert a["categorical_handling_arm0"].startswith("NONE")
    assert a["sample_weights_arm0"].startswith("NONE")
    assert "NOT used by Arm 0" in a["prediction_target"]["ppg_games_total_composition"]


def test_audit_records_the_clipping_asymmetry():
    a = EX.audit_production()
    clip = a["transforms_and_clipping"]["prediction_clipping"]
    assert "walk_forward" in clip and "UNCLIPPED" in clip
    src = (COACH.parent / "build_rb_projection.py").read_text(encoding="utf-8")
    wf = src.split("def walk_forward", 1)[1].split("\ndef ", 1)[0]
    assert "clip" not in wf, "the evaluation path must remain unclipped for this claim to hold"
    assert "np.clip" in src.split("def _score_bundle", 1)[1].split("\n# repo-facing", 1)[0]


def test_audit_flags_the_cosmetic_bundle_note_mismatch():
    a = EX.audit_production()
    d = a["code_vs_bundle_disagreements"]["bundle_note_text"]
    assert "COSMETIC" in d and "RB season-total" in d
    arm0 = EX.arm0_definition()
    assert "RB season-total" in arm0[("QB", "veteran")]["note"], (
        "the QB bundle really does carry the RB note text")


def test_all_players_on_a_team_season_receive_one_identical_bundle(small_panel, coach_a):
    """Team-season features must REPLICATE to every player row without fan-out or divergence."""
    sub = small_panel[small_panel.bucket == "veteran"]
    joined, feats = EX.attach_coach_features(sub, coach_a, "ARM_5", "RB")
    assert len(joined) == len(sub), "a fan-out would change the row count"
    g = joined.groupby(["season", "team"])[feats].nunique(dropna=False)
    assert (g <= 1).all().all(), "players on one team-season got different bundles"
    counts = joined.groupby(["season", "team"]).size()
    assert (counts == sub.groupby(["season", "team"]).size()).all()


def test_no_production_artifact_changes(small_panel, coach_a, arm0):
    before = EX.assert_no_production_writes()
    EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                      bootstrap_draws=50, run_placebo=False, verbose=False)
    EX.assert_no_production_writes(before)


# =====================================================================================================
# THE FROZEN TEN-CONDITION PRIMARY VERDICT (prereg §7)
# =====================================================================================================
COHORT_ROWS, NONCOHORT_ROWS = 24, 24   # RB cohort is 24, so 48 rows/season splits exactly


def _mk_outer(seasons=None, sel_scale=0.80, noncohort_sel_scale=None, worse_seasons=(),
              arm0_rank_scramble=True):
    """Deterministic outer frame with directly controlled per-row errors.

    Cohort rows drive conditions 1/3/4/5; non-cohort rows drive 6/7. Expected statistics are
    recomputed with plain numpy in each test, never by calling the function under test.
    """
    seasons = list(EX.OUTER_SEASONS if seasons is None else seasons)
    noncohort_sel_scale = sel_scale if noncohort_sel_scale is None else noncohort_sel_scale
    rows = []
    for Y in seasons:
        scale = 1.25 if Y in worse_seasons else sel_scale   # >1 => selected is WORSE that season
        for grp, n, sc in (("cohort", COHORT_ROWS, scale),
                           ("non", NONCOHORT_ROWS, noncohort_sel_scale)):
            y = np.linspace(200.0, 400.0, n) if grp == "cohort" else np.linspace(10.0, 60.0, n)
            e0 = np.full(n, 10.0)
            if grp == "cohort" and arm0_rank_scramble:
                # ARM_0 keeps |error| = 10 but flips sign in a fixed alternating pattern, which
                # degrades its within-season RANK while leaving its MAE at exactly 10.
                e0 = np.where(np.arange(n) % 2 == 0, 10.0, -10.0)
            for i in range(n):
                rows.append(dict(season=Y, team=f"T{i % 8:02d}", player_id=f"{grp}_{Y}_{i}",
                                 y=float(y[i]), pred_ARM_0=float(y[i] + e0[i]),
                                 pred_selected=float(y[i] + 10.0 * sc),
                                 in_cohort=(grp == "cohort")))
    return pd.DataFrame(rows)


def _boot(ci_hi=-0.5):
    return {u: dict(ci_hi=ci_hi, ci_lo=ci_hi - 1.0, observed_diff=ci_hi - 0.5, p_value=0.01)
            for u in EX.CLUSTER_UNITS}


def _placebo(observed=0.9, p95=0.2, draws=200):
    return dict(observed=observed, p95=p95, draws=draws)


def _folds(n_nonbaseline=8, seasons=None):
    seasons = list(EX.OUTER_SEASONS if seasons is None else seasons)
    return {Y: ("ARM_3" if i < n_nonbaseline else "ARM_0") for i, Y in enumerate(seasons)}


def _verdict(**kw):
    f = kw.pop("frame", None)
    if f is None:
        f = _mk_outer()
    return EX.primary_verdict("RB", f, kw.pop("boot", _boot()), kw.pop("placebo", _placebo()),
                              kw.pop("folds", _folds()), **kw)


def test_a_fixture_engineered_to_satisfy_all_ten_conditions_passes():
    v = _verdict()
    assert v["n_conditions_passed"] == 10, v["failure_reasons"]
    assert v["verdict"] == "DEVELOPMENTAL CANDIDATE"
    assert v["challenger"] == "nested_selected_design_a"
    assert v["improvement_statistic"] == EX.IMPROVEMENT_STATISTIC


def test_c1_requires_a_three_percent_pooled_top_cohort_improvement():
    f = _mk_outer(sel_scale=0.80)
    c = f[f.in_cohort]
    exp = ((np.abs(c.pred_ARM_0 - c.y).mean() - np.abs(c.pred_selected - c.y).mean())
           / np.abs(c.pred_ARM_0 - c.y).mean())
    assert exp >= 0.03
    assert _verdict(frame=f)["c1_top_cohort_improves_3pct"] is True
    f2 = _mk_outer(sel_scale=0.99)          # ~1% gain
    v2 = _verdict(frame=f2)
    assert v2["c1_top_cohort_improves_3pct"] is False
    assert v2["verdict"].startswith("NO")
    assert "c1_top_cohort_improves_3pct" in v2["failure_reasons"]


def test_c2_requires_both_clustered_upper_bounds_below_zero():
    assert _verdict(boot=_boot(ci_hi=-0.5))["c2_both_clustered_ci_upper_below_zero"] is True
    assert _verdict(boot=_boot(ci_hi=0.01))["c2_both_clustered_ci_upper_below_zero"] is False
    mixed = {"player": dict(ci_hi=-0.5), "team_season": dict(ci_hi=0.2)}
    assert _verdict(boot=mixed)["c2_both_clustered_ci_upper_below_zero"] is False
    one = {"player": dict(ci_hi=-0.5)}       # a missing cluster unit cannot pass
    assert _verdict(boot=one)["c2_both_clustered_ci_upper_below_zero"] is False


def test_c3_requires_six_of_eight_outer_seasons():
    ok = _mk_outer(worse_seasons=(2018, 2019))            # 6 of 8 improve
    v = _verdict(frame=ok)
    assert v["n_outer_seasons_improved"] == 6 and v["c3_improves_6_of_8_outer_seasons"] is True
    bad = _mk_outer(worse_seasons=(2018, 2019, 2020))     # only 5
    v2 = _verdict(frame=bad)
    assert v2["n_outer_seasons_improved"] == 5 and v2["c3_improves_6_of_8_outer_seasons"] is False


def test_c4_requires_four_of_five_recent_seasons():
    bad = _mk_outer(worse_seasons=(2024, 2025))           # 2 of the 5 recent seasons worsen
    v = _verdict(frame=bad)
    assert v["n_recent_seasons_improved"] == 3
    assert v["c4_improves_4_of_5_recent_seasons"] is False
    ok = _mk_outer(worse_seasons=(2025,))
    assert _verdict(frame=ok)["c4_improves_4_of_5_recent_seasons"] is True


def test_c5_requires_a_spearman_gain_of_0p005():
    ok = _mk_outer(arm0_rank_scramble=True)
    v = _verdict(frame=ok)
    assert v["mean_within_season_spearman_gain"] >= 0.005
    assert v["c5_top_cohort_spearman_gain_0p005"] is True
    flat = _mk_outer(arm0_rank_scramble=False)   # both arms perfectly monotone -> zero gain
    v2 = _verdict(frame=flat)
    assert abs(v2["mean_within_season_spearman_gain"]) < 1e-12
    assert v2["c5_top_cohort_spearman_gain_0p005"] is False


def test_c6_and_c7_limit_full_panel_damage():
    f = _mk_outer(sel_scale=0.80, noncohort_sel_scale=8.0)   # non-cohort rows get much worse
    v = _verdict(frame=f)
    assert v["full_panel_mae_delta"] > EX.PASS_MAX_FULL_PANEL_MAE_WORSENING
    assert v["c6_full_panel_mae_worsens_le_0p25"] is False
    assert v["full_panel_rmse_relative_delta"] > EX.PASS_MAX_FULL_PANEL_RMSE_WORSENING
    assert v["c7_full_panel_rmse_worsens_le_1pct"] is False
    clean = _mk_outer(sel_scale=0.80)
    v2 = _verdict(frame=clean)
    assert v2["c6_full_panel_mae_worsens_le_0p25"] is True
    assert v2["c7_full_panel_rmse_worsens_le_1pct"] is True


def test_c8_requires_a_nonbaseline_arm_in_four_of_eight_folds():
    assert _verdict(folds=_folds(4))["c8_nonbaseline_arm_in_4_of_8_folds"] is True
    v = _verdict(folds=_folds(3))
    assert v["n_nonbaseline_folds"] == 3
    assert v["c8_nonbaseline_arm_in_4_of_8_folds"] is False
    assert _verdict(folds=_folds(0))["c8_nonbaseline_arm_in_4_of_8_folds"] is False


def test_c9_requires_beating_the_placebo_95th_percentile():
    assert _verdict(placebo=_placebo(observed=0.9, p95=0.2))["c9_beats_placebo_p95"] is True
    assert _verdict(placebo=_placebo(observed=0.1, p95=0.2))["c9_beats_placebo_p95"] is False
    # zero draws cannot pass: an unrun placebo is not a passed placebo
    assert _verdict(placebo=_placebo(draws=0))["c9_beats_placebo_p95"] is False
    assert _verdict(placebo=dict(observed=0.9, p95=np.nan,
                                draws=200))["c9_beats_placebo_p95"] is False


def test_c10_fails_when_an_integrity_assertion_fails():
    v = _verdict(integrity_ok=False, integrity_detail="a production pkl changed")
    assert v["c10_all_assertions_pass"] is False
    assert v["integrity_detail"] == "a production pkl changed"
    assert v["verdict"].startswith("NO")


def test_every_condition_can_fail_independently():
    """Each of the ten flips on its own; none is dead code and none is silently coupled."""
    cases = {
        "c1_top_cohort_improves_3pct": dict(frame=_mk_outer(sel_scale=0.99)),
        "c2_both_clustered_ci_upper_below_zero": dict(boot=_boot(0.1)),
        "c3_improves_6_of_8_outer_seasons": dict(
            frame=_mk_outer(worse_seasons=(2018, 2019, 2020))),
        "c4_improves_4_of_5_recent_seasons": dict(frame=_mk_outer(worse_seasons=(2024, 2025))),
        "c5_top_cohort_spearman_gain_0p005": dict(frame=_mk_outer(arm0_rank_scramble=False)),
        "c6_full_panel_mae_worsens_le_0p25": dict(frame=_mk_outer(noncohort_sel_scale=8.0)),
        "c7_full_panel_rmse_worsens_le_1pct": dict(frame=_mk_outer(noncohort_sel_scale=8.0)),
        "c8_nonbaseline_arm_in_4_of_8_folds": dict(folds=_folds(3)),
        "c9_beats_placebo_p95": dict(placebo=_placebo(observed=0.0)),
        "c10_all_assertions_pass": dict(integrity_ok=False),
    }
    for cond, kw in cases.items():
        v = _verdict(**kw)
        assert v[cond] is False, f"{cond} did not fail under its targeted perturbation"
        assert cond in v["failure_reasons"]
        assert v["verdict"].startswith("NO")


def test_a_fixed_arm_cannot_rescue_a_failed_nested_selected_result():
    """A brilliant fixed arm sits in the frame; the verdict must still read only pred_selected."""
    f = _mk_outer(sel_scale=0.99)                 # nested-selected barely improves -> c1 fails
    f["pred_ARM_3"] = f["y"]                      # a perfect fixed arm
    f["pred_ARM_5"] = f["y"]
    v = _verdict(frame=f)
    assert v["c1_top_cohort_improves_3pct"] is False
    assert v["verdict"].startswith("NO")
    baseline = _verdict(frame=_mk_outer(sel_scale=0.99))
    for k in ("top_cohort_abs_improvement", "top_cohort_rel_improvement", "n_conditions_passed"):
        assert v[k] == baseline[k], "a fixed-arm column changed the primary verdict"


def test_design_b_cannot_affect_the_verdict(small_panel, coach_a, coach_b):
    a = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=50, placebo_draws=2, verbose=False)
    b = EX.run_experiment(small_panel, coach_a, coach_b, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=50, placebo_draws=2, verbose=False)
    assert len(a["verdict"]) == 1 and len(b["verdict"]) == 1
    pd.testing.assert_frame_equal(a["verdict"], b["verdict"])
    assert set(b["verdict"].design) == {AF.DESIGN_A}
    assert set(b["verdict"].challenger) == {"nested_selected_design_a"}


def test_verdict_is_emitted_by_run_experiment(small_panel, coach_a):
    res = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                            bootstrap_draws=50, placebo_draws=2, verbose=False)
    assert "verdict" in res and len(res["verdict"]) == 1
    row = res["verdict"].iloc[0]
    for c in ("c1_top_cohort_improves_3pct", "c10_all_assertions_pass", "verdict",
              "failure_reasons", "n_conditions_passed"):
        assert c in res["verdict"].columns
    assert row["integrity_ok"] is True or row["integrity_ok"] == True  # noqa: E712


def test_spec_pins_all_ten_pass_thresholds_and_the_improvement_statistic():
    s = EX.experiment_spec()
    r = s["primary_pass_rule_ten_conditions"]
    assert r["c1_top_cohort_improves_3pct"] == 0.03
    assert r["c3_improves_6_of_8_outer_seasons"] == 6
    assert r["c4_improves_4_of_5_recent_seasons"] == 4
    assert r["c5_top_cohort_spearman_gain"] == 0.005
    assert r["c6_full_panel_mae_worsens_at_most"] == 0.25
    assert r["c7_full_panel_rmse_worsens_at_most_relative"] == 0.01
    assert r["c8_nonbaseline_arm_in_at_least_folds"] == 4
    assert r["c9_beats_placebo_percentile"] == 95
    assert "NESTED-SELECTED" in r["scope"] and "rescue" in r["scope"]
    i = s["improvement_statistic"]
    assert i["name"] == "pooled_top_cohort_mae_reduction"
    assert "POOLED" in i["definition"]
    assert set(i["used_identically_for"]) == {"the §7(1) 3% rule", "the §7(9) permutation placebo"}


def test_the_improvement_statistic_is_pooled_not_a_per_season_mean():
    """Seasons of unequal cohort size must be weighted by ROWS, which is what pooled means."""
    f = pd.DataFrame([
        dict(season=2018, y=0.0, pred_ARM_0=10.0, pred_selected=0.0, in_cohort=True),
        dict(season=2019, y=0.0, pred_ARM_0=10.0, pred_selected=10.0, in_cohort=True),
        dict(season=2019, y=0.0, pred_ARM_0=10.0, pred_selected=10.0, in_cohort=True),
        dict(season=2019, y=0.0, pred_ARM_0=10.0, pred_selected=10.0, in_cohort=True),
    ])
    pooled = EX.top_cohort_improvement(f)
    assert pooled == pytest.approx(10.0 - 7.5)         # rows: (10,10,10,10) vs (0,10,10,10)
    per_season_mean = np.mean([10.0, 0.0])
    assert pooled != pytest.approx(per_season_mean)


# =====================================================================================================
# PLACEBO — must follow the NESTED-SELECTED pipeline, not a modal fixed arm
# =====================================================================================================
def test_placebo_reruns_nested_selection_and_returns_fold_specific_picks(small_panel, coach_a,
                                                                        arm0):
    dist, picks = EX.placebo_distribution(small_panel, coach_a, "RB", [2018, 2019], arm0,
                                          draws=2, seed=5)
    assert len(dist) == 2 and len(picks) == 2
    for p in picks:
        assert set(p) == {2018, 2019}, "every draw must select per OUTER FOLD"
        assert all(a in AF.ARMS for a in p.values())


def test_placebo_can_select_different_arms_in_different_folds(small_panel, coach_a, arm0,
                                                             monkeypatch):
    """Regression guard for the modal-fixed-arm bug: force fold-specific selections and prove the
    placebo honours them rather than collapsing to one arm."""
    forced = {2018: "ARM_2", 2019: "ARM_4"}
    seen = []

    real_outer = EX.outer_predictions

    def fake_select(scores):
        Y = fake_select.current
        return forced[Y], "forced by test", scores

    def spy_outer(panel, coach, position, Y, a0, arms=None):
        fake_select.current = Y
        seen.append((Y, tuple(arms or [])))
        return real_outer(panel, coach, position, Y, a0, arms=arms)

    # `inner_scores` runs first for each fold, so set the fold marker there
    real_inner = EX.inner_scores

    def spy_inner(panel, coach, position, Y, a0, verbose=False):
        fake_select.current = Y
        return real_inner(panel, coach, position, Y, a0, verbose=False)

    monkeypatch.setattr(EX, "inner_scores", spy_inner)
    monkeypatch.setattr(EX, "select_arm", fake_select)
    monkeypatch.setattr(EX, "outer_predictions", spy_outer)

    dist, picks = EX.placebo_distribution(small_panel, coach_a, "RB", [2018, 2019], arm0,
                                          draws=1, seed=7)
    assert picks == [forced], f"placebo did not follow fold-specific selections: {picks}"
    asked = {Y: arms for Y, arms in seen}
    assert "ARM_2" in asked[2018] and "ARM_4" in asked[2019]
    assert len(dist) == 1


def test_arm0_and_therefore_the_cohort_are_invariant_under_permutation(small_panel, coach_a, arm0):
    """ARM_0 carries no coaching feature, so permuting bundles cannot move it. That is what makes the
    observed statistic and every placebo draw comparable on identical rows."""
    pc = EX.permute_team_bundles(coach_a, seed=11)
    a = EX.outer_predictions(small_panel, coach_a, "RB", 2019, arm0, arms=["ARM_0"])["ARM_0"]
    b = EX.outer_predictions(small_panel, pc, "RB", 2019, arm0, arms=["ARM_0"])["ARM_0"]
    pd.testing.assert_frame_equal(a, b)
    ca = a.rename(columns={"pred": "pred_ARM_0"})
    cb = b.rename(columns={"pred": "pred_ARM_0"})
    assert (EX.baseline_cohort_mask(ca) == EX.baseline_cohort_mask(cb)).all()


def test_placebo_row_records_the_nested_selected_challenger(small_panel, coach_a):
    res = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                            bootstrap_draws=50, placebo_draws=2, verbose=False)
    p = res["placebo"].iloc[0]
    assert p["challenger"] == "nested_selected_design_a"
    assert p["improvement_statistic"] == EX.IMPROVEMENT_STATISTIC
    assert "observed_fold_selections" in res["placebo"].columns
    assert p["draws"] == 2


def test_observed_statistic_and_placebo_use_the_same_function(small_panel, coach_a, arm0):
    m, picks = EX.nested_selected_outer_frame(small_panel, coach_a, "RB", [2019], arm0)
    res = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                            bootstrap_draws=50, run_placebo=False, verbose=False)
    assert res["verdict"].iloc[0]["top_cohort_abs_improvement"] == pytest.approx(
        EX.top_cohort_improvement(m))


# =====================================================================================================
# FULL ORDERED X REACHES fit()
# =====================================================================================================
def test_manifest_full_model_x_is_exactly_what_reaches_fit(small_panel, coach_a, arm0):
    """For every available (position, bucket, arm) the manifest's full X must equal the column list
    the harness actually hands to the production fitter, in order."""
    man = json.loads((DATA / "arm_feature_manifest_v39.json").read_text(encoding="utf-8"))
    captured = {}
    real_prep = EX._production_engine()[0]._prep

    for (pos, bucket), spec in arm0.items():
        sub = small_panel[(small_panel.position == pos) & (small_panel.bucket == bucket)]
        for arm in AF.ARMS:
            feats = spec["feature_cols"] + AF.arm_features(arm, pos)
            captured[(pos, bucket, arm)] = feats
            assert man["full_model_x"][f"{pos}/{bucket}"][arm] == feats
        if len(sub):
            joined, cf = EX.attach_coach_features(sub, coach_a, "ARM_5", pos)
            x = spec["feature_cols"] + cf
            Xtr, _Xte = real_prep("lightgbm", joined, joined.head(1), x)
            assert Xtr.shape[1] == len(x) == len(man["full_model_x"][f"{pos}/{bucket}"]["ARM_5"])
    assert man["full_model_x"]["QB/rookie"] is None
    assert "ABSENT" in man["missing_production_paths"]["QB/rookie"]


def test_manifest_pins_baselines_per_bucket_and_arm0_equals_the_baseline():
    man = json.loads((DATA / "arm_feature_manifest_v39.json").read_text(encoding="utf-8"))
    assert man["arm0_baseline_counts"] == {"QB/veteran": 32, "RB/veteran": 32, "RB/rookie": 41,
                                          "WR/veteran": 32, "WR/rookie": 44,
                                          "TE/veteran": 32, "TE/rookie": 44}
    for key, arms in man["full_model_x"].items():
        if arms is None:
            continue
        assert arms["ARM_0"] == man["arm0_baseline_features"][key]
        for arm, x in arms.items():
            nb = len(man["arm0_baseline_features"][key])
            assert x[:nb] == man["arm0_baseline_features"][key]
            assert len(set(x)) == len(x)


# =====================================================================================================
# v3.9b §1 — EXACT DENOMINATORS
# =====================================================================================================
def test_the_complete_eight_and_five_fixture_still_passes():
    v = _verdict()
    assert v["required_outer_seasons"] == 8 and v["required_recent_seasons"] == 5
    assert v["outer_panel_complete"] and v["recent_panel_complete"] and v["fold_set_complete"]
    assert v["denominator_problems"] == ""
    assert v["n_conditions_passed"] == 10 and v["verdict"] == "DEVELOPMENTAL CANDIDATE"


def test_six_improving_seasons_supplied_as_only_six_seasons_fails_c3():
    """The v3.9a defect: counting improvements without requiring the frozen denominator."""
    six = [2018, 2019, 2020, 2021, 2022, 2023]
    f = _mk_outer(seasons=six)                     # all six improve
    v = _verdict(frame=f, folds=_folds(8, seasons=six))
    assert v["n_outer_seasons_improved"] == 6, "six seasons really do improve"
    assert v["outer_panel_complete"] is False
    assert v["c3_improves_6_of_8_outer_seasons"] is False, (
        "6 improvements out of a SIX-season panel must not satisfy '6 of 8'")
    assert "outer seasons MISSING [2024, 2025]" in v["denominator_problems"]
    assert v["verdict"].startswith("NO")


def test_four_improving_recent_seasons_supplied_as_only_four_fails_c4():
    seasons = [2018, 2019, 2020, 2021, 2022, 2023, 2024]     # 2025 absent -> only 4 recent present
    f = _mk_outer(seasons=seasons)
    v = _verdict(frame=f, folds=_folds(8, seasons=seasons))
    assert v["n_recent_seasons_improved"] == 4, "four recent seasons really do improve"
    assert v["recent_panel_complete"] is False
    assert v["c4_improves_4_of_5_recent_seasons"] is False, (
        "4 improvements out of a FOUR-season recent panel must not satisfy '4 of 5'")
    assert "recent seasons MISSING [2025]" in v["denominator_problems"]


def test_four_nonbaseline_selections_across_only_four_folds_fails_c8():
    folds = {2018: "ARM_3", 2019: "ARM_3", 2020: "ARM_3", 2021: "ARM_3"}
    v = _verdict(folds=folds)
    assert v["n_nonbaseline_folds"] == 4, "four nonbaseline selections really are present"
    assert v["fold_set_complete"] is False
    assert v["c8_nonbaseline_arm_in_4_of_8_folds"] is False, (
        "4 nonbaseline out of FOUR folds must not satisfy '4 of 8'")
    assert "fold selections MISSING" in v["denominator_problems"]


def test_unexpected_seasons_cannot_yield_a_candidate():
    f = _mk_outer(seasons=list(EX.OUTER_SEASONS) + [2026])
    v = _verdict(frame=f, folds=_folds(8, seasons=list(EX.OUTER_SEASONS) + [2026]))
    assert v["outer_panel_complete"] is False
    assert "outer seasons UNEXPECTED [2026]" in v["denominator_problems"]
    assert v["fold_set_complete"] is False
    assert "fold selections UNEXPECTED [2026]" in v["denominator_problems"]
    assert v["verdict"] != "DEVELOPMENTAL CANDIDATE"


def test_duplicate_player_season_cohort_rows_cannot_yield_a_candidate():
    f = _mk_outer()
    dup = pd.concat([f, f[f.in_cohort].head(3)], ignore_index=True)
    v = _verdict(frame=dup)
    assert v["duplicate_player_season_rows"] == 3
    assert v["outer_panel_complete"] is False and v["recent_panel_complete"] is False
    assert v["c3_improves_6_of_8_outer_seasons"] is False
    assert v["c4_improves_4_of_5_recent_seasons"] is False
    assert "DUPLICATE" in v["denominator_problems"]
    assert v["verdict"] != "DEVELOPMENTAL CANDIDATE"


def test_missing_fold_selections_cannot_yield_a_candidate():
    folds = {Y: "ARM_3" for Y in EX.OUTER_SEASONS if Y != 2022}
    v = _verdict(folds=folds)
    assert v["fold_set_complete"] is False
    assert "fold selections MISSING [2022]" in v["denominator_problems"]
    assert v["verdict"] != "DEVELOPMENTAL CANDIDATE"


def test_the_frozen_required_season_sets_are_exactly_the_prereg_windows():
    assert EX.REQUIRED_OUTER_SEASONS == (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
    assert EX.REQUIRED_RECENT_SEASONS == (2021, 2022, 2023, 2024, 2025)


# =====================================================================================================
# v3.9b §2 — CONDITION 10 IS A REAL RUNTIME PREFLIGHT
# =====================================================================================================
PROTECTED_DATA_FILES = tuple(AF.UPSTREAM_PROTECTED) + tuple(EX.V39_ARTIFACT_HASHES)


@pytest.fixture
def temp_data(tmp_path):
    """A COPY of the artifacts the preflight reads, so corruption tests never touch canon."""
    import shutil
    d = tmp_path / "data"
    d.mkdir()
    for f in PROTECTED_DATA_FILES:
        shutil.copy2(DATA / f, d / f)
    return d


def test_preflight_passes_on_the_real_artifacts():
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["n_checks"] == len(EX.PREFLIGHT_CHECKS)
    assert set(pf["checks"]) == set(EX.PREFLIGHT_CHECKS)
    assert pf["all_ok"] is True, pf["failures"]


def test_preflight_passes_on_an_untouched_copy(temp_data):
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is True, pf["failures"]


def test_pinned_v39_hashes_match_disk():
    """The pins cannot go stale silently."""
    import hashlib
    for f, h in EX.V39_ARTIFACT_HASHES.items():
        got = hashlib.md5((DATA / f).read_bytes()).hexdigest()
        assert got == h, f"{f}: pinned {h}, on disk {got}"


@pytest.mark.parametrize("victim,check", [
    ("arm3_stage2_effects_v38.csv", "protected_hashes"),
    ("team_coach_features_design_a_v39.csv", "v39_artifacts_pinned"),
])
def test_preflight_fails_when_a_pinned_artifact_is_corrupted(temp_data, victim, check):
    (temp_data / victim).write_text("corrupted\n", encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert pf["checks"][check]["ok"] is False, pf["failures"]


def test_preflight_fails_on_an_unauthorized_sixth_artifact(temp_data):
    (temp_data / "sneaky_extra_v39.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["no_unauthorized_v39_artifact"]["ok"] is False
    assert "sneaky_extra_v39.csv" in pf["checks"]["no_unauthorized_v39_artifact"]["detail"]


def test_preflight_fails_on_wrong_row_count(temp_data):
    a = pd.read_csv(temp_data / "team_coach_features_design_a_v39.csv")
    a.head(400).to_csv(temp_data / "team_coach_features_design_a_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["feature_table_keys_and_rows"]["ok"] is False
    assert "400 rows" in pf["checks"]["feature_table_keys_and_rows"]["detail"]


def test_preflight_fails_when_design_a_identity_coverage_moves(temp_data):
    a = pd.read_csv(temp_data / "team_coach_features_design_a_v39.csv")
    m = (a.season == 2019) & (a.caller_identity_known == 0)
    a.loc[a.index[m][:5], "caller_identity_known"] = 1
    a.to_csv(temp_data / "team_coach_features_design_a_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["design_a_outer_identity_coverage"]["ok"] is False
    assert "157/256" in pf["checks"]["design_a_outer_identity_coverage"]["detail"]


def test_preflight_fails_when_unknown_routing_is_broken(temp_data):
    a = pd.read_csv(temp_data / "team_coach_features_design_a_v39.csv")
    m = a.caller_identity_known == 0
    a.loc[a.index[m][:3], "caller_is_head_coach"] = 0.0     # asserts delegation with no evidence
    a.to_csv(temp_data / "team_coach_features_design_a_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["unknown_and_no_history_routing"]["ok"] is False


def test_preflight_fails_when_a_model_feature_is_nan(temp_data):
    a = pd.read_csv(temp_data / "team_coach_features_design_a_v39.csv")
    a.loc[a.index[0], "pc_career_off_rank_pct"] = np.nan
    a.to_csv(temp_data / "team_coach_features_design_a_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["unknown_and_no_history_routing"]["ok"] is False


def test_preflight_fails_when_the_manifest_full_x_drifts(temp_data):
    man = json.loads((temp_data / "arm_feature_manifest_v39.json").read_text(encoding="utf-8"))
    man["full_model_x"]["RB/veteran"]["ARM_3"] = ["not", "the", "real", "columns"]
    (temp_data / "arm_feature_manifest_v39.json").write_text(json.dumps(man), encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["manifest_full_x_matches_bundles"]["ok"] is False
    assert "RB/veteran/ARM_3" in pf["checks"]["manifest_full_x_matches_bundles"]["detail"]


def test_preflight_fails_when_qb_rookie_is_not_null(temp_data):
    man = json.loads((temp_data / "arm_feature_manifest_v39.json").read_text(encoding="utf-8"))
    man["full_model_x"]["QB/rookie"] = {a: [] for a in AF.ARMS}
    (temp_data / "arm_feature_manifest_v39.json").write_text(json.dumps(man), encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["manifest_qb_rookie_null"]["ok"] is False


def test_preflight_fails_when_coverage_stops_reconciling(temp_data):
    cov = pd.read_csv(temp_data / "arm_feature_coverage_v39.csv")
    m = (cov.design == "design_a") & (cov.arm == "ARM_1") & (cov.identity_state == "all")
    cov.loc[cov.index[m][0], "caller_identity_known"] = 99
    cov.to_csv(temp_data / "arm_feature_coverage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["coverage_reconciles"]["ok"] is False


def test_preflight_fails_when_lineage_timing_is_violated(temp_data):
    lin = pd.read_csv(temp_data / "arm_feature_lineage_v39.csv")
    i = lin.index[lin.record_kind == "caller_contribution"][0]
    lin.loc[i, "source_season"] = int(lin.loc[i, "season"]) + 1
    lin.to_csv(temp_data / "arm_feature_lineage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["lineage_strict_timing"]["ok"] is False


def test_preflight_fails_when_contribution_lineage_stops_reconciling(temp_data):
    lin = pd.read_csv(temp_data / "arm_feature_lineage_v39.csv")
    i = lin.index[(lin.record_kind == "caller_contribution") & (lin.included_in_career == 1)][0]
    lin.loc[i, "pbp_games"] = float(lin.loc[i, "pbp_games"]) + 7
    lin.to_csv(temp_data / "arm_feature_lineage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["contribution_lineage_reconciles"]["ok"] is False


def test_preflight_requires_the_pipeline_assertions_to_have_RUN():
    zero = {k: 0 for k in EX._PIPELINE_ASSERTIONS}
    pf = EX.preflight(pipeline_assertions=zero)
    assert pf["checks"]["pipeline_timing_assertions_ran"]["ok"] is False
    assert "never executed" in pf["checks"]["pipeline_timing_assertions_ran"]["detail"]
    ran = {k: 3 for k in EX._PIPELINE_ASSERTIONS}
    pf2 = EX.preflight(pipeline_assertions=ran)
    assert pf2["checks"]["pipeline_timing_assertions_ran"]["ok"] is True


def test_the_pipeline_actually_increments_every_assertion_counter(small_panel, coach_a):
    EX.reset_pipeline_assertions()
    EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                      bootstrap_draws=50, run_placebo=False, verbose=False)
    for k, v in EX._PIPELINE_ASSERTIONS.items():
        assert v > 0, f"assertion site {k} never ran"


def test_c10_is_the_preflight_and_run_experiment_reports_it(small_panel, coach_a):
    res = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                            bootstrap_draws=50, run_placebo=False, verbose=False)
    assert "preflight" in res and len(res["preflight"]) == 1
    p = res["preflight"].iloc[0]
    assert p["n_checks"] == len(EX.PREFLIGHT_CHECKS)
    assert bool(p["all_ok"]) is True
    for c in EX.PREFLIGHT_CHECKS:
        assert bool(p[f"chk_{c}"]) is True, c
    assert bool(res["verdict"].iloc[0]["c10_all_assertions_pass"]) is True


def test_c10_fails_when_the_preflight_fails():
    v = _verdict(integrity_ok=False, integrity_detail="lineage_strict_timing: 4 rows bad")
    assert v["c10_all_assertions_pass"] is False
    assert "lineage_strict_timing" in v["integrity_detail"]


# =====================================================================================================
# v3.9b §3 — RUN MODES (the real-authorization paradox)
# =====================================================================================================
@pytest.mark.parametrize("mode,constant,env,expect", [
    # synthetic_prefit: both locks MUST be closed
    (EX.RUN_MODE_SYNTHETIC_PREFIT, False, False, True),
    (EX.RUN_MODE_SYNTHETIC_PREFIT, True, False, False),
    (EX.RUN_MODE_SYNTHETIC_PREFIT, False, True, False),
    (EX.RUN_MODE_SYNTHETIC_PREFIT, True, True, False),
    # authorized_real: both locks MUST be open
    (EX.RUN_MODE_AUTHORIZED_REAL, False, False, False),
    (EX.RUN_MODE_AUTHORIZED_REAL, True, False, False),
    (EX.RUN_MODE_AUTHORIZED_REAL, False, True, False),
    (EX.RUN_MODE_AUTHORIZED_REAL, True, True, True),
])
def test_run_mode_truth_table(mode, constant, env, expect):
    ok, detail = EX.validate_run_mode(mode, lock_state=(constant, env))
    assert ok is expect, f"{mode} c={constant} e={env}: {detail}"
    if not ok:
        assert detail


def test_an_unknown_run_mode_fails_closed():
    for bad in ("real", "prefit", "", None, "AUTHORIZED_REAL"):
        ok, detail = EX.validate_run_mode(bad, lock_state=(True, True))
        assert ok is False and "unknown run_mode" in detail


def test_authorized_real_is_reachable_so_a_candidate_verdict_is_possible():
    """The v3.9a paradox: C10 hard-failed on an unlocked gate, so an authorized real run could never
    produce DEVELOPMENTAL CANDIDATE. Under authorized_real, open locks must be VALID."""
    ok, _ = EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL, lock_state=(True, True))
    assert ok is True
    pf = EX.preflight(run_mode=EX.RUN_MODE_SYNTHETIC_PREFIT, require_pipeline_assertions=False)
    assert pf["checks"]["run_mode_locks"]["ok"] is True     # this pass: prefit, locks shut


def test_this_pass_is_synthetic_prefit_with_both_locks_shut():
    assert EX.DEFAULT_RUN_MODE == EX.RUN_MODE_SYNTHETIC_PREFIT
    assert EX.real_fit_lock_state() == (False, False)
    assert EX.real_fit_is_unlocked() is False
    ok, _ = EX.validate_run_mode(EX.RUN_MODE_SYNTHETIC_PREFIT)
    assert ok is True


def test_run_experiment_rejects_an_invalid_mode(small_panel, coach_a):
    with pytest.raises(AssertionError, match="invalid run mode"):
        EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=20, run_placebo=False, verbose=False,
                          run_mode="whatever")


def test_no_run_mode_relaxes_a_non_lock_check(temp_data):
    """The mode governs the lock expectation ONLY."""
    (temp_data / "arm_feature_coverage_v39.csv").write_text("x\n1\n", encoding="utf-8")
    for mode in EX.RUN_MODES:
        pf = EX.preflight(run_mode=mode, data_dir=temp_data, require_pipeline_assertions=False)
        assert pf["checks"]["v39_artifacts_pinned"]["ok"] is False, mode
        assert pf["all_ok"] is False, mode


def test_the_locks_are_not_opened_anywhere_in_this_pass():
    """AST-level: no executable statement assigns True to the lock constant.

    A plain substring scan is wrong here — the module docstring and the refusal message legitimately
    quote `REAL_FIT_AUTHORIZED = True` when documenting what a FUTURE authorized run must do.
    """
    import ast
    assert EX.REAL_FIT_AUTHORIZED is False
    assert os.environ.get(EX.REAL_FIT_ENV_SWITCH) != EX.REAL_FIT_ENV_TOKEN
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "REAL_FIT_AUTHORIZED":
                    assigns.append(node.value)
    assert len(assigns) == 1, f"expected exactly one assignment, found {len(assigns)}"
    assert isinstance(assigns[0], ast.Constant) and assigns[0].value is False
    # and nothing sets the env token either
    assert "environ[" not in src and "setenv" not in src and "putenv" not in src


# =====================================================================================================
# v3.9c §1 — coverage_reconciles is a FULL-FRAME check, not a spot-check
# =====================================================================================================
def test_coverage_reconciles_is_a_full_frame_comparison():
    pf = EX.preflight(require_pipeline_assertions=False)
    d = pf["checks"]["coverage_reconciles"]
    assert d["ok"] is True
    assert "full-frame" in d["detail"]
    assert "728 rows" in d["detail"] and "columns" in d["detail"]


def test_THE_EXACT_CODEX_CASE_corrupting_ARM_2_known_with_history_now_fails(temp_data):
    """Codex's reproduction: change `ARM_2 / known_with_history / n_team_seasons` to 999.

    v3.9b reported `coverage_reconciles = True` because it only inspected
    `ARM_1 / identity_state == "all"` and only two columns. The SEMANTIC check must fail now, not
    merely the byte-hash check.
    """
    cov = pd.read_csv(temp_data / "arm_feature_coverage_v39.csv")
    m = ((cov.design == "design_a") & (cov.arm == "ARM_2")
         & (cov.identity_state == "known_with_history"))
    assert m.any()
    cov.loc[cov.index[m][0], "n_team_seasons"] = 999
    cov.to_csv(temp_data / "arm_feature_coverage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["coverage_reconciles"]["ok"] is False, (
        "the SEMANTIC coverage check must catch this, not just the hash")
    assert "n_team_seasons" in pf["checks"]["coverage_reconciles"]["detail"]
    assert "ARM_2" in pf["checks"]["coverage_reconciles"]["detail"]


@pytest.mark.parametrize("col,value", [
    ("row_coverage_rate", 0.5),                       # a RATE
    ("caller_known_no_history", 77),                  # an identity-state count
    ("league_prior_rate_for_this_arm", 0.99),         # an arm-level rate
    ("mean_caller_history_games", 1234.5),            # a MEAN
    ("n_features_TE", 99),                            # an arm feature count
    ("arm_uses_caller_identity", 0),                  # a caller-dependence flag (ARM_4 is 1)
    ("rows_at_league_prior_for_this_arm", 3),         # league-prior row count
    ("caller_effect_nonzero", 31),                    # an effect count
])
def test_corrupting_any_coverage_column_fails_the_semantic_check(temp_data, col, value):
    cov = pd.read_csv(temp_data / "arm_feature_coverage_v39.csv")
    m = (cov.design == "design_b_oracle") & (cov.arm == "ARM_4") & (cov.identity_state == "unknown")
    assert m.any()
    cov.loc[cov.index[m][0], col] = value
    cov.to_csv(temp_data / "arm_feature_coverage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["coverage_reconciles"]["ok"] is False, col
    assert col in pf["checks"]["coverage_reconciles"]["detail"]


def test_coverage_schema_key_and_duplicate_corruptions_are_caught(temp_data):
    p = temp_data / "arm_feature_coverage_v39.csv"
    base = pd.read_csv(p)

    base.drop(columns=["row_coverage_rate"]).to_csv(p, index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    d = pf["checks"]["coverage_reconciles"]["detail"]
    assert pf["checks"]["coverage_reconciles"]["ok"] is False
    assert "schema" in d or "row_coverage_rate" in d

    pd.concat([base, base.head(1)], ignore_index=True).to_csv(p, index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["coverage_reconciles"]["ok"] is False
    d = pf["checks"]["coverage_reconciles"]["detail"]
    assert "row count" in d or "duplicate" in d

    dropped = base[~((base.design == "design_a") & (base.arm == "ARM_5")
                     & (base.identity_state == "unknown"))]
    dropped.to_csv(p, index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["coverage_reconciles"]["ok"] is False


def test_the_builder_and_the_preflight_share_one_coverage_derivation():
    """No parallel re-implementation: `compare_coverage` regenerates with `coverage()` itself."""
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    body = src.split("def compare_coverage", 1)[1].split("\ndef ", 1)[0]
    assert "coverage({DESIGN_A:" in body.replace(" ", "").replace("\n", "") or \
challenge_ok(body), "compare_coverage must call coverage() rather than re-derive"
    pf_src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    cov_body = pf_src.split("def _cov_rec", 1)[1].split("check(", 1)[0]
    assert "AF.compare_coverage" in cov_body


def challenge_ok(body):
    return "coverage(" in body and "DESIGN_A" in body


# =====================================================================================================
# v3.9c §2 — preflight FAILS CLOSED and always returns the structured record
# =====================================================================================================
def test_THE_EXACT_CODEX_CASE_deleting_design_a_returns_instead_of_raising(temp_data):
    """Codex's reproduction: delete the Design A table. v3.9b raised FileNotFoundError."""
    (temp_data / "team_coach_features_design_a_v39.csv").unlink()
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)   # must NOT raise
    assert isinstance(pf, dict) and set(pf["checks"]) == set(EX.PREFLIGHT_CHECKS)
    assert pf["all_ok"] is False
    assert pf["checks"]["v39_artifacts_pinned"]["ok"] is False
    assert pf["checks"]["v39_artifacts_readable"]["ok"] is False
    for dep in ("feature_table_keys_and_rows", "design_a_outer_identity_coverage",
                "unknown_and_no_history_routing", "coverage_reconciles",
                "contribution_lineage_reconciles"):
        c = pf["checks"][dep]
        assert c["ok"] is False, dep
        assert "blocked by design_a" in c["detail"], f"{dep}: {c['detail']}"
        assert "FileNotFoundError" in c["detail"]


@pytest.mark.parametrize("victim,blocked_key,dependents", [
    ("team_coach_features_design_a_v39.csv", "design_a",
     ("feature_table_keys_and_rows", "coverage_reconciles")),
    ("team_coach_features_design_b_oracle_v39.csv", "design_b",
     ("feature_table_keys_and_rows", "coverage_reconciles")),
    ("arm_feature_coverage_v39.csv", "coverage", ("coverage_reconciles",)),
    ("arm_feature_lineage_v39.csv", "lineage",
     ("lineage_strict_timing", "lineage_states_the_primary_policy")),
    ("arm_feature_manifest_v39.json", "manifest",
     ("manifest_full_x_matches_bundles", "manifest_qb_rookie_null", "forbidden_feature_policy")),
])
def test_a_missing_artifact_blocks_its_dependents_without_crashing(temp_data, victim, blocked_key,
                                                                  dependents):
    (temp_data / victim).unlink()
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert pf["checks"]["v39_artifacts_readable"]["ok"] is False
    for dep in dependents:
        assert pf["checks"][dep]["ok"] is False, dep
        assert f"blocked by {blocked_key}" in pf["checks"][dep]["detail"], dep


@pytest.mark.parametrize("victim,blocked_key", [
    ("team_coach_features_design_b_oracle_v39.csv", "design_b"),
    ("arm_feature_coverage_v39.csv", "coverage"),
    ("arm_feature_lineage_v39.csv", "lineage"),
])
def test_a_malformed_csv_fails_closed(temp_data, victim, blocked_key):
    (temp_data / victim).write_text('a,b\n"unterminated,1\n\x00\x00\n', encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert pf["checks"]["v39_artifacts_readable"]["ok"] is False
    assert blocked_key in pf["checks"]["v39_artifacts_readable"]["detail"]


def test_malformed_manifest_json_fails_closed(temp_data):
    (temp_data / "arm_feature_manifest_v39.json").write_text("{not: valid json,,,", encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert pf["checks"]["v39_artifacts_readable"]["ok"] is False
    for dep in ("manifest_full_x_matches_bundles", "manifest_qb_rookie_null"):
        assert pf["checks"][dep]["ok"] is False
        assert "blocked by manifest" in pf["checks"][dep]["detail"]


def test_a_schema_invalid_csv_fails_closed(temp_data):
    """Right filename, valid CSV, wrong columns."""
    (temp_data / "team_coach_features_design_a_v39.csv").write_text(
        "alpha,beta\n1,2\n", encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert "schema invalid" in pf["checks"]["v39_artifacts_readable"]["detail"]
    assert "blocked by design_a" in pf["checks"]["feature_table_keys_and_rows"]["detail"]


def test_an_empty_csv_fails_closed(temp_data):
    (temp_data / "arm_feature_coverage_v39.csv").write_text(
        "design,arm,season,identity_state\n", encoding="utf-8")
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["all_ok"] is False
    assert "is empty" in pf["checks"]["v39_artifacts_readable"]["detail"]


def test_preflight_never_raises_for_any_single_missing_artifact(temp_data):
    import shutil
    keep = temp_data.parent / "keep"
    shutil.copytree(temp_data, keep)
    for victim in EX.V39_ARTIFACT_HASHES:
        shutil.rmtree(temp_data)
        shutil.copytree(keep, temp_data)
        (temp_data / victim).unlink()
        pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
        assert isinstance(pf, dict) and pf["all_ok"] is False, victim
        assert set(pf["checks"]) == set(EX.PREFLIGHT_CHECKS), victim


# =====================================================================================================
# v3.9c §3 — the lineage artifact must STATE the primary policy
# =====================================================================================================
def test_preflight_validates_the_lineage_policy_semantically():
    pf = EX.preflight(require_pipeline_assertions=False)
    assert "lineage_states_the_primary_policy" in pf["checks"]
    assert pf["checks"]["lineage_states_the_primary_policy"]["ok"] is True


def test_a_reintroduced_source_date_gate_in_lineage_fails_the_semantic_check(temp_data):
    """Not caught by the MD5 alone if someone rebuilt and repinned."""
    lin = pd.read_csv(temp_data / "arm_feature_lineage_v39.csv")
    i = lin.index[(lin.record_kind == "feature_definition")
                  & (lin.feature == "pc_career_epa_play_z")][0]
    lin.loc[i, "timing_rule"] = ("seasons < Y; Design A additionally requires source upper bound "
                                 "<= Y cutoff")
    lin.to_csv(temp_data / "arm_feature_lineage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["lineage_states_the_primary_policy"]["ok"] is False
    assert "pc_career_epa_play_z" in pf["checks"]["lineage_states_the_primary_policy"]["detail"]


def test_a_reintroduced_gated_openers_note_fails_the_semantic_check(temp_data):
    lin = pd.read_csv(temp_data / "arm_feature_lineage_v39.csv")
    i = lin.index[lin.feature == "pc_tenure_current_team"][0]
    lin.loc[i, "note"] = "Design A openers are themselves gated on Y's cutoff"
    lin.to_csv(temp_data / "arm_feature_lineage_v39.csv", index=False)
    pf = EX.preflight(data_dir=temp_data, require_pipeline_assertions=False)
    assert pf["checks"]["lineage_states_the_primary_policy"]["ok"] is False
    assert "openers are themselves gated" in \
        pf["checks"]["lineage_states_the_primary_policy"]["detail"]


# =====================================================================================================
# v3.9c §5 — the no-real-outcome boundary is PRODUCTION logic that tests call
# =====================================================================================================
def test_no_real_outcome_access_passes_on_the_real_modules():
    ok, detail = EX.no_real_outcome_access()
    assert ok is True, detail
    assert "authorization-first" in detail


def test_c10_includes_the_no_real_outcome_check():
    pf = EX.preflight(require_pipeline_assertions=False)
    assert "no_real_outcome_access" in pf["checks"]
    assert pf["checks"]["no_real_outcome_access"]["ok"] is True


@pytest.mark.parametrize("injection,fragment", [
    ("df = pd.read_csv('season_dataset_2014_2026.csv')", "season_dataset_2014_2026.csv"),
    ("y = ps['half_ppr']", "half_ppr"),
    ("t = season_total_target()", "season_total_target"),
    ("s = nfl.load_player_stats(seasons=[2024])", "load_player_stats"),
    ("v = df['target_ppg']", "target_ppg"),
])
def test_an_injected_real_outcome_path_is_detected(injection, fragment):
    """Injected into PURE SOURCE — canonical files are never modified."""
    good = {m: (COACH / m).read_text(encoding="utf-8") for m in EX.V39_SOURCE_MODULES}
    ok, _ = EX.no_real_outcome_access(sources=good)
    assert ok is True
    bad = dict(good)
    bad["build_arm_features_v39.py"] += f"\n\ndef _injected():\n    {injection}\n"
    ok2, detail = EX.no_real_outcome_access(sources=bad)
    assert ok2 is False, f"{injection} was not detected"
    assert fragment in detail


def test_documenting_the_boundary_is_not_mistaken_for_crossing_it():
    """A docstring naming the outcome must NOT trip the check — that is how the audit records it."""
    good = {m: (COACH / m).read_text(encoding="utf-8") for m in EX.V39_SOURCE_MODULES}
    doc = dict(good)
    doc["build_arm_features_v39.py"] += (
        '\n\ndef _documented():\n    """Never reads season_dataset_2014_2026.csv or target_ppg."""\n'
        "    return None\n")
    ok, detail = EX.no_real_outcome_access(sources=doc)
    assert ok is True, detail


def _swap_assemble(src, replacement):
    """Replace the whole `assemble_real_panel` def with a syntactically valid variant."""
    import re
    pat = re.compile(r"\ndef assemble_real_panel\(.*?\n(?=\n\n(?:# |def |[A-Z_]+ ))",
                     re.DOTALL)
    out, n = pat.subn("\n" + replacement, src)
    assert n == 1, f"expected exactly one assemble_real_panel def, replaced {n}"
    return out


def test_assemble_real_panel_must_stay_authorization_first_and_unimplemented():
    good = {m: (COACH / m).read_text(encoding="utf-8") for m in EX.V39_SOURCE_MODULES}
    key = "run_coach_projection_experiment_v39.py"

    # authorization no longer FIRST
    reordered = dict(good)
    reordered[key] = _swap_assemble(good[key],
                                    "def assemble_real_panel(*_a, **_k):\n"
                                    "    panel = 1\n"
                                    "    require_real_fit_authorization()\n"
                                    "    raise NotImplementedError('x')\n")
    ok, detail = EX.no_real_outcome_access(sources=reordered)
    assert ok is False and "authorization" in detail, detail

    # no longer unimplemented
    implemented = dict(good)
    implemented[key] = _swap_assemble(good[key],
                                      "def assemble_real_panel(*_a, **_k):\n"
                                      "    require_real_fit_authorization()\n"
                                      "    return None\n")
    ok2, detail2 = EX.no_real_outcome_access(sources=implemented)
    assert ok2 is False and "NotImplementedError" in detail2, detail2

    # the real source satisfies both
    ok3, _ = EX.no_real_outcome_access(sources=good)
    assert ok3 is True


def test_an_attempt_to_open_the_lock_in_source_is_detected():
    good = {m: (COACH / m).read_text(encoding="utf-8") for m in EX.V39_SOURCE_MODULES}
    flipped = dict(good)
    flipped["run_coach_projection_experiment_v39.py"] += "\nREAL_FIT_AUTHORIZED = True\n"
    ok, detail = EX.no_real_outcome_access(sources=flipped)
    assert ok is False and "REAL_FIT_AUTHORIZED" in detail

    env = dict(good)
    env["run_coach_projection_experiment_v39.py"] += (
        "\ndef _sneak():\n    os.environ[REAL_FIT_ENV_SWITCH] = REAL_FIT_ENV_TOKEN\n")
    ok2, detail2 = EX.no_real_outcome_access(sources=env)
    assert ok2 is False and "environ" in detail2


def test_the_tests_and_c10_share_one_definition():
    """The boundary logic lives in the runtime module; the tests must not re-implement it."""
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    assert "def no_real_outcome_access" in src
    assert 'check("no_real_outcome_access", no_real_outcome_access)' in src
    this = pathlib.Path(__file__).read_text(encoding="utf-8")
    # a DEFINITION at column 0 in the test file would mean a parallel implementation; a mention
    # inside an assertion is fine
    assert not re.search(r"(?m)^def no_real_outcome_access", this), (
        "the test must call the module's definition, not redefine it")


def test_the_harness_writes_nothing_at_all():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    assert not re.findall(r'DATA / "([^"]+)"\)\.write_text', src)
    assert not re.findall(r'to_csv\(DATA / "([^"]+)"', src)
    for bad in ("MODELS /", "RESULTS", "SEAS /"):
        assert f'to_csv({bad}' not in src
    assert ".to_parquet(" not in src
    assert "joblib.dump" not in src, "the harness must never re-serialise a model bundle"


def test_audit_and_spec_artifacts_are_deterministic():
    a1 = json.dumps(EX.audit_production(write=False), sort_keys=True)
    a2 = json.dumps(EX.audit_production(write=False), sort_keys=True)
    assert a1 == a2
    s1 = json.dumps(EX.experiment_spec(write=False), sort_keys=True)
    s2 = json.dumps(EX.experiment_spec(write=False), sort_keys=True)
    assert s1 == s2


def test_experiment_is_deterministic_on_identical_inputs(small_panel, coach_a):
    a = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=100, run_placebo=False, verbose=False)
    b = EX.run_experiment(small_panel, coach_a, None, outer_seasons=[2019], positions=["RB"],
                          bootstrap_draws=100, run_placebo=False, verbose=False)
    for k in ("selection", "metrics", "bootstrap"):
        pd.testing.assert_frame_equal(a[k], b[k])


def test_spec_pins_every_frozen_constant():
    s = EX.experiment_spec(write=False)
    assert s["real_fit_authorized"] is False
    assert s["outer_seasons"] == list(range(2018, 2026))
    assert s["recent_panel"] == list(range(2021, 2026))
    assert s["full_panel_tolerance_mae"] == 0.25
    assert s["min_relative_top_cohort_improvement"] == 0.01
    assert s["tie_band_mae"] == 0.25
    assert s["cohort_sizes"] == {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
    assert s["bootstrap_draws"] == 20_000 and s["bootstrap_seed"] == 20260728
    assert s["placebo"]["draws"] == 200
    assert "TEAM-LEVEL" in s["placebo"]["kind"]
    assert s["primary_design"] == AF.DESIGN_A and s["oracle_design"] == AF.DESIGN_B
    assert s["arm3_structurally_unavailable_before_target_season"] == 2018
    assert s["worked_example_outer_2018"] == [{"train": [2014, 2015], "validate": 2016},
                                              {"train": [2014, 2015, 2016], "validate": 2017}]


def test_arm3_is_structurally_unavailable_in_the_outer_2018_inner_folds(coach_a):
    """Both inner folds for outer 2018 validate on a season with no Arm 3 effects, so Arm 3 and
    Arm 5 carry no caller/context effect information there. Stated, not hidden."""
    folds = EX.expanding_inner_folds(range(2014, 2026), 2018)
    seasons = {v for _t, v in folds} | {s for t, _v in folds for s in t}
    sub = coach_a[coach_a.season.isin(seasons)]
    assert (sub.arm3_effects_available == 0).all()
    assert (sub.caller_adjusted_offense_effect == 0).all()
