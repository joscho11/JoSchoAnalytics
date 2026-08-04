"""DraftKings NFL Classic lineup optimizer — the single production implementation.

The ILP used to be copy-pasted into BOTH `optimizer.ipynb` and `dfs_pipeline.ipynb`
(the same duplication that produced the matching defect fixed in `dfs_matching.py`).
It now lives here; both notebooks import it. Matching stays in `dfs_matching.py` —
this module never re-implements it.

Solver: PuLP's bundled CBC (`pulp.PULP_CBC_CMD`). There is no scipy / linprog
fallback: a missing CBC binary raises, it does not silently degrade to a different
solver whose behaviour on a binary program is not the same problem.

DK Classic roster (9 slots, $50,000 cap):
    QB 1 | RB 2 | WR 3 | TE 1 | FLEX (RB/WR/TE) 1 | DST 1
FLEX is implicit: 9 total with 1 QB + 1 DST + the RB/WR/TE minimums (2+3+1 = 6)
leaves exactly one extra RB/WR/TE, chosen by the solver.

Run the module directly for a solver report:
    python fantasy/dfs/lineup_optimizer.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pulp

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dfs_matching import assert_objective_finite  # noqa: E402

BUDGET = 50_000
ROSTER_SIZE = 9
MAX_PER_TEAM = 8
POSITION_MIN = {"RB": 2, "WR": 3, "TE": 1}     # FLEX-eligible minimums
POSITION_EXACT = {"QB": 1, "DST": 1}
FLEX_POOL = ("RB", "WR", "TE")
FLEX_TOTAL = ROSTER_SIZE - sum(POSITION_EXACT.values())   # 7 RB/WR/TE bodies


# --------------------------------------------------------------------- solver
def cbc_solver(msg: int = 0) -> pulp.PULP_CBC_CMD:
    """The one solver constructor used everywhere (tests included)."""
    return pulp.PULP_CBC_CMD(msg=msg)


def solver_info() -> dict:
    """Measured facts about the solver actually installed — no assumptions.

    NOTE: in PuLP 3.x `LpSolver.available()` returns the solver PATH (a truthy str),
    not the literal ``True``; callers must test truthiness, and this dict records
    both the raw return and its bool.
    """
    s = cbc_solver()
    raw = s.available()
    info = {
        "pulp_version": pulp.__version__,
        "solver_class": type(s).__name__,
        "solver_name": s.name,
        "path": str(getattr(s, "path", "")),
        "available_raw": raw,
        "available": bool(raw),
        "cbc_version": None,
    }
    if info["available"] and info["path"]:
        try:
            out = subprocess.run([info["path"], "-quit"], capture_output=True,
                                 text=True, timeout=60).stdout
            for line in out.splitlines():
                if line.strip().startswith("Version:"):
                    info["cbc_version"] = line.split(":", 1)[1].strip()
                    break
        except (OSError, subprocess.SubprocessError):    # pragma: no cover
            pass
    return info


def assert_cbc_available() -> dict:
    """Raise unless the bundled CBC binary is really runnable. Returns solver_info()."""
    info = solver_info()
    if not info["available"]:
        raise RuntimeError(
            "PuLP's CBC solver is not available. Install pulp (>=2.7,<4.0) with its "
            f"bundled binary; solver_info()={info}"
        )
    return info


# ----------------------------------------------------------------- slotting
def assign_slots(lineup_df: pd.DataFrame) -> pd.DataFrame:
    """Label each row with its DK roster slot (QB/RB/WR/TE/FLEX/DST)."""
    df = lineup_df.copy().reset_index(drop=True)
    slots = [""] * len(df)
    seen = {p: 0 for p in FLEX_POOL}
    for i, row in df.iterrows():
        pos = row["position"]
        if pos in POSITION_EXACT:
            slots[i] = pos
        elif pos in seen:
            seen[pos] += 1
            slots[i] = pos if seen[pos] <= POSITION_MIN[pos] else "FLEX"
    df.insert(0, "Slot", slots)
    return df


# back-compat alias for the notebooks' historical private name
_assign_slots = assign_slots


# --------------------------------------------------------------------- ILP
def optimize_lineup(
    players: pd.DataFrame,
    budget: int = BUDGET,
    locked: list[str] | None = None,
    excluded: list[str] | None = None,
    objective_col: str = "proj_pts",
    strict_names: bool = True,
    solver=None,
) -> pd.DataFrame | None:
    """Maximise ``objective_col`` over a DK Classic roster. Returns the 9-row lineup
    (with a Slot column) or None when CBC proves the problem infeasible.

    ``strict_names``: a locked/excluded name absent from the pool raises instead of
    being silently dropped — a typo in LOCKED used to change nothing at all.
    """
    df = players.reset_index(drop=True)
    # A NaN objective coefficient used to come straight from an unmatched row, because
    # float(x or 0) does not catch NaN. Fail loudly instead of solving on garbage.
    assert_objective_finite(df, objective_col)
    locked = list(dict.fromkeys(locked or []))
    excluded = list(dict.fromkeys(excluded or []))
    if strict_names:
        pool_names = set(df["name"])
        unknown = [n for n in (locked + excluded) if n not in pool_names]
        if unknown:
            raise ValueError(f"locked/excluded name(s) not in the player pool: {unknown}")
    both = set(locked) & set(excluded)
    if both:
        raise ValueError(f"name(s) both locked and excluded: {sorted(both)}")

    n = len(df)
    prob = pulp.LpProblem("DFS_Classic", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{i}", cat="Binary") for i in range(n)]

    def pidx(pos):
        return [i for i in range(n) if df.iloc[i]["position"] == pos]

    # Objective
    prob += pulp.lpSum(df.iloc[i][objective_col] * x[i] for i in range(n))

    # Constraints
    prob += pulp.lpSum(df.iloc[i]["salary"] * x[i] for i in range(n)) <= budget
    prob += pulp.lpSum(x[i] for i in range(n)) == ROSTER_SIZE
    for pos, k in POSITION_EXACT.items():
        prob += pulp.lpSum(x[i] for i in pidx(pos)) == k
    for pos, k in POSITION_MIN.items():
        prob += pulp.lpSum(x[i] for i in pidx(pos)) >= k

    for team in df["team"].dropna().unique():
        tidx = [i for i in range(n) if df.iloc[i]["team"] == team]
        if len(tidx) > MAX_PER_TEAM:
            prob += pulp.lpSum(x[i] for i in tidx) <= MAX_PER_TEAM

    for name in locked:
        for i in df[df["name"] == name].index:
            prob += x[i] == 1
    for name in excluded:
        for i in df[df["name"] == name].index:
            prob += x[i] == 0

    status = prob.solve(solver if solver is not None else cbc_solver())
    if pulp.LpStatus[status] != "Optimal":
        return None

    selected = [i for i in range(n) if pulp.value(x[i]) > 0.5]
    order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "DST": 5}
    lineup = df.iloc[selected].copy()
    lineup["_sort"] = lineup["position"].map(order).fillna(4)
    lineup = lineup.sort_values("_sort").drop(columns=["_sort"])
    lineup = assign_slots(lineup)
    lineup.attrs["lp_status"] = pulp.LpStatus[status]
    lineup.attrs["objective"] = float(pulp.value(prob.objective))
    lineup.attrs["objective_col"] = objective_col
    return lineup


def lineup_facts(lineup: pd.DataFrame, objective_col: str = "proj_pts") -> dict:
    """Every DK Classic rule, MEASURED off a returned lineup. Nothing is printed;
    the caller asserts on the values."""
    pos = lineup["position"].value_counts().to_dict()
    flex_bodies = sum(pos.get(p, 0) for p in FLEX_POOL)
    per_team = lineup["team"].value_counts().to_dict()
    return {
        "lp_status": lineup.attrs.get("lp_status"),
        "n_players": int(len(lineup)),
        "salary": int(lineup["salary"].sum()),
        "objective": float(lineup[objective_col].sum()),
        "pos_counts": {p: int(pos.get(p, 0)) for p in ("QB", "RB", "WR", "TE", "DST")},
        "flex_bodies": int(flex_bodies),
        "max_from_one_team": int(max(per_team.values())) if per_team else 0,
        "slots": lineup["Slot"].tolist() if "Slot" in lineup.columns else [],
        "names": lineup["name"].tolist(),
    }


if __name__ == "__main__":                       # pragma: no cover
    for k, v in assert_cbc_available().items():
        print(f"{k:16s}: {v}")
