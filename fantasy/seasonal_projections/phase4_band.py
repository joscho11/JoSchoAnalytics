"""Phase 4 core v2: calibrated uncertainty band around the market's point estimate.

ENGINEERING, not a gated test — definitions pinned BEFORE computation, LOSO
validation, miscalibration reported flat. v1 findings (2026-07-11, kept in
phase4_validation_v1.json semantics): 80% band covered 77.3%, rank-banding LOST
to a constant-width baseline on pinball, unprojected rows 1/7 covered.

v2 refinements (R1, pinned blind before any refined number existed):
  1. SIMPLIFIED: residual pools are POSITION-LEVEL x estimate_source. Rank still
     conditions the point estimate and P(top-N)/bust through the estimate; only
     the spread is flat per position. All band/merge machinery removed.
  2. WIDENING from convention, zero parameters: quantiles use the Weibull (n+1)
     plotting-position convention (numpy method="weibull"), the standard
     exceedance-unbiased finite-sample estimator, replacing the default linear
     method that biases small-sample tails inward. Not tuned to any target.
  3. MISSING-PROJECTION FLAG: is_unprojected rows draw bands from the
     UNPROJECTED-row residual pool only (actual - adp_implied on projection-
     missing pool rows; tiny n): P10/P90 = empirical min/max of that pool,
     P25/50/75 Weibull, band_confidence = LOW (NORMAL otherwise). Empty-pool
     fallback = cross-position unprojected pool. Flag + label ship in-schema.
  4. P(top-12) high-decile overconfidence: LEFT, documented (n=10 cells).

Everything else unchanged from v1 pins: levels P10/25/50/75/90; additive
residuals; P(top-N) = share of pool residuals with estimate + r >= T_N
(T_N = mean N-th-best actual among position actives, train seasons);
bust = phase0 convention (drafted top-24/12, P(finish below T_36/T_18));
crossing guard per row; isotonic ADP curve fit on calibration seasons only;
Q1 scope fence (functions of point estimate/position/rank/actuals ONLY);
H7 embargo (no efficiency fields); pool = ADP top-180 phase0 convention.

Modes:
  python phase4_band.py            -> LOSO validation 2021-2025 -> phase4_validation.json
  python phase4_band.py --artifact -> 2026 payload -> phase4_band_2026.csv
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE     = Path(__file__).resolve().parent
ADP_CSV  = HERE / "sleeper_adp_2020_2026.csv"
VAL_JSON = HERE / "phase4_validation.json"
ART_CSV  = HERE / "phase4_band_2026.csv"

POS4     = ["QB", "RB", "WR", "TE"]
PANEL    = list(range(2021, 2026))
LEVELS   = [10, 25, 50, 75, 90]
QMETHOD  = "weibull"                 # (n+1) plotting-position convention (R1 pin 2)
MIN_POOL = 40                        # below this: min/max tails + LOW confidence
TOP_N    = [12, 24]
BUST_DRAFT  = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}     # phase0 convention
BUST_FINISH = {"QB": 18, "RB": 36, "WR": 36, "TE": 18}
LICENSE_POINT  = "powered by Sleeper's projections vs the draft market"
LICENSE_SIGNAL = ("disagreement signal validated in aggregate (stable veterans); "
                  "threshold tiers unvalidated; volatile slice unvalidated")


def load_panel():
    df = pb.assemble()
    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[(pool["adp_overall"] <= pb.POOL_SIZE) & pool["position"].isin(POS4)]
    pool = pool[pool["season"].isin(PANEL)].copy()
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    return df, pool


def fit_adp_curves(train_pool):
    curves = {}
    for p in POS4:
        t = train_pool[train_pool.position == p]
        iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
        iso.fit(t["adp_pos_rank"], t["actual_pts"])
        curves[p] = iso
    return curves


def finish_thresholds(df_all, seasons):
    T = {}
    need = sorted(set(TOP_N + list(BUST_FINISH.values())))
    for p in POS4:
        for n in need:
            vals = [df_all[(df_all.season == s) & (df_all.position == p)]["actual_pts"]
                    .nlargest(n).iloc[-1] for s in seasons]
            T[(p, n)] = float(np.mean(vals))
    return T


def build_tables(train_pool, curves):
    """Position-level residual pools: ('sleeper', pos) from projected rows,
    ('adp_implied', pos) from UNPROJECTED rows only; ('adp_implied','ALL') fallback."""
    tp = train_pool.copy()
    tp["adp_implied"] = [curves[r.position].predict([r.adp_pos_rank])[0]
                         for r in tp.itertuples()]
    proj = tp[tp.sleeper_pts_half_ppr.notna()]
    unproj = tp[tp.sleeper_pts_half_ppr.isna()]
    tables = {}
    for p in POS4:
        pp = proj[proj.position == p]
        tables[("sleeper", p)] = (pp["actual_pts"] - pp["sleeper_pts_half_ppr"]).to_numpy()
        up = unproj[unproj.position == p]
        tables[("adp_implied", p)] = (up["actual_pts"] - up["adp_implied"]).to_numpy()
    tables[("adp_implied", "ALL")] = (unproj["actual_pts"] - unproj["adp_implied"]).to_numpy()
    return tables


def cell_quantiles(res, est):
    """Band quantiles per R1: Weibull convention; tiny pools get min/max tails + LOW."""
    if len(res) >= MIN_POOL:
        qs = {l: est + float(np.percentile(res, l, method=QMETHOD)) for l in LEVELS}
        conf = "NORMAL"
    else:
        qs = {l: est + float(np.percentile(res, l, method=QMETHOD)) for l in (25, 50, 75)}
        qs[10], qs[90] = est + float(res.min()), est + float(res.max())
        conf = "LOW"
    return qs, conf


def score_rows(rows, curves, tables, T):
    out = []
    for r in rows.itertuples():
        implied = float(curves[r.position].predict([r.adp_pos_rank])[0])
        if pd.notna(r.sleeper_pts_half_ppr):
            est, src, unproj = float(r.sleeper_pts_half_ppr), "sleeper", False
            res = tables[("sleeper", r.position)]
        else:
            est, src, unproj = implied, "adp_implied", True
            res = tables[("adp_implied", r.position)]
            if len(res) == 0:
                res = tables[("adp_implied", "ALL")]
        qs, conf = cell_quantiles(res, est)
        assert qs[10] <= qs[25] <= qs[50] <= qs[75] <= qs[90], f"crossing at {r.Index}"
        row = {"season": r.season, "position": r.position,
               "adp_pos_rank": int(r.adp_pos_rank), "estimate": round(est, 1),
               "estimate_source": src, "is_unprojected": unproj,
               "band_confidence": conf,
               **{f"p{l}": round(qs[l], 1) for l in LEVELS}}
        for n in TOP_N:
            row[f"p_top{n}"] = round(float((est + res >= T[(r.position, n)]).mean()), 3)
        if r.adp_pos_rank <= BUST_DRAFT[r.position]:
            tb = T[(r.position, BUST_FINISH[r.position])]
            row["p_bust"] = round(float((est + res < tb).mean()), 3)
        else:
            row["p_bust"] = None
        out.append(row)
    return pd.DataFrame(out, index=rows.index)


def pinball(actual, q, level):
    tau = level / 100
    d = actual - q
    return np.mean(np.maximum(tau * d, (tau - 1) * d))


def validate():
    df, pool = load_panel()
    finish = pb.finish_ranks(df)
    cov = {(p, lo, hi): [] for p in POS4 for lo, hi in [(10, 90), (25, 75)]}
    cov_src = {s: {(10, 90): [], (25, 75): []} for s in ["sleeper", "adp_implied"]}
    pin_model, pin_base = {l: [] for l in LEVELS}, {l: [] for l in LEVELS}
    reliab, conf_counts = [], {"NORMAL": 0, "LOW": 0}
    for t in PANEL:
        tr, te = pool[pool.season != t], pool[pool.season == t]
        curves = fit_adp_curves(tr)
        T = finish_thresholds(df, [s for s in PANEL if s != t])
        tables = build_tables(tr, curves)
        scored = score_rows(te, curves, tables, T)
        scored["actual"] = te["actual_pts"].values
        scored["finish"] = finish.loc[te.index].values
        for r in scored.itertuples():
            conf_counts[r.band_confidence] += 1
            for lo, hi in [(10, 90), (25, 75)]:
                inside = getattr(r, f"p{lo}") <= r.actual <= getattr(r, f"p{hi}")
                cov[(r.position, lo, hi)].append(inside)
                cov_src[r.estimate_source][(lo, hi)].append(inside)
            reliab.append((r.p_top12, r.finish <= 12, r.position, r.season))
        # v1 baseline UNCHANGED for comparability: position-level LINEAR quantiles of
        # sleeper residuals applied to every row
        base_tab = {p: tr[(tr.position == p) & tr.sleeper_pts_half_ppr.notna()]
                    .eval("actual_pts - sleeper_pts_half_ppr").to_numpy() for p in POS4}
        for l in LEVELS:
            pin_model[l].append(pinball(scored["actual"].to_numpy(),
                                        scored[f"p{l}"].to_numpy(), l))
            bq = np.array([scored.loc[i, "estimate"] +
                           np.percentile(base_tab[scored.loc[i, "position"]], l)
                           for i in scored.index])
            pin_base[l].append(pinball(scored["actual"].to_numpy(), bq, l))

    print("=== v2 LOSO coverage (nominal 80% = P10-P90, 50% = P25-P75), pooled folds ===")
    print(f"{'pos':4} {'80% cov':>8} {'n':>5} {'50% cov':>8}")
    for p in POS4:
        c80, c50 = cov[(p, 10, 90)], cov[(p, 25, 75)]
        print(f"{p:4} {np.mean(c80):>8.1%} {len(c80):>5} {np.mean(c50):>8.1%}")
    a80 = [x for p in POS4 for x in cov[(p, 10, 90)]]
    a50 = [x for p in POS4 for x in cov[(p, 25, 75)]]
    print(f"ALL  {np.mean(a80):>8.1%} {len(a80):>5} {np.mean(a50):>8.1%}")
    print("\nby estimate_source (80% / 50%):")
    for s, d in cov_src.items():
        if len(d[(10, 90)]):
            print(f"  {s:12} {np.mean(d[(10,90)]):.1%} / {np.mean(d[(25,75)]):.1%} "
                  f"(n={len(d[(10,90)])})")
    print(f"band_confidence counts: {conf_counts}")
    print("\npinball loss (mean over folds), v2 model vs v1 constant-width baseline:")
    for l in LEVELS:
        m, b = np.mean(pin_model[l]), np.mean(pin_base[l])
        print(f"  P{l:2}: model {m:6.2f}  baseline {b:6.2f}  ({(b-m)/b:+.1%})")
    print("\nP(top-12) reliability (deciles, pooled folds; high-decile wobble documented, left):")
    rel = pd.DataFrame(reliab, columns=["p", "hit", "position", "season"])
    rel["dec"] = pd.cut(rel.p, np.arange(0, 1.05, .1), include_lowest=True)
    tab = rel.groupby("dec", observed=True).agg(pred=("p", "mean"),
                                                real=("hit", "mean"), n=("p", "size"))
    print(tab.round(3).to_string())
    VAL_JSON.write_text(json.dumps({
        "version": "v2 (position-level pools, weibull quantiles, unprojected flag)",
        "coverage_80": {p: float(np.mean(cov[(p, 10, 90)])) for p in POS4},
        "coverage_50": {p: float(np.mean(cov[(p, 25, 75)])) for p in POS4},
        "coverage_by_source": {s: {f"{lo}_{hi}": float(np.mean(v)) for (lo, hi), v
                                   in d.items() if len(v)} for s, d in cov_src.items()},
        "pinball_model": {l: float(np.mean(v)) for l, v in pin_model.items()},
        "pinball_baseline_v1": {l: float(np.mean(v)) for l, v in pin_base.items()},
        "reliability": tab.reset_index().astype(str).to_dict("records"),
        "known_wobble": "P(top-12) high-decile overconfidence left as documented (n=10 cells)"},
        indent=2))
    print(f"wrote {VAL_JSON.name}")


def artifact():
    df, pool = load_panel()
    curves = fit_adp_curves(pool)
    T = finish_thresholds(df, PANEL)
    tables = build_tables(pool, curves)
    adp = pd.read_csv(ADP_CSV)
    p26 = adp[(adp.season == 2026) & adp.adp_half_ppr.notna()
              & adp.position.isin(POS4)].copy()
    p26["adp_overall"] = p26["adp_half_ppr"].rank(method="first")
    p26 = p26[p26.adp_overall <= pb.POOL_SIZE]
    p26["adp_pos_rank"] = p26.groupby("position")["adp_half_ppr"].rank(method="first")
    p26["season"] = 2026
    scored = score_rows(p26, curves, tables, T)
    scored.insert(1, "player", p26["player"].values)
    scored["powered_by"] = LICENSE_POINT
    scored["signal_status"] = LICENSE_SIGNAL
    assert scored["powered_by"].notna().all() and scored["signal_status"].notna().all()
    scored = scored.sort_values(["position", "adp_pos_rank"])
    scored.to_csv(ART_CSV, index=False)
    print(f"wrote {ART_CSV.name} ({len(scored)} rows; sources: "
          f"{scored.estimate_source.value_counts().to_dict()}; "
          f"confidence: {scored.band_confidence.value_counts().to_dict()})")
    print(scored.groupby("position").head(2)[
        ["player", "position", "adp_pos_rank", "estimate", "estimate_source",
         "band_confidence", "p10", "p50", "p90", "p_top12", "p_bust"]].to_string(index=False))


if __name__ == "__main__":
    if "--artifact" in sys.argv:
        artifact()
    else:
        validate()
