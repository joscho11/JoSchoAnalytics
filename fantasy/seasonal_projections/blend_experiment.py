"""Experiment: does blending our independent projection with ADP beat ADP alone?

We never feed ADP into the model (that would be circular -- the tree would just
copy ADP). Instead we keep our board projection fully independent, then combine
the two RANKINGS after the fact:

    blended_score = w * our_rank + (1 - w) * adp_rank          (lower = better)

and sweep w from 0 (pure ADP) to 1 (pure us). Classic ensemble logic: two
imperfect, partly-independent rankers can beat the better one alone if their
errors are not too correlated. If some w in (0,1) lifts Spearman rho above ADP's
by more than noise -- and seasons agree on the direction -- that is a real,
usable draft edge (you draft by the blend).

Walk-forward: retrain the vet models on seasons < N each fold (no leakage), build
the drafted pool, rank within season. Judged on actual VOR, pooled across folds.

Honest caveat printed at the end: the best w is chosen in-sample on the same 5
seasons, so its rho is mildly optimistic; the real signal is whether the curve
peaks interior at all and whether each season independently prefers w > 0.

Run:  python fantasy/seasonal_projections/blend_experiment.py
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
WEIGHTS = np.round(np.arange(0.0, 1.001, 0.05), 3)   # 0 = pure ADP, 1 = pure us (fine grid)


def build_pool(df, group):
    """Walk-forward: per season, drafted pool with our_rank, adp_rank, actual_vor.

    group in {'all','vet'} selects the evaluation population.
    """
    a_params, b_params = bb._tuned_params()
    feats = [c for c in df.columns if c not in bb.EXCLUDE]
    frames = []
    for yr in BACKTEST_SEASONS:
        vet_a, vet_b = bb.train_fold(df[df.season < yr], a_params, b_params, feats)
        d = bb.predict(df[df.season == yr], vet_a, vet_b)
        pop = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        if group == "vet":
            pop = pop[pop.is_rookie == 0]
        pop["actual_total"] = pop.target_ppg * pop.target_games
        pop["actual_vor"]   = bb._vor(pop, "actual_total")
        # within-season ranks, 1 = best (our: high VOR; ADP: low rank number)
        pop["our_rank"] = pop.vor.rank(ascending=False, method="average")
        pop["adp_rank"] = pop.adp_overall_rank.rank(ascending=True, method="average")
        pop["season_"] = yr
        frames.append(pop[["season_", "our_rank", "adp_rank", "actual_vor"]])
    return pd.concat(frames, ignore_index=True)


def rho_at(pool, w):
    blended = w * pool.our_rank + (1 - w) * pool.adp_rank   # lower = better
    return float(spearmanr(-blended, pool.actual_vor).statistic)


def sweep(pool, label):
    """Fine pooled sweep + leave-one-season-out confirmation of the weight."""
    n = len(pool)
    se = 1.0 / np.sqrt(n - 1)                               # approx SE of Spearman rho
    rhos = {w: rho_at(pool, w) for w in WEIGHTS}
    adp = rhos[0.0]
    best_w = max(rhos, key=rhos.get)
    print(f"\n=== {label} (pooled n={n}, approx SE={se:.3f}) ===")
    print("  fine sweep (w = our weight; 0 = pure ADP, 1 = pure us):")
    for w in WEIGHTS:
        bar = "#" * int(round((rhos[w] - 0.45) / 0.005)) if rhos[w] > 0.45 else ""
        mark = "  <- best" if w == best_w else ("   (ADP)" if w == 0 else "")
        print(f"   {w:>4.2f}  {rhos[w]:.4f} {bar}{mark}")
    gain = rhos[best_w] - adp
    print(f"  pooled best w={best_w:.2f}: rho={rhos[best_w]:.4f} vs ADP {adp:.4f} "
          f"(gain {gain:+.4f}, ~{gain/se:.1f} SE)")
    # broad-optimum check: the range of w that beats ADP at all
    winning = [w for w in WEIGHTS if rhos[w] > adp]
    if winning:
        print(f"  weights that beat pure ADP: {min(winning):.2f} to {max(winning):.2f}")

    # ---- leave-one-season-out: pick w on the other 4 seasons, test on the held-out one ----
    print("  leave-one-season-out (w chosen on the other 4 seasons, then tested):")
    chosen_ws, held_blend, held_adp = [], [], []
    for h in BACKTEST_SEASONS:
        train = pool[pool.season_ != h]
        test  = pool[pool.season_ == h]
        if len(test) < 10:
            continue
        tr = {w: rho_at(train, w) for w in WEIGHTS}
        w_star = max(tr, key=tr.get)
        r_blend, r_adp = rho_at(test, w_star), rho_at(test, 0.0)
        chosen_ws.append(w_star); held_blend.append(r_blend); held_adp.append(r_adp)
        print(f"    holdout {h}: picked w={w_star:.2f}  ->  blend {r_blend:+.4f}  ADP {r_adp:+.4f}  "
              f"{'blend better' if r_blend > r_adp else 'ADP better'}")
    if chosen_ws:
        n_better = sum(b > a for b, a in zip(held_blend, held_adp))
        mean_gain = float(np.mean(held_blend) - np.mean(held_adp))
        print(f"  -> chosen w range {min(chosen_ws):.2f}-{max(chosen_ws):.2f} "
              f"(median {np.median(chosen_ws):.2f}); held-out blend beats ADP "
              f"{n_better}/{len(chosen_ws)} seasons, mean held-out gain {mean_gain:+.4f}")
        print(f"  verdict: {_verdict(mean_gain, se, n_better, len(chosen_ws))}")
    return best_w


def _verdict(gain, se, agree, total):
    if gain > 2 * se and agree == total:
        return "REAL edge -- blend beats ADP robustly out-of-sample"
    if agree >= total - 1 and gain > 0:
        return "small but consistent gain -- real direction, marginal size (not a big edge)"
    return "no reliable edge -- ADP alone is as good or better"


def main():
    df = pd.read_csv(bb.DATA)
    best = {}
    for group, label in [("all", "ALL drafted players"), ("vet", "VETERANS only")]:
        pool = build_pool(df, group)
        best[group] = sweep(pool, label)
    print(f"\nSUMMARY: pooled best w (our weight) -- all={best['all']:.2f}, vet={best['vet']:.2f}")


if __name__ == "__main__":
    main()
