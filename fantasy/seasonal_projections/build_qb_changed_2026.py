"""Build 2026 `qb_changed` from a DATED preseason QB1 snapshot vs the prior-season passer.

WHY (2026-08-03): `season_dataset_2014_2026.csv` has `qb_changed` NULL for all 923 rows of
2026, while training carries ~31% ones. The feature is in the `feature_cols` of ALL SEVEN
shipped projection bundles (importance rank 5/44 in te_rookie, 13/44 in wr_rookie, 21/32 in
qb_veteran). LightGBM routes NaN and 0 down the same branch here, so every 2026 player is
effectively scored as "his team did not change QB" — false for roughly a third of teams.
`build_2026_board.py` seeds the NaN deliberately; this script supplies the real value.

DEFINITION
  prior primary passer  = the QB with the most pass attempts for that team in 2025
  preseason QB1         = depth_rank 1 at QB in the latest depth snapshot on or before
                          SNAPSHOT_DATE (default: the day this is run, pre-Week-1)
  qb_changed            = 1 if they differ, 0 if the same
                        = <NA> if either side is missing or AMBIGUOUS (never 0)

Missing/ambiguous is left EXPLICITLY UNAVAILABLE. Filling it with 0 is the defect this
replaces, because 0 is a substantive claim ("same QB"), not an absence.

    python fantasy/seasonal_projections/build_qb_changed_2026.py --snapshot-date 2026-08-03
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fantasy"))

from depth_adapter import (DepthSchemaError, as_of_snapshot,  # noqa: E402
                           assert_season_invariants, normalize_depth_charts)

OUT_CSV = Path(__file__).resolve().parent / "qb_changed_2026.csv"
OUT_JSON = Path(__file__).resolve().parent / "qb_changed_2026.provenance.json"
TARGET_SEASON = 2026
PRIOR_SEASON = 2025


def _norm(s: str) -> str:
    import re
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", str(s))
                if unicodedata.category(c) != "Mn").lower().strip()
    s = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$", "", s)
    s = re.sub(r"[\'.\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def prior_primary_passer(season: int) -> pd.DataFrame:
    """Team -> the QB with the most 2025 pass attempts. Ties are AMBIGUOUS."""
    import nflreadpy as nfl
    ps = nfl.load_player_stats([season]).to_pandas()
    att_col = next((c for c in ("attempts", "passing_attempts", "pass_attempts")
                    if c in ps.columns), None)
    if att_col is None:
        raise SystemExit(f"no pass-attempt column in player_stats; got {list(ps.columns)[:20]}")
    team_col = next(c for c in ("team", "recent_team", "team_abbr") if c in ps.columns)
    name_col = next(c for c in ("player_display_name", "player_name", "full_name")
                    if c in ps.columns)
    id_col = next((c for c in ("player_id", "gsis_id") if c in ps.columns), None)

    q = ps[ps[att_col].fillna(0) > 0]
    agg = (q.groupby([team_col, name_col] + ([id_col] if id_col else []))[att_col]
             .sum().reset_index().rename(columns={team_col: "team", name_col: "player",
                                                  att_col: "attempts"}))
    rows = []
    for team, g in agg.groupby("team"):
        top = g[g["attempts"] == g["attempts"].max()]
        rows.append({
            "team": team,
            "prior_passer": top["player"].iloc[0] if len(top) == 1 else None,
            "prior_passer_id": (top[id_col].iloc[0] if (id_col and len(top) == 1) else None),
            "prior_attempts": float(top["attempts"].iloc[0]),
            "prior_ambiguous": len(top) > 1,
        })
    return pd.DataFrame(rows)


def preseason_qb1(season: int, snapshot_date: str) -> pd.DataFrame:
    """Team -> QB1 at the latest depth snapshot on or before `snapshot_date`."""
    import nflreadpy as nfl
    norm = normalize_depth_charts(nfl.load_depth_charts([season]).to_pandas())
    assert_season_invariants(norm, season)
    snap = as_of_snapshot(norm, season, position="QB", depth_rank=1,
                          on_or_before=snapshot_date)
    rows = []
    for team, g in snap.groupby("team"):
        names = sorted(set(g["player_name"].dropna()))
        rows.append({
            "team": team,
            "qb1": names[0] if len(names) == 1 else None,
            "qb1_id": (g["gsis_id"].dropna().iloc[0]
                       if len(names) == 1 and g["gsis_id"].notna().any() else None),
            "qb1_ambiguous": len(names) != 1,
            "qb1_candidates": "|".join(names) if len(names) != 1 else "",
            "snapshot_dt": (str(g["_dt"].max()) if "_dt" in g and g["_dt"].notna().any()
                            else snapshot_date),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-date", default=str(date.today()),
                    help="latest depth snapshot to consider (YYYY-MM-DD)")
    args = ap.parse_args()

    prior = prior_primary_passer(PRIOR_SEASON)
    qb1 = preseason_qb1(TARGET_SEASON, args.snapshot_date)
    m = qb1.merge(prior, on="team", how="outer")

    def decide(r):
        if bool(r.get("qb1_ambiguous")) or bool(r.get("prior_ambiguous")):
            return pd.NA, "ambiguous"
        if not isinstance(r.get("qb1"), str) or not isinstance(r.get("prior_passer"), str):
            return pd.NA, "missing"
        same = _norm(r["qb1"]) == _norm(r["prior_passer"])
        return (0 if same else 1), ("unchanged" if same else "changed")

    decided = [decide(r) for _, r in m.iterrows()]
    m["qb_changed"] = pd.array([d[0] for d in decided], dtype="Int64")
    m["qb_changed_status"] = [d[1] for d in decided]

    counts = m["qb_changed_status"].value_counts().to_dict()
    resolved = int(m["qb_changed"].notna().sum())
    print(f"teams={len(m)}  resolved={resolved}  status={counts}")
    print(f"  changed={int((m['qb_changed'] == 1).sum())}  "
          f"unchanged={int((m['qb_changed'] == 0).sum())}")
    if resolved == 0:
        print("ABORT: nothing resolved — refusing to write an all-NA artifact")
        return 1

    m.sort_values("team").to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_season": TARGET_SEASON, "prior_season": PRIOR_SEASON,
        "snapshot_date_requested": args.snapshot_date,
        "snapshot_dt_max": str(m["snapshot_dt"].dropna().max()),
        "definition": {
            "prior_primary_passer": "max 2025 pass attempts per team; ties = ambiguous",
            "preseason_qb1": "depth_rank==1 at QB in the latest snapshot <= snapshot_date",
            "qb_changed": "1 if different, 0 if same, <NA> if missing/ambiguous "
                          "(NEVER defaulted to 0)",
        },
        "sources": {"depth_charts": "nflreadpy.load_depth_charts (current dt/pos_rank schema)",
                    "player_stats": "nflreadpy.load_player_stats"},
        "counts": counts, "n_teams": int(len(m)), "n_resolved": resolved,
        "n_changed": int((m["qb_changed"] == 1).sum()),
        "n_unchanged": int((m["qb_changed"] == 0).sum()),
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT_CSV.name} + {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
