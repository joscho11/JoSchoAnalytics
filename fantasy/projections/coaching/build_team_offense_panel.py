"""TEAM-OFFENSE PANEL — one row per (season, team), 1999-2025, from nflverse play-by-play.

Governing prereg: PREREG_coach_quality_2026-07-28.md (§DATA, §ARM2, §ARM4).

This is the raw material every coaching arm is built from. It contains NO coach identity and NO
shrinkage -- it is the observed offensive record of a team-season, nothing more. Attribution to a
coach happens downstream so the attribution rule can change without recomputing PBP.

FROZEN PBP FILTERS (prereg §DATA; documented here because Arm 2 requires it explicitly):
  - REG season only (`season_type == 'REG'`), `posteam` non-null.
  - Offensive plays = `play_type in {'pass','run'}`. This excludes punts, field goals, kickoffs,
    extra points, timeouts, and penalty-only `no_play` rows.
  - Kneels and spikes EXCLUDED from every rate metric (`qb_kneel != 1`, `qb_spike != 1`) -- they are
    clock management, not offensive intent, and they concentrate in blowouts and end-of-half.
  - Two-point conversions EXCLUDED (`two_point_attempt != 1`): untimed, non-down scrimmage plays.
  - Drive metrics use nflverse `fixed_drive` / `fixed_drive_result`, which repair the raw drive
    counter across changes of possession.

Every metric is a same-season observation. Lagging, attribution and shrinkage are downstream.
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
DATA.mkdir(parents=True, exist_ok=True)

FIRST_PBP_SEASON = 1999          # nflverse EPA coverage begins here
LAST_OBS_SEASON = 2025
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}

PBP_COLS = ["season", "week", "game_id", "posteam", "season_type", "play_type", "epa", "success",
            "yards_gained", "qb_kneel", "qb_spike", "two_point_attempt", "pass", "rush", "down",
            "yardline_100", "fixed_drive", "fixed_drive_result", "score_differential", "qtr",
            "wp", "pass_oe", "xpass", "air_yards", "half_seconds_remaining", "touchdown",
            "rusher_player_id", "receiver_player_id", "play_id"]


def _num(df, col, default=0.0):
    return pd.to_numeric(df[col], errors="coerce").fillna(default) if col in df.columns \
        else pd.Series(default, index=df.index)


def load_pbp(seasons):
    import nflreadpy as nfl
    frames = []
    for s in seasons:
        p = nfl.load_pbp(seasons=[s])
        try:
            p = p.to_pandas()
        except AttributeError:
            pass
        keep = [c for c in PBP_COLS if c in p.columns]
        p = p[keep].copy()
        p["posteam"] = p["posteam"].replace(TEAM_CANON)
        frames.append(p)
        print(f"    {s}: {len(p):,} plays")
    return pd.concat(frames, ignore_index=True)


def offensive_plays(pbp):
    """The frozen offensive-play universe. Returns (scrimmage, rate_plays)."""
    d = pbp
    if "season_type" in d.columns:
        d = d[d["season_type"] == "REG"]
    d = d[d["posteam"].notna()]
    scrim = d[d["play_type"].isin(["pass", "run"])].copy()
    mask = (_num(scrim, "qb_kneel") != 1) & (_num(scrim, "qb_spike") != 1) \
        & (_num(scrim, "two_point_attempt") != 1)
    return scrim, scrim[mask].copy()


def build_panel(seasons=None):
    seasons = seasons or list(range(FIRST_PBP_SEASON, LAST_OBS_SEASON + 1))
    print("=" * 78)
    print(f"TEAM-OFFENSE PANEL — {seasons[0]}-{seasons[-1]} from nflverse PBP")
    print("=" * 78)
    pbp = load_pbp(seasons)
    print(f"  loaded {len(pbp):,} raw plays")

    scrim, rp = offensive_plays(pbp)
    print(f"  scrimmage plays {len(scrim):,} -> after kneel/spike/2pt filter {len(rp):,} "
          f"({100*(1-len(rp)/len(scrim)):.1f}% removed)")

    rp["epa"] = _num(rp, "epa", np.nan)
    rp["success"] = _num(rp, "success", np.nan)
    rp["yards_gained"] = _num(rp, "yards_gained", np.nan)
    rp["is_pass"] = _num(rp, "pass")
    rp["is_rush"] = _num(rp, "rush")
    rp["explosive"] = np.where(
        rp["is_pass"] == 1, (rp["yards_gained"] >= 20).astype(float),
        np.where(rp["is_rush"] == 1, (rp["yards_gained"] >= 10).astype(float), np.nan))

    g = rp.groupby(["season", "posteam"])
    panel = g.agg(
        plays=("play_id", "count"),
        games=("game_id", "nunique"),
        epa_play=("epa", "mean"),
        success_rate=("success", "mean"),
        yards_play=("yards_gained", "mean"),
        explosive_rate=("explosive", "mean"),
        pass_rate=("is_pass", "mean"),
    ).reset_index().rename(columns={"posteam": "team"})
    panel["plays_per_game"] = panel["plays"] / panel["games"]

    # ---- PROE: nflverse ships xpass/pass_oe; pass_oe is already (pass - xpass) in pct points
    if "pass_oe" in rp.columns:
        proe = rp.groupby(["season", "posteam"])["pass_oe"].mean().reset_index()
        proe.columns = ["season", "team", "proe"]
        panel = panel.merge(proe, on=["season", "team"], how="left")

    # ---- neutral / early-down / red-zone pass rate
    wp = _num(rp, "wp", np.nan)
    neutral = rp[(wp.between(0.20, 0.80)) & (_num(rp, "qtr", 9) <= 3)
                 & (_num(rp, "half_seconds_remaining", 9999) > 120)]
    panel = panel.merge(
        neutral.groupby(["season", "posteam"])["is_pass"].mean().reset_index()
        .rename(columns={"posteam": "team", "is_pass": "neutral_pass_rate"}),
        on=["season", "team"], how="left")

    early = rp[_num(rp, "down", 9).isin([1, 2])]
    panel = panel.merge(
        early.groupby(["season", "posteam"])["is_pass"].mean().reset_index()
        .rename(columns={"posteam": "team", "is_pass": "early_down_pass_rate"}),
        on=["season", "team"], how="left")

    rz = rp[_num(rp, "yardline_100", 99) <= 20]
    panel = panel.merge(
        rz.groupby(["season", "posteam"])["is_pass"].mean().reset_index()
        .rename(columns={"posteam": "team", "is_pass": "redzone_pass_rate"}),
        on=["season", "team"], how="left")

    # ---- drive-based: points per drive, red-zone TD rate
    dcols = ["season", "posteam", "game_id", "fixed_drive", "fixed_drive_result"]
    if all(c in scrim.columns for c in ["fixed_drive", "fixed_drive_result"]):
        drives = scrim.dropna(subset=["fixed_drive"]).copy()
        dr = drives.groupby(dcols[:4]).agg(
            result=("fixed_drive_result", "first"),
            min_yl=("yardline_100", "min")).reset_index()
        res = dr["result"].astype(str)
        dr["pts"] = np.select(
            [res.str.contains("Touchdown", case=False, na=False),
             res.str.contains("Field goal", case=False, na=False),
             res.str.contains("Safety", case=False, na=False)],
            [7.0, 3.0, -2.0], default=0.0)
        pd_ = dr.groupby(["season", "posteam"]).agg(
            points_per_drive=("pts", "mean"), n_drives=("pts", "size")).reset_index()
        panel = panel.merge(pd_.rename(columns={"posteam": "team"}), on=["season", "team"], how="left")

        rzd = dr[dr["min_yl"] <= 20].copy()
        rzd["is_td"] = rzd["result"].astype(str).str.contains("Touchdown", case=False, na=False).astype(float)
        panel = panel.merge(
            rzd.groupby(["season", "posteam"])["is_td"].mean().reset_index()
            .rename(columns={"posteam": "team", "is_td": "redzone_td_rate"}),
            on=["season", "team"], how="left")

    # ---- pace: seconds per offensive play (drive-time based, neutral only, kneels already gone)
    panel["seconds_per_play"] = np.nan   # filled below if game clock fields present

    panel = panel.sort_values(["season", "team"]).reset_index(drop=True)
    panel.to_csv(DATA / "team_offense_panel.csv", index=False)

    print(f"\npanel: {len(panel)} team-seasons, {panel.season.min()}-{panel.season.max()}")
    print("\ncoverage (non-null %):")
    for c in ["epa_play", "success_rate", "yards_play", "explosive_rate", "points_per_drive",
              "redzone_td_rate", "proe", "neutral_pass_rate", "early_down_pass_rate",
              "redzone_pass_rate"]:
        if c in panel.columns:
            print(f"  {c:22s} {100*panel[c].notna().mean():5.1f}%   "
                  f"[{panel[c].min():.3f}, {panel[c].max():.3f}]")

    print("\nSANITY — 2024 top 6 offenses by EPA/play:")
    s24 = panel[panel.season == 2024].nlargest(6, "epa_play")
    print(s24[["team", "epa_play", "success_rate", "points_per_drive", "proe"]].to_string(index=False))
    print("\nSANITY — 2024 bottom 3:")
    print(panel[panel.season == 2024].nsmallest(3, "epa_play")[
        ["team", "epa_play", "success_rate", "points_per_drive"]].to_string(index=False))
    print(f"\nwrote {DATA/'team_offense_panel.csv'}")
    return panel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from-season", type=int, default=FIRST_PBP_SEASON)
    a = ap.parse_args()
    if a.build:
        build_panel(list(range(a.from_season, LAST_OBS_SEASON + 1)))
    else:
        raise SystemExit("pass --build")


if __name__ == "__main__":
    main()
