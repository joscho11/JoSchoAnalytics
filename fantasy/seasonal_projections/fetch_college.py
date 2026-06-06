"""Fetch & aggregate college production from cfbfastR (key-less, no API needed).

Why: the ADP-value backtest showed the market (ADP/Sleeper) is efficient on
veterans but demonstrably WEAK on rookies — rookies have no NFL prior for the
market to price. The one untapped, orthogonal signal is COLLEGE production
(dominator rating, breakout-by-class-year, efficiency), which NFL prior-season
stats can't contain by definition. This builds that feature source.

Source: github.com/sportsdataverse/cfbfastR-data (public parquet, no key). The
player_stats files are play-level with player attribution; we aggregate to one
row per (athlete, season), compute team-relative DOMINATOR shares, join the
roster for class-year + position, then summarize each player's college CAREER
into one row keyed by normalized name (the bridge to NFL draftees — ~90% match;
cfbfastR uses ESPN ids, NFL draft_picks uses sports-ref slugs, so no id join).

Outputs (cached, re-runnable):
  college_production_2014_2024.csv  — one row per (athlete, season)
  college_features.csv              — one row per college player (career summary,
                                       keyed by norm_name) for the NFL rookie join

Run:  python fetch_college.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import norm_name

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SEASONS = list(range(2014, 2025))   # covers college careers of NFL rookies 2020-2025+
RAW = "https://github.com/sportsdataverse/cfbfastR-data/raw/main"
PROD_CSV = HERE / "college_production_2014_2024.csv"
FEAT_CSV = HERE / "college_features.csv"


def _stat_url(yr):
    return f"{RAW}/player_stats/parquet/player_stats_{yr}.parquet"


def _roster_url(yr):
    return f"{RAW}/cfb/roster/parquet/roster_{yr}.parquet"


def aggregate_season(yr):
    """One row per (athlete_id, season) of college scrimmage production + team shares."""
    ps = pd.read_parquet(_stat_url(yr))

    # receiving
    rec = (ps.dropna(subset=["reception_player_id"])
           .groupby("reception_player_id")
           .agg(name=("reception_player", "last"), team=("team", "last"),
                rec_yds=("reception_yds", "sum"), rec=("play_id", "count")).reset_index()
           .rename(columns={"reception_player_id": "pid"}))
    # rushing
    rush = (ps.dropna(subset=["rush_player_id"])
            .groupby("rush_player_id")
            .agg(rush_name=("rush_player", "last"), rush_team=("team", "last"),
                 rush_yds=("rush_yds", "sum"), car=("play_id", "count")).reset_index()
            .rename(columns={"rush_player_id": "pid"}))
    # passing (completions)
    pas = (ps.dropna(subset=["completion_player_id"])
           .groupby("completion_player_id")
           .agg(pass_name=("completion_player", "last"), pass_team=("team", "last"),
                pass_yds=("completion_yds", "sum"), cmp=("play_id", "count")).reset_index()
           .rename(columns={"completion_player_id": "pid"}))
    # targets
    tgt = (ps.dropna(subset=["target_player_id"])
           .groupby("target_player_id").agg(tgt=("play_id", "count")).reset_index()
           .rename(columns={"target_player_id": "pid"}))

    # touchdowns, split rec vs rush by whether the scorer was the receiver/rusher on that play
    td = ps.dropna(subset=["touchdown_player_id"]).copy()
    td["rec_td"] = (td["touchdown_player_id"] == td["reception_player_id"]).astype(int)
    td["rush_td"] = (td["touchdown_player_id"] == td["rush_player_id"]).astype(int)
    tds = (td.groupby("touchdown_player_id").agg(rec_td=("rec_td", "sum"), rush_td=("rush_td", "sum"))
           .reset_index().rename(columns={"touchdown_player_id": "pid"}))

    # games: distinct games a player appears in any offensive role
    long = pd.concat([
        ps[["reception_player_id", "game_id"]].rename(columns={"reception_player_id": "pid"}),
        ps[["rush_player_id", "game_id"]].rename(columns={"rush_player_id": "pid"}),
        ps[["completion_player_id", "game_id"]].rename(columns={"completion_player_id": "pid"}),
    ], ignore_index=True).dropna(subset=["pid"])
    games = long.groupby("pid")["game_id"].nunique().rename("games").reset_index()

    m = (rec.merge(rush, on="pid", how="outer").merge(pas, on="pid", how="outer")
         .merge(tgt, on="pid", how="outer").merge(tds, on="pid", how="outer")
         .merge(games, on="pid", how="outer"))
    # coalesce name/team across roles
    m["name"] = m["name"].fillna(m["rush_name"]).fillna(m["pass_name"])
    m["team"] = m["team"].fillna(m["rush_team"]).fillna(m["pass_team"])
    m = m.drop(columns=["rush_name", "rush_team", "pass_name", "pass_team"])
    for c in ["rec_yds", "rec", "rush_yds", "car", "pass_yds", "cmp", "tgt", "rec_td", "rush_td", "games"]:
        m[c] = m[c].fillna(0)
    m["scrim_yds"] = m["rec_yds"] + m["rush_yds"]
    m["scrim_td"] = m["rec_td"] + m["rush_td"]
    m["season"] = yr

    # team-relative dominator: player's share of team scrimmage yards & TDs
    tot = m.groupby("team").agg(team_scrim_yds=("scrim_yds", "sum"),
                                team_scrim_td=("scrim_td", "sum"),
                                team_rec_yds=("rec_yds", "sum")).reset_index()
    m = m.merge(tot, on="team", how="left")
    yd_share = m["scrim_yds"] / m["team_scrim_yds"].replace(0, np.nan)
    td_share = m["scrim_td"] / m["team_scrim_td"].replace(0, np.nan)
    m["dominator"] = np.nanmean(np.vstack([yd_share, td_share]), axis=0)
    m["rec_yds_share"] = m["rec_yds"] / m["team_rec_yds"].replace(0, np.nan)
    return m


def add_roster(prod):
    """Attach class-year (`year`) and position from the season roster (by athlete_id)."""
    frames = []
    for yr in SEASONS:
        try:
            r = pd.read_parquet(_roster_url(yr))[["athlete_id", "year", "position", "weight", "height", "season"]]
            frames.append(r)
        except Exception as e:
            print(f"  roster {yr}: {type(e).__name__} (skipped)")
    if not frames:
        prod["class_year"] = np.nan; prod["cfb_pos"] = np.nan
        return prod
    ros = pd.concat(frames, ignore_index=True).rename(columns={"athlete_id": "pid"})
    ros["pid"] = pd.to_numeric(ros["pid"], errors="coerce")
    prod["pid"] = pd.to_numeric(prod["pid"], errors="coerce")
    prod = prod.merge(ros.rename(columns={"year": "class_year", "position": "cfb_pos"}),
                      on=["pid", "season"], how="left")
    return prod


def build_career_features(prod):
    """Collapse each player's college seasons into one career-summary row for the NFL join."""
    prod = prod.sort_values(["pid", "season"])
    prod["norm_name"] = prod["name"].map(norm_name)

    def per_player(g):
        g = g.sort_values("season")
        last = g.iloc[-1]                       # final college season (closest to draft)
        gp = g["games"].replace(0, np.nan)
        # best dominator season + the class-year it happened (lower class = earlier breakout)
        bi = g["dominator"].idxmax() if g["dominator"].notna().any() else None
        best_dom = g["dominator"].max()
        breakout_class = g.loc[bi, "class_year"] if bi is not None else np.nan
        return pd.Series({
            "cfb_pid": last["pid"],
            "cfb_name": last["name"],
            "cfb_team": last["team"],
            "cfb_pos": last.get("cfb_pos", np.nan),
            "cfb_seasons": len(g),
            "cfb_last_season": last["season"],
            "cfb_final_class": last["class_year"],
            # final-season production (per game)
            "cfb_rec_ypg": last["rec_yds"] / (last["games"] or np.nan),
            "cfb_rush_ypg": last["rush_yds"] / (last["games"] or np.nan),
            "cfb_scrim_ypg": last["scrim_yds"] / (last["games"] or np.nan),
            "cfb_scrim_td": last["scrim_td"],
            "cfb_rec_pg": last["rec"] / (last["games"] or np.nan),
            "cfb_final_dom": last["dominator"],
            "cfb_final_recshare": last["rec_yds_share"],
            "cfb_ypc": last["rush_yds"] / (last["car"] or np.nan),
            "cfb_ypr": last["rec_yds"] / (last["rec"] or np.nan),
            # career signal
            "cfb_best_dom": best_dom,
            "cfb_breakout_class": breakout_class,        # 1-2 = early breakout (strong)
            "cfb_career_scrim_yds": g["scrim_yds"].sum(),
            "cfb_career_scrim_td": g["scrim_td"].sum(),
        })

    feat = prod.groupby("pid", group_keys=False).apply(per_player).reset_index(drop=True)
    feat["norm_name"] = feat["cfb_name"].map(norm_name)
    # keep the most productive player per norm_name (handles the rare name collision)
    feat = feat.sort_values("cfb_career_scrim_yds", ascending=False).drop_duplicates("norm_name")
    return feat


def main():
    print(f"Aggregating cfbfastR player_stats {SEASONS[0]}-{SEASONS[-1]} ...")
    prod = pd.concat([aggregate_season(y) for y in SEASONS], ignore_index=True)
    print(f"  player-seasons: {len(prod):,}")
    prod = add_roster(prod)
    prod.to_csv(PROD_CSV, index=False)
    print(f"  wrote {PROD_CSV.name}")

    feat = build_career_features(prod)
    feat.to_csv(FEAT_CSV, index=False)
    print(f"  wrote {FEAT_CSV.name}  ({len(feat):,} college players)")
    print("\nsample (top career scrimmage yards):")
    cols = ["cfb_name", "cfb_pos", "cfb_last_season", "cfb_final_dom", "cfb_best_dom", "cfb_breakout_class", "cfb_scrim_ypg"]
    print(feat.sort_values("cfb_career_scrim_yds", ascending=False).head(8)[cols].to_string(index=False))
    return feat


if __name__ == "__main__":
    main()
