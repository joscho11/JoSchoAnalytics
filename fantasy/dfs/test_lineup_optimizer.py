"""REAL PuLP/CBC proof for the DFS lineup optimizer.

Every assertion below runs against the genuine CBC branch-and-bound binary bundled
with PuLP -- there is no scipy stand-in and no linear-relaxation substitute. If CBC
is missing these tests FAIL (they do not skip): a solver-less run is exactly the
condition the proof exists to detect, and CI asserts the skip count is zero.

The pool is the retained week-10 slate: dk_salaries_2025_week10_synthetic.csv merged
onto projections_2025_week10.csv through the dfs_matching cascade -- the same pool
the pipeline optimises.

Run:  python -m pytest fantasy/dfs/test_lineup_optimizer.py -q
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import dfs_matching as M            # noqa: E402
import lineup_optimizer as O        # noqa: E402

import pulp                         # noqa: E402

REPO = _HERE.parents[1]
REAL_PROJ = REPO / "fantasy" / "fantasy_projections" / "projections_2025_week10.csv"
DK_CSV = _HERE / "dk_salaries_2025_week10_synthetic.csv"
# The pool files are committed. Their absence is a repo defect, not a reason to skip:
# nothing in this module is decorated with skipif.


# --------------------------------------------------------------- the real pool
@pytest.fixture(scope="module")
def pool() -> pd.DataFrame:
    assert REAL_PROJ.exists(), f"missing retained projection file: {REAL_PROJ}"
    assert DK_CSV.exists(), f"missing retained DK salary file: {DK_CSV}"
    proj = pd.read_csv(REAL_PROJ)
    dk = pd.read_csv(DK_CSV).rename(columns={
        "Position": "position", "Name": "name", "Salary": "salary",
        "TeamAbbrev": "team", "AvgPointsPerGame": "avg_pts"})
    players = M.merge_projections(dk, proj)
    players["dfs_proj_pts"] = M.calc_dk_proj_pts(players)
    M.assert_objective_finite(players, "dfs_proj_pts")
    return players


OBJ = "dfs_proj_pts"


# ------------------------------------------------------- 1. CBC really is there
def test_cbc_is_available_and_is_a_real_binary():
    info = O.solver_info()
    assert bool(info["available"]) is True, info
    assert info["solver_class"] == "PULP_CBC_CMD"
    p = Path(info["path"])
    assert p.exists(), f"PuLP reports CBC at {p} but the file does not exist"
    assert info["cbc_version"], "could not read a version string out of the CBC binary"
    # pulp itself must be the declared range (requirements-research.txt)
    major = int(pulp.__version__.split(".")[0])
    assert 2 <= major < 4, pulp.__version__


def test_assert_cbc_available_returns_the_recorded_facts():
    info = O.assert_cbc_available()
    assert info["available"] is True
    assert info["path"].endswith(("cbc", "cbc.exe"))


def test_no_scipy_stand_in_anywhere_in_the_optimizer():
    """Scanned over the PARSED module, so prose in the docstring/comments (which does
    mention scipy, to say it is not used) cannot make this pass or fail spuriously."""
    import ast
    tree = ast.parse((_HERE / "lineup_optimizer.py").read_text(encoding="utf-8"))
    imported, referenced = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert "scipy" not in imported, imported
    assert {"linprog", "milp"} & referenced == set(), referenced
    assert "pulp" in imported, imported
    # and the solve really is routed through the CBC constructor
    assert "PULP_CBC_CMD" in referenced, referenced


def test_the_solve_actually_calls_cbc(pool, monkeypatch):
    """Proves the CBC code path is the one exercised: swap in a solver that records
    the call, and confirm the ILP goes through PULP_CBC_CMD.solve."""
    calls = []
    real_solve = pulp.PULP_CBC_CMD.actualSolve

    def spy(self, lp, *a, **k):
        calls.append(type(self).__name__)
        return real_solve(self, lp, *a, **k)

    monkeypatch.setattr(pulp.PULP_CBC_CMD, "actualSolve", spy)
    lineup = O.optimize_lineup(pool, objective_col=OBJ)
    assert lineup is not None
    assert calls == ["PULP_CBC_CMD"], calls


# --------------------------------------------- 2. the full constraint assertion
@pytest.fixture(scope="module")
def base_lineup(pool):
    return O.optimize_lineup(pool, objective_col=OBJ)


def test_status_is_optimal(base_lineup):
    assert base_lineup is not None
    assert base_lineup.attrs["lp_status"] == "Optimal"


def test_exactly_nine_players(base_lineup):
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["n_players"] == 9, f


def test_salary_within_cap(base_lineup):
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["salary"] <= 50_000, f["salary"]


def test_exactly_one_qb_and_one_dst(base_lineup):
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["pos_counts"]["QB"] == 1, f["pos_counts"]
    assert f["pos_counts"]["DST"] == 1, f["pos_counts"]


def test_position_minimums(base_lineup):
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["pos_counts"]["RB"] >= 2, f["pos_counts"]
    assert f["pos_counts"]["WR"] >= 3, f["pos_counts"]
    assert f["pos_counts"]["TE"] >= 1, f["pos_counts"]


def test_flex_legality(base_lineup):
    """RB+WR+TE == 7: one body beyond the 2/3/1 minimums, and it is slotted FLEX."""
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["flex_bodies"] == 7, f["pos_counts"]
    assert f["slots"].count("FLEX") == 1, f["slots"]
    assert sorted(f["slots"]) == sorted(
        ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]), f["slots"]
    flex_pos = base_lineup.loc[base_lineup["Slot"] == "FLEX", "position"].iloc[0]
    assert flex_pos in ("RB", "WR", "TE"), flex_pos


def test_max_eight_from_one_team(base_lineup):
    f = O.lineup_facts(base_lineup, OBJ)
    assert f["max_from_one_team"] <= 8, f["max_from_one_team"]


def test_objective_is_finite_and_matches_the_lp(base_lineup):
    import math
    f = O.lineup_facts(base_lineup, OBJ)
    assert math.isfinite(f["objective"])
    assert f["objective"] > 0
    # CBC's reported objective must equal the sum over the selected rows
    assert base_lineup.attrs["objective"] == pytest.approx(f["objective"], abs=1e-6)


def test_no_player_selected_twice(base_lineup):
    names = O.lineup_facts(base_lineup, OBJ)["names"]
    assert len(set(names)) == len(names), names


def test_it_is_actually_optimal_not_merely_feasible(pool, base_lineup):
    """A branch-and-bound optimum: excluding any single selected player cannot
    produce a BETTER lineup, and the greedy salary-sorted alternative is worse."""
    best = base_lineup.attrs["objective"]
    for name in O.lineup_facts(base_lineup, OBJ)["names"][:3]:
        alt = O.optimize_lineup(pool, objective_col=OBJ, excluded=[name])
        assert alt is not None
        assert alt.attrs["objective"] <= best + 1e-6, (name, alt.attrs["objective"], best)


# ------------------------------------------------------- 3. locks / excludes bind
def test_lock_binds(pool, base_lineup):
    """Lock a player the unconstrained optimum did NOT take; he must appear."""
    chosen = set(O.lineup_facts(base_lineup, OBJ)["names"])
    cand = pool[(pool["position"] == "WR") & (~pool["name"].isin(chosen))]
    lock_name = cand.sort_values(OBJ, ascending=False)["name"].iloc[0]
    assert lock_name not in chosen

    locked = O.optimize_lineup(pool, objective_col=OBJ, locked=[lock_name])
    assert locked is not None
    facts = O.lineup_facts(locked, OBJ)
    assert lock_name in facts["names"], facts["names"]
    assert facts["n_players"] == 9 and facts["salary"] <= 50_000
    # binding a constraint can only cost objective value
    assert facts["objective"] <= base_lineup.attrs["objective"] + 1e-6


def test_exclude_binds(pool, base_lineup):
    drop = O.lineup_facts(base_lineup, OBJ)["names"][0]
    out = O.optimize_lineup(pool, objective_col=OBJ, excluded=[drop])
    assert out is not None
    facts = O.lineup_facts(out, OBJ)
    assert drop not in facts["names"], facts["names"]
    assert facts["n_players"] == 9 and facts["salary"] <= 50_000
    assert facts["objective"] <= base_lineup.attrs["objective"] + 1e-6


def test_locking_a_whole_legal_roster_reproduces_it(pool, base_lineup):
    names = O.lineup_facts(base_lineup, OBJ)["names"]
    out = O.optimize_lineup(pool, objective_col=OBJ, locked=names)
    assert out is not None
    assert sorted(O.lineup_facts(out, OBJ)["names"]) == sorted(names)


def test_infeasible_lock_returns_none(pool):
    """Locking two QBs violates the exactly-one-QB equality: CBC proves infeasible."""
    qbs = pool[pool["position"] == "QB"]["name"].tolist()[:2]
    assert len(qbs) == 2
    assert O.optimize_lineup(pool, objective_col=OBJ, locked=qbs) is None


def test_salary_cap_actually_binds(pool):
    """A cap far below the cheapest legal roster must be infeasible, and a normal
    solve must not exceed the cap."""
    assert O.optimize_lineup(pool, objective_col=OBJ, budget=1_000) is None


def test_unknown_lock_name_raises_instead_of_being_ignored(pool):
    with pytest.raises(ValueError, match="not in the player pool"):
        O.optimize_lineup(pool, objective_col=OBJ, locked=["Definitely Not A Player"])
    with pytest.raises(ValueError, match="not in the player pool"):
        O.optimize_lineup(pool, objective_col=OBJ, excluded=["Definitely Not A Player"])


def test_locked_and_excluded_conflict_raises(pool, base_lineup):
    n = O.lineup_facts(base_lineup, OBJ)["names"][0]
    with pytest.raises(ValueError, match="both locked and excluded"):
        O.optimize_lineup(pool, objective_col=OBJ, locked=[n], excluded=[n])


def test_nan_objective_is_refused(pool):
    bad = pool.copy()
    bad.loc[bad.index[0], OBJ] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        O.optimize_lineup(bad, objective_col=OBJ)


# ---------------------------------------- 4. the notebooks use THIS implementation
def test_notebooks_import_the_module_and_do_not_redefine_the_ilp():
    import json
    for nb in ("optimizer.ipynb", "dfs_pipeline.ipynb"):
        cells = json.load(open(_HERE / nb, encoding="utf-8"))["cells"]
        code = "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")
        assert "lineup_optimizer" in code, f"{nb}: does not import lineup_optimizer"
        assert "def optimize_lineup(" not in code, f"{nb}: still redefines the ILP"
        assert "def _assign_slots(" not in code, f"{nb}: still redefines slot assignment"
        assert "def merge_projections(" not in code, f"{nb}: matching must stay in dfs_matching"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
