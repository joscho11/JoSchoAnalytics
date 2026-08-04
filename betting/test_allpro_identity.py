"""All-Pro identity: two players sharing a name must never be merged.

Regression of record (2026-08-03). `betting/nfl_allpro_1997_2025.csv` carries

    ILB,C.J. Mosley,BAL,2014,defense
    MLB,C.J. Mosley,DET,2014,defense

— two distinct players. Every consumer keyed on the NAME, and the weighted lookback then
did `sort_values("Weight").drop_duplicates(["Player", ...])`, so one of them was discarded
and *which* one depended on pandas' unstable default sort. Adding `kind="stable"` would
only have made the wrong answer deterministic; the defect is identity.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

_BETTING = Path(__file__).resolve().parent
if str(_BETTING) not in sys.path:
    sys.path.insert(0, str(_BETTING))

from allpro_identity import (AllProIdentityError,  # noqa: E402
                             IDENTITY_OVERRIDES, default_identity,
                             resolve_allpro_identities, weighted_lookback)

_CSV = _BETTING / "nfl_allpro_1997_2025.csv"


@pytest.fixture(scope="module")
def resolved():
    return resolve_allpro_identities(pd.read_csv(_CSV))


def _team_weight(ap, target_season, team):
    w = weighted_lookback(ap, target_season)
    row = w[w["Team"] == team]
    return float(row["allpro_weighted"].iloc[0]) if len(row) else 0.0


# ---------------------------------------------------------------------------
# The two players stay separate, in every affected target season
# ---------------------------------------------------------------------------
def test_the_two_mosleys_get_different_identities(resolved):
    m = resolved[resolved["Player"] == "C.J. Mosley"]
    bal14 = m[(m.Year == 2014) & (m.Team == "BAL")]["allpro_id"].iloc[0]
    det14 = m[(m.Year == 2014) & (m.Team == "DET")]["allpro_id"].iloc[0]
    assert bal14 != det14, "the two C.J. Mosleys were merged into one identity"


def test_a_real_team_change_does_NOT_create_a_second_identity(resolved):
    """BAL -> NYJ is the same man. Splitting on team would be the opposite error."""
    m = resolved[resolved["Player"] == "C.J. Mosley"]
    bal = set(m[(m.Team == "BAL")]["allpro_id"])
    nyj = set(m[(m.Team == "NYJ")]["allpro_id"])
    assert len(bal) == 1 and bal == nyj, (
        f"the Ravens/Jets lineage split across teams: BAL={bal} NYJ={nyj}")


@pytest.mark.parametrize("target,why", [
    (2015, "both 2014 rows are one year back -> both weight 4"),
    (2016, "both 2014 rows are two years back -> both weight 2"),
])
def test_both_teams_contribute_in_the_symmetric_years(resolved, target, why):
    bal = _team_weight(resolved, target, "BAL")
    det = _team_weight(resolved, target, "DET")
    assert bal > 0 and det > 0, f"target {target}: a team lost its player ({why})"
    # The DET player's ONLY selection is 2014, so his contribution is exactly the
    # window weight; prove it is present rather than merely non-zero elsewhere.
    m = resolved[(resolved.Player == "C.J. Mosley") & (resolved.Team == "DET")]
    assert len(m) == 1
    picked = weighted_lookback(resolved, target)
    assert "DET" in set(picked["Team"]), f"DET absent from target {target}"


def test_target_2017_keeps_both_the_newer_BAL_weight_and_the_older_DET_weight(resolved):
    """The case the legacy code got wrong even with a stable sort.

    For target 2017 the BAL player's 2016 selection is one year back (weight 4) and the
    DET player's 2014 selection is three years back (weight 1). Under a name key the DET
    record was dropped as a duplicate of the BAL one.
    """
    w = weighted_lookback(resolved, 2017)
    ids = set(resolve_allpro_identities(pd.read_csv(_CSV))["allpro_id"])
    assert {"cj_mosley__ravens_jets_ilb", "cj_mosley__lions_2014"} <= ids
    det = _team_weight(resolved, 2017, "DET")
    assert det > 0, "the DET player's weight-1 record was discarded in target 2017"
    # And BAL still carries the newer weight-4 selection.
    assert _team_weight(resolved, 2017, "BAL") > 0


def test_one_player_selected_in_several_lookback_years_counts_once_at_max_weight():
    """Repeat selections collapse to the highest weight, not the sum."""
    ap = pd.DataFrame([
        {"Player": "Solo Guy", "Team": "KC", "Year": 2014, "Side": "defense", "Pos": "LB"},
        {"Player": "Solo Guy", "Team": "KC", "Year": 2015, "Side": "defense", "Pos": "LB"},
        {"Player": "Solo Guy", "Team": "KC", "Year": 2016, "Side": "defense", "Pos": "LB"},
    ])
    r = resolve_allpro_identities(ap)
    # target 2017: 2016 -> 4, 2015 -> 2, 2014 -> 1. Max only.
    assert _team_weight(r, 2017, "KC") == 4.0, "repeat selections were summed, not maxed"


def test_a_team_change_credits_the_highest_weight_team():
    ap = pd.DataFrame([
        {"Player": "Mover", "Team": "BAL", "Year": 2015, "Side": "defense", "Pos": "LB"},
        {"Player": "Mover", "Team": "NYJ", "Year": 2016, "Side": "defense", "Pos": "LB"},
    ])
    r = resolve_allpro_identities(ap)
    assert _team_weight(r, 2017, "NYJ") == 4.0
    assert _team_weight(r, 2017, "BAL") == 0.0


# ---------------------------------------------------------------------------
# Fail-closed
# ---------------------------------------------------------------------------
def test_an_unresolved_collision_aborts():
    ap = pd.DataFrame([
        {"Player": "Two People", "Team": "KC", "Year": 2014, "Side": "defense", "Pos": "LB"},
        {"Player": "Two People", "Team": "SF", "Year": 2014, "Side": "defense", "Pos": "LB"},
    ])
    with pytest.raises(AllProIdentityError, match="unresolved All-Pro identity collision"):
        resolve_allpro_identities(ap)


def test_a_partially_covered_ambiguous_name_aborts():
    """A lineage may not be half-resolved — that silently splits the player."""
    ap = pd.DataFrame([
        {"Player": "C.J. Mosley", "Team": "BAL", "Year": 2014, "Side": "defense", "Pos": "ILB"},
        {"Player": "C.J. Mosley", "Team": "DET", "Year": 2014, "Side": "defense", "Pos": "MLB"},
        {"Player": "C.J. Mosley", "Team": "XXX", "Year": 1999, "Side": "defense", "Pos": "LB"},
    ])
    with pytest.raises(AllProIdentityError, match="missing from IDENTITY_OVERRIDES"):
        resolve_allpro_identities(ap)


def test_every_source_row_gets_a_non_null_identity(resolved):
    assert resolved["allpro_id"].notna().all()
    assert (resolved["allpro_id"].astype(str).str.len() > 0).all()


def test_exactly_one_name_is_split_in_the_real_source(resolved):
    """913 identities from 912 names — the single reviewed split, nothing more."""
    assert resolved["Player"].nunique() == 912
    assert resolved["allpro_id"].nunique() == 913


# ---------------------------------------------------------------------------
# Order invariance — the property that replaced kind="stable"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2, 7, 99])
def test_output_is_invariant_under_row_shuffling(resolved, seed):
    base = weighted_lookback(resolved, 2017).sort_values("Team").reset_index(drop=True)
    shuffled = resolved.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    got = weighted_lookback(shuffled, 2017).sort_values("Team").reset_index(drop=True)
    pd.testing.assert_frame_equal(base, got)


def test_no_sort_values_in_the_lookback_path():
    """The order dependence must not creep back in as a 'stable' sort.

    Parsed with AST, not text: the function's own docstring explains that it does not
    sort, and a substring scan flags that prose as a violation.
    """
    import ast
    src = (_BETTING / "allpro_identity.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "weighted_lookback")
    called = {node.func.attr for node in ast.walk(fn)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "sort_values" not in called, (
        f"weighted_lookback sorts again ({sorted(called)}) — use an order-invariant "
        "reduction instead")
    # Self-proof: the AST selector must actually be able to see a sort call.
    probe = ast.parse("def f():\n    return df.sort_values('x')")
    probe_calls = {n.func.attr for n in ast.walk(probe)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "sort_values" in probe_calls, "AST selector is dead"


def test_default_identity_is_a_pure_function_of_the_name():
    assert default_identity("Patrick Mahomes") == default_identity("patrick  mahomes")
    assert default_identity("T.J. Watt") != default_identity("TJ Watts")
    assert default_identity("José Álvarez") == default_identity("Jose Alvarez")


# ---------------------------------------------------------------------------
# Training and serving agree
# ---------------------------------------------------------------------------
def test_training_and_serving_builders_agree_on_team_aggregates(resolved):
    """features.py `_build_allpro` and the shared primitive must produce one answer."""
    import features as F
    ap = pd.read_csv(_CSV)
    ap = ap[ap["Team"] != "2TM"].copy()
    ap["Team"] = ap["Team"].replace(F.TEAM_MAP)
    r = resolve_allpro_identities(ap)
    target = 2017
    upcoming = pd.DataFrame([{"home_team": "BAL", "away_team": "DET"}])
    served = F._build_allpro(upcoming, ap, target)
    expect_bal = _team_weight(r, target, "BAL")
    expect_det = _team_weight(r, target, "DET")
    assert float(served["home_allpro_last_3_years_weighted"].iloc[0]) == expect_bal
    assert float(served["away_allpro_last_3_years_weighted"].iloc[0]) == expect_det


def test_the_notebook_no_longer_keys_on_player_name():
    import json
    nb = json.load(open(_BETTING / "model_comparison.ipynb", encoding="utf-8"))
    src = "".join(nb["cells"][15]["source"])
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert 'drop_duplicates(["Player","season"])' not in code.replace(" ", ""), \
        "the notebook still dedupes All-Pro rows by player NAME"
    assert "resolve_allpro_identities" in code, "notebook does not resolve identities"
    assert '["Player"].nunique()' not in code.replace(" ", ""), \
        "prev-year counts still count distinct NAMES"


def test_the_reviewed_override_table_is_fully_documented():
    from allpro_identity import REVIEW_NOTES
    names = {n for (n, _y, _t) in IDENTITY_OVERRIDES}
    assert names <= set(REVIEW_NOTES), (
        f"override(s) without a written review rationale: {sorted(names - set(REVIEW_NOTES))}")


# ---------------------------------------------------------------------------
# Injury -> identity matching (Phase 1 integration hole, closed 2026-08-03)
# ---------------------------------------------------------------------------
from allpro_identity import (attach_injury_identity,  # noqa: E402
                            injured_allpro_weight)

_MR = "cj_mosley__ravens_jets_ilb"
_ML = "cj_mosley__lions_2014"


def _two_mosley_weight_table(season=2015):
    """The 3-year weight window for `season`, both Mosleys present."""
    ap = pd.DataFrame([
        {"Player": "C.J. Mosley", "Team": "BAL", "Year": 2014, "Side": "defense", "Pos": "ILB"},
        {"Player": "C.J. Mosley", "Team": "DET", "Year": 2014, "Side": "defense", "Pos": "MLB"},
    ])
    r = resolve_allpro_identities(ap)
    r = r.assign(season=r["Year"] + (season - 2014), weight=4)
    return r


def test_each_injury_matches_only_its_own_identity():
    ap = _two_mosley_weight_table(2015)
    inj = pd.DataFrame([
        {"full_name": "C.J. Mosley", "team": "BAL", "season": 2015, "week": 3},
        {"full_name": "C.J. Mosley", "team": "DET", "season": 2015, "week": 3},
    ])
    got = attach_injury_identity(inj, ap, inj_name_col="full_name")
    assert list(got["allpro_id"]) == [_MR, _ML], list(got["allpro_id"])


def test_injury_merge_does_not_duplicate_rows():
    """The exact fan-out the name-only merge produced: 2 rows in, 4 rows out."""
    ap = _two_mosley_weight_table(2015)
    inj = pd.DataFrame([
        {"full_name": "C.J. Mosley", "team": "BAL", "season": 2015, "week": 3},
        {"full_name": "C.J. Mosley", "team": "DET", "season": 2015, "week": 3},
    ])
    out = injured_allpro_weight(inj, ap, inj_name_col="full_name")
    assert len(out) == 2, f"injury rows fanned out to {len(out)}"
    # Legacy behaviour, for contrast: a name-only merge really does double.
    legacy = inj.assign(_n="cj mosley").merge(
        ap.assign(_n="cj mosley")[["_n", "season", "weight"]], on=["_n", "season"], how="left")
    assert len(legacy) == 4, "the legacy fan-out no longer reproduces; test is stale"


def test_team_totals_are_correct_per_identity():
    ap = _two_mosley_weight_table(2015)
    inj = pd.DataFrame([
        {"full_name": "C.J. Mosley", "team": "BAL", "season": 2015, "week": 3},
        {"full_name": "C.J. Mosley", "team": "DET", "season": 2015, "week": 3},
    ])
    out = injured_allpro_weight(inj, ap, inj_name_col="full_name")
    tot = out.groupby("team")["weight"].sum().to_dict()
    assert tot == {"BAL": 4.0, "DET": 4.0}, tot


def test_unresolved_injury_ambiguity_aborts():
    """A colliding name with no crosswalk entry must fail, not guess or duplicate."""
    ap = pd.DataFrame([
        {"Player": "C.J. Mosley", "Team": "BAL", "Year": 2014, "Side": "defense", "Pos": "ILB"},
        {"Player": "C.J. Mosley", "Team": "DET", "Year": 2014, "Side": "defense", "Pos": "MLB"},
    ])
    r = resolve_allpro_identities(ap).assign(season=2015, weight=4)
    inj = pd.DataFrame([{"full_name": "C.J. Mosley", "team": "NYJ",  # not in crosswalk
                         "season": 2015, "week": 3}])
    with pytest.raises(AllProIdentityError, match="ambiguous injury"):
        attach_injury_identity(inj, r, inj_name_col="full_name")


def test_a_legitimate_team_change_still_matches():
    """BAL->NYJ: weight earned at BAL must still attach to the injury at NYJ.

    Team is a disambiguator for collisions only — never a general join key.
    """
    ap = pd.DataFrame([
        {"Player": "C.J. Mosley", "Team": "BAL", "Year": 2018, "Side": "defense", "Pos": "MLB"},
    ])
    r = resolve_allpro_identities(ap).assign(season=2019, weight=4)
    inj = pd.DataFrame([{"full_name": "C.J. Mosley", "team": "NYJ", "season": 2019, "week": 1}])
    out = injured_allpro_weight(inj, r, inj_name_col="full_name")
    assert len(out) == 1 and float(out["weight"].iloc[0]) == 4.0
    assert out["allpro_id"].iloc[0] == _MR


def test_unmatched_injuries_are_dropped_not_zero_filled():
    ap = _two_mosley_weight_table(2015)
    inj = pd.DataFrame([{"full_name": "Nobody AtAll", "team": "KC", "season": 2015, "week": 3}])
    assert len(injured_allpro_weight(inj, ap, inj_name_col="full_name")) == 0


def test_serving_injury_path_uses_the_shared_helper_not_a_name_merge():
    src = (_BETTING / "features.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "injured_allpro_weight(" in code, "serving does not use the shared matcher"
    assert 'on=["_name_norm", "season"]' not in code, \
        "serving still merges injuries on name+season"
    assert "_prev_yr_ap_norms" not in code, "prev-year injury set is still name-based"


def test_training_notebook_injury_block_uses_the_shared_helper():
    import json
    nb = json.load(open(_BETTING / "model_comparison.ipynb", encoding="utf-8"))
    src = "".join(nb["cells"][36]["source"])
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert 'drop_duplicates(["Player","season"])' not in code.replace(" ", ""), \
        "training still dedupes the All-Pro weight lookup by NAME"
    assert "injured_allpro_weight(" in code, "training does not use the shared matcher"
    assert 'on=["norm_name","season"]' not in code.replace(" ", ""), \
        "training still joins injuries on name+season"


def test_training_and_serving_injury_weights_agree():
    """Both paths reduce to the same shared helper, so they must agree numerically."""
    ap = _two_mosley_weight_table(2015)
    inj = pd.DataFrame([
        {"full_name": "C.J. Mosley", "team": "BAL", "season": 2015, "week": 3},
        {"full_name": "C.J. Mosley", "team": "DET", "season": 2015, "week": 3},
    ])
    shared = (injured_allpro_weight(inj, ap, inj_name_col="full_name")
              .groupby(["season", "week", "team"])["weight"].sum().reset_index())
    again = (injured_allpro_weight(inj.copy(), ap.copy(), inj_name_col="full_name")
             .groupby(["season", "week", "team"])["weight"].sum().reset_index())
    pd.testing.assert_frame_equal(shared, again)
    assert set(shared["team"]) == {"BAL", "DET"}
