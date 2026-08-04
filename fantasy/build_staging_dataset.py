"""Rebuild raw_dataset + features_dataset to a STAGING path, depth block via the adapter.

Runs the exact joins of `data_pipeline.ipynb` (Parts 1-4) followed by `features.ipynb`,
except that every depth-chart / availability column comes from `depth_features`, which is
schema-aware and fail-closed. Nothing under `fantasy/` production paths is written:

    fantasy/staging/raw_dataset.staging.csv
    fantasy/staging/features_dataset.staging.csv
    fantasy/staging/depth_report.json

Usage (from fantasy/):  python build_staging_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from nfl_cache import cache_hashes, load_all  # noqa: E402
import depth_features as DF  # noqa: E402

SEASONS = list(range(2018, 2026))
COACH_SEASONS = list(range(1999, 2026))
STAGING = _HERE / "staging"
RAW_OUT = STAGING / "raw_dataset.staging.csv"
FEAT_OUT = STAGING / "features_dataset.staging.csv"
REPORT_OUT = STAGING / "depth_report.json"

#: The published features_dataset.csv was last committed at 976e94a; features.ipynb and
#: data_pipeline.ipynb both changed AFTER it (474a970, 8888d09, ef8f1d9), replacing
#: cross-season rolling windows with per-season ones. Setting this to True reproduces the
#: PRE-976e94a semantics so the published file can be reconciled column-by-column; it is a
#: diagnostic only and never used for the promoted artifact.
LEGACY_ROLLING_SEMANTICS = False


def _roll_group(cols):
    return cols[:1] if LEGACY_ROLLING_SEMANTICS else cols

TEAM_MAP = {"STL": "LA", "LAR": "LA", "OAK": "LV", "LVR": "LV",
            "SD": "LAC", "SDG": "LAC", "NWE": "NE", "KAN": "KC",
            "GNB": "GB", "NOR": "NO", "TAM": "TB", "SFO": "SF"}

FFO_FILL = ["ffo_actual_pts", "ffo_expected_pts", "ffo_pts_diff",
            "rec_attempt", "rush_attempt", "rec_yards_gained_exp",
            "rush_yards_gained_exp", "rec_touchdown_exp", "rush_touchdown_exp"]


# ── Part 1/2: base tables ─────────────────────────────────────────────────────────

def build_base(data):
    ps = data["player_stats"]
    ps = ps[(ps["season_type"] == "REG") & ps["position"].isin(DF.SKILL_POSITIONS)]
    ps_cols = [
        "player_id", "player_display_name", "position", "team", "opponent_team",
        "season", "week", "game_id", "fantasy_points", "fantasy_points_ppr",
        "completions", "attempts", "passing_yards", "passing_tds",
        "passing_interceptions", "passing_air_yards", "passing_epa",
        "carries", "rushing_yards", "rushing_tds", "rushing_fumbles_lost", "rushing_epa",
        "receptions", "targets", "receiving_yards", "receiving_tds",
        "receiving_fumbles_lost", "receiving_air_yards",
        "receiving_yards_after_catch", "receiving_epa",
        "target_share", "air_yards_share", "wopr", "racr",
    ]
    player_stats_clean = ps[ps_cols].copy()

    ffo = data["ff_opportunity"]
    ffo_clean = ffo[["player_id", "season", "week", "game_id",
                     "total_fantasy_points", "total_fantasy_points_exp",
                     "total_fantasy_points_diff", "rec_attempt", "rush_attempt",
                     "rec_yards_gained_exp", "rush_yards_gained_exp",
                     "rec_touchdown_exp", "rush_touchdown_exp"]].copy()
    ffo_clean = ffo_clean.rename(columns={
        "total_fantasy_points": "ffo_actual_pts",
        "total_fantasy_points_exp": "ffo_expected_pts",
        "total_fantasy_points_diff": "ffo_pts_diff"})

    sched = data["schedules"]
    sched = sched[sched["game_type"] == "REG"]
    cols = ["season", "week", "home_team", "away_team", "total_line", "spread_line",
            "wind", "temp", "roof", "surface", "home_rest", "away_rest"]
    home = sched[cols].copy().rename(columns={"home_team": "team", "away_team": "opponent"})
    home["implied_team_total"] = (home["total_line"] - home["spread_line"]) / 2
    home["is_home"] = 1
    home["days_rest"] = home["home_rest"]
    away = sched[["season", "week", "away_team", "home_team", "total_line", "spread_line",
                  "wind", "temp", "roof", "surface", "home_rest", "away_rest"]].copy()
    away = away.rename(columns={"away_team": "team", "home_team": "opponent"})
    away["implied_team_total"] = (away["total_line"] + away["spread_line"]) / 2
    away["is_home"] = 0
    away["days_rest"] = away["away_rest"]
    for frame in (home, away):
        frame["is_dome"] = frame["roof"].isin(["dome", "closed", "retractable"]).astype(int)
        frame["effective_wind"] = frame["wind"].fillna(0) * (1 - frame["is_dome"])
        frame["effective_temp"] = frame["temp"].where(frame["is_dome"] == 0,
                                                      other=70).fillna(65)
    vegas = pd.concat([home, away], ignore_index=True)[[
        "season", "week", "team", "implied_team_total", "is_home", "days_rest",
        "is_dome", "effective_wind", "effective_temp", "surface"]]

    for col in ("season", "week"):
        player_stats_clean[col] = player_stats_clean[col].astype(int)
        ffo_clean[col] = ffo_clean[col].astype(int)
        vegas[col] = vegas[col].astype(int)
    for frame in (player_stats_clean, ffo_clean):
        frame["game_id"] = frame["game_id"].astype(str)
        frame["player_id"] = frame["player_id"].astype(str)
    return player_stats_clean, ffo_clean, vegas


# ── Part 3/4: master rebuild ──────────────────────────────────────────────────────

def build_raw(data, tables: DF.DepthTables):
    player_stats_clean, ffo_clean, vegas = build_base(data)
    inj = DF.build_injury_scores(data["injuries"])

    df = player_stats_clean.copy()
    df = df.merge(ffo_clean.drop(columns=["game_id"]),
                  on=["player_id", "season", "week"], how="left")
    df = df.drop_duplicates(subset=["player_id", "season", "week"], keep="first")
    df = df.merge(vegas, on=["team", "season", "week"], how="left")
    df[FFO_FILL] = df[FFO_FILL].fillna(0)

    df = df.merge(
        inj[["season", "week", "player_id", "injury_status_score",
             "practice_status_score"]].drop_duplicates(
            subset=["season", "week", "player_id"], keep="first"),
        on=["season", "week", "player_id"], how="left")
    df["injury_status_score"] = df["injury_status_score"].fillna(1.0)
    df["practice_status_score"] = df["practice_status_score"].fillna(1.0)

    df = df.merge(tables.teammate_flags, on=["season", "week", "team"], how="left")
    for c in DF.TEAMMATE_FLAG_COLS:
        df[c] = df[c].fillna(1.0)

    pdr = tables.player_depth_rank.copy()
    pdr["depth_chart_position"] = pdr["depth_chart_position"].astype("Int64")
    df = df.merge(pdr, on=["season", "week", "team", "player_id", "position"], how="left")
    df["depth_chart_position"] = (df["depth_chart_position"]
                                  .fillna(DF.UNKNOWN_DEPTH_RANK).astype(int))

    df["surface"] = df["surface"].str.strip().str.lower()
    df["is_turf"] = df["surface"].isin(
        ["fieldturf", "matrixturf", "sportturf", "astroturf", "a_turf"]).astype(int)
    df = df.drop(columns=["surface"])

    df = df.merge(tables.def_flags, left_on=["season", "week", "opponent_team"],
                  right_on=["season", "week", "team"], how="left")
    df = df.drop(columns=["team_y"]).rename(columns={"team_x": "team"})
    for c in DF.DEF_FLAG_COLS:
        df[c] = df[c].fillna(1.0)

    df = df.merge(tables.ol_flags, on=["season", "week", "team"], how="left")
    for c in DF.OL_FLAG_COLS:
        df[c] = df[c].fillna(1.0)

    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    df = add_coach(df, data)
    df, pbp = add_offense(df, data)
    df = add_defense(df, pbp)
    df = add_allpro(df)
    df = add_snaps(df, data)
    return df


def add_coach(df, data):
    raw_coach = data["coach_schedules"]
    ch = raw_coach[(raw_coach["game_type"] == "REG") & raw_coach["result"].notna()].copy()
    ch["season"] = ch["season"].astype(int)
    ch["week"] = ch["week"].astype(int)
    ch["home_team"] = ch["home_team"].replace(TEAM_MAP)
    ch["away_team"] = ch["away_team"].replace(TEAM_MAP)
    home = ch[["season", "week", "home_team", "home_score", "away_score",
               "home_coach"]].rename(columns={"home_team": "team", "home_score": "team_score",
                                              "away_score": "opp_score",
                                              "home_coach": "coach"})
    away = ch[["season", "week", "away_team", "away_score", "home_score",
               "away_coach"]].rename(columns={"away_team": "team", "away_score": "team_score",
                                              "home_score": "opp_score",
                                              "away_coach": "coach"})
    g = pd.concat([home, away], ignore_index=True)
    g["win"] = (g["team_score"] > g["opp_score"]).astype(int)
    g = g.sort_values(["coach", "season", "week"]).reset_index(drop=True)
    g["cumulative_wins"] = g.groupby("coach")["win"].transform(
        lambda x: x.shift(1, fill_value=0).cumsum())
    g["cumulative_games"] = g.groupby("coach").cumcount()
    g["coach_win_pct"] = (g["cumulative_wins"] / g["cumulative_games"]).where(
        g["cumulative_games"] >= 10).round(4)
    lkp = g[g["season"].isin(SEASONS)][["season", "week", "team", "coach_win_pct"]].copy()
    df = df.drop(columns=["coach_win_pct", "opp_coach_win_pct"], errors="ignore")
    df = df.merge(lkp, on=["season", "week", "team"], how="left")
    df = df.merge(lkp.rename(columns={"team": "opponent_team",
                                      "coach_win_pct": "opp_coach_win_pct"}),
                  on=["season", "week", "opponent_team"], how="left")
    return df


def _pbp_frame(data):
    pbp = data["pbp"]
    pbp = pbp[pbp["play_type"].isin(["run", "pass"]) & pbp["posteam"].notna()].copy()
    pbp["season"] = pbp["season"].astype(int)
    pbp["week"] = pbp["week"].astype(int)
    pbp["is_pass"] = (pbp["play_type"] == "pass").astype(int)
    pbp["is_rz"] = (pbp["yardline_100"] <= 20).astype(int)
    pbp["is_rz_td"] = ((pbp["yardline_100"] <= 20) & (pbp["touchdown"] == 1)).astype(int)
    return pbp


_AGG = dict(epa_sum=("epa", "sum"), yards_sum=("yards_gained", "sum"),
            play_count=("play_id", "count"), pass_count=("is_pass", "sum"),
            rz_plays=("is_rz", "sum"), rz_tds=("is_rz_td", "sum"))


def add_offense(df, data):
    pbp = _pbp_frame(data)
    off = pbp.groupby(["season", "week", "posteam"]).agg(**_AGG).reset_index().rename(
        columns={"posteam": "team"})
    off["epa_per_play"] = off["epa_sum"] / off["play_count"]
    off["yards_per_play"] = off["yards_sum"] / off["play_count"]
    off["pass_rate"] = off["pass_count"] / off["play_count"]
    off["rz_score_rate"] = off["rz_tds"] / off["rz_plays"].replace(0, float("nan"))
    off = off.sort_values(["team", "season", "week"]).reset_index(drop=True)
    roll = {"epa_per_play": "off_epa_roll4", "yards_per_play": "off_yards_per_play_roll4",
            "pass_rate": "off_pass_rate_roll4", "rz_score_rate": "off_red_zone_rate_roll4"}
    for src, dst in roll.items():
        off[dst] = off.groupby(_roll_group(["team", "season"]))[src].transform(
            lambda x: x.shift(1).rolling(4, min_periods=1).mean())
    cols = list(roll.values())
    df = df.drop(columns=cols, errors="ignore")
    df = df.merge(off[["season", "week", "team"] + cols], on=["season", "week", "team"],
                  how="left")
    return df, pbp


def add_defense(df, pbp):
    dg = pbp.groupby(["season", "week", "defteam"]).agg(**_AGG).reset_index().rename(
        columns={"defteam": "team"})
    dg["epa_allowed_per_play"] = dg["epa_sum"] / dg["play_count"]
    dg["yards_allowed_per_play"] = dg["yards_sum"] / dg["play_count"]
    dg["pass_rate_faced"] = dg["pass_count"] / dg["play_count"]
    dg["rz_allowed_rate"] = dg["rz_tds"] / dg["rz_plays"].replace(0, float("nan"))
    dg = dg.sort_values(["team", "season", "week"]).reset_index(drop=True)
    roll = {"epa_allowed_per_play": "def_epa_allowed_roll4",
            "yards_allowed_per_play": "def_yards_allowed_roll4",
            "pass_rate_faced": "def_pass_rate_faced_roll4",
            "rz_allowed_rate": "def_red_zone_allowed_roll4"}
    for src, dst in roll.items():
        dg[dst] = dg.groupby(_roll_group(["team", "season"]))[src].transform(
            lambda x: x.shift(1).rolling(4, min_periods=1).mean())
    cols = list(roll.values())
    df = df.drop(columns=cols, errors="ignore")
    return df.merge(dg[["season", "week", "team"] + cols].rename(
        columns={"team": "opponent_team"}), on=["season", "week", "opponent_team"],
        how="left")


def add_allpro(df):
    candidates = [_HERE.parent / "betting" / "nfl_allpro_1997_2025.csv"]
    path = next(p for p in candidates if p.exists())
    allpro = pd.read_csv(path)
    allpro["Team"] = allpro["Team"].replace(TEAM_MAP)
    allpro = allpro[allpro["Team"] != "2TM"].copy()

    def build_weighted(ap):
        frames = []
        for season in SEASONS:
            curr = []
            for yrs_back, weight in zip([1, 2, 3], [4, 2, 1]):
                tmp = ap[ap["Year"] == season - yrs_back].copy()
                tmp["weight"] = weight
                tmp["season"] = season
                curr.append(tmp)
            comb = pd.concat(curr)
            dedup = comb.sort_values("weight", ascending=False).drop_duplicates(
                ["Player", "season"])
            wc = dedup.groupby(["season", "Team"])["weight"].sum().reset_index()
            wc.columns = ["season", "Team", "allpro_weighted"]
            frames.append(wc)
        return pd.concat(frames, ignore_index=True)

    w_all = build_weighted(allpro)
    w_off = build_weighted(allpro[allpro["Side"] == "offense"])
    w_def = build_weighted(allpro[allpro["Side"] == "defense"])
    new_cols = ["team_allpro_weighted", "team_offense_allpro", "team_defense_allpro",
                "opp_allpro_weighted", "opp_offense_allpro", "opp_defense_allpro"]
    df = df.drop(columns=new_cols, errors="ignore")
    for src, key, name in [(w_all, "team", "team_allpro_weighted"),
                           (w_off, "team", "team_offense_allpro"),
                           (w_def, "team", "team_defense_allpro"),
                           (w_all, "opponent_team", "opp_allpro_weighted"),
                           (w_off, "opponent_team", "opp_offense_allpro"),
                           (w_def, "opponent_team", "opp_defense_allpro")]:
        df = df.merge(src.rename(columns={"Team": key, "allpro_weighted": name}),
                      on=["season", key], how="left")
    for c in new_cols:
        df[c] = df[c].fillna(0)
    return df


def add_snaps(df, data):
    players = data["players"]
    bridge = players.loc[players["pfr_id"].notna() & players["gsis_id"].notna(),
                         ["pfr_id", "gsis_id"]].drop_duplicates()
    snap_raw = data["snap_counts"]
    snap = (snap_raw[snap_raw["game_type"] == "REG"]
            [["pfr_player_id", "season", "week", "offense_pct"]]
            .merge(bridge, left_on="pfr_player_id", right_on="pfr_id", how="left")
            .rename(columns={"gsis_id": "player_id"})
            [["player_id", "season", "week", "offense_pct"]]
            .dropna(subset=["player_id"]))
    snap["season"] = snap["season"].astype(int)
    snap["week"] = snap["week"].astype(int)
    snap = snap.sort_values(["player_id", "season", "week"])
    snap["snap_pct_roll3"] = snap.groupby(["player_id", "season"])["offense_pct"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    snap["snap_pct_roll5"] = snap.groupby(["player_id", "season"])["offense_pct"].transform(
        lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    snap["snap_pct_trend"] = snap["snap_pct_roll3"] - snap["snap_pct_roll5"]
    cols = ["snap_pct_roll3", "snap_pct_roll5", "snap_pct_trend"]
    df = df.drop(columns=cols, errors="ignore")
    df = df.merge(snap[["player_id", "season", "week"] + cols],
                  on=["player_id", "season", "week"], how="left")
    df[cols] = df[cols].fillna(0)
    return df


# ── features.ipynb ────────────────────────────────────────────────────────────────

ROLL_COLS = ["fantasy_points_half_ppr", "targets", "receptions", "receiving_yards",
             "receiving_tds", "carries", "rushing_yards", "rushing_tds", "target_share",
             "air_yards_share", "wopr", "receiving_air_yards",
             "receiving_yards_after_catch", "ffo_expected_pts", "ffo_pts_diff"]
TREND_COLS = ["fantasy_points_half_ppr", "targets", "target_share", "air_yards_share",
              "wopr", "carries"]

FEATURE_COLS = [
    "player_id", "player_display_name", "position", "team", "opponent_team",
    "season", "week",
    "fantasy_points_half_ppr_roll3", "targets_roll3", "receptions_roll3",
    "receiving_yards_roll3", "receiving_tds_roll3", "carries_roll3",
    "rushing_yards_roll3", "rushing_tds_roll3", "target_share_roll3",
    "air_yards_share_roll3", "wopr_roll3", "receiving_air_yards_roll3",
    "receiving_yards_after_catch_roll3", "ffo_expected_pts_roll3", "ffo_pts_diff_roll3",
    "fantasy_points_half_ppr_roll5", "targets_roll5", "receptions_roll5",
    "receiving_yards_roll5", "receiving_tds_roll5", "carries_roll5",
    "rushing_yards_roll5", "rushing_tds_roll5", "target_share_roll5",
    "air_yards_share_roll5", "wopr_roll5", "receiving_air_yards_roll5",
    "receiving_yards_after_catch_roll5", "ffo_expected_pts_roll5", "ffo_pts_diff_roll5",
    "fantasy_points_half_ppr_trend", "targets_trend", "target_share_trend",
    "air_yards_share_trend", "wopr_trend", "carries_trend",
    "snap_pct_roll3", "snap_pct_roll5", "snap_pct_trend",
    "def_pts_allowed_roll4", "implied_team_total", "total_line", "team_spread", "is_home",
    "opp_season_win_pct", "opp_win_pct_roll4", "off_epa_rank", "sos_rank",
    "coach_win_pct", "opp_coach_win_pct", "is_new_coach", "opp_is_new_coach",
    "off_epa_roll4", "off_yards_per_play_roll4", "off_pass_rate_roll4",
    "off_red_zone_rate_roll4",
    "def_epa_allowed_roll4", "def_yards_allowed_roll4", "def_pass_rate_faced_roll4",
    "def_red_zone_allowed_roll4",
    "team_allpro_weighted", "team_offense_allpro", "team_defense_allpro",
    "opp_allpro_weighted", "opp_offense_allpro", "opp_defense_allpro",
    "days_rest", "is_dome", "effective_wind", "effective_temp", "is_turf",
    "injury_status_score", "practice_status_score",
] + DF.TEAMMATE_FLAG_COLS + ["depth_chart_position"] + DF.DEF_FLAG_COLS + DF.OL_FLAG_COLS \
  + ["target_half_ppr"]


def build_features(df, data):
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    df["fantasy_points_half_ppr"] = df["fantasy_points"] + 0.5 * df["receptions"]
    df["target_half_ppr"] = df.groupby(["player_id", "season"])[
        "fantasy_points_half_ppr"].shift(-1)

    for col in ROLL_COLS:
        g = df.groupby(_roll_group(["player_id", "season"]))[col]
        df[f"{col}_roll3"] = g.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
        df[f"{col}_roll5"] = g.transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    for col in TREND_COLS:
        df[f"{col}_trend"] = df[f"{col}_roll3"] - df[f"{col}_roll5"]

    pts_allowed = (df.groupby(["season", "week", "opponent_team", "position"])
                   ["fantasy_points_half_ppr"].sum().reset_index()
                   .rename(columns={"opponent_team": "team",
                                    "fantasy_points_half_ppr": "pts_scored_vs_team"}))
    pts_allowed = pts_allowed.sort_values(["team", "position", "season", "week"])
    pts_allowed["def_pts_allowed_roll4"] = (
        pts_allowed.groupby(["team", "position"] if LEGACY_ROLLING_SEMANTICS
                            else ["team", "position", "season"])["pts_scored_vs_team"]
        .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean()))
    df = df.merge(pts_allowed[["season", "week", "team", "position",
                               "def_pts_allowed_roll4"]],
                  left_on=["season", "week", "opponent_team", "position"],
                  right_on=["season", "week", "team", "position"], how="left")
    df = df.drop(columns=["team_y"]).rename(columns={"team_x": "team"})

    _cm = df if LEGACY_ROLLING_SEMANTICS else df[df["season"] <= 2024]
    coach_median = _cm["coach_win_pct"].median()
    opp_coach_median = _cm["opp_coach_win_pct"].median()
    df["is_new_coach"] = df["coach_win_pct"].isna().astype(int)
    df["opp_is_new_coach"] = df["opp_coach_win_pct"].isna().astype(int)
    df["coach_win_pct"] = df["coach_win_pct"].fillna(coach_median)
    df["opp_coach_win_pct"] = df["opp_coach_win_pct"].fillna(opp_coach_median)

    sched_raw = data["schedules"]
    sched = sched_raw[sched_raw["game_type"] == "REG"][
        ["season", "week", "home_team", "away_team", "home_score", "away_score"]
    ].dropna(subset=["home_score", "away_score"]).copy()
    tmap = {"OAK": "LV", "SD": "LAC", "STL": "LA", "JAC": "JAX", "ARZ": "ARI",
            "BLT": "BAL", "CLV": "CLE", "HST": "HOU"}
    sched["home_team"] = sched["home_team"].replace(tmap)
    sched["away_team"] = sched["away_team"].replace(tmap)
    home = sched[["season", "week", "home_team", "home_score", "away_score"]].copy()
    home["team"] = home["home_team"]
    home["win"] = (home["home_score"] > home["away_score"]).astype(int)
    away = sched[["season", "week", "away_team", "home_score", "away_score"]].copy()
    away["team"] = away["away_team"]
    away["win"] = (away["away_score"] > away["home_score"]).astype(int)
    rec = pd.concat([home[["season", "week", "team", "win"]],
                     away[["season", "week", "team", "win"]]]).sort_values(
        ["team", "season", "week"]).reset_index(drop=True)
    rec["cum_wins"] = rec.groupby(["team", "season"])["win"].cumsum()
    rec["cum_games"] = rec.groupby(["team", "season"]).cumcount() + 1
    rec["win_pct"] = ((rec["cum_wins"] - rec["win"]) / (rec["cum_games"] - 1)).fillna(0.5)
    opp_wp = rec[["season", "week", "team", "win_pct"]].rename(
        columns={"team": "opponent_team", "win_pct": "opp_season_win_pct"})
    df = df.merge(opp_wp, on=["season", "week", "opponent_team"], how="left")
    df["opp_season_win_pct"] = df["opp_season_win_pct"].fillna(0.5)

    team_sos = (df.drop_duplicates(subset=["team", "season", "week"])
                [["team", "season", "week", "opp_season_win_pct"]]
                .sort_values(["team", "season", "week"]).copy())
    team_sos["opp_win_pct_roll4"] = team_sos.groupby(["team", "season"])[
        "opp_season_win_pct"].transform(
        lambda x: x.shift(1).rolling(4, min_periods=1).mean())
    team_sos["opp_win_pct_roll4"] = team_sos["opp_win_pct_roll4"].fillna(0.5)
    df = df.merge(team_sos[["team", "season", "week", "opp_win_pct_roll4"]],
                  on=["team", "season", "week"], how="left")

    sh = sched_raw[sched_raw["game_type"] == "REG"][
        ["season", "week", "home_team", "spread_line", "total_line"]].copy()
    sh = sh.rename(columns={"home_team": "team"})
    sh["team_spread"] = sh["spread_line"]
    sa = sched_raw[sched_raw["game_type"] == "REG"][
        ["season", "week", "away_team", "spread_line", "total_line"]].copy()
    sa = sa.rename(columns={"away_team": "team"})
    sa["team_spread"] = -sa["spread_line"]
    spread_ctx = pd.concat([sh, sa], ignore_index=True)[
        ["season", "week", "team", "total_line", "team_spread"]]
    df = df.drop(columns=["total_line", "team_spread"], errors="ignore")
    df = df.merge(spread_ctx, on=["season", "week", "team"], how="left")
    df["total_line"] = df["total_line"].fillna(
        (df if LEGACY_ROLLING_SEMANTICS else df[df["season"] <= 2024])["total_line"].median())
    df["team_spread"] = df["team_spread"].fillna(0.0)

    team_week = df.groupby(["team", "season", "week"])[
        ["off_epa_roll4", "opp_win_pct_roll4"]].mean().reset_index()
    team_week["off_epa_rank"] = team_week.groupby(["season", "week"])["off_epa_roll4"].rank(
        ascending=False, method="min", na_option="bottom").astype("Int64")
    team_week["sos_rank"] = team_week.groupby(["season", "week"])["opp_win_pct_roll4"].rank(
        ascending=False, method="min", na_option="bottom").astype("Int64")
    df = df.merge(team_week[["team", "season", "week", "off_epa_rank", "sos_rank"]],
                  on=["team", "season", "week"], how="left")

    model = df[df["target_half_ppr"].notna()].copy()
    model = model[model["fantasy_points_half_ppr_roll3"].notna()].copy()
    missing = [c for c in FEATURE_COLS if c not in model.columns]
    if missing:
        raise RuntimeError(f"feature columns missing from the staging build: {missing}")
    return model[FEATURE_COLS].copy()


def main(legacy_replica: bool = False):
    global LEGACY_ROLLING_SEMANTICS
    LEGACY_ROLLING_SEMANTICS = legacy_replica
    feat_out = (STAGING / "features_dataset.legacyreplica.csv") if legacy_replica \
        else FEAT_OUT
    raw_out = (STAGING / "raw_dataset.legacyreplica.csv") if legacy_replica else RAW_OUT
    STAGING.mkdir(parents=True, exist_ok=True)
    print(f"Loading nflverse inputs ... (legacy_replica={legacy_replica})")
    data = load_all(SEASONS, COACH_SEASONS)

    print("Building depth tables via depth_features / depth_adapter ...")
    tables = DF.build_depth_tables(data["depth_charts"], data["schedules"],
                                   data["injuries"], SEASONS)
    print(json.dumps(tables.report["snapshot_check"], indent=1))

    print("Building raw dataset ...")
    raw = build_raw(data, tables)
    raw.to_csv(raw_out, index=False)
    print(f"  {raw_out.name}: {raw.shape[0]:,} x {raw.shape[1]}")

    print("Building features dataset ...")
    feats = build_features(raw, data)
    feats.to_csv(feat_out, index=False)
    print(f"  {feat_out.name}: {feats.shape[0]:,} x {feats.shape[1]}")

    if legacy_replica:
        return
    report = dict(tables.report)
    report["input_hashes"] = cache_hashes()
    report["raw_shape"] = list(raw.shape)
    report["features_shape"] = list(feats.shape)
    REPORT_OUT.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"  {REPORT_OUT.name} written")


if __name__ == "__main__":
    main(legacy_replica="--legacy-replica" in sys.argv)
