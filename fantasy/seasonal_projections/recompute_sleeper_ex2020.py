"""K2 (2026-07-10): recompute every published Sleeper number ex-2020.

The provenance audit (see PREREGISTRATION.md Outcomes + fetch_adp.py quarantine
comment) found Sleeper's stored 2020 "projections" are near-actuals. 2020 is
therefore excluded from every Sleeper-projection metric. NOTE, recorded before
these numbers existed: removing 2020 LOWERS Sleeper's measured skill and
therefore FLATTERS our models — the exclusion is justified by provenance
evidence about the artifact (gp/actual corr +0.91, Mixon 88.0/6), not by any
hypothesis about the comparison. ADP is unaffected (audited CLEAN, all seasons).

Restates, mechanically (no new hypotheses, frozen weights, harness machinery):
  1. phase0 Sleeper + ADP rows on the 2021-2025 pool (was 2020-2025).
  2. The three-way blend (frozen 0.2 our / 0.3 ADP / 0.5 Sleeper) on 2021-2024
     (the original 2020-2024 eval window minus the voided season). This is a
     phase0-harness restatement: "our" = walk-forward LightGBM points (the
     original 2026-06-03 numbers used the CatBoost VOR board — machinery
     differs, and the original weights were also TUNED on data including 2020,
     which cannot be undone without re-tuning; noted, not re-tuned).

Run:  python fantasy/seasonal_projections/recompute_sleeper_ex2020.py
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT  = HERE / "sleeper_ex2020_results.json"
POS4 = ["QB", "RB", "WR", "TE"]
EX   = list(range(2021, 2026))
BLEND_SEASONS = list(range(2021, 2025))          # original window 2020-2024, minus 2020
W3 = {"our": 0.20, "adp": 0.30, "slp": 0.50}     # frozen shipped weights
W2 = {"our": 0.30, "adp": 0.70}                  # frozen old two-way


def main():
    df = pb.assemble()
    df["finish_all"] = pb.finish_ranks(df)
    df["model_wf"] = pb.walk_forward_model(df) * 17
    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]

    # 1. phase0 Sleeper + ADP rows, 2021-2025
    p = pool[pool.season.isin(EX)]
    res = {"sleeper_2021_2025": pb.eval_source(p, "sleeper_pts_half_ppr", False, positions=POS4),
           "adp_2021_2025":     pb.eval_source(p, "adp", True, positions=POS4)}
    old = json.load(open(HERE / "phase0_benchmark_results.json"))["2020-2025 (all sources)"]
    print("K2.1 — Sleeper preseason projection, per position (rho / top12 / bust)")
    print(f"  {'pos':4} {'old 2020-25':>12} {'ex-2020':>9} {'delta':>7}   (ADP ex-2020 for scale)")
    for pos in POS4:
        o = old["sleeper"][pos]["rho"]; n = res["sleeper_2021_2025"][pos]["rho"]
        a = res["adp_2021_2025"][pos]["rho"]
        print(f"  {pos:4} {o:12.3f} {n:9.3f} {n-o:+7.3f}   (adp {a:.3f})")

    # 2. blend restatement, 2021-2024, overall-pool ranking (frozen weights)
    rhos = {"three_way": [], "two_way": [], "adp": [], "sleeper": []}
    for s in BLEND_SEASONS:
        g = pool[pool.season == s].copy()
        r_our = g["model_wf"].rank(ascending=False, na_option="bottom")
        r_adp = g["adp"].rank(ascending=True)
        r_slp = g["sleeper_pts_half_ppr"].rank(ascending=False, na_option="keep").fillna(r_adp)
        b3 = W3["our"] * r_our + W3["adp"] * r_adp + W3["slp"] * r_slp
        b2 = W2["our"] * r_our + W2["adp"] * r_adp
        rhos["three_way"].append(-spearmanr(b3, g["actual_pts"]).statistic)
        rhos["two_way"].append(-spearmanr(b2, g["actual_pts"]).statistic)
        rhos["adp"].append(-spearmanr(r_adp, g["actual_pts"]).statistic)
        rhos["sleeper"].append(-spearmanr(r_slp, g["actual_pts"]).statistic)
    print("\nK2.2 — blend restatement, overall-pool rho, 2021-2024 (frozen weights, harness machinery)")
    for k, v in rhos.items():
        print(f"  {k:10} mean {np.mean(v):.3f}   by season " +
              " ".join(f"{s}:{r:.3f}" for s, r in zip(BLEND_SEASONS, v)))
    res["blend_2021_2024"] = {k: {"mean": float(np.mean(v)), "by_season": [float(x) for x in v]}
                              for k, v in rhos.items()}

    OUT.write_text(json.dumps(res, indent=2, default=float))
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
