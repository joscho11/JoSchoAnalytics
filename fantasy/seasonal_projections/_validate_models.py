"""Validate the bakeoff finding: do LightGBM/RF/XGB really beat CatBoost per-position,
and does the better standalone model improve the BLEND (our model + Sleeper) — the product?"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college

GPS = 17


def wmae(e, w):
    return float(np.sum(np.abs(e) * w) / np.sum(w))


def main():
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    feats = [c for c in mb.FEATS if c in df.columns]
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    trainable = df[df["target_ppg"].notna()].copy()

    cfgs = {
        "CatBoost": ("catboost", dict(depth=5, learning_rate=0.04, l2_leaf_reg=4, iterations=400)),
        "LightGBM": ("lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8)),
        "RandomForest": ("rf", dict(n_estimators=400, max_depth=8, min_samples_leaf=5)),
        "XGBoost": ("xgb", dict(max_depth=4, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8)),
    }
    chunks = []
    for N in range(2021, 2026):
        tr = trainable[trainable["season"] < N]
        te = pool[pool["season"] == N].copy()
        if len(te) < 20:
            continue
        for nm, (fam, pr) in cfgs.items():
            te[nm] = mb.fit_predict(fam, pr, tr, te, feats)
        chunks.append(te)
    a = pd.concat(chunks, ignore_index=True)
    a["TreeEns"] = a[["LightGBM", "RandomForest", "XGBoost"]].mean(axis=1)
    a["sleeper_ppg"] = a["sleeper_pts_half_ppr"] / GPS
    models = ["CatBoost", "LightGBM", "RandomForest", "XGBoost", "TreeEns"]

    print("=== standalone PPG MAE by position (pooled 2021-2025) ===")
    print(f"  {'model':14s} {'QB':>5} {'RB':>5} {'WR':>5} {'TE':>5} {'ALL':>5} {'2025':>6}")
    for m in models:
        cells = []
        for pos in ["QB", "RB", "WR", "TE", None]:
            g = a if pos is None else a[a["position"] == pos]
            cells.append(wmae(g[m] - g["target_ppg"], g["sample_weight"].clip(lower=1)))
        g25 = a[a["season"] == 2025]
        c25 = wmae(g25[m] - g25["target_ppg"], g25["sample_weight"].clip(lower=1))
        print(f"  {m:14s} " + " ".join(f"{c:5.2f}" for c in cells) + f" {c25:6.2f}")

    # does the better standalone improve the blend? sweep weight for CatBoost vs TreeEns
    print("\n=== BLEND with Sleeper: best ALL MAE (sweep our-weight) ===")
    both = a.dropna(subset=["sleeper_ppg", "target_ppg"]).copy()
    base = wmae(both["sleeper_ppg"] - both["target_ppg"], both["sample_weight"].clip(lower=1))
    print(f"  Sleeper alone: {base:.3f}")
    for m in ["CatBoost", "TreeEns"]:
        best = (base, 0.0)
        for w in np.arange(0, 0.61, 0.05):
            bl = w * both[m] + (1 - w) * both["sleeper_ppg"]
            mae = wmae(bl - both["target_ppg"], both["sample_weight"].clip(lower=1))
            if mae < best[0]:
                best = (mae, w)
        b25 = both[both["season"] == 2025]
        bl25 = best[1] * b25[m] + (1 - best[1]) * b25["sleeper_ppg"]
        print(f"  blend({m:8s}+Sleeper): best w={best[1]:.2f} -> MAE {best[0]:.3f} "
              f"(beats Sleeper {base-best[0]:+.3f}) | 2025 {wmae(bl25-b25['target_ppg'], b25['sample_weight'].clip(lower=1)):.3f}")


if __name__ == "__main__":
    main()
