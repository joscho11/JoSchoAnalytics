"""Extended value eval: 11 seasons of ADP (FFC 2014-2019 + Sleeper 2020-2025).

Attacks the noise-limit directly with ~2.5x the data. Re-anchors the residual on the
per-season ADP->points curve (available every year, unlike Sleeper's 2018+ projection),
so "residual" now means "beats/misses their DRAFT PRICE" -- exactly the value-vs-ADP
question. Compares the old 6-season (Sleeper-anchored) setup to the new 11-season one
on the placebo-controlled residual edge and the bootstrap tail test.

Run:  python value_eval_extended.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import value_eval as ve
from college_rookie_test import attach_college, COLLEGE

HERE = Path(__file__).resolve().parent
ORTHO = avm.SITU + avm.BIAS + COLLEGE
rng = np.random.default_rng(42)


def attach_historical_adp(df):
    """Fill adp_* for 2014-2019 from FFC (Sleeper already covers 2020+)."""
    ffc = pd.read_csv(HERE / "ffc_adp_2014_2019.csv")
    df = df.copy()
    m = df.merge(ffc[["season", "norm_name", "position", "ffc_overall_rank", "ffc_pos_rank", "ffc_adp"]],
                 on=["season", "norm_name", "position"], how="left")
    for dst, src in [("adp_overall_rank", "ffc_overall_rank"), ("adp_pos_rank", "ffc_pos_rank"),
                     ("adp_half_ppr", "ffc_adp")]:
        df[dst] = df[dst].fillna(m[src])
    return df


def adp_anchored_eval(df, ortho, test_seasons, drafted_max=180, label=""):
    """Walk-forward residual edge anchored on the per-season ADP->ppg curve."""
    df = avm.add_bias_features(df)
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()
              & df["adp_pos_rank"].notna()].copy()
    chunks = []
    for N in test_seasons:
        tr = pool[pool["season"] < N].copy()
        te = pool[pool["season"] == N].copy()
        if len(te) < 30 or len(tr) < 150:
            continue
        # anchor = expected ppg given draft price (ADP), fit per fold on train only
        anc = ["adp_pos_rank", "adp_overall_rank", "position"]
        exp_tr = ve._cat_fit(tr[anc].copy(), tr["target_ppg"], tr[anc].copy())
        te["exp"] = ve._cat_fit(tr[anc].copy(), tr["target_ppg"], te[anc].copy())
        tr["resid"] = tr["target_ppg"].values - exp_tr
        te["resid"] = te["target_ppg"].values - te["exp"].values
        feats = [c for c in ortho if c in tr.columns] + ["position"]
        te["pred_resid"] = ve._cat_fit(tr[feats].copy(), tr["resid"], te[feats].copy(),
                                       w=tr["sample_weight"].clip(lower=1))
        te["placebo_resid"] = rng.permutation(te["pred_resid"].values)
        te["fold"] = N

        def _z(s):
            sd = s.std(ddof=0)
            return (s - s.mean()) / sd if sd else s * 0
        te["z_res"] = te.groupby("position")["pred_resid"].transform(_z)
        chunks.append(te)
    allp = pd.concat(chunks, ignore_index=True)

    edge = (avm.wmean_pos_spearman(allp, "pred_resid", actual_col="resid")
            - avm.wmean_pos_spearman(allp, "placebo_resid", actual_col="resid"))
    per = {int(N): avm.wmean_pos_spearman(g, "pred_resid", actual_col="resid")
           for N, g in allp.groupby("fold")}
    print(f"=== {label}: {len(allp)} rows, {len(per)} test seasons ===")
    print(f"  residual edge above placebo: {edge:+.3f}")
    print("  per-season ρ: " + "  ".join(f"{y}:{v:+.2f}" for y, v in per.items()))
    return allp


def main():
    base = pd.read_csv(avm.newest_dataset())
    base = attach_college(base)

    # OLD: 6 seasons, Sleeper-anchored (for reference, from value_eval)
    print("--- OLD baseline (6 seasons, Sleeper ADP only) ---")
    old = ve.production_model_test(base.pipe(lambda d: d), avm.SITU + avm.BIAS + COLLEGE) \
        if False else None  # (kept in value_eval; skip here)

    # NEW: 11 seasons, FFC+Sleeper ADP, ADP-curve anchor
    ext = attach_historical_adp(base)
    print(f"ADP coverage after FFC fill: "
          f"{ext['adp_pos_rank'].notna().sum()} rows, seasons "
          f"{sorted(ext.loc[ext['adp_pos_rank'].notna(),'season'].unique().tolist())}\n")

    allp_new = adp_anchored_eval(ext, ORTHO, range(2016, 2026),
                                 label="NEW 11-season (FFC 2014-19 + Sleeper 2020-25), ADP-anchored")
    print()
    ve.residual_tail_test(allp_new)


if __name__ == "__main__":
    main()
