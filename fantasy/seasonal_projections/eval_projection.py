"""Projection-quality evaluation for the seasonal model, scored on POINTS PER GAME.

This replaces finishing-rank as the board's headline evaluation. Rank is misleading for a
projection (a tight cluster flips many ranks on a tiny PPG gap); what matters is how close
the projected half-PPR PPG is to actual. We report a full metric panel, games-weighted,
walk-forward, with 2025 as the live test, for our model vs Sleeper vs naive baselines vs
the ensemble blend.

Metrics:
  MAE     mean absolute error (PPG)         - headline accuracy
  RMSE    root mean sq error                - punishes big misses (booms/busts)
  bias    mean(pred-actual)                 - systematic over/under-projection
  medAE   median absolute error             - robust-to-outlier accuracy
  r       Pearson corr(pred, actual)        - does the spread of projections track reality
  R2      variance explained                - overall fit
  hit3    % of players projected within 3 PPG of actual - intuitive accuracy

Run:  python eval_projection.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import value_eval as ve
from college_rookie_test import attach_college, COLLEGE

ORTHO = avm.SITU + avm.BIAS + COLLEGE
GPS = 17
BLEND_W = 0.20   # our weight in the ours/Sleeper PPG blend (rest Sleeper)


def make_predictions(test_seasons=range(2021, 2026), drafted_max=180):
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()].copy()
    preds = []
    for N in test_seasons:
        tr = pool[pool["season"] < N]
        te = pool[pool["season"] == N].copy()
        if len(te) < 20 or len(tr) < 150:
            continue
        feats = [c for c in ORTHO if c in tr.columns] + ["position"]
        te["our_ppg"] = ve._cat_fit(tr[feats].copy(), tr["target_ppg"], te[feats].copy(),
                                    w=tr["sample_weight"].clip(lower=1))
        preds.append(te)
    allp = pd.concat(preds, ignore_index=True)
    allp["sleeper_ppg"] = allp["sleeper_pts_half_ppr"] / GPS
    allp["naive_prior"] = allp["prior_ppg"]
    allp["naive_3yr"] = allp["ppg_3yr"]
    # ensemble: blend our model with Sleeper (fallback to whichever is present)
    s = allp["sleeper_ppg"]
    allp["blend_ppg"] = np.where(s.notna(), BLEND_W * allp["our_ppg"] + (1 - BLEND_W) * s, allp["our_ppg"])
    return allp


def metrics(frame, col, actual="target_ppg", wcol="sample_weight"):
    g = frame.dropna(subset=[col, actual]).copy()
    if len(g) < 5:
        return None
    e = g[col].values - g[actual].values
    w = g[wcol].clip(lower=1).values.astype(float)
    mae = np.sum(np.abs(e) * w) / np.sum(w)
    rmse = np.sqrt(np.sum(e ** 2 * w) / np.sum(w))
    bias = np.sum(e * w) / np.sum(w)
    medae = float(np.median(np.abs(e)))
    r = float(np.corrcoef(g[col], g[actual])[0, 1]) if g[col].std() > 0 else np.nan
    ss_res = np.sum(w * e ** 2)
    ss_tot = np.sum(w * (g[actual].values - np.average(g[actual].values, weights=w)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    hit3 = float(np.average(np.abs(e) < 3, weights=w))
    return dict(n=len(g), MAE=mae, RMSE=rmse, bias=bias, medAE=medae, r=r, R2=r2, hit3=hit3)


MODELS = {"OUR": "our_ppg", "BLEND (.2/.8)": "blend_ppg", "Sleeper": "sleeper_ppg",
          "naive last-yr": "naive_prior", "naive 3yr": "naive_3yr"}


def panel(frame, title):
    print(f"\n=== {title}  (n={len(frame)}, games-weighted) ===")
    print(f"  {'model':15s} {'MAE':>5} {'RMSE':>5} {'bias':>6} {'medAE':>6} {'r':>5} {'R2':>6} {'hit<3':>6}")
    for name, col in MODELS.items():
        m = metrics(frame, col)
        if m:
            print(f"  {name:15s} {m['MAE']:5.2f} {m['RMSE']:5.2f} {m['bias']:+6.2f} "
                  f"{m['medAE']:6.2f} {m['r']:5.2f} {m['R2']:6.2f} {m['hit3']*100:5.0f}%")


def by_position(frame, col="our_ppg"):
    print(f"\n=== OUR model MAE/r by position (pooled) ===")
    print(f"  {'pos':4s} {'n':>4} {'MAE':>5} {'Sleeper':>8} {'blend':>6} {'r':>5}")
    for pos in ["QB", "RB", "WR", "TE"]:
        g = frame[frame["position"] == pos]
        mo, ms, mb = metrics(g, "our_ppg"), metrics(g, "sleeper_ppg"), metrics(g, "blend_ppg")
        if mo:
            print(f"  {pos:4s} {mo['n']:>4} {mo['MAE']:5.2f} {ms['MAE']:8.2f} {mb['MAE']:6.2f} {mo['r']:5.2f}")


def main():
    allp = make_predictions()
    panel(allp, "POOLED 2021-2025")
    panel(allp[allp["season"] == 2025], "2025 LIVE TEST")
    by_position(allp)
    print("\nnotes: bias + = over-projects; lower MAE/RMSE/medAE better; higher r/R2/hit<3 better.")
    print("Sleeper PPG is its season-total projection / 17 (slightly understates injury-risk PPG).")


if __name__ == "__main__":
    main()
