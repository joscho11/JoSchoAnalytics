"""Evaluate the seasonal model on SEASON-TOTAL half-PPR points (the value-relevant target).

PPG flatters the model by hiding availability. Total points = PPG x games is what wins
leagues, and it's where injuries/availability actually matter. It's also where Sleeper's
projection lives natively (it projects season totals), so this is the fairest head-to-head
(no /17 conversion).

Our total = PPG_pred (LightGBM) x games_pred (LightGBM availability model). We also test
PPG_pred x 16.5 (constant games) to see whether modeling availability earns its keep, and a
blend with Sleeper. Walk-forward, 2025 live test, per position.

Caveat: actual_total = target_ppg x target_games, so this scores players who played >= 3
games (the drafted pool is ~90%+ of them). The most extreme injury busts (<3 games) aren't
scored here -- a documented limitation, not a bug.

Run:  python eval_totals.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college

LGBM = ("lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8))
CONST_GAMES = 16.5
BLEND_W = 0.20


def metrics(g, col, actual="actual_total"):
    g = g.dropna(subset=[col, actual])
    if len(g) < 5:
        return None
    e = g[col].values - g[actual].values
    mae = np.mean(np.abs(e))
    rmse = np.sqrt(np.mean(e ** 2))
    bias = np.mean(e)
    r = float(np.corrcoef(g[col], g[actual])[0, 1]) if g[col].std() > 0 else np.nan
    ss = np.sum((g[actual] - g[actual].mean()) ** 2)
    r2 = 1 - np.sum(e ** 2) / ss if ss > 0 else np.nan
    return dict(n=len(g), MAE=mae, RMSE=rmse, bias=bias, r=r, R2=r2)


def run(test_seasons=range(2021, 2026), drafted_max=180):
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    feats = [c for c in mb.FEATS if c in df.columns]
    ppg_feats = [c for c in feats if c not in ("prior_games_missed", "missed_prior_season")]  # PPG: drop injury
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()].copy()
    tr_ppg = df[df["target_ppg"].notna()]
    tr_g = df[df["target_games"].notna()]

    chunks = []
    for N in test_seasons:
        te = pool[pool["season"] == N].copy()
        if len(te) < 20:
            continue
        te["ppg_pred"] = mb.fit_predict(LGBM[0], LGBM[1], tr_ppg[tr_ppg.season < N], te, ppg_feats)
        te["games_pred"] = np.clip(mb.fit_predict(LGBM[0], LGBM[1], tr_g[tr_g.season < N], te, feats,
                                                  ), 1, 17)  # availability model
        chunks.append(te)
    a = pd.concat(chunks, ignore_index=True)

    a["actual_total"] = a["target_ppg"] * a["target_games"]
    a["our_modelgames"] = a["ppg_pred"] * a["games_pred"]
    a["our_constgames"] = a["ppg_pred"] * CONST_GAMES
    a["sleeper"] = a["sleeper_pts_half_ppr"]
    a["naive_lastyr"] = a["prior_half_ppr"]
    s = a["sleeper"]
    a["blend"] = np.where(s.notna(), BLEND_W * a["our_modelgames"] + (1 - BLEND_W) * s, a["our_modelgames"])

    models = {"OUR (ppg×games)": "our_modelgames", "OUR (ppg×16.5)": "our_constgames",
              "BLEND .2/.8": "blend", "Sleeper": "sleeper", "naive last-yr": "naive_lastyr"}

    def panel(frame, title):
        print(f"\n=== {title}  (n={len(frame)}) — SEASON TOTAL half-PPR points ===")
        print(f"  {'model':18s} {'MAE':>6} {'RMSE':>6} {'bias':>7} {'r':>5} {'R2':>6}")
        for nm, col in models.items():
            m = metrics(frame, col)
            if m:
                print(f"  {nm:18s} {m['MAE']:6.1f} {m['RMSE']:6.1f} {m['bias']:+7.1f} {m['r']:5.2f} {m['R2']:6.2f}")

    panel(a, "POOLED 2021-2025")
    panel(a[a.season == 2025], "2025 LIVE TEST")
    # does the availability model beat constant games?
    mg, cg = metrics(a, "our_modelgames"), metrics(a, "our_constgames")
    print(f"\n  availability model vs constant 16.5 games (pooled MAE): "
          f"{mg['MAE']:.1f} vs {cg['MAE']:.1f}  -> games model {'HELPS' if mg['MAE']<cg['MAE'] else 'does NOT help'} "
          f"({cg['MAE']-mg['MAE']:+.1f})")


if __name__ == "__main__":
    run()
