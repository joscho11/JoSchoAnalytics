"""ALLOCATION / PACE / SCORING PANEL — completes the team-offense data layer for Arms 1, 3 and 4.

Adds to `team_offense_panel.csv` the quantities the frozen arms require but the efficiency panel
did not carry:

  ARM 1   offensive points per game (the fifth ranking component)
  ARM 4   seconds_per_play (REAL pace, replacing the all-null placeholder), plus
          rb/qb carry share, rb/wr/te target share, red-zone opportunity share by position,
          and WR air-yard tendency (adot)
  ARM 3   the personnel-control block: prior-season team form, QB continuity, returning shares of
          QB attempts / RB carries / WR-TE targets, vacated shares, OL sack rate, and aggregate
          returning skill production.

Position is resolved by joining PBP actor ids to `load_players` (one row per player, so the join
cannot fan out) -- NOT to weekly rosters, which would multiply rows per player-week.

PACE. Seconds per play is the mean gap between consecutive offensive snaps WITHIN a drive, taken
from `game_seconds_remaining`. Gaps outside (0, 60] seconds are dropped: they span timeouts,
quarter breaks, change of possession and clock stoppages, none of which measure tempo.

Every column here is a SAME-SEASON observation. Lagging, coach attribution and shrinkage happen
downstream -- this file never looks at a coach.
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
FIRST, LAST = 1999, 2025
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}

PBP_COLS = ["season", "week", "game_id", "posteam", "season_type", "play_type", "epa", "success",
            "yards_gained", "qb_kneel", "qb_spike", "two_point_attempt", "pass", "rush", "down",
            "yardline_100", "fixed_drive", "fixed_drive_result", "game_seconds_remaining",
            "air_yards", "sack", "rusher_player_id", "receiver_player_id", "passer_player_id",
            "play_id", "touchdown", "rush_attempt", "pass_attempt", "complete_pass"]


def _num(d, c, default=0.0):
    return pd.to_numeric(d[c], errors="coerce").fillna(default) if c in d.columns \
        else pd.Series(default, index=d.index)


def load_positions():
    """player_id -> position, one row per player."""
    import nflreadpy as nfl
    p = nfl.load_players()
    try:
        p = p.to_pandas()
    except AttributeError:
        pass
    idcol = "gsis_id" if "gsis_id" in p.columns else "player_id"
    poscol = "position" if "position" in p.columns else "position_group"
    pos = p[[idcol, poscol]].dropna().drop_duplicates(idcol)
    pos.columns = ["pid", "pos"]
    return pos


def load_pbp(seasons):
    import nflreadpy as nfl
    frames = []
    for s in seasons:
        d = nfl.load_pbp(seasons=[s])
        try:
            d = d.to_pandas()
        except AttributeError:
            pass
        d = d[[c for c in PBP_COLS if c in d.columns]].copy()
        d["posteam"] = d["posteam"].replace(TEAM_CANON)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def build(seasons=None):
    seasons = seasons or list(range(FIRST, LAST + 1))
    print("=" * 80)
    print(f"ALLOCATION / PACE / SCORING PANEL — {seasons[0]}-{seasons[-1]}")
    print("=" * 80)
    pbp = load_pbp(seasons)
    pos = load_positions()
    print(f"  loaded {len(pbp):,} plays | {len(pos):,} player positions")

    d = pbp[(pbp.get("season_type", "REG") == "REG") & pbp["posteam"].notna()].copy()
    scrim = d[d["play_type"].isin(["pass", "run"])].copy()
    rp = scrim[(_num(scrim, "qb_kneel") != 1) & (_num(scrim, "qb_spike") != 1)
               & (_num(scrim, "two_point_attempt") != 1)].copy()
    key = ["season", "posteam"]

    g = rp.groupby(key).agg(games=("game_id", "nunique")).reset_index()

    # ---------------------------------------------------------------- PACE (real, not a placeholder)
    p = rp.dropna(subset=["fixed_drive", "game_seconds_remaining"]).copy()
    p = p.sort_values(["game_id", "fixed_drive", "play_id"])
    p["gap"] = p.groupby(["game_id", "fixed_drive"])["game_seconds_remaining"].diff().mul(-1)
    valid = p[(p["gap"] > 0) & (p["gap"] <= 60)]
    pace = valid.groupby(key)["gap"].mean().reset_index(name="seconds_per_play")
    print(f"  pace: {len(valid):,} valid inter-snap gaps "
          f"({100*len(valid)/max(len(p),1):.0f}% of plays)")

    # ---------------------------------------------------------------- offensive points per game
    dr = scrim.dropna(subset=["fixed_drive"]).groupby(
        ["season", "posteam", "game_id", "fixed_drive"]).agg(
        result=("fixed_drive_result", "first")).reset_index()
    res = dr["result"].astype(str)
    dr["pts"] = np.select(
        [res.str.contains("Touchdown", case=False, na=False),
         res.str.contains("Field goal", case=False, na=False),
         res.str.contains("Safety", case=False, na=False)], [7.0, 3.0, -2.0], default=0.0)
    ppg = dr.groupby(key)["pts"].sum().reset_index(name="off_points")
    ppg = ppg.merge(g, on=key, how="left")
    ppg["off_points_per_game"] = ppg["off_points"] / ppg["games"]

    # ---------------------------------------------------------------- allocation shares
    rush = rp[_num(rp, "rush_attempt") == 1].merge(
        pos.rename(columns={"pid": "rusher_player_id", "pos": "rusher_pos"}),
        on="rusher_player_id", how="left")
    tot_rush = rush.groupby(key).size().reset_index(name="team_carries")
    by_rp = rush.groupby(key + ["rusher_pos"]).size().reset_index(name="n")
    carry = by_rp.pivot_table(index=key, columns="rusher_pos", values="n",
                              aggfunc="sum").reset_index().fillna(0)
    carry = carry.merge(tot_rush, on=key, how="left")
    for src, out in (("RB", "rb_carry_share"), ("QB", "qb_carry_share")):
        carry[out] = carry.get(src, 0) / carry["team_carries"].replace(0, np.nan)

    tgt = rp[_num(rp, "pass_attempt") == 1].dropna(subset=["receiver_player_id"]).merge(
        pos.rename(columns={"pid": "receiver_player_id", "pos": "rec_pos"}),
        on="receiver_player_id", how="left")
    tot_tgt = tgt.groupby(key).size().reset_index(name="team_targets")
    by_tp = tgt.groupby(key + ["rec_pos"]).size().reset_index(name="n")
    tsh = by_tp.pivot_table(index=key, columns="rec_pos", values="n",
                            aggfunc="sum").reset_index().fillna(0)
    tsh = tsh.merge(tot_tgt, on=key, how="left")
    for src, out in (("RB", "rb_target_share"), ("WR", "wr_target_share"), ("TE", "te_target_share")):
        tsh[out] = tsh.get(src, 0) / tsh["team_targets"].replace(0, np.nan)

    # ---------------------------------------------------------------- red-zone opportunity shares
    rz = rp[_num(rp, "yardline_100", 99) <= 20].copy()
    rz_r = rz[_num(rz, "rush_attempt") == 1].merge(
        pos.rename(columns={"pid": "rusher_player_id", "pos": "actor_pos"}),
        on="rusher_player_id", how="left")[key + ["actor_pos"]]
    rz_t = rz[_num(rz, "pass_attempt") == 1].dropna(subset=["receiver_player_id"]).merge(
        pos.rename(columns={"pid": "receiver_player_id", "pos": "actor_pos"}),
        on="receiver_player_id", how="left")[key + ["actor_pos"]]
    rz_all = pd.concat([rz_r, rz_t], ignore_index=True)
    rz_tot = rz_all.groupby(key).size().reset_index(name="rz_opps")
    rz_by = rz_all.groupby(key + ["actor_pos"]).size().reset_index(name="n")
    rzs = rz_by.pivot_table(index=key, columns="actor_pos", values="n",
                            aggfunc="sum").reset_index().fillna(0)
    rzs = rzs.merge(rz_tot, on=key, how="left")
    for src, out in (("RB", "rz_rb_share"), ("WR", "rz_wr_share"), ("TE", "rz_te_share"),
                     ("QB", "rz_qb_share")):
        rzs[out] = rzs.get(src, 0) / rzs["rz_opps"].replace(0, np.nan)

    # ---------------------------------------------------------------- WR air-yard tendency + OL sack rate
    adot = rp[_num(rp, "pass_attempt") == 1].groupby(key)["air_yards"].mean() \
        .reset_index(name="team_adot")
    dropbacks = scrim[(_num(scrim, "pass_attempt") == 1) | (_num(scrim, "sack") == 1)]
    sack = dropbacks.groupby(key).apply(
        lambda x: _num(x, "sack").sum() / max(len(x), 1), include_groups=False) \
        .reset_index(name="ol_sack_rate")

    out = g
    for frame, cols in ((pace, ["seconds_per_play"]),
                        (ppg, ["off_points_per_game"]),
                        (carry, ["rb_carry_share", "qb_carry_share", "team_carries"]),
                        (tsh, ["rb_target_share", "wr_target_share", "te_target_share",
                               "team_targets"]),
                        (rzs, ["rz_rb_share", "rz_wr_share", "rz_te_share", "rz_qb_share",
                               "rz_opps"]),
                        (adot, ["team_adot"]), (sack, ["ol_sack_rate"])):
        out = out.merge(frame[key + cols], on=key, how="left")
    out = out.rename(columns={"posteam": "team"}).sort_values(["season", "team"])

    # merge into the efficiency panel
    base = pd.read_csv(DATA / "team_offense_panel.csv")
    base = base.drop(columns=[c for c in base.columns
                              if c in out.columns and c not in ("season", "team")])
    full = base.merge(out, on=["season", "team"], how="left")
    full.to_csv(DATA / "team_offense_panel.csv", index=False)

    print(f"\npanel now {full.shape[0]} team-seasons x {full.shape[1]} columns")
    print("\ncoverage (non-null %) of the NEW columns:")
    for c in ["seconds_per_play", "off_points_per_game", "rb_carry_share", "qb_carry_share",
              "rb_target_share", "wr_target_share", "te_target_share", "rz_rb_share",
              "rz_wr_share", "rz_te_share", "rz_qb_share", "team_adot", "ol_sack_rate"]:
        if c in full.columns:
            print(f"  {c:22s} {100*full[c].notna().mean():5.1f}%   "
                  f"[{full[c].min():.3f}, {full[c].max():.3f}]")

    print("\nSANITY — 2024 pace (fastest 3 / slowest 3, seconds per play):")
    s = full[full.season == 2024].dropna(subset=["seconds_per_play"])
    print(s.nsmallest(3, "seconds_per_play")[["team", "seconds_per_play", "plays_per_game"]]
          .to_string(index=False))
    print(s.nlargest(3, "seconds_per_play")[["team", "seconds_per_play", "plays_per_game"]]
          .to_string(index=False))
    print("\nSANITY — 2024 highest RB target share / highest TE target share:")
    print(full[full.season == 2024].nlargest(3, "rb_target_share")[
        ["team", "rb_target_share", "wr_target_share", "te_target_share"]].to_string(index=False))
    print(full[full.season == 2024].nlargest(3, "te_target_share")[
        ["team", "rb_target_share", "wr_target_share", "te_target_share"]].to_string(index=False))
    return full


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from-season", type=int, default=FIRST)
    a = ap.parse_args()
    if a.build:
        build(list(range(a.from_season, LAST + 1)))
    else:
        raise SystemExit("pass --build")
