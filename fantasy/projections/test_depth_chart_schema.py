"""Regression tests for the two-schema depth-chart parse in build_rb_projection.py.

nflverse changed depth-chart providers for 2025: <=2024 are weekly charts
(season/club_code/week/game_type/position/depth_team), 2025+ are ESPN daily snapshots
(dt/team/pos_abb/pos_slot/pos_rank) with no season and no position/depth_team column. The old
single `position == "RB"` filter silently dropped 100% of 2025 and 2026.

These tests are hermetic: both nflreadpy loaders are monkeypatched with synthetic frames, so
they run offline and the as-of rule can be exercised deterministically. The final test is pure
local file I/O and asserts that this parsing fix moved no protected artifact.

Run:  .venv-test\\Scripts\\python.exe -m pytest -q fantasy/projections/test_depth_chart_schema.py
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO / "fantasy" / "seasonal_projections"))

import nflreadpy
import build_rb_projection as B


# ----------------------------------------------------------------------------- synthetic feeds
def _legacy_frame():
    """<=2024 weekly schema. Week 1 and week 2 rows so the MIN-REG-week rule is exercised, plus
    a POST row and a non-RB row that must both be filtered out."""
    return pd.DataFrame([
        # (season, club_code, week, game_type, depth_team, position, gsis_id)
        (2024, "JAX", 1, "REG", "1", "RB", "00-A"),
        (2024, "JAX", 2, "REG", "2", "RB", "00-A"),      # later week: must lose to week 1
        (2024, "JAX", 1, "REG", "2", "RB", "00-B"),
        (2024, "JAX", 1, "REG", "3", "RB", "00-C"),
        (2024, "JAX", 1, "POST", "1", "RB", "00-D"),     # POST: filtered out
        (2024, "JAX", 1, "REG", "1", "WR", "00-E"),      # wrong position: filtered out
        (2023, "BAL", 2, "REG", "1", "RB", "00-A"),      # same player, earlier season
    ], columns=["season", "club_code", "week", "game_type", "depth_team", "position", "gsis_id"])


_KICKOFF = "2025-09-04"


def _modern_frame():
    """2025+ ESPN daily-snapshot schema. Three snapshot dates: two strictly before kickoff and
    one AFTER it. The as-of rule must select the latest PRE-kickoff snapshot."""
    rows = []
    for dt, ranks in [
        ("2025-08-01T09:00:00Z", {"00-A": 1, "00-B": 2, "00-C": 3, "00-D": 4}),   # stale
        ("2025-08-20T09:00:00Z", {"00-B": 1, "00-A": 2, "00-C": 3, "00-D": 4}),   # the as-of one
        ("2025-09-20T09:00:00Z", {"00-C": 1, "00-A": 2, "00-B": 3, "00-D": 4}),   # post-kickoff
    ]:
        for gsis, rk in ranks.items():
            rows.append((dt, "JAX", gsis, "RB", 11, rk))
        rows.append((dt, "JAX", "00-Z", "WR", 3, 1))     # wrong position: filtered out
    return pd.DataFrame(rows, columns=["dt", "team", "gsis_id", "pos_abb", "pos_slot", "pos_rank"])


def _sched_frame():
    return pd.DataFrame({"game_type": ["PRE", "REG", "REG"],
                         "gameday": ["2025-08-08", _KICKOFF, "2025-09-11"]})


@pytest.fixture
def feeds(monkeypatch):
    def fake_depth(seasons=None, **kw):
        """Faithful stand-in: nflreadpy honours the `seasons` argument, so the fake must too.
        The legacy branch filters on its own `season` column; the new feed has none, so a
        request for any new-feed season returns that season's snapshots."""
        seasons = list(seasons or [])
        if any(s >= B.NEW_FEED_FIRST_SEASON for s in seasons):
            return _modern_frame()
        return _legacy_frame().query("season in @seasons")

    monkeypatch.setattr(nflreadpy, "load_depth_charts", fake_depth)
    monkeypatch.setattr(nflreadpy, "load_schedules", lambda seasons=None, **kw: _sched_frame())


# ------------------------------------------------------------------------------------- tests
def test_both_schemas_are_parsed(feeds):
    """The whole point of the fix: legacy AND new-feed seasons both produce rows."""
    out = B.depth_rank_table(position="RB", seasons=[2023, 2024, 2025])
    seasons = set(out.season.tolist())
    assert 2024 in seasons and 2023 in seasons, "legacy seasons dropped"
    assert 2025 in seasons, "new-feed season still dropped (the bug)"
    assert list(out.columns) == ["gsis_id", "season", "depth_rank", B.DEPTH_SRC]
    assert out.season.dtype == np.int64 and out.depth_rank.dtype == np.int64


def test_new_feed_seasons_are_not_dropped(feeds):
    """2025 and 2026 must each yield rows; under the old filter both were empty."""
    for s in (2025, 2026):
        out = B.depth_rank_table(position="RB", seasons=[s])
        assert len(out) > 0, f"{s} produced no rows"
        assert set(out.season) == {s}


def test_raw_source_rank_is_preserved(feeds):
    """The provider's own pos_rank survives verbatim in source_pos_rank; legacy has none."""
    out = B.depth_rank_table(position="RB", seasons=[2024, 2025])
    new = out[out.season == 2025].set_index("gsis_id")
    # the as-of snapshot is 2025-08-20, where B is rank 1 and A is rank 2
    assert new.loc["00-B", B.DEPTH_SRC] == 1
    assert new.loc["00-A", B.DEPTH_SRC] == 2
    legacy = out[out.season == 2024]
    assert legacy[B.DEPTH_SRC].isna().all(), "legacy feed has no provider rank to preserve"


def test_new_feed_canonical_tiers_restricted_to_1_and_2(feeds):
    """Deeper camp-roster players are left UNLISTED, not fabricated into a tier."""
    out = B.depth_rank_table(position="RB", seasons=[2025])
    assert set(out.depth_rank.unique()) <= {1, 2}, "canonical tier escaped 1-2"
    assert set(out.gsis_id) == {"00-A", "00-B"}, "tier-3+ players must not be emitted"
    assert "00-C" not in set(out.gsis_id) and "00-D" not in set(out.gsis_id)


def test_duplicate_daily_snapshots_resolve_to_the_as_of_date(feeds):
    """Many snapshots per season: take the LAST one strictly BEFORE the first REG gameday.
    Here that is 2025-08-20 (B ahead of A), never the stale 08-01 or the post-kickoff 09-20."""
    out = B.depth_rank_table(position="RB", seasons=[2025]).set_index("gsis_id")
    assert out.loc["00-B", "depth_rank"] == 1, "did not use the latest pre-kickoff snapshot"
    assert out.loc["00-A", "depth_rank"] == 2
    assert len(out) == 2 and not out.index.duplicated().any(), "one row per player per season"


def test_legacy_uses_min_reg_week_and_filters_post_and_other_positions(feeds):
    """Legacy behaviour is unchanged: season-open (min REG week) row, REG only, RB only."""
    out = B.depth_rank_table(position="RB", seasons=[2024]).set_index("gsis_id")
    assert out.loc["00-A", "depth_rank"] == 1, "min-REG-week row not used"
    assert set(out.index) == {"00-A", "00-B", "00-C"}, "POST or non-RB rows leaked in"
    assert out.loc["00-C", "depth_rank"] == 3, "legacy tiers are not capped"


def test_depth_columns_are_in_no_feature_pool():
    """Amendment 1 stands: this is a parsing and disclosure correction only."""
    for pool in (B.VET_ALL, B.ROOK_ALL, B.VET_FEATS):
        for col in (B.DEPTH, B.DEPTH_SRC):
            assert col not in pool, f"{col} leaked into a production feature pool"
        assert not [c for c in pool if "depth_team" in c or "depth_chart" in c]


def test_no_protected_artifact_changed():
    """No model pkl and no existing projection/result CSV may move for a parsing fix."""
    models = _REPO / "fantasy" / "projections" / "models"
    results = _REPO / "fantasy" / "projections" / "results"
    pinned_pkl = {
        "qb_veteran_model.pkl": "7632549f95995b9702baefdf016d7271",
        "rb_rookie_model.pkl": "da230ee66575ca574f02cbc2139e1a80",
        "rb_veteran_model.pkl": "167aca71a8511afcced37c0abc846004",
        "te_rookie_model.pkl": "f79dad0ab26af5cb4e06a9f1723328cd",
        "te_veteran_model.pkl": "5a2f0b504d4cc6fc9a2e04453fd76a44",
        "wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
        "wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
    }
    pinned_csv = {
        "qb_projection_2026.csv": "0cd86fa33437677e6ca66bfe1f190c95",
        "qb_rookie_board_projection.csv": "e73620343a76b6fcd1e430f7f37cafa2",
        "qb_sleeper_comparison.csv": "bd4d558371e255968bd89913103341bf",
        "qb_walkforward_predictions.csv": "fff920ee50f6fa022ae6a81f0b042091",
        "rb_projection_2026.csv": "6e203fb41f282fad6b85333e41b6a757",
        "rb_rookie_board_projection.csv": "2dc5935b914d845c19dbc0f1efc2401d",
        "sleeper_comparison.csv": "0752a65b60248efc4ea6e1fd349472fa",
        "te_projection_2026.csv": "0fa323be7ac32ca4d993b226eee6f345",
        "te_rookie_board_projection.csv": "0f951d8868987fcee2cb02e7f33ece02",
        "te_sleeper_comparison.csv": "9b2b41db7ecade0caee3ee2134999f47",
        "te_walkforward_predictions.csv": "ff696393b529a21c4cea480ccbbf8c0c",
        "walkforward_predictions.csv": "eb2a810153ee17084beb284be70e3787",
        "wr_projection_2026.csv": "4ed5699367ece695399d5d9dcdea5d11",
        "wr_rookie_board_projection.csv": "074324aef05057c734c262721f71b192",
        "wr_sleeper_comparison.csv": "00263f195ec9fa28e5f95b4812f158cd",
        "wr_walkforward_predictions.csv": "f78723f0fc3d45ca1bca5af3a82cd721",
    }
    rookie_ppg = _REPO / "fantasy" / "seasonal_projections" / "models" / "rookie_ppg_model.pkl"

    def md5(p):
        return hashlib.md5(p.read_bytes()).hexdigest()

    for name, want in pinned_pkl.items():
        assert md5(models / name) == want, f"{name} CHANGED"
    for name, want in pinned_csv.items():
        assert md5(results / name) == want, f"{name} CHANGED"
    assert md5(rookie_ppg) == "872467b2295fce27761f9e04da01b6e8", "rookie_ppg_model.pkl CHANGED"
