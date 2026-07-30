"""PHASE 1E/1F synthetic tests (prereg v3.7). NO REAL OUTCOMES ARE TOUCHED.

Covers the frozen pre-fit checklist: leakage, per-fold preprocessing, equal season weighting,
QB routing, same-season centering, exposure fidelity, HC==caller, unknown-caller neutrality, a
closed-form block-ridge check, penalty independence, forbidden columns, and the boundary/tie
protocol.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))

import build_reliability as BR       # noqa: E402
import stage_models as SM            # noqa: E402


# ---------------------------------------------------------------- Stage 1 target
def test_same_season_centering_gives_zero_league_mean():
    df = pd.DataFrame({"season": [2020] * 4 + [2021] * 3,
                       "team": list("ABCDEFG"),
                       "epa_play": [0.1, 0.2, -0.1, 0.0, 1.0, 2.0, 3.0]})
    out = SM.relative_epa_play(df)
    means = out.groupby("season").relative_epa_play.mean()
    assert np.allclose(means.values, 0.0, atol=1e-12)
    # centering is a within-season shift: spread is preserved
    for s, g in out.groupby("season"):
        assert np.isclose(g.relative_epa_play.std(ddof=0), g.epa_play.std(ddof=0))


def test_league_mean_is_outcome_normalization_not_a_predictor():
    assert "league_mean_epa_play" not in SM.STAGE1_PREDICTORS
    assert "relative_epa_play" not in SM.STAGE1_PREDICTORS


# ---------------------------------------------------------------- temporal CV
def test_no_validation_or_outer_season_reaches_training():
    seasons = list(range(2014, 2026))
    folds = SM.expanding_folds(seasons, target_season=2024)
    assert folds, "frozen minimums should be satisfiable here"
    for train, val in folds:
        assert max(train) < val, "training season >= validation season"
        assert val < 2024, "validation season reached the outer target season"
        assert 2024 not in train and 2025 not in train


def test_folds_are_expanding_and_never_train_on_the_future():
    folds = SM.expanding_folds(range(2014, 2026), target_season=2025)
    sizes = [len(t) for t, _ in folds]
    assert sizes == sorted(sizes) and len(set(sizes)) == len(sizes)   # strictly expanding
    for train, val in folds:
        assert all(s < val for s in train)


def test_frozen_minimums_return_no_folds_rather_than_shrinking():
    assert SM.expanding_folds([2014, 2015], target_season=2016) == []
    assert SM.expanding_folds([2014, 2015, 2016, 2017], target_season=2018,
                              min_validation_seasons=5) == []


def test_each_validation_season_gets_equal_tuning_weight():
    """A 1000-row season must not outweigh a 3-row season."""
    big = np.full(1000, 0.1)      # small errors, many rows
    small = np.full(3, 1.0)       # big errors, few rows
    season_avg = SM.season_averaged_mse([big, small])
    pooled = float(np.mean(np.concatenate([big, small]) ** 2))
    assert np.isclose(season_avg, (0.01 + 1.0) / 2)
    assert season_avg > pooled, "season averaging must not collapse to row pooling"


# ---------------------------------------------------------------- preprocessing
def _frame(n, qbs, seed=0):
    rng = np.random.default_rng(seed)
    d = {c: rng.normal(size=n) for c in SM.STAGE1_NUMERIC}
    d.update({c: rng.integers(0, 2, n).astype(float) for c in SM.STAGE1_BINARY})
    d["prior_qb_id"] = qbs
    return pd.DataFrame(d)


def test_preprocessing_learns_only_from_inner_training_rows():
    train = _frame(50, ["qb_a"] * 25 + ["qb_b"] * 25, seed=1)
    train.loc[:, "prior_epa_play"] = np.arange(50.0)
    pre = SM.Stage1Preprocessor().fit(train)
    med_train, mean_train = pre.medians_["prior_epa_play"], pre.mean_["prior_epa_play"]

    val = _frame(20, ["qb_a"] * 20, seed=2)
    val.loc[:, "prior_epa_play"] = np.arange(1000.0, 1020.0)   # wildly different scale
    pre.transform(val)
    assert pre.medians_["prior_epa_play"] == med_train
    assert pre.mean_["prior_epa_play"] == mean_train, "validation data moved the fitted scaler"


def test_missing_and_unseen_qb_routing():
    train = _frame(20, ["qb_a"] * 10 + ["qb_b"] * 10)
    pre = SM.Stage1Preprocessor().fit(train)
    val = _frame(3, ["qb_a", "qb_zzz_never_seen", None])
    Z = pre.transform(val)
    assert Z.loc[0, "qb__qb_a"] == 1.0
    assert Z.loc[1, f"qb__{SM.UNSEEN_QB}"] == 1.0, "unseen QB must route to the explicit level"
    assert Z.loc[2, f"qb__{SM.MISSING_QB}"] == 1.0
    assert "qb__qb_zzz_never_seen" not in Z.columns, "target-season category was learned"
    # unseen QB carries no learned identity: its own indicator is the only one lit
    assert Z.loc[1, [c for c in Z.columns if c.startswith("qb__")]].sum() == 1.0


def test_binary_columns_are_not_standardized():
    train = _frame(40, ["qb_a"] * 40)
    Z = SM.Stage1Preprocessor().fit(train).transform(train)
    for c in SM.STAGE1_BINARY:
        assert set(np.unique(Z[c])) <= {0.0, 1.0}


# ---------------------------------------------------------------- Stage 2 exposures
def _exposure(rows):
    return pd.DataFrame(rows, columns=["season", "team", "person_id", "role", "exposure"])


def test_exposure_weights_match_supplied_game_shares():
    e = _exposure([(2020, "AAA", "cal_x", BR.ROLE_CALLER, 0.75),
                   (2020, "AAA", "hc_y", BR.ROLE_HC_CTX, 0.75),
                   (2020, "BBB", "cal_z", BR.ROLE_CALLER, 1.0)])
    keys, X, names, blocks = SM.stage2_design(e, target_season=2021)
    col = dict(zip(names, range(len(names))))
    i = keys.index[(keys.season == 2020) & (keys.team == "AAA")][0]
    assert X[i, col["caller__cal_x"]] == 0.75
    assert X[i, col["hc_context__hc_y"]] == 0.75
    assert X.min() >= 0.0 and X.max() <= 1.0


def test_hc_equal_caller_gives_one_caller_contribution_and_no_context():
    """Self-calling HC: caller block only."""
    e = _exposure([(2020, "AAA", "coach_p", BR.ROLE_CALLER, 1.0)])
    _keys, X, names, _b = SM.stage2_design(e, target_season=2021)
    assert names == ["caller__coach_p"]
    assert X.shape == (1, 1) and X[0, 0] == 1.0
    assert not any(n.startswith("hc_context__") for n in names)


def test_unknown_caller_games_contribute_zero_to_both_blocks():
    """4 games, 2 with a known distinct caller and 2 unknown -> 0.5 / 0.5, never 1.0."""
    e = _exposure([(2020, "AAA", "cal_x", BR.ROLE_CALLER, 0.5),
                   (2020, "AAA", "hc_y", BR.ROLE_HC_CTX, 0.5)])
    _keys, X, names, _b = SM.stage2_design(e, target_season=2021)
    assert X.sum() == 1.0                       # 0.5 + 0.5, the unknown half contributes nothing
    assert set(names) == {"caller__cal_x", "hc_context__hc_y"}


def test_stage2_design_excludes_outer_and_future_seasons():
    e = _exposure([(2019, "AAA", "p", BR.ROLE_CALLER, 1.0),
                   (2020, "AAA", "p", BR.ROLE_CALLER, 1.0),
                   (2021, "AAA", "p", BR.ROLE_CALLER, 1.0)])
    keys, _X, _n, _b = SM.stage2_design(e, target_season=2020)
    assert set(keys.season) == {2019}


# ---------------------------------------------------------------- block ridge
def test_block_ridge_matches_closed_form_small_example():
    X = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    y = np.array([1.0, 2.0, 4.0])
    alphas = {"a": 2.0, "b": 7.0}
    block = {0: "a", 1: "b"}
    c, coef = SM.block_ridge(X, y, block, alphas)
    Xd = np.hstack([np.ones((3, 1)), X])
    pen = np.diag([0.0, 2.0, 7.0])                       # intercept UNPENALIZED
    expect = np.linalg.solve(Xd.T @ Xd + pen, Xd.T @ y)
    assert np.allclose([c, *coef], expect)


def test_intercept_is_unpenalized():
    X = np.zeros((5, 1))
    y = np.full(5, 3.0)
    c, coef = SM.block_ridge(X, y, {0: "a"}, {"a": 1e9})
    assert np.isclose(c, 3.0), "a huge penalty must not shrink the intercept"
    assert np.isclose(coef[0], 0.0)


def test_changing_alpha_caller_does_not_alter_the_hc_penalty():
    """Orthogonal blocks: the context coefficient must be invariant to alpha_caller."""
    X = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    y = np.array([1.0, 3.0, 2.0, 4.0])
    block = {0: "caller", 1: "hc_context"}
    _c1, b1 = SM.block_ridge(X, y, block, {"caller": 0.01, "hc_context": 5.0}, fit_intercept=False)
    _c2, b2 = SM.block_ridge(X, y, block, {"caller": 1e6, "hc_context": 5.0}, fit_intercept=False)
    assert np.isclose(b1[1], b2[1]), "alpha_caller leaked into the HC-context block"
    assert not np.isclose(b1[0], b2[0]), "alpha_caller had no effect on its own block"


def test_a_single_shared_penalty_is_not_used():
    """Two blocks with different support must be able to receive different penalties."""
    X = np.array([[1.0, 0.0], [0.0, 1.0]])
    y = np.array([1.0, 1.0])
    _c, b = SM.block_ridge(X, y, {0: "caller", 1: "hc_context"},
                           {"caller": 0.0, "hc_context": 100.0}, fit_intercept=False)
    assert b[0] > b[1], "blocks were shrunk identically"


# ---------------------------------------------------------------- alpha protocol
def test_interior_optimum_needs_no_extension():
    target = SM.ALPHA_GRID[12]
    out = SM.select_alpha(lambda a: (np.log10(a) - np.log10(target)) ** 2)
    assert np.isclose(out["alpha"], target)
    assert out["extensions_lo"] == out["extensions_hi"] == 0
    assert not out["boundary_unresolved"]


def test_upper_boundary_extends_then_records_complete_pooling():
    out = SM.select_alpha(lambda a: -np.log10(a))          # monotone: always wants more alpha
    assert out["extensions_hi"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["final_hi_exp"] == 8.0 + 2 * SM.EXTEND_DECADES
    assert out["effective_complete_pooling"] and out["boundary_unresolved"]


def test_lower_boundary_extends_at_most_twice():
    out = SM.select_alpha(lambda a: np.log10(a))
    assert out["extensions_lo"] == SM.MAX_EXTENSIONS_PER_DIRECTION
    assert out["final_lo_exp"] == -4.0 - 2 * SM.EXTEND_DECADES
    assert out["at_lower_boundary"]


def test_exact_ties_resolve_toward_the_larger_alpha():
    out = SM.select_alpha(lambda a: 1.0)                   # every alpha ties
    assert out["alpha"] == max(SM._grid(out["final_lo_exp"], out["final_hi_exp"]))


def test_grid_keeps_half_decade_spacing_after_extension():
    g = SM._grid(-8.0, 12.0)
    steps = np.diff(np.log10(g))
    assert np.allclose(steps, SM.GRID_STEP_DECADES)
    assert np.allclose(SM.ALPHA_GRID, SM._grid(-4.0, 8.0))


def test_all_candidates_and_fold_losses_are_persisted():
    out = SM.select_alpha(lambda a: (np.log10(a) - 2.0) ** 2)
    assert out["history"] and "alphas" in out["history"][0] and "scores" in out["history"][0]
    assert len(out["history"][0]["alphas"]) == len(SM.ALPHA_GRID)


def test_stage1_and_stage2_penalties_are_reported_separately():
    s1 = SM.select_alpha(lambda a: (np.log10(a) - 1.0) ** 2)
    s2c = SM.select_alpha(lambda a: (np.log10(a) - 3.0) ** 2)
    s2h = SM.select_alpha(lambda a: (np.log10(a) - 5.0) ** 2)
    diag = {"stage1_alpha": s1["alpha"], "alpha_caller": s2c["alpha"],
            "alpha_hc_context": s2h["alpha"]}
    assert len(set(diag.values())) == 3, "penalties collapsed into one another"


# ---------------------------------------------------------------- forbidden columns
def test_reliability_count_and_censoring_fields_cannot_enter_X():
    for bad in ("observed_reliability", "observed_prior_games", "observed_games_log",
                "observable_prior_seasons", "history_left_censored", "no_prior_history",
                "hc_resume", "unknown_caller_hc_games"):
        with pytest.raises(AssertionError):
            BR.assert_design_matrix_is_clean(["caller_exposure", bad], "stage2")


def test_stage2_design_matrix_passes_the_guard():
    e = _exposure([(2020, "AAA", "cal_x", BR.ROLE_CALLER, 1.0),
                   (2020, "BBB", "hc_y", BR.ROLE_HC_CTX, 0.5)])
    _k, _X, names, _b = SM.stage2_design(e, target_season=2021)
    assert BR.assert_design_matrix_is_clean(names, "stage2")


def test_stage1_predictor_list_contains_no_coaching_identity_or_reliability():
    for f in BR.FORBIDDEN_IN_X:
        assert f not in SM.STAGE1_PREDICTORS
    assert "prior_qb_id" in SM.STAGE1_PREDICTORS      # personnel control IS required
