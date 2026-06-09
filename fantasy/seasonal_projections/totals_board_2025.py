"""Best season-TOTAL projection for 2025, with a full position table.

Best method (from eval_totals): rate model (LightGBM PPG, injury features removed) x a
constant games estimate (the availability model HURT, so we don't use it), blended with
Sleeper's native season-total projection. Blend weight is tuned on 2021-2024 and applied to
2025 (no peeking). Picks the position our projection ranked best and prints every drafted
player: Proj Pts, Actual Pts, Pts Diff, Proj Rank, Actual Rank, Rank Diff.
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


def wmae(p, a):
    return float(np.mean(np.abs(np.asarray(p) - np.asarray(a))))


def build():
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    ppg_feats = [c for c in mb.FEATS if c in df.columns and c not in ("prior_games_missed", "missed_prior_season")]
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    tr_ppg = df[df["target_ppg"].notna()]

    chunks = []
    for N in range(2021, 2026):
        te = pool[pool["season"] == N].copy()
        if len(te) < 20:
            continue
        te["ppg_pred"] = mb.fit_predict(LGBM[0], LGBM[1], tr_ppg[tr_ppg.season < N], te, ppg_feats)
        gconst = pool[pool["season"] < N]["target_games"].mean()   # leak-safe constant games
        te["our"] = te["ppg_pred"] * gconst
        chunks.append(te)
    a = pd.concat(chunks, ignore_index=True)
    a["actual_total"] = a["target_ppg"] * a["target_games"]
    a["sleeper"] = a["sleeper_pts_half_ppr"]

    # tune blend weight on 2021-2024 (not 2025)
    dev = a[(a.season < 2025) & a["sleeper"].notna()]
    bestw, bestm = 0.0, 1e9
    for w in np.arange(0, 0.61, 0.05):
        m = wmae(w * dev["our"] + (1 - w) * dev["sleeper"], dev["actual_total"])
        if m < bestm:
            bestm, bestw = m, w
    s = a["sleeper"]
    a["blend"] = np.where(s.notna(), bestw * a["our"] + (1 - bestw) * s, a["our"])
    return a, bestw


def main():
    a, w = build()
    a25 = a[a.season == 2025].copy()
    print(f"blend weight (tuned on 2021-24): {w:.2f}*our + {1-w:.2f}*Sleeper\n")
    print("2025 season-total MAE — pick the best method:")
    for nm, col in [("our (rate×games)", "our"), ("Sleeper", "sleeper"), ("BLEND", "blend")]:
        g = a25.dropna(subset=[col, "actual_total"])
        print(f"  {nm:18s} MAE {wmae(g[col], g['actual_total']):.1f}")
    best_col = min([("our", a25), ("sleeper", a25), ("blend", a25)],
                   key=lambda t: wmae(t[1].dropna(subset=[t[0]])[t[0]], t[1].dropna(subset=[t[0]])["actual_total"]))[0]
    print(f"  -> best method: {best_col}\n")

    print("Best method, 2025 per-position rank corr (proj vs actual):")
    summ = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        g = a25[a25.position == pos].dropna(subset=[best_col, "actual_total"])
        if len(g) < 5:
            continue
        summ[pos] = g[best_col].rank().corr(g["actual_total"].rank())
        print(f"  {pos}: ρ={summ[pos]:.2f} (n={len(g)})")
    bp = max(summ, key=summ.get)
    print(f"  -> best position: {bp}\n")

    g = a25[a25.position == bp].dropna(subset=[best_col, "actual_total"]).copy()
    g["ProjPts"] = g[best_col].round(0).astype(int)
    g["ActPts"] = g["actual_total"].round(0).astype(int)
    g["PtsDiff"] = (g["ActPts"] - g["ProjPts"]).astype(int)            # + = beat projection
    g["ProjRk"] = g[best_col].rank(ascending=False, method="min").astype(int)
    g["ActRk"] = g["actual_total"].rank(ascending=False, method="min").astype(int)
    g["RkDiff"] = (g["ProjRk"] - g["ActRk"]).astype(int)              # + = finished better than projected
    g = g.sort_values("ProjRk")
    print(f"=== 2025 {bp} — BEST total-points projection ({best_col}); all drafted {bp}s ===")
    print(f"  {'Player':22s} {'ProjPts':>7} {'ActPts':>7} {'PtsΔ':>6} {'ProjRk':>6} {'ActRk':>6} {'RkΔ':>5}")
    for _, r in g.iterrows():
        print(f"  {r['player'][:22]:22s} {r['ProjPts']:7d} {r['ActPts']:7d} {r['PtsDiff']:+6d} "
              f"{bp}{r['ProjRk']:<4d} {bp}{r['ActRk']:<4d} {r['RkDiff']:+5d}")


if __name__ == "__main__":
    main()
