"""Sample 2025 value board — what the ADP-benchmarked value-flag overlay would show.

Walk-forward: train on seasons < 2025, predict 2025 (true out-of-sample). The model
anchors on Sleeper's projection and nudges it with our opportunity/situation residual
signal. We rank players, compare to ADP, and flag BUY (undervalued vs the casual ADP
line) / FADE (overvalued). Because 2025 is complete, we show how each call actually
turned out. Judged on half-PPR points per game (talent/role, not injury luck).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import value_eval as ve
from college_rookie_test import attach_college, COLLEGE

SHRINK = 0.3
ORTHO = avm.SITU + avm.BIAS + COLLEGE


def build_2025_board():
    df = pd.read_csv(avm.newest_dataset())
    df = attach_college(df)
    df = avm.add_bias_features(df)

    cov = df["sleeper_pts_half_ppr"].notna() & df["target_ppg"].notna()
    train = df[cov & (df["season"] < 2025) & (df["adp_overall_rank"] <= 180)].copy()
    test = df[(df["season"] == 2025) & (df["adp_overall_rank"] <= 180)
              & df["sleeper_pts_half_ppr"].notna() & df["target_ppg"].notna()].copy()

    # stage 1: market expectation (actual ppg from Sleeper projection)
    exp_tr = ve._cat_fit(train[["sleeper_pts_half_ppr", "position"]].copy(), train["target_ppg"],
                         train[["sleeper_pts_half_ppr", "position"]].copy())
    test["exp"] = ve._cat_fit(train[["sleeper_pts_half_ppr", "position"]].copy(), train["target_ppg"],
                              test[["sleeper_pts_half_ppr", "position"]].copy())
    train["resid"] = train["target_ppg"].values - exp_tr
    feats = [c for c in ORTHO if c in train.columns] + ["position"]
    test["pred_resid"] = ve._cat_fit(train[feats].copy(), train["resid"], test[feats].copy(),
                                     w=train["sample_weight"].clip(lower=1))

    # our projection = Sleeper anchor + opportunity nudge (standardized within position)
    def z(s):
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd else s * 0
    g = test.groupby("position")
    test["our_proj"] = g["exp"].transform(z) + SHRINK * g["pred_resid"].transform(z)

    # positional ranks (1 = best)
    test["adp_rk"] = g["adp_pos_rank"].transform(lambda s: s.rank(method="min"))
    test["our_rk"] = test.groupby("position")["our_proj"].transform(lambda s: s.rank(ascending=False, method="min"))
    test["act_rk"] = test.groupby("position")["target_ppg"].transform(lambda s: s.rank(ascending=False, method="min"))
    test["value"] = test["adp_rk"] - test["our_rk"]          # + = we rank ahead of ADP (BUY)
    test["beat_adp"] = test["adp_rk"] - test["act_rk"]       # + = actually finished ahead of ADP
    return test


def _row(r):
    p = r["position"]
    return (f"{r['player'][:21]:21s} {p:3s} {str(r['team'])[:3]:3s}  "
            f"{p}{int(r['adp_rk']):<2d}  {p}{int(r['our_rk']):<2d}  {int(r['value']):+3d}   "
            f"{p}{int(r['act_rk']):<2d}")


def main():
    b = build_2025_board()
    BUY_T = 5
    buys = b[b["value"] >= BUY_T].sort_values("value", ascending=False)
    fades = b[b["value"] <= -BUY_T].sort_values("value")

    print(f"2025 value board (out-of-sample). pool = {len(b)} drafted players (ADP top 180).")
    print(f"columns: Player Pos Team | ADP  Our  Value | Actual\n")

    print(f"=== TOP 12 BUYS (we flag undervalued vs ADP) ===   [hit = finished ahead of ADP]")
    print(f"  {'Player':21s} {'Ps':3s} {'Tm':3s}  {'ADP':4s} {'Our':4s} {'Val':4s}  {'Fin':4s}  result")
    for _, r in buys.head(12).iterrows():
        print(f"  {_row(r)}   {'HIT ' if r['beat_adp'] > 0 else 'miss'}")

    print(f"\n=== TOP 12 FADES (we flag overvalued vs ADP) ===   [hit = finished behind ADP]")
    print(f"  {'Player':21s} {'Ps':3s} {'Tm':3s}  {'ADP':4s} {'Our':4s} {'Val':4s}  {'Fin':4s}  result")
    for _, r in fades.head(12).iterrows():
        print(f"  {_row(r)}   {'HIT ' if r['beat_adp'] < 0 else 'miss'}")

    bh = (buys["beat_adp"] > 0).mean()
    fh = (fades["beat_adp"] < 0).mean()
    print(f"\n=== 2025 scorecard ===")
    print(f"  BUY  flags: {len(buys):2d}   hit {bh*100:.0f}% (finished ahead of their ADP)")
    print(f"  FADE flags: {len(fades):2d}   hit {fh*100:.0f}% (finished behind their ADP)")
    print(f"  baseline: a coin flip is 50%. (Edge here is modest and 2025 is one season.)")


if __name__ == "__main__":
    main()
