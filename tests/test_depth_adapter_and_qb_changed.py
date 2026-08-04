"""Dual-schema depth adapter + 2026 qb_changed. Fail-closed, never default to zero."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_R / "fantasy"))

from depth_adapter import (DepthSchemaError, as_of_snapshot,  # noqa: E402
                           assert_season_invariants, detect_schema,
                           normalize_depth_charts)

_LEGACY = pd.DataFrame([
    {"season": 2024, "club_code": "KC", "week": 1, "game_type": "REG",
     "depth_team": "1", "position": "QB", "football_name": "Patrick Mahomes"},
    {"season": 2024, "club_code": "KC", "week": 1, "game_type": "REG",
     "depth_team": "2", "position": "QB", "football_name": "Backup Guy"},
])
_CURRENT = pd.DataFrame([
    {"dt": "2026-08-02T09:06:30Z", "team": "KC", "player_name": "Patrick Mahomes",
     "gsis_id": "00-0033873", "pos_abb": "QB", "pos_rank": 1},
    {"dt": "2026-08-02T09:06:30Z", "team": "KC", "player_name": "Backup Guy",
     "gsis_id": "00-0000001", "pos_abb": "QB", "pos_rank": 2},
])


def test_detects_each_schema():
    assert detect_schema(_LEGACY) == "legacy"
    assert detect_schema(_CURRENT) == "current"


def test_both_schemas_normalise_to_the_same_shape():
    for df in (_LEGACY, _CURRENT):
        n = normalize_depth_charts(df)
        assert {"season", "team", "position", "depth_rank"} <= set(n.columns)
        assert len(n) == 2
        assert set(n["position"]) == {"QB"}
        assert sorted(n["depth_rank"]) == [1.0, 2.0]


def test_an_unknown_schema_aborts():
    with pytest.raises(DepthSchemaError):
        normalize_depth_charts(pd.DataFrame([{"nonsense": 1}]))


def test_a_season_selecting_nothing_aborts_rather_than_defaulting():
    """THE 2025 failure mode: a filter matching zero rows must not yield empty features."""
    n = normalize_depth_charts(_CURRENT)
    with pytest.raises(DepthSchemaError, match="normalised depth rows"):
        assert_season_invariants(n, 2099)


def test_a_constant_depth_rank_block_aborts():
    flat = pd.DataFrame([{"dt": "2026-08-02T00:00:00Z", "team": f"T{i}",
                          "player_name": f"P{i}", "gsis_id": None,
                          "pos_abb": "QB", "pos_rank": 1} for i in range(200)])
    n = normalize_depth_charts(flat)
    with pytest.raises(DepthSchemaError, match="distinct value"):
        assert_season_invariants(n, 2026)


def test_as_of_snapshot_respects_the_cutoff():
    two = pd.DataFrame([
        {"dt": "2026-07-01T00:00:00Z", "team": "KC", "player_name": "Old Starter",
         "gsis_id": None, "pos_abb": "QB", "pos_rank": 1},
        {"dt": "2026-08-02T00:00:00Z", "team": "KC", "player_name": "New Starter",
         "gsis_id": None, "pos_abb": "QB", "pos_rank": 1},
    ])
    n = normalize_depth_charts(two)
    assert as_of_snapshot(n, 2026, "QB", 1, "2026-07-15")["player_name"].tolist() == \
        ["Old Starter"]
    assert as_of_snapshot(n, 2026, "QB", 1, "2026-08-03")["player_name"].tolist() == \
        ["New Starter"]


# --- qb_changed artifact -----------------------------------------------------
_QB = _R / "fantasy" / "seasonal_projections" / "qb_changed_2026.csv"
_PROV = _R / "fantasy" / "seasonal_projections" / "qb_changed_2026.provenance.json"
_has = _QB.exists()


@pytest.mark.skipif(not _has, reason="run build_qb_changed_2026.py first")
def test_qb_changed_is_never_defaulted_to_zero():
    d = pd.read_csv(_QB)
    unresolved = d[d["qb_changed_status"].isin(["missing", "ambiguous"])]
    assert unresolved["qb_changed"].isna().all(), \
        "an unresolved team was given a numeric qb_changed — 0 is a claim, not an absence"


@pytest.mark.skipif(not _has, reason="run build_qb_changed_2026.py first")
def test_qb_changed_covers_every_team_and_has_real_variance():
    d = pd.read_csv(_QB)
    assert len(d) == 32, f"expected 32 teams, got {len(d)}"
    assert d["qb_changed"].notna().sum() == 32, "some teams unresolved"
    assert set(d["qb_changed"].dropna().unique()) == {0, 1}, \
        "qb_changed is constant — the 0%-coverage defect would recur"
    assert 1 <= int((d["qb_changed"] == 1).sum()) <= 20


@pytest.mark.skipif(not _has, reason="run build_qb_changed_2026.py first")
def test_provenance_is_recorded():
    p = json.loads(_PROV.read_text(encoding="utf-8"))
    for k in ("created_utc", "snapshot_date_requested", "snapshot_dt_max",
              "definition", "sources", "counts"):
        assert k in p and p[k], f"provenance missing {k}"
    assert "NEVER defaulted to 0" in p["definition"]["qb_changed"]
