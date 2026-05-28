"""Totals model baseline (v3.5 — canonical totals feature set).

Final feature set after three iterations of exploration (see CLAUDE.md
Active Experiments). Best CV result on 6-fold walk-forward (2020-2025):
  - 2-voter consensus UNDER (XGBoost + Ridge agree): 55.7% on n=575
  - Random Forest best single model: 53.3% ± 2.1%
  - XGBoost: 52.3% ± 1.9%

14 totals-specific features on top of the existing 35 spread features:
  v2 base (12): total_line, home_implied_pts, away_implied_pts, temp_f,
                wind_mph, is_dome, home_pts_scored_5g, home_pts_allowed_5g,
                away_pts_scored_5g, away_pts_allowed_5g, combined_pts_5g,
                league_avg_total_4wk
  v3.5 new (2): pace_5g (PBP-derived), div_game (binary categorical)

Excluded after multicollinearity ablation (helped XGB +0.7pp but hurt
Ridge -0.9pp): abs_spread, rest_diff, sum_pr_prev_year, sum_active_allpro,
outdoor_wind_mph, team_total_combined. All linear combinations of
features in the spread set.

Target: total_diff = total_points - total_line (mean-centered residual).

Next session: promote this script into betting/totals_features.ipynb +
betting/totals_model.ipynb + betting/predict_totals.ipynb, mirroring
the spread side's notebook structure.
"""
import argparse, json, sys, time, warnings
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))
from tune_time_decay import load_prep_cells, decay_weights, MODELS


def build_totals_features_v3_5(ns):
    g = ns['g']
    sched = ns['sched']

    # ── Re-merge scores + raw roof string (roof in g is ordinal-encoded) ─────
    aux = sched[['game_id', 'home_score', 'away_score', 'roof']].rename(
        columns={'roof': 'roof_str'})
    g = g.merge(aux, on='game_id', how='left')
    g['total_points'] = g['home_score'] + g['away_score']

    # Implied team totals
    g['home_implied_pts'] = (g['total_line'] + g['spread_line']) / 2.0
    g['away_implied_pts'] = (g['total_line'] - g['spread_line']) / 2.0

    # is_dome (using raw string — bug fix from v2)
    g['is_dome'] = g['roof_str'].fillna('outdoors').isin(['dome', 'closed']).astype(int)
    n_dome = g['is_dome'].sum()
    print(f"  is_dome: {n_dome:,} games detected ({n_dome/len(g)*100:.1f}%)")

    # Weather (neutralize for domes)
    weather_path = ROOT / 'betting/nfl_weather_2014_2025.csv'
    if weather_path.exists():
        wx = pd.read_csv(weather_path)[['game_id', 'temp_f', 'wind_mph']]
        g = g.merge(wx, on='game_id', how='left')
        dome_mask = g['is_dome'] == 1
        g.loc[dome_mask, 'temp_f'] = 70.0
        g.loc[dome_mask, 'wind_mph'] = 0.0
        g['temp_f']   = g['temp_f'].fillna(g['temp_f'].mean())
        g['wind_mph'] = g['wind_mph'].fillna(g['wind_mph'].mean())
        print(f"  Weather merged: {len(wx):,} games covered")

    # Rolling points per team
    hg = sched[['game_id', 'season', 'week', 'home_team', 'home_score', 'away_score']].rename(
        columns={'home_team': 'team', 'home_score': 'pts_scored', 'away_score': 'pts_allowed'})
    ag = sched[['game_id', 'season', 'week', 'away_team', 'away_score', 'home_score']].rename(
        columns={'away_team': 'team', 'away_score': 'pts_scored', 'home_score': 'pts_allowed'})
    long_pts = pd.concat([hg, ag], ignore_index=True).sort_values(['team', 'season', 'week'])
    for col in ['pts_scored', 'pts_allowed']:
        long_pts[f'rolling_{col}_5g'] = (long_pts.groupby('team')[col]
            .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean()))

    home_pts = long_pts[['game_id', 'team', 'rolling_pts_scored_5g', 'rolling_pts_allowed_5g']].rename(
        columns={'team': 'home_team',
                 'rolling_pts_scored_5g':  'home_pts_scored_5g',
                 'rolling_pts_allowed_5g': 'home_pts_allowed_5g'})
    away_pts = long_pts[['game_id', 'team', 'rolling_pts_scored_5g', 'rolling_pts_allowed_5g']].rename(
        columns={'team': 'away_team',
                 'rolling_pts_scored_5g':  'away_pts_scored_5g',
                 'rolling_pts_allowed_5g': 'away_pts_allowed_5g'})
    g = g.merge(home_pts, on=['game_id', 'home_team'], how='left')
    g = g.merge(away_pts, on=['game_id', 'away_team'], how='left')
    g['combined_pts_5g'] = (g['home_pts_scored_5g'] + g['home_pts_allowed_5g'] +
                            g['away_pts_scored_5g'] + g['away_pts_allowed_5g']) / 4.0
    for c in ['home_pts_scored_5g', 'home_pts_allowed_5g',
              'away_pts_scored_5g', 'away_pts_allowed_5g', 'combined_pts_5g']:
        g[c] = g[c].fillna(g[c].mean())

    # League scoring environment
    sc = sched[sched['home_score'].notna()].copy()
    sc['game_total'] = sc['home_score'] + sc['away_score']
    weekly_avg = (sc.groupby(['season', 'week'])['game_total']
                  .mean().reset_index().rename(columns={'game_total': 'week_avg_total'}))
    weekly_avg['league_avg_total_4wk'] = (weekly_avg.groupby('season')['week_avg_total']
        .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean()))
    g = g.merge(weekly_avg[['season', 'week', 'league_avg_total_4wk']], on=['season', 'week'], how='left')
    g['league_avg_total_4wk'] = g['league_avg_total_4wk'].fillna(g['league_avg_total_4wk'].mean())

    # Pace (rolling 5-game plays per team, avg of both teams)
    pbp_full = ns['pbp_full']
    plays_per_game = (pbp_full[pbp_full['posteam'].notna()]
                      .groupby(['game_id', 'posteam']).size().reset_index(name='plays'))
    pace_long = plays_per_game.rename(columns={'posteam': 'team'})
    week_lkp = sched[['game_id', 'season', 'week']]
    pace_long = pace_long.merge(week_lkp, on='game_id', how='left').sort_values(['team', 'season', 'week'])
    pace_long['rolling_pace_5g'] = (pace_long.groupby('team')['plays']
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean()))
    pace_home = pace_long[['game_id', 'team', 'rolling_pace_5g']].rename(
        columns={'team': 'home_team', 'rolling_pace_5g': 'home_pace_5g'})
    pace_away = pace_long[['game_id', 'team', 'rolling_pace_5g']].rename(
        columns={'team': 'away_team', 'rolling_pace_5g': 'away_pace_5g'})
    g = g.merge(pace_home, on=['game_id', 'home_team'], how='left')
    g = g.merge(pace_away, on=['game_id', 'away_team'], how='left')
    g['pace_5g'] = (g['home_pace_5g'] + g['away_pace_5g']) / 2.0
    g['pace_5g'] = g['pace_5g'].fillna(g['pace_5g'].mean())

    # div_game (already in g from mc cell 30, just ensure int)
    g['div_game'] = g['div_game'].fillna(0).astype(int)

    g = g.drop(columns=['roof_str', 'home_pace_5g', 'away_pace_5g'], errors='ignore')
    ns['g'] = g

    TOTALS_FEATURES = [
        'total_line', 'home_implied_pts', 'away_implied_pts',
        'temp_f', 'wind_mph', 'is_dome',
        'home_pts_scored_5g', 'home_pts_allowed_5g',
        'away_pts_scored_5g', 'away_pts_allowed_5g',
        'combined_pts_5g', 'league_avg_total_4wk',
        'pace_5g', 'div_game',
    ]
    return TOTALS_FEATURES


# ── Walk-forward CV + eval (inlined here so v3.5 is self-contained) ─────────
def totals_acc(preds, total_line, actual_total):
    pred_over = preds > total_line
    actual_over = actual_total > total_line
    push = actual_total == total_line
    valid = ~push
    if not valid.any():
        return 0.0
    return float(((pred_over == actual_over) & valid).sum()) / float(valid.sum())


def make_cv_folds(train_start=2014):
    return [{"train": list(range(train_start, ty)), "test": [ty]}
            for ty in [2020, 2021, 2022, 2023, 2024, 2025]]


def build_fold_data(folds, ns, feature_cols):
    g = ns['g']
    out = []
    for fold in folds:
        tr_m = g["season"].isin(fold["train"])
        te_m = g["season"].isin(fold["test"])
        _wk = (g.loc[tr_m].groupby("week")["total_points"]
                          .apply(lambda x: x.abs().mean()))
        g_fold = g.copy()
        g_fold["league_rolling_avg_abs_margin_by_week"] = (
            g_fold["week"].map(_wk).fillna(_wk.mean()))
        y_tr_diff = (g_fold.loc[tr_m, "total_points"] - g_fold.loc[tr_m, "total_line"]).values.astype("float32")
        y_te_diff = (g_fold.loc[te_m, "total_points"] - g_fold.loc[te_m, "total_line"]).values.astype("float32")
        X_tr = g_fold.loc[tr_m, feature_cols].fillna(0).values.astype("float32")
        X_te = g_fold.loc[te_m, feature_cols].fillna(0).values.astype("float32")
        total_line_te = g_fold.loc[te_m, "total_line"].fillna(0).values
        actual_total_te = g_fold.loc[te_m, "total_points"].fillna(0).values
        out.append({"yr": fold["test"][0],
                    "X_tr": X_tr, "y_tr": y_tr_diff,
                    "X_te": X_te, "y_te": y_te_diff,
                    "total_line_te": total_line_te, "actual_total_te": actual_total_te,
                    "tr_seasons": g_fold.loc[tr_m, "season"].values.astype("int32"),
                    "max_train_year": int(max(fold["train"])),
                    "n_train": len(X_tr)})
    return out


def cv_eval(run_fn, alpha, fold_data):
    accs, maes = [], []
    for fd in fold_data:
        w = decay_weights(fd, alpha)
        fd_for_model = {
            "X_tr": fd["X_tr"], "y_tr": fd["y_tr"],
            "X_te": fd["X_te"], "y_te": fd["y_te"],
            "sp": fd["total_line_te"], "tr_seasons": fd["tr_seasons"],
            "max_train_year": fd["max_train_year"],
        }
        preds_diff = run_fn(fd_for_model, w)
        preds_total = fd["total_line_te"] + preds_diff
        accs.append(totals_acc(preds_total, fd["total_line_te"], fd["actual_total_te"]))
        maes.append(float(np.abs(preds_diff - fd["y_te"]).mean()))
    return {"alpha": alpha, "fold_hit": accs, "fold_mae_diff": maes,
            "mean_hit": float(np.mean(accs)), "std_hit": float(np.std(accs)),
            "mean_mae_diff": float(np.mean(maes))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="totals_baseline_v3_5_results.json")
    args = ap.parse_args()
    label = "Totals v3.5 (Ridge-friendly: drop multicollinear derived feats)"
    print(f"\n{label}")

    ns = load_prep_cells(earliest=2014)
    new_features = build_totals_features_v3_5(ns)
    feature_cols = list(ns['avail']) + new_features
    g = ns['g']
    g = g[g['total_line'].notna() & g['total_points'].notna()].copy()
    ns['g'] = g
    print(f"  Filter: → {len(g):,} games")
    print(f"  Feature count: {len(ns['avail'])} spread + {len(new_features)} totals = {len(feature_cols)}")
    print()

    fold_data = build_fold_data(make_cv_folds(2014), ns, feature_cols)

    results = []
    for model_name, run_fn in MODELS:
        t = time.time()
        r = cv_eval(run_fn, 0.0, fold_data)
        r["model"] = model_name
        r["train_start"] = 2014
        results.append(r)
        print(f"  {model_name:14}  α=0.00  "
              f"hit={r['mean_hit']:.1%} ± {r['std_hit']:.1%}  "
              f"MAE-diff={r['mean_mae_diff']:.2f}  ({time.time()-t:.1f}s)")

    # Consensus filter analysis inline
    print(f"\n{'='*78}\n  Consensus filter (Ridge + XGBoost agree)\n{'='*78}")
    import numpy as np
    ridge_o, xgb_o, actual = [], [], []
    for fd in fold_data:
        fd_for_model = {
            "X_tr": fd["X_tr"], "y_tr": fd["y_tr"], "X_te": fd["X_te"], "y_te": fd["y_te"],
            "sp": fd["total_line_te"], "tr_seasons": fd["tr_seasons"],
            "max_train_year": fd["max_train_year"],
        }
        push = fd["actual_total_te"] == fd["total_line_te"]
        valid = ~push
        for name, fn in MODELS:
            if name == 'Ridge':
                ridge_diff = fn(fd_for_model, None)
                ridge_o.extend((ridge_diff[valid] > 0).tolist())
            elif name == 'XGBoost':
                xgb_diff = fn(fd_for_model, None)
                xgb_o.extend((xgb_diff[valid] > 0).tolist())
        actual.extend((fd["actual_total_te"][valid] > fd["total_line_te"][valid]).tolist())
    ridge_o = np.array(ridge_o); xgb_o = np.array(xgb_o); actual = np.array(actual)
    both_over = ridge_o & xgb_o
    both_under = ~ridge_o & ~xgb_o
    disagree = ridge_o != xgb_o

    over_hit  = (actual[both_over]  == True ).mean() if both_over.sum()  else 0
    under_hit = (actual[both_under] == False).mean() if both_under.sum() else 0
    overall   = (((actual[both_over]==True).sum() + (actual[both_under]==False).sum())
                 / (both_over.sum() + both_under.sum()))
    print(f"  Both OVER  picks: {both_over.sum():>5}   hit-rate: {over_hit*100:.1f}%")
    print(f"  Both UNDER picks: {both_under.sum():>5}   hit-rate: {under_hit*100:.1f}%")
    print(f"  Disagree (PASS):  {disagree.sum():>5}")
    print(f"  Consensus overall: {overall*100:.1f}% on {(both_over.sum()+both_under.sum())/len(actual)*100:.1f}% of games")

    out_path = HERE / args.out
    out_path.write_text(json.dumps({
        "label": label, "feature_cols": feature_cols, "new_features": new_features,
        "results": results,
        "consensus": {
            "both_over_n": int(both_over.sum()),  "both_over_hit": float(over_hit),
            "both_under_n": int(both_under.sum()), "both_under_hit": float(under_hit),
            "disagree_n": int(disagree.sum()), "consensus_overall": float(overall),
        },
    }, indent=2))
    print(f"\nWrote {out_path}")

    print(f"\n{'='*78}\n  v3.5 SUMMARY — break-even = 52.4%\n{'='*78}")
    for r in results:
        marker = " ✓" if r["mean_hit"] > 0.524 else "  "
        print(f"  {r['model']:14}  {r['mean_hit']:.1%} ± {r['std_hit']:.1%}{marker}")


if __name__ == "__main__":
    main()
