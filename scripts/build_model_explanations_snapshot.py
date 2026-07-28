"""Regenerate the Help-page model explanation snapshot.

Run from the repository root after intentionally replacing a covered model:
    python scripts/build_model_explanations_snapshot.py

Tree SHAP summaries still require an explicit recomputation and corresponding
SHAP_SNAPSHOTS update; this script refuses to bless them against a new artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import model_explanations as me


def _native_models() -> tuple[list[dict], list[Path]]:
    models = []
    paths = sorted((ROOT / "fantasy" / "models").glob("*_model.pkl"))
    for path in paths:
        bundle = joblib.load(path)
        values = np.asarray(bundle["model"].feature_importances_, dtype=float)
        values = 100 * values / values.sum()
        top = np.argsort(values)[::-1][:5]
        stem = path.stem.removesuffix("_model")
        parts = stem.split("_")
        position = parts[0].upper()
        target = " ".join(parts[1:]).replace("rec yards", "receiving yards")
        label = f"{position} · {target.title()}" if target else f"{position} · Fantasy points"
        models.append({
            "id": f"weekly_{stem}",
            "label": label,
            "group": "Weekly fantasy",
            "subgroup": position,
            "method": "XGBoost gain",
            "features": [
                (me._feature(bundle["feature_cols"][i]), round(float(values[i]), 1))
                for i in top
            ],
        })

    for filename, label in (
        ("totals_xgboost.pkl", "Totals · XGBoost"),
        ("totals_ridge.pkl", "Totals · Ridge"),
    ):
        path = ROOT / "betting" / "models" / filename
        paths.append(path)
        bundle = joblib.load(path)
        if filename.startswith("totals_xgboost"):
            values = np.asarray(bundle["model"].feature_importances_, dtype=float)
            method = "XGBoost gain"
        else:
            values = np.abs(np.asarray(bundle["model"].coef_, dtype=float))
            method = "absolute standardized coefficient"
        values = 100 * values / values.sum()
        top = np.argsort(values)[::-1][:5]
        models.append({
            "id": filename.removesuffix(".pkl"),
            "label": label,
            "group": "Betting",
            "method": method,
            "features": [
                (me._feature(bundle["feature_cols"][i]), round(float(values[i]), 1))
                for i in top
            ],
        })
    return models, paths


def build_snapshot() -> dict:
    shap_models = []
    source_paths = []
    for model_id, label, group, rel, expected, n_rows, features in me.SHAP_SNAPSHOTS:
        path = ROOT / rel
        actual = me._md5(path)
        if actual != expected:
            raise RuntimeError(
                f"{rel} changed ({actual}); recompute its Tree SHAP summary before "
                "updating SHAP_SNAPSHOTS"
            )
        source_paths.append(path)
        shap_models.append({
            "id": model_id,
            "label": label,
            "group": group,
            "method": "mean absolute Tree SHAP",
            "n": n_rows,
            "features": [(me._feature(name), share) for name, share in features],
        })

    native_models, native_paths = _native_models()
    source_paths.extend(native_paths)
    sources = {
        path.relative_to(ROOT).as_posix(): me._md5(path)
        for path in sorted(set(source_paths))
    }
    return {
        "schema_version": 1,
        "shap_models": shap_models,
        "native_models": native_models,
        "sources": sources,
    }


if __name__ == "__main__":
    payload = json.dumps(build_snapshot(), indent=2, sort_keys=True) + "\n"
    me.SNAPSHOT_PATH.write_text(payload, encoding="utf-8")
    print(f"Wrote {me.SNAPSHOT_PATH.relative_to(ROOT)}")
