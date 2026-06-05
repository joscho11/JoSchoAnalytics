"""Does the rookie model (or pure ADP) improve the rookie slice of the shipped blend?

The shipped board blends 0.30*our_rank + 0.70*ADP within the drafted pool. For
ROOKIES, "our_rank" currently comes from the veteran Model A, which has no rookie
signal (rookie ranking rho ~0.13). This tests three ways to handle rookies inside
the blend, walk-forward (retrain on seasons < N, drafted pool, judged on actual VOR):

  A (shipped)  rookies use the veteran model in the 0.30 slot
  B (swap)     rookies use the dedicated rookie model in the 0.30 slot (rho ~0.26)
  C (ADP-only) rookies are ranked by pure ADP (drop our model for them entirely)

Measured both ways:
  - rookie-slice rho   (only the rookie rows -- the thing we're trying to fix)
  - overall blend rho  (whole drafted pool -- must not regress)

Reference ceiling: pure ADP on rookies is ~0.46; our rookie model standalone ~0.26.
Because the rookie model LOSES to ADP standalone, the live question is whether
blending it in still beats the veteran-blended status quo, and whether simply
trusting ADP for rookies (C) is the cheaper, better answer.

Run:  python fantasy/seasonal_projections/rookie_blend_test.py
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
import rookie_model_experiment as rk

BACKTEST_SEASONS = [2020, 2021, 2022, 2023, 2024]
W = 0.30   # the our/ADP 2-way weight this experiment was run against (now superseded by the 3-way blend)


def _rho(score, actual_vor, mask=None):
    """Spearman of -score (lower score = earlier pick) vs actual VOR, optional subset."""
    s, a = (score[mask], actual_vor[mask]) if mask is not None else (score, actual_vor)
    if len(s) < 8 or a.nunique() < 3:
        return np.nan
    return float(spearmanr(-s, a).statistic)


def main():
    df = rk.prep(pd.read_csv(bb.DATA))                       # adds combine cols (live join)
    rk_tr_all = df[(df.is_rookie == 1) & df.target_ppg.notna() & (df.season < 2025)]
    best, _ = rk.tune(rk_tr_all)
    print(f"rookie params: { {k: best[k] for k in ('depth','learning_rate','l2_leaf_reg')} }\n")

    a_params, b_params = bb._tuned_params()
    feats = [c for c in df.columns if c not in bb.EXCLUDE]

    print("Walk-forward (drafted pool, ADP top 180). rho vs actual VOR; higher better.")
    print("  A=shipped(vet)  B=rookie-model  C=pure-ADP-for-rookies\n")
    print(f"  {'season':>6} {'n_rk':>5} | {'OVERALL: A':>10} {'B':>6} {'C':>6} | "
          f"{'ROOKIE: A':>9} {'B':>6} {'C':>6}")
    rows = []
    for yr in BACKTEST_SEASONS:
        vet_a, vet_b = bb.train_fold(df[df.season < yr], a_params, b_params, feats)
        rk_model = rk.fit_rookie(best, df[(df.season < yr) & (df.is_rookie == 1) & df.target_ppg.notna()])

        d = bb.predict(df[df.season == yr], vet_a, vet_b)        # vet vor for all
        mask_rk = d.is_rookie == 1
        d2 = d.copy()
        d2.loc[mask_rk, "ppg_pred"] = np.clip(rk_model.predict(d2.loc[mask_rk, rk.ROOKIE_FEATS]), 0, None)
        d2["projected_total"] = d2.ppg_pred * d2.games_pred
        d["vor_swap"] = bb._vor(d2, "projected_total")          # rookies use rookie model

        pool = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        if len(pool) < 30:
            continue
        pool["actual_total"] = pool.target_ppg * pool.target_games
        pool["actual_vor"]   = bb._vor(pool, "actual_total")
        is_rk = (pool.is_rookie == 1).values

        adp_r     = pool.adp_overall_rank.rank(ascending=True)
        our_r_vet = pool.vor.rank(ascending=False)
        our_r_swp = pool.vor_swap.rank(ascending=False)

        score_A = W * our_r_vet + (1 - W) * adp_r
        score_B = W * our_r_swp + (1 - W) * adp_r
        score_C = score_A.copy()
        score_C[is_rk] = adp_r[is_rk]                            # rookies = pure ADP

        av = pool.actual_vor
        rec = (yr, int(is_rk.sum()),
               _rho(score_A, av), _rho(score_B, av), _rho(score_C, av),
               _rho(score_A, av, is_rk), _rho(score_B, av, is_rk), _rho(score_C, av, is_rk))
        rows.append(rec)
        print(f"  {rec[0]:>6} {rec[1]:>5} | {rec[2]:>10.3f} {rec[3]:>6.3f} {rec[4]:>6.3f} | "
              f"{rec[5]:>9.3f} {rec[6]:>6.3f} {rec[7]:>6.3f}")

    arr = np.array([r[2:] for r in rows], dtype=float)
    m = np.nanmean(arr, axis=0)
    print(f"  {'mean':>6} {'':>5} | {m[0]:>10.3f} {m[1]:>6.3f} {m[2]:>6.3f} | "
          f"{m[3]:>9.3f} {m[4]:>6.3f} {m[5]:>6.3f}")

    print("\nverdict:")
    print(f"  overall  shipped(A)={m[0]:.3f}  rookie-model(B)={m[1]:.3f}  pure-ADP-rookies(C)={m[2]:.3f}")
    print(f"  rookies  shipped(A)={m[3]:.3f}  rookie-model(B)={m[4]:.3f}  pure-ADP-rookies(C)={m[5]:.3f}")
    best_overall = ["A (shipped)", "B (rookie model)", "C (pure ADP rookies)"][int(np.argmax(m[:3]))]
    best_rookie  = ["A (shipped)", "B (rookie model)", "C (pure ADP rookies)"][int(np.argmax(m[3:]))]
    print(f"  -> best overall: {best_overall};  best on rookies: {best_rookie}")


if __name__ == "__main__":
    main()
