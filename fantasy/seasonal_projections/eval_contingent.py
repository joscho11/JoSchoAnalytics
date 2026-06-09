"""Test whether the contingent-opportunity features improve the seasonal PPG model.

Compares the best model (LightGBM) with vs without contingent_tgt_opp / contingent_rush_opp,
games-weighted PPG MAE, walk-forward, per position (it should help WR/RB most if anything).
Also checks the placebo-controlled residual edge (does it sharpen value-vs-market signal).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college
from contingent_features import add_contingent_opportunity, CONTINGENT_COLS

LGBM = ("lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8))


def wmae(e, w):
    return float(np.sum(np.abs(e) * w) / np.sum(w))


def predict(df, feats, test_seasons=range(2021, 2026), drafted_max=180):
    tr_all = df[df["target_ppg"].notna()]
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()]
    chunks = []
    for N in test_seasons:
        tr = tr_all[tr_all["season"] < N]
        te = pool[pool["season"] == N].copy()
        if len(te) < 20:
            continue
        te["pred"] = mb.fit_predict(LGBM[0], LGBM[1], tr, te, feats)
        chunks.append(te)
    return pd.concat(chunks, ignore_index=True)


def main():
    df = avm.add_bias_features(add_contingent_opportunity(attach_college(pd.read_csv(avm.newest_dataset()))))
    base = [c for c in mb.FEATS if c in df.columns]
    plus = base + CONTINGENT_COLS

    a0 = predict(df, base)
    a1 = predict(df, plus)
    print("PPG MAE (LightGBM), games-weighted — base vs +contingent:")
    print(f"  {'pos':4s} {'base':>6} {'+cont':>6} {'Δ':>7}")
    for pos in ["QB", "RB", "WR", "TE", None]:
        g0 = a0 if pos is None else a0[a0["position"] == pos]
        g1 = a1 if pos is None else a1[a1["position"] == pos]
        m0 = wmae(g0["pred"] - g0["target_ppg"], g0["sample_weight"].clip(lower=1))
        m1 = wmae(g1["pred"] - g1["target_ppg"], g1["sample_weight"].clip(lower=1))
        lab = "ALL" if pos is None else pos
        print(f"  {lab:4s} {m0:6.3f} {m1:6.3f} {m1-m0:+7.3f}")
    for yr in (2025,):
        g0 = a0[a0["season"] == yr]; g1 = a1[a1["season"] == yr]
        m0 = wmae(g0["pred"] - g0["target_ppg"], g0["sample_weight"].clip(lower=1))
        m1 = wmae(g1["pred"] - g1["target_ppg"], g1["sample_weight"].clip(lower=1))
        print(f"  {yr} ALL  {m0:6.3f} {m1:6.3f} {m1-m0:+7.3f}  (live test)")
    print("\n(negative Δ = contingent features help; lower MAE is better)")


if __name__ == "__main__":
    main()
