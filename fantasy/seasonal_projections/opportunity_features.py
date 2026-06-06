"""Landing-spot / opportunity features — the signal the residual test says the market underweights.

The Sleeper-residual test (value_eval.py) showed our edge is concentrated in
OPPORTUNITY: `vacated_*_share` were the top drivers by a wide margin, but they're
crude (team-level "who left"). This builds richer, player-level opportunity:

  team_changed            - player on a different team than last season (movers are mispriced)
  ret_tgt_competition     - returning target share held by OTHER players on the season-N team
                            (how crowded the target tree is — low = more room)
  ret_rush_competition    - returning rush share held by other players (RB room)
  net_tgt_room            - vacated_target_share - ret_tgt_competition (net opportunity opening up)
  net_rush_room           - vacated_rush_share  - ret_rush_competition
  n_ret_pass_catchers     - count of returning teammates with prior target_share >= 0.10

All derivable from the existing season dataset (prior shares + season-N team) plus a
roster load for the team-change flag. Keyed by (player_id, season) for a clean join.

Run standalone to cache:  python opportunity_features.py   -> opportunity_features.csv
Or import add_opportunity(df) to attach on the fly.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
OPP_COLS = ["team_changed", "ret_tgt_competition", "ret_rush_competition",
            "net_tgt_room", "net_rush_room", "n_ret_pass_catchers"]


def _prior_team_map():
    """player_id -> {season: team}, shifted to give each row its PRIOR-season team."""
    import nflreadpy as nfl
    ros = nfl.load_rosters(list(range(2013, 2026))).to_pandas()
    ros = ros[["season", "team", "gsis_id"]].dropna().rename(columns={"gsis_id": "player_id"})
    ros = ros.drop_duplicates(["player_id", "season"]).sort_values(["player_id", "season"])
    ros["prior_team"] = ros.groupby("player_id")["team"].shift(1)
    ros["season"] = ros["season"]
    return ros[["player_id", "season", "team", "prior_team"]]


def add_opportunity(df, use_roster=True):
    """Attach opportunity features. Pure-pandas from `df`; roster load only for team_changed."""
    d = df.copy()

    # crowdedness of the role: returning prior shares held by teammates on the season-N team.
    # prior_target_share is the player's OWN N-1 target share; summing per (team, season) and
    # subtracting self gives the returning competition for targets. Carries use prior_carries_pg
    # as a volume proxy (no rush-share column in the dataset), normalized within team.
    d["_tgt"] = d["prior_target_share"].fillna(0)
    team_tgt = d.groupby(["team", "season"])["_tgt"].transform("sum")
    d["ret_tgt_competition"] = (team_tgt - d["_tgt"]).clip(lower=0)

    d["_car"] = d["prior_carries_pg"].fillna(0)
    team_car = d.groupby(["team", "season"])["_car"].transform("sum")
    team_car_safe = team_car.replace(0, np.nan)
    d["ret_rush_competition"] = ((team_car - d["_car"]) / team_car_safe).clip(lower=0).fillna(0)

    # net room = opportunity vacated minus what returning teammates still command
    d["net_tgt_room"] = d["vacated_target_share"].fillna(0) - d["ret_tgt_competition"]
    d["net_rush_room"] = d["vacated_rush_share"].fillna(0) - d["ret_rush_competition"]

    # number of returning meaningful pass-catchers on the team (target competition count)
    d["_big"] = (d["prior_target_share"].fillna(0) >= 0.10).astype(int)
    team_big = d.groupby(["team", "season"])["_big"].transform("sum")
    d["n_ret_pass_catchers"] = (team_big - d["_big"]).clip(lower=0)

    # team change (movers are systematically mispriced by points-anchored ADP)
    d["team_changed"] = np.nan
    if use_roster:
        try:
            pt = _prior_team_map()
            d = d.merge(pt[["player_id", "season", "prior_team"]], on=["player_id", "season"], how="left")
            d["team_changed"] = ((d["prior_team"].notna()) & (d["team"] != d["prior_team"])).astype(float)
            d.loc[d["prior_team"].isna(), "team_changed"] = np.nan   # rookies / unknown -> NaN, not 0
            d.drop(columns=["prior_team"], inplace=True)
        except Exception as e:
            print(f"  team_changed roster load failed ({type(e).__name__}); leaving NaN")

    d.drop(columns=["_tgt", "_car", "_big"], inplace=True)
    return d


def main():
    import glob
    ds = sorted(glob.glob(str(HERE / "season_dataset_2014_*.csv")))
    f = next((p for p in ds if p.endswith("2014_2025.csv")), ds[-1])
    df = pd.read_csv(f)
    out = add_opportunity(df)
    out[["player_id", "season"] + OPP_COLS].to_csv(HERE / "opportunity_features.csv", index=False)
    print(f"wrote opportunity_features.csv ({len(out):,} rows)")
    print(out[OPP_COLS].describe().round(3).to_string())


if __name__ == "__main__":
    main()
