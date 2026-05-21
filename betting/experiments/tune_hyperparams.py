"""Manual hyperparameter sweep across the 5 models with walk-forward CV.

Reuses the data prep from betting/model_comparison.ipynb (cells 1-37).
Scores each config by Mean ATS - 1*Std (risk-adjusted), prints sorted leaderboard.
"""
import json, sys, time, warnings
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent  # project root
HERE = Path(__file__).resolve().parent               # betting/experiments/

# ── 1. Load notebook & run prep cells (1 through 37) in shared namespace ─────
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
    if 'assert' in src and ('passed' in src or 'tests' in src.lower()):
        # Skip inline test cells — they assert but don't define new things we need
        continue
    try:
        exec(src, ns)
    except Exception as e:
        print(f"  Cell {i} error: {type(e).__name__}: {e}")
        if 'EXPECTED' in src or 'assert' in src:
            continue  # tolerate test asserts
        raise

print(f"  Prep done in {time.time()-t0:.1f}s — g.shape={ns['g'].shape}, avail={len(ns['avail'])} features")

# Pull what we need into module scope
g           = ns['g']
avail       = ns['avail']
ats_acc     = ns['ats_acc']
TRAIN_SEASONS = ns['TRAIN_SEASONS']
TEST_SEASONS  = ns['TEST_SEASONS']

# ── 2. CV folds (same as Section 20) ────────────────────────────────────────
CV_FOLDS = [
    {"train": list(range(2014, 2020)), "test": [2020]},
    {"train": list(range(2014, 2021)), "test": [2021]},
    {"train": list(range(2014, 2022)), "test": [2022]},
    {"train": list(range(2014, 2023)), "test": [2023]},
    {"train": list(range(2014, 2024)), "test": [2024]},
    {"train": list(range(2014, 2025)), "test": [2025]},
]

# Pre-compute fold data once
fold_data = []
for fold in CV_FOLDS:
    test_yr = fold["test"][0]
    tr_m = g["season"].isin(fold["train"])
    te_m = g["season"].isin(fold["test"])

    _fold_wk_lkp = (
        g.loc[tr_m].groupby("week")["home_margin"]
        .apply(lambda x: x.abs().mean())
    )
    g_fold = g.copy()
    g_fold["league_rolling_avg_abs_margin_by_week"] = (
        g_fold["week"].map(_fold_wk_lkp).fillna(_fold_wk_lkp.mean())
    )
    X_tr = g_fold.loc[tr_m, avail].fillna(0).values.astype("float32")
    y_tr = g_fold.loc[tr_m, "home_margin"].values.astype("float32")
    X_te = g_fold.loc[te_m, avail].fillna(0).values.astype("float32")
    y_te = g_fold.loc[te_m, "home_margin"].values.astype("float32")
    sp   = g_fold.loc[te_m, "spread_line"].fillna(0).values
    fold_data.append({"yr": test_yr, "X_tr": X_tr, "y_tr": y_tr, "X_te": X_te, "y_te": y_te, "sp": sp})

print(f"  CV folds prepared: {len(fold_data)} folds")

# ── 3. Trainer functions ────────────────────────────────────────────────────
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

device = "cuda" if torch.cuda.is_available() else "cpu"

class BettingMLP(nn.Module):
    def __init__(self, n_in, hidden=(256, 128, 64), dropout=(0.3, 0.2, 0.1)):
        super().__init__()
        layers = []
        prev = n_in
        for h, d in zip(hidden, dropout):
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(d)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)
    def forward(self, x): return self.net(x).squeeze(1)


def run_xgb(params, fd):
    m = xgb.XGBRegressor(objective="reg:squarederror", random_state=42, n_jobs=-1, **params)
    m.fit(fd["X_tr"], fd["y_tr"])
    return m.predict(fd["X_te"])


def run_rf(params, fd):
    m = RandomForestRegressor(random_state=42, n_jobs=-1, **params)
    m.fit(fd["X_tr"], fd["y_tr"])
    return m.predict(fd["X_te"])


def run_ridge(params, fd):
    sc = StandardScaler()
    Xtr = sc.fit_transform(fd["X_tr"])
    Xte = sc.transform(fd["X_te"])
    m = Ridge(**params)
    m.fit(Xtr, fd["y_tr"])
    return m.predict(Xte)


def run_lgbm(params, fd):
    # Use chronological 15% holdout within fold's training data for early stopping
    cut = int(len(fd["X_tr"]) * 0.85)
    lgb_tr  = lgb.Dataset(fd["X_tr"][:cut], label=fd["y_tr"][:cut])
    lgb_val = lgb.Dataset(fd["X_tr"][cut:], label=fd["y_tr"][cut:], reference=lgb_tr)
    base = dict(objective="regression", metric="rmse", verbose=-1, n_jobs=-1,
                seed=42, feature_fraction_seed=42, bagging_seed=42)
    base.update(params)
    n_rounds = base.pop("num_boost_round", 500)
    m = lgb.train(base, lgb_tr, num_boost_round=n_rounds, valid_sets=[lgb_val],
                  callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    return m.predict(fd["X_te"])


def run_mlp(params, fd):
    hidden  = params.get("hidden", (256, 128, 64))
    dropout = params.get("dropout", (0.3, 0.2, 0.1))
    lr      = params.get("lr", 3e-4)
    wd      = params.get("wd", 1e-4)
    epochs  = params.get("epochs", 150)
    bsz     = params.get("batch_size", 64)
    delta   = params.get("huber_delta", 7.0)

    sc = StandardScaler().fit(fd["X_tr"])
    Xtr = torch.tensor(sc.transform(fd["X_tr"]), dtype=torch.float32)
    Xte = torch.tensor(sc.transform(fd["X_te"]), dtype=torch.float32)
    ytr = torch.tensor(fd["y_tr"], dtype=torch.float32)

    net = BettingMLP(fd["X_tr"].shape[1], hidden=hidden, dropout=dropout).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.HuberLoss(delta=delta)
    dl = DataLoader(TensorDataset(Xtr, ytr), batch_size=bsz, shuffle=True)
    for _ in range(epochs):
        net.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(); loss_fn(net(xb), yb).backward(); opt.step()
        sch.step()
    net.eval()
    with torch.no_grad():
        return net(Xte.to(device)).cpu().numpy()


def cv_eval(name, run_fn, params):
    accs, maes = [], []
    for fd in fold_data:
        preds = run_fn(params, fd)
        accs.append(ats_acc(preds, fd["sp"], fd["y_te"]))
        maes.append(float(np.abs(preds - fd["y_te"]).mean()))
    accs, maes = np.array(accs), np.array(maes)
    return {"name": name, "mean_ats": accs.mean(), "std_ats": accs.std(),
            "min_ats": accs.min(), "max_ats": accs.max(),
            "mean_mae": maes.mean(), "score": accs.mean() - accs.std()}


# ── 4. Hyperparameter grids ─────────────────────────────────────────────────
xgb_base = dict(n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
                subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0, reg_lambda=3.0)

xgb_grid = [
    ("XGB baseline (depth=3, reg=1/3)", xgb_base),
    ("XGB deeper (depth=5)", {**xgb_base, "max_depth": 5}),
    ("XGB shallower (depth=2)", {**xgb_base, "max_depth": 2}),
    ("XGB more reg (alpha=2, lambda=5)", {**xgb_base, "reg_alpha": 2.0, "reg_lambda": 5.0}),
    ("XGB less reg (alpha=0.5, lambda=1)", {**xgb_base, "reg_alpha": 0.5, "reg_lambda": 1.0}),
    ("XGB more sampling (0.8/0.8)", {**xgb_base, "subsample": 0.8, "colsample_bytree": 0.8}),
]

rf_grid = [
    ("RF baseline (n=500, leaf=5, sqrt)", dict(n_estimators=500, max_features="sqrt", min_samples_leaf=5)),
    ("RF more trees (n=1000)", dict(n_estimators=1000, max_features="sqrt", min_samples_leaf=5)),
    ("RF larger leaves (leaf=10)", dict(n_estimators=500, max_features="sqrt", min_samples_leaf=10)),
    ("RF smaller leaves (leaf=2)", dict(n_estimators=500, max_features="sqrt", min_samples_leaf=2)),
    ("RF max_features=0.3", dict(n_estimators=500, max_features=0.3, min_samples_leaf=5)),
    ("RF depth-capped (max_depth=10)", dict(n_estimators=500, max_features="sqrt", min_samples_leaf=5, max_depth=10)),
]

ridge_grid = [
    ("Ridge alpha=0.1",  {"alpha": 0.1}),
    ("Ridge alpha=1.0",  {"alpha": 1.0}),
    ("Ridge alpha=5.0",  {"alpha": 5.0}),
    ("Ridge alpha=10.0 (baseline)",  {"alpha": 10.0}),
    ("Ridge alpha=50.0", {"alpha": 50.0}),
    ("Ridge alpha=100.0", {"alpha": 100.0}),
]

lgbm_base = dict(learning_rate=0.01, num_leaves=15, max_depth=4, min_data_in_leaf=20,
                 feature_fraction=0.6, bagging_fraction=0.6, bagging_freq=5,
                 reg_alpha=1.0, reg_lambda=3.0, num_boost_round=500)

lgbm_grid = [
    ("LGB baseline (leaves=15, d=4)", lgbm_base),
    ("LGB more leaves (leaves=31, d=5)", {**lgbm_base, "num_leaves": 31, "max_depth": 5}),
    ("LGB fewer leaves (leaves=7, d=3)", {**lgbm_base, "num_leaves": 7, "max_depth": 3}),
    ("LGB more reg (alpha=2, lambda=5)", {**lgbm_base, "reg_alpha": 2.0, "reg_lambda": 5.0}),
    ("LGB larger min_data (50)", {**lgbm_base, "min_data_in_leaf": 50}),
    ("LGB higher lr (0.02)", {**lgbm_base, "learning_rate": 0.02}),
]

mlp_grid = [
    ("MLP baseline (256/128/64, lr=3e-4, ep=150)", dict()),
    ("MLP bigger (512/256/128)", dict(hidden=(512, 256, 128))),
    ("MLP smaller (128/64/32)", dict(hidden=(128, 64, 32))),
    ("MLP more dropout (0.4/0.3/0.2)", dict(dropout=(0.4, 0.3, 0.2))),
    ("MLP lower lr (1e-4), longer (250)", dict(lr=1e-4, epochs=250)),
    ("MLP larger batch (128)", dict(batch_size=128)),
]

# ── 5. Run sweep ─────────────────────────────────────────────────────────────
all_results = []
sweeps = [
    ("XGBoost",      run_xgb,   xgb_grid),
    ("Ridge",        run_ridge, ridge_grid),
    ("Random Forest",run_rf,    rf_grid),
    ("LightGBM",     run_lgbm,  lgbm_grid),
    ("MLP",          run_mlp,   mlp_grid),
]

for model_name, run_fn, grid in sweeps:
    print(f"\n{'='*80}\n{model_name} ({len(grid)} configs × {len(fold_data)} folds)")
    print('='*80)
    for cfg_name, params in grid:
        t0 = time.time()
        try:
            r = cv_eval(cfg_name, run_fn, params)
        except Exception as e:
            print(f"  {cfg_name}: ERROR {type(e).__name__}: {e}")
            continue
        r["family"] = model_name
        all_results.append(r)
        print(f"  {cfg_name:<48} mean={r['mean_ats']:.1%} ± {r['std_ats']:.1%}  "
              f"(min={r['min_ats']:.1%} max={r['max_ats']:.1%})  "
              f"MAE={r['mean_mae']:.2f}  score={r['score']:.3f}  [{time.time()-t0:.1f}s]")

# ── 6. Leaderboard ───────────────────────────────────────────────────────────
print(f"\n{'='*80}\nFULL LEADERBOARD (sorted by Mean ATS - Std)\n{'='*80}")
all_results.sort(key=lambda r: r["score"], reverse=True)
print(f"{'#':<3}{'Config':<48}{'Family':<14}{'Score':>8}{'Mean':>8}{'Std':>7}{'MAE':>7}")
print('-'*95)
for i, r in enumerate(all_results, 1):
    print(f"{i:<3}{r['name']:<48}{r['family']:<14}{r['score']*100:>6.2f}  {r['mean_ats']*100:>6.2f}%  {r['std_ats']*100:>5.2f}%  {r['mean_mae']:>5.2f}")

print(f"\n{'='*80}\nBEST PER FAMILY\n{'='*80}")
seen = set()
for r in all_results:
    if r["family"] in seen: continue
    seen.add(r["family"])
    print(f"  {r['family']:<14} → {r['name']}")
    print(f"    {'':<14}   mean={r['mean_ats']:.1%}  std={r['std_ats']:.1%}  MAE={r['mean_mae']:.2f}  score={r['score']:.3f}")

# Save results to a JSON file for reference
with open(HERE / 'hyperparam_sweep_results.json', 'w') as f:
    json.dump([{**r, "mean_ats": float(r["mean_ats"]), "std_ats": float(r["std_ats"]),
                "min_ats": float(r["min_ats"]), "max_ats": float(r["max_ats"]),
                "mean_mae": float(r["mean_mae"]), "score": float(r["score"])} for r in all_results], f, indent=2)
print(f"\nResults saved to hyperparam_sweep_results.json ({len(all_results)} configs)")
