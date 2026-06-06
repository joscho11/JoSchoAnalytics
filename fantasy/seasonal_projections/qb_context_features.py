"""QB-context features — new orthogonal signal the market underweights for pass-catchers.

The residual test found opportunity drives our edge, but the existing `qb_changed` is
just a binary. What actually moves a WR/TE is the QUALITY of their quarterback and,
especially, the *change* in it (a receiver getting a QB upgrade is systematically
under-priced by points-anchored ADP). This builds, per (team, season):

  team_qb_quality   - the season-N primary QB's PRIOR-season passing quality
                      (fantasy pts/game blended with EPA/att; NaN for rookie/new QBs
                      with no NFL prior, which trees handle natively)
  team_qb_delta     - that quality minus the team's N-1 primary QB's prior quality
                      (positive = the team upgraded at QB going into season N)

Kept deliberately to 2 features — the sample is ~700 rows and we already saw more
features overfit. Mild hindsight (uses the season-N primary passer, ~known by a
late-August draft) — same convention as the dataset's existing qb_changed flag.

Import add_qb_context(df); or run standalone to cache qb_context_features.csv.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
QB_COLS = ["team_qb_quality", "team_qb_delta"]
LOAD_FROM = 2012


def _qb_season_quality():
    """One row per (player_id, season): a QB's passing quality that season."""
    import nflreadpy as nfl
    ps = nfl.load_player_stats(list(range(LOAD_FROM, 2026))).to_pandas()
    ps = ps[(ps["season_type"] == "REG") & (ps["position"] == "QB")].copy()
    g = ps.groupby(["player_id", "season"]).agg(
        team=("team", "last"),
        att=("attempts", "sum"),
        games=("week", "nunique"),
        fpts=("fantasy_points", "sum"),
        pass_epa=("passing_epa", "sum"),
    ).reset_index()
    g = g[g["att"] >= 50]                       # ignore cameo/wildcat passers
    g["qb_fppg"] = g["fpts"] / g["games"].replace(0, np.nan)
    g["qb_epa_att"] = g["pass_epa"] / g["att"].replace(0, np.nan)
    # blended, standardized quality score (z of fppg + z of epa/att)
    def z(s):
        return (s - s.mean()) / s.std(ddof=0)
    g["qb_quality"] = z(g["qb_fppg"]) + z(g["qb_epa_att"])
    return g[["player_id", "season", "team", "att", "qb_quality"]]


def _primary_qb(qb):
    """Leading passer (most attempts) per (team, season)."""
    return (qb.sort_values(["att", "player_id"], ascending=[False, True])
            .groupby(["team", "season"]).head(1)[["team", "season", "player_id", "qb_quality"]])


def add_qb_context(df):
    try:
        qb = _qb_season_quality()
    except Exception as e:
        print(f"  qb context load failed ({type(e).__name__}); leaving NaN")
        df["team_qb_quality"] = np.nan; df["team_qb_delta"] = np.nan
        return df

    prim = _primary_qb(qb).rename(columns={"player_id": "qb_id"})
    # each team-season's primary QB and that QB's PRIOR-season quality
    prior = qb[["player_id", "season", "qb_quality"]].rename(
        columns={"player_id": "qb_id", "season": "qb_prior_season", "qb_quality": "qb_prior_quality"})
    prim = prim.merge(prior.assign(season=lambda d: d["qb_prior_season"] + 1)
                      [["qb_id", "season", "qb_prior_quality"]], on=["qb_id", "season"], how="left")
    prim = prim.sort_values(["team", "season"])
    # delta vs the team's prior-season primary QB's prior quality
    prim["prev_team_q"] = prim.groupby("team")["qb_prior_quality"].shift(1)
    prim["team_qb_quality"] = prim["qb_prior_quality"]
    prim["team_qb_delta"] = prim["qb_prior_quality"] - prim["prev_team_q"]

    out = df.merge(prim[["team", "season", "team_qb_quality", "team_qb_delta"]],
                   on=["team", "season"], how="left")
    return out


def main():
    import glob
    ds = sorted(glob.glob(str(HERE / "season_dataset_2014_*.csv")))
    f = next((p for p in ds if p.endswith("2014_2025.csv")), ds[-1])
    df = pd.read_csv(f)
    out = add_qb_context(df)
    out[["player_id", "season", "team"] + QB_COLS].to_csv(HERE / "qb_context_features.csv", index=False)
    print(f"wrote qb_context_features.csv ({len(out):,} rows)")
    print(f"coverage: team_qb_quality {out['team_qb_quality'].notna().mean()*100:.0f}%  "
          f"team_qb_delta {out['team_qb_delta'].notna().mean()*100:.0f}%")
    # biggest QB upgrades among pass-catchers (sanity)
    pc = out[out["position"].isin(["WR", "TE"]) & out["team_qb_delta"].notna()]
    big = pc.sort_values("team_qb_delta", ascending=False).drop_duplicates(["team", "season"]).head(6)
    print("\nbiggest QB upgrades (team-season):")
    print(big[["season", "team", "team_qb_quality", "team_qb_delta"]].to_string(index=False))


if __name__ == "__main__":
    main()
