"""PHASE E — end-to-end synthetic tests that call the PRODUCTION orchestration entry points.

These invoke `run_arm3_v38.run_stage1` / `run_stage2` — the same functions the real build calls —
so a pass here exercises the production code path, not a parallel re-implementation.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))

import build_reliability as BR   # noqa: E402
import run_arm3_v38 as RUN       # noqa: E402
import stage_models as SM        # noqa: E402

TEAMS = [f"T{i:02d}" for i in range(8)]


def _panel(seasons, seed=0):
    """Synthetic Stage 1 input with all 17 predictors present."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i, t in enumerate(TEAMS):
            r = dict(season=s, team=t, epa_play=rng.normal(0.02 * i, 0.05))
            for c in SM.STAGE1_NUMERIC:
                r[c] = rng.normal()
            for c in SM.STAGE1_BINARY:
                r[c] = float(rng.integers(0, 2))
            r["prior_qb_id"] = f"qb_{s}_{i}" if s >= max(seasons) else f"qb_{i}"
            rows.append(r)
    return pd.DataFrame(rows)


def _expo(seasons, callers=True):
    rows = []
    for s in seasons:
        for i, t in enumerate(TEAMS):
            if callers:
                rows.append(dict(season=s, team=t, person_id=f"cal_{i % 3}",
                                 role=BR.ROLE_CALLER, exposure=1.0))
            if i % 2 == 0:
                rows.append(dict(season=s, team=t, person_id=f"hc_{i % 2}",
                                 role=BR.ROLE_HC_CTX, exposure=1.0))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Stage 1 timing
def test_stage1_training_excludes_target_and_future_seasons():
    df = _panel(range(2010, 2021))
    res, tune, folds, schemas = RUN.run_stage1(df, targets=[2018], verbose=False)
    assert set(res.season) == {2018}
    assert res.last_train_season.max() == 2017
    assert res.first_train_season.min() == 2010
    assert schemas["2018"]["last_train_season"] == 2017


def test_final_preprocessing_uses_all_and_only_seasons_before_S():
    df = _panel(range(2010, 2021))
    _r, _t, _f, sch = RUN.run_stage1(df, targets=[2019], verbose=False)
    s = sch["2019"]
    assert s["first_train_season"] == 2010 and s["last_train_season"] == 2018
    assert s["n_train_rows"] == 9 * len(TEAMS)


def test_target_season_qb_identities_never_enter_the_vocabulary():
    """Target-season QB ids are unique by construction; none may appear in the learned vocab."""
    df = _panel(range(2010, 2021))
    _r, _t, _f, sch = RUN.run_stage1(df, targets=[2020], verbose=False)
    vocab = set(sch["2020"]["qb_vocabulary"])
    assert not any(v.startswith("qb_2020_") for v in vocab)
    assert SM.UNSEEN_QB in vocab and SM.MISSING_QB in vocab


def test_frozen_stage1_minimums_skip_targets_without_enough_history():
    df = _panel(range(2014, 2020))
    res, _t, _f, _s = RUN.run_stage1(df, targets=[2016], verbose=False)
    assert res.empty, "a target with too little history must be SKIPPED, not silently relaxed"


def test_every_candidate_and_fold_loss_reaches_the_tuning_artifacts():
    df = _panel(range(2010, 2021))
    res, tune, folds, _s = RUN.run_stage1(df, targets=[2019], verbose=False)
    assert len(tune) >= len(SM.ALPHA_GRID)
    assert set(tune.columns) >= {"target_season", "alpha", "season_avg_mse"}
    assert len(folds) == res.n_inner_folds.iloc[0]
    assert (folds.n_val_rows > 0).all()


def test_stage1_residual_identity_holds():
    df = _panel(range(2010, 2021))
    res, _t, _f, _s = RUN.run_stage1(df, targets=[2018, 2019], verbose=False)
    assert np.allclose(res.team_offense_residual,
                       res.relative_epa_play - res.predicted_relative_epa_play)
    assert np.allclose(res.relative_epa_play, res.epa_play - res.league_mean_epa_play)


def test_retired_drive_names_are_rejected_at_load(tmp_path):
    """A panel still carrying `points_per_drive` must fail loudly at load, not fit silently."""
    p = tmp_path / "panel.csv"
    c = tmp_path / "ctrl.csv"
    pd.DataFrame({"season": [2020], "team": ["T00"], "epa_play": [0.1],
                  "points_per_drive": [1.5]}).to_csv(p, index=False)
    pd.DataFrame({"season": [2020], "team": ["T00"]}).to_csv(c, index=False)
    with pytest.raises(AssertionError):
        RUN.load_stage1_inputs(panel_path=p, controls_path=c)


def test_duplicate_season_team_keys_are_rejected(tmp_path):
    p = tmp_path / "panel.csv"
    c = tmp_path / "ctrl.csv"
    pd.DataFrame({"season": [2020, 2020], "team": ["T00", "T00"],
                  "epa_play": [0.1, 0.2]}).to_csv(p, index=False)
    pd.DataFrame({"season": [2020], "team": ["T00"]}).to_csv(c, index=False)
    with pytest.raises(AssertionError):
        RUN.load_stage1_inputs(panel_path=p, controls_path=c)


# ---------------------------------------------------------------- Stage 2
def _resid(seasons, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame([dict(season=s, team=t, team_offense_residual=rng.normal(0, 0.05))
                         for s in seasons for t in TEAMS])


def test_stage2_retains_residual_rows_with_zero_identity_exposure():
    """THE ROW-UNIVERSE DEFECT: keys derived from exposure rows drop unknown-identity
    team-seasons entirely instead of keeping them as all-zero identity rows."""
    resid = _resid(range(2014, 2018))
    expo = _expo(range(2014, 2018))
    expo = expo[expo.team != "T07"]                      # T07 has NO identity exposure at all
    keys, X, names, _b = SM.stage2_design(expo, 2018, row_universe=resid)
    assert (keys.team == "T07").sum() == 4, "rows with zero identity exposure were dropped"
    i = keys.index[(keys.team == "T07") & (keys.season == 2015)][0]
    assert X[i].sum() == 0.0, "a zero-identity row must be all-zero, not absent"
    assert len(keys) == len(resid[resid.season < 2018])


def test_stage2_row_universe_defaults_to_exposure_when_not_supplied():
    resid = _resid(range(2014, 2018))
    expo = _expo(range(2014, 2018))
    expo = expo[expo.team != "T07"]
    keys, _X, _n, _b = SM.stage2_design(expo, 2018)       # no row_universe
    assert (keys.team == "T07").sum() == 0                # documents the old behaviour


def test_inner_validation_unseen_coach_routes_to_zero():
    """A caller present only in the validation season gets no column, hence zero contribution."""
    resid = _resid(range(2014, 2018))
    expo = _expo(range(2014, 2017))
    late = pd.DataFrame([dict(season=2017, team="T00", person_id="brand_new",
                              role=BR.ROLE_CALLER, exposure=1.0)])
    expo = pd.concat([expo, late], ignore_index=True)
    vocab = (sorted(expo[(expo.season < 2017) & (expo.role == BR.ROLE_CALLER)]
                    .person_id.unique()), [])
    assert "brand_new" not in vocab[0]
    keys, X, names, _b = SM.stage2_design(expo, 2018, persons_caller=vocab[0], persons_ctx=[],
                                          row_universe=resid)
    assert not any("brand_new" in n for n in names)
    i = keys.index[(keys.team == "T00") & (keys.season == 2017)][0]
    assert X[i].sum() == 0.0


def test_stage2_vocabularies_use_inner_training_data_only():
    resid = _resid(range(2014, 2020))
    expo = _expo(range(2014, 2020))
    c, coef, names, blocks, vocab = RUN._stage2_fit(resid, expo, [2014, 2015], 1.0, 1.0)
    seen = set(expo[expo.season.isin([2014, 2015])].person_id)
    assert all(n.split("__", 1)[1] in seen for n in names)


def test_stage2_end_to_end_produces_effects_and_diagnostics():
    resid = _resid(range(2014, 2020))
    expo = _expo(range(2014, 2020))
    eff, tune, folds = RUN.run_stage2(resid=resid, expo=expo, targets=[2019], verbose=False)
    assert not eff.empty
    assert set(eff.role) <= {BR.ROLE_CALLER, BR.ROLE_HC_CTX}
    for c in ("selected_alpha_caller", "selected_alpha_hc_context", "observed_exposure",
              "n_observed_team_seasons", "block_boundary_status", "n_inner_folds"):
        assert c in eff.columns
    assert len(tune) >= len(SM.ALPHA_GRID) ** 2
    assert len(folds) == eff.n_inner_folds.iloc[0]


# ---------------------------------------------------------------- joint alpha protocol
def test_joint_selection_finds_the_hand_calculated_best_pair():
    tgt_c, tgt_h = SM.ALPHA_GRID[8], SM.ALPHA_GRID[16]
    out = SM.select_alpha_pair(
        lambda ac, ah: (np.log10(ac) - np.log10(tgt_c)) ** 2
        + (np.log10(ah) - np.log10(tgt_h)) ** 2)
    assert np.isclose(out["alpha_caller"], tgt_c)
    assert np.isclose(out["alpha_hc_context"], tgt_h)
    assert out["extensions"] == {"caller_lo": 0, "caller_hi": 0, "hc_lo": 0, "hc_hi": 0}


def test_joint_exact_ties_follow_the_frozen_three_step_rule():
    """All pairs tie -> maximise the SUM of log alphas, i.e. the largest of both."""
    out = SM.select_alpha_pair(lambda ac, ah: 1.0)
    hi_c = SM._grid(out["final_caller_lo"], out["final_caller_hi"]).max()
    hi_h = SM._grid(out["final_hc_lo"], out["final_hc_hi"]).max()
    assert out["alpha_caller"] == hi_c and out["alpha_hc_context"] == hi_h

    # tie only along the caller axis -> larger alpha_caller wins, hc pinned by its own term
    tgt_h = SM.ALPHA_GRID[10]
    out2 = SM.select_alpha_pair(lambda ac, ah: (np.log10(ah) - np.log10(tgt_h)) ** 2)
    assert np.isclose(out2["alpha_hc_context"], tgt_h)
    assert out2["alpha_caller"] == SM._grid(out2["final_caller_lo"],
                                            out2["final_caller_hi"]).max()


def test_each_block_expands_its_boundary_independently():
    """Caller wants the ceiling; HC-context wants an interior value."""
    tgt_h = SM.ALPHA_GRID[10]
    out = SM.select_alpha_pair(
        lambda ac, ah: -np.log10(ac) + (np.log10(ah) - np.log10(tgt_h)) ** 2)
    assert out["extensions"]["caller_hi"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["extensions"]["hc_hi"] == 0 and out["extensions"]["hc_lo"] == 0
    assert out["caller_complete_pooling"] and not out["hc_complete_pooling"]


def test_both_boundaries_can_expand_in_the_same_iteration():
    out = SM.select_alpha_pair(lambda ac, ah: -(np.log10(ac) + np.log10(ah)))
    assert out["extensions"]["caller_hi"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["extensions"]["hc_hi"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["final_caller_hi"] == out["final_hc_hi"] == 8.0 + 2 * SM.EXTEND_DECADES


def test_persistent_upper_boundary_marks_only_the_affected_block():
    tgt_h = SM.ALPHA_GRID[6]
    out = SM.select_alpha_pair(
        lambda ac, ah: -np.log10(ac) + (np.log10(ah) - np.log10(tgt_h)) ** 2)
    assert out["caller_complete_pooling"] is True
    assert out["hc_complete_pooling"] is False
    assert out["caller_boundary_unresolved"] and not out["hc_boundary_unresolved"]


def test_opposite_directions_expand_independently():
    out = SM.select_alpha_pair(lambda ac, ah: np.log10(ac) - np.log10(ah))
    assert out["extensions"]["caller_lo"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["extensions"]["hc_hi"] == SM.MAX_EXTENSIONS_PER_DIRECTION


# ---------------------------------------------------------------- forbidden fields
def test_forbidden_fields_cannot_enter_stage1_or_stage2_X():
    for bad in ("observed_reliability", "observed_prior_games", "observed_games_log",
                "no_prior_history", "history_left_censored", "observable_prior_seasons",
                "hc_resume", "unknown_caller_hc_games"):
        with pytest.raises(AssertionError):
            BR.assert_design_matrix_is_clean(["caller_exposure", bad], "stage2")
        assert bad not in SM.STAGE1_PREDICTORS


def test_no_prior_history_is_routing_only():
    assert "no_prior_history" in BR.ROUTING_ONLY
    assert "no_prior_history" not in BR.MODEL_PREDICTORS
    assert "no_prior_history" not in SM.STAGE1_PREDICTORS


# ---------------------------------------------------------------- determinism
def test_two_identical_builds_are_byte_identical():
    df = _panel(range(2010, 2021))
    a = RUN.run_stage1(df, targets=[2019], verbose=False)
    b = RUN.run_stage1(df, targets=[2019], verbose=False)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])
    assert a[3] == b[3]

    resid, expo = _resid(range(2014, 2020)), _expo(range(2014, 2020))
    e1, t1, f1 = RUN.run_stage2(resid=resid, expo=expo, targets=[2019], verbose=False)
    e2, t2, f2 = RUN.run_stage2(resid=resid, expo=expo, targets=[2019], verbose=False)
    pd.testing.assert_frame_equal(e1, e2)
    pd.testing.assert_frame_equal(f1, f2)
