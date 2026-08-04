"""qb_changed must be populated for every rostered 2026 row and reach all 12 consumers."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_R = Path(__file__).resolve().parents[1]
_SP = _R / "fantasy" / "seasonal_projections"
for p in (str(_SP), str(_R / "fantasy" / "projections"), str(_R / "fantasy"), str(_R)):
    sys.path.insert(0, p)

_DS = _SP / "season_dataset_2014_2026.csv"
_QBC = _SP / "qb_changed_2026.csv"
_MAN = _SP / "qb_changed_join_manifest.json"

CONSUMERS = [
    "fantasy/projections/models/qb_veteran_model.pkl",
    "fantasy/projections/models/rb_veteran_model.pkl",
    "fantasy/projections/models/rb_rookie_model.pkl",
    "fantasy/projections/models/wr_veteran_model.pkl",
    "fantasy/projections/models/wr_rookie_model.pkl",
    "fantasy/projections/models/te_veteran_model.pkl",
    "fantasy/projections/models/te_rookie_model.pkl",
    "fantasy/seasonal_projections/models/qb_ppg_model.pkl",
    "fantasy/seasonal_projections/models/rb_ppg_model.pkl",
    "fantasy/seasonal_projections/models/wr_ppg_model.pkl",
    "fantasy/seasonal_projections/models/te_ppg_model.pkl",
    "fantasy/seasonal_projections/models/rookie_ppg_model.pkl",
]


@pytest.fixture(scope="module")
def d26():
    d = pd.read_csv(_DS, low_memory=False)
    return d[d["season"] == 2026].copy()


def test_every_rostered_2026_row_has_qb_changed(d26):
    rostered = d26[d26["team"].notna()]
    assert len(rostered) == 916, f"expected 916 rostered rows, got {len(rostered)}"
    assert rostered["qb_changed"].notna().all(), (
        f"{int(rostered['qb_changed'].isna().sum())} rostered rows still unpopulated")


def test_unrostered_rows_stay_explicitly_na_never_zero(d26):
    """A team feature is undefined without a team; 0 would be a false claim."""
    un = d26[d26["team"].isna()]
    assert len(un) == 7
    assert un["qb_changed"].isna().all(), "an unsigned free agent was given a numeric value"


def test_values_match_the_artifact_team_by_team(d26):
    qbc = pd.read_csv(_QBC)
    assert len(qbc) == 32 and not qbc["team"].duplicated().any()
    want = dict(zip(qbc["team"], qbc["qb_changed"].astype(int)))
    got = d26[d26["team"].notna()].groupby("team")["qb_changed"].agg(["min", "max"])
    for team, r in got.iterrows():
        assert r["min"] == r["max"] == want[team], f"{team}: {r.to_dict()} != {want[team]}"


def test_the_feature_is_not_constant(d26):
    v = set(d26["qb_changed"].dropna().unique())
    assert v == {0, 1}, f"qb_changed is degenerate: {v}"
    assert int((d26["qb_changed"] == 1).sum()) == 199


def test_all_twelve_consumers_are_inventoried_and_carry_the_feature():
    import joblib
    found = []
    for rel in CONSUMERS:
        b = joblib.load(_R / rel)
        assert "qb_changed" in list(b["feature_cols"]), f"{rel} lost the feature"
        found.append(rel)
    assert len(found) == 12, f"expected 12 consumers, inventoried {len(found)}"


def test_every_consumer_is_sensitive_to_the_feature(d26):
    """Flipping qb_changed must move predictions — otherwise the join is cosmetic."""
    import joblib
    import numpy as np
    insensitive = []
    for rel in CONSUMERS:
        b = joblib.load(_R / rel)
        fc = list(b["feature_cols"])
        mdl = b.get("model") or b.get("estimator")
        X = d26.copy()
        for c in fc:
            if c not in X.columns:
                X[c] = np.nan
        X = X[fc]
        flip = X.copy()
        flip["qb_changed"] = 1 - X["qb_changed"].fillna(0)
        d = np.abs(np.asarray(mdl.predict(X), dtype=float)
                   - np.asarray(mdl.predict(flip), dtype=float))
        if d.max() <= 1e-9:
            insensitive.append(rel)
    assert insensitive == [], f"consumers ignore qb_changed entirely: {insensitive}"


def test_the_board_builder_no_longer_seeds_nan_unconditionally():
    src = (_SP / "build_2026_board.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert 'seed["qb_changed"] = np.nan' not in code, \
        "build_2026_board.py still seeds qb_changed as NaN unconditionally"
    assert "qb_changed_2026.csv" in code, "the artifact is not a required input"
    assert "raise FileNotFoundError" in code or "raise ValueError" in code, \
        "a missing/invalid artifact does not abort"


def test_join_manifest_records_provenance():
    m = json.loads(_MAN.read_text(encoding="utf-8"))
    for k in ("created_utc", "rows_2026", "rows_2026_rostered", "coverage_after",
              "qb_changed_source", "dataset_before_sha256", "promoted"):
        assert k in m, f"manifest missing {k}"
    assert m["promoted"] is True
    assert m["coverage_after"] == m["rows_2026_rostered"] == 916
    assert m["rows_2026_unrostered_left_na"] == 7
    assert len(m["qb_changed_source"]["sha256"]) == 64
