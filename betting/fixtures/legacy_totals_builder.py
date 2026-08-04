"""VENDORED LEGACY BUILDER — the pre-fix `build_totals_features`, kept so the
"historical values did not move" claim is proved by EXECUTION against the real old code
rather than by reading a diff.

Source of record: commit `3dbd110`, `betting/totals_features.ipynb` cell 10.
The cell source is pinned by sha256 below; `test_totals_live.py` re-derives that hash from
the committed notebook history and refuses to run the equivalence proof if it has drifted.

DO NOT EDIT the function body. It is a frozen historical artifact, defects included
(the game_id-keyed rolling merges and the mean/zero imputation are exactly the defects the
new builder removes on the live path).
"""
LEGACY_CELL_SHA256 = "2eb81cdfed60954385135add18751fdaeda7cb67708f44e96543054e7b68775a"
LEGACY_CELL_SOURCE_COMMIT = "3dbd110"

from pathlib import Path

import numpy as np  # noqa: F401  (kept: the vendored body was exec'd in a numpy namespace)
import pandas as pd


def build_totals_features(g, sched, pbp_full, weather_path=None):
    # Defensive: caller must pass sched with the raw `roof` string column
    # (not pre-encoded). is_dome detection depends on this.
    assert 'roof' in sched.columns, \
        "build_totals_features: sched is missing the 'roof' column — is_dome would silently be 0"

    # ── scores + raw roof string ──────────────────────────────────────────────
    # `g` may already carry home_score/away_score (predict_totals path, where
    # game_rows comes from a full_schedule slice) or may not (totals_model
    # path, where g comes from mc cells which drop the scores). Only pull
    # the score columns from sched when g doesn't already have them — pulling
    # both would create _x/_y suffix collisions.
    _aux_cols = ['game_id', 'roof']
    if 'home_score' not in g.columns:
        _aux_cols += ['home_score', 'away_score']
    aux = sched[_aux_cols].rename(columns={'roof': 'roof_str'})
    g = g.merge(aux, on='game_id', how='left')
    g['total_points'] = g['home_score'] + g['away_score']

    # ── implied team totals ───────────────────────────────────────────────────
    g['home_implied_pts'] = (g['total_line'] + g['spread_line']) / 2.0
    g['away_implied_pts'] = (g['total_line'] - g['spread_line']) / 2.0

    # ── dome flag (raw string) ────────────────────────────────────────────────
    g['is_dome'] = g['roof_str'].fillna('outdoors').isin(['dome', 'closed']).astype(int)

    # ── weather (neutralize domes; fill outdoor nulls with mean) ─────────────
    if weather_path is not None and Path(weather_path).exists():
        wx = pd.read_csv(weather_path)[['game_id', 'temp_f', 'wind_mph']]
        g = g.merge(wx, on='game_id', how='left')
    else:
        g['temp_f']   = 60.0   # outdoor league-average fallback
        g['wind_mph'] = 8.0    # outdoor league-average fallback
    dome_mask = g['is_dome'] == 1
    g.loc[dome_mask, 'temp_f']   = 70.0
    g.loc[dome_mask, 'wind_mph'] = 0.0
    g['temp_f']   = g['temp_f'].fillna(g['temp_f'].mean())
    g['wind_mph'] = g['wind_mph'].fillna(g['wind_mph'].mean())

    # ── rolling pts scored / allowed per team (5-game, shift(1)) ─────────────
    hg = sched[['game_id', 'season', 'week', 'home_team', 'home_score', 'away_score']].rename(
        columns={'home_team': 'team', 'home_score': 'pts_scored', 'away_score': 'pts_allowed'})
    ag = sched[['game_id', 'season', 'week', 'away_team', 'away_score', 'home_score']].rename(
        columns={'away_team': 'team', 'away_score': 'pts_scored', 'home_score': 'pts_allowed'})
    long_pts = pd.concat([hg, ag], ignore_index=True).sort_values(['team', 'season', 'week'])
    for col in ['pts_scored', 'pts_allowed']:
        long_pts[f'rolling_{col}_5g'] = (
            long_pts.groupby('team')[col]
            .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean()))
    home_pts = long_pts[['game_id', 'team', 'rolling_pts_scored_5g', 'rolling_pts_allowed_5g']].rename(
        columns={'team': 'home_team',
                 'rolling_pts_scored_5g': 'home_pts_scored_5g',
                 'rolling_pts_allowed_5g': 'home_pts_allowed_5g'})
    away_pts = long_pts[['game_id', 'team', 'rolling_pts_scored_5g', 'rolling_pts_allowed_5g']].rename(
        columns={'team': 'away_team',
                 'rolling_pts_scored_5g': 'away_pts_scored_5g',
                 'rolling_pts_allowed_5g': 'away_pts_allowed_5g'})
    g = g.merge(home_pts, on=['game_id', 'home_team'], how='left')
    g = g.merge(away_pts, on=['game_id', 'away_team'], how='left')
    g['combined_pts_5g'] = (
        g['home_pts_scored_5g'] + g['home_pts_allowed_5g'] +
        g['away_pts_scored_5g'] + g['away_pts_allowed_5g']) / 4.0
    for c in ['home_pts_scored_5g', 'home_pts_allowed_5g',
              'away_pts_scored_5g', 'away_pts_allowed_5g', 'combined_pts_5g']:
        g[c] = g[c].fillna(g[c].mean())

    # ── league scoring environment (rolling 4-week avg) ──────────────────────
    sc = sched[sched['home_score'].notna()].copy()
    sc['game_total'] = sc['home_score'] + sc['away_score']
    weekly_avg = (sc.groupby(['season', 'week'])['game_total']
                  .mean().reset_index()
                  .rename(columns={'game_total': 'week_avg_total'}))
    weekly_avg['league_avg_total_4wk'] = (
        weekly_avg.groupby('season')['week_avg_total']
        .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean()))
    g = g.merge(weekly_avg[['season', 'week', 'league_avg_total_4wk']],
                on=['season', 'week'], how='left')
    g['league_avg_total_4wk'] = g['league_avg_total_4wk'].fillna(g['league_avg_total_4wk'].mean())

    # ── pace: rolling plays per game (5-game, both teams averaged) ───────────
    plays = (pbp_full[pbp_full['posteam'].notna()]
             .groupby(['game_id', 'posteam']).size().reset_index(name='plays')
             .rename(columns={'posteam': 'team'}))
    week_lkp = sched[['game_id', 'season', 'week']]
    pace_long = (plays.merge(week_lkp, on='game_id', how='left')
                 .sort_values(['team', 'season', 'week']))
    pace_long['rolling_pace_5g'] = (
        pace_long.groupby('team')['plays']
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean()))
    for side, col in [('home_team', 'home_pace_5g'), ('away_team', 'away_pace_5g')]:
        lkp = pace_long[['game_id', 'team', 'rolling_pace_5g']].rename(
            columns={'team': side, 'rolling_pace_5g': col})
        g = g.merge(lkp, on=['game_id', side], how='left')
    g['pace_5g'] = (g['home_pace_5g'] + g['away_pace_5g']) / 2.0
    g['pace_5g'] = g['pace_5g'].fillna(g['pace_5g'].mean())

    # ── div_game (already in g from mc pipeline, ensure int) ─────────────────
    g['div_game'] = g['div_game'].fillna(0).astype(int)

    g = g.drop(columns=['roof_str', 'home_pace_5g', 'away_pace_5g'], errors='ignore')
    return g

