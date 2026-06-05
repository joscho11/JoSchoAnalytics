"""Diagnostic: is our ADP shortfall driven by rookies, or do we lose on veterans too?

The aggregate walk-forward backtest in build_draft_board.py says we trail ADP by
~0.06 rho. But the model fades rookies by construction (no prior-season data), and
the 2025 "reaches" were almost all rookies. This splits the SAME walk-forward
backtest (retrain on seasons < N, drafted pool only, judged on actual VOR) into
veterans (is_rookie==0) vs rookies (is_rookie==1), per season and pooled.

If we match/beat ADP on veterans and only lose on rookies, the veteran projection
is competitive and a rookie model is worth considering. If we lose on veterans too,
the system has no edge and we park it.

Run:  python fantasy/seasonal_projections/diagnose_vet_rookie.py
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

BACKTEST_SEASONS = [2020, 2021, 2022, 2023, 2024]   # ADP-era seasons (build_draft_board derives this per-run inside main())


def rho_pair(sub):
    """(our VOR rho, ADP rho) vs actual VOR, on a subgroup."""
    if len(sub) < 10 or sub.actual_vor.nunique() < 3:
        return None
    ro = float(spearmanr(sub.vor, sub.actual_vor).statistic)
    ra = float(spearmanr(-sub.adp_overall_rank, sub.actual_vor).statistic)
    return ro, ra


def main():
    df = pd.read_csv(bb.DATA)
    a_params, b_params = bb._tuned_params()
    feats = [c for c in df.columns if c not in bb.EXCLUDE]

    pooled = {"all": [], "vet": [], "rookie": []}
    print(f"Walk-forward backtest split by rookie status (drafted pool, ADP top {bb.DRAFTED_MAX_RANK})")
    print(f"ranking quality vs actual VOR (Spearman rho, higher better); edge = ours - ADP\n")
    print(f"  {'season':>6} | {'grp':>6} {'n':>4} {'ours':>7} {'ADP':>7} {'edge':>7}")
    for yr in BACKTEST_SEASONS:
        ma, mb = bb.train_fold(df[df.season < yr], a_params, b_params, feats)
        d = bb.predict(df[df.season == yr], ma, mb)
        pop = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        pop["actual_total"] = pop.target_ppg * pop.target_games
        pop["actual_vor"]   = bb._vor(pop, "actual_total")
        groups = [("all", pop), ("vet", pop[pop.is_rookie == 0]), ("rookie", pop[pop.is_rookie == 1])]
        for g, sub in groups:
            r = rho_pair(sub)
            if r is None:
                print(f"  {yr:>6} | {g:>6} {len(sub):>4}   (too few)")
                continue
            ro, ra = r
            pooled[g].append(sub.assign(_ours=ro, _adp=ra))
            print(f"  {yr:>6} | {g:>6} {len(sub):>4} {ro:>7.3f} {ra:>7.3f} {ro - ra:>+7.3f}")
        print()

    print(f"  {'POOLED':>6} | {'grp':>6} {'n':>4} {'ours':>7} {'ADP':>7} {'edge':>7}")
    pool_frames = {}
    for g in ("all", "vet", "rookie"):
        allrows = pd.concat(pooled[g], ignore_index=True) if pooled[g] else pd.DataFrame()
        pool_frames[g] = allrows
        if len(allrows) < 10:
            print(f"  {'':>6} | {g:>6} {len(allrows):>4}   (too few)")
            continue
        ro = float(spearmanr(allrows.vor, allrows.actual_vor).statistic)
        ra = float(spearmanr(-allrows.adp_overall_rank, allrows.actual_vor).statistic)
        print(f"  {'':>6} | {g:>6} {len(allrows):>4} {ro:>7.3f} {ra:>7.3f} {ro - ra:>+7.3f}")

    # composition + how much of the pool is rookies (context for the aggregate)
    allp = pool_frames["all"]
    if len(allp):
        nrk = int((allp.is_rookie == 1).sum())
        print(f"\n  pool composition: {len(allp)} drafted player-seasons, "
              f"{nrk} rookies ({nrk / len(allp):.0%}), {len(allp) - nrk} veterans")
        # do our rookie projections at least order rookies sensibly, or are they noise?
        rk = pool_frames["rookie"]
        if len(rk):
            print(f"  rookie projection range: our VOR {rk.vor.min():.0f} to {rk.vor.max():.0f} "
                  f"(if near-flat, the model can't tell rookies apart)")


if __name__ == "__main__":
    main()
