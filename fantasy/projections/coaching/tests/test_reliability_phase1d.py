"""PHASE 1D registered tests — game-based reliability.

Covers the scenario list frozen for 1D: 16- and 17-game seasons, a midseason split spanning a bye,
caller change, HC change, HC taking over play-calling, unknown-caller segments, a person changing
teams, a person moving from OC-caller to HC-caller, playoff exclusion, and no duplicate game_ids
within a role block.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parent
COACH = HERE.parent
DATA = COACH / "data"
sys.path.insert(0, str(COACH))

import build_exposure as BE        # noqa: E402
import build_reliability as BR     # noqa: E402


@pytest.fixture(scope="module")
def rel():
    return pd.read_csv(DATA / "coach_reliability.csv")


@pytest.fixture(scope="module")
def gl():
    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    hc = pd.read_csv(DATA / "head_coach_games.csv")
    return BE.game_level_identity(hc, tbl)


def _syn(rows, season, team="SYN"):
    return pd.DataFrame([dict(season=season, team=team, week=w, game_id=f"g{season}{team}{w}",
                              hc_person_id=hc, caller_person_id=c) for w, hc, c in rows])


def _counts(gl_syn, Y):
    per = BR._per_season_counts(gl_syn)
    prior = per[per.season < Y]
    return (prior.groupby(["person_id", "role"])["games"].sum().to_dict())


# ------------------------------------------------------------------ timing
def test_no_row_uses_games_from_its_own_or_a_future_season(rel):
    bad = rel[rel.max_observed_season >= rel.target_season]
    assert bad.empty, f"{len(bad)} rows draw on season >= target_season"


def test_reliability_formula_is_exactly_g_over_g_plus_32(rel):
    expect = rel.observed_prior_games / (rel.observed_prior_games + BR.K_SHRINK)
    # 1 ULP tolerance: the artifact round-trips through CSV, so a value like 320/352 can come back
    # one bit off. Measured max deviation is 1.11e-16 -- representation, not arithmetic.
    assert np.allclose(rel.observed_reliability, expect, atol=1e-15, rtol=0)
    assert BR.K_SHRINK == 32


def test_counts_are_games_not_seasons(rel):
    """16 x n_seasons must never reproduce the counts -- that is the whole point of 1D."""
    r = rel[(rel.role == "hc_resume") & (rel.observed_prior_games > 0)]
    assert not (r.observed_prior_games == 16 * r.n_observed_prior_seasons).all()
    assert (r.observed_prior_games != 16 * r.n_observed_prior_seasons).any()


# ------------------------------------------------------------------ exact portability
def test_mcdaniel_exact_entering_2026(rel):
    r = rel[(rel.person_id == "mike_mcdaniel") & (rel.target_season == 2026)
            & (rel.role == "caller")].iloc[0]
    assert int(r.observed_prior_games) == 68
    assert r.observed_reliability == 68 / (68 + 32) == 0.68


def test_mcvay_exact_and_unified_across_teams_and_titles(rel):
    r = rel[(rel.person_id == "sean_mcvay") & (rel.target_season == 2026)
            & (rel.role == "caller")].iloc[0]
    assert int(r.observed_prior_games) == 181
    assert r.observed_reliability == 181 / (181 + 32)
    lin = pd.read_csv(DATA / "coach_reliability_lineage.csv")
    mv = lin[(lin.person_id == "sean_mcvay") & (lin.role == "caller") & (lin.season < 2026)]
    by_team = mv.groupby("team").game_id.nunique().to_dict()
    assert by_team == {"LA": 149, "WAS": 32}, by_team    # OC games + HC games, one identity
    assert mv.game_id.nunique() == 181


def test_hc_equals_caller_counts_in_caller_and_resume_but_not_context(rel):
    """McDaniel called every MIA game: caller 68, hc_resume 68, hc_context 0."""
    r = rel[(rel.person_id == "mike_mcdaniel") & (rel.target_season == 2026)]
    d = r.set_index("role").observed_prior_games.to_dict()
    assert d["caller"] == 68 and d["hc_resume"] == 68
    assert d.get(BR.ROLE_HC_CTX, 0) == 0


def test_reid_decomposition_is_192_plus_5_plus_240(rel):
    """The v3.5 artifact reported hc_context=245 and it was described as 245 DELEGATED games.
    That was FALSE: only 5 are verified delegated (Matt Nagy, 2017); 240 are unknown-caller games,
    all 1999-2013, entirely before the attribution window opens."""
    d = rel[(rel.person_id == "andy_reid") & (rel.target_season == 2026)].set_index(
        "role").observed_prior_games.to_dict()
    assert d["hc_resume"] == 437
    assert d["caller"] == 192
    assert d[BR.ROLE_HC_CTX] == 5, "only Matt Nagy's 2017 games are verified delegated"
    assert d[BR.ROLE_UNKNOWN_HC] == 240
    self_called = d["hc_resume"] - d[BR.ROLE_HC_CTX] - d[BR.ROLE_UNKNOWN_HC]
    assert self_called + d[BR.ROLE_HC_CTX] + d[BR.ROLE_UNKNOWN_HC] == 437


def test_reid_delegated_games_route_to_nagy_in_2017():
    lin = pd.read_csv(DATA / "coach_reliability_lineage.csv")
    d = lin[(lin.person_id == "andy_reid") & (lin.role == BR.ROLE_HC_CTX) & (lin.season < 2026)]
    assert set(d.season) == {2017}
    assert d.game_id.nunique() == 5
    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    kc = tbl[(tbl.season == 2017) & (tbl.team == "KC")]
    assert "Matt Nagy" in set(kc.actual_play_caller)


def test_mcvay_and_mcdaniel_have_zero_context_and_zero_unknown(rel):
    for pid, cal, hcr in [("mike_mcdaniel", 68, 68), ("sean_mcvay", 181, 149)]:
        d = rel[(rel.person_id == pid) & (rel.target_season == 2026)].set_index(
            "role").observed_prior_games.to_dict()
        assert d["caller"] == cal and d["hc_resume"] == hcr
        assert d.get(BR.ROLE_HC_CTX, 0) == 0
        assert d.get(BR.ROLE_UNKNOWN_HC, 0) == 0


# ------------------------------------------------------------------ scenarios
def test_16_game_and_17_game_seasons_count_actual_games():
    g16 = _syn([(w, "hc_a", "hc_a") for w in range(1, 17)], 2015)
    g17 = _syn([(w, "hc_a", "hc_a") for w in range(1, 18)], 2021)
    assert _counts(g16, 2016)[("hc_a", "caller")] == 16
    assert _counts(pd.concat([g16, g17]), 2022)[("hc_a", "caller")] == 33   # NOT 16*2


def test_midseason_caller_split_across_a_bye():
    """Weeks 1-9 caller A (8 games, week 5 is a bye), weeks 10-17 caller B."""
    weeks = [w for w in range(1, 18) if w != 5]
    rows = [(w, "hc_a", "call_a" if w <= 9 else "call_b") for w in weeks]
    c = _counts(_syn(rows, 2021), 2022)
    assert c[("call_a", "caller")] == 8      # 9 weeks minus the bye
    assert c[("call_b", "caller")] == 8
    assert c[("call_a", "caller")] + c[("call_b", "caller")] == 16


def test_hc_takes_over_play_calling_midseason():
    """HC delegates weeks 1-8, then calls weeks 9-17 himself."""
    rows = [(w, "hc_a", "call_b" if w <= 8 else "hc_a") for w in range(1, 18)]
    c = _counts(_syn(rows, 2021), 2022)
    assert c[("hc_a", "hc_resume")] == 17
    assert c[("hc_a", "caller")] == 9                 # only the games he actually called
    assert c[("call_b", "caller")] == 8
    assert c[("hc_a", BR.ROLE_HC_CTX)] == 8           # context ONLY while delegating


def test_hc_change_midseason():
    rows = [(w, "hc_a" if w <= 10 else "hc_b", "call_c") for w in range(1, 18)]
    c = _counts(_syn(rows, 2021), 2022)
    assert c[("hc_a", "hc_resume")] == 10
    assert c[("hc_b", "hc_resume")] == 7
    assert c[("call_c", "caller")] == 17


def test_unknown_caller_games_activate_NEITHER_identity_block():
    """v3.6. The old rule granted the HC context on unknown-caller games and called it
    conservative. It is not -- it assigns offensive residuals to the HC with no evidence he
    delegated. Unknown games now activate neither block; only résumé accrues."""
    rows = [(w, "hc_a", None if w <= 6 else "call_b") for w in range(1, 18)]
    c = _counts(_syn(rows, 2021), 2022)
    assert c.get(("call_b", "caller")) == 11
    assert c[("hc_a", "hc_resume")] == 17                      # résumé unaffected
    assert c[("hc_a", BR.ROLE_HC_CTX)] == 11                   # ONLY the distinct-known games
    assert c[("hc_a", BR.ROLE_UNKNOWN_HC)] == 6                # tracked separately
    assert c[("hc_a", BR.ROLE_HC_CTX)] + c[("hc_a", BR.ROLE_UNKNOWN_HC)] == 17


def test_four_games_two_known_two_unknown_shares():
    """Frozen §5 case: 2 known-distinct + 2 unknown of 4 games."""
    rows = [(1, "hc_a", "call_b"), (2, "hc_a", "call_b"), (3, "hc_a", None), (4, "hc_a", None)]
    gl = _syn(rows, 2021)
    exp = BE.exposure_long(gl)
    cal = exp[(exp.role == BE.ROLE_CALLER)].exposure.sum()
    ctx = exp[(exp.role == BE.ROLE_HC_CTX)].exposure.sum()
    sh = BE.caller_known_share(gl).iloc[0]
    assert cal == 0.5, cal
    assert ctx == 0.5, ctx
    assert sh.unknown_caller_share == 0.5
    assert sh.caller_known_share == 0.5
    assert sh.hc_context_share == 0.5


def test_all_callers_unknown_gives_zero_to_both_blocks():
    rows = [(w, "hc_a", None) for w in range(1, 18)]
    gl = _syn(rows, 2021)
    exp = BE.exposure_long(gl)
    assert exp[exp.role == BE.ROLE_CALLER].exposure.sum() == 0
    assert exp[exp.role == BE.ROLE_HC_CTX].exposure.sum() == 0
    sh = BE.caller_known_share(gl).iloc[0]
    assert sh.unknown_caller_share == 1.0
    c = _counts(gl, 2022)
    assert c[("hc_a", "hc_resume")] == 17          # résumé still counts normally
    assert c.get(("hc_a", BR.ROLE_HC_CTX), 0) == 0


def test_exposure_shares_reconcile_per_team_season(gl):
    sh = BE.caller_known_share(gl)
    assert ((sh.caller_known_share + sh.unknown_caller_share - 1.0).abs() < 1e-12).all()
    assert (sh.hc_context_share <= sh.caller_known_share + 1e-12).all()


def test_person_changes_teams_history_follows_the_person():
    a = _syn([(w, "x", "x") for w in range(1, 18)], 2021, team="AAA")
    b = _syn([(w, "x", "x") for w in range(1, 18)], 2022, team="BBB")
    c = _counts(pd.concat([a, b]), 2023)
    assert c[("x", "caller")] == 34


def test_person_moves_from_oc_caller_to_hc_caller():
    """OC-caller games and later HC-caller games accumulate under ONE identity (the McVay case)."""
    oc = _syn([(w, "boss", "p") for w in range(1, 18)], 2021, team="AAA")
    hc = _syn([(w, "p", "p") for w in range(1, 18)], 2022, team="BBB")
    c = _counts(pd.concat([oc, hc]), 2023)
    assert c[("p", "caller")] == 34            # unified
    assert c[("p", "hc_resume")] == 17         # HC résumé starts only in 2022
    assert c.get(("p", BR.ROLE_HC_CTX), 0) == 0


def test_no_playoff_games_enter_counts(gl):
    """head_coach_games is REG-only; a 17-game era team-season must never exceed 17."""
    per_ts = gl.groupby(["season", "team"]).game_id.nunique()
    assert per_ts.max() <= 17, f"a team-season has {per_ts.max()} games -- playoffs leaked in"


def test_no_duplicate_game_ids_within_a_role_block():
    lin = pd.read_csv(DATA / "coach_reliability_lineage.csv")
    d = lin.groupby(["role", "person_id", "game_id"]).size()
    assert (d == 1).all(), "a game_id appears twice within one role block"


def test_every_historical_team_season_reconciles(gl):
    """Role-game totals must reconcile against the game-level identity artifact."""
    lin = pd.read_csv(DATA / "coach_reliability_lineage.csv")
    for (s, t), g in gl.groupby(["season", "team"]):
        n = g.game_id.nunique()
        sub = lin[(lin.season == s) & (lin.team == t)]
        assert sub[sub.role == "hc_resume"].game_id.nunique() == n, f"hc_resume {s} {t}"
        known = g[g.caller_person_id.notna()].game_id.nunique()
        assert sub[sub.role == "caller"].game_id.nunique() == known, f"caller {s} {t}"


# ------------------------------------------------------------------ routing flags
def test_unknown_identity_and_known_no_history_are_separate_flags():
    rf = BR.routing_flags()
    assert not ((rf.caller_identity_unknown == 1) & (rf.caller_no_prior_history == 1)).any()
    # both populations must actually exist, else the distinction is untested
    assert (rf.caller_identity_unknown == 1).any()
    both = rf[rf.routes_to_league_prior == 1]
    assert len(both) >= (rf.caller_identity_unknown == 1).sum()


def test_unknown_identity_carries_no_prior_games():
    rf = BR.routing_flags()
    unk = rf[rf.caller_identity_unknown == 1]
    assert unk.caller_observed_prior_games.isna().all(), (
        "an unidentified caller must not be assigned any person's history")
    assert unk.caller_no_prior_history.eq(0).all()


def test_known_caller_with_zero_history_is_flagged_not_dropped():
    rf = BR.routing_flags()
    z = rf[rf.caller_no_prior_history == 1]
    if len(z):
        assert z.caller_identity_unknown.eq(0).all()
        assert (z.caller_observed_prior_games == 0).all()
        assert (z.caller_observed_reliability == 0).all()
        assert z.expected_opening_caller_id.notna().all()


# ------------------------------------------------------------------ left-censoring
def test_left_censoring_is_flagged_not_silent(rel):
    """Caller history starts 2014; HC history starts 1999. Rows whose true history provably
    predates the caller window must be marked."""
    assert (rel[rel.role == "caller"].observed_history_start == 2014).all()
    assert (rel[rel.role == "hc_resume"].observed_history_start == 1999).all()
    reid = rel[(rel.person_id == "andy_reid") & (rel.role == "caller")]
    assert reid.history_left_censored.eq(1).all(), (
        "Reid called plays from 1999 but the caller table starts 2014 -- must be flagged")
    assert rel[rel.role == "hc_resume"].history_left_censored.eq(0).all()


def test_caller_counts_grow_with_window_width_for_censored_people(rel):
    """The confound itself: a censored person's caller count rises with target season purely
    because the observation window widens."""
    reid = rel[(rel.person_id == "andy_reid") & (rel.role == "caller")].sort_values("target_season")
    g = reid.set_index("target_season").observed_prior_games
    assert g.loc[2015] == 16 and g.loc[2026] == 192
    assert g.is_monotonic_increasing


# ------------------------------------------------------------------ v3.6 policy
def test_target_season_unknown_caller_assumes_neither_delegation_nor_self_call():
    rf = BR.routing_flags()
    assert (rf.assumes_delegation == 0).all()
    unk = rf[rf.caller_identity_unknown == 1]
    assert unk.hc_context_identity_routes_to_prior.eq(1).all(), (
        "an unknown expected caller must route the HC-context identity to the prior too")
    assert unk.caller_observed_prior_games.isna().all()


def test_feature_policy_lists_are_disjoint():
    lists = {"MODEL_PREDICTORS": set(BR.MODEL_PREDICTORS),
             "PRECISION_ONLY": set(BR.PRECISION_ONLY),
             "ROUTING_ONLY": set(BR.ROUTING_ONLY),
             "AUDIT_ONLY": set(BR.AUDIT_ONLY)}
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            assert not (lists[a] & lists[b]), f"{a} and {b} overlap: {lists[a] & lists[b]}"


def test_observed_reliability_is_precision_only_not_a_predictor():
    """r = g/(g+32) is a strictly monotone bijection of g, so admitting r as a predictor readmits
    the forbidden count -- and its left-censoring/calendar signal -- through the back door."""
    assert "observed_reliability" in BR.PRECISION_ONLY
    assert "observed_reliability" not in BR.MODEL_PREDICTORS
    assert "observed_reliability" in BR.FORBIDDEN_IN_X


def test_reliability_is_a_bijection_of_the_forbidden_count():
    """Demonstrates the leak the policy exists to prevent: g is exactly recoverable from r."""
    g = np.arange(0, 500)
    r = g / (g + BR.K_SHRINK)
    recovered = BR.K_SHRINK * r / (1 - r)
    assert np.allclose(recovered, g)
    assert np.all(np.diff(r) > 0)          # strictly monotone => information-preserving


def test_counts_and_calendar_proxies_are_forbidden_in_X():
    for f in ("observed_prior_games", "observed_games_log", "n_observed_prior_seasons",
              "observable_prior_seasons", "history_left_censored", "observed_history_start",
              "hc_resume", "unknown_caller_hc_games"):
        assert f in BR.FORBIDDEN_IN_X, f"{f} must be barred from X"


def test_design_matrix_guard_rejects_forbidden_columns():
    """The guard inspects an ACTUAL matrix, not a hand-maintained list."""
    BR.assert_design_matrix_is_clean(["caller_exposure",
                                      "noncalling_hc_context_exposure"], "stage2")
    for bad in ("observed_reliability", "observed_prior_games", "observable_prior_seasons",
                "no_prior_history"):
        try:
            BR.assert_design_matrix_is_clean(["caller_exposure", bad], "stage2")
        except AssertionError:
            continue
        raise AssertionError(f"guard failed to reject {bad}")


def test_canonical_schema_has_no_legacy_aliases(rel):
    assert list(rel.columns) == BR.CANONICAL_SCHEMA
    for legacy in BR.LEGACY_ALIASES_REMOVED:
        assert legacy not in rel.columns, f"legacy alias {legacy} is still persisted"
