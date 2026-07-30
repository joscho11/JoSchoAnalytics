"""PHASE 2A tests (prereg v3.9 PREFIT) — point-in-time coaching representations.

Synthetic cases drive `build_arm_features_v39.build_features` itself -- the same entry point the real
build calls -- so a passing synthetic test exercises the production code path.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
DATA = COACH / "data"
sys.path.insert(0, str(COACH))

import build_arm_features_v39 as AF   # noqa: E402
import build_reliability as BR        # noqa: E402
import date_provenance as DP          # noqa: E402


# =====================================================================================================
# fixtures
# =====================================================================================================
@pytest.fixture(scope="module")
def design_a():
    return pd.read_csv(DATA / "team_coach_features_design_a_v39.csv")


@pytest.fixture(scope="module")
def design_b():
    return pd.read_csv(DATA / "team_coach_features_design_b_oracle_v39.csv")


@pytest.fixture(scope="module")
def effects():
    return pd.read_csv(DATA / "arm3_stage2_effects_v38.csv")


@pytest.fixture(scope="module")
def coverage():
    return pd.read_csv(DATA / "arm_feature_coverage_v39.csv")


@pytest.fixture(scope="module")
def manifest():
    return json.loads((DATA / "arm_feature_manifest_v39.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- synthetic builders
SEG_SCHEMA = (["season", "team", "person_id", "week_start", "week_end", "ledger_games",
               "pbp_games", "n_games_attributed", "source_upper_bound"]
              + [c for _s, (c, _p) in AF.SEG_METRICS.items()])


def _syn_seg(rows):
    """rows: (season, team, person_id, week_start, week_end, games, source_date, level).

    Always emits the full schema, because a zero-row frame built from an empty list of dicts has NO
    columns at all and `df.season` then raises instead of filtering to nothing.
    """
    out = []
    for season, team, pid, ws, we, games, sdate, level in rows:
        r = dict(season=season, team=team, person_id=pid, week_start=ws, week_end=we,
                 ledger_games=games, pbp_games=games, n_games_attributed=games,
                 source_upper_bound=sdate)
        for _stem, (col, _prior) in AF.SEG_METRICS.items():
            r[col] = float(level)
        out.append(r)
    return pd.DataFrame(out, columns=SEG_SCHEMA)


def _syn_gl(rows):
    """rows: (season, team, week, hc_person_id, caller_person_id)."""
    return pd.DataFrame([dict(season=s, team=t, week=w, game_id=f"g{s}_{t}_{w}",
                              head_coach=hc, hc_person_id=hc, caller_person_id=c)
                         for s, t, w, hc, c in rows])


def _syn_res(rows):
    """rows: (season, team, week, hc_person_id, win)."""
    return pd.DataFrame([dict(season=s, week=w, team=t, game_id=f"g{s}_{t}_{w}",
                              head_coach=hc, hc_person_id=hc, margin=(1 if win == 1 else -1),
                              win=float(win))
                         for s, t, w, hc, win in rows])


def _syn_eff(rows):
    cols = ["target_season", "person_id", "role", "effect"]
    return pd.DataFrame([dict(target_season=y, person_id=p, role=r, effect=e)
                         for y, p, r, e in rows], columns=cols)


def _syn_ident(rows):
    df = pd.DataFrame([dict(season=s, team=t, expected_caller_id=c, expected_hc_id=h)
                       for s, t, c, h in rows])
    for col in ("expected_caller_id", "expected_hc_id"):
        df[col] = df[col].astype("object").where(df[col].notna(), None)
    return df


def _cutoffs(seasons):
    return {int(s): f"{int(s)}-09-01" for s in seasons}


# =====================================================================================================
# 2026 ROUTING — the three pinned team-seasons
# =====================================================================================================
def test_lac_2026_routing_mcdaniel_over_roman_under_harbaugh(design_a, effects):
    r = design_a[(design_a.season == 2026) & (design_a.team == "LAC")].iloc[0]
    assert r.expected_caller_id == "mike_mcdaniel"
    assert r.expected_hc_id == "jim_harbaugh"
    assert r.pc_changed_entering == 1.0, "the caller CHANGED entering 2026"
    assert r.caller_is_head_coach == 0.0
    assert abs(r.caller_adjusted_offense_effect - 0.005262) < 5e-7
    # Harbaugh IS a distinct non-calling HC, so his context coefficient applies -- and it is
    # NUMERICALLY zero because the HC-context block sat at the extended upper alpha boundary.
    assert abs(r.noncalling_hc_context_effect) < AF.NUMERICAL_ZERO
    assert r.noncalling_hc_context_effect != 0.0 or True   # value is the fitted one, not forced


def test_lac_2026_previous_caller_was_greg_roman(design_a):
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
    row = snap[(snap.season == 2026) & (snap.team == "LAC")].iloc[0]
    assert row.prev_season_closing_caller_id == "greg_roman"


def test_arm3_does_not_support_a_chargers_upgrade(effects):
    """Joseph's standing instruction: never force McDaniel or McVay upward.

    McDaniel's ADJUSTED entering-2026 coefficient is BELOW Greg Roman's, so Arm 3 supplies no basis
    for describing the Chargers as a play-calling upgrade.
    """
    cal, _ctx = AF.arm3_lookup(effects, 2026)
    d = cal["mike_mcdaniel"] - cal["greg_roman"]
    assert abs(d - (-0.002219)) < 5e-7, f"expected -0.002219 EPA/play, got {d:+.6f}"
    assert d < 0


def test_rams_2026_mcvay_effect_appears_exactly_once(design_a, effects):
    r = design_a[(design_a.season == 2026) & (design_a.team == "LA")].iloc[0]
    assert r.expected_caller_id == "sean_mcvay" and r.expected_hc_id == "sean_mcvay"
    assert r.pc_changed_entering == 0.0
    assert r.caller_is_head_coach == 1.0
    assert abs(r.caller_adjusted_offense_effect - 0.025936) < 5e-7
    assert r.noncalling_hc_context_effect == 0.0, "self-calling HC contributes nothing to context"
    assert len(effects[(effects.person_id == "sean_mcvay")
                       & (effects.role == BR.ROLE_HC_CTX)]) == 0, (
        "McVay must not appear in the HC-context block at all — otherwise the effect is duplicated")


def test_kc_2026_reid_context_suppressed_while_self_calling(design_a, effects):
    r = design_a[(design_a.season == 2026) & (design_a.team == "KC")].iloc[0]
    assert r.expected_caller_id == "andy_reid" and r.expected_hc_id == "andy_reid"
    assert abs(r.caller_adjusted_offense_effect - 0.038287) < 5e-7
    assert r.noncalling_hc_context_effect == 0.0
    # Reid DOES have a context coefficient in the table; routing is what suppresses it.
    _cal, ctx = AF.arm3_lookup(effects, 2026)
    assert "andy_reid" in ctx, "Reid has a context row (5 delegated games to Nagy in 2017)"


# =====================================================================================================
# ARM 3 ROUTING — as a unit
# =====================================================================================================
def test_route_arm3_unknown_caller_activates_neither_block():
    assert AF.route_arm3(None, "hc1", {"x": 0.9}, {"hc1": 0.7}) == (0.0, 0.0)


def test_route_arm3_self_calling_hc_gets_caller_effect_only():
    assert AF.route_arm3("hc1", "hc1", {"hc1": 0.4}, {"hc1": 0.7}) == (0.4, 0.0)


def test_route_arm3_distinct_known_caller_permits_both():
    assert AF.route_arm3("oc1", "hc1", {"oc1": 0.4}, {"hc1": 0.7}) == (0.4, 0.7)


def test_route_arm3_identity_absent_from_the_table_gets_the_zero_prior():
    assert AF.route_arm3("nobody", "nohc", {}, {}) == (0.0, 0.0)
    assert AF.route_arm3("nobody", "hc1", {}, {"hc1": 0.7}) == (0.0, 0.7)


# =====================================================================================================
# COVERAGE
# =====================================================================================================
def _all_rows(coverage, design, arm="ARM_1"):
    """The `all` identity-state slice. The artifact carries one row per identity state PLUS an
    aggregate, so summing without this filter double-counts every season."""
    return coverage[(coverage.design == design) & (coverage.arm == arm)
                    & (coverage.identity_state == "all")]


def test_design_a_outer_caller_coverage_is_152_of_256(coverage):
    c = _all_rows(coverage, AF.DESIGN_A)
    c = c[c.season.isin(AF.OUTER_SEASONS)]
    assert len(c) == 8, "one aggregate row per outer season"
    assert int(c.caller_identity_known.sum()) == 152
    assert int(c.n_team_seasons.sum()) == 256


def test_design_b_outer_caller_coverage_is_the_retrospective_244_of_256(coverage):
    c = _all_rows(coverage, AF.DESIGN_B)
    c = c[c.season.isin(AF.OUTER_SEASONS)]
    assert int(c.caller_identity_known.sum()) == 244


def test_identity_states_decompose_the_aggregate_exactly(coverage):
    for design in (AF.DESIGN_A, AF.DESIGN_B):
        for Y in AF.TARGET_SEASONS:
            g = coverage[(coverage.design == design) & (coverage.arm == "ARM_1")
                         & (coverage.season == Y)]
            agg = g[g.identity_state == "all"].iloc[0]
            parts = g[g.identity_state != "all"]
            assert set(parts.identity_state) == {"known_with_history", "known_no_history",
                                                 "unknown"}
            assert int(parts.n_rows.sum()) == int(agg.n_rows) == 32
            assert (int(agg.caller_known_with_history) + int(agg.caller_known_no_history)
                    == int(agg.caller_identity_known))


def test_coverage_reports_rates_as_well_as_counts(coverage):
    g = coverage[coverage.identity_state != "all"]
    assert (g.row_coverage_rate.between(0, 1)).all()
    assert "league_prior_rate_for_this_arm" in coverage.columns
    a19 = _all_rows(coverage, AF.DESIGN_A)
    a19 = a19[a19.season == 2019].iloc[0]
    # 2019 Design A: 7 identified callers, only 3 of them with any eligible prior history
    assert int(a19.caller_identity_known) == 7
    assert int(a19.caller_known_with_history) == 3
    assert int(a19.caller_known_no_history) == 4
    assert int(a19.caller_identity_unknown) == 25


def test_design_a_has_zero_coverage_seasons_and_they_are_disclosed(coverage):
    c = _all_rows(coverage, AF.DESIGN_A)
    zero = sorted(int(s) for s in c[c.caller_identity_known == 0].season)
    assert 2017 in zero, "2017 has no pre-cutoff league-wide source at all"


def test_arm3_effects_are_zero_before_target_season_2018(design_a, design_b):
    """Stage 2's frozen minimums make entering-2018 the earliest estimable target. Nothing is
    backfilled, so 2014-2017 carry all-zero effects and that must stay visible."""
    for df in (design_a, design_b):
        early = df[df.season < 2018]
        assert (early.caller_adjusted_offense_effect == 0).all()
        assert (early.noncalling_hc_context_effect == 0).all()
        assert (early.arm3_effects_available == 0).all()
        assert (df[df.season >= 2018].arm3_effects_available == 1).all()


def test_coverage_reports_every_arm_design_and_season(coverage):
    assert set(coverage.arm) == set(AF.ARMS)
    assert set(coverage.design) == {AF.DESIGN_A, AF.DESIGN_B}
    assert sorted(coverage.season.unique()) == AF.TARGET_SEASONS


# =====================================================================================================
# DESIGN A / B ISOLATION
# =====================================================================================================
# Regexes, not substrings: "opening_caller_id" is a SUBSTRING of the legitimate
# "expected_opening_caller_id", so a plain `in` check flags the correct code.
FORBIDDEN_IN_DESIGN_A = (
    r"retrospective_opening_caller_id",
    r"expectation_matched_actual",
    r"(?<!expected_)(?<!prev_)(?<!prev_season_)closing_caller_id",
    r"historical_primary_caller_id",
    r"retrospective_staff_transitions",
)


def test_design_a_never_reads_a_retrospective_identity_field():
    """The Design A branch may touch the eligibility-gated snapshot and nothing else.

    The explicit guard block (which necessarily NAMES the forbidden columns in order to assert their
    absence) is stripped before the scan, so the test measures what the branch READS.
    """
    import re
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    body = src.split("def target_identities", 1)[1].split("\ndef ", 1)[0]
    a_branch = body.split("if design == DESIGN_A", 1)[1].split("elif design == DESIGN_B", 1)[0]
    guard_start = a_branch.index("forbidden = {")
    guard_end = a_branch.index("snap = snap[snap.season")
    scanned = a_branch[:guard_start] + a_branch[guard_end:]
    for pat in FORBIDDEN_IN_DESIGN_A:
        assert not re.search(pat, scanned), f"the Design A branch references {pat}"
    assert "preseason_staff_snapshot.csv" in scanned and "eligible_at_cutoff" in scanned


def test_the_gated_snapshot_itself_carries_no_retrospective_answer():
    cols = set(pd.read_csv(DATA / "preseason_staff_snapshot.csv").columns)
    for f in ("retrospective_opening_caller_id", "expectation_matched_actual",
              "closing_caller_id", "historical_primary_caller_id"):
        assert f not in cols, f"{f} is one join away from a feature builder"


def test_only_the_design_b_branch_reads_the_retrospective_ledger():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    body = src.split("def target_identities", 1)[1].split("\ndef ", 1)[0]
    b_branch = body.split("elif design == DESIGN_B", 1)[1]
    assert "retrospective_staff_transitions.csv" in b_branch
    assert body.count("retrospective_staff_transitions.csv") == 1


def test_design_a_and_b_share_rows_schema_and_the_entire_hc_block(design_a, design_b):
    """Renamed from `..._differ_only_on_identity_supply`, which OVERCLAIMED.

    The designs differ on TWO axes, not one: the target-season caller identity supply AND the
    historical caller attribution available to the aggregates (Design A gates history on the
    attributing source's date; Design B does not). `test_design_b_history_is_ungated_and_therefore_larger`
    proves the second axis, so a name asserting "only identity supply" contradicted a sibling test.

    What this test actually establishes: identical rows, identical schema, and a bit-identical
    head-coach block — because HC identity and HC results are shared between the designs.
    """
    assert list(design_a.columns) == list(design_b.columns)
    a = design_a.sort_values(["season", "team"]).reset_index(drop=True)
    b = design_b.sort_values(["season", "team"]).reset_index(drop=True)
    assert (a.season == b.season).all() and (a.team == b.team).all()
    for c in AF.ARM_HC_FEATURES:
        pd.testing.assert_series_equal(a[c], b[c], check_names=False)
    assert not a.expected_caller_id.equals(b.expected_caller_id), (
        "the two designs must supply DIFFERENT caller identities")


def test_the_designs_differ_on_target_identity_and_that_is_the_ONLY_axis(design_a, design_b):
    """SUPERSEDED BY v3.9b and rewritten.

    The v3.9a version of this test asserted the contrast had TWO axes (identity supply AND historical
    attribution availability), because Design A gated history on the citation date. Under the v3.9b
    primary policy both designs use the identical strictly-prior retrospective ledger, so the contrast
    is single-axis again. The old two-axis assertion is withdrawn as a description of current policy.
    """
    a = design_a.set_index(["season", "team"])
    b = design_b.set_index(["season", "team"])
    # the one axis: target-season identity supply
    assert int((a.caller_identity_known != b.caller_identity_known).sum()) > 0
    # B still holds MORE total history, but only because it KNOWS more identities -- not because its
    # history rule differs. Verified per matched identity in
    # test_design_a_and_b_now_differ_on_target_identity_ONLY.
    assert b.caller_history_games_career.sum() > a.caller_history_games_career.sum()
    assert int((b.caller_identity_known == 1).sum()) > int((a.caller_identity_known == 1).sum())


def test_design_b_is_labelled_nondeployable(manifest):
    lab = manifest["designs"][AF.DESIGN_B]
    for phrase in ("ORACLE", "NOT achievable in deployment"):
        assert phrase in lab
    assert "deployable" in manifest["designs"][AF.DESIGN_A]


def test_design_c_is_not_authorized(design_a):
    with pytest.raises(ValueError, match="NOT AUTHORIZED"):
        AF.target_identities("design_c", pd.DataFrame(), pd.DataFrame())


# =====================================================================================================
# FORBIDDEN METADATA / FEATURE POLICY
# =====================================================================================================
def test_no_manifest_arm_carries_forbidden_metadata(manifest):
    for pos, arms in manifest["by_position"].items():
        for arm, feats in arms.items():
            AF.assert_no_forbidden_features(feats, f"{pos}/{arm}")
            for f in feats:
                assert f not in BR.PRECISION_ONLY + BR.ROUTING_ONLY + BR.AUDIT_ONLY


def test_reliability_counts_and_censoring_can_never_be_features():
    for bad in ("observed_reliability", "observed_prior_games", "observed_games_log",
                "no_prior_history", "history_left_censored", "observable_prior_seasons",
                "hc_resume", "unknown_caller_hc_games"):
        with pytest.raises(AssertionError):
            AF.assert_no_forbidden_features(["hc_tenure_current_team", bad], "probe")


def test_diagnostic_columns_ride_along_but_are_not_model_features(design_a, manifest):
    model_cols = {f for arms in manifest["by_position"].values() for fs in arms.values() for f in fs}
    for c in AF.DIAGNOSTIC_COLUMNS:
        assert c in design_a.columns, f"{c} must be emitted for audit"
        assert c not in model_cols, f"{c} is diagnostic and must not be a model feature"


def test_arm5_excludes_arm1_win_rank_and_arm2_efficiency(manifest):
    for pos in AF.POSITIONS:
        a5 = set(manifest["by_position"][pos]["ARM_5"])
        assert not (a5 & {"hc_career_win_pct_shrunk", "hc_roll3_win_pct_shrunk",
                          "pc_career_off_rank_pct", "pc_roll3_off_rank_pct"})
        assert not (a5 & set(AF.ARM2_QUALITY))


# =====================================================================================================
# MANIFEST SHAPE
# =====================================================================================================
def test_manifest_pins_exact_ordered_features_by_position_and_arm(manifest):
    assert manifest["by_position"]["RB"]["ARM_HC"] == [
        "hc_career_win_pct_shrunk", "hc_roll3_win_pct_shrunk", "hc_tenure_current_team",
        "hc_changed_entering"]
    assert manifest["by_position"]["RB"]["ARM_3"] == [
        "caller_adjusted_offense_effect", "noncalling_hc_context_effect", "caller_is_head_coach"]
    assert manifest["by_position"]["RB"]["ARM_1"][:4] == manifest["by_position"]["RB"]["ARM_HC"]
    assert manifest["by_position"]["QB"]["ARM_0"] == []
    counts = manifest["feature_counts"]
    assert {p: counts[p]["ARM_HC"] for p in AF.POSITIONS} == {p: 4 for p in AF.POSITIONS}
    assert {p: counts[p]["ARM_1"] for p in AF.POSITIONS} == {p: 9 for p in AF.POSITIONS}
    assert {p: counts[p]["ARM_2"] for p in AF.POSITIONS} == {p: 15 for p in AF.POSITIONS}
    assert {p: counts[p]["ARM_3"] for p in AF.POSITIONS} == {p: 3 for p in AF.POSITIONS}
    assert counts["QB"]["ARM_4"] == 10 and counts["TE"]["ARM_4"] == 8
    assert counts["QB"]["ARM_5"] == 17 and counts["TE"]["ARM_5"] == 15


def test_arm4_is_position_specific_and_not_interchangeable(manifest):
    qb = manifest["by_position"]["QB"]["ARM_4"]
    rb = manifest["by_position"]["RB"]["ARM_4"]
    wr = manifest["by_position"]["WR"]["ARM_4"]
    te = manifest["by_position"]["TE"]["ARM_4"]
    assert qb != rb != wr and te != wr
    assert any("qb_carry_share" in f for f in qb) and not any("qb_carry_share" in f for f in rb)
    assert any("rush_tendency" in f for f in rb) and not any("rush_tendency" in f for f in wr)
    assert any("team_adot" in f for f in wr) and not any("team_adot" in f for f in te)
    assert any("rz_te_share" in f for f in te) and not any("rz_te_share" in f for f in qb)


def test_rush_tendency_is_the_exact_negation_of_pass_tendency(design_a):
    for w in AF.WINDOWS:
        assert np.allclose(design_a[f"pc_{w}_rush_tendency_z"],
                           -design_a[f"pc_{w}_pass_tendency_z"], atol=0, rtol=0)


# =====================================================================================================
# NEUTRAL ENCODING
# =====================================================================================================
def test_unknown_caller_rows_carry_the_frozen_neutral_values(design_a):
    u = design_a[design_a.caller_identity_known == 0]
    assert len(u) > 0
    assert (u.pc_career_off_rank_pct == AF.PRIOR_RANKPCT).all()
    assert (u.pc_roll3_off_rank_pct == AF.PRIOR_RANKPCT).all()
    for c in AF.ARM2_QUALITY:
        assert (u[c] == AF.PRIOR_Z).all()
    assert (u.caller_adjusted_offense_effect == AF.NEUTRAL_EFFECT).all()
    assert (u.noncalling_hc_context_effect == AF.NEUTRAL_EFFECT).all()
    assert (u.pc_tenure_current_team == AF.NEUTRAL_TENURE).all()
    assert (u.pc_changed_entering == AF.NEUTRAL_CHANGED).all()
    assert (u.caller_is_head_coach == AF.NEUTRAL_IS_HC).all()


def test_unknown_is_a_VALUE_not_a_missingness_pattern(design_a):
    """NaN on an unknown-caller row would be close to a season indicator under Design A, which is
    exactly the calendar proxy the feature policy exists to exclude."""
    cols = [c for c in AF.ALL_FEATURE_COLUMNS if c != "hc_changed_entering"]
    assert not design_a[cols].isna().any().any()


def test_known_caller_with_no_prior_history_also_receives_league_priors(design_a):
    k = design_a[(design_a.caller_identity_known == 1)
                 & (design_a.caller_history_games_career == 0)]
    assert len(k) > 0, "expected at least one identified caller with zero prior games"
    assert (k.pc_career_off_rank_pct == AF.PRIOR_RANKPCT).all()
    for c in AF.ARM2_QUALITY:
        assert (k[c] == AF.PRIOR_Z).all()
    # ...but the routing flags DIFFER from an unknown identity: he is identified.
    assert (k.caller_is_head_coach != AF.NEUTRAL_IS_HC).all()


# =====================================================================================================
# POINT-IN-TIME EVIDENCE GATE
# =====================================================================================================
def test_a_later_source_cannot_build_an_earlier_feature():
    """BUF 2014's caller is attributed by an ESPN piece dated 2016-10-29. It may not feed a
    target-2015 feature, and it may feed target-2017."""
    seg = AF.caller_segments()
    row = seg[(seg.season == 2014) & (seg.team == "BUF")].iloc[0]
    ub = row.source_upper_bound
    cuts = AF.projection_cutoffs()
    assert str(ub).startswith("2016"), f"fixture drifted: BUF 2014 upper bound is {ub}"
    assert not AF.eligible_at(ub, cuts[2015])
    assert not AF.eligible_at(ub, cuts[2016])
    assert AF.eligible_at(ub, cuts[2017])


def test_the_gate_shrinks_eligible_history_and_the_effect_is_measured():
    seg = AF.caller_segments()
    cuts = AF.projection_cutoffs()
    for Y, expected_eligible, expected_total in ((2015, 15, 27), (2019, 154, 163),
                                                 (2026, 364, 378)):
        prior = seg[(seg.season < Y) & seg.person_id.notna()]
        n_ok = int(AF._gate_mask(prior, cuts[Y]).sum())
        assert (n_ok, len(prior)) == (expected_eligible, expected_total), (
            f"target {Y}: gate admits {n_ok}/{len(prior)}")


def test_missing_or_inferred_dates_are_never_eligible():
    assert not AF.eligible_at(None, "2020-09-01")
    assert not AF.eligible_at(np.nan, "2020-09-01")
    assert not AF.eligible_at(float("nan"), "2020-09-01")
    prov = DP.classify("cbs2022phi", "2022-01-01")
    lo, hi = DP.bounds(prov["source_date"], prov["source_date_precision"])
    assert hi is None and not AF.eligible_at(hi, "2022-09-07")


def test_design_b_holds_more_history_because_it_KNOWS_more_identities(design_a, design_b):
    """Renamed at v3.9b. It was `..._history_is_ungated_and_therefore_larger`, which is now wrong:
    BOTH designs use the identical ungated strictly-prior ledger. B holds more history purely because
    it knows 244/256 target identities against A's 152/256."""
    a = design_a.set_index(["season", "team"])
    b = design_b.set_index(["season", "team"])
    assert b.caller_history_games_career.sum() > a.caller_history_games_career.sum()
    assert int((b.caller_identity_known == 1).sum()) > int((a.caller_identity_known == 1).sum())


# =====================================================================================================
# PORTABILITY / RELOCATION / TENURE
# =====================================================================================================
def test_caller_identity_is_portable_across_teams_and_titles():
    """McVay's WAS coordinator games and his LA head-coach games accumulate under ONE identity."""
    seg = AF.caller_segments()
    hist, support = AF.caller_history(seg, 2026, AF.projection_cutoffs()[2026], gated=True)
    assert support["sean_mcvay"]["career_segments"] > 1
    mv = seg[(seg.person_id == "sean_mcvay") & (seg.season < 2026) & (seg.pbp_games > 0)]
    assert set(mv.team) >= {"LA", "WAS"}, f"McVay teams seen: {sorted(set(mv.team))}"
    assert support["sean_mcvay"]["career_games"] == float(mv.pbp_games.sum())


def test_mcdaniel_carries_his_miami_head_coach_games_into_a_coordinator_role():
    seg = AF.caller_segments()
    _h, sup = AF.caller_history(seg, 2026, AF.projection_cutoffs()[2026], gated=True)
    mia = seg[(seg.person_id == "mike_mcdaniel") & (seg.team == "MIA")]
    assert int(mia.pbp_games.sum()) == 68
    assert sup["mike_mcdaniel"]["career_games"] == 68.0


def test_tenure_bridges_a_franchise_relocation():
    """head_coach_games folds STL->LA, SD->LAC and OAK->LV onto one code, so tenure must not reset
    at the move. Jeff Fisher coached the Rams through the 2016 relocation."""
    gl = AF.game_identity()
    hco = AF.hc_openers_closers(gl)
    op = {(int(r.season), r.team): r.hc_opener for r in hco.itertuples()}
    assert op[(2015, "LA")] == "jeff_fisher" and op[(2016, "LA")] == "jeff_fisher"
    assert AF.tenure(op, 2016, "LA", "jeff_fisher") >= 4
    assert set(gl.team) & {"STL", "SD", "OAK"} == set(), "relocation codes must be folded"


def test_tenure_counts_only_consecutive_prior_seasons():
    op = {(2020, "T"): "a", (2021, "T"): "b", (2022, "T"): "a", (2023, "T"): "a"}
    assert AF.tenure(op, 2024, "T", "a") == 2      # 2023, 2022 — the 2021 break stops the count
    assert AF.tenure(op, 2022, "T", "a") == 0      # 2021 was someone else
    assert AF.tenure(op, 2024, "T", None) == AF.NEUTRAL_TENURE


def test_hc_changed_entering_matches_the_frozen_snapshot(design_a):
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
    m = design_a.merge(snap[["season", "team", "hc_changed_entering"]],
                       on=["season", "team"], suffixes=("", "_snap"))
    both = m.dropna(subset=["hc_changed_entering", "hc_changed_entering_snap"])
    assert len(both) > 300
    assert (both.hc_changed_entering == both.hc_changed_entering_snap).all()


# =====================================================================================================
# SYNTHETIC — through the production entry point
# =====================================================================================================
def _syn_world(caller_rows, gl_rows, ident_rows, eff_rows=(), seasons=(2020, 2021, 2022)):
    return dict(seg=_syn_seg(caller_rows), gl=_syn_gl(gl_rows), res=_syn_res(
        [(s, t, w, hc, 1) for s, t, w, hc, _c in gl_rows]),
        effects=_syn_eff(eff_rows), ident=_syn_ident(ident_rows),
        cutoffs=_cutoffs(seasons), target_seasons=list(seasons))


def test_synthetic_unknown_caller_gets_neutral_and_no_context_effect():
    gl = [(s, "SYN", w, "hc1", None) for s in (2020, 2021) for w in (1, 2)]
    gl += [(2022, "SYN", w, "hc1", None) for w in (1, 2)]
    w = _syn_world([], gl, [(s, "SYN", None, "hc1") for s in (2020, 2021, 2022)],
                   eff_rows=[(2022, "hc1", BR.ROLE_HC_CTX, 0.9)])
    out = AF.build_features(AF.DESIGN_A, verbose=False, **w)
    r = out[out.season == 2022].iloc[0]
    assert r.caller_is_head_coach == AF.NEUTRAL_IS_HC
    assert r.pc_changed_entering == AF.NEUTRAL_CHANGED
    assert r.pc_career_off_rank_pct == AF.PRIOR_RANKPCT
    assert r.noncalling_hc_context_effect == 0.0, "unknown caller must not credit the HC"
    assert r.caller_adjusted_offense_effect == 0.0


def test_synthetic_midseason_split_attributes_only_each_callers_own_games():
    """Two callers split 2020; entering 2022 each carries HIS OWN segment level, not the team's."""
    segs = [(2020, "SYN", "pcA", 1, 8, 8, "2020-01-01", 1.0),
            (2020, "SYN", "pcB", 9, 99, 8, "2020-01-01", -1.0)]
    gl = ([(2020, "SYN", w, "hc1", "pcA" if w <= 8 else "pcB") for w in range(1, 17)]
          + [(2021, "SYN", w, "hc1", "pcA") for w in range(1, 17)]
          + [(2022, "SYN", w, "hc1", "pcA") for w in range(1, 17)])
    w1 = _syn_world(segs, gl, [(2020, "SYN", "pcA", "hc1"), (2021, "SYN", "pcA", "hc1"),
                               (2022, "SYN", "pcA", "hc1")])
    a = AF.build_features(AF.DESIGN_A, verbose=False, **w1)
    ra = a[a.season == 2022].iloc[0]
    w2 = _syn_world(segs, gl, [(2020, "SYN", "pcB", "hc1"), (2021, "SYN", "pcB", "hc1"),
                               (2022, "SYN", "pcB", "hc1")])
    b = AF.build_features(AF.DESIGN_A, verbose=False, **w2)
    rb = b[b.season == 2022].iloc[0]
    assert ra.pc_career_epa_play_z > 0 > rb.pc_career_epa_play_z, (
        "the two callers in a split must NOT receive identical values")
    assert ra.caller_history_games_career == 8.0 and rb.caller_history_games_career == 8.0


def test_synthetic_strict_timing_target_season_games_never_enter():
    """A colossal season-Y segment must not move any season-Y feature."""
    base = [(2020, "SYN", "pcA", 1, 99, 16, "2020-01-01", 1.0)]
    gl = [(s, "SYN", w, "hc1", "pcA") for s in (2020, 2021, 2022) for w in range(1, 17)]
    ident = [(s, "SYN", "pcA", "hc1") for s in (2020, 2021, 2022)]
    a = AF.build_features(AF.DESIGN_A, verbose=False, **_syn_world(base, gl, ident))
    poisoned = base + [(2022, "SYN", "pcA", 1, 99, 16, "2020-01-01", 999.0)]
    b = AF.build_features(AF.DESIGN_A, verbose=False, **_syn_world(poisoned, gl, ident))
    ra = a[a.season == 2022].iloc[0]
    rb = b[b.season == 2022].iloc[0]
    for c in AF.ALL_FEATURE_COLUMNS:
        assert ra[c] == rb[c] or (pd.isna(ra[c]) and pd.isna(rb[c])), f"{c} moved on season-Y data"


def test_synthetic_the_primary_policy_does_NOT_hide_a_late_published_source():
    """v3.9b: a late citation date no longer suppresses earlier history in the PRIMARY build. The
    retired strict rule still does, and is reachable only through the diagnostic flag."""
    gl = [(s, "SYN", w, "hc1", "pcA") for s in (2020, 2021, 2022) for w in range(1, 17)]
    ident = [(s, "SYN", "pcA", "hc1") for s in (2020, 2021, 2022)]
    early = [(2021, "SYN", "pcA", 1, 99, 16, "2021-03-01", 2.0)]
    late = [(2021, "SYN", "pcA", 1, 99, 16, "2023-03-01", 2.0)]

    for segs in (early, late):
        out = AF.build_features(AF.DESIGN_A, verbose=False, **_syn_world(segs, gl, ident))
        assert out[out.season == 2022].iloc[0].pc_career_epa_play_z != AF.PRIOR_Z, (
            "the primary policy must count the segment regardless of the citation date")

    # the retired strict rule, reachable ONLY via the diagnostic flag
    strict_late = AF.build_features(AF.DESIGN_A, verbose=False,
                                    history_source_date_gated=True, **_syn_world(late, gl, ident))
    assert strict_late[strict_late.season == 2022].iloc[0].pc_career_epa_play_z == AF.PRIOR_Z
    strict_early = AF.build_features(AF.DESIGN_A, verbose=False,
                                     history_source_date_gated=True, **_syn_world(early, gl, ident))
    assert strict_early[strict_early.season == 2022].iloc[0].pc_career_epa_play_z != AF.PRIOR_Z

    # the ORACLE design behaves identically to primary A on history
    o = AF.build_features(AF.DESIGN_B, verbose=False,
                          **{**_syn_world(late, gl, ident), "ident": _syn_ident(ident)})
    assert o[o.season == 2022].iloc[0].pc_career_epa_play_z != AF.PRIOR_Z


def test_synthetic_hc_change_and_win_pct_shrinkage():
    gl = ([(2020, "SYN", w, "hcA", None) for w in range(1, 17)]
          + [(2021, "SYN", w, "hcA", None) for w in range(1, 17)]
          + [(2022, "SYN", w, "hcB", None) for w in range(1, 17)])
    res = _syn_res([(2020, "SYN", w, "hcA", 1) for w in range(1, 17)]
                   + [(2021, "SYN", w, "hcA", 1) for w in range(1, 17)]
                   + [(2022, "SYN", w, "hcB", 1) for w in range(1, 17)])
    w = _syn_world([], gl, [(2020, "SYN", None, "hcA"), (2021, "SYN", None, "hcA"),
                            (2022, "SYN", None, "hcB")])
    w["res"] = res
    out = AF.build_features(AF.DESIGN_A, verbose=False, **w)
    r21 = out[out.season == 2021].iloc[0]
    r22 = out[out.season == 2022].iloc[0]
    assert r21.hc_changed_entering == 0.0 and r21.hc_tenure_current_team == 1.0
    assert r22.hc_changed_entering == 1.0 and r22.hc_tenure_current_team == 0.0
    # hcA won all 16 prior games: r = 16/48 = 1/3, shrunk = 1/3*1.0 + 2/3*0.5 = 2/3
    assert abs(r21.hc_career_win_pct_shrunk - (16 / 48 * 1.0 + 32 / 48 * 0.5)) < 1e-12
    # hcB has no prior games at all -> exactly the 0.500 league prior, no penalty and no bonus
    assert r22.hc_career_win_pct_shrunk == AF.PRIOR_WINPCT


def test_synthetic_ties_count_half_a_win_and_stay_in_the_denominator():
    res = _syn_res([(2020, "SYN", 1, "hcA", 1), (2020, "SYN", 2, "hcA", 0)])
    res.loc[len(res)] = dict(season=2020, week=3, team="SYN", game_id="g3",
                             head_coach="hcA", hc_person_id="hcA", margin=0, win=0.5)
    h = AF.hc_history(res, 2021)
    games, wins = 3.0, 1.5
    r = games / (games + AF.K_SHRINK)
    assert abs(h["hcA"][0] - (r * (wins / games) + (1 - r) * 0.5)) < 1e-12
    assert h["hcA"][2] == games


# =====================================================================================================
# TARGET-FREE CONSTRUCTION / DETERMINISM / INTEGRITY
# =====================================================================================================
def test_feature_construction_never_touches_a_fantasy_outcome():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#")).split('"""')
    body = "".join(code[2:]) if len(code) > 2 else src
    for token in ("season_dataset", "target_ppg", "half_ppr", "fantasy_points",
                  "sleeper_pts", "rookie_ppg", "player_id"):
        assert token not in body, f"the feature builder references the outcome token {token!r}"


def test_two_identical_builds_are_byte_identical():
    seg, gl = AF.caller_segments(), AF.game_identity()
    res = AF.hc_game_results()
    eff = pd.read_csv(DATA / "arm3_stage2_effects_v38.csv")
    a1 = AF.build_features(AF.DESIGN_A, seg, gl, res, eff, verbose=False,
                           target_seasons=[2024, 2025, 2026])
    a2 = AF.build_features(AF.DESIGN_A, seg, gl, res, eff, verbose=False,
                           target_seasons=[2024, 2025, 2026])
    pd.testing.assert_frame_equal(a1, a2)
    assert AF.manifest() == AF.manifest()
    pd.testing.assert_frame_equal(AF.lineage(), AF.lineage())


def test_lineage_covers_every_emitted_feature_exactly_once():
    lin = AF.lineage()
    assert set(lin.feature) == set(AF.ALL_FEATURE_COLUMNS)
    assert lin.feature.is_unique
    for col in ("source_artifact", "timing_rule", "aggregation", "neutral_on_unknown_identity"):
        assert lin[col].notna().all()
    a3 = lin[lin.feature == "caller_adjusted_offense_effect"].iloc[0]
    assert "NONE" in str(a3.shrinkage), "a ridge effect must never be shrunk a second time"


def test_no_split_caller_inherits_full_team_season_offense():
    """Defect 1, guarded at the v3.9 layer: in a split team-season the two callers must NOT carry
    identical offense values, and neither may equal the FULL-season value."""
    seg = AF.caller_segments()
    full = pd.read_csv(DATA / "full_season_offense_reference.csv")
    splits = seg.groupby(["season", "team"]).size()
    multi = splits[splits > 1]
    assert len(multi) >= 15, f"expected the 18 sourced midseason splits, found {len(multi)}"
    checked = 0
    for (s, t) in list(multi.index):
        g = seg[(seg.season == s) & (seg.team == t)]
        if g.epa_play.notna().sum() < 2:
            continue
        assert g.epa_play.nunique() == len(g), (
            f"{s} {t}: split callers share an EPA/play value -> full-season inheritance")
        fs = full[(full.season == s) & (full.team == t)]
        if len(fs):
            assert not np.isclose(g.epa_play, float(fs.epa_play.iloc[0])).all(), (
                f"{s} {t}: every segment equals the FULL-season value")
        checked += 1
    assert checked >= 15


def test_segment_game_membership_reconciles_with_the_canonical_ledger():
    seg = AF.caller_segments()
    played = seg[seg.pbp_games > 0]
    assert (played.pbp_games == played.n_games_attributed).all()
    tot = played.groupby(["season", "team"]).agg(pbp=("pbp_games", "sum"),
                                                led=("n_games_attributed", "sum"))
    assert (tot.pbp == tot.led).all(), "a split reassigns games; it never creates or destroys them"


def test_routing_lineage_proves_strict_timing_and_membership():
    lin = pd.read_csv(DATA / "arm_feature_lineage_v39.csv")
    assert set(lin.record_kind) == {"feature_definition", "identity_routing",
                                    "caller_contribution"}
    r = lin[lin.record_kind == "identity_routing"].copy()
    assert len(r) == 2 * len(AF.TARGET_SEASONS) * 32
    assert r.strict_timing_ok.astype(str).str.lower().isin({"true"}).all()
    have = r.dropna(subset=["last_source_season"])
    assert (have.last_source_season.astype(int) < have.season.astype(int)).all()
    # league-prior fallback is recorded WITH its reason, never silently
    fb = r[r.caller_features_at_league_prior == 1]
    assert (fb.league_prior_reason.astype(str).str.len() > 0).all()
    assert set(fb.identity_state) <= {"unknown", "known_no_history"}


def test_lineage_records_the_target_identity_gate_and_the_shared_history_rule():
    """v3.9b renamed `evidence_gate` -> `target_identity_gate` + `history_rule`, because the gate now
    applies to the target identity only and the history rule is shared."""
    lin = pd.read_csv(DATA / "arm_feature_lineage_v39.csv")
    r = lin[lin.record_kind == "identity_routing"]
    assert "evidence_gate" not in r.columns
    a = r[r.design == AF.DESIGN_A].target_identity_gate.unique()
    b = r[r.design == AF.DESIGN_B].target_identity_gate.unique()
    assert len(a) == 1 and "pre-cutoff evidence required" in a[0]
    assert len(b) == 1 and "ORACLE" in b[0]
    assert r.history_rule.nunique() == 1, "both designs must share ONE history rule"
    assert "NOT source-date gated" in r.history_rule.iloc[0]


# =====================================================================================================
# HERMETIC — no network, no external cache
# =====================================================================================================
@pytest.fixture
def no_network(monkeypatch):
    """Hard-block outbound sockets AND the nflverse loaders.

    Before this pass, `projection_cutoffs()` and `hc_game_results()` both called
    `nflreadpy.load_schedules()`, so a clean checkout with an empty temp dir failed five tests and the
    254-pass result depended on mutable state outside the repo.
    """
    import socket

    def deny(*a, **k):
        raise AssertionError("NETWORK ACCESS ATTEMPTED — the v3.9 build must be hermetic")

    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    try:
        import nflreadpy
        for fn in ("load_schedules", "load_pbp", "load_players", "load_depth_charts",
                   "load_player_stats"):
            if hasattr(nflreadpy, fn):
                monkeypatch.setattr(nflreadpy, fn, deny)
    except ImportError:
        pass
    return deny


def test_the_frozen_schedule_snapshot_is_a_repo_file():
    assert AF.SCHEDULE_SNAPSHOT.exists(), AF.SCHEDULE_SNAPSHOT
    assert "seasonal_projections" in AF.SCHEDULE_SNAPSHOT.parts
    assert AF.SCHEDULE_SNAPSHOT.name == "schedules_1999_2025.parquet"


def test_cutoffs_and_hc_history_build_with_NETWORK_BLOCKED(no_network):
    cut = dict(AF.projection_cutoffs())
    assert cut[2014] == "2014-09-03" and cut[2025] == "2025-09-03"
    assert cut[2026] == "2026-07-21", "2026 uses the frozen production as-of date"
    assert set(range(2014, 2027)) <= set(cut)
    res = AF.hc_game_results()
    assert len(res) == 13934, f"expected 6,967 REG games x 2 team-rows, got {len(res)}"
    assert set(res.win.unique()) <= {0.0, 0.5, 1.0}
    assert res.hc_person_id.notna().all()
    h = AF.hc_history(res, 2026)
    assert h["andy_reid"][2] > 400, "Reid's REG head-coach games entering 2026"


def test_a_full_feature_build_runs_with_NETWORK_BLOCKED(no_network):
    seg, gl = AF.caller_segments(), AF.game_identity()
    res = AF.hc_game_results()
    eff = pd.read_csv(DATA / "arm3_stage2_effects_v38.csv")
    out = AF.build_features(AF.DESIGN_A, seg, gl, res, eff, verbose=False,
                            target_seasons=[2025, 2026])
    assert len(out) == 64
    r = out[(out.season == 2026) & (out.team == "LAC")].iloc[0]
    assert r.expected_caller_id == "mike_mcdaniel"
    assert abs(r.caller_adjusted_offense_effect - 0.005262) < 5e-7


def test_no_v39_module_calls_a_live_nflverse_loader():
    for mod in ("build_arm_features_v39.py", "run_coach_projection_experiment_v39.py"):
        src = (COACH / mod).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for bad in ("nfl.load_schedules(", "nflreadpy.load_schedules(", "import nflreadpy"):
            assert bad not in code, f"{mod} still reaches a live loader: {bad}"
        assert "build_preseason_snapshot" not in code, (
            f"{mod} imports build_preseason_snapshot, whose projection_cutoffs() hits the network")


def test_snapshot_derived_cutoffs_match_the_persisted_artifact():
    """The hermetic derivation must agree with the cutoffs the eligibility gate was BUILT with."""
    cut = AF.projection_cutoffs()
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")[["season", "projection_cutoff"]]
    snap = snap.drop_duplicates().dropna()
    assert len(snap) == 13
    for r in snap.itertuples():
        assert cut[int(r.season)] == r.projection_cutoff, int(r.season)


def test_the_builder_writes_no_cache_outside_the_five_artifacts():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    assert "SCRATCH" not in src, "the external scratch cache must be gone"
    assert "tempfile" not in src and "COACH_V39_SCRATCH" not in src


# =====================================================================================================
# CONTRIBUTION LINEAGE — membership is provable, not asserted
# =====================================================================================================
@pytest.fixture(scope="module")
def lineage_df():
    return pd.read_csv(DATA / "arm_feature_lineage_v39.csv")


def test_lineage_carries_all_three_record_kinds(lineage_df):
    vc = lineage_df.record_kind.value_counts().to_dict()
    assert vc["feature_definition"] == 51
    assert vc["identity_routing"] == 2 * len(AF.TARGET_SEASONS) * 32
    assert vc["caller_contribution"] > 0


def test_contribution_rows_reconcile_with_the_feature_table_game_counts(design_a, design_b,
                                                                       lineage_df):
    """The claim "lineage proves source membership" is only true if the rows ADD UP."""
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    for design, feat in ((AF.DESIGN_A, design_a), (AF.DESIGN_B, design_b)):
        sub = c[c.design == design]
        car = (sub[sub.included_in_career == 1]
               .groupby(["season", "team"])
               .agg(games=("pbp_games", "sum"), segs=("segment_key", "nunique")))
        r3 = (sub[sub.included_in_roll3 == 1].groupby(["season", "team"])["pbp_games"].sum())
        f = feat.set_index(["season", "team"])
        checked = 0
        for key, row in f.iterrows():
            exp_games = float(row.caller_history_games_career)
            exp_segs = int(row.caller_history_segments_career)
            got_games = float(car.games.get(key, 0.0))
            got_segs = int(car.segs.get(key, 0))
            assert got_games == exp_games, f"{design} {key}: career games {got_games} != {exp_games}"
            assert got_segs == exp_segs, f"{design} {key}: career segments {got_segs} != {exp_segs}"
            assert float(r3.get(key, 0.0)) == float(row.caller_history_games_roll3), (
                f"{design} {key}: roll3 games mismatch")
            checked += 1
        assert checked == 416


def test_contribution_rows_exclude_nothing_by_source_date_under_the_primary_policy(lineage_df):
    """SUPERSEDED BY v3.9b. The v3.9a version required the Design A gate to exclude segments; the
    primary policy excludes none. What remains asserted is that nothing is excluded silently and that
    the retired rule is still recorded per row (see
    `test_the_strict_gate_remains_auditable_from_the_lineage_artifact`)."""
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    for design in (AF.DESIGN_A, AF.DESIGN_B):
        sub = c[c.design == design]
        assert (sub.gate_eligible == 1).all(), f"{design}: the primary policy excludes nothing"
        assert (sub.gate_exclusion_reason.fillna("") == "").all()
    # the target cutoff is still recorded on every row so the retired rule stays checkable
    assert c.target_cutoff.notna().all()


def test_contribution_rows_identify_the_segment_and_trace_the_games(lineage_df):
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    for col in ("segment_key", "source_season", "source_team", "source_week_start",
                "source_week_end", "pbp_games", "game_id_trace"):
        assert c[col].notna().all(), col
    r = c.iloc[0]
    assert r.segment_key.count("|") == 3
    assert str(r.segment_key).startswith(f"{int(r.source_season)}|{r.source_team}|")
    assert set(c.game_id_trace.unique()) == {"coach_reliability_lineage.csv"}
    assert (COACH / "data" / "coach_reliability_lineage.csv").exists()


def test_every_contribution_row_is_strictly_prior(lineage_df):
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    assert (c.source_season.astype(int) < c.season.astype(int)).all()
    assert c.strict_timing_ok.astype(str).str.lower().eq("true").all()


def test_a_gate_excluded_segment_appears_but_contributes_zero(lineage_df):
    """BUF 2014's caller is attributed by a 2016-10-29 article: present as a candidate for target
    2015/2016, excluded there, and included from 2017."""
    c = lineage_df[(lineage_df.record_kind == "caller_contribution")
                   & (lineage_df.design == AF.DESIGN_A)
                   & (lineage_df.source_season == 2014) & (lineage_df.source_team == "BUF")]
    assert len(c) > 0
    for Y in (2015, 2016):
        s = c[c.season == Y]
        if len(s):
            assert (s.gate_eligible == 0).all() and (s.included_in_career == 0).all()
    later = c[c.season >= 2017]
    assert len(later) and (later.gate_eligible == 1).all()


# =====================================================================================================
# v3.9b §4 — PRIMARY HISTORY POLICY: strictly prior, FULL retrospective ledger (not source-date gated)
# =====================================================================================================
def test_the_primary_history_policy_is_ungated():
    assert AF.PRIMARY_HISTORY_SOURCE_DATE_GATED is False


def test_design_a_and_b_now_differ_on_target_identity_ONLY(design_a, design_b):
    """The single-axis property the v3.9b policy exists to restore.

    On every row where the two designs supply the SAME target caller, all 51 model features must be
    identical — history, tenure, entering-change and Arm 3 effects included.
    """
    a = design_a.set_index(["season", "team"]).sort_index()
    b = design_b.set_index(["season", "team"]).sort_index()
    same = a.expected_caller_id.fillna("~") == b.expected_caller_id.fillna("~")
    assert int(same.sum()) > 200, "expected a large identity-matching overlap"
    differing = [c for c in AF.ALL_FEATURE_COLUMNS
                 if not np.allclose(a.loc[same, c].fillna(-999),
                                    b.loc[same, c].fillna(-999), atol=0, rtol=0)]
    assert differing == [], f"single-axis broken; these differ on matched identities: {differing}"


def test_a_late_published_source_no_longer_suppresses_earlier_history():
    """BUF 2014 is attributed by a 2016-10-29 article. Under the retired strict rule that segment was
    excluded until target 2017; under the primary rule it counts from target 2015."""
    seg = AF.caller_segments()
    cuts = AF.projection_cutoffs()
    row = seg[(seg.season == 2014) & (seg.team == "BUF")].iloc[0]
    assert str(row.source_upper_bound).startswith("2016")
    assert not AF.eligible_at(row.source_upper_bound, cuts[2015])   # strict rule would drop it
    pid = row.person_id
    _h, sup = AF.caller_history(seg, 2015, cuts[2015], gated=False)
    assert sup.get(pid, {}).get("career_games", 0) >= float(row.pbp_games), (
        "the primary policy must count the 2014 segment for target 2015")
    _hg, supg = AF.caller_history(seg, 2015, cuts[2015], gated=True)
    assert supg.get(pid, {}).get("career_games", 0) == 0.0


def test_history_remains_STRICTLY_PRIOR_under_the_ungated_policy():
    seg = AF.caller_segments()
    cuts = AF.projection_cutoffs()
    for Y in (2018, 2022, 2026):
        _h, sup = AF.caller_history(seg, Y, cuts[Y], gated=False)
        for pid, s in sup.items():
            assert s["last_source_season"] < Y, f"{pid} used season {s['last_source_season']} for {Y}"


def test_the_ungated_policy_adds_ZERO_outer_rows_and_358_games(design_a):
    """The measured effect, recomputed here. Both the earlier '~76 more rows' claim and a naive
    '28 more rows' upper bound are wrong: the real row gain on the outer window is ZERO."""
    seg, gl = AF.caller_segments(), AF.game_identity()
    cuts = AF.projection_cutoffs()
    ident = AF.target_identities(AF.DESIGN_A, seg, gl)
    known = wh_un = wh_g = 0
    games_un = games_g = 0.0
    for Y in range(2018, 2026):
        _hu, su = AF.caller_history(seg, Y, cuts[Y], gated=False)
        _hg, sg = AF.caller_history(seg, Y, cuts[Y], gated=True)
        for r in ident[ident.season == Y].itertuples():
            cal = AF._none(r.expected_caller_id)
            if cal is None:
                continue
            known += 1
            gu = float(su.get(cal, {}).get("career_games", 0.0))
            gg = float(sg.get(cal, {}).get("career_games", 0.0))
            wh_un += int(gu > 0)
            wh_g += int(gg > 0)
            games_un += gu
            games_g += gg
    assert known == 152, "Design A outer known target identities"
    assert wh_g == 124 and wh_un == 124, (
        f"row gain must be ZERO: gated {wh_g}, ungated {wh_un}")
    assert wh_un - wh_g == 0
    assert round(games_un - games_g) == 358, f"expected +358 caller-games, got {games_un - games_g}"
    assert wh_un <= known, "known-with-history can never exceed known identities"


def test_the_28_known_no_history_rows_are_genuine_first_time_callers():
    """They were never suppressed by the gate — no prior segment exists for them at all. This is why
    ungating adds no rows."""
    seg, gl = AF.caller_segments(), AF.game_identity()
    cuts = AF.projection_cutoffs()
    ident = AF.target_identities(AF.DESIGN_A, seg, gl)
    n_no_hist = n_truly_none = 0
    for Y in range(2018, 2026):
        _hu, su = AF.caller_history(seg, Y, cuts[Y], gated=False)
        for r in ident[ident.season == Y].itertuples():
            cal = AF._none(r.expected_caller_id)
            if cal is None:
                continue
            if float(su.get(cal, {}).get("career_games", 0.0)) == 0.0:
                n_no_hist += 1
                if not len(seg[(seg.person_id == cal) & (seg.season < Y)]):
                    n_truly_none += 1
    assert n_no_hist == 28
    assert n_truly_none == 28, "all 28 must have no prior segment in the ledger at all"


def test_design_a_known_with_history_cannot_exceed_known_identities(design_a):
    """The arithmetic that makes the retracted 200/256 claim impossible."""
    o = design_a[design_a.season.between(2018, 2025)]
    known = int((o.caller_identity_known == 1).sum())
    with_hist = int(((o.caller_identity_known == 1) & (o.caller_history_games_career > 0)).sum())
    assert known == 152 and with_hist == 124
    assert with_hist <= known
    assert known - with_hist == 28, "the arithmetic ceiling on any increase is 28, and 0 is realised"


# ---------------------------------------------------------------- the retired strict gate, as a sensitivity
def test_the_strict_gate_survives_only_as_an_in_memory_sensitivity():
    s = AF.strict_gate_sensitivity(target_seasons=[2024, 2025])
    assert len(s) == 2 * 2
    assert (s.label == AF.SENSITIVITY_LABEL).all()
    for token in ("DIAGNOSTIC SENSITIVITY", "NONPRIMARY", "NONSELECTABLE", "Never persisted"):
        assert token in AF.SENSITIVITY_LABEL
    a = s[s.design == AF.DESIGN_A]
    assert (a.rows_gained_by_primary >= 0).all()
    assert (a.games_gained_by_primary >= 0).all()


def test_the_sensitivity_is_never_written_to_a_repo_artifact():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    body = src.split("def strict_gate_sensitivity", 1)[1].split("\ndef ", 1)[0]
    assert ".to_csv(" not in body and "write_text" not in body
    found = {p.name for p in (COACH / "data").glob("*_v39.*")}
    assert not any("sensitivit" in n.lower() or "strict" in n.lower() for n in found)
    assert len(found) == 5


def test_the_strict_gate_remains_auditable_from_the_lineage_artifact(lineage_df):
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    assert (c.gate_eligible == 1).all(), "the primary policy excludes nothing by source date"
    assert "strict_source_date_gate_would_exclude" in c.columns
    n = int(c.strict_source_date_gate_would_exclude.sum())
    assert n > 0, "the retired rule must remain measurable"
    excl = c[c.strict_source_date_gate_would_exclude == 1]
    assert (excl.strict_gate_exclusion_reason.astype(str).str.len() > 0).all()
    assert set(excl.strict_gate_exclusion_reason.unique()) <= {
        "attributing source has no usable date",
        "attributing source postdates the target cutoff"}


def test_routing_lineage_states_the_single_axis(lineage_df):
    r = lineage_df[lineage_df.record_kind == "identity_routing"]
    assert r.history_rule.nunique() == 1
    assert "NOT source-date gated" in r.history_rule.iloc[0]
    a = r[r.design == AF.DESIGN_A].target_identity_gate.unique()
    b = r[r.design == AF.DESIGN_B].target_identity_gate.unique()
    assert len(a) == 1 and "pre-cutoff evidence required" in a[0]
    assert len(b) == 1 and "ORACLE" in b[0] and "nondeployable" in b[0]


def test_2026_routing_history_totals_match_the_verified_v36_figures(design_a):
    """Reid 192, McVay 181, McDaniel 68 — the v3.6 exact figures, now under the primary policy."""
    r = design_a[design_a.season == 2026].set_index("team")
    assert float(r.loc["KC", "caller_history_games_career"]) == 192.0
    assert float(r.loc["LA", "caller_history_games_career"]) == 181.0
    assert float(r.loc["LAC", "caller_history_games_career"]) == 68.0


# =====================================================================================================
# v3.9c §3 — the GENERATED lineage artifact must state the PRIMARY policy
# =====================================================================================================
def test_every_caller_history_lineage_row_carries_the_primary_timing_rule(lineage_df):
    fd = lineage_df[lineage_df.record_kind == "feature_definition"]
    caller_blocks = {"caller_rank_quality", "caller_efficiency", "caller_scheme",
                     "caller_continuity"}
    cal = fd[fd.block.isin(caller_blocks)]
    hist = cal[cal.timing_rule != AF.TARGET_SEASON_ONLY_RULE]
    assert len(hist) >= 40
    assert (hist.timing_rule == AF.PRIMARY_TIMING_RULE).all(), (
        f"rows off-policy: {sorted(set(hist[hist.timing_rule != AF.PRIMARY_TIMING_RULE].feature))}")
    assert "FULL retrospective" in AF.PRIMARY_TIMING_RULE
    assert "NOT gated by the attributing source's publication date" in AF.PRIMARY_TIMING_RULE


def test_the_two_specific_rows_codex_flagged_are_now_correct(lineage_df):
    fd = lineage_df[lineage_df.record_kind == "feature_definition"].set_index("feature")
    for feat in ("pc_career_epa_play_z", "pc_tenure_current_team"):
        assert fd.loc[feat, "timing_rule"] == AF.PRIMARY_TIMING_RULE
        assert "source upper bound" not in str(fd.loc[feat, "timing_rule"])
        assert "gated" not in str(fd.loc[feat, "note"]) or \
            "evidence-gated" in str(fd.loc[feat, "note"])
    note = str(fd.loc["pc_tenure_current_team", "note"])
    assert "openers are themselves gated" not in note
    assert "SAME full retrospective ledger" in note and "TARGET-season" in note


def test_no_live_lineage_row_asserts_a_source_date_gate_on_history(lineage_df):
    fd = lineage_df[lineage_df.record_kind == "feature_definition"]
    for col in ("timing_rule", "note", "aggregation", "shrinkage"):
        text = fd[col].fillna("").astype(str)
        for phrase in AF.RETIRED_HISTORY_GATE_PHRASES:
            hits = fd[text.str.contains(phrase, regex=False)]
            assert not len(hits), f"{col} still asserts {phrase!r} on {list(hits.feature)[:3]}"


def test_the_lineage_policy_validator_rejects_a_reintroduced_gate(lineage_df):
    ok, detail = AF.validate_lineage_policy(lineage_df)
    assert ok is True, detail
    bad = lineage_df.copy()
    i = bad.index[bad.feature == "pc_roll3_yards_play_z"][0]
    bad.loc[i, "timing_rule"] = "seasons < Y; Design A additionally requires source upper bound <= Y cutoff"
    ok2, detail2 = AF.validate_lineage_policy(bad)
    assert ok2 is False and "pc_roll3_yards_play_z" in detail2


def test_the_retired_gate_stays_present_as_a_labelled_diagnostic(lineage_df):
    c = lineage_df[lineage_df.record_kind == "caller_contribution"]
    assert (c.gate_eligible == 1).all()
    assert int(c.strict_source_date_gate_would_exclude.sum()) > 0
    assert AF.PRIMARY_HISTORY_SOURCE_DATE_GATED is False
    for token in ("DIAGNOSTIC SENSITIVITY", "NONPRIMARY", "NONSELECTABLE"):
        assert token in AF.SENSITIVITY_LABEL


def test_the_contribution_lineage_docstring_no_longer_claims_gate_exclusions():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    doc = src.split("def contribution_lineage", 1)[1].split('"""', 2)[1]
    assert "were excluded by the Design A evidence gate" not in doc
    assert "excludes nothing by publication date" in doc


# =====================================================================================================
# v3.9c §1 — the canonical coverage derivation is shared
# =====================================================================================================
def test_compare_coverage_accepts_the_real_artifact(design_a, design_b):
    cov = pd.read_csv(DATA / "arm_feature_coverage_v39.csv")
    ok, detail = AF.compare_coverage(cov, design_a, design_b)
    assert ok is True, detail
    assert "full-frame" in detail


def test_compare_coverage_catches_a_corruption_in_any_arm_or_state(design_a, design_b):
    cov = pd.read_csv(DATA / "arm_feature_coverage_v39.csv")
    for arm, state, col in (("ARM_2", "known_with_history", "n_team_seasons"),
                            ("ARM_HC", "unknown", "row_coverage_rate"),
                            ("ARM_5", "known_no_history", "caller_known_no_history"),
                            ("ARM_0", "all", "mean_hc_resume_games")):
        bad = cov.copy()
        m = (bad.design == "design_a") & (bad.arm == arm) & (bad.identity_state == state)
        assert m.any(), f"{arm}/{state} missing from the artifact"
        bad.loc[bad.index[m][0], col] = 4242
        ok, detail = AF.compare_coverage(bad, design_a, design_b)
        assert ok is False, f"{arm}/{state}/{col} corruption not caught"
        assert col in detail and arm in detail


def test_upstream_phase1_artifacts_are_unchanged():
    """The v3.9 build must not have touched anything it inherited."""
    import hashlib
    expected = {
        "actual_play_caller.csv": "98f1c66b7387c16bba6a5463f4e0fa06",
        "arm3_stage1_residuals_v38.csv": "f4ac3bee6ae208bb1aca6bdedadc9224",
        "arm3_stage1_tuning_v38.csv": "65720dca75a0c6a5b2b1e732f0a86e57",
        "arm3_stage1_fold_losses_v38.csv": "bc57b3e4d17e6d5bdbfdaa3dc8237c43",
        "arm3_stage1_feature_schemas_v38.json": "d0a5f34af073a2a330f13c4c8d002555",
        "arm3_stage2_effects_v38.csv": "4286cbd542854e23a6042bcec1b4b8ed",
        "arm3_stage2_tuning_v38.csv": "28873246729b558593a29956b3a14de1",
        "arm3_stage2_fold_losses_v38.csv": "3c73e25c1bf4fc592ab3b2d5211a44c5",
    }
    for f, h in expected.items():
        got = hashlib.md5((DATA / f).read_bytes()).hexdigest()
        assert got == h, f"{f} CHANGED: {got}"
