"""Research-only: NESTED walk-forward CV for the spread XGBoost, to size how much
the headline ~56.9% CV win-rate is inflated by hyperparameter/feature selection.

The production sweep (tune_hyperparams.py) scores each config across ALL six folds
(2020-2025) and reports the best -- so the chosen config has "seen" every test fold.
That's optimistic (select-then-report on the same folds). This script instead does a
proper nested loop: for each outer test year N, it tunes the SAME xgb grid using only
seasons < N (inner walk-forward on the last 3 prior seasons), picks the best inner
config, retrains on all of < N, and scores N. The mean of those outer-fold ATS is a
leak-free estimate; the gap vs the optimistic number is the selection bias.

This changes NOTHING in production -- the models are frozen and the real arbiter is
forward live tracking. It only puts an honest band on the backtest figure.

Run:  python betting/experiments/nested_cv_xgb.py
"""
import json, sys, time, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import xgboost as xgb

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

# ── 1. Reuse model_comparison data prep (cells 1-37) -> g, avail, ats_acc ────
print("Loading data prep from model_comparison.ipynb (cells 1-37)...")
t0 = time.time()
with open(ROOT / 'betting/model_comparison.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)
ns = {'__name__': '__main__'}
for i in range(1, 38):
    cell = nb['cells'][i]
    if cell['cell_type'] != 'code':
        continue
    src = ''.join(cell['source'])
    # skip PURE test cells (assert-only), but never a cell that imports or defines
    # something we need (Section 2's imports cell carries a smoke assert too).
    is_pure_test = ('assert' in src and ('passed' in src or 'tests' in src.lower())
                    and 'import ' not in src and 'def ' not in src)
    if is_pure_test:
        continue
    try:
        exec(src, ns)
    except Exception as e:
        if 'EXPECTED' in src or 'assert' in src:
            continue
        raise
g, avail, ats_acc = ns['g'], ns['avail'], ns['ats_acc']
print(f"  prep done in {time.time()-t0:.1f}s — g={g.shape}, {len(avail)} features")

OUTER = [2020, 2021, 2022, 2023, 2024, 2025]

# Same XGB grid as the production sweep (tune_hyperparams.py)
xgb_base = dict(n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
                subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0, reg_lambda=3.0)
GRID = [
    ("baseline (d3, reg1/3)", xgb_base),
    ("deeper (d5)", {**xgb_base, "max_depth": 5}),
    ("shallower (d2)", {**xgb_base, "max_depth": 2}),
    ("more reg (a2,l5) [PROD]", {**xgb_base, "reg_alpha": 2.0, "reg_lambda": 5.0}),
    ("less reg (a0.5,l1)", {**xgb_base, "reg_alpha": 0.5, "reg_lambda": 1.0}),
    ("more sampling (0.8/0.8)", {**xgb_base, "subsample": 0.8, "colsample_bytree": 0.8}),
]
PROD = "more reg (a2,l5) [PROD]"


def make_fold(train_years, test_year):
    """X/y/spread for (train_years -> test_year), with the league-rolling-avg
    feature recomputed on TRAIN ONLY (matches tune_hyperparams; avoids leakage)."""
    tr_m = g["season"].isin(train_years)
    te_m = g["season"] == test_year
    wk = g.loc[tr_m].groupby("week")["home_margin"].apply(lambda x: x.abs().mean())
    gf = g.copy()
    if "league_rolling_avg_abs_margin_by_week" in gf.columns:
        gf["league_rolling_avg_abs_margin_by_week"] = gf["week"].map(wk).fillna(wk.mean())
    return {
        "X_tr": gf.loc[tr_m, avail].fillna(0).values.astype("float32"),
        "y_tr": gf.loc[tr_m, "home_margin"].values.astype("float32"),
        "X_te": gf.loc[te_m, avail].fillna(0).values.astype("float32"),
        "y_te": gf.loc[te_m, "home_margin"].values.astype("float32"),
        "sp":   gf.loc[te_m, "spread_line"].fillna(0).values,
        "n":    int(te_m.sum()),
    }


def fit_ats(params, fd):
    m = xgb.XGBRegressor(objective="reg:squarederror", random_state=42, n_jobs=-1, **params)
    m.fit(fd["X_tr"], fd["y_tr"])
    return ats_acc(m.predict(fd["X_te"]), fd["sp"], fd["y_te"])


def inner_pick(pool_years):
    """Tune the grid on seasons < N only: inner walk-forward over the last 3 prior
    seasons, pick the config with the best mean inner ATS."""
    inner_tests = pool_years[-3:]
    best, best_s = None, -1.0
    for name, params in GRID:
        accs = []
        for iy in inner_tests:
            itr = [y for y in pool_years if y < iy]
            if len(itr) < 3:
                continue
            accs.append(fit_ats(params, make_fold(itr, iy)))
        if accs and np.mean(accs) > best_s:
            best, best_s = (name, params), float(np.mean(accs))
    return best, best_s


def main():
    # ── non-nested references (the optimistic, select-then-report numbers) ──
    pooled = {}
    for name, params in GRID:
        accs = [fit_ats(params, make_fold(list(range(2014, N)), N)) for N in OUTER]
        pooled[name] = (float(np.mean(accs)), float(np.std(accs)))
    opt_name, (opt_mean, opt_std) = max(pooled.items(), key=lambda kv: kv[1][0])
    prod_mean, prod_std = pooled[PROD]

    print("\nNon-nested (each config scored across ALL 6 folds, then we pick the best):")
    for name in sorted(pooled, key=lambda n: -pooled[n][0]):
        m, s = pooled[name]
        tag = "  <- optimistic 'reported' (best on pooled)" if name == opt_name else ""
        print(f"  {name:<26} {m:.1%} ± {s:.1%}{tag}")

    # ── nested: tune on < N, score N ──
    print("\nNested walk-forward (tune on seasons < N only, then score N):")
    nested, picks = [], []
    for N in OUTER:
        pool = list(range(2014, N))
        (pname, pparams), inner_s = inner_pick(pool)
        acc = fit_ats(pparams, make_fold(pool, N))
        nested.append(acc); picks.append(pname)
        print(f"  {N}: inner-pick = {pname:<26} (inner {inner_s:.1%})  ->  {N} ATS = {acc:.1%}")
    nmean, nstd = float(np.mean(nested)), float(np.std(nested))

    print("\n" + "=" * 64)
    print(f"  optimistic (best config on pooled folds): {opt_mean:.1%} ± {opt_std:.1%}   [{opt_name}]")
    print(f"  production config across folds:           {prod_mean:.1%} ± {prod_std:.1%}")
    print(f"  NESTED (leak-free):                       {nmean:.1%} ± {nstd:.1%}")
    print(f"  selection optimism (optimistic - nested): {(opt_mean - nmean)*100:+.1f} pp")
    print(f"  break-even: 52.4%")
    print("=" * 64)

    out = {"outer_years": OUTER, "pooled": pooled, "optimistic_best": opt_name,
           "optimistic_mean": opt_mean, "production_mean": prod_mean,
           "nested_mean": nmean, "nested_std": nstd, "nested_per_fold": nested,
           "nested_picks": picks, "optimism_pp": (opt_mean - nmean) * 100}
    (HERE / "nested_cv_xgb_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nsaved nested_cv_xgb_results.json")


if __name__ == "__main__":
    main()
