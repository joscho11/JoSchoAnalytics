"""Honest edge evaluation — isolate whether we know anything the MARKET doesn't.

Two evals that the rank-ρ test doesn't give us:

1. SLEEPER-RESIDUAL TEST (the gold standard for "did we find a hole"):
   - Fit, per fold on TRAIN, the market's expected PPG from Sleeper's projection.
   - residual = actual_ppg - expected_ppg  (where the market was actually wrong).
   - Fit a model on TRAIN residuals using ONLY orthogonal features (situational,
     bias flags, college — NO market inputs), predict TEST residuals.
   - OOS ρ(predicted_residual, actual_residual), pooled per position.
   - If > 0 meaningfully, we predict the market's errors => real, isolated edge.
     A PLACEBO (shuffled predictions) shows the zero-skill floor.

2. PLACEBO-CONTROLLED BUY/FADE: our buy/fade hit-rate minus a shuffled-prediction
   floor on the identical pool, so mean-reversion / pool-edge can't masquerade as skill.

Run:  python value_eval.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
from college_rookie_test import attach_college, COLLEGE
from opportunity_features import add_opportunity, OPP_COLS
from qb_context_features import add_qb_context, QB_COLS

HERE = Path(__file__).resolve().parent
USE_OPP = True                                  # toggle the new landing-spot/opportunity features
ORTHO = avm.SITU + avm.BIAS + COLLEGE + (OPP_COLS if USE_OPP else [])   # everything NOT from the market
rng = np.random.default_rng(42)


def _cat_fit(Xtr, ytr, Xte, w=None, cat=("position",)):
    cat = [c for c in cat if c in Xtr.columns]
    for c in cat:
        Xtr[c] = Xtr[c].astype(str); Xte[c] = Xte[c].astype(str)
    pool = Pool(Xtr, ytr, cat_features=cat, weight=w)
    m = CatBoostRegressor(iterations=400, depth=5, learning_rate=0.04, loss_function="MAE",
                          l2_leaf_reg=4.0, random_seed=42, verbose=0, allow_writing_files=False)
    m.fit(pool)
    return m.predict(Xte)


def residual_edge(df, ortho, test_seasons=range(2022, 2026), drafted_max=180):
    """Core walk-forward residual test for a given orthogonal feature set.
    Returns (pooled_edge_above_placebo, {season: per-season ρ}, allp)."""
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()
              & df["sleeper_pts_half_ppr"].notna()].copy()
    chunks = []
    for N in test_seasons:
        tr = pool[pool["season"] < N].copy()
        te = pool[pool["season"] == N].copy()
        if len(te) < 30 or len(tr) < 150:
            continue
        exp_tr = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                          tr[["sleeper_pts_half_ppr", "position"]].copy())
        exp_te = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                          te[["sleeper_pts_half_ppr", "position"]].copy())
        tr["resid"] = tr["target_ppg"].values - exp_tr
        te["resid"] = te["target_ppg"].values - exp_te
        feats = [c for c in ortho if c in tr.columns] + ["position"]
        te["pred_resid"] = _cat_fit(tr[feats].copy(), tr["resid"], te[feats].copy(),
                                    w=tr["sample_weight"].clip(lower=1))
        te["placebo_resid"] = rng.permutation(te["pred_resid"].values)
        te["fold"] = N
        chunks.append(te)
    allp = pd.concat(chunks, ignore_index=True)
    edge = (avm.wmean_pos_spearman(allp, "pred_resid", actual_col="resid")
            - avm.wmean_pos_spearman(allp, "placebo_resid", actual_col="resid"))
    per = {int(N): avm.wmean_pos_spearman(g, "pred_resid", actual_col="resid")
           for N, g in allp.groupby("fold")}
    return edge, per, allp


def sweep_feature_sets(df):
    df = avm.add_bias_features(df)
    LEAN = ["vacated_target_share", "vacated_rush_share", "prior_team_plays", "prior_team_pass_rate",
            "age", "prior_touches_pg", "prior_target_share", "ppg_trend", "prior_snap_share_pg",
            "draft_pick", "years_exp"]
    sets = {
        "SITU+BIAS": avm.SITU + avm.BIAS,
        "SITU+BIAS+COLLEGE": avm.SITU + avm.BIAS + COLLEGE,
        "SITU+BIAS+COLLEGE+QB": avm.SITU + avm.BIAS + COLLEGE + QB_COLS,
        "LEAN (11 hand-picked)": LEAN,
        "LEAN+QB": LEAN + QB_COLS,
        "LEAN+QB+college_dom": LEAN + QB_COLS + ["cfb_final_dom", "cfb_best_dom"],
    }
    print("=== FEATURE-SET SWEEP (residual edge above placebo; want high pooled AND recent) ===")
    print(f"  {'set':30s} {'pooled':>7} | {'2022':>6} {'2023':>6} {'2024':>6} {'2025*':>6}")
    best = None
    for name, fs in sets.items():
        edge, per, _ = residual_edge(df, fs)
        row = f"  {name:30s} {edge:+7.3f} | " + " ".join(f"{per.get(y, float('nan')):+6.3f}" for y in (2022, 2023, 2024, 2025))
        print(row)
        score = edge + per.get(2025, 0) + per.get(2024, 0)   # reward recent generalization
        if best is None or score > best[0]:
            best = (score, name, fs)
    print(f"\n  most robust set: {best[1]}  (* 2025 = live holdout)")
    return best[2]


def production_model_test(df, ortho, shrinks=(0.3, 0.5, 0.7, 1.0),
                          test_seasons=range(2022, 2026), drafted_max=180):
    """The decisive test: does (Sleeper anchor + shrink*residual) BEAT Sleeper alone OOS?
    Reports per-position ρ of the two-stage final projection vs the market baselines."""
    df = avm.add_bias_features(df)
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()
              & df["sleeper_pts_half_ppr"].notna()].copy()
    chunks = []
    for N in test_seasons:
        tr = pool[pool["season"] < N].copy()
        te = pool[pool["season"] == N].copy()
        if len(te) < 30 or len(tr) < 150:
            continue
        exp_tr = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                          tr[["sleeper_pts_half_ppr", "position"]].copy())
        te["exp"] = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                             te[["sleeper_pts_half_ppr", "position"]].copy())
        tr["resid"] = tr["target_ppg"].values - exp_tr
        te["resid"] = te["target_ppg"].values - te["exp"].values   # actual minus market expectation
        feats = [c for c in ortho if c in tr.columns] + ["position"]
        te["pred_resid"] = _cat_fit(tr[feats].copy(), tr["resid"], te[feats].copy(),
                                    w=tr["sample_weight"].clip(lower=1))
        chunks.append(te)
    allp = pd.concat(chunks, ignore_index=True)

    # standardize sleeper proj and our residual WITHIN (season, position), then nudge raw Sleeper
    def _z(s):
        sd = s.std()
        return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0
    allp["z_slp"] = allp.groupby(["season", "position"])["sleeper_pts_half_ppr"].transform(_z)
    allp["z_res"] = allp.groupby(["season", "position"])["pred_resid"].transform(_z)

    rho_adp = avm.wmean_pos_spearman(allp.assign(_a=-allp["adp_pos_rank"]), "_a")
    rho_slp = avm.wmean_pos_spearman(allp, "sleeper_pts_half_ppr")
    print("=== PRODUCTION TWO-STAGE TEST (does Sleeper + residual nudge beat Sleeper?) ===")
    print(f"  baselines:  ADP {rho_adp:+.3f}   Sleeper {rho_slp:+.3f}")
    best = None
    for sh in shrinks:
        allp["final"] = allp["z_slp"] + sh * allp["z_res"]   # raw-Sleeper anchor + residual nudge
        rho = avm.wmean_pos_spearman(allp, "final")
        per25 = avm.wmean_pos_spearman(allp[allp.season == 2025], "final")
        flag = " BEATS" if rho > rho_slp else ""
        print(f"  nudge {sh:.2f}:  final ρ {rho:+.3f}  (2025 {per25:+.3f})  vs Sleeper {rho - rho_slp:+.3f}{flag}")
        if best is None or rho > best[0]:
            best = (rho, sh)
    print(f"  best nudge {best[1]} -> ρ {best[0]:+.3f}  ({'BEATS' if best[0] > rho_slp else 'does NOT beat'} Sleeper {rho_slp:+.3f})")
    return allp


def broad_training_test(df, ortho, test_seasons=range(2022, 2026), drafted_max=180):
    """Attack the sample-size wall: train the residual model on the BROAD Sleeper-covered
    population (~2000 rows) vs only the drafted top-180 (~700), test value on the drafted
    pool either way. More training data should reduce the overfit that sinks new features."""
    df = avm.add_bias_features(df)
    cov = df["sleeper_pts_half_ppr"].notna() & df["target_ppg"].notna()
    print("=== TRAINING-SCOPE TEST (does more training data beat the overfit wall?) ===")
    for scope in ("drafted-only", "broad"):
        chunks = []
        for N in test_seasons:
            trm = df[cov & (df["season"] < N)]
            if scope == "drafted-only":
                trm = trm[trm["adp_overall_rank"] <= drafted_max]
            te = df[cov & (df["season"] == N) & (df["adp_overall_rank"] <= drafted_max)].copy()
            if len(te) < 30 or len(trm) < 150:
                continue
            trm = trm.copy()
            exp_tr = _cat_fit(trm[["sleeper_pts_half_ppr", "position"]].copy(), trm["target_ppg"],
                              trm[["sleeper_pts_half_ppr", "position"]].copy())
            te["exp"] = _cat_fit(trm[["sleeper_pts_half_ppr", "position"]].copy(), trm["target_ppg"],
                                 te[["sleeper_pts_half_ppr", "position"]].copy())
            trm["resid"] = trm["target_ppg"].values - exp_tr
            te["resid"] = te["target_ppg"].values - te["exp"].values
            feats = [c for c in ortho if c in trm.columns] + ["position"]
            te["pred_resid"] = _cat_fit(trm[feats].copy(), trm["resid"], te[feats].copy(),
                                        w=trm["sample_weight"].clip(lower=1))
            te["placebo"] = rng.permutation(te["pred_resid"].values)
            te["fold"] = N
            chunks.append(te)
        allp = pd.concat(chunks, ignore_index=True)
        edge = (avm.wmean_pos_spearman(allp, "pred_resid", actual_col="resid")
                - avm.wmean_pos_spearman(allp, "placebo", actual_col="resid"))
        per25 = avm.wmean_pos_spearman(allp[allp.season == 2025], "pred_resid", actual_col="resid")
        ntr = "all Sleeper-covered" if scope == "broad" else "top-180 only"
        print(f"  train={scope:13s} ({ntr:20s}): residual edge {edge:+.3f}  | 2025 ρ {per25:+.3f}")
    return allp


def residual_tail_test(allp, z_thresh=0.8):
    """Clean, isolated product test: does our ORTHOGONAL residual signal identify who
    beats/misses their SLEEPER expectation, at the tails? (allp from production_model_test,
    has z_res = standardized residual prediction, resid = actual - market-expected.)
    Compares to a shuffled placebo and reports a bootstrap 95% CI on the edge."""
    a = allp.dropna(subset=["z_res", "resid"]).copy()
    buy = a[a["z_res"] >= z_thresh]
    fade = a[a["z_res"] <= -z_thresh]
    buy_hit = (buy["resid"] > 0).mean()
    fade_hit = (fade["resid"] < 0).mean()
    # placebo: shuffle the signal, same tail sizes, many draws
    base_buy, base_fade = [], []
    for k in range(400):
        z = rng.permutation(a["z_res"].values)
        base_buy.append((a["resid"].values[z >= z_thresh] > 0).mean())
        base_fade.append((a["resid"].values[z <= -z_thresh] < 0).mean())
    pb, pf = np.nanmean(base_buy), np.nanmean(base_fade)
    # bootstrap CI on buy edge
    edges = []
    for k in range(1000):
        s = buy.sample(frac=1, replace=True, random_state=k)
        edges.append((s["resid"] > 0).mean() - pb)
    lo, hi = np.percentile(edges, [2.5, 97.5])
    print("=== RESIDUAL TAIL TEST (does our orthogonal signal beat SLEEPER at the tails?) ===")
    print(f"  BUY  (z_res>=+{z_thresh}): {buy_hit*100:.0f}% beat Sleeper exp (n={len(buy)})  vs placebo {pb*100:.0f}%  -> edge {(buy_hit-pb)*100:+.0f}pp")
    print(f"  FADE (z_res<=-{z_thresh}): {fade_hit*100:.0f}% missed (n={len(fade)})  vs placebo {pf*100:.0f}%  -> edge {(fade_hit-pf)*100:+.0f}pp")
    print(f"  BUY edge bootstrap 95% CI: [{lo*100:+.0f}pp, {hi*100:+.0f}pp]  "
          f"({'excludes 0 -> real' if lo > 0 else 'straddles 0 -> not significant'})")


def sleeper_residual_test(df, test_seasons=range(2022, 2026), drafted_max=180):
    df = avm.add_bias_features(df)
    pool = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()
              & df["sleeper_pts_half_ppr"].notna()].copy()

    chunks = []
    for N in test_seasons:
        tr = pool[pool["season"] < N].copy()
        te = pool[pool["season"] == N].copy()
        if len(te) < 30 or len(tr) < 150:
            continue
        # market expectation: actual_ppg ~ f(sleeper projection), per fold (no leakage)
        exp_tr = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                          tr[["sleeper_pts_half_ppr", "position"]].copy())
        exp_te = _cat_fit(tr[["sleeper_pts_half_ppr", "position"]].copy(), tr["target_ppg"],
                          te[["sleeper_pts_half_ppr", "position"]].copy())
        tr["resid"] = tr["target_ppg"].values - exp_tr
        te["resid"] = te["target_ppg"].values - exp_te
        # predict the residual from ORTHOGONAL features only
        feats = [c for c in ORTHO if c in tr.columns] + ["position"]
        pr = _cat_fit(tr[feats].copy(), tr["resid"], te[feats].copy(),
                      w=tr["sample_weight"].clip(lower=1))
        te["pred_resid"] = pr
        te["placebo_resid"] = rng.permutation(pr)
        te["fold"] = N
        chunks.append(te)
        last_model = (tr[feats].copy(), tr["resid"], feats)   # for importance

    allp = pd.concat(chunks, ignore_index=True)
    rho_edge = avm.wmean_pos_spearman(allp, "pred_resid", actual_col="resid")
    rho_plac = avm.wmean_pos_spearman(allp, "placebo_resid", actual_col="resid")
    r_overall = allp["pred_resid"].corr(allp["resid"])
    print("=== SLEEPER-RESIDUAL TEST (can we predict where the market is wrong?) ===")
    print(f"  pooled per-position ρ(pred_resid, actual_resid): {rho_edge:+.3f}")
    print(f"  placebo floor (shuffled):                        {rho_plac:+.3f}")
    print(f"  overall Pearson r:                               {r_overall:+.3f}")
    print(f"  EDGE above placebo: {rho_edge - rho_plac:+.3f}   "
          f"({'real signal' if rho_edge - rho_plac > 0.05 else 'no meaningful edge'})")
    print("  per-season ρ (pred vs actual residual):")
    for N, g in allp.groupby("fold"):
        print(f"    {int(N)}: {avm.wmean_pos_spearman(g, 'pred_resid', actual_col='resid'):+.3f}  (n={len(g)})")
    # feature importance from a final fit on all pre-2025 residuals
    Xtr, ytr, feats = last_model
    for c in ["position"]:
        Xtr[c] = Xtr[c].astype(str)
    fm = CatBoostRegressor(iterations=400, depth=5, learning_rate=0.04, loss_function="MAE",
                           l2_leaf_reg=4.0, random_seed=42, verbose=0, allow_writing_files=False)
    fm.fit(Pool(Xtr, ytr, cat_features=["position"]))
    imp = pd.Series(fm.feature_importances_, index=feats).sort_values(ascending=False)
    print("  top features driving the residual prediction:")
    for k, v in imp.head(12).items():
        print(f"    {v:5.1f}  {k}")
    return allp


def placebo_buyfade(df, test_seasons=range(2022, 2026), buy_thresh=4, drafted_max=180):
    df = avm.add_bias_features(df)
    graded = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()].copy()
    chunks = []
    for N in test_seasons:
        tr = df[(df["season"] < N) & df["adp_pos_rank"].notna()]
        te = graded[graded["season"] == N].copy()
        if len(te) < 30:
            continue
        te["pred"] = avm.fit_predict(tr, te, avm.SITU + avm.BIAS + avm.MARKET)
        te["adp_posrk"] = te.groupby("position")["adp_pos_rank"].transform(lambda s: avm.pos_rank(s, ascending=True))
        te["pred_posrk"] = te.groupby("position")["pred"].transform(lambda s: avm.pos_rank(s))
        te["actual_posrk"] = te.groupby("position")["target_ppg"].transform(lambda s: avm.pos_rank(s))
        te["plac"] = rng.permutation(te["pred"].values)   # shuffled predictions = zero-skill control
        te["plac_posrk"] = te.groupby("position")["plac"].transform(lambda s: avm.pos_rank(s))
        chunks.append(te)
    allp = pd.concat(chunks, ignore_index=True)
    allp["beat"] = allp["adp_posrk"] - allp["actual_posrk"]

    def rates(predrk):
        val = allp["adp_posrk"] - allp[predrk]
        b = allp[val >= buy_thresh]; f = allp[val <= -buy_thresh]
        return (b["beat"] > 0).mean(), len(b), (f["beat"] < 0).mean(), len(f)

    bh, bn, fh, fn = rates("pred_posrk")
    pbh, pbn, pfh, pfn = rates("plac_posrk")
    print("\n=== PLACEBO-CONTROLLED BUY/FADE (vs ADP) ===")
    print(f"  model  BUY {bh*100:4.0f}% (n={bn})   FADE {fh*100:4.0f}% (n={fn})")
    print(f"  placebo BUY {pbh*100:4.0f}% (n={pbn})   FADE {pfh*100:4.0f}% (n={pfn})  <- artifact floor")
    print(f"  EDGE above placebo: BUY {(bh-pbh)*100:+.0f}pp  FADE {(fh-pfh)*100:+.0f}pp")


def main():
    df = pd.read_csv(avm.newest_dataset())
    df = attach_college(df)
    df = add_opportunity(df)
    df = add_qb_context(df)
    broad_training_test(df, avm.SITU + avm.BIAS + COLLEGE)
    print()
    sweep_feature_sets(df)
    print()
    allp = production_model_test(df, avm.SITU + avm.BIAS + COLLEGE)
    print()
    residual_tail_test(allp)
    print()
    sleeper_residual_test(df)
    placebo_buyfade(df)


if __name__ == "__main__":
    main()
