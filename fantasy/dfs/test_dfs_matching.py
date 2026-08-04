"""Regression tests for the constrained DK <-> projection matching cascade.

Every cross-position case below was REPRODUCED against the shipped code before the fix:
the legacy `difflib.get_close_matches(cutoff=0.72)` merge matched an absent Josh Allen
to Josh Palmer, Aaron Rodgers to Aaron Jones, Mac Jones to Zay Jones and Caleb Williams
to Kyle Williams, and labelled all four `match == "model"`. These tests are red against
that implementation and green against `dfs_matching`.

Run:  python -m pytest fantasy/dfs/test_dfs_matching.py -q
"""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import dfs_matching as M  # noqa: E402

REPO = _HERE.parents[1]
REAL_PROJ = REPO / "fantasy" / "fantasy_projections" / "projections_2025_week10.csv"


def _proj(rows):
    """rows: (player_id, name, position, team, projected_pts)"""
    return pd.DataFrame(
        [dict(player_id=r[0], player_display_name=r[1], position=r[2], team=r[3],
              projected_pts=r[4]) for r in rows]
    )


def _dk(rows):
    """rows: (name, position, team, salary, avg_pts) [+ optional player_id]"""
    out = []
    for r in rows:
        d = dict(name=r[0], position=r[1], team=r[2], salary=r[3], avg_pts=r[4])
        if len(r) > 5:
            d["player_id"] = r[5]
        out.append(d)
    return pd.DataFrame(out)


def _status(dk_df, proj_df):
    return M.merge_projections(dk_df, proj_df)


# ── 1. the three named cross-position substitutions must NOT match ────────────
CROSS_POSITION_CASES = [
    # (DK row)                            (only projection available)
    (("Josh Allen", "QB", "BUF"), ("Josh Palmer", "WR", "BUF")),
    (("Aaron Rodgers", "QB", "PIT"), ("Aaron Jones", "RB", "MIN")),
    (("Mac Jones", "QB", "SF"), ("Zay Jones", "WR", "ARI")),
    (("Caleb Williams", "QB", "CHI"), ("Kyle Williams", "WR", "NE")),
]


@pytest.mark.parametrize("dk_row,proj_row", CROSS_POSITION_CASES)
def test_cross_position_substitution_never_matches(dk_row, proj_row):
    proj = _proj([("p1", proj_row[0], proj_row[1], proj_row[2], 19.9)])
    dk = _dk([(dk_row[0], dk_row[1], dk_row[2], 8000, 3.5)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] in ("unmatched", "ambiguous"), (
        f"{dk_row[0]} ({dk_row[1]}) matched {proj_row[0]} ({proj_row[1]})"
    )
    assert not out.loc[0, "used_model"]
    assert out.loc[0, "match"] != "model", "no row may carry the old generic 'model' label"
    assert out.loc[0, "proj_pts"] == 3.5, "an unmatched row must fall back to the DK average"


def test_cross_position_would_have_matched_under_legacy_cutoff():
    """Guard the premise: these pairs really are >= 0.72 similar, so the constraint --
    not luck -- is what rejects them."""
    import difflib
    for (dk_row, proj_row) in CROSS_POSITION_CASES:
        s = difflib.SequenceMatcher(None, M.norm_name(dk_row[0]), M.norm_name(proj_row[0])).ratio()
        assert s >= 0.72, f"{dk_row[0]} vs {proj_row[0]} = {s:.3f}"


# ── 2. normalisation: suffixes and punctuation ────────────────────────────────
@pytest.mark.parametrize("dk_name,proj_name", [
    ("Marvin Harrison Jr.", "Marvin Harrison"),
    ("Marvin Harrison", "Marvin Harrison Jr."),
    ("Kenneth Walker III", "Kenneth Walker"),
    ("Patrick Mahomes", "Patrick Mahomes II"),
    ("T.J. Hockenson", "TJ Hockenson"),
    ("TJ Hockenson", "T.J. Hockenson"),
    ("De'Von Achane", "DeVon Achane"),
    ("Amon-Ra St. Brown", "Amon Ra St Brown"),
    ("Deebo Samuel Sr.", "Deebo Samuel"),
])
def test_suffix_and_punctuation_still_match_exactly(dk_name, proj_name):
    pos = "TE" if "Hockenson" in dk_name else "WR" if "Harrison" in dk_name or "Brown" in dk_name else \
          "QB" if "Mahomes" in dk_name else "RB" if "Walker" in dk_name or "Achane" in dk_name else "WR"
    proj = _proj([("p1", proj_name, pos, "SEA", 15.0)])
    dk = _dk([(dk_name, pos, "SEA", 7000, 9.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "exact", out.loc[0, "match_note"]
    assert out.loc[0, "proj_pts"] == 15.0


def test_norm_name_is_stable():
    assert M.norm_name("De'Von Achane Jr.") == "devon achane"
    assert M.norm_name("Patrick Mahomes II") == "patrick mahomes"
    assert M.norm_name("T.J. Hockenson") == M.norm_name("TJ Hockenson") == "tj hockenson"
    assert M.norm_name(None) == "" and M.norm_name(float("nan")) == ""


# ── 3. team normalisation and traded players ──────────────────────────────────
def test_team_abbreviation_aliases_are_the_same_team():
    proj = _proj([("p1", "Puka Nacua", "WR", "LA", 17.0)])
    dk = _dk([("Puka Nacua", "WR", "LAR", 8200, 14.0)])   # DK says LAR, nflverse says LA
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "exact", "LAR/LA must normalise to one team"
    for a, b in [("JAC", "JAX"), ("WSH", "WAS"), ("OAK", "LV"), ("SD", "LAC"), ("LAR", "LA")]:
        assert M.norm_team(a) == M.norm_team(b) == M.norm_team(b.upper())


def test_traded_player_matches_but_keeps_an_explicit_status():
    """Projections still list the old team; DK has the new one. Same name + position,
    unique league-wide -> use the projection, but say so."""
    proj = _proj([("p1", "Davante Adams", "WR", "LV", 16.5),
                  ("p2", "Some Other Guy", "WR", "NYJ", 8.0)])
    dk = _dk([("Davante Adams", "WR", "NYJ", 7800, 12.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "team_mismatch"
    assert out.loc[0, "match"] != "exact" and out.loc[0, "match"] != "model"
    assert out.loc[0, "match_name"] == "Davante Adams"
    assert out.loc[0, "proj_pts"] == 16.5
    assert "LV" in out.loc[0, "match_note"] and "NYJ" in out.loc[0, "match_note"]


# ── 4. duplicate names on different teams ─────────────────────────────────────
def test_duplicate_names_are_disambiguated_by_team():
    proj = _proj([("p1", "Michael Thomas", "WR", "NO", 14.0),
                  ("p2", "Michael Thomas", "WR", "HOU", 4.0)])
    dk = _dk([("Michael Thomas", "WR", "NO", 6000, 9.0),
              ("Michael Thomas", "WR", "HOU", 3000, 2.0)])
    out = _status(dk, proj)
    assert list(out["match"]) == ["exact", "exact"]
    assert list(out["proj_pts"]) == [14.0, 4.0]


def test_duplicate_names_with_no_team_agreement_are_ambiguous():
    proj = _proj([("p1", "Michael Thomas", "WR", "NO", 14.0),
                  ("p2", "Michael Thomas", "WR", "HOU", 4.0)])
    dk = _dk([("Michael Thomas", "WR", "SEA", 6000, 9.0)])   # third team: cannot resolve
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "ambiguous"
    assert not out.loc[0, "used_model"]
    assert out.loc[0, "proj_pts"] == 9.0, "ambiguous rows fall back to the DK average"


def test_same_team_same_position_near_collision_is_ambiguous_not_guessed():
    proj = _proj([("p1", "Michael Carter", "RB", "NYJ", 9.0),
                  ("p2", "Michael Carter II", "RB", "NYJ", 1.0)])
    dk = _dk([("Michel Carter", "RB", "NYJ", 5000, 6.0)])    # typo, close to BOTH
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "ambiguous", out.loc[0, "match_note"]
    assert not out.loc[0, "used_model"]


# ── 5. Out player absent from the projections ─────────────────────────────────
def test_out_player_absent_from_projections_is_unmatched_not_substituted():
    """`predict_fantasy` drops every player ruled Out, so a real DK export always
    contains names the projection file lacks. That row must fall back, explicitly."""
    proj = _proj([("p1", "Jaylen Waddle", "WR", "MIA", 13.0),
                  ("p2", "Malik Washington", "WR", "MIA", 6.0)])
    dk = _dk([("Tyreek Hill", "WR", "MIA", 8800, 17.2)])     # ruled Out -> not projected
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "unmatched"
    assert out.loc[0, "used_model"] is False or not out.loc[0, "used_model"]
    assert out.loc[0, "proj_pts"] == 17.2
    assert out.loc[0, "match_name"] == ""


# ── 6. stable id wins, and alias table ────────────────────────────────────────
def test_stable_id_takes_precedence():
    proj = _proj([("00-0031234", "Chris Godwin", "WR", "TB", 12.0)])
    dk = _dk([("C. Godwin", "WR", "TB", 6400, 10.0, "00-0031234")])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "id"
    assert out.loc[0, "proj_pts"] == 12.0


def test_reviewed_alias_table_resolves_known_spellings():
    proj = _proj([("p1", "Joshua Palmer", "WR", "BUF", 11.0)])
    dk = _dk([("Josh Palmer", "WR", "BUF", 5200, 8.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "alias"
    assert out.loc[0, "proj_pts"] == 11.0


def test_alias_table_cannot_cross_positions():
    """The alias bridge is applied UNDER the position constraint."""
    proj = _proj([("p1", "Joshua Palmer", "WR", "BUF", 11.0)])
    dk = _dk([("Josh Palmer", "QB", "BUF", 5200, 8.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] in ("unmatched", "ambiguous")
    assert not out.loc[0, "used_model"]


def test_alias_groups_are_well_formed():
    seen = {}
    for g in M.ALIAS_GROUPS:
        assert len(g) >= 2, f"an alias group needs >=2 spellings: {g}"
        for n in g:
            assert n == M.norm_name(n), f"alias entries must already be normalized: {n!r}"
            assert n not in seen, f"{n!r} is in two alias groups"
            seen[n] = True


# ── 7. fuzzy fallback is constrained and margin-gated ─────────────────────────
def test_fuzzy_requires_same_team_and_position():
    proj = _proj([("p1", "Jonathan Taylor", "RB", "IND", 18.0)])
    dk = _dk([("Jonathan Tayler", "RB", "IND", 7600, 15.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "fuzzy"
    assert out.loc[0, "match_score"] >= M.FUZZY_MIN

    dk_other_team = _dk([("Jonathan Tayler", "RB", "DAL", 7600, 15.0)])
    out2 = _status(dk_other_team, proj)
    assert out2.loc[0, "match"] == "unmatched", "fuzzy must never cross teams"


def test_low_similarity_is_unmatched():
    proj = _proj([("p1", "Bijan Robinson", "RB", "ATL", 20.0)])
    dk = _dk([("Tyler Allgeier", "RB", "ATL", 4800, 7.0)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "unmatched"


# ── 8. DST and the status vocabulary ──────────────────────────────────────────
def test_dst_uses_dk_average_and_its_own_status():
    proj = _proj([("p1", "Josh Allen", "QB", "BUF", 22.3)])
    dk = _dk([("Bills", "DST", "BUF", 3600, 8.1)])
    out = _status(dk, proj)
    assert out.loc[0, "match"] == "dst"
    assert out.loc[0, "proj_pts"] == 8.1


def test_no_status_is_the_generic_model_label():
    assert "model" not in M.ALL_STATUSES
    assert set(M.MODEL_STATUSES).isdisjoint(M.FALLBACK_STATUSES)


def test_status_counts_cover_every_row():
    proj = _proj([("p1", "Puka Nacua", "WR", "LA", 17.0)])
    dk = _dk([("Puka Nacua", "WR", "LA", 8000, 14.0),
              ("Nobody Here", "WR", "LA", 3000, 1.0),
              ("Rams", "DST", "LA", 3200, 7.0)])
    out = _status(dk, proj)
    counts = M.match_status_counts(out)
    assert sum(counts.values()) == len(out) == 3
    assert counts["exact"] == 1 and counts["unmatched"] == 1 and counts["dst"] == 1
    report = M.format_match_report(out)
    assert "unmatched" in report and "Nobody Here" in report


# ── 9. the NaN-into-the-objective bug ─────────────────────────────────────────
def test_num_catches_nan_where_or_zero_did_not():
    assert float("nan") or 0     # the old idiom: NaN is truthy, so `or 0` never fires
    assert math.isnan(float(float("nan") or 0))
    assert M.num(float("nan")) == 0.0
    assert M.num(None) == 0.0
    assert M.num("") == 0.0
    assert M.num(3.5) == 3.5


def test_nan_stats_never_reach_the_objective():
    players = pd.DataFrame([
        dict(name="Unmatched WR", position="WR", team="LA", salary=4000, avg_pts=5.0,
             proj_pts=5.0, pred_wr_receptions=float("nan"), pred_wr_rec_yards=float("nan")),
        dict(name="Unmatched QB", position="QB", team="LA", salary=5000, avg_pts=6.0,
             proj_pts=6.0, pred_qb_pass_yards=float("nan"), pred_qb_rush_yards=float("nan")),
        dict(name="Unmatched RB", position="RB", team="LA", salary=4500, avg_pts=4.0,
             proj_pts=4.0, pred_rush_yards=float("nan"), pred_rec_yards=float("nan")),
        dict(name="Unmatched TE", position="TE", team="LA", salary=3000, avg_pts=3.0,
             proj_pts=3.0, pred_te_receptions=float("nan"), pred_te_rec_yards=float("nan")),
    ])
    pts = M.calc_dk_proj_pts(players)
    assert all(math.isfinite(p) for p in pts), pts
    assert pts == [5.0, 6.0, 4.0, 3.0]
    players["dfs_proj_pts"] = pts
    M.assert_objective_finite(players)


def test_assert_objective_finite_raises_on_nan():
    bad = pd.DataFrame([dict(name="X", dfs_proj_pts=float("nan"))])
    with pytest.raises(ValueError, match="non-finite"):
        M.assert_objective_finite(bad)


def test_merge_leaves_no_nan_projection():
    proj = _proj([("p1", "Puka Nacua", "WR", "LA", 17.0)])
    dk = _dk([("Ruled Out Guy", "WR", "LA", 4000, float("nan"))])
    out = M.merge_projections(dk, proj)
    assert out.loc[0, "match"] == "unmatched"
    assert out.loc[0, "proj_pts"] == 0.0, "a NaN DK average must become 0, not NaN"
    out["dfs_proj_pts"] = M.calc_dk_proj_pts(out)
    M.assert_objective_finite(out)


# ── 10. end-to-end on the real projection file ────────────────────────────────
@pytest.mark.skipif(not REAL_PROJ.exists(), reason="week-10 projection file not present")
def test_leave_one_out_false_match_rate_is_zero():
    proj = pd.read_csv(REAL_PROJ)
    legacy = M.loo_match_rate(proj, matcher="legacy")
    cascade = M.loo_match_rate(proj, matcher="cascade")
    assert legacy["false_matches"] > 100, "premise: the legacy matcher was badly wrong"
    assert legacy["cross_position"] > 50
    assert cascade["false_matches"] == 0, cascade["examples"][:5]
    assert cascade["cross_position"] == 0


@pytest.mark.skipif(not REAL_PROJ.exists(), reason="week-10 projection file not present")
def test_real_slate_matches_every_skill_player():
    proj = pd.read_csv(REAL_PROJ)
    dk = pd.read_csv(_HERE / "dk_salaries_2025_week10_synthetic.csv").rename(columns={
        "Position": "position", "Name": "name", "Salary": "salary",
        "TeamAbbrev": "team", "AvgPointsPerGame": "avg_pts"})
    out = M.merge_projections(dk, proj)
    counts = M.match_status_counts(out)
    assert counts["ambiguous"] == 0 and counts["unmatched"] == 0, counts
    assert counts["exact"] == 568 and counts["dst"] == 28, counts
    out["dfs_proj_pts"] = M.calc_dk_proj_pts(out)
    M.assert_objective_finite(out)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
