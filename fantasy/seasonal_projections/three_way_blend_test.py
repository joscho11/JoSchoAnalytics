"""Three-way blend: our model + ADP + Sleeper's own season projection.

The shipped board blends our independent VOR ranking with ADP (70/30). Sleeper also
publishes a full-season point projection (`sleeper_pts_half_ppr`), which is ALREADY
more accurate than our model (season-total MAE ~36.8 vs our ~38.8). This sweeps a
three-way blend of rankings -- our model, ADP, Sleeper's projection -- to answer:

  1. Does (our + ADP + Sleeper) rank the drafted pool better than (our + ADP)?
  2. Critically: how much weight does OUR model still earn once Sleeper's projection
     is in the mix? If it collapses to ~0, the board is really just "ADP + Sleeper"
     and our projection adds no independent value -- an honest negative.

All three are turned into within-pool ranks (1 = best); blend = weighted sum (lower
= earlier pick); judged on actual VOR, walk-forward (retrain vets on seasons < N).
Sleeper's projection is a genuine FORWARD projection (its MAE vs actual is ~37, not
~0), so using it at draft time is not leakage.

Run:  python fantasy/seasonal_projections/three_way_blend_test.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_draft_board as bb

BACKTEST_SEASONS = [2020, 2021, 2022, 2023, 2024]
STEP = 0.1
OLD_2WAY_W = 0.30   # the our-weight of the prior our/ADP 2-way blend, for reference comparison


def weight_grid():
    """All (w_our, w_adp, w_sleeper) on the simplex, 0.1 steps."""
    ks = [round(k * STEP, 2) for k in range(int(1 / STEP) + 1)]
    for wo in ks:
        for wa in ks:
            ws = round(1 - wo - wa, 2)
            if ws < -1e-9:
                continue
            yield wo, wa, ws


def build_pool(df):
    """Walk-forward drafted pool with our/adp/sleeper ranks + actual VOR, pooled."""
    a_params, b_params = bb._tuned_params()
    feats = [c for c in df.columns if c not in bb.EXCLUDE]
    frames = []
    for yr in BACKTEST_SEASONS:
        vet_a, vet_b = bb.train_fold(df[df.season < yr], a_params, b_params, feats)
        d = bb.predict(df[df.season == yr], vet_a, vet_b)
        pool = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()
                 & d.sleeper_pts_half_ppr.notna()].copy()
        if len(pool) < 30:
            continue
        pool["actual_total"] = pool.target_ppg * pool.target_games
        pool["actual_vor"]   = bb._vor(pool, "actual_total")
        pool["our_rank"]     = pool.vor.rank(ascending=False)
        pool["adp_rank"]     = pool.adp_overall_rank.rank(ascending=True)
        pool["sleeper_rank"] = pool.sleeper_pts_half_ppr.rank(ascending=False)
        pool["season_"] = yr
        frames.append(pool[["season_", "our_rank", "adp_rank", "sleeper_rank", "actual_vor"]])
    return pd.concat(frames, ignore_index=True)


def rho(pool, wo, wa, ws):
    score = wo * pool.our_rank + wa * pool.adp_rank + ws * pool.sleeper_rank
    return float(spearmanr(-score, pool.actual_vor).statistic)


def main():
    df = pd.read_csv(bb.DATA)
    pool = build_pool(df)
    n = len(pool)
    se = 1.0 / np.sqrt(n - 1)
    print(f"pooled drafted pool n={n} (with ADP + Sleeper proj), approx SE={se:.3f}\n")

    # reference points
    r_adp     = rho(pool, 0.0, 1.0, 0.0)
    r_sleeper = rho(pool, 0.0, 0.0, 1.0)
    r_our     = rho(pool, 1.0, 0.0, 0.0)
    r_2way    = rho(pool, OLD_2WAY_W, 1 - OLD_2WAY_W, 0.0)   # shipped our+ADP
    print(f"  pure ADP            rho={r_adp:.4f}")
    print(f"  pure Sleeper proj   rho={r_sleeper:.4f}")
    print(f"  pure our model      rho={r_our:.4f}")
    print(f"  shipped 2-way (our {OLD_2WAY_W}/ADP {1-OLD_2WAY_W:.1f})  rho={r_2way:.4f}")

    # full simplex sweep
    best = max(weight_grid(), key=lambda w: rho(pool, *w))
    r_best = rho(pool, *best)
    print(f"\n  best 3-way weights  our={best[0]:.1f}  adp={best[1]:.1f}  sleeper={best[2]:.1f}"
          f"   rho={r_best:.4f}")
    print(f"  gain vs shipped 2-way: {r_best - r_2way:+.4f}  (~{(r_best - r_2way)/se:.1f} SE)")
    print(f"  gain vs pure ADP:      {r_best - r_adp:+.4f}")

    # best blend that still INCLUDES Sleeper but keeps our model out, for contrast
    best_adp_sleeper = max(((0.0, wa, round(1 - wa, 2)) for wa in [round(k*STEP,2) for k in range(int(1/STEP)+1)]),
                           key=lambda w: rho(pool, *w))
    print(f"  best ADP+Sleeper (no us): adp={best_adp_sleeper[1]:.1f} sleeper={best_adp_sleeper[2]:.1f}"
          f"  rho={rho(pool, *best_adp_sleeper):.4f}")

    print("\n  verdict:")
    if best[0] >= 0.2 and r_best > r_2way + 0.005:
        print(f"   our model keeps real weight ({best[0]:.1f}) and the 3-way beats the 2-way -> worth shipping")
    elif best[0] < 0.1:
        print("   our model's weight collapses to ~0 -> the board is really ADP + Sleeper; our projection is redundant")
    else:
        print("   marginal: our model earns a little weight but the 3-way gain is within noise")

    # per-season robustness at the best weights
    print("\n  per-season (best 3-way vs shipped 2-way):")
    agree = 0
    for yr in BACKTEST_SEASONS:
        ps = pool[pool.season_ == yr]
        if len(ps) < 10:
            continue
        a, b = rho(ps, *best), rho(ps, OLD_2WAY_W, 1 - OLD_2WAY_W, 0.0)
        agree += a > b
        print(f"    {yr}: 3-way {a:+.3f}  2-way {b:+.3f}  {'3-way better' if a > b else '2-way better'}")
    print(f"  -> 3-way beats 2-way in {agree}/{len(BACKTEST_SEASONS)} seasons")

    # leave-one-season-out: pick weights on the other 4 seasons, test on the held-out one
    print("\n  leave-one-season-out (weights chosen on the other 4 seasons, then tested):")
    chosen, held_3way, held_2way = [], [], []
    for h in BACKTEST_SEASONS:
        tr_pool = pool[pool.season_ != h]
        te_pool = pool[pool.season_ == h]
        if len(te_pool) < 10:
            continue
        w_star = max(weight_grid(), key=lambda w: rho(tr_pool, *w))
        r3 = rho(te_pool, *w_star)
        r2 = rho(te_pool, OLD_2WAY_W, 1 - OLD_2WAY_W, 0.0)
        chosen.append(w_star); held_3way.append(r3); held_2way.append(r2)
        print(f"    holdout {h}: picked our/adp/slp {w_star[0]:.1f}/{w_star[1]:.1f}/{w_star[2]:.1f}"
              f"  ->  3-way {r3:+.3f}  2-way {r2:+.3f}  {'3-way better' if r3 > r2 else '2-way better'}")
    if chosen:
        n_better = sum(a > b for a, b in zip(held_3way, held_2way))
        mean_gain = float(np.mean(held_3way) - np.mean(held_2way))
        ws = np.array(chosen)
        print(f"  -> held-out 3-way beats 2-way {n_better}/{len(chosen)} seasons, mean gain {mean_gain:+.4f}")
        print(f"     chosen-weight ranges  our {ws[:,0].min():.1f}-{ws[:,0].max():.1f}  "
              f"adp {ws[:,1].min():.1f}-{ws[:,1].max():.1f}  sleeper {ws[:,2].min():.1f}-{ws[:,2].max():.1f}"
              f"  (median our={np.median(ws[:,0]):.1f}/adp={np.median(ws[:,1]):.1f}/slp={np.median(ws[:,2]):.1f})")


if __name__ == "__main__":
    main()
