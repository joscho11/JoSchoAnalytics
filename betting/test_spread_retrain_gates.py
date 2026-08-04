"""Gates the retrained spread models must pass before promotion.

The deployed pkls predate the dense-sack and All-Pro identity fixes, so they encode
features the corrected walk-forward no longer uses. These tests check the retrained
artifacts are contract-correct and that the SERVING path agrees with the TRAINING path.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

_B = Path(__file__).resolve().parent
if str(_B) not in sys.path:
    sys.path.insert(0, str(_B))

import features as F  # noqa: E402

STAGE = _B / "models_staged"
pytestmark = pytest.mark.skipif(
    not (STAGE / "ensemble_prod_model.pkl").exists(),
    reason="run betting/retrain_spread_models.py first")


def test_staged_ensemble_feature_order_is_exactly_prod_features_35():
    b = joblib.load(STAGE / "ensemble_prod_model.pkl")
    assert list(b["feature_cols"]) == list(F.PROD_FEATURES_35)
    assert len(b["feature_cols"]) == 35


def test_staged_bundle_carries_every_required_component():
    b = joblib.load(STAGE / "ensemble_prod_model.pkl")
    for k in ("xgb_model", "ridge_model", "scaler", "roof_surface_encoder",
              "xgb_weight", "train_seasons"):
        assert k in b, f"missing {k}"
    assert b["xgb_weight"] == 0.75
    assert list(b["train_seasons"]) == list(range(2014, 2025))


def test_xgboost_pipeline_keeps_the_preprocessor_step_name():
    """predict_betting relies on a step literally named 'preprocessor'."""
    p = joblib.load(STAGE / "xgboost_prod_model.pkl")["pipeline"]
    assert "preprocessor" in dict(p.named_steps)


def test_manifest_records_provenance():
    m = json.loads((STAGE / "MANIFEST.json").read_text(encoding="utf-8"))
    for k in ("created_utc", "train_seasons", "code_hashes", "input_hashes",
              "environment", "staged_artifacts", "feature_contract"):
        assert k in m and m[k], f"manifest missing {k}"
    assert m["feature_contract"]["n"] == 35
    for f in ("features.py", "allpro_identity.py", "model_comparison.ipynb"):
        assert len(m["code_hashes"][f]) == 64


def test_staged_models_predict_finite_values_on_the_retained_fixture():
    fx = pd.read_csv(_B / "fixtures" / "spread_pred_fixture.csv")
    b = joblib.load(STAGE / "ensemble_prod_model.pkl")
    X = fx[F.PROD_FEATURES_35].fillna(0).values.astype("float32")
    p = 0.75 * b["xgb_model"].predict(X) + 0.25 * b["ridge_model"].predict(
        b["scaler"].transform(X))
    assert np.isfinite(p).all()
    assert p.std() > 1.0, "predictions are ~constant — the model did not train"
    assert np.abs(p).max() < 60, "implausible margin magnitude"


def test_target_game_sacks_cannot_affect_pregame_features():
    """Re-assert the leak guard at the model boundary (detail in test_sack_leak.py)."""
    from test_sack_leak import _pbp, _wk_lookup
    base = None
    for target_sacks in (0, 3, 9):
        counts = {1: 3, 2: 2, 3: 0, 4: 4, 5: target_sacks}
        prior = {f"g{w}" for w in (1, 2, 3, 4)}
        pbp = _pbp(counts)
        wk = _wk_lookup(sorted(counts))
        out = F._build_situational_pbp(
            pd.DataFrame([{"home_team": "KC", "away_team": "OPP"}]),
            pbp[pbp.game_id.isin(prior)], wk[wk.game_id.isin(prior)])
        v = float(out["home_rolling_sacks"].iloc[0])
        if base is None:
            base = v
        assert v == base == 2.25


def test_training_and_serving_allpro_agree_on_the_same_team_season():
    """Serving `_build_allpro` must equal the shared primitive the notebook now uses."""
    from allpro_identity import resolve_allpro_identities, weighted_lookback
    ap = pd.read_csv(_B / "nfl_allpro_1997_2025.csv")
    ap = ap[ap["Team"] != "2TM"].copy()
    ap["Team"] = ap["Team"].replace(F.TEAM_MAP)
    r = resolve_allpro_identities(ap)
    for season in (2017, 2021, 2024):
        w = weighted_lookback(r, season).set_index("Team")["allpro_weighted"]
        served = F._build_allpro(
            pd.DataFrame([{"home_team": "KC", "away_team": "SF"}]), ap, season)
        assert float(served["home_allpro_last_3_years_weighted"].iloc[0]) == \
            float(w.get("KC", 0.0)), f"KC mismatch in {season}"
        assert float(served["away_allpro_last_3_years_weighted"].iloc[0]) == \
            float(w.get("SF", 0.0)), f"SF mismatch in {season}"
