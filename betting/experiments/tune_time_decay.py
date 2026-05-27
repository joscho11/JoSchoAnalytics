"""Time-decay sample-weighting + extended-training-range sweep.

For each (train_start, α) cell, retrains all 5 models with
    sample_weight = exp(-α * (max_train_year - sample_year))
and compares mean ATS across the 6 walk-forward CV folds (2020 through 2025).

CLI:
  --alphas         comma-separated α values to sweep (default: 0,0.05,0.10,0.15,0.20)
  --train-starts   comma-separated TRAIN_SEASONS start years (default: 2014)
  --earliest YEAR  override the data-load lower bound (default = min of --train-starts).
                   When < 2014, extends ALL_SEASONS, reloads PBP/injuries/schedules,
                   and runs verify_coverage() to fail-fast on mechanical zero-fill.
  --out FILE       output JSON filename (placed in betting/experiments/)
  --label TEXT     free-text label written to the JSON

The verify_coverage() gate detects mechanical-zero-fill shifts: any feature whose
zero-rate jumps >25pp between the early extended-data window and the 2014+ window
fails the run. This catches silent coverage holes (e.g., pre-2009 injuries hard-floor
in nflreadpy, pre-2006 AllPro hardcoded floor in mc cell 15).

α = 0 reproduces the current production baseline (uniform weights).

Reuses data prep from betting/model_comparison.ipynb (cells 1-37), same pattern
as tune_hyperparams.py.

Experiments run May 2026 — all rejected (see CLAUDE.md Completed Work entry):
  Pass 1 (default):                       time-decay alone at TRAIN_SEASONS=2014+
  Pass 2 real (--earliest 2005):          extending range alone, partial coverage
  Pass 3 (--earliest 2005, full grid):    decay × range, partial coverage
  Pass 3 clean (--earliest 2008, full):   decay × range with verified-clean data

Outputs:
  <out>.json     full per-fold breakdown including alpha, train_start, fold ATS / MAE
  printed summary table (XGBoost mean ATS by train_start × α)
"""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent


def load_prep_cells(earliest=2014):
    """Run mc cells 1-37 in a shared namespace, optionally overriding
    ALL_SEASONS to extend the data load back to `earliest`.

    If `earliest` < 2014, after cell 2 runs we override `ALL_SEASONS` to
    list(range(earliest, 2026)) so that cell 8's PBP + schedule load and
    cell 36's injuries load cover the extended range. nfl.load_injuries
    is also monkey-patched to filter pre-2009 seasons (nflreadpy doesn't
    have injury data before 2009; without this patch the whole injury
    block would skip).

    Manual passer-rating fallback (cell 18, years < 2016) automatically
    extends to all years < 2016 in the new ALL_SEASONS — no extra work.
    NGS (cell 18, years >= 2016) is unchanged. AllPro CSV has 1997+.

    Returns the populated namespace dict.
    """
    print(f"Loading data prep from model_comparison.ipynb (cells 1-37) [earliest={earliest}]...")
    t0 = time.time()

    with open(ROOT / 'betting/model_comparison.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)

    ns = {'__name__': '__main__'}
    for i in range(1, 38):
        cell = nb['cells'][i]
        if cell['cell_type'] != 'code':
            continue
        src = ''.join(cell['source'])
        first_line = next((ln for ln in src.split('\n') if ln.strip()), '')
        is_test_cell = first_line.lstrip().startswith('# ── Section') and 'tests' in first_line.lower()
        if is_test_cell:
            continue

        # Source-string patch: mc cell 15's `build_weighted` hardcodes
        # `range(2006, max(ALL_SEASONS)+2)` as the AllPro-year floor.
        # For ALL_SEASONS starting < 2006, this leaves those early years
        # with 100% zero AllPro features. Patch the literal so the range
        # tracks the actual ALL_SEASONS lower bound. This is a no-op for
        # production runs (ALL_SEASONS=2014-2025, min > 2006).
        if i == 15 and earliest < 2006:
            old = 'for yr in range(2006, max(ALL_SEASONS)+2):'
            new = 'for yr in range(min(ALL_SEASONS), max(ALL_SEASONS)+2):'
            if old in src:
                src = src.replace(old, new)
                print(f"  [patched] cell 15: AllPro range floor 2006 → min(ALL_SEASONS)")
            else:
                raise RuntimeError("cell 15 patch target not found — has the AllPro builder been refactored?")

        try:
            exec(src, ns)
        except Exception as e:
            print(f"  Cell {i} error: {type(e).__name__}: {e}")
            raise

        # After cell 2 (which defines ALL_SEASONS), inject our override
        # before the data-loading cells run.
        if i == 2 and earliest < 2014:
            new_all = list(range(earliest, 2026))
            ns['ALL_SEASONS'] = new_all
            print(f"  Overrode ALL_SEASONS → {earliest}-2025 ({len(new_all)} seasons)")

        # After cell 5 (imports), monkey-patch nfl.load_injuries.
        # nflreadpy injury reports are sparse pre-2009; the patch tries the
        # full requested range, and on failure progressively drops the
        # earliest year until the load succeeds.
        if i == 5 and earliest < 2014:
            nfl_mod = ns.get('nfl')
            if nfl_mod is not None:
                _orig_load_injuries = nfl_mod.load_injuries
                def _safe_load_injuries(seasons):
                    s_list = sorted(seasons)
                    # First-pass: drop anything before 2009 (known lower bound).
                    s_list = [y for y in s_list if y >= 2009]
                    while s_list:
                        try:
                            print(f"  [patched] load_injuries: trying {min(s_list)}-{max(s_list)} ({len(s_list)} seasons)")
                            return _orig_load_injuries(seasons=s_list)
                        except Exception as ex:
                            print(f"    failed ({ex}); dropping earliest year {min(s_list)}")
                            s_list = s_list[1:]
                    raise RuntimeError("load_injuries: no year worked")
                nfl_mod.load_injuries = _safe_load_injuries

    print(f"  Prep done in {time.time()-t0:.1f}s — g.shape={ns['g'].shape}, avail={len(ns['avail'])} features")
    if earliest < 2014:
        g = ns['g']
        seasons_in_g = sorted(g['season'].unique())
        print(f"  Seasons in g: {min(seasons_in_g)}-{max(seasons_in_g)} ({len(seasons_in_g)} total)")
    return ns


def verify_coverage(ns, candidate_train_starts, max_zero_shift_pp=25.0,
                    baseline_anchor=2014, hard_fail=True):
    """Detect MECHANICAL coverage shifts: features whose zero-rate jumps
    dramatically in pre-baseline_anchor years vs the baseline_anchor+
    years. Structural features (like is_playoff = 96% zero always)
    are fine — only flag features where adding early years would
    introduce a near-constant zero block.

    For each candidate train_start (where ts < baseline_anchor):
      - For each feature in avail:
        - early_zero = zero-rate in [ts, baseline_anchor)
        - late_zero  = zero-rate in [baseline_anchor, 2025]
        - shift_pp = early_zero - late_zero (pp)
        - if shift_pp > max_zero_shift_pp → coverage issue

    A feature flagged means the extra training rows would be mechanically
    zero-filled rather than carrying real information. Reject this
    train_start unless hard_fail=False.
    """
    import pandas as pd
    g = ns['g']
    avail = ns['avail']
    print(f"\n{'='*78}")
    print(f"  COVERAGE VERIFICATION — detecting mechanical zero-fill shifts")
    print(f"  baseline_anchor={baseline_anchor} (zero-rate compared vs {baseline_anchor}+ data)")
    print(f"  max_zero_shift_pp={max_zero_shift_pp}pp — fail if early period inflates zeros by more")
    print('='*78)

    issues = []
    late_mask = g['season'].between(baseline_anchor, 2024)
    late_rows = g[late_mask]

    for ts in candidate_train_starts:
        if ts >= baseline_anchor:
            print(f"\n  train_start={ts}+ : at or after baseline anchor — no shift to check")
            continue

        early_mask = g['season'].between(ts, baseline_anchor - 1)
        early_rows = g[early_mask]
        if len(early_rows) == 0:
            issues.append((ts, 'EMPTY', 'No early-period rows for this train_start'))
            continue

        print(f"\n  train_start={ts}+ : checking early={ts}-{baseline_anchor-1} ({len(early_rows):,} rows) "
              f"vs late={baseline_anchor}-2024 ({len(late_rows):,} rows)")
        bad_features = []
        for col in avail:
            if col not in g.columns:
                bad_features.append((col, 'MISSING_COL'))
                continue
            early_zero = (early_rows[col].fillna(0) == 0).mean() * 100
            late_zero  = (late_rows[col].fillna(0)  == 0).mean() * 100
            shift_pp = early_zero - late_zero
            if shift_pp > max_zero_shift_pp:
                bad_features.append((col, f'early={early_zero:.0f}% late={late_zero:.0f}% (+{shift_pp:.0f}pp)'))

        if bad_features:
            print(f"    ⚠  {len(bad_features)} features have a mechanical-zero shift > {max_zero_shift_pp}pp:")
            for col, tag in bad_features:
                # Show per-year breakdown for this feature within the early window
                per_year = early_rows.groupby('season')[col].apply(lambda s: (s.fillna(0)==0).mean()*100)
                worst = per_year.nlargest(3)
                worst_str = ", ".join(f"{int(y)}={v:.0f}%" for y, v in worst.items())
                print(f"      {col:<48} {tag}  early-yrs: {worst_str}")
                issues.append((ts, col, tag))
        else:
            print(f"    ✓ All {len(avail)} features clean — no mechanical-zero shift > {max_zero_shift_pp}pp")

    print()
    if issues and hard_fail:
        raise AssertionError(
            f"Coverage check failed: {len(issues)} (train_start, feature) coverage shifts detected. "
            f"Adding early-period training rows would feed mechanical zeros into the model. "
            f"Pick a later train_start or fix the data-source coverage bug."
        )
    return issues


# ── CV folds + per-fold data (includes `tr_seasons` for decay weighting) ──
def make_cv_folds(train_start=2014):
    """Walk-forward CV: train on [train_start, test_year), test on [test_year]."""
    return [
        {"train": list(range(train_start, ty)), "test": [ty]}
        for ty in [2020, 2021, 2022, 2023, 2024, 2025]
    ]


def build_fold_data(folds, ns):
    g = ns['g']
    avail = ns['avail']
    out = []
    for fold in folds:
        tr_m = g["season"].isin(fold["train"])
        te_m = g["season"].isin(fold["test"])
        _wk = (g.loc[tr_m].groupby("week")["home_margin"]
                          .apply(lambda x: x.abs().mean()))
        g_fold = g.copy()
        g_fold["league_rolling_avg_abs_margin_by_week"] = (
            g_fold["week"].map(_wk).fillna(_wk.mean())
        )
        X_tr = g_fold.loc[tr_m, avail].fillna(0).values.astype("float32")
        y_tr = g_fold.loc[tr_m, "home_margin"].values.astype("float32")
        X_te = g_fold.loc[te_m, avail].fillna(0).values.astype("float32")
        y_te = g_fold.loc[te_m, "home_margin"].values.astype("float32")
        sp   = g_fold.loc[te_m, "spread_line"].fillna(0).values
        tr_seasons = g_fold.loc[tr_m, "season"].values.astype("int32")
        max_train_year = int(max(fold["train"]))
        out.append({"yr": fold["test"][0], "X_tr": X_tr, "y_tr": y_tr,
                    "X_te": X_te, "y_te": y_te, "sp": sp,
                    "tr_seasons": tr_seasons, "max_train_year": max_train_year,
                    "n_train": len(X_tr)})
    return out


def decay_weights(fd, alpha):
    if alpha <= 0:
        return None
    yrs_ago = fd["max_train_year"] - fd["tr_seasons"]
    return np.exp(-alpha * yrs_ago).astype("float32")


# ── 3. Trainers (production-tuned hyperparameters; accept sample_weight) ────
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

device = "cuda" if torch.cuda.is_available() else "cpu"

# Production hyperparameters (per CLAUDE.md 2026-05-20):
XGB_PARAMS = dict(n_estimators=500, max_depth=3, learning_rate=0.01,
                  min_child_weight=3, subsample=0.6, colsample_bytree=0.6,
                  reg_alpha=2.0, reg_lambda=5.0,
                  objective="reg:squarederror", random_state=42, n_jobs=-1)
RIDGE_ALPHA = 50.0
LGBM_PARAMS = dict(objective="regression", metric="rmse", learning_rate=0.01,
                   num_leaves=15, max_depth=4, min_data_in_leaf=20,
                   feature_fraction=0.6, bagging_fraction=0.6, bagging_freq=5,
                   reg_alpha=1.0, reg_lambda=3.0, verbose=-1, n_jobs=-1,
                   seed=42, feature_fraction_seed=42, bagging_seed=42)
RF_PARAMS = dict(n_estimators=500, max_features="sqrt", min_samples_leaf=5,
                 random_state=42, n_jobs=-1)
MLP_HIDDEN = (256, 128, 64)
MLP_DROPOUT = (0.3, 0.2, 0.1)
MLP_EPOCHS = 150


def run_xgb(fd, w):
    m = xgb.XGBRegressor(**XGB_PARAMS)
    m.fit(fd["X_tr"], fd["y_tr"], sample_weight=w)
    return m.predict(fd["X_te"])


def run_rf(fd, w):
    m = RandomForestRegressor(**RF_PARAMS)
    m.fit(fd["X_tr"], fd["y_tr"], sample_weight=w)
    return m.predict(fd["X_te"])


def run_ridge(fd, w):
    sc = StandardScaler()
    Xtr = sc.fit_transform(fd["X_tr"])
    Xte = sc.transform(fd["X_te"])
    m = Ridge(alpha=RIDGE_ALPHA)
    m.fit(Xtr, fd["y_tr"], sample_weight=w)
    return m.predict(Xte)


def run_lgbm(fd, w):
    cut = int(len(fd["X_tr"]) * 0.85)
    if w is None:
        lgb_tr  = lgb.Dataset(fd["X_tr"][:cut], label=fd["y_tr"][:cut])
        lgb_val = lgb.Dataset(fd["X_tr"][cut:], label=fd["y_tr"][cut:], reference=lgb_tr)
    else:
        lgb_tr  = lgb.Dataset(fd["X_tr"][:cut], label=fd["y_tr"][:cut], weight=w[:cut])
        lgb_val = lgb.Dataset(fd["X_tr"][cut:], label=fd["y_tr"][cut:], weight=w[cut:], reference=lgb_tr)
    m = lgb.train(LGBM_PARAMS, lgb_tr, num_boost_round=500,
                  valid_sets=[lgb_val],
                  callbacks=[lgb.early_stopping(50, verbose=False),
                             lgb.log_evaluation(0)])
    return m.predict(fd["X_te"])


class BettingMLP(nn.Module):
    def __init__(self, n_in, hidden=MLP_HIDDEN, dropout=MLP_DROPOUT):
        super().__init__()
        layers = []
        prev = n_in
        for h, d in zip(hidden, dropout):
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(d)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)
    def forward(self, x): return self.net(x).squeeze(1)


def run_mlp(fd, w):
    sc = StandardScaler().fit(fd["X_tr"])
    Xtr = torch.tensor(sc.transform(fd["X_tr"]), dtype=torch.float32)
    Xte = torch.tensor(sc.transform(fd["X_te"]), dtype=torch.float32)
    ytr = torch.tensor(fd["y_tr"], dtype=torch.float32)
    if w is None:
        wtr = torch.ones_like(ytr)
    else:
        wtr = torch.tensor(w, dtype=torch.float32)

    net = BettingMLP(fd["X_tr"].shape[1]).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-4, weight_decay=1e-4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=MLP_EPOCHS)
    loss_fn = nn.HuberLoss(delta=7.0, reduction='none')
    dl = DataLoader(TensorDataset(Xtr, ytr, wtr), batch_size=64, shuffle=True)
    for _ in range(MLP_EPOCHS):
        net.train()
        for xb, yb, wb in dl:
            xb, yb, wb = xb.to(device), yb.to(device), wb.to(device)
            opt.zero_grad()
            per_sample = loss_fn(net(xb), yb)
            (per_sample * wb).mean().backward()
            opt.step()
        sch.step()
    net.eval()
    with torch.no_grad():
        return net(Xte.to(device)).cpu().numpy()


MODELS = [
    ("XGBoost",       run_xgb),
    ("Ridge",         run_ridge),
    ("Random Forest", run_rf),
    ("LightGBM",      run_lgbm),
    ("MLP",           run_mlp),
]


def cv_eval(run_fn, alpha, fold_data, ats_acc):
    accs, maes = [], []
    for fd in fold_data:
        w = decay_weights(fd, alpha)
        preds = run_fn(fd, w)
        accs.append(ats_acc(preds, fd["sp"], fd["y_te"]))
        maes.append(float(np.abs(preds - fd["y_te"]).mean()))
    return {"alpha": alpha, "fold_ats": accs, "fold_mae": maes,
            "mean_ats": float(np.mean(accs)), "std_ats": float(np.std(accs)),
            "min_ats": float(np.min(accs)), "max_ats": float(np.max(accs)),
            "mean_mae": float(np.mean(maes))}


# ── 4. Run sweep ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", type=str, default="0,0.05,0.10,0.15,0.20",
                    help="Comma-separated α values to sweep.")
    ap.add_argument("--train-starts", type=str, default="2014",
                    help="Comma-separated TRAIN_SEASONS start years to sweep. "
                         "Single value = Pass 1 mode; multiple values = Pass 2/3 mode.")
    ap.add_argument("--earliest", type=int, default=None,
                    help="Override the data-load lower bound (default = min "
                         "of --train-starts). Set < 2014 to extend ALL_SEASONS "
                         "and reload PBP/injuries/etc. for the wider range.")
    ap.add_argument("--out", type=str, default="time_decay_results.json",
                    help="Output JSON filename (in betting/experiments/).")
    ap.add_argument("--label", type=str, default="Pass 1",
                    help="Free-text pass label written to the JSON.")
    args = ap.parse_args()
    alphas = [float(x) for x in args.alphas.split(",")]
    train_starts = [int(x) for x in args.train_starts.split(",")]
    earliest = args.earliest if args.earliest is not None else min(train_starts)
    print(f"\n{args.label}: sweeping α = {alphas} × train_start = {train_starts} (earliest data = {earliest})")

    # Load data prep cells with the requested earliest year. If earliest < 2014,
    # this extends ALL_SEASONS and triggers a longer PBP/injury load.
    ns = load_prep_cells(earliest=earliest)
    ats_acc = ns['ats_acc']

    # COVERAGE GATE — for any train_start before 2014, verify that
    # adding the pre-2014 rows doesn't introduce a mechanical zero-fill
    # shift on any feature. This catches things like pre-2009 injuries
    # (100% zero) or pre-2006 AllPro (100% zero before the floor fix).
    # Structural features that are uniformly zero (like is_playoff)
    # don't trigger because the SHIFT vs baseline is small.
    verify_coverage(ns, train_starts, max_zero_shift_pp=25.0,
                    baseline_anchor=2014, hard_fail=True)

    # Pre-build fold data per train_start so we only build it once
    fold_data_by_start = {ts: build_fold_data(make_cv_folds(ts), ns) for ts in train_starts}
    print(f"CV fold sets prepared: {len(fold_data_by_start)}")
    for ts in train_starts:
        n_tr = sum(fd["n_train"] for fd in fold_data_by_start[ts])
        n_te = sum(len(fd["y_te"]) for fd in fold_data_by_start[ts])
        print(f"  train_start={ts}+ : total train rows across 6 folds = {n_tr:,}, total test rows = {n_te:,}")
    print()

    # results[(train_start, alpha)] = {model_name: result_dict}
    results = []
    for train_start in train_starts:
        fold_data = fold_data_by_start[train_start]
        for model_name, run_fn in MODELS:
            for alpha in alphas:
                t = time.time()
                r = cv_eval(run_fn, alpha, fold_data, ats_acc)
                r["train_start"] = train_start
                r["model"] = model_name
                results.append(r)
                tag = "[baseline]" if (alpha == 0 and train_start == 2014) else ""
                print(f"  train={train_start}+  {model_name:14}  α={alpha:.2f}  "
                      f"mean={r['mean_ats']:.1%}  std={r['std_ats']:.1%}  "
                      f"MAE={r['mean_mae']:.2f}  ({time.time()-t:.1f}s) {tag}")

    # Save JSON
    out_path = HERE / args.out
    out_path.write_text(json.dumps({
        "label": args.label,
        "alphas": alphas,
        "train_starts": train_starts,
        "earliest_loaded": earliest,
        "results": results,
    }, indent=2))
    print(f"\nWrote {out_path}")

    # Summary table by (train_start × α) for XGBoost
    print(f"\n{'='*78}\n  SUMMARY — XGBoost mean ATS by (train_start × α)")
    print('='*78)
    header = "  α      " + "  ".join(f"train={ts:4}+" for ts in train_starts)
    print(header)
    for alpha in alphas:
        row = f"  {alpha:.2f}   "
        for ts in train_starts:
            r = next(x for x in results if x["model"] == "XGBoost"
                     and x["train_start"] == ts and x["alpha"] == alpha)
            row += f"  {r['mean_ats']:.1%} ± {r['std_ats']:.1%}"
        print(row)


if __name__ == "__main__":
    main()
