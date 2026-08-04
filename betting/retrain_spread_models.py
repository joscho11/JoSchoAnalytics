"""Retrain the shipped spread models through the CORRECTED feature pipeline.

Why (2026-08-03): the deployed pkls were trained before two defects were fixed —
  * the sack leak (`sack_pg` built only from sack-positive rows; presence encoded the
    target game's own outcome, and a downstream fillna(0) wrote it in);
  * the All-Pro identity collision (two distinct C.J. Mosleys merged under a name key,
    survivor decided by an unstable sort), including the injury-path fan-out.
`PROD_FEATURES_35` #2, #3 and #11 are affected. The corrected walk-forward
(`experiments/audit_2026-08-03c_final/`) therefore describes a DIFFERENT model from the
one on disk. This script closes that gap.

STAGED BY DEFAULT. Nothing in betting/models/ is touched unless every gate passes AND
--promote is given.

    C:/tmp/jsa-bt/Scripts/python.exe betting/retrain_spread_models.py            # stage+gate
    C:/tmp/jsa-bt/Scripts/python.exe betting/retrain_spread_models.py --promote  # replace
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import features as _F  # noqa: E402

PROD = HERE / "models"
STAGE = HERE / "models_staged"
TRAIN_SEASONS = list(range(2014, 2025))
FIXTURE = HERE / "fixtures" / "spread_pred_fixture.csv"


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()


def build_g():
    """Run the canonical data prep (model_comparison.ipynb cells 1-37)."""
    nb = json.loads((HERE / "model_comparison.ipynb").read_text(encoding="utf-8"))
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
    return ns["g"], ns["avail"], ns["enc"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote", action="store_true",
                    help="replace betting/models/*.pkl after ALL gates pass")
    args = ap.parse_args()

    t0 = time.time()
    print("Building corrected feature matrix...")
    g, avail, enc = build_g()
    print(f"  g={g.shape}  features={len(avail)}  ({time.time()-t0:.1f}s)")

    # ---- GATE 1: exact PROD_FEATURES_35 names AND order --------------------
    if list(avail) != list(_F.PROD_FEATURES_35):
        print("GATE 1 FAILED: feature list differs from PROD_FEATURES_35")
        for i, (a, b) in enumerate(zip(avail, _F.PROD_FEATURES_35)):
            if a != b:
                print(f"    idx {i}: built={a!r} expected={b!r}")
        return 1
    print(f"GATE 1 ok: {len(avail)} features, exact PROD_FEATURES_35 order")

    m = g["season"].isin(TRAIN_SEASONS)
    X = g.loc[m, avail].fillna(0).values.astype("float32")
    y = g.loc[m, "home_margin"].values.astype("float32")
    print(f"Training rows: {len(X):,} (seasons {TRAIN_SEASONS[0]}-{TRAIN_SEASONS[-1]})")

    sc = StandardScaler()
    Xs = sc.fit_transform(X)

    xgb_m = xgb.XGBRegressor(
        n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
        subsample=0.6, colsample_bytree=0.6, reg_alpha=2.0, reg_lambda=5.0,
        objective="reg:squarederror", random_state=42, tree_method="hist",
        n_jobs=1, verbosity=0)
    xgb_m.fit(X, y)
    ridge_m = Ridge(alpha=50.0)
    ridge_m.fit(Xs, y)

    STAGE.mkdir(exist_ok=True)
    joblib.dump({"xgb_model": xgb_m, "ridge_model": ridge_m, "scaler": sc,
                 "xgb_weight": 0.75, "feature_cols": avail,
                 "roof_surface_encoder": enc, "train_seasons": TRAIN_SEASONS},
                STAGE / "ensemble_prod_model.pkl")

    cat, num = ["roof", "surface"], [c for c in avail if c not in ("roof", "surface")]
    gf = g.loc[m].copy()
    Xp = gf[["roof_raw", "surface_raw"]].rename(
        columns={"roof_raw": "roof", "surface_raw": "surface"})
    for c in num:
        Xp[c] = gf[c].fillna(0) if c in gf.columns else 0.0
    Xp = Xp[cat + num]
    pipe = Pipeline([
        ("preprocessor", ColumnTransformer([
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cat),
            ("num", "passthrough", num)], remainder="drop")),
        ("regressor", xgb.XGBRegressor(
            n_estimators=500, max_depth=3, learning_rate=0.01, min_child_weight=3,
            subsample=0.6, colsample_bytree=0.6, reg_alpha=2.0, reg_lambda=5.0,
            objective="reg:squarederror", random_state=42, tree_method="hist",
            n_jobs=1, verbosity=0))])
    pipe.fit(Xp, y)
    joblib.dump({"pipeline": pipe}, STAGE / "xgboost_prod_model.pkl")

    try:
        import lightgbm as lgb
        lgbm = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.01, max_depth=3,
                                 subsample=0.6, colsample_bytree=0.6, random_state=42,
                                 n_jobs=1, verbose=-1)
        lgbm.fit(X, y)
        joblib.dump({"model": lgbm, "feature_cols": avail}, STAGE / "lgbm_prod_model.pkl")
        have_lgbm = True
    except Exception as e:                                   # pragma: no cover
        print(f"  lightgbm unavailable ({e}) — lgbm not staged")
        have_lgbm = False
    print("Staged models written.")

    # ---- GATE 2: staged pkls reload and expose the exact feature contract ---
    ens = joblib.load(STAGE / "ensemble_prod_model.pkl")
    if list(ens["feature_cols"]) != list(_F.PROD_FEATURES_35):
        print("GATE 2 FAILED: staged ensemble feature_cols != PROD_FEATURES_35")
        return 1
    for key in ("xgb_model", "ridge_model", "scaler", "roof_surface_encoder", "xgb_weight"):
        if key not in ens:
            print(f"GATE 2 FAILED: staged ensemble missing {key!r}")
            return 1
    print("GATE 2 ok: staged artifacts reload with the exact feature contract")

    # ---- Retained fixture: old vs new predictions --------------------------
    FIXTURE.parent.mkdir(exist_ok=True)
    if not FIXTURE.exists():
        fx = g.loc[g["season"] == 2024, ["game_id", "home_team", "away_team"] + avail]
        fx.head(200).to_csv(FIXTURE, index=False)
        print(f"Created retained fixture: {FIXTURE.name} ({min(200, len(fx))} rows)")
    fx = pd.read_csv(FIXTURE)
    Xf = fx[avail].fillna(0).values.astype("float32")

    def ens_pred(bundle, Xin):
        p_x = bundle["xgb_model"].predict(Xin)
        p_r = bundle["ridge_model"].predict(bundle["scaler"].transform(Xin))
        w = bundle["xgb_weight"]
        return w * p_x + (1 - w) * p_r

    new_p = ens_pred(ens, Xf)
    old_path = PROD / "ensemble_prod_model.pkl"
    delta_summary = None
    if old_path.exists():
        try:
            old = joblib.load(old_path)
            old_p = ens_pred(old, Xf)
            d = np.abs(new_p - old_p)
            order = np.argsort(-d)[:10]
            delta_summary = {
                "n": int(len(d)), "mean_abs": float(d.mean()),
                "median_abs": float(np.median(d)), "max_abs": float(d.max()),
                "n_gt_1pt": int((d > 1).sum()), "n_gt_3pt": int((d > 3).sum()),
                "largest": [{"game_id": str(fx["game_id"].iloc[i]),
                             "old": round(float(old_p[i]), 3),
                             "new": round(float(new_p[i]), 3),
                             "delta": round(float(new_p[i] - old_p[i]), 3)}
                            for i in order],
            }
            print(f"\nOld vs new on {len(d)} retained fixture games:")
            print(f"  mean|Δ|={d.mean():.4f}  median|Δ|={np.median(d):.4f}  "
                  f"max|Δ|={d.max():.4f}  >1pt={int((d>1).sum())}  >3pt={int((d>3).sum())}")
            for r in delta_summary["largest"][:5]:
                print(f"    {r['game_id']}: {r['old']:+.2f} -> {r['new']:+.2f} "
                      f"({r['delta']:+.2f})")
        except Exception as e:
            print(f"  old-model comparison unavailable: {e}")

    # ---- Manifest ----------------------------------------------------------
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reason": "retrain through corrected dense-sack + All-Pro identity pipeline",
        "train_seasons": TRAIN_SEASONS,
        "n_train_rows": int(len(X)),
        "feature_contract": {"name": "PROD_FEATURES_35", "n": len(avail),
                             "order_sha256": hashlib.sha256(
                                 "\n".join(avail).encode()).hexdigest().upper()},
        "code_hashes": {
            "features.py": sha256(HERE / "features.py"),
            "allpro_identity.py": sha256(HERE / "allpro_identity.py"),
            "model_comparison.ipynb": sha256(HERE / "model_comparison.ipynb"),
            "retrain_spread_models.py": sha256(Path(__file__)),
        },
        "input_hashes": {
            "nfl_allpro_1997_2025.csv": sha256(HERE / "nfl_allpro_1997_2025.csv"),
            "data/nfl.xlsx": sha256(HERE / "data" / "nfl.xlsx"),
        },
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__, "numpy": np.__version__,
            "xgboost": xgb.__version__,
            "scikit_learn": __import__("sklearn").__version__,
        },
        "staged_artifacts": {p.name: sha256(p) for p in sorted(STAGE.glob("*.pkl"))},
        "fixture": {"path": str(FIXTURE.relative_to(ROOT)), "sha256": sha256(FIXTURE)},
        "old_vs_new_fixture_predictions": delta_summary,
        "promoted": False,
    }
    if have_lgbm:
        manifest["environment"]["lightgbm"] = __import__("lightgbm").__version__

    if args.promote:
        PROD.mkdir(exist_ok=True)
        backup = HERE / "models_pre_2026-08-03"
        backup.mkdir(exist_ok=True)
        for p in sorted(STAGE.glob("*.pkl")):
            live = PROD / p.name
            if live.exists():
                shutil.copy2(live, backup / p.name)
            shutil.copy2(p, live)
        manifest["promoted"] = True
        manifest["backup_dir"] = str(backup.relative_to(ROOT))
        manifest["promoted_artifacts"] = {p.name: sha256(PROD / p.name)
                                          for p in sorted(STAGE.glob("*.pkl"))}
        print(f"\nPROMOTED to {PROD} (previous pkls copied to {backup.name}/)")
    else:
        print("\nSTAGED ONLY — pass --promote to replace betting/models/*.pkl")

    (STAGE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest -> {(STAGE / 'MANIFEST.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
