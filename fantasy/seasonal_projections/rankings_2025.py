"""Show 2025 rankings from our BEST standalone model (no Sleeper blend).

Trains the tree ensemble (LightGBM + RandomForest + XGBoost, our best standalone in the
bakeoff) on seasons < 2025, projects 2025 half-PPR PPG for the drafted pool, and ranks by
the projection. Finds the position our model ranked best (highest proj-vs-actual rank corr)
and prints the full table: Proj PPG, Actual PPG, Proj Rank, Actual Rank.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college

ENS = {
    "lgbm": dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8),
    "rf":   dict(n_estimators=400, max_depth=8, min_samples_leaf=5),
    "xgb":  dict(max_depth=4, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8),
}


def predict_2025():
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    feats = [c for c in mb.FEATS if c in df.columns]
    tr = df[(df["target_ppg"].notna()) & (df["season"] < 2025)]
    te = df[(df["season"] == 2025) & (df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    P = np.zeros(len(te))
    for fam, pr in ENS.items():
        P += mb.fit_predict(fam, pr, tr, te, feats)
    te["proj_ppg"] = P / len(ENS)
    te["actual_ppg"] = te["target_ppg"]
    return te


def main():
    te = predict_2025()
    print("Per-position accuracy of our best standalone model on 2025 (drafted pool):")
    print(f"  {'pos':4s} {'n':>3} {'MAE':>5} {'rankρ':>6}")
    summ = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        g = te[te["position"] == pos]
        if len(g) < 5:
            continue
        mae = (g["proj_ppg"] - g["actual_ppg"]).abs().mean()
        rho = g["proj_ppg"].rank().corr(g["actual_ppg"].rank())
        summ[pos] = rho
        print(f"  {pos:4s} {len(g):>3} {mae:5.2f} {rho:6.2f}")
    best = max(summ, key=summ.get)
    print(f"\n  best-ranked position (proj-vs-actual rank corr): {best} (ρ={summ[best]:.2f})\n")

    g = te[te["position"] == best].copy()
    g["Proj Rank"] = g["proj_ppg"].rank(ascending=False, method="min").astype(int)
    g["Actual Rank"] = g["actual_ppg"].rank(ascending=False, method="min").astype(int)
    g = g.sort_values("Proj Rank")
    print(f"=== 2025 {best} rankings — our best standalone model (tree ensemble, NO Sleeper) ===")
    print(f"  {'Player':22s} {'ProjPPG':>7} {'ActPPG':>7} {'ProjRk':>6} {'ActRk':>6}  {'miss':>5}")
    for _, r in g.iterrows():
        d = int(r["Proj Rank"] - r["Actual Rank"])
        print(f"  {r['player'][:22]:22s} {r['proj_ppg']:7.1f} {r['actual_ppg']:7.1f} "
              f"{best}{int(r['Proj Rank']):<4d} {best}{int(r['Actual Rank']):<4d}  {d:+5d}")


if __name__ == "__main__":
    main()
