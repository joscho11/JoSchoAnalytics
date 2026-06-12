"""Incoming-competition guard for the value board.

Our prior-stats model projects an incumbent from last year's usage as if their role is
unchanged. It does NOT see touches *arriving* to take work away — a drafted rookie, a
free-agent/trade signing, or a star teammate returning from injury. So it over-likes
incumbents whose room just got more crowded (e.g. James Conner / Trey Benson once Arizona
adds a back), flagging false BUYs. The market (ADP/Sleeper) prices this; we can't, from
stats alone. This guard is a leak-safe RULE (everything is known at draft time) that flags,
for each player, whether a NEW or RETURNING threat joined their position room on their team.
`build_value_board.py` then suppresses BUY calls on threatened incumbents.

Threat at (team, position) = another player in that room who is:
  - rookie      : a rookie drafted in round <= 3
  - new signing : arrived from another team this offseason (roster change), with real prior usage
  - returning starter : missed >= 6 games last year but was a genuine producer (high career-high PPG)

All from draft-time-knowable info (rosters, draft round, prior usage/availability).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Deliberately CONSERVATIVE: only a significant incoming piece counts as a real role threat,
# so we don't fade a clear starter just because their team made a depth move.
ROOKIE_MAX_ROUND = 2                                       # a featured early-round rookie, not Day-3 depth
FA_CARRIES = 12                                            # a lead-back workload (carries/game) for an RB arrival
FA_TGTSHARE = 0.18                                         # a clear go-to target share for a WR/TE arrival
RETURN_PPG = {"QB": 16, "RB": 12, "WR": 11, "TE": 9}      # a genuine producer returning from injury, by position
ELITE_POS_RANK = 12                                       # an incumbent inside the top-12 at their position has a
                                                          # secure role -> never flag them (handled in build_value_board)


def _arrivals(season):
    """gsis_ids that changed NFL teams INTO `season` (free agents / trades). By player id, so
    team-abbreviation differences between data sources don't matter."""
    import nflreadpy as nfl
    ros = nfl.load_rosters([season - 1, season]).to_pandas()
    ros = ros[["season", "team", "gsis_id"]].dropna().drop_duplicates(["gsis_id", "season"])
    prev = ros[ros.season == season - 1][["gsis_id", "team"]].rename(columns={"team": "prev_team"})
    cur = ros[ros.season == season][["gsis_id", "team"]]
    m = cur.merge(prev, on="gsis_id", how="left")
    return set(m[m["prev_team"].notna() & (m["team"] != m["prev_team"])]["gsis_id"])


def add_incoming_competition(season_df):
    """Return a Series (aligned to season_df.index) giving, for each player, the type of NEW/
    RETURNING threat present elsewhere in their (team, position) room — '' if none."""
    d = season_df.copy()
    season = int(d["season"].iloc[0])
    try:
        arrivals = _arrivals(season)
    except Exception as e:
        print(f"  incoming_competition: roster load failed ({type(e).__name__}); skipping arrivals")
        arrivals = set()

    cap = d["draft_round"].fillna(99)
    ts = d["prior_target_share"].fillna(0)
    cpg = d["prior_carries_pg"].fillna(0)
    gm = d["prior_games_missed"].fillna(0)
    chp = d["career_high_ppg"].fillna(0)
    bar = d["position"].map(RETURN_PPG).fillna(10)

    is_rookie = (d["is_rookie"] == 1) & (cap <= ROOKIE_MAX_ROUND)
    is_arrival = d["player_id"].isin(arrivals) & ((ts >= FA_TGTSHARE) | (cpg >= FA_CARRIES))
    is_injret = (gm >= 6) & (chp >= bar)
    d["_ttype"] = np.where(is_rookie, "rookie",
                  np.where(is_arrival, "new signing",
                  np.where(is_injret, "returning starter", "")))

    out = pd.Series("", index=d.index)
    for (team, pos), g in d.groupby(["team", "position"]):
        if pos == "QB":                                     # QB roles are clear; a backup doesn't threaten the starter
            continue
        threats = g[g["_ttype"] != ""]
        # crowded BACKFIELD (RB only): a 4-deep committee of capable bodies dilutes everyone's touches.
        crowded = pos == "RB" and int((g["prior_carries_pg"].fillna(0) >= 5).sum()) >= 4
        for idx in g.index:
            # an ELITE incumbent (secure top-of-position role) is never threatened by a new piece
            if d.loc[idx, "adp_pos_rank"] <= ELITE_POS_RANK:
                continue
            others = threats[threats.index != idx]          # competition = a THREAT that isn't you
            if len(others):
                out.loc[idx] = others["_ttype"].iloc[0]
            elif crowded and (d.loc[idx, "prior_carries_pg"] or 0) < 14:   # not a clear bell-cow
                out.loc[idx] = "crowded backfield"
    return out


def main():
    import glob
    HERE = Path(__file__).resolve().parent
    f = sorted(glob.glob(str(HERE / "season_dataset_2014_*.csv")))[-1]
    df = pd.read_csv(f)
    for season in (2025, 2026):
        sd = df[df.season == season]
        if sd.empty:
            continue
        comp = add_incoming_competition(sd)
        flagged = sd.loc[comp[comp != ""].index]
        flagged = flagged[flagged["adp_overall_rank"] <= 180]
        print(f"\n{season}: {len(flagged)} drafted players facing incoming competition. sample:")
        show = flagged.assign(threat=comp).sort_values("adp_overall_rank")
        print(show[["player", "position", "team", "threat"]].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
