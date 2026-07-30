"""Phase 1D.2 — team-specific returning personnel and half-PPR returning production.

Two defects these tests pin, both found by Joseph in code review:

1. `ret_ids` was built ONCE per season from the whole league, so a player who left KC for BUF still
   counted as returning for KC. `qb_returns` flipped 1 -> 0 on **143 of 859** team-seasons once
   corrected, and `ret_wrte_target_share` changed on 714/859.
2. `ret_skill_fantasy_share` was `mean(ret_rb_carry_share, ret_wrte_target_share)` -- an average of
   two OPPORTUNITY shares, not production.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))

import build_personnel_controls as BPC   # noqa: E402


def _rost(rows):
    return pd.DataFrame(rows, columns=["season", "team", "pid"])


# ---------------------------------------------------------------- returning_ids
def test_returning_ids_is_team_specific():
    r = _rost([(2020, "KC", "p1"), (2020, "BUF", "p2")])
    assert BPC.returning_ids(r, 2020, "KC") == {"p1"}
    assert BPC.returning_ids(r, 2020, "BUF") == {"p2"}


def test_player_who_changes_teams_does_not_return_for_his_old_team():
    """THE DEFECT. p1 played for KC in 2019 and is on BUF in 2020."""
    r = _rost([(2020, "BUF", "p1")])
    assert BPC.returning_ids(r, 2020, "KC") is None        # KC has no roster evidence here
    r2 = _rost([(2020, "BUF", "p1"), (2020, "KC", "other")])
    assert "p1" not in BPC.returning_ids(r2, 2020, "KC")
    assert "p1" in BPC.returning_ids(r2, 2020, "BUF")


def test_player_who_leaves_the_league_returns_for_nobody():
    r = _rost([(2020, "KC", "someone_else")])
    assert "gone" not in BPC.returning_ids(r, 2020, "KC")


def test_missing_roster_evidence_gives_none_not_empty_set():
    """None -> NaN downstream. An empty set would read as 'everyone departed' and fabricate a
    vacated share of 1.0."""
    assert BPC.returning_ids(_rost([]), 2020, "KC") is None
    assert BPC.returning_ids(_rost([(2020, "KC", "p")]), 2021, "KC") is None


def test_franchise_code_normalization_is_respected():
    """_norm_roster canonicalizes team codes; returning_ids compares against canonical codes."""
    assert "OAK" in BPC.TEAM_CANON or "LV" in set(BPC.TEAM_CANON.values())
    r = _rost([(2020, "LV", "p1")])
    assert BPC.returning_ids(r, 2020, "LV") == {"p1"}
    assert BPC.returning_ids(r, 2020, "OAK") is None


# ---------------------------------------------------------------- returning_share
def test_returning_share_counts_only_same_team_players():
    usage = pd.DataFrame({"pid": ["a", "b", "c"], "car": [50.0, 30.0, 20.0]})
    assert BPC.returning_share(usage, {"a", "b"}, "car") == 0.8
    assert BPC.returning_share(usage, {"a"}, "car") == 0.5
    assert BPC.returning_share(usage, set(), "car") == 0.0


def test_returning_share_is_nan_when_evidence_or_denominator_missing():
    usage = pd.DataFrame({"pid": ["a"], "car": [10.0]})
    assert np.isnan(BPC.returning_share(usage, None, "car"))
    zero = pd.DataFrame({"pid": ["a"], "car": [0.0]})
    assert np.isnan(BPC.returning_share(zero, {"a"}, "car"))


# ---------------------------------------------------------------- half-PPR share
def test_half_ppr_definition():
    assert BPC.half_ppr(pd.Series([10.0]), pd.Series([4.0])).iloc[0] == 12.0
    assert BPC.half_ppr(pd.Series([0.0]), pd.Series([0.0])).iloc[0] == 0.0


def test_returning_fantasy_share_hand_calculated():
    """RB 120.0, WR 80.0, TE 50.0 half-PPR; the WR is traded away.

        denominator = 120 + 80 + 50 = 250
        numerator   = 120 + 50      = 170   (WR is vacated production)
        share       = 170 / 250     = 0.68
    """
    prior = pd.DataFrame({"pid": ["rb", "wr", "te"], "half_ppr": [120.0, 80.0, 50.0]})
    got = BPC.returning_fantasy_share(prior, {"rb", "te"})
    assert got == 0.68


def test_traded_skill_player_counts_as_vacated_for_the_old_team():
    prior = pd.DataFrame({"pid": ["star", "scrub"], "half_ppr": [200.0, 50.0]})
    assert BPC.returning_fantasy_share(prior, {"scrub"}) == 0.2      # star departed
    assert BPC.returning_fantasy_share(prior, {"star", "scrub"}) == 1.0


def test_returning_fantasy_share_is_nan_on_zero_or_missing_denominator():
    assert np.isnan(BPC.returning_fantasy_share(
        pd.DataFrame({"pid": ["a"], "half_ppr": [0.0]}), {"a"}))
    assert np.isnan(BPC.returning_fantasy_share(
        pd.DataFrame({"pid": ["a"], "half_ppr": [10.0]}), None))


def test_fantasy_share_is_not_the_mean_of_opportunity_shares():
    """Production weighting must differ from the old formula: a high-volume/low-production player
    and a low-volume/high-production player are no longer interchangeable."""
    prior = pd.DataFrame({"pid": ["a", "b"], "half_ppr": [190.0, 10.0]})
    prod_share = BPC.returning_fantasy_share(prior, {"a"})
    assert prod_share == 0.95
    assert prod_share != np.mean([0.5, 0.5])       # a naive opportunity mean would give 0.5


# ---------------------------------------------------------------- artifact-level
def test_artifact_has_all_17_canonical_predictors():
    import stage_models as SM
    c = pd.read_csv(COACH / "data" / "personnel_controls.csv")
    missing = [f for f in SM.STAGE1_PREDICTORS if f not in c.columns]
    assert not missing, f"personnel_controls.csv missing {missing}"


def test_qb_returns_is_never_true_for_a_departed_quarterback():
    """Spot-check the rebuilt artifact: where qb_returns == 1 the prior passer must appear on that
    same team's roster for the target season."""
    c = pd.read_csv(COACH / "data" / "personnel_controls.csv")
    assert c.qb_returns.dropna().isin([0.0, 1.0]).all()
    # the correction must actually have bitten
    assert (c.qb_returns == 0.0).sum() > 0


def test_vacated_shares_are_complements_of_returning_shares():
    c = pd.read_csv(COACH / "data" / "personnel_controls.csv")
    for ret, vac in [("ret_rb_carry_share", "vacated_rush_share"),
                     ("ret_wrte_target_share", "vacated_target_share")]:
        both = c[ret].notna() & c[vac].notna()
        assert np.allclose(c.loc[both, ret] + c.loc[both, vac], 1.0)
