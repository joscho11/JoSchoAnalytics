"""Show the 2025 table from the PRODUCTION Model A (LightGBM, no injury features).

Loads the production {pos}_ppg_model.pkl (trained 2014-2024, so 2025 is clean holdout),
projects season totals = PPG_pred x constant games (the availability model hurts totals,
so we use a constant -- see eval_totals.py), and prints the best position's full table:
Proj Pts, Actual Pts, Pts Diff, Proj Rank, Actual Rank, Rank Diff.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
POSITIONS = ["QB", "RB", "WR", "TE"]


def main():
    df = pd.read_csv(DATA)
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    gconst = pool[pool.season < 2025]["target_games"].mean()    # constant games (2014-2024 drafted pool)

    te = pool[pool.season == 2025].copy()
    te["ppg_pred"] = np.nan
    for pos in POSITIONS:
        art = joblib.load(MODELS_DIR / f"{pos.lower()}_ppg_model.pkl")
        m = te.position == pos
        te.loc[m, "ppg_pred"] = np.clip(art["model"].predict(te.loc[m, art["feature_cols"]]), 0, None)
    te["proj_total"] = te["ppg_pred"] * gconst
    te["actual_total"] = te["target_ppg"] * te["target_games"]

    print(f"Production Model A (LightGBM, no injury feats) | constant games = {gconst:.1f}")
    print("2025 per-position rank corr (proj total vs actual finish):")
    summ = {}
    for pos in POSITIONS:
        g = te[te.position == pos]
        summ[pos] = g["proj_total"].rank().corr(g["actual_total"].rank())
        print(f"  {pos}: ρ={summ[pos]:.2f} (n={len(g)})")
    bp = max(summ, key=summ.get)
    print(f"  -> best position: {bp}\n")

    g = te[te.position == bp].copy()
    g["ProjPts"] = g["proj_total"].round(0).astype(int)
    g["ActPts"] = g["actual_total"].round(0).astype(int)
    g["PtsDiff"] = (g["ActPts"] - g["ProjPts"]).astype(int)
    g["ProjRk"] = g["proj_total"].rank(ascending=False, method="min").astype(int)
    g["ActRk"] = g["actual_total"].rank(ascending=False, method="min").astype(int)
    g["RkDiff"] = (g["ProjRk"] - g["ActRk"]).astype(int)
    g = g.sort_values("ProjRk")
    print(f"=== 2025 {bp} — production Model A (LightGBM); all drafted {bp}s ===")
    print(f"  {'Player':22s} {'ProjPts':>7} {'ActPts':>7} {'PtsΔ':>6} {'ProjRk':>6} {'ActRk':>6} {'RkΔ':>5}")
    for _, r in g.iterrows():
        print(f"  {r['player'][:22]:22s} {r['ProjPts']:7d} {r['ActPts']:7d} {r['PtsDiff']:+6d} "
              f"{bp}{r['ProjRk']:<4d} {bp}{r['ActRk']:<4d} {r['RkDiff']:+5d}")


if __name__ == "__main__":
    main()
