"""Two equivalence proofs that separate CODE change from INPUT change.

The published `features_dataset.csv` was built in May 2026 from a May-2026 snapshot of
nflverse. Comparing a fresh rebuild to it therefore mixes three things: the depth fix, the
committed-but-never-rebuilt notebook changes, and a year of nflverse revisions. These two
checks hold the inputs fixed so only code is under test.

A. `depth_flags_match_original_notebook` — the four depth tables this repo now builds via
   `depth_features` are compared, on the SAME cached nflverse pull, against a verbatim
   re-implementation of the pre-fix `data_pipeline.ipynb` cells 22-28, restricted to the
   legacy seasons those cells could actually read. Any difference is a regression.

B. `features_stage_reproduces_published` — `build_staging_dataset.build_features` with
   `LEGACY_ROLLING_SEMANTICS = True` is run on the PUBLISHED `raw_dataset.csv` and
   compared to the published `features_dataset.csv`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import depth_features as DF  # noqa: E402

_REPORT_MAP = {None: 1.0, "Questionable": 0.5, "Doubtful": 0.25, "Out": 0.0, "Note": 1.0}
_PRACTICE_MAP = {"Full Participation in Practice": 1.0,
                 "Limited Participation in Practice": 0.5,
                 "Did Not Participate In Practice": 0.0, "\n": 1.0, "Note": 1.0}

_ORIG_GROUPS = [
    (DF.SKILL_POSITIONS, {"QB": "starter_qb_availability", "RB": "starter_rb_availability",
                          "WR": "starter_wr_availability", "TE": "starter_te_availability"},
     DF.TEAMMATE_FLAG_COLS, "teammate_flags"),
    (DF.DEFENSIVE_POSITIONS, {"CB": "opp_cb1_availability", "OLB": "opp_olb1_availability",
                              "ILB": "opp_ilb1_availability", "MLB": "opp_mlb1_availability",
                              "DE": "opp_de1_availability", "DT": "opp_dt1_availability",
                              "FS": "opp_fs1_availability", "SS": "opp_ss1_availability"},
     DF.DEF_FLAG_COLS, "def_flags"),
    (DF.OL_POSITIONS, {"T": "starter_tackle_availability", "G": "starter_guard_availability",
                       "C": "starter_center_availability"}, DF.OL_FLAG_COLS, "ol_flags"),
]


def _original_inj(injuries: pd.DataFrame) -> pd.DataFrame:
    inj = injuries[injuries["game_type"] == "REG"].copy()
    inj["season"] = inj["season"].astype(int)
    inj["week"] = inj["week"].astype(int)
    inj["injury_status_score"] = inj["report_status"].map(_REPORT_MAP).fillna(1.0)
    inj["practice_status_score"] = inj["practice_status"].map(_PRACTICE_MAP).fillna(1.0)
    return inj.rename(columns={"gsis_id": "player_id"})[
        ["season", "week", "player_id", "injury_status_score", "practice_status_score"]]


def _original_flags(depth, inj, positions, rename, cols):
    """data_pipeline.ipynb cells 22-28 as they stood before the adapter."""
    z = depth[(depth["game_type"] == "REG") & depth["position"].isin(positions)
              & (depth["depth_team"] == "1")].copy()
    z["season"] = z["season"].astype(int)
    z["week"] = z["week"].astype(int)
    z = z[["season", "week", "club_code", "gsis_id", "position"]].rename(
        columns={"club_code": "team", "gsis_id": "player_id"})
    z = z.sort_values(["season", "week", "team", "position", "player_id"]).drop_duplicates(
        subset=["season", "week", "team", "position"])
    h = z.merge(inj, on=["season", "week", "player_id"], how="left")
    h["injury_status_score"] = h["injury_status_score"].fillna(1.0)
    h["practice_status_score"] = h["practice_status_score"].fillna(1.0)
    h["_a"] = h["injury_status_score"] * 0.6 + h["practice_status_score"] * 0.4
    f = h.pivot_table(index=["season", "week", "team"], columns="position", values="_a",
                      aggfunc="mean", observed=True).reset_index()
    f.columns.name = None
    f = f.rename(columns=rename)
    for c in cols:
        if c not in f.columns:
            f[c] = 1.0
        f[c] = f[c].fillna(1.0)
    return f[["season", "week", "team"] + cols]


def depth_flags_match_original_notebook(data, tables, legacy_max_season: int = 2024) -> dict:
    inj = _original_inj(data["injuries"])
    out = {"max_mismatch_rate": 0.0, "per_column": {}, "joined_rows": {}}
    for positions, rename, cols, attr in _ORIG_GROUPS:
        orig = _original_flags(data["depth_charts"], inj, positions, rename, cols)
        new = getattr(tables, attr)
        m = orig.merge(new, on=["season", "week", "team"], suffixes=("_o", "_n"))
        m = m[m["season"] <= legacy_max_season]
        out["joined_rows"][attr] = int(len(m))
        for c in cols:
            r = float((~np.isclose(m[f"{c}_o"], m[f"{c}_n"], equal_nan=True)).mean())
            out["per_column"][c] = round(r, 6)
            out["max_mismatch_rate"] = max(out["max_mismatch_rate"], r)
    out["identical"] = out["max_mismatch_rate"] == 0.0
    return out


def features_stage_reproduces_published(published_raw: Path, published_features: Path,
                                        data, seasons) -> dict:
    import build_staging_dataset as B
    prev = B.LEGACY_ROLLING_SEMANTICS
    B.LEGACY_ROLLING_SEMANTICS = True
    try:
        rebuilt = B.build_features(pd.read_csv(published_raw), data)
    finally:
        B.LEGACY_ROLLING_SEMANTICS = prev

    old = pd.read_csv(published_features)
    key = ["player_id", "season", "week"]
    m = old.merge(rebuilt, on=key, suffixes=("_o", "_n"))
    m = m[m["season"].isin(list(seasons))]
    id_cols = {"player_id", "player_display_name", "position", "team", "opponent_team",
               "season", "week"}
    drift = {}
    for c in rebuilt.columns:
        if c in id_cols:
            continue
        a, b = m[f"{c}_o"], m[f"{c}_n"]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            bad = ~np.isclose(a.astype(float), b.astype(float), rtol=1e-6, atol=1e-8,
                              equal_nan=True)
        else:
            bad = a.astype(str) != b.astype(str)
        if bad.mean() > 0:
            drift[c] = round(float(bad.mean()), 6)
    return {"published_rows": int(len(old)), "rebuilt_rows": int(len(rebuilt)),
            "row_count_identical": len(old) == len(rebuilt),
            "compared_rows": int(len(m)),
            "max_mismatch_rate": max(drift.values()) if drift else 0.0,
            "drift": drift}
