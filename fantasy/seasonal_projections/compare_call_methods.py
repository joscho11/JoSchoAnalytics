"""Which call-generation method finds ADP mispricings best? (2018+, Sleeper era)

  our_dev     : rank by our model alone, deviation from ADP
  sleeper_dev : rank by Sleeper alone, deviation from ADP
  blend_dev   : rank by a COMBINED model (0.4*our + 0.6*Sleeper season totals), dev from ADP
  consensus   : our_dev call, but only when Sleeper agrees vs ADP (the gate from improve_calls)

Decides whether to rank calls off a combined model or off our model with a Sleeper gate.
Fades gated to the good-fade subset (declining/aging, not young).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fade_deep_dive as fdd

WB = 0.4   # our weight in the combined (blend) season-total model


def hit(g, col="our_dev"):
    return (np.sign(g[col]) == np.sign(g["actual_dev"])).mean()


def main():
    a = fdd.build()
    a = a[a["sleeper_pts_half_ppr"].notna()].copy()       # Sleeper era only, fair comparison
    g = a.groupby(["season", "position"])
    a["sleeper_rk"] = g["sleeper_pts_half_ppr"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["blend_total"] = WB * a["our_total"] + (1 - WB) * a["sleeper_pts_half_ppr"]
    a["blend_rk"] = a.groupby(["season", "position"])["blend_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["sleeper_dev"] = a["adp_rk"] - a["sleeper_rk"]
    a["blend_dev"] = a["adp_rk"] - a["blend_rk"]

    pos, age = a["position"], a["age"].fillna(26)
    age_cliff = (((pos == "RB") & (age >= 27)) | (pos.isin(["WR", "TE"]) & (age >= 29)) | ((pos == "QB") & (age >= 34)))
    declining = a["ppg_trend"].fillna(0) < -1
    young = a["years_exp"] <= 2
    gate = (age_cliff | declining) & (~young)

    def buy_hit(devcol, thr):
        s = a[a[devcol] >= thr]
        return hit(s, devcol), len(s)

    def fade_hit(devcol, thr):
        s = a[(a[devcol] <= -thr) & gate]
        return hit(s, devcol), len(s)

    print("=== BUY hit-rate by method and confidence ===")
    print(f"  {'method':14s} {'>=5':>14} {'>=8':>14}")
    for name, col in [("our model", "our_dev"), ("Sleeper", "sleeper_dev"), ("blend(.4/.6)", "blend_dev")]:
        h5, n5 = buy_hit(col, 5); h8, n8 = buy_hit(col, 8)
        print(f"  {name:14s} {h5*100:4.0f}% (n={n5:3d}) {h8*100:4.0f}% (n={n8:3d})")
    # consensus = our_dev call gated by Sleeper agreement
    cons5 = a[(a.our_dev >= 5) & (a.sleeper_dev > 0)]
    cons8 = a[(a.our_dev >= 8) & (a.sleeper_dev > 0)]
    print(f"  {'consensus':14s} {hit(cons5)*100:4.0f}% (n={len(cons5):3d}) {hit(cons8)*100:4.0f}% (n={len(cons8):3d})")

    print("\n=== gated-FADE hit-rate by method and confidence ===")
    print(f"  {'method':14s} {'>=5':>14} {'>=8':>14}")
    for name, col in [("our model", "our_dev"), ("Sleeper", "sleeper_dev"), ("blend(.4/.6)", "blend_dev")]:
        h5, n5 = fade_hit(col, 5); h8, n8 = fade_hit(col, 8)
        print(f"  {name:14s} {h5*100:4.0f}% (n={n5:3d}) {h8*100:4.0f}% (n={n8:3d})")
    consf5 = a[(a.our_dev <= -5) & (a.sleeper_dev < 0) & gate]
    consf8 = a[(a.our_dev <= -8) & (a.sleeper_dev < 0) & gate]
    print(f"  {'consensus':14s} {hit(consf5)*100:4.0f}% (n={len(consf5):3d}) {hit(consf8)*100:4.0f}% (n={len(consf8):3d})")


if __name__ == "__main__":
    main()
