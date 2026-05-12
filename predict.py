# predict.py
# Run as: python predict.py monday | thursday | sunday

import os
import sys
import joblib
import numpy as np
import pandas as pd
import nflreadpy as nfl
from datetime import datetime
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
_DIR = Path(__file__).parent

TARGET_SEASON   = 2025
EDGE_THRESHOLD  = 1.0
TRACKER_PATH    = str(_DIR / 'predictions_tracker.csv')
ALLPRO_CSV_PATH = str(_DIR / 'nfl_allpro_1997_2025.csv')
MODEL_PATH      = str(_DIR / 'fantasy_model.pkl')
MODE            = sys.argv[1] if len(sys.argv) > 1 else 'thursday'

print(f"Running in {MODE.upper()} mode — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Load model ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FinalCfg:
    test_size: float = 0.2
    random_state: int = 42
    oof_splits: int = 5
    weight_win: float = 2.0
    weight_loss: float = 1.0
    drop_non_features: Tuple[str, ...] = ('game_id', 'home_team', 'away_team', 'season', 'week')
    categorical_cols: Tuple[str, ...] = ('roof', 'surface')
    boolean_cols: Tuple[str, ...] = (
        'is_playoff', 'is_final_week', 'home_qb_switch', 'away_qb_switch',
        'is_home_qb_new', 'is_away_qb_new'
    )
    base_xgb_params: Dict[str, Any] = field(default_factory=lambda: dict(
        n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
        subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0, reg_lambda=3.0,
        objective='reg:squarederror', random_state=42, tree_method='hist', n_jobs=1
    ))

res      = joblib.load(MODEL_PATH)
pipeline = res['pipeline']
pre      = pipeline.named_steps['preprocessor']
cat_cols = list(pre.transformers_[0][2])
num_cols = list(pre.transformers_[1][2])
model_features = cat_cols + num_cols
print(f"Model loaded — expects {len(model_features)} features")

# ── Load static data ──────────────────────────────────────────────────────────
allpro_df = pd.read_csv(ALLPRO_CSV_PATH)
allpro_df = allpro_df[allpro_df['Team'] != '2TM'].copy()

TEAM_MAP = {
    'STL': 'LA', 'LAR': 'LA', 'OAK': 'LV', 'LVR': 'LV',
    'SD': 'LAC', 'SDG': 'LAC', 'NWE': 'NE', 'KAN': 'KC',
    'GNB': 'GB', 'NOR': 'NO', 'TAM': 'TB', 'SFO': 'SF',
}
allpro_df['Team'] = allpro_df['Team'].replace(TEAM_MAP)

# ── Helper: detect current/previous week ─────────────────────────────────────
def get_week_info(season):
    raw      = nfl.load_schedules([season])
    schedule = raw.to_pandas() if hasattr(raw, 'to_pandas') else pd.DataFrame(raw)
    reg      = schedule[(schedule['season'] == season) & (schedule['game_type'] == 'REG')]
    future   = reg[reg['result'].isna()]
    done     = reg[reg['result'].notna()]
    if future.empty:
        return None, int(done['week'].max())
    upcoming_week = int(future['week'].min())
    prev_week     = upcoming_week - 1 if upcoming_week > 1 else None
    return upcoming_week, prev_week

# ── Full feature pipeline ─────────────────────────────────────────────────────
def build_features(target_week, target_season, full_schedule, pbp_rp, allpro_df):
    """
    Builds all 79 features for target_week using only data
    available before that week. Returns upcoming DataFrame.
    """
    history  = full_schedule[
        (full_schedule['season'] == target_season) &
        (full_schedule['week']   <  target_week) &
        (full_schedule['result'].notna())
    ].copy()

    upcoming = full_schedule[
        (full_schedule['season'] == target_season) &
        (full_schedule['week']   == target_week)
    ].copy()

    if upcoming.empty:
        return None

    # ── Group 1 — schedule features ──────────────────────────────────────────
    upcoming['temp']        = upcoming['temp'].fillna(72)
    upcoming['wind']        = upcoming['wind'].fillna(0)
    upcoming['is_playoff']  = (upcoming['game_type'] != 'REG')
    final_week_num          = history[history['game_type'] == 'REG']['week'].max()
    upcoming['is_final_week'] = (
        (upcoming['game_type'] == 'REG') & (upcoming['week'] == final_week_num)
    )

    # ── Group 2 — rolling PBP stats ──────────────────────────────────────────
    pbp_s      = pbp_rp[pbp_rp['season'] == target_season].copy()
    wk_lookup  = full_schedule[['game_id', 'week']].drop_duplicates()

    off_stats = (
        pbp_s.groupby(['game_id', 'posteam'])
        .agg(avg_epa=('epa', 'mean'), avg_yards=('yards_gained', 'mean'), play_count=('play_id', 'count'))
        .reset_index().rename(columns={'posteam': 'team'})
    )
    off_stats = off_stats.merge(wk_lookup, on='game_id', how='left')
    off_stats = off_stats[off_stats['week'] < target_week].sort_values(['team', 'week'])
    for feat in ['avg_epa', 'avg_yards', 'play_count']:
        off_stats[f'rolling_{feat}'] = (
            off_stats.groupby('team')[feat]
            .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
        )

    def_stats = (
        pbp_s.groupby(['game_id', 'defteam'])
        .agg(allowed_avg_epa=('epa', 'mean'), allowed_avg_yards=('yards_gained', 'mean'), allowed_play_count=('play_id', 'count'))
        .reset_index().rename(columns={'defteam': 'team'})
    )
    def_stats = def_stats.merge(wk_lookup, on='game_id', how='left')
    def_stats = def_stats[def_stats['week'] < target_week].sort_values(['team', 'week'])
    for feat in ['allowed_avg_epa', 'allowed_avg_yards', 'allowed_play_count']:
        def_stats[f'rolling_{feat}'] = (
            def_stats.groupby('team')[feat]
            .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
        )

    latest_off = off_stats.groupby('team').last().reset_index()
    latest_def = def_stats.groupby('team').last().reset_index()

    for side, df in [('home_team', latest_off), ('away_team', latest_off)]:
        prefix = 'home_' if side == 'home_team' else 'away_'
        cols   = [c for c in df.columns if c.startswith('rolling_')]
        upcoming = upcoming.merge(
            df[['team'] + cols].rename(columns={'team': side, **{c: f'{prefix}{c}' for c in cols}}),
            on=side, how='left'
        )
    for side, df in [('home_team', latest_def), ('away_team', latest_def)]:
        prefix = 'home_' if side == 'home_team' else 'away_'
        cols   = [c for c in df.columns if c.startswith('rolling_')]
        upcoming = upcoming.merge(
            df[['team'] + cols].rename(columns={'team': side, **{c: f'{prefix}{c}' for c in cols}}),
            on=side, how='left'
        )

    upcoming['epa_home_off_away_def_rolling_diff']       = upcoming['home_rolling_avg_epa']           - upcoming['away_rolling_allowed_avg_epa']
    upcoming['epa_home_def_away_off_rolling_diff']       = upcoming['home_rolling_allowed_avg_epa']   - upcoming['away_rolling_avg_epa']
    upcoming['avg_yards_home_off_away_def_rolling_diff'] = upcoming['home_rolling_avg_yards']         - upcoming['away_rolling_allowed_avg_yards']
    upcoming['avg_yards_home_def_away_off_rolling_diff'] = upcoming['home_rolling_allowed_avg_yards'] - upcoming['away_rolling_avg_yards']
    upcoming['play_count_home_off_away_def_rolling_diff']= upcoming['home_rolling_play_count']        - upcoming['away_rolling_allowed_play_count']
    upcoming['play_count_home_def_away_off_rolling_diff']= upcoming['home_rolling_allowed_play_count']- upcoming['away_rolling_play_count']

    # ── Group 3 — SOS ────────────────────────────────────────────────────────
    home_g = history[['season','week','home_team','away_team','home_score','away_score']].copy()
    home_g.columns = ['season','week','team','opponent','team_score','opp_score']
    away_g = history[['season','week','away_team','home_team','away_score','home_score']].copy()
    away_g.columns = ['season','week','team','opponent','team_score','opp_score']
    long_df = pd.concat([home_g, away_g]).sort_values(['team','season','week'])
    long_df['team_win'] = (long_df['team_score'] > long_df['opp_score']).astype(int)
    long_df['win_pct']  = long_df.groupby('team')['team_win'].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    opp_wp = long_df[['season','week','team','win_pct']].copy()
    opp_wp.columns = ['season','week','opponent','opponent_win_pct']
    long_df = long_df.merge(opp_wp, on=['season','week','opponent'], how='left')
    long_df['recent_sos'] = long_df.groupby('team')['opponent_win_pct'].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean().fillna(0)
    )
    long_df['season_sos'] = long_df.groupby('team')['opponent_win_pct'].transform(
        lambda x: x.shift(1).expanding().mean().fillna(0)
    )
    latest_sos = long_df.groupby('team').last().reset_index()[['team','recent_sos','season_sos']]
    upcoming = upcoming.merge(latest_sos.rename(columns={'team':'home_team','recent_sos':'home_recent_sos_opponent_avg','season_sos':'home_season_sos_opponent_avg'}), on='home_team', how='left')
    upcoming = upcoming.merge(latest_sos.rename(columns={'team':'away_team','recent_sos':'away_recent_sos_opponent_avg','season_sos':'away_season_sos_opponent_avg'}), on='away_team', how='left')
    for col in ['home_recent_sos_opponent_avg','home_season_sos_opponent_avg','away_recent_sos_opponent_avg','away_season_sos_opponent_avg']:
        upcoming[col] = upcoming[col].fillna(0)
    upcoming['sos_diff']        = upcoming['home_recent_sos_opponent_avg'] - upcoming['away_recent_sos_opponent_avg']
    upcoming['season_sos_diff'] = upcoming['home_season_sos_opponent_avg'] - upcoming['away_season_sos_opponent_avg']

    # ── Group 4 — All-Pro ────────────────────────────────────────────────────
    offense_df = allpro_df[allpro_df['Side'] == 'offense'].copy()
    defense_df = allpro_df[allpro_df['Side'] == 'defense'].copy()

    def build_weighted(df_ap):
        frames = []
        for year in range(2006, target_season + 1):
            curr = []
            for yrs_back, weight in zip([1, 2, 3], [4, 2, 1]):
                tmp = df_ap[df_ap['Year'] == year - yrs_back].copy()
                tmp['Weight'] = weight
                tmp['Year_target'] = year
                curr.append(tmp)
            comb    = pd.concat(curr)
            deduped = comb.sort_values('Weight', ascending=False).drop_duplicates(['Player', 'Year_target'])
            wc      = deduped.groupby(['Year_target', 'Team'])['Weight'].sum().reset_index()
            wc.columns = ['season', 'Team', 'allpro_weighted']
            frames.append(wc)
        return pd.concat(frames, ignore_index=True)

    weighted_allpro  = build_weighted(allpro_df)
    offense_weighted = build_weighted(offense_df)
    defense_weighted = build_weighted(defense_df)

    def merge_allpro(df, feat_df, feat_col, home_col, away_col):
        lookup = feat_df[feat_df['season'] == target_season].drop(columns='season')
        df = df.merge(lookup.rename(columns={'Team': 'home_team', feat_col: home_col}), on='home_team', how='left')
        df = df.merge(lookup.rename(columns={'Team': 'away_team', feat_col: away_col}), on='away_team', how='left')
        df[home_col] = df[home_col].fillna(0)
        df[away_col] = df[away_col].fillna(0)
        return df

    upcoming = merge_allpro(upcoming, weighted_allpro,  'allpro_weighted', 'home_allpro_last_3_years_weighted', 'away_allpro_last_3_years_weighted')
    upcoming = merge_allpro(upcoming, offense_weighted, 'allpro_weighted', 'home_offense_allpro_3_years',        'away_offense_allpro_3_years')
    upcoming = merge_allpro(upcoming, defense_weighted, 'allpro_weighted', 'home_defense_allpro_3_years',        'away_defense_allpro_3_years')

    prev_overall = allpro_df.assign(season=allpro_df['Year']+1).groupby(['season','Team'])['Player'].nunique().reset_index(name='allpro_prev_year')
    prev_offense = offense_df.assign(season=offense_df['Year']+1).groupby(['season','Team'])['Player'].nunique().reset_index(name='allpro_prev_year')
    prev_defense = defense_df.assign(season=defense_df['Year']+1).groupby(['season','Team'])['Player'].nunique().reset_index(name='allpro_prev_year')

    upcoming = merge_allpro(upcoming, prev_overall, 'allpro_prev_year', 'home_allpro_prev_year',         'away_allpro_prev_year')
    upcoming = merge_allpro(upcoming, prev_offense, 'allpro_prev_year', 'home_offense_allpro_prev_year', 'away_offense_allpro_prev_year')
    upcoming = merge_allpro(upcoming, prev_defense, 'allpro_prev_year', 'home_defense_allpro_prev_year', 'away_defense_allpro_prev_year')

    upcoming['diff_allpro_last_3_years_weighted']        = upcoming['home_allpro_last_3_years_weighted']  - upcoming['away_allpro_last_3_years_weighted']
    upcoming['diff_allpro_prev_year']                    = upcoming['home_allpro_prev_year']               - upcoming['away_allpro_prev_year']
    upcoming['allpro_diff_home_off_away_def_3_years']    = upcoming['home_offense_allpro_3_years']         - upcoming['away_defense_allpro_3_years']
    upcoming['allpro_diff_home_def_away_off_3_years ']   = upcoming['home_defense_allpro_3_years']         - upcoming['away_offense_allpro_3_years']   # trailing space matches model
    upcoming['allpro_diff_home_off_away_def_prev_year']  = upcoming['home_offense_allpro_prev_year']       - upcoming['away_defense_allpro_prev_year']
    upcoming['allpro_diff_home_def_away_off_prev_year']  = upcoming['home_defense_allpro_prev_year']       - upcoming['away_offense_allpro_prev_year']

    # ── Group 5 — rolling win pct, scoring, cover rate, league margin ────────
    long_df['rolling_win_pct'] = long_df.groupby('team')['team_win'].transform(
        lambda x: x.shift(1).rolling(5, min_periods=1).mean()
    )
    latest_wp = long_df.groupby('team').last().reset_index()[['team','rolling_win_pct']]
    upcoming  = upcoming.merge(latest_wp.rename(columns={'team':'home_team','rolling_win_pct':'home_rolling_win_pct'}), on='home_team', how='left')
    upcoming  = upcoming.merge(latest_wp.rename(columns={'team':'away_team','rolling_win_pct':'away_rolling_win_pct'}), on='away_team', how='left')

    long_df['rolling_scored']  = long_df.groupby('team')['team_score'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    long_df['rolling_allowed'] = long_df.groupby('team')['opp_score'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    latest_sc = long_df.groupby('team').last().reset_index()[['team','rolling_scored','rolling_allowed']]
    upcoming  = upcoming.merge(latest_sc.rename(columns={'team':'home_team','rolling_scored':'home_rolling_scored','rolling_allowed':'home_rolling_allowed'}), on='home_team', how='left')
    upcoming  = upcoming.merge(latest_sc.rename(columns={'team':'away_team','rolling_scored':'away_rolling_scored','rolling_allowed':'away_rolling_allowed'}), on='away_team', how='left')
    upcoming['scoring_diff']         = upcoming['home_rolling_scored'] - upcoming['away_rolling_scored']
    upcoming['scoring_diff_reverse'] = upcoming['away_rolling_scored'] - upcoming['home_rolling_scored']

    history2 = history.copy()
    history2['home_covered'] = (history2['result'] > history2['spread_line']).astype(int)
    home_cov = history2[['season','week','home_team','home_covered']].rename(columns={'home_team':'team','home_covered':'covered'})
    away_cov = history2[['season','week','away_team','home_covered']].copy()
    away_cov['covered'] = 1 - away_cov['home_covered']
    away_cov = away_cov.rename(columns={'away_team':'team'})
    cover_df = pd.concat([home_cov, away_cov]).sort_values(['team','season','week'])
    cover_df['rolling_cover_rate'] = cover_df.groupby('team')['covered'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    latest_cover = cover_df.groupby('team').last().reset_index()[['team','rolling_cover_rate']]
    upcoming = upcoming.merge(latest_cover.rename(columns={'team':'home_team','rolling_cover_rate':'home_rolling_cover_rate'}), on='home_team', how='left')
    upcoming = upcoming.merge(latest_cover.rename(columns={'team':'away_team','rolling_cover_rate':'away_rolling_cover_rate'}), on='away_team', how='left')
    upcoming['cover_rate_diff'] = upcoming['home_rolling_cover_rate'] - upcoming['away_rolling_cover_rate']

    upcoming['league_rolling_avg_abs_margin_by_week'] = history.groupby('week')['result'].apply(lambda x: x.abs().mean()).iloc[-1]

    # ── Group 6 — sacks, turnovers, third down (from PBP) ───────────────────
    sack_df = pbp_s[pbp_s['sack'] == 1].copy()
    sack_df = sack_df.merge(wk_lookup, on='game_id', how='left')
    sack_df = sack_df[sack_df['week'] < target_week]
    sacks   = sack_df.groupby(['game_id','defteam']).size().reset_index(name='sacks').rename(columns={'defteam':'team'})
    sacks   = sacks.merge(wk_lookup, on='game_id', how='left').sort_values(['team','week'])
    sacks['rolling_sacks'] = sacks.groupby('team')['sacks'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    latest_sacks = sacks.groupby('team').last().reset_index()[['team','rolling_sacks']]
    upcoming = upcoming.merge(latest_sacks.rename(columns={'team':'home_team','rolling_sacks':'home_rolling_sacks'}), on='home_team', how='left')
    upcoming = upcoming.merge(latest_sacks.rename(columns={'team':'away_team','rolling_sacks':'away_rolling_sacks'}), on='away_team', how='left')
    upcoming['sack_diff']         = upcoming['home_rolling_sacks'] - upcoming['away_rolling_sacks']
    upcoming['sack_diff_reverse'] = upcoming['away_rolling_sacks'] - upcoming['home_rolling_sacks']

    pbp_s2 = pbp_s.copy()
    pbp_s2['turnover'] = ((pbp_s2['interception'] == 1) | (pbp_s2['fumble_lost'] == 1)).astype(int)
    to_df = pbp_s2.groupby(['game_id','posteam'])['turnover'].sum().reset_index().rename(columns={'posteam':'team'})
    to_df = to_df.merge(wk_lookup, on='game_id', how='left')
    to_df = to_df[to_df['week'] < target_week].sort_values(['team','week'])
    to_df['rolling_turnovers'] = to_df.groupby('team')['turnover'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    latest_to = to_df.groupby('team').last().reset_index()[['team','rolling_turnovers']]
    upcoming  = upcoming.merge(latest_to.rename(columns={'team':'home_team','rolling_turnovers':'home_rolling_turnovers'}), on='home_team', how='left')
    upcoming  = upcoming.merge(latest_to.rename(columns={'team':'away_team','rolling_turnovers':'away_rolling_turnovers'}), on='away_team', how='left')
    upcoming['turnover_diff']         = upcoming['home_rolling_turnovers'] - upcoming['away_rolling_turnovers']
    upcoming['turnover_diff_reverse'] = upcoming['away_rolling_turnovers'] - upcoming['home_rolling_turnovers']

    pbp_s2['third_att']  = (pbp_s2['down'] == 3).astype(int)
    pbp_s2['third_conv'] = ((pbp_s2['down'] == 3) & (pbp_s2['first_down'] == 1)).astype(int)
    third_df = pbp_s2.groupby(['game_id','posteam']).agg(third_att=('third_att','sum'), third_conv=('third_conv','sum')).reset_index().rename(columns={'posteam':'team'})
    third_df['third_down_rate'] = third_df['third_conv'] / third_df['third_att'].replace(0, 1)
    third_df = third_df.merge(wk_lookup, on='game_id', how='left')
    third_df = third_df[third_df['week'] < target_week].sort_values(['team','week'])
    third_df['rolling_third'] = third_df.groupby('team')['third_down_rate'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    latest_third = third_df.groupby('team').last().reset_index()[['team','rolling_third']]
    upcoming = upcoming.merge(latest_third.rename(columns={'team':'home_team','rolling_third':'home_rolling_third_down'}), on='home_team', how='left')
    upcoming = upcoming.merge(latest_third.rename(columns={'team':'away_team','rolling_third':'away_rolling_third_down'}), on='away_team', how='left')
    upcoming['third_down_diff']         = upcoming['home_rolling_third_down'] - upcoming['away_rolling_third_down']
    upcoming['third_down_diff_reverse'] = upcoming['away_rolling_third_down'] - upcoming['home_rolling_third_down']

    # ── Group 7 — QB switch ──────────────────────────────────────────────────
    home_qbs = history[['season','week','home_team','home_qb_name']].rename(columns={'home_team':'team','home_qb_name':'qb_name'})
    away_qbs = history[['season','week','away_team','away_qb_name']].rename(columns={'away_team':'team','away_qb_name':'qb_name'})
    team_qbs = pd.concat([home_qbs, away_qbs]).sort_values(['team','season','week'])
    last_qb  = team_qbs.groupby('team').last().reset_index()[['team','qb_name']].rename(columns={'qb_name':'last_qb'})
    upcoming = upcoming.merge(last_qb.rename(columns={'team':'home_team','last_qb':'home_last_qb'}), on='home_team', how='left')
    upcoming = upcoming.merge(last_qb.rename(columns={'team':'away_team','last_qb':'away_last_qb'}), on='away_team', how='left')
    upcoming['home_qb_switch'] = (upcoming['home_qb_name'] != upcoming['home_last_qb']).fillna(False)
    upcoming['away_qb_switch'] = (upcoming['away_qb_name'] != upcoming['away_last_qb']).fillna(False)
    upcoming['is_home_qb_new'] = upcoming['home_qb_switch']
    upcoming['is_away_qb_new'] = upcoming['away_qb_switch']

    # ── Group 8 — passer rating (prior season) ───────────────────────────────
    pass_plays = pbp_rp[
        (pbp_rp['play_type'] == 'pass') &
        (pbp_rp['season']    == target_season - 1) &
        (pbp_rp['passer_player_name'].notna())
    ].copy()
    qb_stats = pass_plays.groupby(['season','posteam','passer_player_name']).agg(
        attempts=('pass_attempt','sum'), completions=('complete_pass','sum'),
        yards=('passing_yards','sum'), tds=('pass_touchdown','sum'), ints=('interception','sum')
    ).reset_index()
    qb_stats = qb_stats[qb_stats['attempts'] >= 100]

    def passer_rating(row):
        a = max(0, min(((row['completions']/row['attempts']) - 0.3) * 5,   2.375))
        b = max(0, min(((row['yards']/row['attempts']) - 3) * 0.25,        2.375))
        c = max(0, min(row['tds']/row['attempts'] * 20,                    2.375))
        d = max(0, min(2.375 - (row['ints']/row['attempts'] * 25),         2.375))
        return ((a+b+c+d)/6)*100

    qb_stats['passer_rating'] = qb_stats.apply(passer_rating, axis=1)
    best_qb  = qb_stats.sort_values('attempts', ascending=False).groupby(['season','posteam']).first().reset_index()[['season','posteam','passer_rating']]
    pr_prev  = best_qb[best_qb['season'] == target_season - 1][['posteam','passer_rating']]
    median_pr = pr_prev['passer_rating'].median()
    upcoming = upcoming.merge(pr_prev.rename(columns={'posteam':'home_team','passer_rating':'home_qbr_prev_year'}), on='home_team', how='left')
    upcoming = upcoming.merge(pr_prev.rename(columns={'posteam':'away_team','passer_rating':'away_qbr_prev_year'}), on='away_team', how='left')
    upcoming['home_qbr_prev_year'] = upcoming['home_qbr_prev_year'].fillna(median_pr)
    upcoming['away_qbr_prev_year'] = upcoming['away_qbr_prev_year'].fillna(median_pr)
    upcoming['diff_qbr_prev_year'] = upcoming['home_qbr_prev_year'] - upcoming['away_qbr_prev_year']

    # ── Group 9 — injuries ───────────────────────────────────────────────────
    try:
        raw_inj = nfl.load_injuries(seasons=[target_season])
        inj_df  = raw_inj.to_pandas() if hasattr(raw_inj, 'to_pandas') else pd.DataFrame(raw_inj)
        inj_week = inj_df[(inj_df['report_status'] == 'Out') & (inj_df['week'] == target_week)].copy()
        inj_by_team = inj_week.groupby('team').agg(count=('full_name','count')).reset_index()

        # Basic count
        upcoming = upcoming.merge(inj_by_team.rename(columns={'team':'home_team','count':'home_injured_count'}), on='home_team', how='left')
        upcoming = upcoming.merge(inj_by_team.rename(columns={'team':'away_team','count':'away_injured_count'}), on='away_team', how='left')
        upcoming[['home_injured_count','away_injured_count']] = upcoming[['home_injured_count','away_injured_count']].fillna(0).astype(int)
        upcoming['diff_injured_count'] = upcoming['home_injured_count'] - upcoming['away_injured_count']

        # Injured allpro weighted
        inj_all = inj_df[(inj_df['report_status'] == 'Out') & (inj_df['week'] == target_week)].copy()
        inj_all['season'] = inj_all['season'].astype(int)
        allpro_hist = []
        for yrs_back, weight in zip([0,1,2,3],[4,2,1,0.5]):
            tmp = allpro_df.copy()
            tmp['season'] = tmp['Year'] + yrs_back
            tmp['weight'] = weight
            allpro_hist.append(tmp)
        allpro_wh = pd.concat(allpro_hist)
        inj_all   = inj_all.merge(allpro_wh[['Player','season','Team','weight']], left_on=['full_name','season'], right_on=['Player','season'], how='left')
        inj_all   = inj_all[inj_all['weight'].notnull()]
        inj_wt    = inj_all.groupby(['season','week','team'])['weight'].sum().reset_index().rename(columns={'weight':'inj_ap_wt'})
        upcoming  = upcoming.merge(inj_wt.rename(columns={'team':'home_team'}).drop(columns=['season','week']), on='home_team', how='left').rename(columns={'inj_ap_wt':'home_inj_ap_wt'})
        upcoming  = upcoming.merge(inj_wt.rename(columns={'team':'away_team'}).drop(columns=['season','week']), on='away_team', how='left').rename(columns={'inj_ap_wt':'away_inj_ap_wt'})
        upcoming[['home_inj_ap_wt','away_inj_ap_wt']] = upcoming[['home_inj_ap_wt','away_inj_ap_wt']].fillna(0)
        upcoming['home_active_allpro_weighted'] = upcoming['home_allpro_last_3_years_weighted'] - upcoming['home_inj_ap_wt']
        upcoming['away_active_allpro_weighted'] = upcoming['away_allpro_last_3_years_weighted'] - upcoming['away_inj_ap_wt']
        upcoming['diff_active_allpro_weighted'] = upcoming['home_active_allpro_weighted'] - upcoming['away_active_allpro_weighted']
        upcoming['diff_active_allpro_prev_year']= upcoming['diff_allpro_prev_year']   # approximation

    except Exception as e:
        print(f"  ⚠️  Injury data unavailable: {e} — using zeros")
        for col in ['home_injured_count','away_injured_count','diff_injured_count','diff_active_allpro_weighted','diff_active_allpro_prev_year']:
            upcoming[col] = 0

    # ── Group 10 — coach win pct ─────────────────────────────────────────────
    raw_coach  = nfl.load_schedules(list(range(1999, target_season + 1)))
    coach_hist = raw_coach.to_pandas() if hasattr(raw_coach, 'to_pandas') else pd.DataFrame(raw_coach)
    coach_hist = coach_hist[coach_hist['result'].notna()].copy()
    home_c = coach_hist[['game_id','season','week','home_team','away_team','home_score','away_score','home_coach']].copy()
    home_c.rename(columns={'home_team':'team','away_team':'opponent','home_score':'team_score','away_score':'opponent_score','home_coach':'coach'}, inplace=True)
    away_c = coach_hist[['game_id','season','week','away_team','home_team','away_score','home_score','away_coach']].copy()
    away_c.rename(columns={'away_team':'team','home_team':'opponent','away_score':'team_score','home_score':'opponent_score','away_coach':'coach'}, inplace=True)
    games_df = pd.concat([home_c, away_c], ignore_index=True)
    games_df['win'] = (games_df['team_score'] > games_df['opponent_score']).astype(int)

    def cumulative_coach(group):
        group = group.sort_values(['season','week','game_id']).copy()
        group['cumulative_wins']  = group['win'].cumsum().shift(fill_value=0)
        group['cumulative_games'] = group['win'].expanding().count().shift(fill_value=0)
        return group

    games_df = games_df.groupby('coach', group_keys=False).apply(cumulative_coach)
    games_df['coach_win_pct_prior'] = (
        games_df['cumulative_wins'] / games_df['cumulative_games'].replace(0, np.nan)
    ).fillna(0).round(3)
    coach_lkp = games_df[['game_id','team','coach_win_pct_prior']]
    upcoming  = upcoming.merge(coach_lkp.rename(columns={'team':'home_team','coach_win_pct_prior':'home_coach_win_pct_prior'})[['game_id','home_team','home_coach_win_pct_prior']], on=['game_id','home_team'], how='left')
    upcoming  = upcoming.merge(coach_lkp.rename(columns={'team':'away_team','coach_win_pct_prior':'away_coach_win_pct_prior'})[['game_id','away_team','away_coach_win_pct_prior']], on=['game_id','away_team'], how='left')
    upcoming[['home_coach_win_pct_prior','away_coach_win_pct_prior']] = upcoming[['home_coach_win_pct_prior','away_coach_win_pct_prior']].fillna(0)

    # ── Final check ──────────────────────────────────────────────────────────
    missing = [f for f in model_features if f not in upcoming.columns]
    if missing:
        print(f"  ⚠️  {len(missing)} features missing for week {target_week}: {missing}")
        for m in missing:
            upcoming[m] = 0

    upcoming = upcoming.fillna(upcoming.median(numeric_only=True))
    return upcoming


# ── Run predictions ───────────────────────────────────────────────────────────
def run_predictions(target_week, target_season, full_schedule, pbp_rp, allpro_df):
    print(f"Building features for season {target_season} week {target_week}...")
    upcoming = build_features(target_week, target_season, full_schedule, pbp_rp, allpro_df)
    if upcoming is None or upcoming.empty:
        print("No games found.")
        return None

    X     = upcoming[model_features].copy()
    preds = pipeline.predict(X)

    results = upcoming[['game_id','home_team','away_team','gameday','spread_line']].copy()
    results['predicted_margin'] = preds.round(1)
    results['model_edge']       = (results['predicted_margin'] - results['spread_line']).round(1)
    results['recommendation']   = results.apply(
        lambda r: f"BET HOME ({r['home_team']})" if r['model_edge'] > 0
        else (f"BET AWAY ({r['away_team']})" if r['model_edge'] < 0 else "PASS"),
        axis=1
    )
    results = results.sort_values('model_edge', key=abs, ascending=False)
    print(results[['home_team','away_team','spread_line','predicted_margin','model_edge','recommendation']].to_string(index=False))
    return results


# ── Update results ────────────────────────────────────────────────────────────
def update_results(season, week):
    if not os.path.exists(TRACKER_PATH):
        print("No tracker found — skipping results update")
        return
    print(f"Updating results for season {season} week {week}...")
    tracker = pd.read_csv(TRACKER_PATH)
    raw     = nfl.load_schedules([season])
    sched   = raw.to_pandas() if hasattr(raw, 'to_pandas') else pd.DataFrame(raw)

    # Pull result AND individual scores
    actual  = sched[(sched['season'] == season) & (sched['week'] == week)][
        ['game_id', 'result', 'home_score', 'away_score']
    ].rename(columns={'result': 'actual_margin'})

    if actual['actual_margin'].isna().all():
        print(f"Results not yet available for week {week} — skipping")
        return
    mask    = (tracker['season'] == season) & (tracker['week'] == week)
    indices = tracker[mask].index
    if len(indices) == 0:
        print(f"No predictions found for week {week} — skipping")
        return
    rows = tracker.loc[indices].copy()
    rows = rows.merge(actual, on='game_id', how='left', suffixes=('_old', '_new'))
    rows['actual_margin'] = rows['actual_margin_new']
    rows = rows.drop(columns=['actual_margin_old', 'actual_margin_new'], errors='ignore')
    rows['home_covered']  = (rows['actual_margin'] > rows['spread_line']).astype(int)
    rows['model_correct'] = ((rows['model_edge'] > 0) == (rows['home_covered'] == 1)).astype(int)

    tracker.loc[indices, 'actual_margin'] = rows['actual_margin'].values
    tracker.loc[indices, 'home_covered']  = rows['home_covered'].values
    tracker.loc[indices, 'model_correct'] = rows['model_correct'].values
    tracker.loc[indices, 'home_score']    = rows['home_score'].values
    tracker.loc[indices, 'away_score']    = rows['away_score'].values
    tracker.to_csv(TRACKER_PATH, index=False)

    correct = int(rows['model_correct'].sum())
    total   = len(rows)
    print(f"✅ Week {week} ATS: {correct}/{total} ({correct/total*100:.1f}%)")


# ── Log predictions ───────────────────────────────────────────────────────────
def log_predictions(results_df, season, week, mode):
    log = results_df[['game_id','home_team','away_team','gameday','spread_line','predicted_margin','model_edge','recommendation']].copy()
    log['season']        = season
    log['week']          = week
    log['mode']          = mode
    log['logged_at']     = datetime.now().strftime('%Y-%m-%d %H:%M')
    log['actual_margin'] = None
    log['home_covered']  = None
    log['model_correct'] = None
    log['home_score']    = None
    log['away_score']    = None
    if os.path.exists(TRACKER_PATH):
        tracker = pd.read_csv(TRACKER_PATH)
        mask    = (tracker['season'] == season) & (tracker['week'] == week)
        if mask.any():
            print(f"Replacing existing week {week} predictions ({mode} refresh)...")
            tracker = tracker[~mask]
        updated = pd.concat([tracker, log], ignore_index=True)
        updated.to_csv(TRACKER_PATH, index=False)
    else:
        log.to_csv(TRACKER_PATH, index=False)
    print(f"✅ Week {week} predictions saved ({mode} — {len(log)} games)")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    TARGET_WEEK, PREV_WEEK = get_week_info(TARGET_SEASON)
    if TARGET_WEEK is None:
        print("✅ Season is over — no predictions to run. See you in September!")
        sys.exit(0)

    print(f"Upcoming week: {TARGET_WEEK} | Previous week: {PREV_WEEK}")

    # Load data once — shared across all modes
    print("Loading schedule...")
    raw_schedule  = nfl.load_schedules([TARGET_SEASON])
    full_schedule = raw_schedule.to_pandas() if hasattr(raw_schedule, 'to_pandas') else pd.DataFrame(raw_schedule)
    full_schedule['season'] = full_schedule['season'].astype(int)
    full_schedule['week']   = full_schedule['week'].astype(int)

    print("Loading PBP data (this takes ~60s)...")
    raw_pbp = nfl.load_pbp([TARGET_SEASON, TARGET_SEASON - 1])
    pbp     = raw_pbp.to_pandas() if hasattr(raw_pbp, 'to_pandas') else pd.DataFrame(raw_pbp)
    pbp_rp  = pbp[
        pbp['play_type'].isin(['run','pass']) &
        pbp['posteam'].notna() &
        pbp['defteam'].notna()
    ].copy()
    print(f"PBP loaded: {pbp_rp.shape} | Seasons: {sorted(pbp_rp['season'].unique())}")

    if MODE == 'monday':
        if PREV_WEEK:
            update_results(TARGET_SEASON, PREV_WEEK)
        if TARGET_WEEK:
            results = run_predictions(TARGET_WEEK, TARGET_SEASON, full_schedule, pbp_rp, allpro_df)
            if results is not None:
                log_predictions(results, TARGET_SEASON, TARGET_WEEK, mode='monday')

    elif MODE == 'thursday':
        if TARGET_WEEK:
            results = run_predictions(TARGET_WEEK, TARGET_SEASON, full_schedule, pbp_rp, allpro_df)
            if results is not None:
                log_predictions(results, TARGET_SEASON, TARGET_WEEK, mode='thursday')

    elif MODE == 'sunday':
        if TARGET_WEEK:
            results = run_predictions(TARGET_WEEK, TARGET_SEASON, full_schedule, pbp_rp, allpro_df)
            if results is not None:
                log_predictions(results, TARGET_SEASON, TARGET_WEEK, mode='sunday')

    else:
        print(f"Unknown mode: {MODE}. Use monday, thursday, or sunday.")