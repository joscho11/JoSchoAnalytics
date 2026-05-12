# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This folder contains a fantasy football half-PPR points prediction system for NFL skill position players (QB, RB, WR, TE). It is a sub-project of BettingEdge, built as a standalone ML pipeline with three notebooks and a trained model.

## Notebook Pipeline (run in order)

| Notebook | Input | Output | Purpose |
|----------|-------|--------|---------|
| `data_pipeline.ipynb` | nflreadpy (live) | `raw_dataset.csv` | Pulls and joins player stats, schedules, injury reports, depth charts |
| `features.ipynb` | `raw_dataset.csv` | `features_dataset.csv` | Engineers rolling windows, trends, weather, injury/availability features |
| `model.ipynb` | `features_dataset.csv` | `models/*.pkl` | Trains and evaluates per-position XGBoost models |

## Dataset

**`features_dataset.csv`** — 30,213 rows × 59 columns, seasons 2020–2025

**Target:** `target_half_ppr` — half-PPR fantasy points scored in week W+1 (forward-looking; week W features predict week W+1 output)

**Identity columns** (never used as model features): `player_id`, `player_display_name`, `position`, `team`, `opponent_team`, `season`, `week`

**Feature groups:**
- Rolling 3-week & 5-week averages: fantasy points, targets, receptions, yards, TDs, carries, target share, air yards share, WOPR, expected points (`_roll3` / `_roll5` suffix)
- Trend features (3-week minus 5-week average): `fantasy_points_half_ppr_trend`, `targets_trend`, `target_share_trend`, `air_yards_share_trend`, `wopr_trend`, `carries_trend`
- Matchup context: `def_pts_allowed_roll4`, `implied_team_total`, `is_home`
- Weather/field: `days_rest`, `is_dome`, `effective_wind`, `effective_temp`, `is_turf`
- Player injury: `injury_status_score`, `practice_status_score` (0.0–1.0 composite)
- Teammate availability: `starter_qb/rb/wr/te_availability`
- Opponent defensive availability: `opp_cb1/olb1/ilb1/mlb1/de1/dt1/fs1/ss1_availability`
- OL availability: `starter_tackle/guard/center_availability`
- `depth_chart_position` (1=starter, NaN filled with 3)

## Model Architecture

- **One XGBoost regressor per position** (QB, RB, WR, TE) — positions have different statistical profiles and feature relevance
- **Train/test split:** seasons 2020–2024 train, 2025 holdout (time-based, never shuffle across seasons to avoid leakage)
- **Saved to:** `models/{position}_model.pkl` via joblib
- **Evaluation metrics:** MAE and RMSE per position

## Key Constraints

- **No data leakage:** Always split on season boundaries. Never use `sklearn.model_selection.train_test_split` with `shuffle=True` on this data.
- **Identity columns must be dropped** before fitting any model — they are only for tracing predictions back to players.
- **`raw_dataset.csv` is not the model input** — always use `features_dataset.csv`. The raw dataset contains current-week game stats that would leak the target.
- **`nfl_allpro_1997_2025.csv`** (in the parent directory) must be updated manually each January for the new season before re-running `data_pipeline.ipynb`.
