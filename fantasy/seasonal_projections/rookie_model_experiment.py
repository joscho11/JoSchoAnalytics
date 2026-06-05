"""Experiment: does a dedicated rookie model close the rookie gap vs ADP?

The vet/rookie diagnostic showed our board's weakness is rookies: ranking rho
0.172 vs ADP 0.462, because the veteran Model A has no prior-season signal for a
rookie and clumps them all low. This trains a SEPARATE rookie model on the info
that IS available at draft time and never reaches the veteran model:

  draft capital   draft_round, draft_pick
  athleticism     combine forty / bench / vertical / broad_jump / cone / shuttle / ht / wt
  landing spot    prior_team_pass_rate, prior_team_plays, vacated target/rush share, coach/qb change
  bio             age, position

Combine joins to our gsis player_id via the draft_picks bridge (pfr id). College
production is NOT in nflreadpy, so we do not have it.

Decisive test: run the SAME walk-forward backtest (retrain on rookies < N, predict
rookies in N), slot the rookie model's PPG into the board in place of the veteran
model's for rookies, and recompute the rookie-subset ranking rho. Compare to:
  - 0.172  the current veteran-model-on-rookies baseline (recomputed here in-run)
  - 0.462  ADP on the same rookies
Beating 0.172 is expected; reaching/beating 0.462 would be a real tool/edge gain.

Run:  python fantasy/seasonal_projections/rookie_model_experiment.py
"""
import sys
import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from catboost import CatBoostRegressor

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_draft_board as bb
import rookie_features as rf       # shared source of truth for COMBINE_COLS / ROOKIE_FEATS / combine join

SEED = 42
BACKTEST_SEASONS = [2020, 2021, 2022, 2023, 2024]   # ADP-era seasons
COMBINE_COLS = rf.COMBINE_COLS
ROOKIE_FEATS = rf.ROOKIE_FEATS
CAT = rf.CAT


def prep(df):
    df = rf.add_rookie_features(df)
    cov = df.loc[df.is_rookie == 1, "wt"].notna().mean()
    print(f"combine join: {cov:.0%} of rookies have measurables\n")
    return df


def cat_grid():
    for depth, lr, l2 in itertools.product([3, 4, 6], [0.03, 0.06], [3.0, 6.0]):
        yield dict(iterations=400, depth=depth, learning_rate=lr, l2_leaf_reg=l2,
                   loss_function="MAE", random_seed=SEED, verbose=0, allow_writing_files=False)


def fit_rookie(params, tr):
    m = CatBoostRegressor(**params, cat_features=CAT)
    m.fit(tr[ROOKIE_FEATS], tr.target_ppg, sample_weight=tr.sample_weight)
    return m


def tune(train_rk):
    best, best_mae = None, np.inf
    for params in cat_grid():
        sc = []
        for vs in [2021, 2022, 2023, 2024]:
            tr = train_rk[train_rk.season < vs]
            va = train_rk[train_rk.season == vs]
            if len(tr) < 80 or len(va) < 15:
                continue
            m = fit_rookie(params, tr)
            pred = np.clip(m.predict(va[ROOKIE_FEATS]), 0, None)
            sc.append(float(np.average(np.abs(va.target_ppg - pred), weights=va.sample_weight)))
        if sc and np.mean(sc) < best_mae:
            best, best_mae = params, float(np.mean(sc))
    return best, best_mae


def holdout_mae(df, best):
    rk = df[(df.is_rookie == 1) & df.target_ppg.notna()]
    tr, ho = rk[rk.season < 2025], rk[rk.season == 2025]
    m = fit_rookie(best, tr)
    pred = np.clip(m.predict(ho[ROOKIE_FEATS]), 0, None)
    wmae = float(np.average(np.abs(ho.target_ppg - pred), weights=ho.sample_weight))
    # baseline: predict the training position-mean rookie PPG
    posmean = tr.groupby("position").apply(lambda g: np.average(g.target_ppg, weights=g.sample_weight))
    base = ho.position.map(posmean)
    bmae = float(np.average(np.abs(ho.target_ppg - base), weights=ho.sample_weight))
    print(f"2025 rookie holdout PPG wMAE: rookie-model={wmae:.3f}  position-mean baseline={bmae:.3f}  (n={len(ho)})")


def backtest(df, rk_params):
    """Swap the rookie model in for rookies and recompute the rookie-subset rho.

    Training DATA is walk-forward (rookies < N each fold); the rookie
    hyperparameters are tuned once globally and shared, matching how the veteran
    models use fixed production params in this backtest.
    """
    a_params, b_params = bb._tuned_params()
    feats = [c for c in df.columns if c not in bb.EXCLUDE]   # veteran Model A feats (no combine)
    print(f"\nWalk-forward rookie backtest (drafted pool, ADP top {bb.DRAFTED_MAX_RANK}):")
    print(f"  {'season':>6} {'n_rk':>5} {'vet-on-rk':>10} {'rookie-mdl':>11} {'ADP':>7}")
    rows = []
    for yr in BACKTEST_SEASONS:
        vet_a, vet_b = bb.train_fold(df[df.season < yr], a_params, b_params, feats)
        rk_tr = df[(df.season < yr) & (df.is_rookie == 1) & df.target_ppg.notna()]
        rk_model = fit_rookie(rk_params, rk_tr)

        d = bb.predict(df[df.season == yr], vet_a, vet_b)        # vet PPG + games + vor for all
        d_rk = d.is_rookie == 1
        # baseline rho: veteran model on rookies (matches the diagnostic)
        pop = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        pop["actual_total"] = pop.target_ppg * pop.target_games
        pop["actual_vor"] = bb._vor(pop, "actual_total")
        rk_pop = pop[pop.is_rookie == 1]
        rho_vet = spearmanr(rk_pop.vor, rk_pop.actual_vor).statistic if len(rk_pop) >= 8 else np.nan
        rho_adp = spearmanr(-rk_pop.adp_overall_rank, rk_pop.actual_vor).statistic if len(rk_pop) >= 8 else np.nan

        # now overwrite rookie PPG with the rookie model and recompute vor
        d.loc[d_rk, "ppg_pred"] = np.clip(rk_model.predict(d.loc[d_rk, ROOKIE_FEATS]), 0, None)
        d["projected_total"] = d.ppg_pred * d.games_pred
        d["vor"] = bb._vor(d, "projected_total")
        pop2 = d[d.adp_overall_rank.le(bb.DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        pop2["actual_total"] = pop2.target_ppg * pop2.target_games
        pop2["actual_vor"] = bb._vor(pop2, "actual_total")
        rk2 = pop2[pop2.is_rookie == 1]
        rho_rk = spearmanr(rk2.vor, rk2.actual_vor).statistic if len(rk2) >= 8 else np.nan
        rows.append((yr, len(rk2), rho_vet, rho_rk, rho_adp))
        print(f"  {yr:>6} {len(rk2):>5} {rho_vet:>10.3f} {rho_rk:>11.3f} {rho_adp:>7.3f}")

    arr = np.array([(r[2], r[3], r[4]) for r in rows if not np.isnan(r[2])])
    mv, mr, ma = arr.mean(0)
    print(f"  {'mean':>6} {'':>5} {mv:>10.3f} {mr:>11.3f} {ma:>7.3f}")
    print(f"\n  rookie model vs vet-on-rookies: {mr - mv:+.3f}")
    print(f"  rookie model vs ADP:            {mr - ma:+.3f}")
    if mr > ma + 0.01:
        print("  -> rookie model BEATS ADP on rookies (productionize)")
    elif mr > mv + 0.03:
        print("  -> rookie model improves the board but does NOT beat ADP (tool gain, not edge)")
    else:
        print("  -> no meaningful improvement (keep as documented experiment)")


def main():
    df = prep(pd.read_csv(bb.DATA))
    rk_tr = df[(df.is_rookie == 1) & df.target_ppg.notna() & (df.season < 2025)]
    best, cv = tune(rk_tr)
    print(f"tuned rookie params (cv wMAE={cv:.3f}): "
          f"{ {k: best[k] for k in ('depth','learning_rate','l2_leaf_reg')} }")
    holdout_mae(df, best)
    backtest(df, best)


if __name__ == "__main__":
    main()
