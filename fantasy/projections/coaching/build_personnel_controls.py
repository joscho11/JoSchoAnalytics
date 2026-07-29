"""ARM 3 PERSONNEL CONTROLS — the preseason expectation model's feature block.

One row per (season, team). EVERY column is knowable BEFORE season S kicks off: it is built from
season S-1 production plus the season-S week-1 roster. No season-S performance enters.

Columns
  prior_epa_play, prior_success_rate, prior_points_per_drive, prior_plays, prior_pass_rate,
  prior_ol_sack_rate            lagged team form (from the team-offense panel)
  prior_qb_id, prior_qb_epa_play, prior_qb_cpoe    S-1 primary passer and his efficiency
  qb_returns                    is the S-1 primary passer on the S week-1 roster
  ret_qb_attempt_share          share of S-1 team pass attempts by players on the S week-1 roster
  ret_rb_carry_share            same for carries by RBs
  ret_wrte_target_share         same for targets by WR/TE
  vacated_rush_share            1 - ret_rb_carry_share
  vacated_target_share          1 - ret_wrte_target_share
  ret_skill_fantasy_share       aggregate returning share of S-1 skill-position fantasy production
  relocated                     franchise played under a different code in S-1 (STL/SD/OAK moves)

CPOE is only available where nflverse ships it (2006+); earlier seasons carry NaN rather than an
invented value.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIRST, LAST = 1999, 2026
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}
RELOCATIONS = {("LA", 2016), ("LAC", 2017), ("LV", 2020)}   # first season under the new code


def _num(d, c, default=0.0):
    return pd.to_numeric(d[c], errors="coerce").fillna(default) if c in d.columns \
        else pd.Series(default, index=d.index)


def _norm_roster(r, season):
    idc = "gsis_id" if "gsis_id" in r.columns else "player_id"
    if idc not in r.columns or "team" not in r.columns:
        return None
    r = r[[idc, "team"]].dropna().rename(columns={idc: "pid"})
    r["team"] = r["team"].replace(TEAM_CANON)
    r["season"] = season
    return r.drop_duplicates()


def week1_rosters(seasons):
    """Season-S week-1 roster: who is actually on hand before a snap is played.

    For an UNPLAYED season there is no week-1 weekly roster, so fall back to the season roster
    (which exists through the offseason). If neither is available the season is omitted entirely
    and every returning share for it comes out NaN -- never 0, which would silently read as
    "the whole roster departed" and hand every team a fabricated vacated share of 1.0.
    """
    import nflreadpy as nfl
    out = []
    for s in seasons:
        r1 = None
        try:
            r = nfl.load_rosters_weekly(seasons=[s])
            try:
                r = r.to_pandas()
            except AttributeError:
                pass
            if "week" in r.columns:
                r = r[pd.to_numeric(r["week"], errors="coerce") == 1]
            if len(r):
                r1 = _norm_roster(r, s)
        except Exception:
            r1 = None
        if r1 is None or not len(r1):
            try:
                r = nfl.load_rosters(seasons=[s])
                try:
                    r = r.to_pandas()
                except AttributeError:
                    pass
                if len(r):
                    r1 = _norm_roster(r, s)
                    print(f"    {s}: week-1 weekly roster empty -> season roster fallback "
                          f"({0 if r1 is None else len(r1)} rows)")
            except Exception:
                r1 = None
        if r1 is not None and len(r1):
            out.append(r1)
        else:
            print(f"    {s}: NO roster available -> returning shares emitted as NaN")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(
        columns=["pid", "team", "season"])


def prior_usage(seasons):
    """S-1 per-player usage by team, from PBP actors."""
    import nflreadpy as nfl
    cols = ["season", "posteam", "season_type", "play_type", "qb_kneel", "qb_spike",
            "two_point_attempt", "rush_attempt", "pass_attempt", "sack", "epa", "cpoe",
            "rusher_player_id", "receiver_player_id", "passer_player_id"]
    frames = []
    for s in seasons:
        d = nfl.load_pbp(seasons=[s])
        try:
            d = d.to_pandas()
        except AttributeError:
            pass
        d = d[[c for c in cols if c in d.columns]].copy()
        d["posteam"] = d["posteam"].replace(TEAM_CANON)
        frames.append(d)
    pbp = pd.concat(frames, ignore_index=True)
    pbp = pbp[(pbp.get("season_type", "REG") == "REG") & pbp["posteam"].notna()]
    pbp = pbp[pbp["play_type"].isin(["pass", "run"])]
    pbp = pbp[(_num(pbp, "qb_kneel") != 1) & (_num(pbp, "qb_spike") != 1)
              & (_num(pbp, "two_point_attempt") != 1)]
    return pbp


def build(seasons=None):
    seasons = seasons or list(range(FIRST, LAST + 1))
    print("=" * 80)
    print("ARM 3 PERSONNEL CONTROLS")
    print("=" * 80)

    panel = pd.read_csv(DATA / "team_offense_panel.csv")
    pbp = prior_usage([s for s in seasons if s <= 2025])
    rost = week1_rosters(seasons)
    print(f"  pbp {len(pbp):,} plays | week-1 roster rows {len(rost):,}")

    import nflreadpy as nfl
    pl = nfl.load_players()
    try:
        pl = pl.to_pandas()
    except AttributeError:
        pass
    idc = "gsis_id" if "gsis_id" in pl.columns else "player_id"
    pos = pl[[idc, "position"]].dropna().drop_duplicates(idc)
    pos.columns = ["pid", "pos"]

    key = ["season", "posteam"]
    # --- per-player prior usage
    att = pbp[_num(pbp, "pass_attempt") == 1].groupby(key + ["passer_player_id"]).size() \
        .reset_index(name="att").rename(columns={"passer_player_id": "pid"})
    car = pbp[_num(pbp, "rush_attempt") == 1].groupby(key + ["rusher_player_id"]).size() \
        .reset_index(name="car").rename(columns={"rusher_player_id": "pid"})
    tgt = pbp[_num(pbp, "pass_attempt") == 1].dropna(subset=["receiver_player_id"]) \
        .groupby(key + ["receiver_player_id"]).size().reset_index(name="tgt") \
        .rename(columns={"receiver_player_id": "pid"})

    # --- primary passer + his efficiency
    qb = att.sort_values("att", ascending=False).drop_duplicates(key)
    qbeff = pbp[_num(pbp, "pass_attempt") == 1].groupby(key + ["passer_player_id"]).agg(
        qb_epa=("epa", "mean"), qb_cpoe=("cpoe", "mean")).reset_index() \
        .rename(columns={"passer_player_id": "pid"})
    qb = qb.merge(qbeff, on=key + ["pid"], how="left")

    rows = []
    for season in seasons:
        prev = season - 1
        p_att = att[att.season == prev]
        p_car = car[car.season == prev].merge(pos, on="pid", how="left")
        p_tgt = tgt[tgt.season == prev].merge(pos, on="pid", how="left")
        p_qb = qb[qb.season == prev]
        r_now = rost[rost.season == season]
        ret_ids = set(r_now["pid"])

        for team in sorted(panel.team.unique()):
            a = p_att[p_att.posteam == team]
            c = p_car[(p_car.posteam == team) & (p_car["pos"] == "RB")]
            t = p_tgt[(p_tgt.posteam == team) & (p_tgt["pos"].isin(["WR", "TE"]))]
            q = p_qb[p_qb.posteam == team]

            def share(df, col):
                tot = df[col].sum()
                if not tot:
                    return np.nan
                return df[df.pid.isin(ret_ids)][col].sum() / tot

            qb_id = q["pid"].iloc[0] if len(q) else None
            rows.append(dict(
                season=season, team=team,
                prior_qb_id=qb_id,
                prior_qb_epa_play=(q["qb_epa"].iloc[0] if len(q) else np.nan),
                prior_qb_cpoe=(q["qb_cpoe"].iloc[0] if len(q) else np.nan),
                qb_returns=(float(qb_id in ret_ids) if (qb_id and len(r_now)) else np.nan),
                ret_qb_attempt_share=share(a, "att"),
                ret_rb_carry_share=share(c, "car"),
                ret_wrte_target_share=share(t, "tgt"),
                relocated=float((team, season) in RELOCATIONS),
            ))
    ctrl = pd.DataFrame(rows)
    ctrl["vacated_rush_share"] = 1 - ctrl["ret_rb_carry_share"]
    ctrl["vacated_target_share"] = 1 - ctrl["ret_wrte_target_share"]
    ctrl["ret_skill_fantasy_share"] = ctrl[
        ["ret_rb_carry_share", "ret_wrte_target_share"]].mean(axis=1)

    # --- lagged team form from the panel
    lag_src = ["epa_play", "success_rate", "points_per_drive", "plays", "pass_rate",
               "ol_sack_rate"]
    lag = panel[["season", "team"] + [c for c in lag_src if c in panel.columns]].copy()
    lag["season"] = lag["season"] + 1
    lag = lag.rename(columns={c: f"prior_{c}" for c in lag_src if c in lag.columns})
    ctrl = ctrl.merge(lag, on=["season", "team"], how="left")

    ctrl.to_csv(DATA / "personnel_controls.csv", index=False)

    print(f"\ncontrols: {ctrl.shape[0]} team-seasons x {ctrl.shape[1]} columns")
    print("\ncoverage (non-null %), 2014-2026 rows:")
    sub = ctrl[ctrl.season.between(2014, 2026)]
    for c in ["prior_epa_play", "prior_success_rate", "prior_points_per_drive", "prior_plays",
              "prior_pass_rate", "prior_ol_sack_rate", "prior_qb_epa_play", "prior_qb_cpoe",
              "qb_returns", "ret_qb_attempt_share", "ret_rb_carry_share",
              "ret_wrte_target_share", "vacated_rush_share", "vacated_target_share",
              "ret_skill_fantasy_share"]:
        if c in sub.columns:
            print(f"  {c:24s} {100*sub[c].notna().mean():5.1f}%")

    print("\nSANITY — 2026 teams with the most vacated WR/TE targets:")
    s26 = ctrl[ctrl.season == 2026].nlargest(5, "vacated_target_share")
    print(s26[["team", "vacated_target_share", "vacated_rush_share", "qb_returns"]]
          .to_string(index=False))
    print(f"\nwrote {DATA/'personnel_controls.csv'}")
    return ctrl


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        raise SystemExit("pass --build")
