"""Step 2 (H4, PREREGISTRATION.md): ADP-anchored residual model — one-shot test.

Architecture (frozen per H4, committed 3b5fbb8 before this file existed):
  final = implied + lambda * residual_pred, where
  - implied  = per-position isotonic (monotone non-increasing) curve of actual
               half-PPR points on within-position ADP rank, fit on seasons < t
  - residual = actual_pts - implied, modeled by the frozen A1/A3 LightGBM config
               on the frozen phase0 feature set (harness columns excluded)
  - lambda   in {0, .25, .5, .75, 1}, selected PER POSITION by inner walk-forward
               CV touching only seasons < t; lambda=0 recovers raw ADP exactly
               (final score embeds a -1e-6 * adp_pos_rank tie-break so isotonic
               flat segments cannot reorder vs the market).
  Residual fit is UNWEIGHTED (decided blind, pre-metric): the target is a season
  TOTAL residual, not a rate; games-weighting would down-weight exactly the bust
  rows that carry the market-error signal.

Pool: ADP top-180 per season (phase0 convention). Positions RB/WR/TE (QB is
market rank per Amendment 2). Null = raw ADP, same `adp` column as the anchor.

Modes:
  python step2_residual_model.py          -> Sub-step F: build + structural
      asserts + provenance. Prints NO evaluation metric of any kind.
  python step2_residual_model.py --fire   -> Sub-step G: the one shot. Applies
      the H4 decision rule verbatim and prints the pre-declared non-gating
      residual board for the most recent season.

Hard fence: no season < 2016 is ever predicted or scored (asserted).
"""
import sys
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
from lightgbm import LGBMRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE      = Path(__file__).resolve().parent
OUT_JSON  = HERE / "step2_results.json"
POS       = ["RB", "WR", "TE"]
LAMBDAS   = [0.0, 0.25, 0.5, 0.75, 1.0]
# Folds start at 2016: an inner fold at 2015 would compute a model-skill metric
# on a preserved-unseen season (2008-2015). For t=2016 the inner set is empty and
# lambda defaults to 0 (= raw ADP, the conservative pre-specified fallback).
FOLDS     = list(range(2016, 2026))     # fold s trained on pool seasons < s
EVAL_MIN  = 2016                        # hard fence (same as extension_gate)
PRIMARY   = list(range(2020, 2026))
CONTEXT   = list(range(2016, 2020))
TIEBREAK  = 1e-6


def build_pool():
    df = pb.assemble()                                   # 2014+ dataset + adp + actual_pts
    df["finish_all"] = pb.finish_ranks(df)
    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]
    pool = pool[pool["position"].isin(POS)].copy()
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    harness_cols = {"actual_pts", "adp", "ffc_adp", "ecr", "naive_pts", "naive_ppg17",
                    "age_curve", "model_wf", "finish_all", "adp_overall", "adp_pos_rank",
                    "implied", "resid_pred", "final"}
    feats = [c for c in pool.columns if c not in pb.EXCLUDE and c not in harness_cols]
    return df, pool, feats


def provenance(pool):
    """F5: which series populates `adp` per eval season (anchor == null check)."""
    print("\n=== F5 ADP provenance (anchor and null are the same `adp` column) ===")
    for s in CONTEXT + PRIMARY:
        rows = pool[pool.season == s]
        sleeper = rows["adp_half_ppr"].notna().mean()
        src = "Sleeper half-PPR" if sleeper > 0.99 else \
              ("FFC (half-PPR)" if s >= 2018 else "FFC (PPR proxy)") if sleeper < 0.01 else "MIXED"
        print(f"  {s}: {src}  (sleeper-sourced {sleeper:.0%}, n={len(rows)})")
        assert src != "MIXED", f"{s}: anchor series is mixed — investigate before firing"
    ok = all(pool[pool.season.isin(PRIMARY)]["adp_half_ppr"].notna())
    print(f"  primary panel 2020-2025 entirely Sleeper half-PPR: {ok}")
    return ok


def run_folds(pool, feats):
    """One pass: for each fold s, iso curve + residual model trained on < s,
    predictions for season s. Returns pool with implied/resid_pred + fit logs."""
    pool = pool.sort_values(["season", "position", "adp_pos_rank"]).reset_index(drop=True)
    pool["implied"] = np.nan
    pool["resid_pred"] = np.nan
    curves = {}
    for s in FOLDS:
        tr = pool[pool.season < s]
        te_idx = pool.index[pool.season == s]
        if not len(te_idx):
            continue
        assert tr["season"].max() < s, f"fold {s}: training rows leak season >= {s}"
        for p in POS:
            trp = tr[tr.position == p]
            tep = pool.loc[te_idx][pool.loc[te_idx, "position"] == p]
            if len(trp) < 20 or not len(tep):
                continue
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not non-increasing at fold {s} {p}"
            curves[(s, p)] = {int(r): float(iso.predict([r])[0]) for r in (1, 6, 12, 24, 36)}
            tr_implied = iso.predict(trp["adp_pos_rank"])
            m = LGBMRegressor(**pb.LGBM_PARAMS)
            m.fit(trp[feats], trp["actual_pts"] - tr_implied)      # unweighted, see docstring
            pool.loc[tep.index, "implied"]    = iso.predict(tep["adp_pos_rank"])
            pool.loc[tep.index, "resid_pred"] = m.predict(tep[feats])
    return pool, curves


def final_score(pool, lam_by_pos):
    lam = pool["position"].map(lam_by_pos)
    return (pool["implied"] + lam * pool["resid_pred"]
            - TIEBREAK * pool["adp_pos_rank"])


def season_rho(rows, col, ascending=False):
    if rows[col].notna().sum() < 5:
        return np.nan
    r = spearmanr(rows[col], rows["actual_pts"]).statistic
    return -r if ascending else r


def select_lambda(pool, t):
    """lambda* per position from inner folds s in [2015, t): mean within-position
    season rho of implied + lambda*resid. Touches only seasons < t (asserted)."""
    inner = pool[(pool.season >= FOLDS[0]) & (pool.season < t) & pool["implied"].notna()]
    assert inner.empty or inner["season"].max() < t, f"lambda selection for {t} touched season >= {t}"
    lam_by_pos = {}
    for p in POS:
        best, best_rho = 0.0, -9
        for lam in LAMBDAS:
            sc = inner[inner.position == p].copy()
            if not len(sc):
                continue
            sc["sc"] = sc["implied"] + lam * sc["resid_pred"] - TIEBREAK * sc["adp_pos_rank"]
            rhos = [season_rho(g, "sc") for _, g in sc.groupby("season")]
            r = float(np.nanmean(rhos)) if rhos else np.nan
            if not np.isnan(r) and r > best_rho:
                best_rho, best = r, lam
        lam_by_pos[p] = best
    return lam_by_pos


def assert_lambda0_is_adp(pool):
    """F4: lambda=0 must reproduce raw-ADP within-position ordering exactly.
    Checked on TRAINING-fold rows only (season 2019, a fold never in the primary panel)."""
    chk = pool[(pool.season == 2019) & pool["implied"].notna()].copy()
    chk["sc0"] = chk["implied"] - TIEBREAK * chk["adp_pos_rank"]
    for p in POS:
        g = chk[chk.position == p]
        rho = spearmanr(-g["sc0"], g["adp_pos_rank"]).statistic
        assert abs(rho - 1.0) < 1e-9, f"lambda=0 != raw ADP at {p} (rho {rho})"
    print("  assert lambda=0 == raw ADP ordering (within position, fold 2019): PASS")


def substep_f():
    df, pool, feats = build_pool()
    prov_ok = provenance(pool)
    pool, curves = run_folds(pool, feats)
    assert pool[pool["resid_pred"].notna()]["season"].min() >= FOLDS[0]
    assert_lambda0_is_adp(pool)
    print("  assert every fold trains strictly on seasons < t: PASS (asserted per fold)")
    print("  assert isotonic non-increasing at every fold/position: PASS (asserted per fit)")
    lam_log = {t: select_lambda(pool, t) for t in CONTEXT + PRIMARY}
    print(f"\n=== F6 build report (NO evaluation metrics) ===")
    print(f"  features ({len(feats)}): {feats}")
    print(f"  lambda grid {LAMBDAS}, selected per position by inner walk-forward CV (< t only):")
    for t, lp in lam_log.items():
        print(f"    t={t}: " + "  ".join(f"{p} {lp[p]:.2f}" for p in POS))
    print("  isotonic curve shape, fold t=2020 (fit on 2014-2019), implied pts at pos-rank 1/6/12/24/36:")
    for p in POS:
        c = curves[(2020, p)]
        print(f"    {p}: " + "  ".join(f"r{r}={c[r]:.0f}" for r in (1, 6, 12, 24, 36)))
    print(f"  pool rows: {len(pool):,} ({pool.season.min()}-{pool.season.max()}); "
          f"per season ~{len(pool)//pool.season.nunique()}")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. Sub-step G (--fire) runs this exact code once.")
    return df, pool, feats, lam_log


def substep_g():
    df, pool, feats, lam_log = substep_f()
    assert pool[pool["resid_pred"].notna()]["season"].min() >= EVAL_MIN, "fenced season predicted"
    # score model + adp on both panels
    res = {}
    per_season_pooled_delta = {}
    for title, seasons in (("2020-2025", PRIMARY), ("2016-2019", CONTEXT)):
        p = pool[pool.season.isin(seasons)].copy()
        assert p.season.min() >= EVAL_MIN, "fenced season scored"
        lam_col = pd.concat([final_score(p[p.season == t], lam_log[t]) for t in seasons])
        p["final"] = lam_col
        stats = {}
        for pos in POS:
            g = p[p.position == pos]
            by_season = {int(t): {"model": season_rho(g[g.season == t], "final"),
                                  "adp":   season_rho(g[g.season == t], "adp", ascending=True)}
                         for t in seasons}
            e = pb.eval_source(p, "final", False, positions=[pos]).get(pos, {})
            a = pb.eval_source(p, "adp", True, positions=[pos]).get(pos, {})
            stats[pos] = {"rho_model": float(np.nanmean([v["model"] for v in by_season.values()])),
                          "rho_adp":   float(np.nanmean([v["adp"] for v in by_season.values()])),
                          "by_season": by_season,
                          "top12_model": e.get("top12_hit"), "top12_adp": a.get("top12_hit"),
                          "bust_model": e.get("bust_rate"), "bust_adp": a.get("bust_rate")}
        res[title] = stats
        per_season_pooled_delta[title] = {
            int(t): float(np.nanmean([stats[pos]["by_season"][t]["model"] -
                                      stats[pos]["by_season"][t]["adp"] for pos in POS]))
            for t in seasons}

    s = res["2020-2025"]
    pooled_m = np.mean([s[p]["rho_model"] for p in POS])
    pooled_a = np.mean([s[p]["rho_adp"] for p in POS])
    d_pooled = round(pooled_m - pooled_a, 3)
    signs = per_season_pooled_delta["2020-2025"]
    n_pos_seasons = sum(1 for v in signs.values() if v > 0)
    floors = {p: round(s[p]["rho_model"] - s[p]["rho_adp"], 3) for p in POS}
    worst = min(floors.values())
    t12_m = np.mean([s[p]["top12_model"] for p in POS])
    t12_a = np.mean([s[p]["top12_adp"] for p in POS])
    bust_m = np.mean([s[p]["bust_model"] for p in POS])
    bust_a = np.mean([s[p]["bust_adp"] for p in POS])
    both_worse = (t12_m < t12_a) and (bust_m > bust_a)

    ca = d_pooled >= 0.020
    cb = n_pos_seasons >= 4
    cc = worst >= -0.010
    cd = not both_worse
    verdict = "PASS" if (ca and cb and cc and cd) else "FAIL"

    print("\n" + "=" * 78)
    print("SUB-STEP G — THE ONE SHOT (H4 decision rule, verbatim)")
    print("=" * 78)
    print(f"\n2020-2025, ADP-top-180 pool | {'pos':4} {'model rho':>10} {'raw ADP':>9} {'delta':>8}")
    for p in POS:
        print(f"{'':33}{p:4} {s[p]['rho_model']:10.3f} {s[p]['rho_adp']:9.3f} {floors[p]:+8.3f}")
    print(f"{'':33}POOL {pooled_m:10.3f} {pooled_a:9.3f} {d_pooled:+8.3f}")
    print("\nper-season pooled delta signs (2020-2025): " +
          "  ".join(f"{t}:{'+' if v > 0 else '-'}({v:+.3f})" for t, v in signs.items()))
    print(f"\ntop-12 hit  (pooled): model {t12_m:.3f} vs ADP {t12_a:.3f}")
    print(f"bust rate   (pooled): model {bust_m:.3f} vs ADP {bust_a:.3f}")
    print(f"\nH4 criteria:")
    print(f"  (a) pooled delta rho {d_pooled:+.3f} >= +0.020 : {ca}")
    print(f"  (b) positive pooled delta in {n_pos_seasons}/6 seasons >= 4 : {cb}")
    print(f"  (c) worst position delta {worst:+.3f} >= -0.010 : {cc}")
    print(f"  (d) top-12 and bust not BOTH worse : {cd}")
    print(f"\nH4 VERDICT: {verdict}")

    print("\ncontext (never a gate): from-scratch model 2020-25 rho RB .520 / WR .500 / TE .323;")
    print("Sleeper preseason 2020-25 rho RB .754 / WR .712 / TE .608 (phase0 results)")
    c = res["2016-2019"]
    print("2016-2019 context panel: " + "  ".join(
        f"{p} model {c[p]['rho_model']:.3f} vs ADP {c[p]['rho_adp']:.3f}" for p in POS))

    print("\n" + "-" * 78)
    print("PRE-DECLARED NON-GATING DIAGNOSTIC — descriptive only, NOT evidence" +
          (" (gate FAILED: this is explicitly not a salvage)" if verdict == "FAIL" else ""))
    last = pool[pool.season == pool.season.max()].copy()
    last["shrunk"] = [lam_log[int(r.season)][r.position] * r.resid_pred for r in last.itertuples()]
    for p in POS:
        g = last[last.position == p].dropna(subset=["shrunk"])
        top = g.nlargest(10, "shrunk"); bot = g.nsmallest(10, "shrunk")
        print(f"\n  {p} {int(last.season.max())} — market too LOW (top 10 shrunk residuals):")
        print("    " + "; ".join(f"{r.player} ({r.shrunk:+.0f})" for r in top.itertuples()))
        print(f"  {p} — market too HIGH (bottom 10):")
        print("    " + "; ".join(f"{r.player} ({r.shrunk:+.0f})" for r in bot.itertuples()))

    OUT_JSON.write_text(json.dumps(
        {"results": res, "per_season_pooled_delta": per_season_pooled_delta,
         "criteria": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)},
         "verdict": verdict, "lambda_log": {str(k): v for k, v in lam_log.items()}},
        indent=2, default=float))
    print(f"\nwrote {OUT_JSON.name}")
    return verdict


if __name__ == "__main__":
    if "--fire" in sys.argv:
        substep_g()
    else:
        substep_f()
