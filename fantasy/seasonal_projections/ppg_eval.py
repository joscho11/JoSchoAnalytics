"""Projection-quality eval: half-PPR points-per-game MAE (how close, not what rank).

Rank correlation answers "do we have an edge vs the market." This answers the more
direct question "is our projection actually good" — measured as games-weighted MAE on
points per game, the way you'd judge a projection (predict CMC 290, he scores 300 -> good,
regardless of where he ranks). Compares our independent model to Sleeper's projection and
to naive baselines, walk-forward, per position, with 2025 as the live test.
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
GAMES_PER_SEASON = 17


def wmae(err, w):
    w = np.asarray(w, float)
    return float(np.sum(np.abs(err) * w) / np.sum(w))


def run(test_seasons=range(2021, 2026), drafted_max=180):
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

    # candidate PPG projections
    allp["sleeper_ppg"] = allp["sleeper_pts_half_ppr"] / GAMES_PER_SEASON   # total -> PPG proxy
    allp["naive_prior"] = allp["prior_ppg"]
    allp["naive_3yr"] = allp["ppg_3yr"]
    models = {"OUR model": "our_ppg", "Sleeper (proj/17)": "sleeper_ppg",
              "naive: last yr PPG": "naive_prior", "naive: 3yr avg PPG": "naive_3yr"}

    def table(frame, title):
        print(f"\n{title}  (games-weighted PPG MAE; lower = better)")
        print(f"  {'model':20s} " + " ".join(f"{p:>6}" for p in ["QB", "RB", "WR", "TE", "ALL"]))
        for name, col in models.items():
            cells = []
            for pos in ["QB", "RB", "WR", "TE", None]:
                g = frame if pos is None else frame[frame["position"] == pos]
                g = g.dropna(subset=[col, "target_ppg"])
                cells.append(f"{wmae(g[col] - g['target_ppg'], g['sample_weight']):6.2f}" if len(g) else "   n/a")
            print(f"  {name:20s} " + " ".join(cells))

    table(allp, f"=== POOLED {min(p['season'].min() for p in [allp])}-2025 (n={len(allp)}) ===")
    table(allp[allp["season"] == 2025], f"=== 2025 LIVE TEST (n={len(allp[allp['season']==2025])}) ===")

    # ENSEMBLE TEST: does blending our model with Sleeper beat Sleeper alone on MAE?
    both = allp.dropna(subset=["our_ppg", "sleeper_ppg", "target_ppg"]).copy()
    print("\n=== ENSEMBLE: blend = w*OUR + (1-w)*Sleeper  (pooled ALL PPG wMAE) ===")
    base = wmae(both["sleeper_ppg"] - both["target_ppg"], both["sample_weight"])
    best = (base, 0.0)
    for w in np.arange(0, 0.61, 0.1):
        bl = w * both["our_ppg"] + (1 - w) * both["sleeper_ppg"]
        m = wmae(bl - both["target_ppg"], both["sample_weight"])
        flag = " <- beats Sleeper" if m < base - 1e-9 else ""
        print(f"  w={w:.1f}:  MAE {m:.3f}{flag}")
        if m < best[0]:
            best = (m, w)
    print(f"  Sleeper alone: {base:.3f}   best blend (w={best[1]:.1f}): {best[0]:.3f}   "
          f"improvement {base - best[0]:+.3f}")
    # same on 2025 only
    b25 = both[both["season"] == 2025]
    base25 = wmae(b25["sleeper_ppg"] - b25["target_ppg"], b25["sample_weight"])
    bl25 = best[1] * b25["our_ppg"] + (1 - best[1]) * b25["sleeper_ppg"]
    print(f"  2025 live: Sleeper {base25:.3f}  vs blend(w={best[1]:.1f}) "
          f"{wmae(bl25 - b25['target_ppg'], b25['sample_weight']):.3f}")

    # quick concrete examples (2025 RBs, biggest names)
    ex = allp[(allp["season"] == 2025) & (allp["position"] == "RB")].copy()
    ex = ex.sort_values("target_ppg", ascending=False).head(8)
    print("\n  2025 RB examples (actual vs our vs Sleeper, PPG):")
    print(f"    {'player':22s} {'actual':>7} {'ours':>6} {'sleeper':>8}")
    for _, r in ex.iterrows():
        print(f"    {r['player'][:22]:22s} {r['target_ppg']:7.1f} {r['our_ppg']:6.1f} {r['sleeper_ppg']:8.1f}")


if __name__ == "__main__":
    run()
