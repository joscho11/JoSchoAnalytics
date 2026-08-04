"""Shared 85-feature engineering pipeline — the single source of truth.

This module is the production source of truth for the spread feature pipeline
(Groups 1-10), imported by:
  - betting/predict_betting.ipynb  (build_features, build_numeric_features, PROD_FEATURES_35)
  - betting/model_comparison.ipynb (constants + pure helpers)
  - betting/test_features.py        (hermetic synthetic-data tests, run in CI)

It was extracted verbatim from the former betting/features.ipynb so notebook
storage quirks (corruption, ensure_ascii drift) can no longer affect production.
Edit feature logic HERE; the notebook is now a thin documentation wrapper.

Public surface: build_features, build_numeric_features, the per-group _build_*
helpers, FEATURE_COLS_85, PROD_FEATURES_35, TEAM_MAP, norm_name,
canonicalize_ngs_team.

NOTE: list order is a contract. PROD_FEATURES_35 order determines training-matrix
column order which determines pkl bytes. The order-hash test in test_features.py
locks the canonical order — if you intentionally change a list, retrain the pkls
and update the expected hash in the same commit.
"""

# ============================================================================
# Imports
# ============================================================================
import re
import unicodedata
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import nflreadpy as nfl

# Canonical All-Pro player identity (2026-08-03). The source CSV has no player ID and two
# distinct players share the name "C.J. Mosley"; keying on the name merged them and the
# survivor depended on pandas' unstable default sort. See betting/allpro_identity.py.
from allpro_identity import (AllProIdentityError, injured_allpro_weight,
                             resolve_allpro_identities, weighted_lookback)

# ============================================================================
# Constants
# ============================================================================
TEAM_MAP = {
    # Modern moves
    "STL": "LA",  "LAR": "LA",   "OAK": "LV",  "LVR": "LV",
    "SD":  "LAC", "SDG": "LAC",
    # Pro-Football-Reference 3-letter codes → schedule 2-letter codes
    "NWE": "NE",  "KAN": "KC",   "GNB": "GB",  "NOR": "NO",
    "TAM": "TB",  "SFO": "SF",
    # Pre-2002 / alternate abbreviations in historical AllPro CSV
    "ARZ": "ARI", "BLT": "BAL",  "CLV": "CLE", "HST": "HOU", "JAC": "JAX",
}

FEATURE_COLS_85 = [
    "roof",
    "surface",
    "spread_line",
    "away_rest",
    "home_rest",
    "total_line",
    "div_game",
    "home_rolling_avg_epa",
    "home_rolling_avg_yards",
    "home_rolling_play_count",
    "away_rolling_avg_epa",
    "away_rolling_avg_yards",
    "away_rolling_play_count",
    "home_rolling_allowed_avg_epa",
    "home_rolling_allowed_avg_yards",
    "home_rolling_allowed_play_count",
    "away_rolling_allowed_avg_epa",
    "away_rolling_allowed_avg_yards",
    "away_rolling_allowed_play_count",
    "epa_home_off_away_def_rolling_diff",
    "epa_home_def_away_off_rolling_diff",
    "avg_yards_home_off_away_def_rolling_diff",
    "avg_yards_home_def_away_off_rolling_diff",
    "play_count_home_off_away_def_rolling_diff",
    "play_count_home_def_away_off_rolling_diff",
    "home_recent_sos_opponent_avg",
    "home_season_sos_opponent_avg",
    "away_recent_sos_opponent_avg",
    "away_season_sos_opponent_avg",
    "sos_diff",
    "season_sos_diff",
    "home_allpro_last_3_years_weighted",
    "away_allpro_last_3_years_weighted",
    "diff_allpro_last_3_years_weighted",
    "home_allpro_prev_year",
    "away_allpro_prev_year",
    "diff_allpro_prev_year",
    "home_offense_allpro_3_years",
    "away_offense_allpro_3_years",
    "home_defense_allpro_3_years",
    "away_defense_allpro_3_years",
    "allpro_diff_home_off_away_def_3_years",
    "allpro_diff_home_def_away_off_3_years ",  # trailing space matches model
    "home_offense_allpro_prev_year",
    "away_offense_allpro_prev_year",
    "home_defense_allpro_prev_year",
    "away_defense_allpro_prev_year",
    "allpro_diff_home_off_away_def_prev_year",
    "allpro_diff_home_def_away_off_prev_year",
    "league_rolling_avg_abs_margin_by_week",
    "home_pr_prev_year",
    "away_pr_prev_year",
    "diff_pr_prev_year",
    "home_cpae_prev_year",
    "away_cpae_prev_year",
    "diff_cpae_prev_year",
    "home_time_to_throw_prev_year",
    "away_time_to_throw_prev_year",
    "diff_time_to_throw_prev_year",
    "home_injured_count",
    "away_injured_count",
    "diff_injured_count",
    "diff_active_allpro_weighted",
    "diff_active_allpro_prev_year",
    "home_rolling_win_pct",
    "away_rolling_win_pct",
    "sack_diff",
    "sack_diff_reverse",
    "turnover_diff",
    "turnover_diff_reverse",
    "third_down_diff",
    "third_down_diff_reverse",
    "cover_rate_diff",
    "scoring_diff",
    "scoring_diff_reverse",
    "home_coach_win_pct_prior",
    "away_coach_win_pct_prior",
    "home_coach_win_pct_roll3",
    "away_coach_win_pct_roll3",
    "is_playoff",
    "is_final_week",
    "home_qb_switch",
    "away_qb_switch",
    "is_home_qb_new",
    "is_away_qb_new",
]

# Top-35 subset, in the order produced by the ablation study
# (descending importance: combined XGB gain + Ridge |coef| + LGB gain).
# Do NOT reorder — column order determines X_tr column order, which
# determines model coefficients. Same set, different order ⇒ different pkl.
PROD_FEATURES_35 = [
    "spread_line",
    "sack_diff",
    "sack_diff_reverse",
    "scoring_diff",
    "home_coach_win_pct_roll3",
    "scoring_diff_reverse",
    "home_coach_win_pct_prior",
    "away_rolling_allowed_play_count",
    "away_rolling_allowed_avg_yards",
    "home_rolling_win_pct",
    "diff_active_allpro_weighted",
    "epa_home_off_away_def_rolling_diff",
    "diff_active_allpro_prev_year",
    "away_season_sos_opponent_avg",
    "diff_allpro_last_3_years_weighted",
    "allpro_diff_home_off_away_def_3_years",
    "home_defense_allpro_prev_year",
    "away_offense_allpro_prev_year",
    "season_sos_diff",
    "third_down_diff",
    "epa_home_def_away_off_rolling_diff",
    "is_playoff",
    "play_count_home_def_away_off_rolling_diff",
    "home_allpro_last_3_years_weighted",
    "away_rolling_avg_yards",
    "home_rolling_allowed_avg_epa",
    "away_defense_allpro_3_years",
    "away_coach_win_pct_prior",
    "home_recent_sos_opponent_avg",
    "away_pr_prev_year",
    "away_rolling_avg_epa",
    "away_injured_count",
    "home_rolling_play_count",
    "avg_yards_home_off_away_def_rolling_diff",
    "allpro_diff_home_off_away_def_prev_year",
]

# ============================================================================
# Helper — `norm_name`
# ============================================================================
def norm_name(s):
    """Strip suffixes (Jr/Sr/II/III/IV/V), punctuation, accents; lowercase."""
    if not isinstance(s, str):
        return ""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    s = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$", "", s)
    s = re.sub(r"[\'.\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# Underscore-prefixed alias retained for any code that referenced the old name.
_norm_name = norm_name

# ============================================================================
# Helper — `canonicalize_ngs_team`
# ============================================================================
def canonicalize_ngs_team(team_abbr, season):
    """NGS uses modern abbreviations (LAR/LV/LAC) for historical seasons;
    map them back to the schedule's per-season convention."""
    if team_abbr == "LAR":
        return "LA"
    if team_abbr == "LV":
        return "OAK" if season < 2020 else "LV"
    if team_abbr == "LAC":
        return "SD" if season < 2017 else "LAC"
    return team_abbr

# ============================================================================
# Group 1 — `_build_schedule_context`
# ============================================================================
def _build_schedule_context(upcoming, full_schedule, target_week):
    """Group 1: roof, surface, is_playoff, is_final_week."""
    upcoming["is_playoff"] = (upcoming["game_type"] != "REG")
    final_week_num = full_schedule[full_schedule["game_type"] == "REG"]["week"].max()
    upcoming["is_final_week"] = (
        (upcoming["game_type"] == "REG") & (upcoming["week"] == final_week_num)
    )
    if upcoming["is_playoff"].any():
        print(f"  ⚠️  Week {target_week} contains playoff games — models were trained on REG season only")
    return upcoming

# ============================================================================
# Group 2 — `_build_rolling_pbp`
# ============================================================================
def _build_rolling_pbp(upcoming, pbp_s, wk_lookup):
    """Group 2: rolling EPA, yards/play, play count (5-game windows)."""
    off_stats = (
        pbp_s.groupby(["game_id", "posteam"])
        .agg(avg_epa=("epa", "mean"), avg_yards=("yards_gained", "mean"), play_count=("play_id", "count"))
        .reset_index().rename(columns={"posteam": "team"})
    )
    off_stats = off_stats.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left")
    off_stats = off_stats.sort_values(["team", "season", "week"])
    for feat in ["avg_epa", "avg_yards", "play_count"]:
        off_stats[f"rolling_{feat}"] = (
            off_stats.groupby("team")[feat]
            .transform(lambda x: x.rolling(5, min_periods=1).mean())
        )

    def_stats = (
        pbp_s.groupby(["game_id", "defteam"])
        .agg(allowed_avg_epa=("epa", "mean"), allowed_avg_yards=("yards_gained", "mean"), allowed_play_count=("play_id", "count"))
        .reset_index().rename(columns={"defteam": "team"})
    )
    def_stats = def_stats.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left")
    def_stats = def_stats.sort_values(["team", "season", "week"])
    for feat in ["allowed_avg_epa", "allowed_avg_yards", "allowed_play_count"]:
        def_stats[f"rolling_{feat}"] = (
            def_stats.groupby("team")[feat]
            .transform(lambda x: x.rolling(5, min_periods=1).mean())
        )

    latest_off = off_stats.groupby("team").nth(-1).reset_index()
    latest_def = def_stats.groupby("team").nth(-1).reset_index()

    for side, df in [("home_team", latest_off), ("away_team", latest_off)]:
        prefix = "home_" if side == "home_team" else "away_"
        cols = [c for c in df.columns if c.startswith("rolling_")]
        upcoming = upcoming.merge(
            df[["team"] + cols].rename(columns={"team": side, **{c: f"{prefix}{c}" for c in cols}}),
            on=side, how="left"
        )
    for side, df in [("home_team", latest_def), ("away_team", latest_def)]:
        prefix = "home_" if side == "home_team" else "away_"
        cols = [c for c in df.columns if c.startswith("rolling_")]
        upcoming = upcoming.merge(
            df[["team"] + cols].rename(columns={"team": side, **{c: f"{prefix}{c}" for c in cols}}),
            on=side, how="left"
        )

    upcoming["epa_home_off_away_def_rolling_diff"]        = upcoming["home_rolling_avg_epa"]            - upcoming["away_rolling_allowed_avg_epa"]
    upcoming["epa_home_def_away_off_rolling_diff"]        = upcoming["home_rolling_allowed_avg_epa"]    - upcoming["away_rolling_avg_epa"]
    upcoming["avg_yards_home_off_away_def_rolling_diff"]  = upcoming["home_rolling_avg_yards"]          - upcoming["away_rolling_allowed_avg_yards"]
    upcoming["avg_yards_home_def_away_off_rolling_diff"]  = upcoming["home_rolling_allowed_avg_yards"]  - upcoming["away_rolling_avg_yards"]
    upcoming["play_count_home_off_away_def_rolling_diff"] = upcoming["home_rolling_play_count"]         - upcoming["away_rolling_allowed_play_count"]
    upcoming["play_count_home_def_away_off_rolling_diff"] = upcoming["home_rolling_allowed_play_count"] - upcoming["away_rolling_play_count"]
    return upcoming

# ============================================================================
# Groups 3 & 5 — `_build_sos_and_performance`
# ============================================================================
def _build_sos_and_performance(upcoming, _hist_rolling, history, week_margin_lkp):
    """Groups 3+5: SOS, rolling win%, scoring, cover rate, league margin.

    Combined because Group 5 builds on the long_df constructed in Group 3.
    """
    # ── Build shared long-format team-game DataFrame ──────────────────────────
    home_g = _hist_rolling[["season", "week", "home_team", "away_team", "home_score", "away_score"]].copy()
    home_g.columns = ["season", "week", "team", "opponent", "team_score", "opp_score"]
    away_g = _hist_rolling[["season", "week", "away_team", "home_team", "away_score", "home_score"]].copy()
    away_g.columns = ["season", "week", "team", "opponent", "team_score", "opp_score"]
    long_df = pd.concat([home_g, away_g]).sort_values(["team", "season", "week"])
    long_df["team_win"] = (long_df["team_score"] > long_df["opp_score"]).astype(int)

    # ── Group 3 — SOS ────────────────────────────────────────────────────────
    long_df["win_pct"] = long_df.groupby("team")["team_win"].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    opp_wp = long_df[["season", "week", "team", "win_pct"]].copy()
    opp_wp.columns = ["season", "week", "opponent", "opponent_win_pct"]
    long_df = long_df.merge(opp_wp, on=["season", "week", "opponent"], how="left")
    long_df["recent_sos"] = long_df.groupby("team")["opponent_win_pct"].transform(
        lambda x: x.rolling(3, min_periods=1).mean().fillna(0)
    )
    # Accumulates across seasons in long_df (target_season-1 + current games) — name matches
    # production model feature exactly; do not rename without retraining.
    long_df["season_sos"] = long_df.groupby("team")["opponent_win_pct"].transform(
        lambda x: x.expanding().mean().fillna(0)
    )
    latest_sos = long_df.groupby("team").nth(-1).reset_index()[["team", "recent_sos", "season_sos"]]
    upcoming = upcoming.merge(latest_sos.rename(columns={"team": "home_team", "recent_sos": "home_recent_sos_opponent_avg", "season_sos": "home_season_sos_opponent_avg"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_sos.rename(columns={"team": "away_team", "recent_sos": "away_recent_sos_opponent_avg", "season_sos": "away_season_sos_opponent_avg"}), on="away_team", how="left")
    for col in ["home_recent_sos_opponent_avg", "home_season_sos_opponent_avg", "away_recent_sos_opponent_avg", "away_season_sos_opponent_avg"]:
        upcoming[col] = upcoming[col].fillna(0)
    upcoming["sos_diff"]        = upcoming["home_recent_sos_opponent_avg"] - upcoming["away_recent_sos_opponent_avg"]
    upcoming["season_sos_diff"] = upcoming["home_season_sos_opponent_avg"] - upcoming["away_season_sos_opponent_avg"]

    # ── Group 5 — rolling win%, scoring, cover rate, league margin ────────────
    long_df["rolling_win_pct"] = long_df.groupby("team")["team_win"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    latest_wp = long_df.groupby("team").nth(-1).reset_index()[["team", "rolling_win_pct"]]
    upcoming = upcoming.merge(latest_wp.rename(columns={"team": "home_team", "rolling_win_pct": "home_rolling_win_pct"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_wp.rename(columns={"team": "away_team", "rolling_win_pct": "away_rolling_win_pct"}), on="away_team", how="left")

    long_df["rolling_scored"]  = long_df.groupby("team")["team_score"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    long_df["rolling_allowed"] = long_df.groupby("team")["opp_score"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    latest_sc = long_df.groupby("team").nth(-1).reset_index()[["team", "rolling_scored", "rolling_allowed"]]
    upcoming = upcoming.merge(latest_sc.rename(columns={"team": "home_team", "rolling_scored": "home_rolling_scored", "rolling_allowed": "home_rolling_allowed"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_sc.rename(columns={"team": "away_team", "rolling_scored": "away_rolling_scored", "rolling_allowed": "away_rolling_allowed"}), on="away_team", how="left")
    upcoming["scoring_diff"]         = upcoming["home_rolling_scored"] - upcoming["away_rolling_scored"]
    upcoming["scoring_diff_reverse"] = upcoming["away_rolling_scored"] - upcoming["home_rolling_scored"]

    history2 = _hist_rolling.copy()
    # push=0 (home) / push=1 (away) matches training behaviour — retrain before switching to NaN
    history2["home_covered"] = (history2["result"] > history2["spread_line"]).astype(int)
    home_cov = history2[["season", "week", "home_team", "home_covered"]].rename(columns={"home_team": "team", "home_covered": "covered"})
    away_cov = history2[["season", "week", "away_team", "home_covered"]].copy()
    away_cov["covered"] = 1 - away_cov["home_covered"]
    away_cov = away_cov.drop(columns="home_covered").rename(columns={"away_team": "team"})
    cover_df = pd.concat([home_cov, away_cov]).sort_values(["team", "season", "week"])
    cover_df["rolling_cover_rate"] = cover_df.groupby("team")["covered"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    latest_cover = cover_df.groupby("team").nth(-1).reset_index()[["team", "rolling_cover_rate"]]
    upcoming = upcoming.merge(latest_cover.rename(columns={"team": "home_team", "rolling_cover_rate": "home_rolling_cover_rate"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_cover.rename(columns={"team": "away_team", "rolling_cover_rate": "away_rolling_cover_rate"}), on="away_team", how="left")
    upcoming["cover_rate_diff"] = upcoming["home_rolling_cover_rate"] - upcoming["away_rolling_cover_rate"]

    # Cross-season per-week avg absolute margin — matches training definition
    _target_week = int(upcoming["week"].iloc[0])
    if week_margin_lkp is not None and _target_week in week_margin_lkp.index:
        upcoming["league_rolling_avg_abs_margin_by_week"] = float(week_margin_lkp[_target_week])
    elif week_margin_lkp is not None and len(week_margin_lkp) > 0:
        upcoming["league_rolling_avg_abs_margin_by_week"] = float(week_margin_lkp.mean())
    else:
        _wk_avgs = history.groupby("week")["result"].apply(lambda x: x.abs().mean()).sort_index()
        upcoming["league_rolling_avg_abs_margin_by_week"] = float(_wk_avgs.iloc[-1]) if len(_wk_avgs) > 0 else 0.0

    return upcoming

# ============================================================================
# Group 4 — `_build_allpro`
# ============================================================================
def _build_allpro(upcoming, allpro_df, target_season):
    """Group 4: weighted 3-year AllPro roster quality (offense/defense split).

    Identity is resolved through `betting/allpro_identity.py` (2026-08-03). This used to
    dedupe with `sort_values("Weight").drop_duplicates(["Player", "Year_target"])`, which
    (a) keyed on the NAME, silently merging two distinct players called C.J. Mosley, and
    (b) depended on pandas' unstable default sort for which of them survived. The
    replacement keys on a canonical identity and never sorts.
    """
    allpro_df = resolve_allpro_identities(allpro_df)
    offense_df = allpro_df[allpro_df["Side"] == "offense"].copy()
    defense_df = allpro_df[allpro_df["Side"] == "defense"].copy()

    def build_weighted(df_ap):
        frames = [weighted_lookback(df_ap, year)
                  for year in range(2006, target_season + 1)]
        frames = [f for f in frames if len(f)]
        if not frames:
            return pd.DataFrame(columns=["season", "Team", "allpro_weighted"])
        return pd.concat(frames, ignore_index=True)

    weighted_allpro  = build_weighted(allpro_df)
    offense_weighted = build_weighted(offense_df)
    defense_weighted = build_weighted(defense_df)

    def merge_allpro(df, feat_df, feat_col, home_col, away_col):
        lookup = feat_df[feat_df["season"] == target_season].drop(columns="season")
        df = df.merge(lookup.rename(columns={"Team": "home_team", feat_col: home_col}), on="home_team", how="left")
        df = df.merge(lookup.rename(columns={"Team": "away_team", feat_col: away_col}), on="away_team", how="left")
        df[home_col] = df[home_col].fillna(0)
        df[away_col] = df[away_col].fillna(0)
        return df

    upcoming = merge_allpro(upcoming, weighted_allpro,  "allpro_weighted", "home_allpro_last_3_years_weighted", "away_allpro_last_3_years_weighted")
    upcoming = merge_allpro(upcoming, offense_weighted, "allpro_weighted", "home_offense_allpro_3_years",        "away_offense_allpro_3_years")
    upcoming = merge_allpro(upcoming, defense_weighted, "allpro_weighted", "home_defense_allpro_3_years",        "away_defense_allpro_3_years")

    # Count distinct IDENTITIES, not names — two players sharing a name on one team would
    # otherwise count as one (2026-08-03).
    prev_overall = allpro_df.assign(season=allpro_df["Year"] + 1).groupby(["season", "Team"])["allpro_id"].nunique().reset_index(name="allpro_prev_year")
    prev_offense = offense_df.assign(season=offense_df["Year"] + 1).groupby(["season", "Team"])["allpro_id"].nunique().reset_index(name="allpro_prev_year")
    prev_defense = defense_df.assign(season=defense_df["Year"] + 1).groupby(["season", "Team"])["allpro_id"].nunique().reset_index(name="allpro_prev_year")

    upcoming = merge_allpro(upcoming, prev_overall, "allpro_prev_year", "home_allpro_prev_year",         "away_allpro_prev_year")
    upcoming = merge_allpro(upcoming, prev_offense, "allpro_prev_year", "home_offense_allpro_prev_year", "away_offense_allpro_prev_year")
    upcoming = merge_allpro(upcoming, prev_defense, "allpro_prev_year", "home_defense_allpro_prev_year", "away_defense_allpro_prev_year")

    upcoming["diff_allpro_last_3_years_weighted"]        = upcoming["home_allpro_last_3_years_weighted"] - upcoming["away_allpro_last_3_years_weighted"]
    upcoming["diff_allpro_prev_year"]                    = upcoming["home_allpro_prev_year"]              - upcoming["away_allpro_prev_year"]
    upcoming["allpro_diff_home_off_away_def_3_years"]    = upcoming["home_offense_allpro_3_years"]        - upcoming["away_defense_allpro_3_years"]
    upcoming["allpro_diff_home_def_away_off_3_years "]   = upcoming["home_defense_allpro_3_years"]        - upcoming["away_offense_allpro_3_years"]   # trailing space matches model
    upcoming["allpro_diff_home_off_away_def_prev_year"]  = upcoming["home_offense_allpro_prev_year"]      - upcoming["away_defense_allpro_prev_year"]
    upcoming["allpro_diff_home_def_away_off_prev_year"]  = upcoming["home_defense_allpro_prev_year"]      - upcoming["away_offense_allpro_prev_year"]
    return upcoming

# ============================================================================
# Group 6 — `_build_situational_pbp`
# ============================================================================
def _build_situational_pbp(upcoming, pbp_s, wk_lookup):
    """Group 6: sacks, turnovers, third-down conversion rate (5-game rolling)."""
    # DENSE sack table -- zero-sack games must keep a row. LEAK/BIAS FIX 2026-08-03.
    # This used to filter `sack == 1` BEFORE the groupby, so a defense with no sack in a
    # game produced no row and the 5-game window silently skipped it instead of averaging
    # a 0. Reproduced: sacks of 3, 2, 0, 4 served 3.0 against a true mean of 2.25. The
    # turnover and third-down blocks below always grouped the full pbp; sacks was the odd
    # one out. Training (model_comparison.ipynb Section 7) carried the same defect plus a
    # contemporaneous-information leak, and was fixed in the same change -- keep the two
    # definitions identical or train/serve skew returns.
    pbp_sack = pbp_s.copy()
    pbp_sack["_sack_i"] = (pbp_sack["sack"] == 1).astype(int)
    sacks   = pbp_sack.groupby(["game_id", "defteam"])["_sack_i"].sum().reset_index(name="sacks").rename(columns={"defteam": "team"})
    sacks   = sacks.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left").sort_values(["team", "season", "week"])
    sacks["rolling_sacks"] = sacks.groupby("team")["sacks"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    latest_sacks = sacks.groupby("team").nth(-1).reset_index()[["team", "rolling_sacks"]]
    upcoming = upcoming.merge(latest_sacks.rename(columns={"team": "home_team", "rolling_sacks": "home_rolling_sacks"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_sacks.rename(columns={"team": "away_team", "rolling_sacks": "away_rolling_sacks"}), on="away_team", how="left")
    upcoming["sack_diff"]         = upcoming["home_rolling_sacks"] - upcoming["away_rolling_sacks"]
    upcoming["sack_diff_reverse"] = upcoming["away_rolling_sacks"] - upcoming["home_rolling_sacks"]

    pbp_s2 = pbp_s.copy()
    pbp_s2["turnover"] = ((pbp_s2["interception"] == 1) | (pbp_s2["fumble_lost"] == 1)).astype(int)
    to_df = pbp_s2.groupby(["game_id", "posteam"])["turnover"].sum().reset_index().rename(columns={"posteam": "team"})
    to_df = to_df.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left").sort_values(["team", "season", "week"])
    to_df["rolling_turnovers"] = to_df.groupby("team")["turnover"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    latest_to = to_df.groupby("team").nth(-1).reset_index()[["team", "rolling_turnovers"]]
    upcoming  = upcoming.merge(latest_to.rename(columns={"team": "home_team", "rolling_turnovers": "home_rolling_turnovers"}), on="home_team", how="left")
    upcoming  = upcoming.merge(latest_to.rename(columns={"team": "away_team", "rolling_turnovers": "away_rolling_turnovers"}), on="away_team", how="left")
    upcoming["turnover_diff"]         = upcoming["home_rolling_turnovers"] - upcoming["away_rolling_turnovers"]
    upcoming["turnover_diff_reverse"] = upcoming["away_rolling_turnovers"] - upcoming["home_rolling_turnovers"]

    pbp_s2["third_att"]  = (pbp_s2["down"] == 3).astype(int)
    pbp_s2["third_conv"] = ((pbp_s2["down"] == 3) & (pbp_s2["first_down"] == 1)).astype(int)
    third_df = pbp_s2.groupby(["game_id", "posteam"]).agg(third_att=("third_att", "sum"), third_conv=("third_conv", "sum")).reset_index().rename(columns={"posteam": "team"})
    third_df["third_down_rate"] = third_df["third_conv"] / third_df["third_att"].replace(0, 1)
    third_df = third_df.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left").sort_values(["team", "season", "week"])
    third_df["rolling_third"] = third_df.groupby("team")["third_down_rate"].transform(lambda x: x.rolling(5, min_periods=1).mean())
    latest_third = third_df.groupby("team").nth(-1).reset_index()[["team", "rolling_third"]]
    upcoming = upcoming.merge(latest_third.rename(columns={"team": "home_team", "rolling_third": "home_rolling_third_down"}), on="home_team", how="left")
    upcoming = upcoming.merge(latest_third.rename(columns={"team": "away_team", "rolling_third": "away_rolling_third_down"}), on="away_team", how="left")
    upcoming["third_down_diff"]         = upcoming["home_rolling_third_down"] - upcoming["away_rolling_third_down"]
    upcoming["third_down_diff_reverse"] = upcoming["away_rolling_third_down"] - upcoming["home_rolling_third_down"]
    return upcoming

# ============================================================================
# Group 7 — `_build_qb_switch`
# ============================================================================
def _build_qb_switch(upcoming, history, coach_hist_df, target_season):
    """Group 7: QB switch flags (home/away qb_switch and is_qb_new)."""
    if coach_hist_df is not None:
        _prior_sched = coach_hist_df[
            (coach_hist_df["season"] == target_season - 1) & coach_hist_df["result"].notna()
        ].copy()
    else:
        try:
            _prior_raw   = nfl.load_schedules([target_season - 1])
            _prior_sched = _prior_raw.to_pandas() if hasattr(_prior_raw, "to_pandas") else pd.DataFrame(_prior_raw)
            _prior_sched = _prior_sched[_prior_sched["result"].notna()].copy()
        except Exception:
            _prior_sched = pd.DataFrame(columns=list(history.columns))
    _qb_hist = pd.concat([
        _prior_sched[["season", "week", "home_team", "away_team", "home_qb_name", "away_qb_name"]],
        history[["season", "week", "home_team", "away_team", "home_qb_name", "away_qb_name"]]
    ]).dropna(subset=["home_team", "away_team"])
    home_qbs = _qb_hist[["season", "week", "home_team", "home_qb_name"]].rename(columns={"home_team": "team", "home_qb_name": "qb_name"})
    away_qbs = _qb_hist[["season", "week", "away_team", "away_qb_name"]].rename(columns={"away_team": "team", "away_qb_name": "qb_name"})
    team_qbs = pd.concat([home_qbs, away_qbs]).sort_values(["team", "season", "week"])
    last_qb  = team_qbs.groupby("team").nth(-1).reset_index()[["team", "qb_name"]].rename(columns={"qb_name": "last_qb"})
    upcoming = upcoming.merge(last_qb.rename(columns={"team": "home_team", "last_qb": "home_last_qb"}), on="home_team", how="left")
    upcoming = upcoming.merge(last_qb.rename(columns={"team": "away_team", "last_qb": "away_last_qb"}), on="away_team", how="left")
    upcoming["home_qb_switch"] = (
        upcoming["home_qb_name"].notna() &
        upcoming["home_last_qb"].notna() &
        (upcoming["home_qb_name"] != upcoming["home_last_qb"])
    )
    upcoming["away_qb_switch"] = (
        upcoming["away_qb_name"].notna() &
        upcoming["away_last_qb"].notna() &
        (upcoming["away_qb_name"] != upcoming["away_last_qb"])
    )
    # Both pairs are currently synonymous; differentiate only if models are retrained
    upcoming["is_home_qb_new"] = upcoming["home_qb_switch"]
    upcoming["is_away_qb_new"] = upcoming["away_qb_switch"]
    return upcoming

# ============================================================================
# Group 8 — `_build_passer_rating`
# ============================================================================
def _build_passer_rating(upcoming, pbp_rp, target_season, ngs_data=None):
    """Group 8: prior-season NFL passer rating diff.

    Source: NFL Next Gen Stats (`nfl.load_nextgen_stats`, 2016+) — the official
    league source. Falls back to the manual NFL-passer-rating formula on PBP
    if NGS is unavailable, or the prior season predates NGS (pre-2016).

    Args:
        upcoming, pbp_rp, target_season: as documented in build_features.
        ngs_data: optional pre-fetched DataFrame with columns ``team_abbr``,
            ``season``, ``week``, ``attempts``, ``passer_rating``,
            ``completion_percentage_above_expectation``, ``avg_time_to_throw``.
            If provided, skips the live ``nfl.load_nextgen_stats`` call — used
            by inline tests for hermetic execution.
    """
    prior_season = target_season - 1

    pr_prev = None
    if prior_season >= 2016:
        try:
            if ngs_data is not None:
                ngs = ngs_data.copy()
            else:
                ngs = nfl.load_nextgen_stats(seasons=[prior_season], stat_type="passing").to_pandas()
            ngs_agg = ngs[(ngs["week"] == 0) & (ngs["attempts"] >= 100)].copy()
            if not ngs_agg.empty:
                ngs_agg["posteam"] = ngs_agg["team_abbr"].apply(lambda t: canonicalize_ngs_team(t, prior_season))
                pr_prev = (ngs_agg.sort_values("attempts", ascending=False)
                                  .groupby("posteam").first().reset_index()
                                  [["posteam", "passer_rating",
                                    "completion_percentage_above_expectation",
                                    "avg_time_to_throw"]])
        except Exception as _e:
            print(f"  WARNING: NGS load failed for {prior_season} ({_e}) — falling back to manual passer-rating")

    if pr_prev is None or pr_prev.empty:
        # Manual NFL passer rating from PBP — pre-2016 or NGS unavailable
        pass_plays = pbp_rp[
            (pbp_rp["play_type"] == "pass") &
            (pbp_rp["season"]    == prior_season) &
            (pbp_rp["passer_player_name"].notna())
        ].copy()
        qb_stats = pass_plays.groupby(["season", "posteam", "passer_player_name"]).agg(
            attempts=("pass_attempt", "sum"), completions=("complete_pass", "sum"),
            yards=("passing_yards", "sum"), tds=("pass_touchdown", "sum"), ints=("interception", "sum")
        ).reset_index()
        qb_stats = qb_stats[qb_stats["attempts"] >= 100]

        def passer_rating(row):
            a = max(0, min(((row["completions"] / row["attempts"]) - 0.3) * 5, 2.375))
            b = max(0, min(((row["yards"]       / row["attempts"]) - 3) * 0.25, 2.375))
            c = max(0, min(row["tds"]           / row["attempts"]  * 20,        2.375))
            d = max(0, min(2.375 - (row["ints"] / row["attempts"] * 25),        2.375))
            return ((a + b + c + d) / 6) * 100

        qb_stats["passer_rating"] = qb_stats.apply(passer_rating, axis=1)
        pr_prev = (qb_stats.sort_values("attempts", ascending=False)
                          .groupby(["season", "posteam"]).first().reset_index()
                          [["posteam", "passer_rating"]])

    median_pr = pr_prev["passer_rating"].median()
    upcoming = upcoming.merge(
        pr_prev[["posteam", "passer_rating"]].rename(columns={"posteam": "home_team", "passer_rating": "home_pr_prev_year"}),
        on="home_team", how="left")
    upcoming = upcoming.merge(
        pr_prev[["posteam", "passer_rating"]].rename(columns={"posteam": "away_team", "passer_rating": "away_pr_prev_year"}),
        on="away_team", how="left")
    upcoming["home_pr_prev_year"] = upcoming["home_pr_prev_year"].fillna(median_pr)
    upcoming["away_pr_prev_year"] = upcoming["away_pr_prev_year"].fillna(median_pr)
    upcoming["diff_pr_prev_year"] = upcoming["home_pr_prev_year"] - upcoming["away_pr_prev_year"]
    for _ngs_col, _feat in [
        ("completion_percentage_above_expectation", "cpae_prev_year"),
        ("avg_time_to_throw", "time_to_throw_prev_year"),
    ]:
        if _ngs_col in pr_prev.columns and pr_prev[_ngs_col].notna().any():
            _med = pr_prev[_ngs_col].median()
            _sub = pr_prev[["posteam", _ngs_col]].dropna(subset=[_ngs_col])
            upcoming = upcoming.merge(
                _sub.rename(columns={"posteam": "home_team", _ngs_col: f"home_{_feat}"}),
                on="home_team", how="left")
            upcoming = upcoming.merge(
                _sub.rename(columns={"posteam": "away_team", _ngs_col: f"away_{_feat}"}),
                on="away_team", how="left")
        else:
            _med = 0.0
            upcoming[f"home_{_feat}"] = float("nan")
            upcoming[f"away_{_feat}"] = float("nan")
        upcoming[f"home_{_feat}"] = upcoming[f"home_{_feat}"].fillna(_med)
        upcoming[f"away_{_feat}"] = upcoming[f"away_{_feat}"].fillna(_med)
        upcoming[f"diff_{_feat}"] = upcoming[f"home_{_feat}"] - upcoming[f"away_{_feat}"]
    return upcoming

# ============================================================================
# Group 9 — `_build_injuries`
# ============================================================================
def _build_injuries(upcoming, allpro_df, target_season, target_week):
    """Group 9: injured player count and AllPro-weighted injury impact.

    Reads home/away_allpro_last_3_years_weighted from upcoming, so must run
    after _build_allpro (Group 4).
    """
    try:
        raw_inj = nfl.load_injuries(seasons=[target_season])
        inj_df  = raw_inj.to_pandas() if hasattr(raw_inj, "to_pandas") else pd.DataFrame(raw_inj)
        _STATUS_WEIGHT = {"Out": 1.0, "Doubtful": 0.75}
        inj_week = inj_df[(inj_df["report_status"].isin(["Out", "Doubtful"])) & (inj_df["week"] == target_week)].copy()
        inj_by_team = inj_week.groupby("team").size().reset_index(name="count")

        upcoming = upcoming.merge(inj_by_team.rename(columns={"team": "home_team", "count": "home_injured_count"}), on="home_team", how="left")
        upcoming = upcoming.merge(inj_by_team.rename(columns={"team": "away_team", "count": "away_injured_count"}), on="away_team", how="left")
        upcoming[["home_injured_count", "away_injured_count"]] = upcoming[["home_injured_count", "away_injured_count"]].fillna(0)
        upcoming["diff_injured_count"] = upcoming["home_injured_count"] - upcoming["away_injured_count"]

        inj_all = inj_df[(inj_df["report_status"].isin(["Out", "Doubtful"])) & (inj_df["week"] == target_week)].copy()
        inj_all["_status_wt"] = inj_all["report_status"].map(_STATUS_WEIGHT).fillna(0)
        inj_all["season"] = inj_all["season"].astype(int)
        allpro_hist = []
        for yrs_back, weight in zip([1, 2, 3], [4, 2, 1]):
            tmp = allpro_df.copy()
            tmp["season"] = tmp["Year"] + yrs_back
            tmp["weight"] = weight
            allpro_hist.append(tmp)
        # ignore_index is load-bearing: pd.concat of the three lookback frames repeats
        # index labels, and `.loc[groupby(...).idxmax()]` on a duplicated index returns
        # EVERY row sharing a winning label — reintroducing the very fan-out the identity
        # fix removes. The fan-out assertion in injured_allpro_weight caught this.
        allpro_wh = pd.concat(allpro_hist, ignore_index=True)
        # Identity-keyed, order-invariant: keep each identity's highest weight per season.
        # Was drop_duplicates(["Player","season"]) — same name-collision defect as Group 4.
        allpro_wh = resolve_allpro_identities(allpro_wh)
        allpro_wh = allpro_wh.loc[allpro_wh.groupby(["allpro_id", "season"])["weight"].idxmax()]
        allpro_wh = allpro_wh.copy()
        # IDENTITY-AWARE injury match (2026-08-03). This previously dropped `allpro_id` and
        # merged on ["_name_norm", "season"], which FANS OUT when two All-Pro players share
        # a name in the same weight window — one injury row matched two All-Pro rows and the
        # weight was subtracted twice, corrupting `diff_active_allpro_weighted`
        # (PROD_FEATURES_35 #11). `injured_allpro_weight` is the shared implementation used
        # by the training notebook too; it asserts no fan-out and aborts on any ambiguity
        # its reviewed crosswalk does not cover.
        inj_all = injured_allpro_weight(inj_all, allpro_wh, inj_name_col="full_name",
                                        inj_team_col="team", season_col="season")
        inj_wt    = inj_all.groupby(["season", "week", "team"])["weight"].sum().reset_index().rename(columns={"weight": "inj_ap_wt"})
        upcoming  = upcoming.merge(inj_wt.rename(columns={"team": "home_team"}).drop(columns=["season", "week"]), on="home_team", how="left").rename(columns={"inj_ap_wt": "home_inj_ap_wt"})
        upcoming  = upcoming.merge(inj_wt.rename(columns={"team": "away_team"}).drop(columns=["season", "week"]), on="away_team", how="left").rename(columns={"inj_ap_wt": "away_inj_ap_wt"})
        upcoming[["home_inj_ap_wt", "away_inj_ap_wt"]] = upcoming[["home_inj_ap_wt", "away_inj_ap_wt"]].fillna(0)
        upcoming["home_active_allpro_weighted"] = (upcoming["home_allpro_last_3_years_weighted"] - upcoming["home_inj_ap_wt"]).clip(lower=0)
        upcoming["away_active_allpro_weighted"] = (upcoming["away_allpro_last_3_years_weighted"] - upcoming["away_inj_ap_wt"]).clip(lower=0)
        upcoming["diff_active_allpro_weighted"] = upcoming["home_active_allpro_weighted"] - upcoming["away_active_allpro_weighted"]
        # Identity-based, not name-based: a same-name player would otherwise be counted as
        # the All-Pro. `inj_all` already carries `allpro_id` from the identity match above.
        _prev_yr_ap_ids = set(allpro_df.loc[allpro_df["Year"] == target_season - 1, "allpro_id"])
        inj_prev_yr     = inj_all[inj_all["allpro_id"].isin(_prev_yr_ap_ids)]
        inj_prev_yr_by_team = inj_prev_yr.groupby("team").size().reset_index(name="inj_ap_prev_yr")
        upcoming = upcoming.merge(inj_prev_yr_by_team.rename(columns={"team": "home_team", "inj_ap_prev_yr": "home_inj_ap_prev_yr"}), on="home_team", how="left")
        upcoming = upcoming.merge(inj_prev_yr_by_team.rename(columns={"team": "away_team", "inj_ap_prev_yr": "away_inj_ap_prev_yr"}), on="away_team", how="left")
        upcoming[["home_inj_ap_prev_yr", "away_inj_ap_prev_yr"]] = upcoming[["home_inj_ap_prev_yr", "away_inj_ap_prev_yr"]].fillna(0)
        _home_active_prev = (upcoming["home_allpro_prev_year"] - upcoming["home_inj_ap_prev_yr"]).clip(lower=0)
        _away_active_prev = (upcoming["away_allpro_prev_year"] - upcoming["away_inj_ap_prev_yr"]).clip(lower=0)
        upcoming["diff_active_allpro_prev_year"] = _home_active_prev - _away_active_prev

    except AllProIdentityError:
        # FAIL CLOSED (2026-08-03). The broad handler below exists for one legitimate
        # reason: the injury FEED may be unavailable, and a game with no injury report is
        # honestly modelled as "no known injuries" (zeros). An IDENTITY failure is a
        # different animal entirely — ambiguous player matches, a merge that fanned out, a
        # violated invariant. Swallowing those and substituting zeros would silently ship
        # wrong `diff_active_allpro_weighted` (PROD_FEATURES_35 #11) instead of refusing to
        # predict. Re-raise so the caller aborts.
        raise
    except Exception as e:
        print(f"  ⚠️  Injury data unavailable: {e} — using zeros")
        for col in ["home_injured_count", "away_injured_count", "diff_injured_count", "diff_active_allpro_weighted", "diff_active_allpro_prev_year"]:
            upcoming[col] = 0
    return upcoming

# ============================================================================
# Group 10 — `_build_coach_win_pct`
# ============================================================================
def _build_coach_win_pct(upcoming, coach_hist_df, target_season, target_week):
    """Group 10: career win% and rolling 3-season win% for home/away coach."""
    if coach_hist_df is None:
        _raw_coach = nfl.load_schedules(list(range(1999, target_season + 1)))
        _ch        = _raw_coach.to_pandas() if hasattr(_raw_coach, "to_pandas") else pd.DataFrame(_raw_coach)
        coach_hist = _ch[_ch["result"].notna()].copy()
    else:
        coach_hist = coach_hist_df
    home_c = coach_hist[["game_id", "season", "week", "home_team", "away_team", "home_score", "away_score", "home_coach"]].copy()
    home_c.rename(columns={"home_team": "team", "away_team": "opponent", "home_score": "team_score", "away_score": "opponent_score", "home_coach": "coach"}, inplace=True)
    away_c = coach_hist[["game_id", "season", "week", "away_team", "home_team", "away_score", "home_score", "away_coach"]].copy()
    away_c.rename(columns={"away_team": "team", "home_team": "opponent", "away_score": "team_score", "home_score": "opponent_score", "away_coach": "coach"}, inplace=True)
    games_df = pd.concat([home_c, away_c], ignore_index=True)
    games_df["win"] = (games_df["team_score"] > games_df["opponent_score"]).astype(int)

    # Vectorised, version-agnostic replacement for a per-coach `.apply` (2026-08-03).
    # `groupby("coach", group_keys=False).apply(fn)` raised KeyError: 'coach' on pandas 3,
    # which removed the grouping column from the frame handed to the callable and dropped
    # `include_groups` entirely, so there was no kwarg fix. The whole build crashed --
    # it was masked in CI only by the exact pandas==2.3.3 pin in requirements-ci.txt.
    # Identities preserved exactly:
    #   cumsum().shift(fill_value=0)          == cumsum() - win   (prior wins)
    #   expanding().count().shift(fill_value=0) == cumcount()     (prior games: 0,1,2,...)
    games_df = games_df.sort_values(["coach", "season", "week", "game_id"]).copy()
    _by_coach = games_df.groupby("coach")
    games_df["cumulative_wins"]  = _by_coach["win"].cumsum() - games_df["win"]
    games_df["cumulative_games"] = _by_coach.cumcount().astype(float)
    games_df["coach_win_pct_prior"] = (
        games_df["cumulative_wins"] / games_df["cumulative_games"].replace(0, np.nan)
    ).fillna(0).round(3)
    latest_coach_wp = (
        games_df.sort_values(["season", "week", "game_id"])
        .groupby("coach").nth(-1).reset_index()[["coach", "coach_win_pct_prior"]]
    )
    upcoming = upcoming.merge(
        latest_coach_wp.rename(columns={"coach": "home_coach", "coach_win_pct_prior": "home_coach_win_pct_prior"}),
        on="home_coach", how="left"
    )
    upcoming = upcoming.merge(
        latest_coach_wp.rename(columns={"coach": "away_coach", "coach_win_pct_prior": "away_coach_win_pct_prior"}),
        on="away_coach", how="left"
    )
    _league_coach_avg = latest_coach_wp["coach_win_pct_prior"].mean() if len(latest_coach_wp) > 0 else 0.5
    upcoming[["home_coach_win_pct_prior", "away_coach_win_pct_prior"]] = (
        upcoming[["home_coach_win_pct_prior", "away_coach_win_pct_prior"]].fillna(_league_coach_avg)
    )

    # Rolling 3-season coach win% — more sensitive to recent performance than career win%
    _roll3_pool = games_df[
        ((games_df["season"] >= target_season - 3) & (games_df["season"] < target_season)) |
        ((games_df["season"] == target_season) & (games_df["week"] < target_week))
    ]
    _roll3_wp = (
        _roll3_pool.groupby("coach")
        .agg(wins=("win", "sum"), g=("win", "count"))
        .assign(coach_win_pct_roll3=lambda d: (d["wins"] / d["g"].replace(0, np.nan)).fillna(_league_coach_avg).round(3))
        .reset_index()[["coach", "coach_win_pct_roll3"]]
    )
    upcoming = upcoming.merge(
        _roll3_wp.rename(columns={"coach": "home_coach", "coach_win_pct_roll3": "home_coach_win_pct_roll3"}),
        on="home_coach", how="left"
    )
    upcoming = upcoming.merge(
        _roll3_wp.rename(columns={"coach": "away_coach", "coach_win_pct_roll3": "away_coach_win_pct_roll3"}),
        on="away_coach", how="left"
    )
    upcoming[["home_coach_win_pct_roll3", "away_coach_win_pct_roll3"]] = (
        upcoming[["home_coach_win_pct_roll3", "away_coach_win_pct_roll3"]].fillna(_league_coach_avg)
    )
    return upcoming

# ============================================================================
# Main pipeline — `build_features`
# ============================================================================
def build_features(
    target_week,
    target_season,
    full_schedule,
    pbp_rp,
    allpro_df,
    week_margin_lkp=None,
    coach_hist_df=None,
    required_features: Optional[Iterable[str]] = None,
):
    """Build all 85 features for ``target_week`` using only data available
    before that week. Returns the ``upcoming`` DataFrame with feature columns
    appended, or ``None`` if no games for that week."""
    history = full_schedule[
        (full_schedule["season"] == target_season) &
        (full_schedule["week"]   <  target_week) &
        (full_schedule["result"].notna())
    ].copy()

    upcoming = full_schedule[
        (full_schedule["season"] == target_season) &
        (full_schedule["week"]   == target_week)
    ].copy()

    if upcoming.empty:
        return None

    if history.empty:
        print(f"  ℹ️  Week 1: no season history yet — SOS/scoring/cover features will be zero-filled")

    # ── Shared intermediates used by multiple groups ───────────────────────────
    pbp_s = pbp_rp[
        ((pbp_rp["season"] == target_season) & (pbp_rp["week"] < target_week)) |
        (pbp_rp["season"] == target_season - 1)
    ].copy()
    wk_lookup = pbp_rp[["game_id", "week", "season"]].drop_duplicates()

    _req_cols = ["season", "week", "home_team", "away_team", "home_score", "away_score", "result", "spread_line"]
    if coach_hist_df is not None and all(c in coach_hist_df.columns for c in _req_cols):
        _hist_rolling = coach_hist_df[
            ((coach_hist_df["season"] == target_season) & (coach_hist_df["week"] < target_week)) |
            (coach_hist_df["season"] == target_season - 1)
        ][_req_cols].copy()
    else:
        _hist_rolling = history[[c for c in _req_cols if c in history.columns]].copy()

    # ── Apply feature groups in order ─────────────────────────────────────────
    upcoming = _build_schedule_context(upcoming, full_schedule, target_week)
    upcoming = _build_rolling_pbp(upcoming, pbp_s, wk_lookup)
    upcoming = _build_sos_and_performance(upcoming, _hist_rolling, history, week_margin_lkp)
    upcoming = _build_allpro(upcoming, allpro_df, target_season)               # Group 4 must run before Group 9
    upcoming = _build_situational_pbp(upcoming, pbp_s, wk_lookup)
    upcoming = _build_qb_switch(upcoming, history, coach_hist_df, target_season)
    upcoming = _build_passer_rating(upcoming, pbp_rp, target_season)
    upcoming = _build_injuries(upcoming, allpro_df, target_season, target_week)  # depends on Group 4 columns
    upcoming = _build_coach_win_pct(upcoming, coach_hist_df, target_season, target_week)

    # ── Final feature check ───────────────────────────────────────────────────
    _all_required = list(dict.fromkeys(required_features)) if required_features is not None else list(FEATURE_COLS_85)
    missing = [f for f in _all_required if f not in upcoming.columns]
    if missing:
        print(f"  ⚠️  {len(missing)} features missing for week {target_week}: {missing}")
        for m in missing:
            upcoming[m] = 0

    _nan_cols = [c for c in upcoming.select_dtypes(include="number").columns
                 if upcoming[c].isna().any()]
    if _nan_cols:
        print(f"  ⚠️  {len(_nan_cols)} NaN column(s) imputed with median: {_nan_cols}")
    upcoming = upcoming.fillna(upcoming.median(numeric_only=True).fillna(0))
    return upcoming

# ============================================================================
# `build_numeric_features` — categorical encode + numeric matrix
# ============================================================================
def build_numeric_features(upcoming_df, feature_cols, enc):
    """Build an ordinal-encoded numeric feature matrix for the Ensemble and
    LightGBM voters. ``enc`` is a fit OrdinalEncoder over (roof, surface).
    Unknown / NaN categories fall back to the first known category to keep the
    matrix dense.
    """
    df = upcoming_df.copy()
    if hasattr(enc, "categories_"):
        for i, col in enumerate(["roof", "surface"]):
            known    = set(enc.categories_[i])
            fallback = enc.categories_[i][0]
            df[col]  = df[col].fillna(fallback).apply(lambda v: v if v in known else fallback)
    df[["roof", "surface"]] = enc.transform(df[["roof", "surface"]])
    X = np.zeros((len(df), len(feature_cols)), dtype="float32")
    for i, col in enumerate(feature_cols):
        if col in df.columns:
            X[:, i] = pd.to_numeric(df[col], errors="coerce").fillna(0).values
    return X
