"""Walk-forward OUT-OF-SAMPLE spread predictions, for an honest multi-season CLV backtest.

The cached pkls are trained through 2024, so predicting 2014-2024 with them is
in-sample (leakage). This rebuilds the production ensemble (0.75 XGBoost + 0.25
Ridge) and the three direction voters (XGB / Ridge / LGBM) fresh for each test
season Y, trained only on seasons < Y. Emits one row per game with the ensemble
predicted_margin + the three voter margins, so clv_backtest can derive the pick
at the opening line and measure CLV across many seasons.

Mirrors feature_ablation.py's data prep (exec model_comparison.ipynb cells 1-37)
and the production hyperparameters (Ridge a=50, XGB alpha=2/lambda=5).

    python betting/experiments/walkforward_oos_preds.py
    -> betting/experiments/walkforward_oos_preds.csv
"""
import json
import sys
import time
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")

import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "betting"))

import argparse
_ap = argparse.ArgumentParser(description="Walk-forward OOS spread predictions")
_ap.add_argument("--line", choices=["close", "open"], default="close",
                 help="line feature: 'close' = nflverse spread_line (default; confounds CLV); "
                      "'open' = substitute the aussportsbetting opening line (honest pick-time eval)")
LINE = _ap.parse_args().line

TEST_SEASONS = list(range(2018, 2026))  # train on >=2014; 4+ train seasons each

# ── 1. data prep (same as feature_ablation) ──────────────────────────────────
print("Loading data prep from model_comparison.ipynb (cells 1-37)...")
t0 = time.time()
with open(ROOT / "betting/model_comparison.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)
ns = {"__name__": "__main__"}
for i in range(1, 38):
    cell = nb["cells"][i]
    if cell["cell_type"] != "code":
        continue
    src = "".join(cell["source"])
    if "assert" in src and ("passed" in src or "tests" in src.lower()):
        continue
    try:
        exec(src, ns)
    except Exception:
        if "EXPECTED" in src or "assert" in src:
            continue
        raise
g = ns["g"]
print(f"  prep done in {time.time()-t0:.1f}s — g.shape={g.shape}")

# production feature set (top 35); fall back to avail if not present
import features as _features  # noqa
FEATURES = list(_features.PROD_FEATURES_35)
print(f"  using {len(FEATURES)} production features")

# identifiers needed to join historical lines (date + teams). Merge from schedule if absent.
need = ["game_id", "home_team", "away_team", "gameday"]
missing = [c for c in need if c not in g.columns]
if missing:
    import nflreadpy as nfl
    sched = nfl.load_schedules(list(range(2014, 2026))).to_pandas()
    keep = [c for c in ["game_id", "home_team", "away_team", "gameday"] if c in sched.columns]
    g = g.merge(sched[keep], on="game_id", how="left", suffixes=("", "_s"))
    for c in missing:
        if c not in g.columns and f"{c}_s" in g.columns:
            g[c] = g[f"{c}_s"]
print(f"  identifier cols present: {[c for c in need if c in g.columns]}")

# De-confound: replace the closing-line `spread_line` feature with the OPENING line
# (the line available at pick time, like production). spread_line is the ONLY
# line-derived feature in PROD_FEATURES_35, so this fully removes closing-line info.
if LINE == "open":
    import historical_lines as hl
    FRANCHISE_NORM = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
    g["gameday"] = pd.to_datetime(g["gameday"])
    g["_h"] = g["home_team"].replace(FRANCHISE_NORM)
    g["_a"] = g["away_team"].replace(FRANCHISE_NORM)
    op = hl.load_lines()[["date", "home", "away", "spread_open"]]
    g = g.merge(op, left_on=["gameday", "_h", "_a"], right_on=["date", "home", "away"], how="left")
    before = len(g)
    g = g.dropna(subset=["spread_open"]).copy()
    g["spread_line"] = g["spread_open"]  # substitute pick-time line
    print(f"  --line open: substituted opening line; kept {len(g)}/{before} games with an open line")


# ── 2. models (production hyperparameters) ───────────────────────────────────
def fit_xgb(Xtr, ytr):
    m = xgb.XGBRegressor(n_estimators=500, max_depth=3, learning_rate=0.01,
                         min_child_weight=3, subsample=0.6, colsample_bytree=0.6,
                         reg_alpha=2.0, reg_lambda=5.0, objective="reg:squarederror",
                         random_state=42, n_jobs=-1)
    m.fit(Xtr, ytr)
    return m


def fit_ridge(Xtr, ytr):
    sc = StandardScaler()
    m = Ridge(alpha=50.0).fit(sc.fit_transform(Xtr), ytr)
    return m, sc


def fit_lgbm(Xtr, ytr):
    cut = int(len(Xtr) * 0.85)
    tr = lgb.Dataset(Xtr[:cut], label=ytr[:cut])
    val = lgb.Dataset(Xtr[cut:], label=ytr[cut:], reference=tr)
    params = dict(objective="regression", metric="rmse", learning_rate=0.01,
                  num_leaves=15, max_depth=4, min_data_in_leaf=20, feature_fraction=0.6,
                  bagging_fraction=0.6, bagging_freq=5, reg_alpha=1.0, reg_lambda=3.0,
                  verbose=-1, n_jobs=-1, seed=42, feature_fraction_seed=42, bagging_seed=42)
    return lgb.train(params, tr, num_boost_round=500, valid_sets=[val],
                     callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])


# ── 3. walk-forward ──────────────────────────────────────────────────────────
ID_COLS = [c for c in ["game_id", "season", "week", "home_team", "away_team",
                       "gameday", "spread_line"] if c in g.columns]
rows = []
for Y in TEST_SEASONS:
    tr_m = (g["season"] >= 2014) & (g["season"] < Y)
    te_m = g["season"] == Y
    if te_m.sum() == 0 or tr_m.sum() == 0:
        continue
    # per-fold, leak-safe recompute of the league-rolling-margin feature (train-only)
    gf = g.copy()
    if "league_rolling_avg_abs_margin_by_week" in FEATURES:
        wk = g.loc[tr_m].groupby("week")["home_margin"].apply(lambda x: x.abs().mean())
        gf["league_rolling_avg_abs_margin_by_week"] = gf["week"].map(wk).fillna(wk.mean())
    Xtr = gf.loc[tr_m, FEATURES].fillna(0).values.astype("float32")
    ytr = gf.loc[tr_m, "home_margin"].values.astype("float32")
    Xte = gf.loc[te_m, FEATURES].fillna(0).values.astype("float32")

    xgb_m = fit_xgb(Xtr, ytr)
    ridge_m, sc = fit_ridge(Xtr, ytr)
    lgbm_m = fit_lgbm(Xtr, ytr)
    xgb_p = xgb_m.predict(Xte)
    ridge_p = ridge_m.predict(sc.transform(Xte))
    lgbm_p = lgbm_m.predict(Xte)
    ens_p = 0.75 * xgb_p + 0.25 * ridge_p

    out = gf.loc[te_m, ID_COLS].copy()
    out["predicted_margin"] = ens_p
    out["xgb_margin"] = xgb_p
    out["ridge_margin"] = ridge_p
    out["lgbm_margin"] = lgbm_p
    rows.append(out)
    print(f"  season {Y}: train {int(tr_m.sum())} / predict {int(te_m.sum())} games")

preds = pd.concat(rows, ignore_index=True)
dest = HERE / (f"walkforward_oos_preds_openline.csv" if LINE == "open"
               else "walkforward_oos_preds.csv")
preds.to_csv(dest, index=False)
print(f"\nwrote {len(preds)} out-of-sample predictions ({preds['season'].min()}-"
      f"{preds['season'].max()}) -> {dest}")
